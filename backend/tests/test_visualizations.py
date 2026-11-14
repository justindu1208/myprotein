import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from protolab import visualization_store as store
from protolab import visualizations as api
from protolab.chimerax_renderer import ChimeraXRenderer

PDB=('ATOM      1  CA  ALA A   1      11.000  12.000  13.000  1.00 80.00           C  \n'
     'ATOM      2  CA  GLY B   1      14.000  12.000  13.000  1.00 80.00           C  \n')

@pytest.fixture
def registered(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path/'runs')
    s=store.read_structure(PDB,'pdb');m=s.clone();del m[0]['A'];target=s.clone();del target[0]['B']
    manifest={'run_id':'run-1','target':store.add_asset('run-1','target','target',target,'test prediction',True,'job-1'), 'candidates':{'RF-004':{'candidate_id':'RF-004','monomer':store.add_asset('run-1','RF-004','monomer',m,'test prediction',True,'job-1'),'complex':store.add_asset('run-1','RF-004','complex',s,'test prediction',True,'job-1'),'target_chains':['A'],'binder_chains':['B'],'interface':store.interface(s,['A'],['B'])}},'transition_label':store.TRANSITION_LABEL}
    store.write_manifest(manifest)
    return manifest


def unavailable_renderer():
    r=ChimeraXRenderer();r.capability={'state':'not_installed','available':False,'version':None,'reason':'not installed'};return r


def test_real_roles_distinct_and_predicted(registered):
    a=store.asset('run-1','RF-004','monomer');b=store.asset('run-1','RF-004','complex')
    assert a['mmcif_url']!=b['mmcif_url'] and a['sha256']!=b['sha256']
    assert a['predicted'] and b['source_job_id']=='job-1'
    registered['candidates']['RF-004']['monomer']['role']='complex';store.write_manifest(registered)
    with pytest.raises(ValueError):store.structure_path('run-1','RF-004','monomer')


@pytest.mark.parametrize('value',['../bad','a/b','a; exit','a\nexit','%2e%2e',''])
def test_identifier_injection(value):
    with pytest.raises(ValueError):store.identifier(value)


def test_missing_samson_never_uses_example(registered):
    status=store.SamsonProvider.resolve(registered['target'])
    assert status=={'state':'not_published','document_url':None,'embed_url':None}


def test_untrusted_samson_url_rejected():
    with pytest.raises(ValueError):store.SamsonProvider.resolve({'samson_document_url':'https://evil.test/documents/123'})


def test_chain_and_residue_command_injection_rejected():
    base={'preset':'cartoon','target_chains':['A'],'binder_chains':['B; exit'],'interface':[]}
    with pytest.raises(ValueError):ChimeraXRenderer.script(base)
    base['binder_chains']=['B'];base['interface']=[{'chain':'A','number':'1; exit'}]
    with pytest.raises(ValueError):ChimeraXRenderer.script(base)


def test_missing_renderer_returns_script_not_fake_media(registered):
    r=unavailable_renderer();status=r.submit('run-1','RF-004')
    assert status['state']=='render_unavailable'
    assert list(status['artifacts'])==['render.cxc']
    assert 'not a molecular-dynamics trajectory' in status['transition_label']
    assert status['media_type']=='illustrative_media'
    folder,_=r.prepare('run-1','RF-004');script=(folder/'render.cxc').read_text()
    assert 'move x -0.5 70 models #3' in script
    assert 'show #1 models' in script and 'complex.mp4' in script
    assert not (folder/'complex.mp4').exists()


def test_cache_key_changes_with_parameters_or_version(registered):
    r=unavailable_renderer();_,a=r.prepare('run-1','RF-004');_,b=r.prepare('run-1','RF-004','surface')
    assert a['cache_key']!=b['cache_key']
    r.capability['version']='new-version';_,c=r.prepare('run-1','RF-004')
    assert a['cache_key']!=c['cache_key']


def test_render_failure_is_recoverable(registered,monkeypatch):
    r=unavailable_renderer();folder,status=r.prepare('run-1','RF-004');r.executable='/trusted/ChimeraX';r.flags=[]
    r.slots.acquire();monkeypatch.setattr('protolab.chimerax_renderer.subprocess.run',Mock(side_effect=RuntimeError('graphics unavailable')))
    r._run(folder,status)
    assert status['state']=='render_failed'
    r.capability={'available':True,'version':None,'reason':None}
    scheduled=[];monkeypatch.setattr(r.executor,'submit',lambda *args:scheduled.append(args))
    assert r.submit('run-1','RF-004')['state']=='queued' and len(scheduled)==1
    assert r.submit('run-1','RF-004')['state']=='queued' and len(scheduled)==1


def test_geometry_contacts_are_not_called_hbonds(registered):
    face=registered['candidates']['RF-004']['interface']
    assert len(face['residues'])==2 and face['contacts'][0]['distance_angstrom']==3
    assert 'not assigned hydrogen bonds' in face['method']


def test_raw_structure_download_and_path_rejection(registered):
    path,mime=api.serve_asset('run-1','RF-004','monomer.cif')
    assert path.is_file() and mime=='chemical/x-mmcif'
    with pytest.raises(ValueError):api.serve_asset('run-1','../RF-004','monomer.cif')
    with pytest.raises(ValueError):api.serve_asset('run-1','RF-004','../../.env')


def test_corrupted_structure_not_rendered(registered):
    p=store.structure_path('run-1','RF-004','complex');p.write_text('bad')
    with pytest.raises(ValueError,match='checksum'):unavailable_renderer().prepare('run-1','RF-004')


def test_no_procedural_molecule_code():
    root=Path(__file__).resolve().parents[2]/'frontend'
    code=(root/'app.js').read_text();html=(root/'index.html').read_text()
    assert 'makeMoleculePoints' not in code and 'drawMolecule' not in code
    assert 'id="molecule"' not in html
    assert 'Molecular Evidence' in html
    assert 'aria-label="ChimeraX molecular presentation video"' in html


def test_precomputed_media_portable_without_renderer(registered):
    r=unavailable_renderer();r.capability={'available':True,'version':'ChimeraX test','reason':None}
    folder,meta=r.prepare('run-1','RF-004')
    names=['monomer.png','complex.png','monomer.mp4','complex.mp4']
    for name in names:(folder/name).write_bytes(b'fixture media')
    meta.update(state='ready',checksums={n:store.sha((folder/n).read_bytes()) for n in names})
    (folder/'metadata.json').write_text(json.dumps(meta))
    other=unavailable_renderer()
    status=other.get_status('run-1','RF-004')
    assert status['state']=='ready' and status['chimerax_version']=='ChimeraX test'
    assert meta['cache_key'] in status['artifacts']['complex.mp4']
    assert other.get_status('run-1','RF-004','surface')['state']=='render_unavailable'
    (folder/'complex.mp4').write_bytes(b'corrupt')
    assert other.get_status('run-1','RF-004')['state']=='render_unavailable'

@pytest.mark.parametrize('requested,status,body',[('bytes=2-5',206,b'2345'),('bytes=-3',206,b'789'),('bytes=100-',416,b''),(None,200,b'0123456789')])
def test_media_byte_ranges(tmp_path,requested,status,body):
    import io
    from protolab.web import Handler
    media=tmp_path/'clip.mp4';media.write_bytes(b'0123456789')
    h=object.__new__(Handler);h.headers={'Range':requested} if requested else {};h.wfile=io.BytesIO()
    codes=[];h.send_response=codes.append;h.send_header=lambda *args:None;h.end_headers=lambda:None
    h.respond_file(media,'video/mp4')
    assert codes==[status] and h.wfile.getvalue()==body
