"""Single live structure prediction. No retry of ambiguous submissions."""
import json, re, threading, urllib.request, urllib.error
from pathlib import Path
from .settings import boltz_api_key
from .live_eval import BASE, save

RUN = Path(__file__).resolve().parents[2] / 'runs/custom-live'
LOCK = threading.Lock()

def request_api(path, body=None):
    key = boltz_api_key()
    if not key: raise ValueError('Boltz API key not configured')
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'x-api-key':key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response: return json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Boltz API returned HTTP {exc.code}') from exc

def payload(data):
    seqs=[]
    for field in ('target','binder'):
        seq=data.get(field,'').strip().upper()
        if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]{10,1000}',seq):
            raise ValueError(f'{field} must contain 10–1000 canonical amino acids')
        seqs.append(seq)
    return {'model':'boltz-2.1','input':{'entities':[{'type':'protein','value':seqs[0],'chain_ids':['A']},{'type':'protein','value':seqs[1],'chain_ids':['B']}], 'binding':{'type':'protein_protein_binding','binder_chain_ids':['B']}, 'num_samples':1}}

def estimate(data):
    body=payload(data)
    response=request_api('estimate-cost',body)
    import hashlib
    return {'estimated_cost_usd':response.get('estimated_cost_usd'), 'disclaimer':response.get('disclaimer'), 'input_hash':hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()}

def submit(data):
    import hashlib
    body=payload(data)
    digest=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    if data.get('input_hash') != digest: raise ValueError('Inputs changed; estimate again')
    with LOCK:
        RUN.mkdir(parents=True,exist_ok=True)
        if (RUN/'attempt.json').exists(): raise ValueError('An existing submission is present; inspect it before submitting another')
        save(RUN/'attempt.json',{'input':body,'input_hash':digest,'status':'submission_started'})
        try: result=request_api('',body)
        except Exception:
            # Request could have reached the server. Never retry automatically.
            save(RUN/'attempt.json',{'input':body,'input_hash':digest,'status':'submission_uncertain'})
            raise
        save(RUN/'submission.json',result)
        return {'id':result['id'],'status':result['status']}

def status():
    if not (RUN/'submission.json').exists():
        return {'status':'submission_uncertain' if (RUN/'attempt.json').exists() else 'not_started'}
    submission=json.loads((RUN/'submission.json').read_text())
    data=request_api(submission['id'])
    status=data['status']
    result={'id':data['id'],'status':status,'model':data.get('model'),'livemode':data.get('livemode')}
    if status=='succeeded':
        if data.get('livemode') is not True: raise ValueError('Expected live result')
        sample=data['output']['all_sample_results'][0]
        import gemmi
        path=RUN/'sample_0.pdb'
        if not path.exists():
            url=sample['structure']['url']
            if not url.startswith('https://'): raise ValueError('Invalid structure URL')
            with urllib.request.urlopen(url,timeout=30) as r: (RUN/'sample_0.cif').write_bytes(r.read())
            gemmi.read_structure(str(RUN/'sample_0.cif')).write_pdb(str(path))
        result.update(metrics=sample['metrics'],binding_metrics=data['output'].get('binding_metrics'),structure_url='/api/custom/structure')
    return result
