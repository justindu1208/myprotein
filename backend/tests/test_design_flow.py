import json
from unittest.mock import patch
import pytest
from protolab import design

@pytest.fixture
def run(tmp_path,monkeypatch):
    monkeypatch.setattr(design,'RUN',tmp_path)
    (tmp_path/'submission.json').write_text(json.dumps({'id':'run1'}))
    (tmp_path/'attempt.json').write_text(json.dumps({'body':{'target':{'entities':[{'value':'ACDEFGHIKLMN'}]},'binder_specification':{'entities':[{'value':'10..20'}]}}}))
    return tmp_path

def test_results_pagination_qc_and_selection(run):
    def fake(url,body=None):
        if url.endswith('/run1'): return {'status':'succeeded','livemode':True}
        if 'after_id=' in url: return {'data':[{'id':'b','entities':[{'type':'protein','chain_ids':['B'],'value':'ACDEFGHIKL'}],'metrics':{'binding_confidence':.95}}], 'has_more':False}
        return {'data':[{'id':'a','entities':[{'type':'protein','chain_ids':['B'],'value':'ACDEFGHIKL'}],'metrics':{'binding_confidence':.8}}], 'has_more':True,'last_id':'a'}
    with patch.object(design,'api',side_effect=fake): result=design.results()
    assert result['selected_for_prediction']==['a']
    assert 'DUPLICATE_CANDIDATE' in result['candidates'][1]['qc']['reasons']

def test_prediction_submission_is_never_repeated(run):
    body={'model':'boltz-2.1','input':{}}
    plan={'jobs':[['a',body]],'estimates':[],'estimated_total_usd':'0.1'}
    plan['input_hash']=design.digest(plan)
    (run/'prediction-estimate.json').write_text(json.dumps(plan))
    with patch.object(design,'prediction_payloads',return_value=[('a',body)]), patch.object(design,'api',return_value={'id':'job1'}) as api:
        design.start_predictions({'input_hash':plan['input_hash']})
        design.start_predictions({'input_hash':plan['input_hash']})
    assert api.call_count==1

def test_uncertain_submission_stops_without_retry(run):
    body={'model':'boltz-2.1','input':{}}
    plan={'jobs':[['a',body],['b',body]],'estimates':[],'estimated_total_usd':'0.2'}
    plan['input_hash']=design.digest(plan)
    (run/'prediction-estimate.json').write_text(json.dumps(plan))
    with patch.object(design,'prediction_payloads',return_value=[('a',body),('b',body)]), patch.object(design,'api',side_effect=TimeoutError) as api:
        out=design.start_predictions({'input_hash':plan['input_hash']})
        design.start_predictions({'input_hash':plan['input_hash']})
    assert api.call_count==1
    assert out['jobs'][0]['status']=='submission_uncertain'
