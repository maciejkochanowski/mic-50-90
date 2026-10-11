"""Independent small-space and linear-program checks of range calibration."""
from fractions import Fraction
from math import factorial, prod

import numpy as np
import pytest
from scipy.optimize import linprog
from scipy.stats import beta

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICBin, MICPanel
from mic_50_90.joint_population import population_distribution
from mic_50_90.range_population import critical_score


def make_problem(n, k, histogram=None, constraints=()):
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in range(1, k+1)))
    rows = list(constraints)
    if histogram is not None:
        rows += [(np.eye(k)[j], h, h) for j, h in enumerate(histogram)]
    return EmpiricalProblem(n=n, panel=panel, quantiles=[], count_intervals=rows)


@pytest.mark.parametrize('method', ['bonferroni', 'range-calibrated'])
def test_largest_valid_confidence_retains_valid_outer_bounds(method):
    result = population_distribution({'a': make_problem(4, 4)}, method=method,
        confidence_level=np.nextafter(1., 0.), include_intervals=True,
        time_limit_seconds=0)
    for row in result['interval_bounds']:
        assert np.isfinite(row['lower']) and np.isfinite(row['upper'])
        assert 0 <= row['lower'] <= row['upper'] <= 1
        # With no information every proper range may contain zero or all isolates.
        if row['stop_index'] - row['start_index'] < 4:
            assert row['lower'] == 0 and row['upper'] == 1


def test_tiny_cutoff_zero_count_upper_seed_matches_closed_form():
    from mic_50_90.joint_population import _cp_start
    alpha = Fraction(1, 10**20)
    low, high = _cp_start(0, 4, alpha)
    assert low == 0
    assert high == pytest.approx(1 - float(alpha / 2)**.25, abs=2e-15)
    assert high < 1


def histograms(n, k):
    if k == 1:
        yield (n,)
    else:
        for first in range(n+1):
            for rest in histograms(n-first, k-1):
                yield (first, *rest)


@pytest.mark.parametrize('n,k', [(1, 2), (2, 3), (3, 5)])
@pytest.mark.parametrize('alpha', [Fraction(1, 20), Fraction(1, 2), Fraction(9, 10)])
def test_exact_small_multinomial_coverage(n, k, alpha):
    cutoff = critical_score(n, k, alpha)
    for weights in histograms(4, k):
        p = [Fraction(w, 4) for w in weights]
        rejected = Fraction(0)
        for h in histograms(n, k):
            bad = False
            for a in range(k):
                for b in range(a+1, k):
                    q, x = sum(p[a:b]), sum(h[a:b])
                    masses = [Fraction(factorial(n), factorial(s)*factorial(n-s))*q**s*(1-q)**(n-s) for s in range(n+1)]
                    score = min(Fraction(1), 2*sum(masses[:x+1]), 2*sum(masses[x:]))
                    bad |= score < cutoff
            if bad:
                rejected += Fraction(factorial(n), prod(factorial(x) for x in h))*prod(q**x for q, x in zip(p, h))
        assert rejected <= alpha


def independent_lp(histogram, cutoff, a, b):
    n, k = sum(histogram), len(histogram)
    matrix, rhs = [], []
    for left in range(k):
        for right in range(left+1, k):
            x = sum(histogram[left:right])
            low = 0 if x == 0 else beta.ppf(float(cutoff)/2, x, n-x+1)
            high = 1 if x == n else beta.ppf(1-float(cutoff)/2, x+1, n-x)
            row = np.array([int(left <= j < right) for j in range(k)])
            matrix.extend([row, -row]); rhs.extend([high, -low])
    objective = np.array([int(a <= j < b) for j in range(k)])
    options = dict(A_ub=matrix, b_ub=rhs, A_eq=[np.ones(k)], b_eq=[1], bounds=(0, 1), method='highs')
    lower = linprog(objective, **options)
    upper = linprog(-objective, **options)
    assert lower.success and upper.success
    return lower.fun, -upper.fun


@pytest.mark.parametrize('h', [(0, 1, 4), (1, 1, 1, 1, 1), (0, 1), (2, 0, 1)])
def test_full_histogram_all_projections_match_independent_lp(h):
    n, k = sum(h), len(h)
    result = population_distribution({'a': make_problem(n, k, h)}, method='range-calibrated', include_intervals=True, time_limit_seconds=0)
    cutoff = critical_score(n, k, 1-Fraction(.95))
    assert result['precision_reached']
    assert result['family_size'] == k*(k-1)//2
    for row in result['interval_bounds']:
        low, high = independent_lp(h, cutoff, row['start_index'], row['stop_index'])
        assert row['lower'] == pytest.approx(low, abs=3e-9)
        assert row['upper'] == pytest.approx(high, abs=3e-9)
        assert row['lower'] <= row['inner_lower'] <= row['inner_upper'] <= row['upper']


def test_incomplete_budget_zero_contains_all_compatible_full_regions():
    problem = make_problem(4, 3, constraints=[(np.array([0., 1., 0.]), 1, 2)])
    result = population_distribution({'a': problem}, method='range-calibrated', include_intervals=True, time_limit_seconds=0)
    for h in histograms(4, 3):
        if not 1 <= h[1] <= 2:
            continue
        full = population_distribution({'a': make_problem(4, 3, h)}, method='range-calibrated', include_intervals=True, time_limit_seconds=0)
        for row, inner in zip(result['interval_bounds'], full['interval_bounds']):
            assert row['lower'] <= inner['lower'] + 1e-15
            assert row['upper'] >= inner['upper'] - 1e-15


def test_complete_enumeration_matches_union_of_independent_lps():
    problem = make_problem(4, 3, constraints=[(np.array([0., 1., 0.]), 1, 2)])
    result = population_distribution({'a': problem}, method='range-calibrated', include_intervals=True, time_limit_seconds=10)
    assert result['precision_reached']
    cutoff = critical_score(4, 3, 1-Fraction(.95))
    for row in result['interval_bounds']:
        reference = [independent_lp(h, cutoff, row['start_index'], row['stop_index']) for h in histograms(4, 3) if 1 <= h[1] <= 2]
        assert row['lower'] == pytest.approx(min(v[0] for v in reference), abs=3e-9)
        assert row['upper'] == pytest.approx(max(v[1] for v in reference), abs=3e-9)


def test_control_with_thirteen_categories_and_zero_internal_count():
    row = np.eye(13)[6]
    result = population_distribution({'a': make_problem(20, 13, constraints=[(row, 0, 0)])}, method='range-calibrated', time_limit_seconds=0)
    assert result['category_bounds'][6][1] < .327
    assert result['method'] == 'range-calibrated'
    assert result['requested_method'] == 'range-calibrated'


def test_extreme_low_confidence_score_one_does_not_crash():
    result = population_distribution({'a': make_problem(1, 2, (0, 1))}, method='range-calibrated', confidence_level=.1)
    assert result['category_bounds'][0][1] == pytest.approx(.5, abs=1e-9)


def test_workflow_preserves_method_and_all_range_family():
    from mic_50_90.distribution_workflow import analyse_distribution
    raw = dict(cohort_id='counts', unit='mg/L', n=20, panel={'levels': [1, 2]}, iid=True,
               additional_counts=[dict(threshold=1, count=8, n=20, unit='mg/L', source='Table'), dict(threshold=2, count=2, n=20, unit='mg/L', source='Table')])
    result = analyse_distribution(raw, population_method='range-calibrated', population_precision_pp=50)
    pop = result['population']
    assert pop['method'] == 'range-calibrated'
    assert len(pop['fixed_family']) == pop['family_size'] == 3
    assert pop['precision_reached']
    assert result['population_resolution']['status'] != 'unavailable'


def test_update_retains_method_and_conservative_bounds():
    from mic_50_90.joint_population import update_population_distribution
    row = np.array([0., 1., 0.])
    old = {'a': make_problem(4, 3, constraints=[(row, 0, 2)])}
    new = {'a': make_problem(4, 3, constraints=[(row, 0, 2), (row, 1, 1)])}
    first = population_distribution(old, method='range-calibrated', include_intervals=True, time_limit_seconds=0)
    second = update_population_distribution(old, new, first, include_intervals=True, time_limit_seconds=0)
    for a, b in zip(first['interval_bounds'], second['interval_bounds']):
        assert a['lower'] <= b['lower'] <= b['upper'] <= a['upper']
    assert second['method'] == 'range-calibrated'


def test_cli_method_survives_configuration_and_html(tmp_path):
    import json
    from mic_50_90.cli import main
    raw = dict(cohort_id='counts', unit='mg/L', n=20, panel={'levels': [1, 2]}, iid=True,
               additional_counts=[dict(threshold=1, count=8, n=20, unit='mg/L', source='Table'), dict(threshold=2, count=2, n=20, unit='mg/L', source='Table')])
    source = tmp_path/'input.json'
    source.write_text(json.dumps(raw), encoding='utf-8')
    output = tmp_path/'output'
    assert main(['distribution', str(source), '--output-dir', str(output),
                 '--population-method', 'range-calibrated']) == 0
    result = json.loads((output/'results.json').read_text(encoding='utf-8'))
    assert result['cohorts'][0]['population']['method'] == 'range-calibrated'
    assert 'Simultaneous bounds for all MIC ranges' in (output/'report.html').read_text(encoding='utf-8')


def test_variants_are_unioned_and_impossible_counts_refused():
    a, b = make_problem(4, 3, (0, 2, 2)), make_problem(4, 3, (2, 2, 0))
    result = population_distribution({'a': a, 'b': b}, method='range-calibrated', include_intervals=True)
    singles = [population_distribution({'a': x}, method='range-calibrated', include_intervals=True) for x in (a, b)]
    for index, row in enumerate(result['interval_bounds']):
        assert row['lower'] == min(x['interval_bounds'][index]['lower'] for x in singles)
        assert row['upper'] == max(x['interval_bounds'][index]['upper'] for x in singles)
    with pytest.raises(ValueError):
        bad = make_problem(4, 3, constraints=[(np.eye(3)[0], 4, 4), (np.eye(3)[1], 2, 2)])
        population_distribution({'a': bad}, method='range-calibrated')


def test_desktop_worker_uses_selected_method(tmp_path):
    import json
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    payload = {'mode': 'distribution', 'config': dict(cohort_id='desktop-ranges', n=5,
        unit='mg/L', panel={'levels': [1, 2]}, iid=True,
        additional_counts=[dict(threshold=1, count=2, n=5, unit='mg/L', source='Table'),
                           dict(threshold=2, count=1, n=5, unit='mg/L', source='Table')]),
        'options': {'population_method': 'range-calibrated', 'population_time_limit': 0}}
    assert validate_payload(payload)['valid']
    execute_job(payload, tmp_path)
    result = json.loads((tmp_path/'output/results.json').read_text(encoding='utf-8'))['cohorts'][0]
    assert result['population']['method'] == 'range-calibrated'
    assert result['population']['precision_reached']
    from pathlib import Path
    import mic_50_90
    html = (Path(mic_50_90.__file__).parent/'gui_assets/index.html').read_text(encoding='utf-8')
    assert '<option value="range-calibrated">' in html


def test_planning_accepts_the_same_fixed_method():
    from mic_50_90.population_acquisition import plan_population_precision
    result = plan_population_precision({'a': make_problem(5, 3, (3, 1, 1))}, method='range-calibrated',
        precision_pp=100, time_limit_seconds=3)
    assert result['method'] == 'range-calibrated'
    assert result['cost_upper'] == '0'


@pytest.mark.parametrize('options', [{'population_time_limit': float('nan')}, {'population_tolerance_pp': float('inf')}])
def test_invalid_optional_range_refinement_keeps_safe_same_method_baseline(options):
    from mic_50_90.distribution_workflow import analyse_distribution
    raw = dict(n=3, unit='mg/L', iid=True, panel={'levels': [1, 2]},
               additional_counts=[dict(threshold=1, count=1, n=3, unit='mg/L', source='Table')])
    result = analyse_distribution(raw, population_method='range-calibrated', **options)
    assert result['sample']['status'] == 'complete'
    assert result['population']['method'] == 'range-calibrated'
    assert result['population']['status'] == 'baseline_retained'
    assert 'settings' in result['population']['reason']
