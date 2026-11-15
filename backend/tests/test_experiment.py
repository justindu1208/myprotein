import csv, io, json, zipfile
from pathlib import Path
from unittest.mock import Mock
import pytest
from protolab import experiment, research, visualization_store as store

@pytest.fixture
def fixture_task(tmp_path,monkeypatch):
    monkeypatch.setattr(research,'ROOT',tmp_path/'research')
    monkeypatch.setattr(experiment,'ROOT',tmp_path/'experiments')
    rid='research-'+'a'*32
    candidates=[{'id':f'design-{i}','sequence':chr(65+i)*80} for i in range(1,4)]
    research.write({'id':rid,'target_sequence':'A'*50,'candidates':candidates,'selected':['design-1'],'diagnostic':['design-2','design-3'],'spec':{'count':10},'stage':'complete'})
    return rid

def test_start_creates_exactly_three_jobs_and_never_resubmits(fixture_task,monkeypatch):
    launch=Mock();monkeypatch.setattr(experiment,'launch',launch)
    first=experiment.start(fixture_task);second=experiment.start(fixture_task)
    assert first==second and first['state']=='running'
    assert [j['candidate_id'] for j in first['jobs']]==['design-1','design-2','design-3']
    assert len({j['jobName'] for j in first['jobs']})==3
    assert 'target_sequence' not in first

def test_missing_shortlist_does_not_submit(fixture_task,monkeypatch):
    launch=Mock();monkeypatch.setattr(experiment,'launch',launch)
    with pytest.raises(ValueError,match='at least one'):experiment.start(fixture_task,[])
    launch.assert_not_called()

def test_select_and_append_candidates_without_duplicates(fixture_task,monkeypatch):
    monkeypatch.setattr(experiment,'launch',Mock())
    first=experiment.start(fixture_task,['design-2'])
    assert [j['candidate_id'] for j in first['jobs']]==['design-2']
    with pytest.raises(ValueError,match='current predictions'):experiment.start(fixture_task,['design-1'])
    first['state']='finished_with_errors';first['jobs'][0]['state']='failed';experiment.write(first)
    with pytest.raises(ValueError,match='already has'):experiment.start(fixture_task,['design-2'])
    with pytest.raises(ValueError,match='Duplicate'):experiment.start(fixture_task,['design-1','design-1'])
    with pytest.raises(ValueError,match='sequence missing'):experiment.start(fixture_task,['unknown'])
    result=experiment.start(fixture_task,['design-3','design-1'])
    assert [j['candidate_id'] for j in result['jobs']]==['design-2','design-3','design-1']

def test_interrupted_submission_not_retried(fixture_task,monkeypatch):
    j={'candidate_id':'design-1','jobName':'protolab-'+'b'*32,'state':'submitting'}
    experiment.write({'research_id':fixture_task,'state':'running','jobs':[j]})
    api=Mock();monkeypatch.setattr(experiment.tamarind,'api',api)
    experiment.work(fixture_task)
    assert experiment.read(fixture_task)['jobs'][0]['state']=='submission_uncertain'
    api.assert_not_called()

def test_boltz_output_checks_both_chain_sequences(monkeypatch):
    base=Path(__file__).resolve().parents[2]/'demo-data'/'visualizations'
    candidates=list(base.glob('*/design-*/complex.cif'))
    if not candidates:pytest.skip('Bundled structure unavailable')
    structure=store.read_structure(candidates[0].read_text());chains=list(structure[0]);assert len(chains)==2
    target=store.chain_sequence(chains[0]);binder=store.chain_sequence(chains[1])
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:
        z.writestr('metrics.csv','pdb_filepath,confidence_score,iptm\ncomplex.cif,0.81,0.76\n')
        z.writestr('complex.cif',candidates[0].read_text())
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def raise_for_status(self):pass
        def iter_bytes(self):yield stream.getvalue()
    client=Mock();client.__enter__=Mock(return_value=client);client.__exit__=Mock();client.stream.return_value=Response()
    monkeypatch.setattr(experiment.httpx,'Client',Mock(return_value=client));monkeypatch.setattr(experiment.tamarind,'api',lambda *args:'https://example.org/result')
    _,fmt,chain,metrics=experiment.get_results('job',target,binder)
    assert fmt=='cif' and chain==chains[1].name and metrics['iptm']==.76
    with pytest.raises(ValueError,match='sequences'):experiment.get_results('job','G'*len(target),binder)

def test_three_submissions_use_matched_sequences_and_one_sample(fixture_task,monkeypatch):
    launch=Mock();monkeypatch.setattr(experiment,'launch',launch)
    record=experiment.start(fixture_task);requests=[]
    def api(path,body=None):
        requests.append((path,body))
        if path=='validate-job':return {'valid':True,'normalized':body['settings']}
        if path=='submit-job':return {'accepted':True}
        if path.startswith('jobs?jobName='):return {'JobStatus':'Failed'}
        raise AssertionError(path)
    monkeypatch.setattr(experiment.tamarind,'api',api)
    experiment.work(fixture_task)
    submitted=[body for path,body in requests if path=='submit-job']
    assert len(submitted)==3 and all(x['type']=='boltz' for x in submitted)
    assert [x['settings']['sequence'] for x in submitted]==['A'*50+':'+chr(65+i)*80 for i in range(1,4)]
    assert all(x['settings']['numSamples']==1 for x in submitted)
    assert experiment.read(fixture_task)['state']=='finished_with_errors'
    experiment.start(fixture_task)
    assert len([1 for path,body in requests if path=='submit-job'])==3

def test_experiment_restart_resumes_running_without_resubmitting_completed(fixture_task,monkeypatch):
    experiment.write({'research_id':fixture_task,'state':'running','jobs':[]})
    launch=Mock();monkeypatch.setattr(experiment,'launch',launch)
    experiment.resume_pending();launch.assert_called_once_with(fixture_task)
    launch.reset_mock();experiment.write({'research_id':fixture_task,'state':'finished_with_errors','jobs':[]})
    experiment.resume_pending();launch.assert_not_called()

def test_boltz_submit_removes_invalid_inactive_default(fixture_task,monkeypatch):
    monkeypatch.setattr(experiment,'launch',Mock());experiment.start(fixture_task)
    submitted=[]
    def api(path,body=None):
        if path=='validate-job':return {'valid':True,'normalized':{**body['settings'],'useBoltzServer':False,'predictProteinAffinity':False}}
        if path=='submit-job':submitted.append(body);return {'accepted':True}
        if path.startswith('jobs?jobName='):return {'JobStatus':'Failed'}
        raise AssertionError(path)
    monkeypatch.setattr(experiment.tamarind,'api',api);experiment.work(fixture_task)
    assert len(submitted)==3
    assert all('predictProteinAffinity' not in x['settings'] for x in submitted)

def test_retry_checks_provider_and_never_resubmits_existing_job(fixture_task,monkeypatch):
    jobs=[{'candidate_id':'design-1','jobName':'protolab-'+'b'*32,'state':'submission_uncertain','reason':'Tamarind HTTP 400; inspect account access and settings'}]
    experiment.write({'research_id':fixture_task,'state':'finished_with_errors','jobs':jobs})
    launch=Mock();monkeypatch.setattr(experiment,'launch',launch)
    monkeypatch.setattr(experiment.tamarind,'api',lambda path:{'jobs':[{'JobName':jobs[0]['jobName']} ]})
    with pytest.raises(ValueError,match='exists'):experiment.retry_rejected(fixture_task)
    launch.assert_not_called()
    monkeypatch.setattr(experiment.tamarind,'api',lambda path:{'jobs':[]})
    retry=experiment.retry_rejected(fixture_task)
    assert retry['state']=='running' and retry['jobs'][0]['state']=='pending'
    launch.assert_called_once_with(fixture_task)
