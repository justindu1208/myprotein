"""Target-first Boltz binder design with explicit evidence gates."""
import hashlib, json, re, threading, urllib.request, urllib.error
from pathlib import Path
from .settings import boltz_api_key
from .live_eval import save
from .harness import Policy, readiness, candidate_qc

BASE='https://api.boltz.bio/compute/v1/protein/design'
RUN=Path(__file__).resolve().parents[2]/'runs/design-live'
LOCK=threading.Lock()

def api(url, body=None):
    key=boltz_api_key()
    if not key: raise ValueError('Boltz API key missing')
    req=urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers={'x-api-key':key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=40) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        raise ValueError('Boltz API HTTP '+str(e.code)) from e

def normalize(data):
    target=data.get('target','').strip().upper()
    try:
        residues=[int(x.strip()) for x in data.get('region','').split(',') if x.strip()]
        lo,hi=int(data['min_length']),int(data['max_length'])
    except (ValueError,KeyError,TypeError): raise ValueError('Invalid target region or binder length')
    if not 10<=lo<=hi<=300: raise ValueError('Binder lengths must be 10–300')
    req={'target_sequence':target,'target_confirmed':data.get('confirmed') is True,'target_region':residues,'intended_use':data.get('intended_use','').strip(),'constraints_confirmed':data.get('confirmed') is True}
    pol=Policy('design-v1',lo,hi,.7)
    assessment=readiness(req,pol)
    if assessment.state!='PASS': return None,assessment.to_dict(),pol
    body={'num_proteins':100,'target':{'type':'no_template','entities':[{'type':'protein','value':target,'chain_ids':['A']}], 'epitope_residues':{'A':[i-1 for i in residues]}},'binder_specification':{'type':'no_template','modality':'custom_protein','entities':[{'type':'designed_protein','chain_ids':['B'],'value':f'{lo}..{hi}'}]}}
    return body,assessment.to_dict(),pol

def digest(body): return hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()

def estimate(data):
    body,ready,_=normalize(data)
    if body is None: return {'readiness':ready}
    out=api(BASE+'/estimate-cost',body)
    return {'readiness':ready,'input_hash':digest(body),'estimate':out}

def start(data):
    body,ready,_=normalize(data)
    if body is None: raise ValueError('Readiness failed')
    if data.get('input_hash')!=digest(body): raise ValueError('Inputs changed; estimate again')
    with LOCK:
        RUN.mkdir(parents=True,exist_ok=True)
        if (RUN/'attempt.json').exists(): raise ValueError('Design run already exists or submission uncertain; do not resubmit')
        save(RUN/'attempt.json',{'body':body,'status':'submission_started'})
        out=api(BASE,body)
        save(RUN/'submission.json',out)
    return {'id':out['id'],'status':out['status']}

def status():
    if not (RUN/'submission.json').exists(): return {'status':'submission_uncertain' if (RUN/'attempt.json').exists() else 'not_started'}
    run=json.loads((RUN/'submission.json').read_text()); result=api(BASE+'/'+run['id'])
    return {'id':run['id'],'status':result['status'],'progress':result.get('progress'),'livemode':result.get('livemode')}

PRED='https://api.boltz.bio/compute/v1/predictions/structure-and-binding'

def results():
    state=status()
    if state.get('status') != 'succeeded' or state.get('livemode') is not True:
        raise ValueError('Wait for a completed live design run')
    attempt=json.loads((RUN/'attempt.json').read_text())
    spec=attempt['body']['binder_specification']['entities'][0]['value']
    lo,hi=map(int,spec.split('..'))
    policy=Policy('design-v1',lo,hi,.7)
    cursor=None; records=[]; ids=set()
    while True:
        from urllib.parse import urlencode
        query={'limit':100}
        if cursor: query['after_id']=cursor
        page=api(BASE+'/'+state['id']+'/results?'+urlencode(query))
        for item in page.get('data',[]):
            cid=item.get('id')
            if not isinstance(cid,str) or not cid or cid in ids: raise ValueError('Invalid or duplicate result ID')
            ids.add(cid);records.append(item)
        if len(records)>100: raise ValueError('Unexpected result count')
        if not page.get('has_more'): break
        next_cursor=page.get('last_id')
        if not next_cursor or next_cursor==cursor: raise ValueError('Invalid pagination cursor')
        cursor=next_cursor
    seen=set(); rows=[]
    for item in records:
        entities=item.get('entities') or []
        binders=[e for e in entities if e.get('type')=='protein' and 'B' in (e.get('chain_ids') or [])]
        seq=binders[0].get('value') if len(binders)==1 else None
        qc=candidate_qc({'id':item['id'],'sequence':seq,'generation_complete':True},policy,seen)
        metrics=item.get('metrics') or {}
        # Keep only finite numeric model outputs, never a surrogate for measured affinity.
        import math
        clean={k:v for k,v in metrics.items() if k in ('binding_confidence','structure_confidence','iptm') and type(v) in (int,float) and math.isfinite(v) and 0<=v<=1}
        rows.append({'id':item['id'],'sequence':seq,'qc':qc.to_dict(),'design_metrics':clean})
    # Selection based on real generator binding confidence; missing scores are not ranked.
    ranked=sorted((r for r in rows if r['qc']['state']=='PASS' and 'binding_confidence' in r['design_metrics']),key=lambda r:(-r['design_metrics']['binding_confidence'],r['id']))[:10]
    selected=[r['id'] for r in ranked]
    report={'design_run_id':state['id'],'generation_status':state['status'],'candidates':rows,'selected_for_prediction':selected,'selection_basis':'Descending Boltz design binding_confidence among sequence-QC passes; not measured affinity.', 'unranked_count':sum(r['qc']['state']=='PASS' and 'binding_confidence' not in r['design_metrics'] for r in rows)}
    save(RUN/'candidates.json',report)
    return report

def prediction_payloads():
    if not (RUN/'candidates.json').exists(): raise ValueError('Retrieve design results first')
    report=json.loads((RUN/'candidates.json').read_text()); attempt=json.loads((RUN/'attempt.json').read_text())
    target=attempt['body']['target']['entities'][0]['value']
    byid={r['id']:r for r in report['candidates']}
    selected=report['selected_for_prediction']
    if not selected: raise ValueError('No eligible candidates with binding confidence')
    return [(cid,{'model':'boltz-2.1','input':{'entities':[{'type':'protein','value':target,'chain_ids':['A']},{'type':'protein','value':byid[cid]['sequence'],'chain_ids':['B']}],'binding':{'type':'protein_protein_binding','binder_chain_ids':['B']},'num_samples':1}}) for cid in selected]

def estimate_predictions():
    payloads=prediction_payloads(); estimates=[]
    from decimal import Decimal
    for cid,body in payloads:
        result=api(PRED+'/estimate-cost',body)
        cost=result.get('estimated_cost_usd')
        if cost is None: raise ValueError('Prediction estimate unavailable')
        estimates.append({'candidate_id':cid,'estimated_cost_usd':cost})
    bundle={'jobs':payloads,'estimates':estimates,'estimated_total_usd':str(sum((Decimal(x['estimated_cost_usd']) for x in estimates),Decimal('0')))}
    bundle['input_hash']=digest(bundle)
    save(RUN/'prediction-estimate.json',bundle)
    return {'input_hash':bundle['input_hash'],'estimated_total_usd':bundle['estimated_total_usd'],'estimates':estimates,'note':'Estimate only; final charges may differ.'}

def start_predictions(data):
    path=RUN/'prediction-estimate.json'
    if not path.exists(): raise ValueError('Estimate prediction costs first')
    with LOCK:
        plan=json.loads(path.read_text())
        if data.get('input_hash')!=plan['input_hash']: raise ValueError('Estimate changed; estimate again')
        if digest(plan['jobs'])!=digest(prediction_payloads()): raise ValueError('Candidate selection changed; estimate again')
        out=[]; jobdir=RUN/'predictions';jobdir.mkdir(exist_ok=True)
        for index,(cid,body) in enumerate(plan['jobs']):
            marker=jobdir/f'{index}.json'
            if marker.exists():
                record=json.loads(marker.read_text());out.append({'candidate_id':cid,'status':record['status']})
                if record['status'] in ('submission_started', 'submission_uncertain'):
                    break
                continue
            record={'candidate_id':cid,'input':body,'status':'submission_started'};save(marker,record)
            try:
                response=api(PRED,body)
                record.update(status='submitted',job_id=response['id'])
            except Exception:
                record['status']='submission_uncertain';save(marker,record);out.append({'candidate_id':cid,'status':record['status']});break
            save(marker,record);out.append({'candidate_id':cid,'status':'submitted'})
        return {'jobs':out,'note':'Existing attempts are never resubmitted automatically.'}

def prediction_status():
    path=RUN/'prediction-estimate.json'
    if not path.exists(): return {'jobs':[],'recommendations':[]}
    plan=json.loads(path.read_text()); rows=[]
    for index,(cid,body) in enumerate(plan['jobs']):
        path=RUN/'predictions'/f'{index}.json'
        if not path.exists(): rows.append({'candidate_id':cid,'status':'not_submitted'});continue
        job=json.loads(path.read_text()); jid=job.get('job_id')
        if not jid: rows.append({'candidate_id':cid,'status':job['status']});continue
        result=api(PRED+'/'+jid)
        if result.get('livemode') is not True: raise ValueError('Expected live prediction')
        item={'candidate_id':cid,'job_id':jid,'status':result['status']}
        if result['status']=='succeeded':
            outputs=result.get('output') or {}; samples=outputs.get('all_sample_results') or []
            if samples:
                met=samples[0].get('metrics') or {}
                item['prediction_metrics']={k:v for k,v in met.items() if k in ('iptm','protein_iptm','structure_confidence')}
            item['binding_metrics']=outputs.get('binding_metrics')
            item['outcome']={'stage':'SIMULATION_OUTCOME','state':'UNCERTAIN','reasons':['INSUFFICIENT_SAMPLING','BINDING_INCONCLUSIVE'],'decision':'HUMAN_REVIEW','evidence':{'source_job_id':jid,'metrics':item.get('prediction_metrics',{})}}
            item['decision']={'stage':'DECISION','state':'UNCERTAIN','reasons':['INSUFFICIENT_EVIDENCE','NEEDS_OFF_TARGET_VALIDATION','DEVELOPABILITY_UNKNOWN'],'decision':'HUMAN_REVIEW'}
        elif result['status']=='failed':
            item['outcome']={'stage':'SIMULATION_OUTCOME','state':'ERROR','reasons':['TOOL_ERROR'],'decision':'HUMAN_REVIEW'}
        rows.append(item)
    return {'jobs':rows,'recommendations':[],'note':'No automatic wet-lab recommendation: site confirmation, replicate agreement, selectivity and developability are not evaluated.'}
