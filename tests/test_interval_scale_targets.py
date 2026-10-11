from copy import deepcopy

import pytest

from mic_50_90.distribution_workflow import analyse_distribution


def censored_input():
    return dict(cohort_id='tail', n=50, unit='mg/L', iid=False,
        panel={'levels': [16, 32]}, additional_counts=[
            dict(threshold=16, count=8, n=50, unit='mg/L'),
            dict(threshold=32, count=8, n=50, unit='mg/L')],
        targets=[dict(threshold=64, unit='mg/L', target_scale='interval',
            decision_operator='<', decision_fraction='.1')])


def test_full_recorded_histogram_does_not_resolve_within_tail():
    result = analyse_distribution(censored_input())
    answer = result['decisions'][0]
    assert answer['sample']['count_components'] == [[0, 8]]
    assert answer['sample']['status'] == 'undetermined'
    assert answer['measurement_ambiguous_categories'] == ['>32']
    assert result['interpretation']['measurement_limitation']
    assert 'measurement' in result['interpretation']['next_step'].lower()


def test_boundary_and_legacy_recorded_meaning_are_distinct():
    raw = censored_input()
    raw['targets'] += [dict(raw['targets'][0], target_scale='recorded'),
                      dict(raw['targets'][0], threshold=32)]
    rows = analyse_distribution(raw)['decisions']
    assert [r['sample']['count_components'] for r in rows] == [[[0, 8]], [[0, 0]], [[8, 8]]]
    del raw['targets'][1]['target_scale']
    assert analyse_distribution(raw)['decisions'][1]['sample']['count_components'] == [[0, 0]]


def test_population_is_projected_from_same_region():
    raw = censored_input()
    raw['iid'] = True
    raw['confidence_level'] = .95
    raw['targets'].append(dict(raw['targets'][0], threshold=32))
    rows = analyse_distribution(raw, population_method='range-calibrated')['decisions']
    assert rows[0]['population']['lower'] == 0
    assert rows[0]['population']['upper'] == rows[1]['population']['upper']
    assert rows[0]['population']['confidence_level'] == .95


def test_invalid_scale_is_not_silently_recorded():
    raw = censored_input()
    raw['targets'][0]['target_scale'] = 'unknown'
    with pytest.raises(ValueError, match='target_scale'):
        analyse_distribution(raw)


def test_unknown_rounding_retains_other_information_and_source():
    raw = censored_input()
    row = dict(threshold=32, percentage='16', n=50, unit='mg/L', source='Table A')
    raw['additional_counts'].append(row)
    result = analyse_distribution(raw)
    assert result['decisions'][0]['sample']['count_components'] == [[0, 8]]
    assert result['input_information_issues'][0]['original'] == row
    assert 'rounding_rule' in result['input_information_issues'][0]['missing_fields']
    only = deepcopy(raw)
    only['additional_counts'] = [row]
    with pytest.raises(ValueError, match='Supply MIC summaries'):
        analyse_distribution(only)


def test_contradictory_counts_are_not_discarded():
    raw = censored_input()
    raw['additional_counts'].append(dict(threshold=32, count_min=9, count_max=10, n=50, unit='mg/L'))
    with pytest.raises(ValueError, match='incompatible'):
        analyse_distribution(raw)


def test_form_missing_rounding_metadata_keeps_sample(tmp_path):
    from mic_50_90.gui_forms import validate_payload, canonical_distribution_input
    raw=censored_input()
    raw['additional_counts'].append(dict(threshold=32,percentage='16',decimal_places=None,
        rounding_rule='',n=50,unit='mg/L'))
    payload=dict(mode='distribution',config=raw)
    checked=validate_payload(payload)
    assert checked['valid'] and checked['warnings']
    result=analyse_distribution(canonical_distribution_input(raw))
    assert result['input_information_issues']


def test_saved_interval_question_update_and_csv(tmp_path):
    import json
    from mic_50_90.cli import main
    raw=censored_input();source=tmp_path/'in.json'
    source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--output-dir',str(tmp_path/'a')])==0
    csv=(tmp_path/'a/decisions.csv').read_text(encoding='utf-8')
    assert 'target_scale' in csv and 'interval' in csv
    raw['additional_counts'].append(dict(threshold=32,count_min=8,count_max=8,n=50,unit='mg/L'))
    source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--previous-output',str(tmp_path/'a'),'--output-dir',str(tmp_path/'b')])==0
    answer=json.loads((tmp_path/'b/results.json').read_text())['cohorts'][0]
    assert answer['decisions'][0]['sample']['count_components']==[[0,8]]


def test_explanation_skips_deferred_count_rows():
    raw=censored_input()
    raw['summaries']={'minimum':'<=16'}
    raw['explain_counts']=True
    raw['additional_counts'].insert(0,dict(threshold=32,percentage='16',n=50,unit='mg/L'))
    result=analyse_distribution(raw)
    explanation=result['count_explanation']
    assert explanation['status']=='complete'
    assert len(explanation['stages'])==2
    assert explanation['stages'][0]['source_row']==2
    assert explanation['stages'][0]['count_rows']==1
    assert len(result['input_information_issues'])==1


def test_saved_update_comparison_counts_usable_rows(tmp_path):
    import json
    from mic_50_90.cli import main
    raw=censored_input()
    raw['additional_counts']=[raw['additional_counts'][1],
        dict(threshold=32,percentage='16',n=50,unit='mg/L')]
    source=tmp_path/'input.json';source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--output-dir',str(tmp_path/'a')])==0
    raw['additional_counts'].append(dict(threshold=16,count=8,n=50,unit='mg/L'))
    source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--previous-output',str(tmp_path/'a'),'--output-dir',str(tmp_path/'b')])==0
    result=json.loads((tmp_path/'b/results.json').read_text())['cohorts'][0]
    assert len(result['sample_comparison']['added_counts'])==1
    assert result['sample_comparison']['added_counts'][0]['threshold']==16


def test_interval_question_without_criterion_has_bounds_and_report(tmp_path):
    import json
    from mic_50_90.cli import main
    raw=censored_input();raw['iid']=True
    raw['targets']=[dict(threshold=64,unit='mg/L',target_scale='interval')]
    source=tmp_path/'input.json';source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--population-method','range-calibrated',
        '--output-dir',str(tmp_path/'result')])==0
    result=json.loads((tmp_path/'result/results.json').read_text())['cohorts'][0]
    answer=result['decisions'][0]
    assert answer['sample']['status']=='available'
    assert answer['sample']['count_components']==[[0,8]]
    assert answer['population']['lower']==0 and answer['population']['upper']>0
    assert result['interpretation']['measurement_limitation']
    html=(tmp_path/'result/report.html').read_text(encoding='utf-8')
    assert 'MIC within the measurement intervals above 64' in html
    assert '0–8' in html
    assert 'Results describe recorded MIC above' not in html
    assert result['provenance']['threshold_context'][0]['target_scale']=='interval'
