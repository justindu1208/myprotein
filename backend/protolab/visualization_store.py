"""Typed molecular evidence assets. No generated coordinates or guessed file URLs."""
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
import gemmi

ROOT = Path(__file__).resolve().parents[2] / 'runs' / 'visualizations'
TRANSITION_LABEL = 'Illustrative transition to the predicted complex — not a molecular-dynamics trajectory.'
ROLES = ('target', 'monomer', 'complex')
PRESETS = ('cartoon', 'surface', 'interface', 'target_only', 'binder_only', 'full_complex')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', value):
        raise ValueError('Invalid run or candidate identifier')
    return value


def chain_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9]{1,8}', value):
        raise ValueError('Unsupported chain identifier')
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_structure(text, fmt='cif'):
    if len(text) > 20_000_000: raise ValueError('Structure exceeds 20 MB')
    if fmt == 'cif': s = gemmi.make_structure_from_block(gemmi.cif.read_string(text).sole_block())
    elif fmt == 'pdb': s = gemmi.read_pdb_string(text)
    else: raise ValueError('Unsupported structure format')
    if len(s) != 1: raise ValueError('A single structure model is required')
    count = 0
    for c in s[0]:
        chain_id(c.name)
        for r in c:
            for a in r:
                count += 1
                if not all(math.isfinite(v) for v in (a.pos.x, a.pos.y, a.pos.z)):
                    raise ValueError('Invalid atom coordinates')
    if not 1 <= count <= 100000: raise ValueError('Invalid or oversized structure')
    return s


def chain_sequence(chain):
    return ''.join(gemmi.find_tabulated_residue(r.name).one_letter_code.upper() for r in chain if r.find_atom('CA', '*'))


def interface(s, targets, binders, cutoff=4.5):
    """Heavy-atom proximity contacts, not hydrogen bonds or energetic evidence."""
    grid, residues, contacts = {}, set(), []
    def key(a): return tuple(math.floor(v / cutoff) for v in (a.pos.x, a.pos.y, a.pos.z))
    for c in s[0]:
        if c.name not in targets: continue
        for r in c:
            for a in r:
                if a.element.is_hydrogen: continue
                grid.setdefault(key(a), []).append((c.name, r, a))
    for c in s[0]:
        if c.name not in binders: continue
        for r in c:
            for a in r:
                if a.element.is_hydrogen: continue
                x,y,z=key(a)
                for dx in (-1,0,1):
                    for dy in (-1,0,1):
                        for dz in (-1,0,1):
                            for tc,tr,ta in grid.get((x+dx,y+dy,z+dz), []):
                                distance=a.pos.dist(ta.pos)
                                if distance <= cutoff:
                                    residues.update(((c.name,r.seqid.num,r.name),(tc,tr.seqid.num,tr.name)))
                                    if len(contacts)<100: contacts.append({'target_chain':tc,'target_residue':tr.seqid.num,'target_atom':ta.name,'binder_chain':c.name,'binder_residue':r.seqid.num,'binder_atom':a.name,'distance_angstrom':round(distance,3)})
    return {'method':'Heavy-atom distance <= 4.5 Å; not assigned hydrogen bonds', 'residues':[{'chain':c,'number':n,'name':name} for c,n,name in sorted(residues)],'contacts':contacts,'contacts_display_limit':100}


class SamsonProvider:
    """Only pre-published, official document URLs. No invented upload endpoint."""
    @staticmethod
    def resolve(entry, preset='cartoon'):
        if preset not in PRESETS: raise ValueError('Invalid representation')
        views = entry.get('samson_views', {})
        document = views.get(preset) or (entry.get('samson_document_url') if preset == 'cartoon' else None)
        if not document: return {'state':'not_published', 'document_url':None, 'embed_url':None}
        parsed=urlparse(document)
        match=re.fullmatch(r'/documents/([a-fA-F0-9]{8}-[a-fA-F0-9-]{27})/?', parsed.path)
        if parsed.scheme!='https' or parsed.netloc!='www.samson-connect.net' or not match:
            raise ValueError('Expected an official SAMSON Connect document URL')
        params={'sam':match[1], 'statcounter':'0'}
        version=entry.get('samson_version')
        if version:
            if not re.fullmatch(r'[a-fA-F0-9-]{36}',version): raise ValueError('Invalid SAMSON version')
            params['version']=version
        return {'state':'published', 'document_url':document,'embed_url':'https://app.samson-connect.net/?'+urlencode(params)}


def directory(run):
    p=ROOT/identifier(run)
    if p.is_symlink(): raise ValueError('Symlink run directories are not supported')
    return p


def manifest(run):
    p=directory(run)/'manifest.json'
    if not p.is_file(): raise ValueError('Visualization run not registered')
    data=json.loads(p.read_text())
    if data.get('run_id')!=run: raise ValueError('Manifest run mismatch')
    return data


def write_manifest(data):
    d=directory(data['run_id']);d.mkdir(parents=True,exist_ok=True)
    (d/'manifest.json').write_text(json.dumps(data,indent=2))


def add_asset(run, candidate, role, structure, source, predicted, source_job_id=None, note='', confidence=None):
    identifier(candidate)
    if role not in ROLES: raise ValueError('Invalid structure role')
    d=directory(run)/candidate;d.mkdir(parents=True,exist_ok=True)
    cif=structure.make_mmcif_document().as_string().encode()
    pdb=structure.make_pdb_string().encode()
    (d/(role+'.cif')).write_bytes(cif);(d/(role+'.pdb')).write_bytes(pdb)
    base=f'/api/visualizations/{run}/{candidate}/{role}'
    return {'role':role,'candidate_id':candidate,'state':'available','mmcif_url':base+'.cif','pdb_url':base+'.pdb','sha256':sha(cif),'source':source,'source_job_id':source_job_id,'predicted':bool(predicted),'note':note,'structure_confidence':confidence,'samson_document_url':None,'samson_views':{},'sequence_length':sum(len(chain_sequence(c)) for c in structure[0]),'chains':[c.name for c in structure[0]]}


def asset(run, candidate, role):
    identifier(candidate)
    if role not in ROLES: raise ValueError('Invalid structure role')
    m=manifest(run)
    entry=m.get('target') if candidate=='target' and role=='target' else m.get('candidates',{}).get(candidate,{}).get(role)
    if not entry or entry.get('role')!=role or entry.get('candidate_id')!=candidate:
        raise ValueError('Structure role or candidate not registered')
    return entry


def structure_path(run, candidate, role, extension='cif'):
    entry=asset(run,candidate,role)
    if extension not in ('cif','pdb'): raise ValueError('Invalid structure extension')
    p=directory(run)/identifier(candidate)/(role+'.'+extension)
    if not p.resolve().is_relative_to(directory(run).resolve()): raise ValueError('Structure path escapes its run')
    if not p.is_file() or p.is_symlink(): raise ValueError('Structure unavailable')
    cif=p.with_suffix('.cif')
    if sha(cif.read_bytes()) != entry['sha256']: raise ValueError('Structure checksum mismatch')
    return p


def catalog():
    return [{'run_id':p.parent.name,'label':m.get('label',p.parent.name),'target':m.get('target_identity',{})} for p in ROOT.glob('*/manifest.json') if (m:=json.loads(p.read_text()))]


def import_tamarind(path):
    data=json.loads(Path(path).read_text());run=identifier(data['jobName'])
    m={'schema_version':1,'run_id':run,'label':'Tamarind design run '+run[-8:],'target_identity':{'sequence':data.get('target_sequence'),'scope':'Target chain from predicted complex'},'candidates':{},'target':None,'experimental_reference':None,'true_trajectory':None,'transition_label':TRANSITION_LABEL}
    for candidate in data['candidates']:
        cid=identifier(candidate['id']);stored=data.get('structures',{}).get(cid)
        if not stored: continue
        complex_s=read_structure(stored['complex']['text'],stored['complex']['format'])
        binder=chain_id(stored['chain']);bind_seq=chain_sequence(complex_s[0][binder])
        if bind_seq!=candidate['sequence']: raise ValueError('Binder sequence mismatch')
        targets=[c.name for c in complex_s[0] if c.name!=binder and chain_sequence(c)]
        if not targets: raise ValueError('No target chain')
        if data.get('target_sequence') and not any(chain_sequence(complex_s[0][c])==data['target_sequence'] for c in targets): raise ValueError('Target sequence mismatch')
        mono=complex_s.clone()
        for c in list(mono[0]):
            if c.name!=binder: del mono[0][c.name]
        target=complex_s.clone()
        del target[0][binder]
        if m['target'] is None: m['target']=add_asset(run,'target','target',target,'BoltzProt target chain from predicted complex',True,run,note='Bound target conformation, not an experimental reference')
        m['candidates'][cid]={'candidate_id':cid,'source_design_id':candidate['design_id'],'sequence':candidate['sequence'],'metrics':candidate['metrics'],'categories':[],
            'monomer':add_asset(run,cid,'monomer',mono,'BoltzProt binder chain',True,run,note='Extracted bound conformation; not an independently predicted monomer',confidence=candidate['metrics'].get('structure_confidence')),
            'complex':add_asset(run,cid,'complex',complex_s,'BoltzProt predicted complex',True,run,confidence=candidate['metrics'].get('structure_confidence')),
            'target_chains':targets,'binder_chains':[binder],'interface':interface(complex_s,targets,[binder])}
    write_manifest(m)
    return run
