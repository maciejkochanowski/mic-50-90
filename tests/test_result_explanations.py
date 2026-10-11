"""A reader must distinguish observed groups, missing counts and inference."""
from copy import deepcopy
from pathlib import Path
import json

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.distribution_report import render_distribution_html
from mic_50_90.gui_forms import desktop_examples


def published():
    root = Path(__file__).resolve().parents[1]
    raw = json.loads((root / 'examples/distribution/published-7133-counts.json').read_text())
    raw['explain_counts'] = True
    raw['targets'] = [{'threshold': 2, 'unit': 'mg/L', 'decision_operator': '<', 'decision_fraction': '0.05'}]
    return raw


def html_for(raw, tmp_path):
    result = analyse_distribution(raw)
    output = tmp_path / 'report.html'
    render_distribution_html({'software_version': '1.0.0', 'cohorts': [result]}, output)
    return result, output.read_text(encoding='utf-8')


def test_publication_opens_with_category_answer_not_cumulative_plot(tmp_path):
    _, text = html_for(published(), tmp_path)
    assert 'class="result-overview"' in text
    assert text.index('All 3 MIC group counts are determined') < text.index('Cumulative share')
    assert '5407' in text and '1583' in text and '143' in text
    assert 'data-chart="category"' in text
    assert 'Print / save as PDF' in text and 'Save PNG' in text


def test_count_story_uses_existing_engine_with_each_available_source_count():
    result = analyse_distribution(published())
    assert result.get('count_explanation', {}).get('status') == 'complete'
    stages = result['count_explanation']['stages']
    assert len(stages) == 2
    assert [(r['count_lower'], r['count_upper']) for r in stages[0]['sample']['categories']] == [(5407, 5407), (0, 1726), (0, 1726)]
    assert stages[0]['decisions'][0]['sample']['status'] == 'undetermined'
    assert stages[1]['decisions'][0]['sample']['status'] == 'supported'
    assert [(r['count_lower'], r['count_upper']) for r in stages[1]['sample']['categories']] == [(5407, 5407), (1583, 1583), (143, 143)]


def test_unrequested_layer_is_not_displayed_as_failed_calculation(tmp_path):
    _, text = html_for(published(), tmp_path)
    assert 'data-layer-status="not_requested"' in text
    raw = published()
    raw['wasserstein_calibration_manifest'] = {'invalid': 'test'}
    _, text = html_for(raw, tmp_path)
    assert 'data-layer-status="unavailable"' in text


def test_saved_update_compares_sample_bounds_recomputed_from_original_input():
    raw = published()
    old = deepcopy(raw)
    old['additional_counts'] = old['additional_counts'][:1]
    previous = {'input': old, 'result': analyse_distribution(old), 'population_method': 'bonferroni'}
    result = analyse_distribution(raw, previous_analysis=previous)
    assert result.get('sample_comparison', {}).get('status') == 'complete'
    assert result['sample_comparison']['before']['categories'][2]['count_upper'] == 1726
    assert result['sample_comparison']['added_counts'][0]['count'] == 143


def test_real_laboratory_example_is_available_without_removing_controlled_cases():
    examples = {row['id']: row['payload'] for row in desktop_examples()}
    assert {'published7133', 'laboratory276', 'counts20', 'summary20'} <= examples.keys()
    example = examples['laboratory276']
    assert example['config']['n'] == 276
    assert sum(row['count'] for row in example['histogram']) == 276
    assert len(example['targets']) == 4


def test_chart_preserves_disconnected_components_and_escapes_source_labels():
    import xml.etree.ElementTree as ET
    from mic_50_90.result_view import count_chart, category_label
    svg = ET.fromstring(count_chart([dict(label='<script>alert(1)</script>',
        count_lower=1, count_upper=9, count_components=[[1, 2], [8, 9]])], 10))
    assert [(r.get('data-count-lower'), r.get('data-count-upper')) for r in svg.iter()
            if r.get('data-count-lower')] == [('1', '2'), ('8', '9')]
    assert all(not r.tag.endswith('script') for r in svg.iter())
    assert category_label('(0.06,2]') == '>0.06 to 2'


def test_contradictory_counts_are_not_explained_as_success():
    import pytest
    raw = published()
    raw['additional_counts'][1]['count'] = 1727
    with pytest.raises(ValueError):
        analyse_distribution(raw)


def test_verification_does_not_fill_gaps_between_reporting_variants():
    from mic_50_90 import verify_reporting
    from mic_50_90.result_view import verification_overview
    def summaries(category):
        return {'minimum':category, 'quantiles':[{'probability':.5,'category':category,'rank':2}, {'probability':.9,'category':category,'rank':3}]}
    spec={'mode':'empirical','n':3,'unit':'mg/L','panel':{'levels':[1,2,4], 'left_censored':False,'right_censored':False},
          'summaries':summaries('1'),'reporting_envelope':{'variants':[{'id':'alternative','summaries':summaries('4')}]},'thresholds':[2]}
    checked=verify_reporting(spec,[{'threshold':2,'unit':'mg/L','decision_operator':'<=','decision_fraction':1}],[])
    assert checked['bounds'][0]['count_components']==[[0,0],[3,3]]
    html=verification_overview(checked,[])
    assert 'data-count-lower="0" data-count-upper="3"' not in html
    assert '0 or 3' in html
    assert 'Count / 3' in html


def test_verification_accepts_source_percentage_and_string_threshold():
    from mic_50_90 import verify_reporting
    from mic_50_90.result_view import verification_overview
    spec={'mode':'empirical','n':20,'unit':'mg/L','panel':{'levels':[1,2]},'thresholds':[2],
          'summaries':{'quantiles':[{'probability':q,'category':'<=1','convention':'ceiling'} for q in (.5,.9)]}}
    criteria=[{'threshold':2,'unit':'mg/L','decision_operator':'<=','decision_fraction':'.05'}]
    for amount, expected in [({'count':1},'1 results'),({'percentage':'5','decimal_places':0,'rounding_rule':'half_up'},'5%')]:
        disclosures=[{'threshold':'2','n':20,'unit':'mg/L',**amount}]
        html=verification_overview(verify_reporting(spec,criteria,disclosures),disclosures)
        assert expected in html and 'None' not in html


def test_threshold_overview_uses_engine_decision_and_preserves_optional_failure():
    from mic_50_90 import analyse_spec
    from mic_50_90.result_view import threshold_overview
    result=analyse_spec({'mode':'empirical','n':20,'unit':'mg/L','panel':{'levels':[1,2]},'thresholds':[2],
        'summaries':{'quantiles':[{'probability':q,'category':'<=1','convention':'ceiling'} for q in (.5,.9)]}})
    result['decision_results']=[{'threshold':2,'decision_operator':'<','decision_fraction_text':'0.05',
                                'sample':{'status':'undetermined'}}]
    result['population_unavailable_reason']='Population analysis failed: test failure'
    result['inference_requested']['population']=True
    text=threshold_overview(result,{'source_location':'source table'})
    assert 'Not enough information: Fewer than 5%' in text
    assert 'data-layer-status="unavailable"' in text and 'test failure' in text
    assert 'Source: source table' in text
