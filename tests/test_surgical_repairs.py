"""Regression checks for reporting variants and explicit count semantics."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from mic_50_90 import analyse_spec
from mic_50_90.model import parse_spec, MICPanel
from mic_50_90.count_updates import _observations, observation_coefficients
from mic_50_90.distribution_workflow import analyse_distribution


def specification():
    return dict(n=20, unit='mg/L', mode='empirical', panel=dict(levels=[1, 2, 4]),
                thresholds=[2], question_utility=dict(enabled=False),
                summaries=dict(quantiles=[
                    dict(probability=.5, category='2', convention='ceiling'),
                    dict(probability=.9, category='4', convention='ceiling')]))


def test_infeasible_primary_keeps_original_alternative_identity():
    raw = specification()
    good = deepcopy(raw['summaries'])
    raw['summaries']['minimum'] = '4'
    raw['reporting_envelope'] = dict(variants=[dict(id='source-alternative', summaries=good)])
    parsed = parse_spec(raw)
    assert [v.identifier for v in parsed.all_reporting_variants] == ['source-alternative']
    assert parsed.rejected_reporting_variants[0]['id'] == 'primary'
    assert analyse_spec(raw)['reporting_uncertainty_envelope']
    assert analyse_distribution(raw)['status'] == 'ok'


@pytest.mark.parametrize('threshold', [True, False, np.bool_(True), float('nan'), float('inf')])
def test_invalid_threshold_types_are_refused(threshold):
    raw = specification()
    raw['thresholds'] = [threshold]
    with pytest.raises(ValueError, match='threshold'):
        parse_spec(raw)


@pytest.mark.parametrize('relation,expected', [
    ('>', [0, 0, 1, 1]), ('>=', [0, 1, 1, 1]),
    ('<', [1, 0, 0, 0]), ('<=', [1, 1, 0, 0])])
def test_explicit_recorded_relations_select_categories(relation, expected):
    panel = MICPanel.from_dict(dict(levels=[1, 2, 4]))
    row = dict(threshold=2, relation=relation, source_scale='recorded', count=10, n=20, unit='mg/L')
    result = _observations([row], SimpleNamespace(n=20, panel=panel))[0]
    assert observation_coefficients(result, panel).tolist() == expected
    assert result['count'] == 10
    assert result['source_information']['source_scale'] == 'recorded'
    assert _observations([result], SimpleNamespace(n=20, panel=panel)) == [result]


def test_measurement_interval_count_cannot_split_a_category():
    panel = MICPanel.from_dict(dict(levels=[1, 2, 4]))
    row = dict(threshold=2, relation='>=', source_scale='interval', count=10, n=20, unit='mg/L')
    with pytest.raises(ValueError, match='category|interval'):
        _observations([row], SimpleNamespace(n=20, panel=panel))


@pytest.mark.parametrize('threshold', [True, False, np.bool_(True)])
def test_legacy_count_boolean_concentration_is_refused(threshold):
    panel = MICPanel.from_dict(dict(levels=[1, 2, 4]))
    with pytest.raises(ValueError, match='threshold'):
        _observations([dict(threshold=threshold,count=4,n=20,unit='mg/L')],
                      SimpleNamespace(n=20,panel=panel))


def test_legacy_relation_and_rounded_counts_keep_meaning():
    panel = MICPanel.from_dict(dict(levels=[1, 2, 4]))
    spec = SimpleNamespace(n=20, panel=panel)
    row = dict(threshold=2, relation='<=', count=10, n=20, unit='mg/L')
    old = _observations([row], spec)[0]
    assert old['threshold'] == 2 and old['count'] == 10
    assert 'source_scale' not in old
    row.update(source_scale='recorded', relation='>=')
    row.pop('count')
    row.update(percentage='50', decimal_places=0, rounding_rule='half_up')
    new = _observations([row], spec)[0]
    assert (new['count_min'], new['count_max']) == (10, 10)


def test_all_reporting_variants_infeasible_are_refused():
    raw = specification()
    raw['summaries']['minimum'] = '4'
    with pytest.raises(ValueError):
        analyse_spec(raw)


def test_malformed_alternative_is_not_silently_discarded():
    raw = specification()
    raw['reporting_envelope'] = dict(variants=[dict(id='bad', summaries='not an object')])
    with pytest.raises(ValueError):
        analyse_spec(raw)


@pytest.mark.parametrize('relation,threshold,count', [('>', 16, 0), ('<', .5, 0), ('>=', .5, 20), ('<=', 16, 20)])
def test_empty_and_full_recorded_selection(relation, threshold, count):
    raw = specification()
    raw['additional_counts'] = [dict(threshold=threshold, relation=relation, source_scale='recorded',
                                     count=count, n=20, unit='mg/L')]
    assert analyse_distribution(raw)['status'] == 'ok'
    raw['additional_counts'][0]['count'] = 1
    with pytest.raises(ValueError):
        analyse_distribution(raw)


@pytest.mark.parametrize('relation,threshold', [('>', 1.5), ('<=', 1.5), ('>=', 2), ('<', 2)])
def test_interval_semantics_keep_crossing_category_unresolved(relation, threshold):
    spec=SimpleNamespace(n=20,panel=MICPanel.from_dict(dict(levels=[1,2,4])))
    with pytest.raises(ValueError, match='category'):
        _observations([dict(threshold=threshold,relation=relation,source_scale='interval',count=10,n=20,unit='mg/L')],spec)


def test_recorded_and_interval_counts_agree_on_an_exact_partition():
    panel=MICPanel.from_dict({'categories':[
        dict(label='<2',lower_bound=None,upper_bound=2,upper_closed=False,panel_value=1),
        dict(label='>=2',lower_bound=2,upper_bound=None,lower_closed=True,panel_value=2)]})
    spec=SimpleNamespace(n=20,panel=panel)
    row=dict(threshold=2,relation='>=',count=10,n=20,unit='mg/L')
    results=[_observations([dict(row,source_scale=s)],spec)[0] for s in ('recorded','interval')]
    assert [observation_coefficients(x,panel).tolist() for x in results] == [[0,1],[0,1]]


@pytest.mark.parametrize('mode', ['distribution', 'batch'])
def test_form_csv_adapter_retains_count_scale_and_analysis(tmp_path, mode):
    import json
    from mic_50_90.gui_worker import execute_job
    raw=specification()
    for key in ('mode', 'question_utility', 'thresholds'):
        raw.pop(key)
    raw['additional_counts']=[dict(threshold=2,relation='>=',source_scale='recorded',count=11,n=20,unit='mg/L')]
    payload=dict(mode=mode,config=raw,targets=[dict(threshold=2,unit='mg/L')],options={})
    execute_job(payload,tmp_path/'job')
    status=json.loads((tmp_path/'job/job-status.json').read_text())
    assert status['status']=='completed', status
    report=(tmp_path/'job/output/report.html').read_text()
    assert '11' in report
    if mode=='batch':
        paths=list((tmp_path/'job').rglob('additional-counts.csv'))
        assert len(paths)==1
        assert 'source_scale' in paths[0].read_text() and 'recorded' in paths[0].read_text()


def test_variant_reordering_preserves_union_and_counts():
    from mic_50_90.analysis import _feasible_variants
    raw=specification()
    good=deepcopy(raw['summaries']);bad={**good,'minimum':'4'}
    bounds=[]
    for first,second in [(good,bad),(bad,good)]:
        candidate={**raw,'summaries':first,'reporting_envelope':{'variants':[{'id':'alternative','summaries':second}]}}
        problems,_,rejected=_feasible_variants(parse_spec(candidate))
        assert len(problems)==1 and len(rejected)==1
        problem=next(iter(problems.values()))
        bounds.append(tuple(x.count for x in problem.bounds(problem.panel.panel_tail(2))))
    assert bounds[0]==bounds[1]
