"""Target-bound real design, quality screening and rendering. No demo data."""
import hashlib
import json
import re
import threading
import time
from pathlib import Path
import httpx
from . import tamarind, tamarind_results, visualization_store as store
from .chimerax_renderer import renderer

ROOT=Path(__file__).resolve().parents[2]/'runs/research'
LOCK=threading.RLock()
WORKERS={}
TERMINAL={'stopped','complete','failed','submission_uncertain','render_failed'}

def write(record):
    ROOT.mkdir(parents=True,exist_ok=True)
    path=ROOT/(record['id']+'.json');tmp=path.with_suffix('.tmp')
    with LOCK:
        tmp.write_text(json.dumps(record,allow_nan=False,indent=2));tmp.replace(path)

def read(rid):
    if not re.fullmatch(r'research-[a-f0-9]{32}',rid or ''):raise ValueError('Invalid research ID')
    return json.loads((ROOT/(rid+'.json')).read_text())

def public(r):
    return {k:v for k,v in r.items() if k not in ('target_sequence',)}

def resolve(data):
    query=str(data.get('target','')).strip();species=data.get('species','Homo sapiens')
    if species not in ('Homo sapiens','Mus musculus'):raise ValueError('Choose a supported species; custom species need a validated accession')
    if data.get('modality','Protein binder')!='Protein binder':raise ValueError('This live workflow currently supports miniprotein binders only')
    if not re.fullmatch(r'[A-Za-z0-9_-]{2,30}',query):raise ValueError('Enter a UniProt accession or an exact gene symbol')
    with httpx.Client(timeout=40) as client:
        if re.fullmatch(r'(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})',query.upper()):
            response=client.get('https://rest.uniprot.org/uniprotkb/'+query.upper()+'.json');response.raise_for_status();entry=response.json()
        else:
            taxon=9606 if species=='Homo sapiens' else 10090
            response=client.get('https://rest.uniprot.org/uniprotkb/search',params={'query':f'gene_exact:{query} AND organism_id:{taxon} AND reviewed:true','format':'json','size':3});response.raise_for_status()
            entries=response.json().get('results',[])
            if len(entries)!=1:raise ValueError('Target name is missing or ambiguous. Enter its exact UniProt accession.')
            entry=entries[0]
    if entry['organism']['scientificName']!=species:raise ValueError('Accession and species do not match')
    sequence=entry['sequence']['value']
    extracellular=[f for f in entry.get('features',[]) if f['type']=='Topological domain' and f.get('description','').lower()=='extracellular']
    if len(extracellular)==1:
        start=extracellular[0]['location']['start']['value'];end=extracellular[0]['location']['end']['value'];domain='Extracellular domain'
    else:
        chains=[f for f in entry.get('features',[]) if f['type']=='Chain']
        signals=[f for f in entry.get('features',[]) if f['type']=='Signal']
        if len(chains)==1 and len(signals)==1 and chains[0]['location']['start']['value']==signals[0]['location']['end']['value']+1:
            start=chains[0]['location']['start']['value'];end=chains[0]['location']['end']['value'];domain='Mature chain (signal peptide excluded)'
        else:start,end,domain=1,len(sequence),'Full-length sequence'
    sequence=sequence[start-1:end]
    if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]{10,2000}',sequence):raise ValueError('Target sequence exceeds supported length or has noncanonical residues')
    spec={'accession':entry['primaryAccession'],'species':species,'symbol':entry.get('genes',[{}])[0].get('geneName',{}).get('value',query.upper()),'name':entry['proteinDescription']['recommendedName']['fullName']['value'],'domain':domain,'start':start,'end':end,'length':len(sequence),'sequence_sha256':store.sha(sequence.encode()),'count':10,'binder_length':80,'modality':'Protein binder','intent':str(data.get('intent','')).strip()[:2000],'source':'https://www.uniprot.org/uniprotkb/'+entry['primaryAccession']+'/entry','limitations':'No epitope, glycosylation, antagonism, off-target binding, toxicity or expression-yield validation is performed. Intended effect is recorded, not inferred from binding.'}
    rid='research-'+store.sha(json.dumps(spec,sort_keys=True).encode())[:32]
    with LOCK:
        if (ROOT/(rid+'.json')).exists():return public(read(rid))
        record={'id':rid,'stage':'ready','spec':spec,'target_sequence':sequence,'candidates':[],'selected':[],'diagnostic':[],'events':['UniProt target sequence and domain verified.']}
        write(record)
    return public(record)

def screen(data):
    seen=set();rows=[]
    for candidate in data['candidates']:
        c={k:v for k,v in candidate.items()};seq=c.get('sequence','');reasons=[]
        if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]{80}',seq):reasons.append('invalid_sequence_or_length')
        if seq in seen:reasons.append('duplicate_sequence')
        seen.add(seq)
        if c.get('structure_state')!='ready':reasons.append('structure_unavailable')
        met=c.get('metrics',{});binding=met.get('binding_confidence');structure=met.get('structure_confidence')
        if binding is None or structure is None:reasons.append('missing_model_confidence')
        c['qc_pass']=not reasons
        if binding is not None and binding<.7:reasons.append('binding_confidence_below_0.70')
        if structure is not None and structure<.68:reasons.append('structure_confidence_below_0.68')
        c.update(reasons=reasons,passed=not reasons)
        rows.append(c)
    ranked=sorted([c for c in rows if c['qc_pass']],key=lambda c:(-c['metrics']['binding_confidence'],-c['metrics']['structure_confidence'],c['id']))
    selected=[c['id'] for c in ranked if c['passed']][:3]
    diagnostic=[c['id'] for c in ranked if c['id'] not in selected][:3-len(selected)]
    return rows,selected,diagnostic

def launch(rid):
    with LOCK:
        if WORKERS.get(rid) and WORKERS[rid].is_alive():return
        thread=threading.Thread(target=work,args=(rid,),daemon=True);WORKERS[rid]=thread;thread.start()

def start(rid):
    with LOCK:
        record=read(rid)
        if record['stage']=='ready':
            record['stage']='preparing';record['events'].append('Validating real Tamarind design settings.');write(record)
        elif record['stage'] in TERMINAL and record['stage']!='render_failed':return public(record)
        launch(rid)
        return public(record)

def status(rid):
    r=read(rid)
    if r['stage'] not in TERMINAL|{'ready'}:launch(rid)
    return public(r)

def work(rid):
    from filelock import FileLock, Timeout
    ROOT.mkdir(parents=True,exist_ok=True)
    try:
        with FileLock(str(ROOT/(rid+'.lock')),timeout=0):_work(rid)
    except Timeout:return

def _work(rid):
    r=read(rid)
    try:
        if not r.get('jobName'):
            prepared=tamarind.prepare({'sequence':r['target_sequence'],'count':r['spec']['count'],'length':r['spec']['binder_length']})
            r.update(jobName=prepared['jobName'],stage='submitting');write(r)
        job=r['jobName'];path,provider_record=tamarind.record_for(job)
        if not path.with_suffix('.attempt').exists():
            tamarind.submit({'jobName':job,'confirmed':True})
        r['stage']='computing';write(r)
        while True:
            try:remote=tamarind.status(job)['state']
            except Exception as exc:
                r['remote_warning']=str(exc);write(r);time.sleep(20);continue
            r['provider_state']=remote;r.pop('remote_warning',None);write(r)
            if remote=='Complete':break
            if remote.lower()=='stopped':
                r.update(stage='stopped');r['events'].append('Cloud task stopped. No automatic resubmission.');write(r);return
            if remote.lower() in ('failed','error','cancelled','canceled'):raise ValueError('Tamarind task '+remote)
            time.sleep(20)
        r['stage']='screening';write(r)
        data=tamarind_results.load(job)
        if data.get('target_sequence')!=r['target_sequence']:raise ValueError('Result target sequence does not match the submitted target')
        rows,selected,diagnostic=screen(data)
        r.update(candidates=rows,selected=selected,diagnostic=diagnostic,screen_version=2,selection_basis='Sequence/structure QC, then descending model binding confidence; structure confidence breaks ties. Passing requires binding ≥0.70 and structure ≥0.68. Not measured affinity.')
        run=store.import_tamarind(tamarind_results.cache_path(job))
        manifest=store.manifest(run);manifest['research_id']=rid;manifest['target_spec']=r['spec'];manifest['label']=r['spec']['symbol']+' '+r['spec']['domain'];store.write_manifest(manifest)
        r.update(visualization_run=run,stage='rendering',rendered=[])
        r['events'].append('Real structures verified against target and binder sequences. '+('Selected candidates passed model gates.' if selected else 'No candidate passed model gates. Best available predictions shown only for diagnostic inspection.'));write(r)
        for cid in ['target',*selected,*diagnostic]:
            r['rendering_candidate']=cid;write(r)
            render=renderer.submit(run,cid)
            while render['state'] in ('queued','running'):
                time.sleep(2);render=renderer.get_status(run,cid)
            if render['state']!='ready':
                r.update(stage='render_failed',error=render.get('reason') or render['state']);write(r);return
            r['rendered'].append(cid);write(r)
        r.update(stage='complete',rendering_candidate=None);r.pop('error',None);write(r)
    except Exception as exc:
        r.update(stage='submission_uncertain' if r['stage']=='submitting' else 'failed',error=str(exc));write(r)


DEMO_IDS={
    'il2':'research-eba262761107935dfaa5bfd9518b09ce',
    'pdl1':'research-69f794897ec6937ef3b2892766a8a47e',
    'pd1':'research-dd0a56e678e1aef43e3e8ce4ad9b48d0',
}

def demos():
    results={}
    for name,rid in DEMO_IDS.items():
        try:results[name]=status(rid)
        except FileNotFoundError:results[name]=None
    return results


def install_bundled_demos():
    """Restore curated public-sequence demo assets without overwriting local runs."""
    import shutil
    bundled=ROOT.parents[1]/'demo-data'
    if not bundled.is_dir():return
    for folder in ('visualizations','research'):
        source=bundled/folder
        for path in source.rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            destination=ROOT.parent/folder/path.relative_to(source)
            if not destination.exists():
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(path,destination)


def resume_pending():
    """Resume already requested work on server restart, never submit a ready demo."""
    for path in ROOT.glob('research-*.json'):
        try:r=read(path.stem)
        except (OSError,ValueError):continue
        if r['stage'] not in TERMINAL|{'ready'}:launch(r['id'])
