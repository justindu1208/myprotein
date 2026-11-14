"""Package source + one real visualization run, excluding credentials and API caches."""
import argparse
import json
from pathlib import Path
import zipfile

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('run');p.add_argument('output',type=Path);p.add_argument('--also',action='append',default=[],help='Additional real run to include');args=p.parse_args()
import sys
sys.path.insert(0,str(root/'backend'))
from protolab import visualization_store as store
from protolab.chimerax_renderer import OUTPUTS
runs=list(dict.fromkeys([args.run,*args.also]))
for rid in runs:store.identifier(rid);store.manifest(rid)
args.output.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED) as archive:
    def add(path):archive.write(path,Path('protolab')/path.relative_to(root))
    for folder in ('frontend','backend','scripts'):
        for path in (root/folder).rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            if any(part.startswith('.') or part=='__pycache__' for part in path.relative_to(root/folder).parts):continue
            if path.suffix in ('.py','.js','.cjs','.css','.html','.txt','.sh','.cmd','.md'):add(path)
    add(root/'MOLECULAR_EVIDENCE.md')
    add(root/'LIVE_RESEARCH.md')
    for rid in runs:
        run=store.directory(rid);manifest=store.manifest(rid)
        add(run/'manifest.json')
        if manifest.get('research_id'):
            report=root/'runs/research'/(manifest['research_id']+'.json')
            if report.is_file():add(report)
        for cid in ['target',*manifest.get('candidates',{})]:
            for path in (run/cid).glob('*'):
                if path.suffix in ('.pdb','.cif') and path.is_file() and not path.is_symlink():add(path)
            for metadata in (run/cid/'renders').glob('*/metadata.json'):
                saved=json.loads(metadata.read_text())
                if saved.get('state')!='ready':continue
                checks=saved.get('checksums',{})
                if not checks or any(n not in OUTPUTS or not (metadata.parent/n).is_file() or store.sha((metadata.parent/n).read_bytes())!=digest for n,digest in checks.items()):raise ValueError('Corrupt media')
                add(metadata)
                for name in [*checks,'render.cxc']:
                    path=metadata.parent/name
                    if path.is_file() and not path.is_symlink():add(path)
print(args.output)
