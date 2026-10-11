"""Reproduced mismatches between exact results and their displayed interpretation."""
import json
import re

import pytest

from mic_50_90 import analyse_spec
from mic_50_90.decisions import decision_results, parse_criterion
from mic_50_90.decision_report import render_acquisition_plan
from mic_50_90.report import result_sections, _interval_chart
from mic_50_90.reporting_report import render_reporting_plan
from mic_50_90.workflows import _flatten


def separated_sample():
    def summary(category):
        return dict(quantiles=[dict(probability=.5, category=category),
                               dict(probability=.9, category=category)],
                    minimum=category, maximum=category)
    return analyse_spec(dict(contract_version='1.0', mode='population', n=10,
        panel=dict(levels=[1, 2], left_censored=False, right_censored=False),
        summaries=summary('1'), thresholds=[1],
        reporting_envelope=dict(variants=[dict(id='alternative', summaries=summary('2'))]),
        population=dict(profile_likelihood_enabled=False, bayes_enabled=False)))


@pytest.mark.parametrize('renderer', ['questions', 'acquisition', 'reporting'])
@pytest.mark.parametrize('fraction,percent', [
    ('0.1000000000000000001', '10.00000000000000001%'),
    ('0.05', '5%'), ('1/3', '100/3%'), ('1e-8', '0.000001%'),
])
def test_display_keeps_the_exact_criterion(renderer, fraction, percent):
    criterion = dict(parse_criterion(dict(decision_operator='<', decision_fraction=fraction)),
                     threshold=1, unit='mg/L', initial_status='supported')
    if renderer == 'questions':
        result = separated_sample()
        result['decision_results'] = decision_results(result, [criterion])
        text = result_sections(result)
    elif renderer == 'acquisition':
        text = render_acquisition_plan(dict(sample_size=10, criteria=[criterion],
                                            status='already_resolved', round_cost_exact='1'))
    else:
        row = dict(criterion, status='supported')
        text = render_reporting_plan(dict(sufficient=True, optimality_verified=True,
            disclosures=[], report_cost='0', initial_decisions=['supported'],
            verification=dict(bounds=[row])))
    assert '&lt; ' + percent in text


def test_disconnected_sample_components_are_visible_without_diagnostics():
    result = separated_sample()
    text = result_sections(result).split('<details>')[0]
    assert '0/10 union 10/10' in text
    assert '0/10 to 10/10' not in text
    # The sample row has two singletons. No SVG segment should connect 0 to 100%.
    chart = _interval_chart(result)
    assert not re.search(r'<line x1="280(?:\.0)?" x2="720(?:\.0)?"[^>]*stroke="#26776B"', chart)
    labels = re.findall(r'<text x="740"[^>]*>(.*?)</text>', chart)
    assert len(labels) == 5  # two sample, two population, one unavailable layer
    assert all(len(label) <= 25 for label in labels)


def test_csv_preserves_components_as_well_as_extreme_bounds():
    result = separated_sample()
    row = _flatten([dict(cohort_id='C', panel_id='P', status='ok', result=result)])[0]
    assert json.loads(row['sample_count_components']) == [[0, 0], [10, 10]]
    assert len(json.loads(row['population_confidence_components'])) == 2
    assert row['sample_lower_count'] == 0 and row['sample_upper_count'] == 10


def test_updated_report_components_follow_the_retained_variants():
    from mic_50_90 import analyse_with_counts
    raw = dict(contract_version='1.0', mode='empirical', n=10,
        panel=dict(levels=[1, 2, 4], left_censored=False, right_censored=False),
        summaries=dict(quantiles=[dict(probability=.5, category='1'),
                                  dict(probability=.9, category='4')]), thresholds=[1])
    result = analyse_with_counts(raw, [dict(threshold=1, unit='mg/L', count=3, n=10)])
    row = _flatten([dict(cohort_id='C', panel_id='P', status='ok', result=result)])[0]
    assert json.loads(row['sample_count_components']) == [[3, 3]]


def test_csv_assumed_radius_does_not_gain_a_calibration_level():
    from pathlib import Path
    raw = json.loads(Path('examples/empirical.json').read_text())
    raw.update(reference_distribution=[1/11]*11, wasserstein_radius=8)
    row = _flatten([dict(cohort_id='C', panel_id='P', status='ok', result=analyse_spec(raw))])[0]
    assert row['conformal_guarantee_class'] == 'assumption_scenario'
    assert row['conformal_confidence_level'] is None


def test_fractional_profile_grid_is_not_silently_truncated(monkeypatch):
    from pathlib import Path
    from mic_50_90.population import PopulationMLE
    import mic_50_90.analysis as analysis
    raw = json.loads(Path('examples/population.json').read_text())
    raw['population'].update(profile_grid_size=11.9, profile_likelihood_enabled=True,
                             bayes_enabled=False)
    fit = PopulationMLE(tuple([1/11]*11), -10.0, True, 'controlled fit', 1)
    monkeypatch.setattr(analysis, 'fit_population_mle', lambda **kwargs: fit)
    result = analyse_spec(raw)
    for row in result['threshold_results']:
        optional = row['optional_efficiency_analysis']
        assert not optional['available']
        assert 'grid_size' in optional['reason']
        assert row['exact_count_confidence']['marginal']['confidence_set_components']
