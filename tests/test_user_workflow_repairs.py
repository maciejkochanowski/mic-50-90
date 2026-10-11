"""Cross-interface information must survive serialization and saved updates."""
from copy import deepcopy
import json

import pytest

from mic_50_90.gui_forms import desktop_examples, validate_payload
from mic_50_90.gui_worker import execute_job
from mic_50_90.distribution_workflow import analyse_distribution


@pytest.mark.parametrize('measurement', [dict(count=10), dict(count_min=9,count_max=10),
    dict(percentage=50,decimal_places=0,rounding_rule='half_up')])
def test_interval_counts_survive_gui_batch(tmp_path,measurement):
    payload=deepcopy(desktop_examples()[0]['payload'])
    row=dict(start_category='2',end_category='2',n=20,unit='mg/L',**measurement)
    payload['config']['additional_counts']=[row]
    payload.update(mode='batch',targets=[dict(threshold=2,unit='mg/L')])
    assert validate_payload(payload)['valid']
    execute_job(payload,tmp_path)
    assert json.loads((tmp_path/'job-status.json').read_text())['status']=='completed'
    import csv
    with (tmp_path/'input/additional-counts.csv').open(newline='') as f:
        saved=list(csv.DictReader(f))[0]
    assert saved['start_category']==saved['end_category']=='2'


@pytest.mark.parametrize('key,value', [('population_precision_pp',101),
    ('population_precision_pp',-1),('population_time_limit',-1),
    ('population_tolerance_pp',0),('population_minimum_bins',1.5),
    ('population_count_plan','yes'),('population_method',[]),('population_method',{})])
def test_gui_preflight_catches_optional_settings(key,value):
    payload=deepcopy(desktop_examples()[0]['payload'])
    payload['options'][key]=value
    result=validate_payload(payload)
    assert not result['valid']
    assert any(issue['field']=='options.'+key for issue in result['issues'])


def test_invalid_population_precision_retains_sample_and_basic_population():
    raw=deepcopy(desktop_examples()[0]['payload']['config']);raw['iid']=True
    original=analyse_distribution(raw)
    result=analyse_distribution(raw,population_precision_pp=101)
    assert result['sample']==original['sample']
    assert result['population']['cdf_bounds']==original['population']['cdf_bounds']
    assert result['population_resolution']['status']=='unavailable'


def test_optional_partition_failure_retains_basic_results(monkeypatch):
    import mic_50_90.population_precision as precision
    def interrupted(*args,**kwargs):
        raise TimeoutError('controlled interruption')
    monkeypatch.setattr(precision,'maximum_population_partition',interrupted)
    raw=deepcopy(desktop_examples()[0]['payload']['config']);raw['iid']=True
    result=analyse_distribution(raw,population_precision_pp=10)
    assert result['sample']['categories']
    assert result['population']['cdf_bounds']
    assert result['population_resolution']['status']=='unavailable'


def test_saved_update_exposes_retained_precision_in_every_projection():
    raw=dict(n=3,panel={'levels':[1,2]},unit='mg/L',iid=True,confidence_level=.5,
        additional_counts=[dict(start_category='<=1',end_category='<=1',count=1,n=3,unit='mg/L')])
    old=analyse_distribution(raw,population_method='joint-exact',population_time_limit=2,population_tolerance_pp=2)
    new=deepcopy(raw)
    new['additional_counts'].append(dict(start_category='2',end_category='2',count=1,n=3,unit='mg/L'))
    updated=analyse_distribution(new,population_method='joint-exact',population_time_limit=0,
        population_tolerance_pp=2,population_precision_pp=60,
        previous_analysis=dict(input=raw,population_method='joint-exact',result=old))
    pop=updated['population']
    row=next(r for r in pop['interval_bounds'] if (r['start_index'],r['stop_index'])==(0,1))
    assert [row['lower'],row['upper']]==pop['cdf_bounds'][0]==pop['category_bounds'][0]
    assert updated['population_resolution']['guaranteed_number_of_bins']>=2


@pytest.mark.parametrize('seconds',[0,10])
def test_planning_contract_present_for_every_terminal_status(seconds):
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICPanel
    from mic_50_90.population_acquisition import plan_population_precision
    p=EmpiricalProblem(n=2,panel=MICPanel.from_dict({'levels':[1,2],'right_censored':False}),quantiles=[])
    r=plan_population_precision({'primary':p},precision_pp='1.00',time_limit_seconds=seconds)
    assert r['precision_pp']==1
    assert r['precision_pp_text']=='1.00'
    assert r['minimum_bins']==2 and r['confidence_level']==.95
    assert r['method']=='bonferroni' and r['n']==2 and r['scope']


def test_distribution_opening_explains_known_unknown_and_next_step():
    from mic_50_90.result_view import distribution_overview
    payload=next(e['payload'] for e in desktop_examples() if e['id']=='published7133')
    html=distribution_overview(analyse_distribution(payload['config']))
    for text in ['Result for this collection','Reading the graph','What to do next','5407','1583','143']:
        assert text in html


def test_verification_schema_migration_preserves_scientific_differences():
    from mic_50_90.result_schema import normalize_reporting_verification
    old={'bounds':[dict(count_min=0,count_max=4)],'decisions':['undetermined']}
    current=deepcopy(old);current['bounds'][0]['count_components']=[[0,4]]
    assert normalize_reporting_verification(old)==normalize_reporting_verification(current)
    current['bounds'][0]['count_components']=[[0,1],[3,4]]
    assert normalize_reporting_verification(old)!=normalize_reporting_verification(current)
    current=deepcopy(old);current['decisions']=['supported']
    assert normalize_reporting_verification(old)!=normalize_reporting_verification(current)
    assert 'count_components' not in old['bounds'][0]


def test_distribution_saved_schema_and_legacy_loading(tmp_path):
    from mic_50_90.distribution_workflow import _load_previous_output
    payload=deepcopy(desktop_examples()[0]['payload'])
    execute_job(payload,tmp_path)
    out=tmp_path/'output'
    results=json.loads((out/'results.json').read_text())
    assert results['result_schema']=='mic-50-90.distribution/1'
    assert _load_previous_output(out)
    results.pop('result_schema')
    (out/'results.json').write_text(json.dumps(results))
    assert _load_previous_output(out)
    results['result_schema']='unknown/999'
    (out/'results.json').write_text(json.dumps(results))
    with pytest.raises(ValueError,match='schema'):
        _load_previous_output(out)


def test_laboratory_opening_explains_scope():
    from mic_50_90 import verify_reporting
    from mic_50_90.result_view import verification_overview
    from pathlib import Path
    certificate=json.loads((Path(__file__).parents[1]/'examples/received_report/certificate.json').read_text())['certificates'][0]
    checked=verify_reporting(certificate['specification'],certificate['criteria'],certificate['disclosures'])
    html=verification_overview(checked,certificate['disclosures'])
    for text in ['What we know','What remains unknown','What to do next','not identify its full histogram']:
        assert text in html


def test_unknown_optional_method_does_not_drop_sample():
    raw=deepcopy(desktop_examples()[0]['payload']['config']);raw['iid']=True
    result=analyse_distribution(raw,population_method='unknown')
    assert result['sample']['categories']
    assert result['population']['status']=='unavailable'
    assert 'population_method' in result['option_issues']


def test_interrupted_saved_refinement_preserves_sample_and_allows_retry(monkeypatch):
    import mic_50_90.joint_population as joint
    raw=deepcopy(desktop_examples()[0]['payload']['config']);raw['iid']=True
    old=analyse_distribution(raw)
    new=deepcopy(raw)
    new['additional_counts']=[dict(threshold=2,count=1,n=20,unit='mg/L')]
    def interrupted(*args,**kwargs):
        raise MemoryError('controlled optional failure')
    with monkeypatch.context() as patch:
        patch.setattr(joint,'update_population_distribution',interrupted)
        result=analyse_distribution(new,previous_analysis=dict(input=raw,population_method='bonferroni',result=old))
    assert result['sample']['categories']
    assert result['population']['status']=='unavailable'
    retried=analyse_distribution(new,previous_analysis=dict(input=new,population_method='bonferroni',result=result))
    assert retried['population']['cdf_bounds']==analyse_distribution(new)['population']['cdf_bounds']


def test_mismatched_saved_population_never_reused():
    raw=dict(n=10,panel={'levels':[1,2]},iid=True,unit='mg/L',
        additional_counts=[dict(start_category='<=1',end_category='<=1',count=2,n=10,unit='mg/L')])
    wrong=deepcopy(raw);wrong['additional_counts'][0]['count']=9
    result=analyse_distribution(raw,previous_analysis=dict(input=raw,population_method='bonferroni',result=analyse_distribution(wrong)))
    assert result['sample']['categories'][0]['count_lower']==2
    assert result['population']['status']=='unavailable'
    assert 'cdf_bounds' not in result['population']
