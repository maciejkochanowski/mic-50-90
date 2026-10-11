"""The original range method must obey the common population-result contract."""
from copy import deepcopy
from fractions import Fraction as F

import pytest

from mic_50_90.distribution_workflow import distribution_problems
from mic_50_90.joint_population import population_distribution, update_population_distribution


def data():
    return dict(cohort_id='control',n=20,unit='mg/L',panel={'levels':[1,2]},iid=True,
                additional_counts=[dict(n=20,unit='mg/L',threshold=2,count=2,source='Control counts')])


def problems(raw):
    return distribution_problems(raw)[0]


def test_no_refinement_retains_own_region_and_metadata():
    r=population_distribution(problems(data()),method='range-hunter',time_limit_seconds=0,include_intervals=True)
    assert r['method']==r['requested_method']=='range-hunter'
    assert r['statistical_target']=='pairwise-range-monotone-majorant'
    assert r['family_kind']=='all_contiguous_ranges_up_to_complements'
    assert r['family_size']==3
    assert len(r['interval_bounds'])==6
    assert len(r['category_bounds'])==3 and len(r['cdf_bounds'])==2
    assert r['bounds_kind']=='conservative_outer'
    assert r['confidence_level']==.95 and r['constraint_signature']
    assert not r['precision_reached']


def test_width_goal_and_endpoint_tolerance_are_independent():
    r=population_distribution(problems(data()),method='range-hunter',time_limit_seconds=0,
                              include_intervals=True,width_target_pp=100)
    assert r['width_goal']['status']=='met'
    assert not r['precision_reached']


def test_optional_failure_keeps_selected_method_bounds(monkeypatch):
    from mic_50_90._hunter import score
    real=score.project
    def fail(*a,**kw):
        if kw.get('time_limit_seconds',0)>0:raise MemoryError('forced allocation failure')
        return real(*a,**kw)
    monkeypatch.setattr(score,'project',fail)
    r=population_distribution(problems(data()),method='range-hunter',time_limit_seconds=1,include_intervals=True)
    assert r['status']=='calculation_incomplete'
    assert r['method']=='range-hunter'
    assert 'failure' in r['reason']
    assert all(0<=a<=b<=1 for a,b in r['category_bounds'])


def test_same_sample_update_preserves_all_saved_range_bounds():
    raw=data();old=problems(raw)
    saved=population_distribution(old,method='range-hunter',time_limit_seconds=0,include_intervals=True)
    newraw=deepcopy(raw)
    newraw['additional_counts'].append(dict(n=20,unit='mg/L',threshold=1,count=8,source='Control counts'))
    new=problems(newraw)
    result=update_population_distribution(old,new,saved,time_limit_seconds=0,include_intervals=True)
    assert result['previous_outer_bounds_preserved']
    assert result['requested_method']=='range-hunter'
    for before,after in zip(saved['interval_bounds'],result['interval_bounds']):
        assert before['lower']<=after['lower']<=after['upper']<=before['upper']


def test_adapter_outer_contains_independently_accepted_small_laws():
    from mic_50_90._hunter.endpoint import certify_witness
    from mic_50_90._hunter.pairwise import as_region
    raw=data();raw['n']=3
    raw['additional_counts']=[dict(n=3,unit='mg/L',threshold=1,count=2),dict(n=3,unit='mg/L',threshold=2,count=1)]
    p=problems(raw);r=population_distribution(p,method='range-hunter',time_limit_seconds=0,include_intervals=True)
    region=as_region(p);checked=0
    for a in range(5):
        for b in range(5-a):
            law=(F(a,4),F(b,4),F(4-a-b,4))
            if not certify_witness(region,law)['accepted']:continue
            checked+=1
            for row in r['interval_bounds']:
                q=sum(law[row['start_index']:row['stop_index']])
                assert F(row['lower'])<=q<=F(row['upper'])
    assert checked


def test_method_switch_during_update_is_rejected():
    p=problems(data());old=population_distribution(p,time_limit_seconds=0)
    with pytest.raises(ValueError,match='original population method'):
        update_population_distribution(p,p,old,method='range-hunter',time_limit_seconds=0)


def test_width_metadata_is_recomputed_after_projection_tightening():
    from mic_50_90.hunter_population import refresh_projection_metadata
    row=dict(start_index=0,stop_index=1,lower=0.,upper=.04,inner_lower=None,inner_upper=None,
             width_status='unresolved')
    r=dict(interval_bounds=[row],width_goal={'target_pp':5.,'status':'unresolved'},
           numerical_tolerance_pp=.01,status='time_limit')
    refresh_projection_metadata(r)
    assert row['width_status']=='met'
    assert r['width_goal']['status']=='met'
    assert not r['precision_reached'] and r['endpoint_gap_pp'] is None


def test_workflow_and_html_identify_the_original_range_method(tmp_path):
    from mic_50_90.distribution_workflow import analyse_distribution
    from mic_50_90.distribution_report import render_distribution_html
    r=analyse_distribution(data(),population_method='range-hunter',population_time_limit=0,
                           population_precision_pp='100')
    assert r['population']['method']=='range-hunter'
    assert r['population']['width_goal']['status']=='met'
    assert r['population_resolution']['guaranteed_number_of_bins']==3
    path=tmp_path/'report.html'
    render_distribution_html({'software_version':'1.0.0','cohorts':[r]},path)
    html=path.read_text(encoding='utf-8')
    assert 'Joint refinement across MIC ranges' in html
    assert '3 range comparisons covered together' in html
    assert 'Requested interval width confirmed' in html


def test_invalid_width_goal_does_not_remove_sample_or_population_result():
    from mic_50_90.distribution_workflow import analyse_distribution
    r=analyse_distribution(data(),population_method='range-hunter',population_time_limit=0,
                           population_precision_pp='bad')
    assert r['sample']['status']=='complete'
    assert r['population']['method']=='range-hunter'
    assert r['population_resolution']['status']=='unavailable'


def test_cli_and_desktop_use_the_same_selected_method(tmp_path):
    import json
    from mic_50_90.cli import main
    from mic_50_90.gui_worker import execute_job
    source=tmp_path/'input.json';source.write_text(json.dumps(data()),encoding='utf-8')
    assert main(['distribution',str(source),'--population-method','range-hunter',
                 '--population-time-limit','0','--population-precision-pp','100',
                 '--output-dir',str(tmp_path/'cli')])==0
    execute_job(dict(mode='distribution',config=data(),options=dict(
        population_method='range-hunter',population_time_limit=0,population_precision_pp='100')),
        tmp_path/'desktop')
    status=json.loads((tmp_path/'desktop/job-status.json').read_text())
    assert status['status']=='completed',status
    cli=json.loads((tmp_path/'cli/results.json').read_text())['cohorts'][0]
    desktop=json.loads((tmp_path/'desktop/output/results.json').read_text())['cohorts'][0]
    assert cli['population']['method']==desktop['population']['method']=='range-hunter'
    assert cli['population']['interval_bounds']==desktop['population']['interval_bounds']
    assert cli['population_resolution']==desktop['population_resolution']


def test_count_planning_accepts_original_method_without_switching():
    from mic_50_90.population_acquisition import plan_population_precision
    r=plan_population_precision(problems(data()),method='range-hunter',precision_pp=100,
                                projection_time_limit_seconds=0,time_limit_seconds=1)
    assert r['method']=='range-hunter'
    assert r['status']=='achieved' and r['cost_upper']=='0'
