from unittest.mock import Mock
import pytest
from protolab import research

def candidate(cid='design-1',seq='A'*80,binding=.9,structure=.8):
    return {'id':cid,'sequence':seq,'structure_state':'ready','metrics':{'binding_confidence':binding,'structure_confidence':structure}}

def test_missing_confidence_is_not_fabricated_or_ranked():
    rows,selected,diagnostic=research.screen({'candidates':[candidate(binding=None)]})
    assert not selected and not diagnostic
    assert rows[0]['metrics']['binding_confidence'] is None
    assert 'missing_model_confidence' in rows[0]['reasons']

def test_no_pass_produces_explicit_diagnostics_not_selected():
    rows,selected,diagnostic=research.screen({'candidates':[candidate(binding=.1)]})
    assert selected==[] and diagnostic==['design-1'] and not rows[0]['passed']

def test_duplicate_candidates_excluded_and_real_metrics_ranked():
    rows,selected,diagnostic=research.screen({'candidates':[candidate(),candidate('design-2'),candidate('design-3','G'*80,.95,.9)]})
    assert selected==['design-3','design-1'] and not diagnostic
    assert 'duplicate_sequence' in rows[1]['reasons']

@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(research,'ROOT',tmp_path)
    return tmp_path

def test_existing_run_is_not_resubmitted(isolated,monkeypatch):
    rid='research-'+'a'*32
    research.write({'id':rid,'stage':'complete','jobName':'existing','events':[]})
    submit=Mock();monkeypatch.setattr(research.tamarind,'submit',submit)
    assert research.start(rid)['jobName']=='existing'
    submit.assert_not_called()

def test_read_cannot_escape_storage(isolated):
    with pytest.raises(ValueError):research.read('../../secret')

def test_target_sequence_changes_produce_new_run(isolated,monkeypatch):
    entry={'primaryAccession':'P00533','organism':{'scientificName':'Homo sapiens'},'sequence':{'value':'A'*100},'features':[{'type':'Topological domain','description':'Extracellular','location':{'start':{'value':25},'end':{'value':90}}}],'genes':[{'geneName':{'value':'EGFR'}}],'proteinDescription':{'recommendedName':{'fullName':{'value':'EGFR'}}}}
    response=Mock();response.json=lambda:entry
    client=Mock();client.get.return_value=response;client.__enter__=Mock(return_value=client);client.__exit__=Mock()
    monkeypatch.setattr(research.httpx,'Client',Mock(return_value=client))
    data={'target':'P00533','species':'Homo sapiens'}
    a=research.resolve(data);assert a['spec']['length']==66 and 'target_sequence' not in a
    assert research.resolve(data)['id']==a['id']
    entry['sequence']['value']='G'*100
    b=research.resolve(data);assert b['id']!=a['id']
    data['species']='Mus musculus'
    with pytest.raises(ValueError,match='species'):research.resolve(data)

def test_wrong_target_results_never_reach_visualization(isolated,monkeypatch):
    rid='research-'+'b'*32
    research.write({'id':rid,'stage':'computing','jobName':'existing','target_sequence':'A'*100,'events':[]})
    provider=isolated/'existing.json';provider.with_suffix('.attempt').touch()
    monkeypatch.setattr(research.tamarind,'record_for',lambda job:(provider,{}))
    monkeypatch.setattr(research.tamarind,'status',lambda job:{'state':'Complete'})
    monkeypatch.setattr(research.tamarind_results,'load',lambda job:{'target_sequence':'G'*100})
    importer=Mock();monkeypatch.setattr(research.store,'import_tamarind',importer)
    research.work(rid)
    assert research.read(rid)['stage']=='failed'
    assert 'target sequence' in research.read(rid)['error']
    importer.assert_not_called()

def test_stopped_job_does_not_resume(isolated,monkeypatch):
    rid='research-'+'c'*32
    research.write({'id':rid,'stage':'stopped','jobName':'cancelled-job','events':[]})
    launch=Mock();monkeypatch.setattr(research,'launch',launch)
    assert research.status(rid)['stage']=='stopped'
    assert research.start(rid)['stage']=='stopped'
    launch.assert_not_called()

def test_secreted_mature_chain_excludes_annotated_signal(isolated,monkeypatch):
    entry={'primaryAccession':'P60568','organism':{'scientificName':'Homo sapiens'},'sequence':{'value':'A'*20+'G'*133},'features':[{'type':'Signal','location':{'start':{'value':1},'end':{'value':20}}},{'type':'Chain','location':{'start':{'value':21},'end':{'value':153}}}],'genes':[{'geneName':{'value':'IL2'}}],'proteinDescription':{'recommendedName':{'fullName':{'value':'Interleukin-2'}}}}
    response=Mock();response.json=lambda:entry
    client=Mock();client.get.return_value=response;client.__enter__=Mock(return_value=client);client.__exit__=Mock()
    monkeypatch.setattr(research.httpx,'Client',Mock(return_value=client))
    r=research.resolve({'target':'P60568'})
    assert r['spec']['start']==21 and r['spec']['end']==153 and r['spec']['length']==133
    assert research.read(r['id'])['target_sequence']=='G'*133

def test_demo_catalog_is_read_only_and_resumes_existing_jobs(isolated,monkeypatch):
    rid='research-'+'d'*32
    monkeypatch.setattr(research,'DEMO_IDS',{'test':rid,'missing':'research-'+'e'*32})
    research.write({'id':rid,'stage':'complete','target_sequence':'SECRET_SEQUENCE','events':[]})
    launch=Mock();monkeypatch.setattr(research,'launch',launch)
    result=research.demos()
    assert result['test']['stage']=='complete' and 'target_sequence' not in result['test']
    assert result['missing'] is None
    launch.assert_not_called()

def test_startup_resumes_only_requested_nonterminal_tasks(isolated,monkeypatch):
    states=['ready','stopped','complete','computing','rendering','failed']
    for i,state in enumerate(states):research.write({'id':'research-'+str(i)*32,'stage':state})
    launch=Mock();monkeypatch.setattr(research,'launch',launch)
    research.resume_pending()
    assert {call.args[0] for call in launch.call_args_list}=={'research-'+'3'*32,'research-'+'4'*32}

def test_top_three_keeps_failed_predictions_distinct_from_passes():
    rows,selected,diagnostic=research.screen({'candidates':[candidate(),candidate('design-2','G'*80,.3),candidate('design-3','L'*80,.2),candidate('design-4','K'*80,.1)]})
    assert selected==['design-1']
    assert diagnostic==['design-2','design-3']
    assert len(selected+diagnostic)==3
    assert not rows[1]['passed'] and not rows[2]['passed']

def test_bundled_demos_restore_without_overwriting(tmp_path,monkeypatch):
    root=tmp_path/'runs'/'research';monkeypatch.setattr(research,'ROOT',root)
    bundled=tmp_path/'demo-data'/'research';bundled.mkdir(parents=True)
    (bundled/'demo.json').write_text('bundled')
    research.install_bundled_demos();assert (root/'demo.json').read_text()=='bundled'
    (root/'demo.json').write_text('local')
    research.install_bundled_demos();assert (root/'demo.json').read_text()=='local'
