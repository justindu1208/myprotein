"""Visualization API and setup CLI; structures stay separate from ranking data."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import httpx
from . import visualization_store as store
from .chimerax_renderer import renderer, OUTPUTS


def resolve_target(accession, species):
    if not re.fullmatch(r'[A-Z0-9]{6,10}', accession or ''): raise ValueError('A resolved UniProt accession is required')
    if species not in ('Homo sapiens','Mus musculus'):raise ValueError('Resolve the target species before loading a structure')
    run='af-'+accession
    try:
        m=store.manifest(run)
        if m['target_identity']['species']==species:return public_manifest(run)
    except (ValueError,FileNotFoundError):pass
    with httpx.Client(timeout=40) as client:
        response=client.get('https://alphafold.ebi.ac.uk/api/prediction/'+accession);response.raise_for_status()
        matches=[m for m in response.json() if m.get('uniprotAccession')==accession and m.get('organismScientificName')==species]
        if len(matches)!=1:raise ValueError('No unique structure with the requested accession and species')
        model=matches[0];url=model['cifUrl'];p=urlparse(url)
        if p.scheme!='https' or p.netloc!='alphafold.ebi.ac.uk' or not p.path.startswith('/files/'):raise ValueError('Unexpected structure source')
        response=client.get(url);response.raise_for_status()
        if len(response.content)>20_000_000:raise ValueError('Target structure too large')
    s=store.read_structure(response.text)
    asset=store.add_asset(run,'target','target',s,'AlphaFold DB '+model['entryId'],True,model['entryId'],note='Full-length predicted reference. The requested target domain has not been isolated; this is not experimental evidence.')
    asset['source_url']=url;asset['model_version']=model.get('latestVersion')
    m={'schema_version':1,'run_id':run,'label':model.get('uniprotDescription',accession),'target_identity':{'accession':accession,'species':species,'scope':'Full-length reference; not domain-cropped'},'target':asset,'candidates':{},'experimental_reference':None,'true_trajectory':None,'transition_label':store.TRANSITION_LABEL}
    store.write_manifest(m)
    return public_manifest(run)


def public_manifest(run):
    m=store.manifest(run)
    entries=[m['target']] if m.get('target') else []
    for candidate in m.get('candidates',{}).values():
        for role in ('monomer','complex'):
            if candidate.get(role):entries.append(candidate[role])
    for entry in entries:
        entry['samson']=store.SamsonProvider.resolve(entry)
    m['renderer']=renderer.check()
    return m


def serve_asset(run,candidate,filename,cache_key=None):
    store.identifier(run);store.identifier(candidate)
    if cache_key is None:
        match=re.fullmatch(r'(target|monomer|complex)\.(pdb|cif)',filename)
        if not match:raise ValueError('Unsupported structure artifact')
        p=store.structure_path(run,candidate,*match.groups())
        return p, 'chemical/x-pdb' if p.suffix=='.pdb' else 'chemical/x-mmcif'
    if not re.fullmatch(r'[a-f0-9]{64}',cache_key) or filename not in OUTPUTS:raise ValueError('Invalid render artifact')
    store.manifest(run)
    p=store.directory(run)/candidate/'renders'/cache_key/filename
    if not p.is_file() or p.is_symlink():raise ValueError('Render artifact unavailable')
    if filename.endswith(('.mp4','.png')):
        metadata=json.loads((p.parent/'metadata.json').read_text())
        if metadata.get('state')!='ready' or store.sha(p.read_bytes())!=metadata.get('checksums',{}).get(filename):raise ValueError('Media checksum mismatch or rendering incomplete')
    return p, {'.mp4':'video/mp4','.png':'image/png','.json':'application/json','.cxc':'text/plain'}[p.suffix]


def link_samson(run,candidate,role,url,preset):
    m=store.manifest(run);entry=m['target'] if candidate=='target' and role=='target' else m['candidates'][candidate][role]
    if preset not in store.PRESETS:raise ValueError('Invalid representation')
    proposal={**entry,'samson_views':{**entry.get('samson_views',{}),preset:url}}
    store.SamsonProvider.resolve(proposal,preset)
    entry['samson_views']=proposal['samson_views']
    if preset=='cartoon':entry['samson_document_url']=url
    store.write_manifest(m)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('check')
    p=sub.add_parser('render-run');p.add_argument('run');p.add_argument('--candidate',action='append');p.add_argument('--preset',choices=store.PRESETS,default='cartoon')
    p=sub.add_parser('import-tamarind');p.add_argument('cache_file')
    p=sub.add_parser('resolve-target');p.add_argument('accession');p.add_argument('--species',default='Homo sapiens')
    p=sub.add_parser('link-samson');p.add_argument('run');p.add_argument('candidate');p.add_argument('role',choices=store.ROLES);p.add_argument('url');p.add_argument('--preset',choices=store.PRESETS,default='cartoon')
    args=parser.parse_args()
    if args.command=='check':print(json.dumps(renderer.check(refresh=True),indent=2))
    elif args.command=='render-run':
        import time
        m=store.manifest(args.run)
        if not renderer.check()['available']:raise SystemExit(renderer.check()['reason'])
        for candidate in args.candidate or ['target',*m['candidates']]:
            status=renderer.submit(args.run,candidate,args.preset)
            while status['state'] in ('queued','running'):
                time.sleep(1);status=renderer.get_status(args.run,candidate,args.preset)
            print(json.dumps({'candidate':candidate,'state':status['state'],'reason':status.get('reason'),'artifacts':status.get('artifacts')}),flush=True)
            if status['state']!='ready':raise SystemExit(1)
    elif args.command=='import-tamarind':print(store.import_tamarind(args.cache_file))
    elif args.command=='resolve-target':print(json.dumps(resolve_target(args.accession,args.species),indent=2))
    elif args.command=='link-samson':link_samson(args.run,args.candidate,args.role,args.url,args.preset);print('Published document linked; content identity must be verified by the publisher.')

if __name__=='__main__':main()
