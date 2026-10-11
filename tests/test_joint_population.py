from fractions import Fraction
from itertools import product

import numpy as np
import pytest
from scipy.stats import binom, multinomial

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICBin, MICPanel
from mic_50_90.joint_population import (
    joint_minp_probability, max_compatible_statistic, joint_report_pvalue,
    rectangle_probability_bounds, population_distribution, box_pvalue_upper,
    update_population_distribution,
)


def problem(n=5):
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in (1, 2, 3)))
    return EmpiricalProblem(n=n, panel=panel, quantiles=[], count_intervals=[(np.array([1., 1., 0.]), 2, 4)])


def histograms(n):
    return np.array([(a, b, n-a-b) for a in range(n+1) for b in range(n-a+1)])


def test_joint_probability_matches_independent_enumeration():
    h = histograms(5)
    for p in ([.1, .3, .6], [0, .5, .5], [1, 0, 0]):
        f = np.cumsum(p)[:-1]
        s = np.cumsum(h, axis=1)[:, :-1]
        scores = np.minimum(1, 2*np.minimum(binom.cdf(s, 5, f), binom.sf(s-1, 5, f))).min(axis=1)
        for t in (.001, .025, .1, .5, 1):
            expected = multinomial.pmf(h, 5, p)[scores <= t+1e-14].sum()
            assert joint_minp_probability(5, f, t) == pytest.approx(expected, abs=2e-12)


def test_compatible_statistic_retains_interval_constraint():
    obj = problem()
    h = histograms(obj.n)
    h = h[(h[:, :2].sum(axis=1) >= 2) & (h[:, :2].sum(axis=1) <= 4)]
    f = np.array([.2, .7])
    s = np.cumsum(h, axis=1)[:, :-1]
    expected = np.minimum(1, 2*np.minimum(binom.cdf(s, obj.n, f), binom.sf(s-1, obj.n, f))).min(axis=1).max()
    assert max_compatible_statistic({'a': obj}, f) == pytest.approx(expected)
    assert .05 <= joint_report_pvalue({'a': obj}, [.2, .5, .3]) <= 1


def test_directed_rectangle_encloses_exact_rational_probability():
    n = 5
    exact = Fraction(0)
    from math import factorial
    for h in histograms(n):
        if 1 <= h[0] <= 3 and 2 <= h[0]+h[1] <= 4:
            c = factorial(n)
            for x in h:
                c //= factorial(int(x))
            # Calculate coefficient without intermediate integer truncation.
            c = factorial(n) // product_factorials(h)
            exact += c * Fraction(1, 4)**int(h[0]) * Fraction(1, 2)**int(h[1]) * Fraction(1, 4)**int(h[2])
    lo, hi = rectangle_probability_bounds(n, [.25, .75], [1, 2], [3, 4])
    assert Fraction.from_float(lo) <= exact <= Fraction.from_float(hi)
    assert hi-lo < 1e-12


def product_factorials(h):
    from math import factorial, prod
    return prod(factorial(int(x)) for x in h)


def test_whole_box_bound_dominates_every_checked_point():
    problems = {'a': problem()}
    lower, upper = [.15, .65], [.2, .72]
    bound = box_pvalue_upper(problems, lower, upper)
    for x, y in product(np.linspace(lower[0], upper[0], 4), np.linspace(lower[1], upper[1], 4)):
        assert joint_report_pvalue(problems, [x, y-x, 1-y]) <= bound+2e-12


def test_timeout_preserves_full_baseline_and_exposes_status():
    result = population_distribution({'a': problem()}, method='joint-exact', time_limit_seconds=0)
    assert result['status'] == 'time_limit'
    assert not result['precision_reached']
    assert result['cdf_bounds'] == result['baseline_cdf_bounds']
    assert result['category_bounds'] == result['baseline_category_bounds']
    assert result['bounds_kind'] == 'conservative_outer'


def test_bonferroni_output_and_invalid_parameters():
    result = population_distribution({'a': problem()})
    assert result['method'] == 'bonferroni'
    assert len(result['cdf_bounds']) == 2
    assert len(result['category_bounds']) == 3
    assert result['family_size'] == 2
    for kwargs in ({'method': 'wilks'}, {'confidence_level': 1}, {'tolerance_pp': -1}, {'time_limit_seconds': float('nan')}):
        with pytest.raises(ValueError):
            population_distribution({'a': problem()}, **kwargs)


def test_numerical_update_cannot_widen_saved_bounds():
    old = {'a': problem()}
    previous = population_distribution(old, method='joint-exact', time_limit_seconds=.2, tolerance_pp=1)
    new = {'a': old['a'].with_equality(np.array([1., 0., 0.]), 1)}
    updated = update_population_distribution(old, new, previous, time_limit_seconds=0)
    for key in ('cdf_bounds', 'category_bounds'):
        assert np.all(np.asarray(updated[key])[:, 0] >= np.asarray(previous[key])[:, 0])
        assert np.all(np.asarray(updated[key])[:, 1] <= np.asarray(previous[key])[:, 1])
    assert updated['previous_outer_bounds_preserved']
    with pytest.raises(ValueError, match='retain'):
        update_population_distribution(new, old, population_distribution(new), time_limit_seconds=0)
