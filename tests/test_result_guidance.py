from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.result_view import distribution_overview


def specimen():
    return {'n':20,'unit':'mg/L','panel':{'levels':[1,2]},
        'source':'A publication <table>',
        'additional_counts':[{'threshold':1,'count':8,'n':20,'unit':'mg/L','source':'Table 1'}]}


def test_missing_count_guidance_uses_actual_cdf_range_and_denominator():
    r=analyse_distribution(specimen())
    g=r['interpretation']
    assert g['missing_count_information']
    assert g['suggested_count']['count_lower']==12
    assert g['suggested_count']['count_upper']==20
    assert g['suggested_count']['recorded_groups']==2
    assert not g['population_requested']
    assert 'same 20 isolates' in g['next_step']
    html=distribution_overview(r)
    assert 'What limits this answer?' in html
    assert 'Table 1' in html
    assert 'A publication &lt;table&gt;' in html


def test_fixed_sample_does_not_recommend_zero_gain_count():
    raw=specimen();raw['additional_counts'].append({'threshold':2,'count':2,'n':20,'unit':'mg/L'})
    r=analyse_distribution(raw)
    assert r['interpretation']['suggested_count'] is None
    assert not r['interpretation']['missing_count_information']


def test_numerical_limit_separate_from_sampling_uncertainty():
    raw=specimen();raw['iid']=True
    r=analyse_distribution(raw,population_method='joint-exact',population_time_limit=0)
    assert r['interpretation']['numerical_refinement_unfinished']
    html=distribution_overview(r)
    assert 'Sampling uncertainty' in html
    assert 'Numerical refinement' in html
    assert 'remain valid' in html


def test_failed_optional_refinement_does_not_claim_baseline_precision(monkeypatch):
    from mic_50_90 import distribution_workflow

    def failed_refinement(*args):
        raise RuntimeError('controlled optional calculation failure')

    raw = specimen()
    raw['iid'] = True
    baseline = analyse_distribution(raw)
    monkeypatch.setattr(distribution_workflow, '_joint_population', failed_refinement)
    result = analyse_distribution(raw, population_method='joint-exact')
    assert result['population']['status'] == 'baseline_retained'
    assert result['population']['cdf'] == baseline['population']['cdf']
    assert not result['population']['precision_reached']
    assert result['interpretation']['numerical_refinement_unfinished']
    assert 'Numerical refinement' in distribution_overview(result)


def test_suggested_count_preserves_disconnected_reporting_variants():
    raw = {'n': 20, 'unit': 'mg/L', 'panel': {'levels': [1, 2]},
           'summaries': {'minimum': '<=1', 'maximum': '<=1'},
           'reporting_envelope': {'variants': [{'id': 'other', 'summaries': {
               'minimum': '2', 'maximum': '2'}}]}}
    result = analyse_distribution(raw)
    guidance = result['interpretation']
    assert guidance['suggested_count']['count_components'] == [[0, 0], [20, 20]]
    assert 'currently 0 or 20' in guidance['next_step']
    assert 'currently 0–20' not in distribution_overview(result)


def test_report_explains_separate_baseline_and_refinement_times(tmp_path):
    from mic_50_90.distribution_report import render_distribution_html

    raw = specimen()
    raw['iid'] = True
    result = analyse_distribution(raw, population_method='joint-exact', population_time_limit=0)
    output = tmp_path / 'report.html'
    render_distribution_html({'software_version': '1.0.0', 'cohorts': [result]}, output)
    html = output.read_text(encoding='utf-8')
    assert 'Baseline calculation time:' in html
    assert 'Optional joint refinement time:' in html
    assert 'budget applies to optional refinement' in html
