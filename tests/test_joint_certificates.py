"""Independent rational checks of the joint population certificates."""

from fractions import Fraction
from itertools import product
from math import comb, factorial, prod

import numpy as np
import pytest

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICBin, MICPanel
from mic_50_90 import joint_population as joint
from mic_50_90.utility import _prefix_distances


def compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for a in range(n + 1):
            for rest in compositions(n - a, k - 1):
                yield (a, *rest)


def probability(h, probabilities):
    coefficient = factorial(sum(h)) // prod(factorial(x) for x in h)
    return coefficient * prod(p**x for p, x in zip(probabilities, h))


def rational_tails(n, q):
    masses = [comb(n, x) * q**x * (1 - q)**(n - x) for x in range(n + 1)]
    return [sum(masses[:x + 1]) for x in range(n + 1)], [sum(masses[x:]) for x in range(n + 1)]


def rational_report_pvalue(problem, cdf):
    n = problem.n
    f = [Fraction.from_float(float(x)) for x in cdf]
    probabilities = [f[0], *(b - a for a, b in zip(f, f[1:])), 1 - f[-1]]
    all_histograms = list(compositions(n, problem.k))
    tails = [rational_tails(n, q) for q in f]
    scores = []
    compatible = []
    matrix, lower, upper = problem.linear_constraints
    for h in all_histograms:
        counts = np.cumsum(h)[:-1]
        scores.append(min(min(Fraction(1), 2 * min(c[x], s[x])) for x, (c, s) in zip(counts, tails)))
        values = matrix @ np.array(h)
        compatible.append(bool(np.all(values >= lower) and np.all(values <= upper)))
    t = max(score for score, keep in zip(scores, compatible) if keep)
    return sum(probability(h, probabilities) for h, score in zip(all_histograms, scores) if score <= t)


def problem(n=4):
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in (1, 2, 3)))
    return EmpiricalProblem(n=n, panel=panel, quantiles=[],
                            count_intervals=[(np.array([1., 1., 0.]), 1, n - 1)])


@pytest.mark.parametrize("cdf,lower,upper", [
    ([0., .125, .75, 1.], [0, 0, 1, 4], [0, 2, 3, 4]),
    ([.25, .25, .75], [0, 1, 1], [3, 2, 4]),
    ([0., .5, 1.], [0, 0, 4], [0, 4, 4]),
    ([.125, .5, .875], [0, 1, 2], [1, 3, 4]),
    ([.25, .25], [0, 3], [2, 4]),
])
def test_rectangle_bounds_enclose_exact_rational_sum(cdf, lower, upper):
    n = 4
    interior = sorted(set(q for q in cdf if 0 < q < 1))
    f = [Fraction(0), *(Fraction.from_float(q) for q in interior), Fraction(1)]
    p = [b - a for a, b in zip(f, f[1:])]
    exact = Fraction(0)
    for h in compositions(n, len(p)):
        prefix = np.cumsum(h)
        lookup = {0.: 0, 1.: n, **dict(zip(interior, prefix))}
        if all(lo <= lookup[q] <= hi for q, lo, hi in zip(cdf, lower, upper)):
            exact += probability(h, p)
    a, b = joint.rectangle_probability_bounds(n, cdf, lower, upper)
    assert Fraction.from_float(a) <= exact <= Fraction.from_float(b)


@pytest.mark.parametrize("lower,upper", [
    ([0., 0.], [1., 1.]),
    ([.25, .25], [.25, .25]),
    ([.125, .25], [.75, .875]),
    ([0., .5], [.5, 1.]),
    ([.125, .75], [.25, .875]),
])
def test_uniform_box_certificate_against_exact_rational_values(lower, upper):
    obj = problem()
    bound = Fraction.from_float(joint.box_pvalue_upper({'a': obj}, lower, upper))
    for q0, q1 in product(*[(lo, (lo + hi) / 2, hi) for lo, hi in zip(lower, upper)]):
        if q0 <= q1:
            assert rational_report_pvalue(obj, [q0, q1]) <= bound


@pytest.mark.parametrize("cdf", [[0., 0.], [0., 1.], [.25, .25], [.25, .75], [.5, .5], [1., 1.]])
def test_point_acceptance_certificate_never_exceeds_exact_value(cdf):
    obj = problem()
    bound = joint._point_lower(obj.n, [_prefix_distances(obj)], np.array(cdf), None)
    assert Fraction.from_float(bound) <= rational_report_pvalue(obj, cdf)


def test_functional_outer_bounds_use_outward_subtraction():
    lower, upper = np.array([.05, .7]), np.array([.1, .9])
    lo, hi = joint._functional_bounds(lower, upper)
    l = [Fraction(0), *(Fraction.from_float(x) for x in lower), Fraction(1)]
    u = [Fraction(0), *(Fraction.from_float(x) for x in upper), Fraction(1)]
    for j in range(3):
        exact_lower = max(Fraction(0), l[j + 1] - u[j])
        exact_upper = min(Fraction(1), u[j + 1] - l[j])
        assert Fraction.from_float(lo[2 + j]) <= exact_lower
        assert Fraction.from_float(hi[2 + j]) >= exact_upper


@pytest.mark.parametrize("n", [2, 5, 20])
def test_initial_cp_brackets_verified_by_exact_binomial_tails(n):
    alpha = (Fraction(1) - Fraction.from_float(.95)) / 3
    for count in sorted({0, 1, n - 1, n}):
        lo, hi = joint._cp_outer(count, n, alpha)
        if count:
            _, sf = rational_tails(n, Fraction.from_float(lo))
            assert sf[count] <= alpha / 2
        else:
            assert lo == 0
        if count < n:
            cdf, _ = rational_tails(n, Fraction.from_float(hi))
            assert cdf[count] <= alpha / 2
        else:
            assert hi == 1


def test_optional_arithmetic_failure_preserves_active_cover(monkeypatch):
    obj = problem()

    def failed(*args, **kwargs):
        raise ArithmeticError('controlled certificate failure')

    monkeypatch.setattr(joint, '_box_upper', failed)
    result = joint.population_distribution({'a': obj}, method='joint-exact', time_limit_seconds=10)
    assert result['status'] == 'unavailable'
    assert result['cdf_bounds'] == result['baseline_cdf_bounds']
    assert result['category_bounds'] == result['baseline_category_bounds']
    assert 'controlled certificate failure' in result['reason']


def test_score_tie_boxes_do_not_starve_other_population_boundaries():
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in (1, 2, 3)))
    obj = EmpiricalProblem(n=20, panel=panel, quantiles=[], equalities=[
        (np.array([1., 0., 0.]), 10),
        (np.array([0., 1., 0.]), 8),
    ])
    result = joint.population_distribution(
        {'a': obj}, method='joint-exact', time_limit_seconds=10, tolerance_pp=1.)
    baseline = np.array(result['baseline_cdf_bounds'])
    bounds = np.array(result['cdf_bounds'])
    assert bounds[0, 0] > baseline[0, 0] + .001
    assert bounds[0, 1] < baseline[0, 1] - .001
    assert result['unresolved_small_boxes'] > 0
    assert result['status'] == 'precision_unresolved'
    assert not result['precision_reached']
    assert result['endpoint_gap_pp'] > result['numerical_tolerance_pp']
    # The test checks bounded search structure and useful certified exclusions,
    # not a machine-dependent elapsed-time claim.
    assert result['box_count'] < 5000
