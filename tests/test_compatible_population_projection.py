"""Independent controls for compatible-prefix population projections.

The oracle enumerates empirical histograms and solves the population problem
with general linear programming. It does not use the production difference
closure, pair domains or endpoint projection formulas.
"""
from fractions import Fraction
from itertools import combinations_with_replacement

import numpy as np
import pytest
from scipy.optimize import linprog
from scipy.stats import beta

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.joint_population import population_distribution, update_population_distribution
from mic_50_90.model import MICBin, MICPanel


def panel(k):
    return MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in range(1, k+1)))


def problem(n, k, rows, *, geometry=None):
    counts = [(np.r_[np.zeros(a), np.ones(b-a), np.zeros(k-b)], lo, hi)
              for a, b, lo, hi in rows]
    return EmpiricalProblem(n=n, panel=geometry or panel(k), quantiles=[], count_intervals=counts)


def oracle(problems, confidence=.95):
    """Enumerate h, optimize each ordered population box by independent LP."""
    obj = next(iter(problems.values()))
    n, k = obj.n, obj.k
    tail = (1-confidence)/(2*(k-1))
    projections = [(a, b) for a in range(k) for b in range(a+1, k+1)]
    lo, hi = np.ones(len(projections)), np.zeros(len(projections))
    order = np.zeros((k-2, k-1))
    for j in range(k-2):
        order[j, j:j+2] = (1, -1)
    feasible = 0
    for categories in combinations_with_replacement(range(k), n):
        h = np.bincount(categories, minlength=k)
        if not any(np.all(p.linear_constraints[0] @ h >= p.linear_constraints[1])
                   and np.all(p.linear_constraints[0] @ h <= p.linear_constraints[2])
                   for p in problems.values()):
            continue
        feasible += 1
        s = np.cumsum(h)[:-1]
        bounds = [(0 if x == 0 else beta.ppf(tail, x, n-x+1),
                   1 if x == n else beta.isf(tail, x+1, n-x)) for x in s]
        for index, (a, b) in enumerate(projections):
            objective = np.zeros(k-1)
            if a:
                objective[a-1] -= 1
            if b < k:
                objective[b-1] += 1
            offset = float(b == k)
            lower = linprog(objective, A_ub=order if k > 2 else None,
                            b_ub=np.zeros(k-2) if k > 2 else None,
                            bounds=bounds, method='highs')
            upper = linprog(-objective, A_ub=order if k > 2 else None,
                            b_ub=np.zeros(k-2) if k > 2 else None,
                            bounds=bounds, method='highs')
            assert lower.success and upper.success
            lo[index] = min(lo[index], offset+lower.fun)
            hi[index] = max(hi[index], offset-upper.fun)
    assert feasible
    return np.column_stack((lo, hi)), feasible


@pytest.mark.parametrize('n,k,rows,target,expected', [
    (50, 5, [(0,1,10,20), (1,2,1,1), (0,3,35,40), (0,4,45,49)], (1,2), .37180860249702),
    (100, 8, [(0,3,30,60), (3,4,1,1), (0,6,80,89), (0,7,90,99)], (3,4), .28250767176954),
    (20, 5, [(0,1,5,9), (1,2,0,0), (0,3,15,17), (0,4,18,20)], (1,2), .54911729820937),
])
def test_range_projection_cannot_mix_incompatible_prefix_counts(n, k, rows, target, expected):
    result = population_distribution({'a': problem(n, k, rows)}, include_intervals=True)
    row = next(r for r in result['interval_bounds'] if (r['start_index'], r['stop_index']) == target)
    assert row['upper'] == pytest.approx(expected, abs=1e-10)
    assert result['category_bounds'][target[0]][1] == row['upper']
    assert row['lower'] <= row['inner_lower'] <= row['inner_upper'] <= row['upper']
    assert row['upper']-row['inner_upper'] < 1e-9


@pytest.mark.parametrize('n,k,rows', [
    (6, 5, [(0,1,1,3), (1,3,1,1), (0,4,4,5)]),
    (6, 5, [(0,2,1,3), (2,3,0,0), (1,4,2,3)]),
    (2, 4, [(0,1,0,1), (1,3,0,0)]),
    (1, 2, [(0,1,1,1)]),
])
def test_all_projections_match_enumerated_histogram_population_lp(n, k, rows):
    problems = {'a': problem(n, k, rows)}
    expected, _ = oracle(problems)
    result = population_distribution(problems, include_intervals=True)
    actual = np.array([[r['lower'], r['upper']] for r in result['interval_bounds']])
    np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=0)
    for r, (lo, hi) in zip(result['interval_bounds'], expected):
        assert r['lower'] <= lo+1e-14
        assert r['upper'] >= hi-1e-14
        assert lo-1e-14 <= r['inner_lower'] <= lo+1e-10
        assert hi-1e-10 <= r['inner_upper'] <= hi+1e-14


def test_reporting_variants_are_united_before_projection_not_crossed():
    variants = {'low': problem(6, 4, [(0,1,0,0), (0,2,1,1)]),
                'high': problem(6, 4, [(0,1,5,5), (0,2,6,6)])}
    expected, _ = oracle(variants)
    result = population_distribution(variants, include_intervals=True)
    actual = np.array([[r['lower'], r['upper']] for r in result['interval_bounds']])
    np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=0)
    assert result['category_bounds'][1][1] < 1


def test_censored_panel_uses_the_same_recorded_category_projection():
    censored = MICPanel.from_dict({'levels': [1,2,4]})
    rows = [(0,1,1,2), (1,3,1,1)]
    result = population_distribution({'p': problem(4,4,rows,geometry=censored)}, include_intervals=True)
    expected, _ = oracle({'p': problem(4,4,rows)})
    np.testing.assert_allclose([[r['lower'],r['upper']] for r in result['interval_bounds']],
                               expected, atol=1e-10, rtol=0)


def test_zero_refinement_budget_keeps_compatible_bounds_without_joint_witnesses():
    problems = {'p': problem(20,5,[(0,1,5,9),(1,2,0,0),(0,3,15,17),(0,4,18,20)])}
    result = population_distribution(problems, method='joint-exact',
                                     time_limit_seconds=0, include_intervals=True)
    assert result['status'] == 'time_limit'
    assert not result['precision_reached']
    assert result['category_bounds'][1][1] == pytest.approx(.54911729820937, abs=1e-10)
    assert all(r['inner_lower'] is None for r in result['interval_bounds'])


def test_truthful_count_update_retains_compatible_projection_and_refreshes_witnesses():
    old = {'p': problem(6,4,[(0,1,1,3)])}
    previous = population_distribution(old, include_intervals=True)
    new = {'p': old['p'].with_count_interval([0,1,0,0], 0, 0)}
    updated = update_population_distribution(old,new,previous,include_intervals=True)
    expected, _ = oracle(new)
    actual = np.array([[r['lower'],r['upper']] for r in updated['interval_bounds']])
    np.testing.assert_allclose(actual,expected,atol=1e-10,rtol=0)
    for fresh, saved in zip(updated['interval_bounds'],previous['interval_bounds']):
        assert fresh['lower'] >= saved['lower'] and fresh['upper'] <= saved['upper']
        assert fresh['lower'] <= fresh['inner_lower'] <= fresh['inner_upper'] <= fresh['upper']
    assert updated['previous_outer_bounds_preserved']


def test_fraction_alpha_and_subtraction_enclose_known_rational_endpoints():
    from mic_50_90.joint_population import _compatible_prefix_projections
    from mic_50_90.utility import _prefix_distances
    obj = problem(1,2,[(0,1,1,1)])
    lo, hi, inner_lo, inner_hi = _compatible_prefix_projections(
        [_prefix_distances(obj)],1,2,Fraction(1,3),[(0,1),(1,2),(0,2)],witnesses=True)
    # n=1, s=1: CP is exactly [alpha/2, 1]. The complementary
    # category is [0, 1-alpha/2]. These fractions are not binary64 exact.
    for j, (a,b) in enumerate([(Fraction(1,6),Fraction(1)),
                               (Fraction(0),Fraction(5,6)),(Fraction(1),Fraction(1))]):
        assert Fraction(float(lo[j])) <= a <= Fraction(float(inner_lo[j]))
        assert Fraction(float(inner_hi[j])) <= b <= Fraction(float(hi[j]))


def test_precision_beyond_certified_endpoint_brackets_is_not_claimed():
    result = population_distribution({'p':problem(1,2,[(0,1,1,1)])},
        confidence_level=.5,include_intervals=True,tolerance_pp=1e-12)
    assert result['status'] == 'precision_unresolved'
    assert not result['precision_reached']
    assert result['endpoint_gap_pp'] > result['numerical_tolerance_pp']
    assert result['cdf_bounds'][0][0] <= .25


def test_prefix_only_constraints_can_attain_the_previous_marginal_projection():
    obj = problem(6,4,[(0,1,1,2),(0,2,3,4),(0,3,5,6)])
    result = population_distribution({'p':obj},include_intervals=True)
    expected, _ = oracle({'p':obj})
    np.testing.assert_allclose([[r['lower'],r['upper']] for r in result['interval_bounds']],
                               expected,atol=1e-10,rtol=0)
