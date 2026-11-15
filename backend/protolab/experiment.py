"""Independent Boltz-2 predictions for one research task's three candidates."""
import csv, io, json, threading, time, uuid
from pathlib import Path
from urllib.parse import urlparse
import httpx
from filelock import FileLock, Timeout
from . import research, tamarind, tamarind_results, visualization_store as store
from .chimerax_renderer import renderer

ROOT=Path(__file__).resolve().parents[2]/'runs'/'experiments'
LOCK=threading.RLock()
WORKERS={}
TERMINAL={'complete','failed','submission_uncertain','stopped','finished_with_errors'}

def path(rid):
    research.read(rid)
    return ROOT/(rid+'.json')

def read(rid):
    p=path(rid)
    if not p.exists():return {'research_id':rid,'state':'not_started','jobs':[]}
    return json.loads(p.read_text())

def write(record):
    p=path(record['research_id']);p.parent.mkdir(parents=True,exist_ok=True)
    with LOCK:
        tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(record,allow_nan=False,indent=2));tmp.replace(p)

def public(record):
    return {k:v for k,v in record.items() if k!='target_sequence'}

def launch(rid):
    with LOCK:
        if WORKERS.get(rid) and WORKERS[rid].is_alive():return
        t=threading.Thread(target=work,args=(rid,),daemon=True);WORKERS[rid]=t;t.start()

def start(rid):
    with LOCK:
        existing=read(rid)
        if existing['state']!='not_started':
            if existing['state'] not in TERMINAL:launch(rid)
            return public(existing)
        r=research.read(rid);ids=(r.get('selected') or [])+(r.get('diagnostic') or [])
        if len(ids)!=3:raise ValueError('Three shortlisted candidates with sequences are required')
        rows={c['id']:c for c in r['candidates']}
        if any(cid not in rows or not rows[cid].get('sequence') for cid in ids):raise ValueError('Candidate sequence missing')
        jobs=[{'candidate_id':cid,'state':'pending','jobName':'protolab-'+uuid.uuid4().hex} for cid in ids]
        record={'research_id':rid,'state':'running','jobs':jobs,'note':'Independent Boltz-2 complex prediction; not a wet-lab validation or proof of binding.'}
        write(record);launch(rid);return public(record)

def retry_rejected(rid):
    """Retry explicit HTTP 400 rejections only after confirming jobs do not exist."""
    with LOCK:
        record=read(rid)
        if record['state']!='finished_with_errors':raise ValueError('Only a finished experiment can be retried')
        retry=[j for j in record['jobs'] if j.get('state')=='submission_uncertain' and str(j.get('reason','')).startswith('Tamarind HTTP 400')]
        if not retry:raise ValueError('No safely retryable HTTP 400 rejections; inspect Tamarind jobs first')
        from urllib.parse import quote
        names=set();cursor=None;seen=set()
        while True:
            result=tamarind.api('jobs'+(('?startKey='+quote(cursor,safe='')) if cursor else ''))
            names.update(item.get('JobName') for item in result.get('jobs',[]))
            cursor=result.get('startKey')
            if not cursor:break
            if cursor in seen:raise ValueError('Could not verify all provider jobs; retry stopped')
            seen.add(cursor)
        if any(j['jobName'] in names for j in retry):raise ValueError('A prior job exists on Tamarind; retry stopped to prevent duplicates')
        for j in retry:
            j['previous_rejection']=j.pop('reason');j['state']='pending'
        record['state']='running';write(record);launch(rid);return public(record)

def status(rid):
    r=read(rid)
    if r['state']=='running':launch(rid)
    return public(r)

def get_results(job,target,binder):
    url=tamarind.api('result',{'jobName':job})
    if not isinstance(url,str) or urlparse(url).scheme!='https':raise ValueError('Unexpected result download URL')
    with httpx.Client(timeout=120) as client:
        with client.stream('GET',url) as response:
            response.raise_for_status();parts=[];size=0
            for chunk in response.iter_bytes():
                size+=len(chunk)
                if size>100_000_000:raise ValueError('Results archive exceeds 100 MB')
                parts.append(chunk)
    files=tamarind_results.unpack(b''.join(parts))
    metrics=[n for n in files if Path(n).name=='metrics.csv']
    if len(metrics)!=1:raise ValueError('Expected one metrics.csv in Boltz results')
    rows=list(csv.DictReader(io.StringIO(files[metrics[0]])))
    if not rows:raise ValueError('No prediction results in metrics.csv')
    def score(row):
        n=tamarind_results.number(row.get('confidence_score'),'confidence_score');return n if n is not None else -1
    row=max(rows,key=score)
    candidate_path=row.get('pdb_filepath') or row.get('structure_file') or ''
    names=[n for n in files if n==candidate_path or n==str(Path(metrics[0]).parent/candidate_path)]
    if not names:names=[n for n in files if Path(n).name==Path(candidate_path).name]
    if len(names)!=1:raise ValueError('Predicted structure file missing or ambiguous')
    name=names[0];structure=store.read_structure(files[name],'pdb' if name.lower().endswith('.pdb') else 'cif')
    chains={chain.name:store.chain_sequence(chain) for chain in structure[0]}
    target_chains=[k for k,v in chains.items() if v==target];binder_chains=[k for k,v in chains.items() if v==binder]
    if len(target_chains)!=1 or len(binder_chains)!=1 or target_chains[0]==binder_chains[0]:raise ValueError('Predicted chains do not uniquely match the target and candidate sequences')
    values={key:tamarind_results.number(row.get(key),key) for key in ('confidence_score','iptm','ptm','complex_plddt')}
    return files[name],('pdb' if name.lower().endswith('.pdb') else 'cif'),binder_chains[0],values

def import_structure(rid,cid,job,text,fmt,chain,metrics):
    r=research.read(rid);c=next(c for c in r['candidates'] if c['id']==cid)
    prediction={'jobName':job,'target_sequence':r['target_sequence'],'candidates':[{'id':cid,'design_id':cid,'sequence':c['sequence'],'metrics':{'structure_confidence':metrics.get('confidence_score')}}], 'structures':{cid:{'complex':{'text':text,'format':fmt},'chain':chain}}}
    ROOT.mkdir(parents=True,exist_ok=True);p=ROOT/(job+'-import.json');p.write_text(json.dumps(prediction))
    try:run=store.import_tamarind(p)
    finally:p.unlink(missing_ok=True)
    manifest=store.manifest(run);manifest['research_id']=rid;manifest['target_spec']=r['spec'];manifest['label']='Boltz-2 simulation '+cid;store.write_manifest(manifest)
    return run

def work(rid):
    ROOT.mkdir(parents=True,exist_ok=True)
    try:
        with FileLock(str(ROOT/(rid+'.lock')),timeout=0):_work(rid)
    except Timeout:return

def _work(rid):
    record=read(rid);research_record=research.read(rid);target=research_record['target_sequence'];candidates={c['id']:c for c in research_record['candidates']}
    for j in record['jobs']:
        if j['state']=='submitting':j.update(state='submission_uncertain',reason='Submission was interrupted; check Tamarind before retrying.');write(record)
        if j['state']!='pending':continue
        try:
            sequence=target+':'+candidates[j['candidate_id']]['sequence']
            settings={'inputFormat':'sequence','sequence':sequence,'numSamples':1,'outputType':'mmcif','useMSA':True}
            validation=tamarind.api('validate-job',{'type':'boltz','settings':settings})
            if validation.get('valid') is not True or not isinstance(validation.get('normalized'),dict):raise ValueError('Tamarind rejected Boltz-2 settings')
            # Tamarind's normalizer currently injects an inactive conditional
            # default. Its own submit validator rejects that field when the
            # hosted Boltz server is disabled, even when its value is false.
            normalized=dict(validation['normalized'])
            if not normalized.get('useBoltzServer') and normalized.get('predictProteinAffinity') is False:
                normalized.pop('predictProteinAffinity')
            j['state']='submitting';write(record)
            tamarind.api('submit-job',{'jobName':j['jobName'],'type':'boltz','settings':normalized})
            j['state']='queued';write(record)
        except Exception as exc:
            j.update(state='submission_uncertain' if j['state']=='submitting' else 'failed',reason=str(exc));write(record)
    while any(j['state'] in ('queued','running','processing','rendering') for j in record['jobs']):
        for j in record['jobs']:
            if j['state'] not in ('queued','running','processing','rendering'):continue
            try:
                if j['state'] in ('queued','running'):
                    try:remote=tamarind.api('jobs?jobName='+j['jobName'])
                    except Exception:
                        j['warning']='Provider status temporarily unavailable; retrying.';write(record);continue
                    j.pop('warning',None);state=remote.get('JobStatus','Unknown');j['provider_state']=state
                    if state=='Complete':j['state']='processing';write(record)
                    elif state.lower() in ('failed','error','stopped','cancelled','canceled'):j.update(state='failed',reason='Tamarind task '+state);write(record);continue
                    else:j['state']='running' if state=='Running' else 'queued';write(record);continue
                if j['state']=='processing':
                    text,fmt,chain,metrics=get_results(j['jobName'],target,candidates[j['candidate_id']]['sequence'])
                    run=import_structure(rid,j['candidate_id'],j['jobName'],text,fmt,chain,metrics)
                    j.update(state='rendering',metrics=metrics,visualization_run=run);write(record)
                if j['state']=='rendering':
                    render=renderer.submit(j['visualization_run'],j['candidate_id'])
                    while render['state'] in ('queued','running'):
                        time.sleep(2);render=renderer.get_status(j['visualization_run'],j['candidate_id'])
                    if render['state']!='ready':raise ValueError(render.get('reason') or render['state'])
                    j.update(state='complete',artifacts=render.get('artifacts',{}));write(record)
            except httpx.RequestError as exc:
                j['warning']='Network temporarily unavailable';write(record)
            except Exception as exc:
                j.update(state='failed',reason=str(exc));write(record)
        if any(j['state'] in ('queued','running','processing','rendering') for j in record['jobs']):time.sleep(15)
    record['state']='complete' if all(j['state']=='complete' for j in record['jobs']) else 'finished_with_errors';write(record)


def resume_pending():
    """Resume previously requested simulations after a server restart."""
    if not ROOT.exists():return
    for p in ROOT.glob('research-*.json'):
        try:
            r=read(p.stem)
            if r.get('state')=='running':launch(r['research_id'])
        except (OSError,ValueError,KeyError):continue
