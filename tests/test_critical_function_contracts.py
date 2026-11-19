"""Exact contracts of the thirteen critical functions named in pyproject.toml ([tool.mutmut]).

Each test states the result a function must return, mostly against an independent calculation:
enumeration of compatible histograms, SciPy beta quantiles, the Turán edge count from explicit
partitions, or a closed form. Messages that the program shows to users are checked word for word.
"""
from __future__ import annotations

import inspect
import itertools
import sys
from fractions import Fraction as F
from math import ulp
from time import monotonic
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import beta, binom

import mic_50_90
from mic_50_90 import joint_population as jp
from mic_50_90 import sufficient_reporting
from mic_50_90.conformal import conformal_rank
from mic_50_90.count_updates import counts_from_percentage
from mic_50_90.dro import CriticalRadiusSearchLimit, critical_radius
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel
from mic_50_90.range_certificates import binomial_shape_certificate
from mic_50_90.range_population import critical_score
from mic_50_90.utility import _prefix_distances
from mic_50_90.validation import ceiling_rank
from test_decision_planning import criteria, specification

ASSUMPTIONS = ('Complete histogram known to the reporter; truthful counts from the same sample. Preserves only the '
               'declared recorded-sample decisions. Costs do not measure staff time or information-acquisition cost.')
GUARANTEE = 'Logical implication of the declared summaries and truthful counts; no new population or calibration guarantee'


# ---------------------------------------------------------------- ceiling_rank
def test_ceiling_rank_values_and_sample_size_message():
    assert [ceiling_rank('.5', n) for n in (1, 2, 3, 67)] == [1, 1, 2, 34]
    assert ceiling_rank('.9', 67) == 61
    for bad in (0, -3, 2.5):
        with pytest.raises(ValueError) as error:
            ceiling_rank('.5', bad)
        assert str(error.value) == 'n must be an exact integer >= 1'


# ---------------------------------------------------------------- critical_score
def turan_edges(k, r):
    """Edges of the complete r-partite graph on k vertices with parts as equal as possible."""
    sizes = [len(part) for part in np.array_split(np.arange(k), r)]
    return (k * k - sum(s * s for s in sizes)) // 2


def critical_score_oracle(n, k, alpha):
    alpha = F(alpha)
    pairs = k * (k - 1) // 2
    candidates = [alpha / pairs]
    for r in range(1, k):
        candidates.append(min(2 * alpha / (pairs + turan_edges(k, r)), 2 * F(r, r + 1) ** n))
    return min(F(1), max(candidates))


@pytest.mark.parametrize('k', range(2, 9))
def test_critical_score_matches_the_turan_edge_formula(k):
    for n in range(1, 13):
        for alpha in (F(1, 100), F(1, 20), F(1, 5), F(1, 2), F(9, 10)):
            value = critical_score(n, k, alpha)
            assert isinstance(value, F)
            assert value == critical_score_oracle(n, k, alpha), (n, k, alpha)


@pytest.mark.parametrize('n, k, message', [
    (0, 2, 'Positive sample size and at least two categories required'),
    (5, 1, 'Positive sample size and at least two categories required'),
    (2.0, 3, 'Positive sample size and at least two categories required'),
    (3, 3.0, 'Positive sample size and at least two categories required')])
def test_critical_score_rejects_invalid_sizes(n, k, message):
    with pytest.raises(ValueError) as error:
        critical_score(n, k, F(1, 20))
    assert str(error.value) == message


@pytest.mark.parametrize('alpha', [0, 1, F(3, 2), -F(1, 10)])
def test_critical_score_rejects_alpha_outside_the_open_unit_interval(alpha):
    with pytest.raises(ValueError) as error:
        critical_score(10, 4, alpha)
    assert str(error.value) == 'alpha must lie in (0,1)'


# ---------------------------------------------------------------- _cp_outer
@pytest.mark.parametrize('n', [1, 2, 7, 30, 200])
def test_cp_outer_brackets_the_exact_clopper_pearson_endpoints(n):
    alpha = F(1, 20)
    for count in range(n + 1):
        lower, upper = jp._cp_outer(count, n, alpha)
        exact_lower = 0.0 if count == 0 else beta.ppf(0.025, count, n - count + 1)
        exact_upper = 1.0 if count == n else beta.ppf(0.975, count + 1, n - count)
        assert exact_lower - 1e-9 <= lower <= exact_lower
        assert exact_upper <= upper <= exact_upper + 1e-9
        if 0 < count:
            assert binom.sf(count - 1, n, lower) <= 0.025 * (1 + 1e-9)
        if count < n:
            assert binom.cdf(count, n, upper) <= 0.025 * (1 + 1e-9)


def test_cp_outer_expands_by_doubling_from_a_poor_start(monkeypatch):
    count, n, alpha = 3, 10, F(1, 20)
    exact_upper = jp._cp_outer(count, n, alpha)[1]
    monkeypatch.setattr(jp, '_cp_start', lambda c, size, a: (0.5, exact_upper))
    lower, upper = jp._cp_outer(count, n, alpha)
    delta = 1e-12
    while binom.sf(count - 1, n, max(0., 0.5 - delta)) > 0.025:
        delta *= 2
    assert lower == max(0., 0.5 - delta)
    assert upper == min(1., exact_upper + 1e-12)


def test_cp_outer_stops_at_the_certain_endpoint(monkeypatch):
    exact_upper = jp._cp_outer(1, 10, F(1, 20))[1]
    monkeypatch.setattr(jp, '_cp_start', lambda c, size, a: (1e-13, exact_upper))
    assert jp._cp_outer(1, 10, F(1, 20)) == (0.0, min(1., exact_upper + 1e-12))


def test_cp_outer_expands_by_doubling_from_a_start_inside_the_interval(monkeypatch):
    # the 90% endpoints lie inside the 95% interval, so both sides must widen step by step
    count, n, alpha = 3, 10, F(1, 20)
    inside = (float(beta.ppf(0.05, count, n - count + 1)), float(beta.ppf(0.95, count + 1, n - count)))
    monkeypatch.setattr(jp, '_cp_start', lambda c, size, a: inside)
    expected = []
    for side, x in enumerate(inside):
        delta = 1e-12
        while True:
            candidate = max(0., x - delta) if side == 0 else min(1., x + delta)
            tail = binom.sf(count - 1, n, candidate) if side == 0 else binom.cdf(count, n, candidate)
            if tail <= 0.025:
                break
            delta *= 2
        expected.append(candidate)
    lower, upper = jp._cp_outer(count, n, alpha)
    assert (lower, upper) == tuple(expected)
    assert lower < inside[0] - 1e-3 and upper > inside[1] + 1e-3


def test_cp_outer_stops_at_the_certain_upper_endpoint(monkeypatch):
    lower = jp._cp_outer(9, 10, F(1, 20))[0]
    start = jp._cp_start(9, 10, F(1, 20))
    monkeypatch.setattr(jp, '_cp_start', lambda c, size, a: (start[0], 1 - 1e-13))
    assert jp._cp_outer(9, 10, F(1, 20)) == (lower, 1.0)


def test_cp_outer_accepts_a_tail_equal_to_half_alpha(monkeypatch):
    candidate = 0.3 - 1e-12
    tail = jp._binomial_tails(1, candidate)[3][1]
    monkeypatch.setattr(jp, '_cp_start', lambda c, size, a: (0.3, 1.))
    assert jp._cp_outer(1, 1, 2 * F(tail)) == (candidate, 1.0)


# ---------------------------------------------------------------- conformal_rank
def test_conformal_rank_values_and_boundaries():
    assert conformal_rank(19, 0.05) == 19
    assert conformal_rank(9, 0.1) == 9
    assert conformal_rank(20, 0.05) == 20
    # (1 + 1) * (1 - alpha) lies 8 or 9 float steps above 1: only the first is roundoff
    assert 2 * (1.0 - 0.4999999999999991) == 1 + 8 * ulp(1.0)
    assert conformal_rank(1, 0.4999999999999991) == 1
    assert 2 * (1.0 - 0.499999999999999) == 1 + 9 * ulp(1.0)
    assert conformal_rank(1, 0.499999999999999) == 2


@pytest.mark.parametrize('size, alpha, message', [
    (0, 0.1, 'calibration_size must be positive'), (5, 0, 'alpha must lie in (0, 1)'),
    (5, 1, 'alpha must lie in (0, 1)'), (5, 1.5, 'alpha must lie in (0, 1)')])
def test_conformal_rank_rejects_invalid_arguments(size, alpha, message):
    with pytest.raises(ValueError) as error:
        conformal_rank(size, alpha)
    assert str(error.value) == message


# ---------------------------------------------------------------- _prefix_distances
def test_prefix_distances_refuse_contradictory_constraints():
    # F_1 <= 1 and F_1 >= 2: a negative cycle of length -1 on the cumulative counts
    problem = SimpleNamespace(k=2, linear_constraints=(np.array([[1., 0.]]), np.array([2.]), np.array([1.])))
    with pytest.raises(ValueError) as error:
        _prefix_distances(problem)
    assert str(error.value) == 'Incompatible cumulative-count constraints'
    feasible = SimpleNamespace(k=2, linear_constraints=(np.array([[1., 0.]]), np.array([1.]), np.array([1.])))
    inf = float('inf')
    assert _prefix_distances(feasible).tolist() == [[0., 1., inf], [-1., 0., inf], [-1., 0., 0.]]


def test_prefix_distances_tolerance_is_one_billionth():
    # F_1 <= 1 and F_1 >= 1.5: half a count of contradiction is refused
    half = SimpleNamespace(k=2, linear_constraints=(np.array([[1., 0.]]), np.array([1.5]), np.array([1.])))
    with pytest.raises(ValueError):
        _prefix_distances(half)
    # a cycle of exactly -1e-9 after closure is rounding, not a contradiction
    rounding = SimpleNamespace(k=2, linear_constraints=(np.array([[1., 0.]]), np.array([5e-10]), np.array([0.])))
    inf = float('inf')
    assert _prefix_distances(rounding).tolist() == [[0., 0., inf], [0., 0., inf], [0., 0., 0.]]


# ---------------------------------------------------------------- counts_from_percentage
@pytest.mark.parametrize('arguments, expected', [
    (dict(percentage=1, n=200, decimal_places=0, rounding_rule='half_up'), (1, 2)),
    (dict(percentage=1, n=200, decimal_places=0, rounding_rule='half_even'), (2, 2)),
    (dict(percentage='0.5', n=2000, decimal_places=1, rounding_rule='half_even'), (10, 10)),
    (dict(percentage='0.4', n=2000, decimal_places=1, rounding_rule='half_even'), (7, 9)),
    (dict(percentage=49, n=67, decimal_places=0, rounding_rule='half_up'), (33, 33)),
    (dict(percentage=10, n=200, decimal_places=0, rounding_rule='floor'), (20, 21)),
    (dict(percentage=10, n=200, decimal_places=0, rounding_rule='ceiling'), (19, 20)),
    (dict(percentage=100, n=7, decimal_places=0, rounding_rule='half_up'), (7, 7)),
    (dict(percentage='40.000000', n=30, decimal_places=6, rounding_rule='half_even'), (12, 12))])
def test_counts_from_percentage_at_rounding_ties(arguments, expected):
    assert counts_from_percentage(**arguments) == expected


@pytest.mark.parametrize('arguments, message', [
    (dict(percentage=5, n=0, decimal_places=0, rounding_rule='half_up'), 'n must be an exact integer >= 1'),
    (dict(percentage=5, n=10, decimal_places=-1, rounding_rule='half_up'), 'decimal_places must be an exact integer >= 0'),
    (dict(percentage=5, n=10, decimal_places=7, rounding_rule='half_up'), 'decimal_places must be between 0 and 6'),
    (dict(percentage='five', n=10, decimal_places=0, rounding_rule='half_up'), 'percentage must be a finite number on the 0..100 scale'),
    (dict(percentage='100.5', n=10, decimal_places=1, rounding_rule='half_up'), 'percentage must lie in 0..100 and match decimal_places'),
    (dict(percentage='5.25', n=10, decimal_places=1, rounding_rule='half_up'), 'percentage must lie in 0..100 and match decimal_places'),
    (dict(percentage=5, n=10, decimal_places=0, rounding_rule='nearest'), 'rounding_rule must be half_up, half_even, floor or ceiling'),
    (dict(percentage=33, n=4, decimal_places=0, rounding_rule='half_up'),
     'No integer count with this n produces the reported percentage and rounding rule')])
def test_counts_from_percentage_messages(arguments, message):
    with pytest.raises(ValueError) as error:
        counts_from_percentage(**arguments)
    assert str(error.value) == message


# ---------------------------------------------------------------- binomial_shape_certificate
def test_shape_certificate_reasons_and_claim(monkeypatch):
    assert binomial_shape_certificate(2, F(1, 20), 0) == dict(status='unresolved', reason='Shape certificate time limit')
    certified = binomial_shape_certificate(3, F(1, 37), float('inf'))
    assert certified['claim'] == ('At most K distinct histograms from K+1 indexed count rows attain all contiguous population '
                                  'projection endpoints in each reporting variant; no equality of full regions is claimed')
    from mic_50_90.range_certificates import _legacy_binomial_shape_certificate
    # These injected brackets test the retained legacy fallback, not the independent receiver.
    monkeypatch.setattr(jp, '_cp_inner', lambda *arguments: None)
    assert _legacy_binomial_shape_certificate(2, F(1, 20), float('inf')) == dict(
        status='unresolved', reason='An inward endpoint was not certified')
    monkeypatch.setattr(jp, '_cp_inner', lambda x, n, c: (0, [F(1, 8), F(1, 2), F(1)][x]))
    monkeypatch.setattr(jp, '_cp_outer', lambda x, n, c: (0, [F(3, 8), F(3, 4), F(1)][x]))
    assert _legacy_binomial_shape_certificate(2, F(1, 20), float('inf')) == dict(
        status='unresolved', reason='Discrete concavity was not certified')


# ---------------------------------------------------------------- verify_reporting
def compatible_histograms(n, k, constraints):
    for cut in itertools.combinations(range(n + k - 1), k - 1):
        bars = (-1,) + cut + (n + k - 1,)
        histogram = [bars[j + 1] - bars[j] - 1 for j in range(k)]
        if all(rule(histogram) for rule in constraints):
            yield histogram


def ranked_category(histogram, rank):
    return next(j for j, cumulative in enumerate(itertools.accumulate(histogram)) if cumulative >= rank)


def test_verify_reporting_bounds_match_enumeration():
    # n = 10, panel 1..16 mg/L; MIC50 (rank 5) in category 1, MIC90 (rank 9) in category 2
    rules = [lambda h: ranked_category(h, 5) == 0, lambda h: ranked_category(h, 9) == 1]
    result = mic_50_90.verify_reporting(specification(), criteria(), [])
    assert set(result) == {'sufficient', 'decisions', 'bounds', 'sample_size', 'scope', 'guarantee'}
    assert result['scope'] == 'recorded_sample_decisions' and result['guarantee'] == GUARANTEE
    assert result['sample_size'] == 10 and result['sufficient'] is False
    for bound, (threshold, cut) in zip(result['bounds'], ((2, 2), (4, 3), (8, 4)), strict=True):
        above = sorted({sum(h[cut:]) for h in compatible_histograms(10, 5, rules)})
        assert bound == dict(threshold=float(threshold), unit='mg/L', decision_operator='<', decision_fraction_text='.05',
                             count_min=above[0], count_max=above[-1], count_components=[[above[0], above[-1]]], n=10,
                             status='undetermined')
    disclosed = mic_50_90.verify_reporting(specification(), criteria(), [
        dict(threshold=2, unit='mg/L', count=1, n=10), dict(threshold=4, unit='mg/L', count=0, n=10)])
    assert disclosed['sufficient'] is True
    assert disclosed['decisions'] == ['contradicted', 'supported', 'supported']
    assert [(b['count_min'], b['count_max']) for b in disclosed['bounds']] == [(1, 1), (0, 0), (0, 0)]


# ---------------------------------------------------------------- plan_reporting
def plan(histogram, specification_=None, criteria_=None, **options):
    return mic_50_90.plan_reporting(specification_ or specification(), histogram, criteria_ or criteria(), **options)


def checked(result, *, complete):
    search = result.pop('search')
    assert set(search) == {'states', 'elapsed_seconds', 'complete'}
    assert search['complete'] is complete and search['elapsed_seconds'] >= 0
    result.pop('verification')
    return search['states']


def test_plan_reporting_documented_defaults(monkeypatch):
    parameters = inspect.signature(mic_50_90.plan_reporting).parameters
    assert parameters['time_limit_seconds'].default == 5.0
    assert parameters['max_states'].default == 5000
    budgets = []

    def recorded(seconds, states):
        budgets.append((seconds, states))
        return budget(seconds, states)
    budget = sufficient_reporting._Budget
    monkeypatch.setattr(sufficient_reporting, '_Budget', recorded)
    plan([5, 4, 1, 0, 0])
    assert budgets == [(5.0, 5000)]


def test_plan_reporting_boundary_certificate_result():
    result = plan([5, 4, 1, 0, 0])
    assert checked(result, complete=True) == 2
    assert result == dict(
        status='optimal', sufficient=True, optimality_verified=True, scope='recorded_sample_decisions', sample_size=10,
        initial_decisions=['undetermined'] * 3,
        disclosures=[dict(threshold=2.0, unit='mg/L', count=1, n=10), dict(threshold=4.0, unit='mg/L', count=0, n=10)],
        selected_queries=[dict(threshold=2.0, unit='mg/L', cost=1.0, cost_exact='1', cut_index=1),
                          dict(threshold=4.0, unit='mg/L', cost=1.0, cost_exact='1', cut_index=2)],
        report_cost=2.0, report_cost_exact='2', cost_lower_bound=2.0, cost_lower_bound_exact='2',
        method='observed_boundary_certificate', reason=None, assumptions=ASSUMPTIONS)


def test_plan_reporting_when_the_summaries_already_decide():
    result = plan([5, 4, 1, 0, 0], criteria_=criteria(fraction='.5'))
    assert checked(result, complete=True) == 0
    assert result == dict(
        status='already_resolved', sufficient=True, optimality_verified=True, scope='recorded_sample_decisions',
        sample_size=10, initial_decisions=['supported'] * 3, disclosures=[], selected_queries=[], report_cost=0.0,
        report_cost_exact='0', cost_lower_bound=0.0, cost_lower_bound_exact='0', method='cost_ordered_report_subsets',
        reason=None, assumptions=ASSUMPTIONS)


def test_plan_reporting_when_no_permitted_count_suffices():
    result = plan([5, 4, 1, 0, 0], queries=[])
    assert checked(result, complete=True) == 0
    assert result == dict(
        status='impossible', sufficient=False, optimality_verified=False, scope='recorded_sample_decisions',
        sample_size=10, initial_decisions=['undetermined'] * 3, disclosures=[], selected_queries=[], report_cost=None,
        report_cost_exact=None, cost_lower_bound=0.0, cost_lower_bound_exact='0', method='cost_ordered_report_subsets',
        reason='Even all permitted truthful counts leave at least one declared decision unresolved for this histogram.',
        assumptions=ASSUMPTIONS)


def variant_problem():
    histograms = [(0, 1, 1, 1), (0, 2, 1, 0), (1, 1, 0, 1), (1, 0, 2, 0)]
    summaries = []
    for h in histograms:
        ordered = [str(2**j) for j, c in enumerate(h) for _ in range(c)]
        summaries.append({'minimum': ordered[0], 'quantiles': [
            {'probability': .5, 'rank': 2, 'category': ordered[1]}, {'probability': .9, 'rank': 3, 'category': ordered[2]}]})
    raw = specification(3, 4)
    raw['summaries'] = summaries[0]
    raw['reporting_envelope'] = {'variants': [{'id': str(j), 'summaries': s} for j, s in enumerate(summaries[1:])]}
    queries = [{'threshold': t, 'unit': 'mg/L', 'cost': c} for t, c in [(1, 1), (2, 3), (4, 1)]]
    return raw, histograms[0], criteria((2,), '.5', '<='), queries


def test_plan_reporting_subset_search_finds_the_cheapest_report():
    raw, histogram, questions, queries = variant_problem()
    result = mic_50_90.plan_reporting(raw, histogram, questions, queries=queries)
    assert checked(result, complete=True) == 4
    assert (result['status'], result['method'], result['report_cost_exact'], result['cost_lower_bound_exact']) == (
        'optimal', 'cost_ordered_report_subsets', '2', '2')
    assert [d['threshold'] for d in result['disclosures']] == [1.0, 4.0]
    assert [q['cut_index'] for q in result['selected_queries']] == [0, 2]
    assert result['optimality_verified'] is True and result['reason'] is None


@pytest.mark.parametrize('states, lower', [(1, '1'), (2, '1'), (3, '2')])
def test_plan_reporting_state_limit_keeps_a_sufficient_report_and_a_lower_bound(states, lower):
    raw, histogram, questions, queries = variant_problem()
    result = mic_50_90.plan_reporting(raw, histogram, questions, queries=queries, max_states=states)
    assert checked(result, complete=False) == states
    assert (result['status'], result['sufficient'], result['optimality_verified']) == ('incomplete', True, False)
    assert (result['report_cost_exact'], result['cost_lower_bound_exact'], result['cost_lower_bound']) == ('5', lower, float(lower))
    assert [d['threshold'] for d in result['disclosures']] == [1.0, 2.0, 4.0]
    assert result['reason'] == 'Search limit reached; the displayed report is sufficient but may not be cheapest.'


@pytest.mark.parametrize('histogram, message', [
    ('5410', 'histogram must contain one count per panel category'),
    (5, 'histogram must contain one count per panel category'),
    ([5, 4, 1, 0], 'histogram must include every category and sum to the original n'),
    ([5, 4, 1, 0, 1], 'histogram must include every category and sum to the original n'),
    ([5, 4, 0.5, 0.5, 0], 'histogram count must be an exact integer >= 0'),
    ([0, 0, 0, 0, 10], 'histogram is incompatible with every declared reporting interpretation')])
def test_plan_reporting_histogram_messages(histogram, message):
    with pytest.raises(ValueError) as error:
        plan(histogram)
    assert str(error.value) == message


def test_plan_reporting_reports_its_own_search_time():
    started = monotonic()
    result = plan([5, 4, 1, 0, 0])
    assert 0 <= result['search']['elapsed_seconds'] <= monotonic() - started


def test_plan_reporting_with_no_time_keeps_the_full_report_and_a_zero_bound():
    raw, histogram, questions, queries = variant_problem()
    result = mic_50_90.plan_reporting(raw, histogram, questions, queries=queries, time_limit_seconds=0)
    assert (result['status'], result['report_cost_exact'], result['cost_lower_bound_exact']) == ('incomplete', '5', '0')
    assert result['search']['states'] == 0


@pytest.mark.parametrize('states, lower', [(1, '2'), (2, '2'), (3, '4')])
def test_plan_reporting_lower_bound_is_a_cost_not_a_count_of_queries(states, lower):
    raw, histogram, questions, queries = variant_problem()
    doubled = [dict(q, cost=2 * q['cost']) for q in queries]
    result = mic_50_90.plan_reporting(raw, histogram, questions, queries=doubled, max_states=states)
    assert (result['status'], result['report_cost_exact'], result['cost_lower_bound_exact']) == ('incomplete', '10', lower)


def test_plan_reporting_refuses_a_report_that_fails_verification(monkeypatch):
    monkeypatch.setattr(sufficient_reporting, 'verify_reporting', lambda *arguments: dict(sufficient=False))
    with pytest.raises(RuntimeError) as error:
        plan([5, 4, 1, 0, 0])
    assert str(error.value) == 'Candidate reporting set did not pass recipient verification'


def test_plan_reporting_total_cost_must_remain_a_finite_double():
    # costs are exact; their total is checked as an exact number that must round to a finite double
    raw, histogram, questions, queries = variant_problem()
    largest = int(sys.float_info.max)
    accepted = [dict(queries[0], cost=str(largest)), dict(queries[1], cost=str(2**970 - 1)), dict(queries[2], cost='0')]
    assert mic_50_90.plan_reporting(raw, histogram, questions, queries=accepted)['status'] == 'optimal'
    refused = [dict(queries[0], cost=str(largest)), dict(queries[1], cost=str(2**970)), dict(queries[2], cost='0')]
    with pytest.raises(ValueError) as error:
        mic_50_90.plan_reporting(raw, histogram, questions, queries=refused)
    assert str(error.value) == 'Acquisition cost must be nonnegative and representable as a finite nonzero number when positive'


def test_plan_reporting_refuses_a_search_that_loses_every_report(monkeypatch):
    raw, histogram, questions, queries = variant_problem()
    monkeypatch.setattr(sufficient_reporting, 'heappush', lambda queue, item: None)
    with pytest.raises(RuntimeError) as error:
        mic_50_90.plan_reporting(raw, histogram, questions, queries=queries)
    assert str(error.value) == 'Sufficient report was lost from subset search'


def search_problem(histograms, thresholds, fraction, costs):
    def summaries(h):
        ordered = [str(2**j) for j, c in enumerate(h) for _ in range(c)]
        size = len(ordered)
        return {'minimum': ordered[0], 'quantiles': [
            {'probability': .5, 'rank': (size + 1) // 2, 'category': ordered[(size + 1) // 2 - 1]},
            {'probability': .9, 'rank': (9 * size + 9) // 10, 'category': ordered[(9 * size + 9) // 10 - 1]}]}
    raw = specification(4, 5)
    raw['summaries'] = summaries(histograms[0])
    raw['reporting_envelope'] = {'variants': [{'id': str(j), 'summaries': summaries(h)} for j, h in enumerate(histograms[1:])]}
    queries = [{'threshold': t, 'unit': 'mg/L', 'cost': c} for t, c in zip((1, 2, 4, 8), costs, strict=True)]
    return mic_50_90.plan_reporting(raw, histograms[0], criteria(thresholds, fraction, '<='), queries=queries)


def test_plan_reporting_search_skips_an_uninformative_count_and_continues():
    result = search_problem([(1, 0, 2, 0, 1), (2, 2, 0, 0, 0), (0, 3, 0, 1, 0)], (2, 4), '.25', (1, 3, 3, 2))
    assert (result['status'], result['report_cost_exact'], result['search']['states']) == ('optimal', '4', 7)
    assert [d['threshold'] for d in result['disclosures']] == [1.0, 4.0]


def test_plan_reporting_search_visits_each_set_of_counts_once():
    result = search_problem([(2, 0, 2, 0, 0), (1, 1, 0, 0, 2), (0, 3, 1, 0, 0), (0, 1, 2, 1, 0)], (1, 2, 8), '.25', (1, 2, 1, 2))
    assert (result['status'], result['report_cost_exact'], result['search']['states']) == ('optimal', '3', 6)
    assert [d['threshold'] for d in result['disclosures']] == [1.0, 2.0]


# ---------------------------------------------------------------- critical_radius
def two_category(levels=(1, 2**20), minimum_index=None):
    panel = MICPanel.from_twofold_levels(list(levels), left_censored=False, right_censored=False)
    return EmpiricalProblem(n=2, panel=panel, quantiles=(), minimum_index=minimum_index)


def radius(problem=None, reference=(1., 0.), truth=1., **options):
    problem = problem or two_category()
    k = problem.k
    objective = np.zeros(k)
    objective[-1] = 1.
    return critical_radius(problem=problem, reference=np.array(reference), positions=options.pop('positions', None),
                           objectives=[objective], truths=[truth], **options)


def test_critical_radius_is_the_transport_cost_of_the_true_tail():
    # moving a share t of the mass across a panel of log2 diameter 20 costs 20 t
    assert radius(truth=.25) == pytest.approx(5., abs=20 / 2**24)
    assert radius(truth=.5, tolerance=0.) == 10.
    assert radius(reference=(0., 1.), truth=.5, tolerance=0.) == 10.
    assert radius(truth=0., tolerance=0.) == 20 / 2**24
    assert radius(truth=1., tolerance=0.) == pytest.approx(20., abs=20 / 2**24)
    assert radius(truth=.25) == radius(truth=.25, steps=24)


def test_critical_radius_default_ceiling():
    narrow = two_category((1, 4))
    assert radius(narrow, truth=.5) == radius(narrow, truth=.5, ceiling=8.)
    wide = two_category((2, 4, 2**21))
    assert radius(wide, reference=(1., 0., 0.), truth=.6) == radius(wide, reference=(1., 0., 0.), truth=.6, ceiling=20.)


def test_critical_radius_uses_the_declared_positions():
    assert radius(truth=1., positions=np.array([0., .5])) == pytest.approx(.5, abs=1e-6)
    with pytest.raises(CriticalRadiusSearchLimit):
        radius(truth=1., positions=np.array([0., .5]), ceiling=.1, tolerance=0.)
    with pytest.raises(CriticalRadiusSearchLimit):
        radius(reference=(0., 1.), truth=-.05, positions=np.array([0., .5]), ceiling=.1, tolerance=.1)
    with pytest.raises(CriticalRadiusSearchLimit):
        radius(reference=(0., 1.), truth=0., positions=np.array([0., .5]), ceiling=.1, tolerance=0.)


def test_critical_radius_empty_ball_at_the_ceiling_is_a_search_limit():
    with pytest.raises(CriticalRadiusSearchLimit) as error:
        radius(two_category(minimum_index=1), truth=1., ceiling=1.)
    assert str(error.value) == 'critical-radius search ceiling is insufficient; use the default panel-diameter bound'


def test_critical_radius_accepts_boundary_controls():
    assert radius(truth=0., ceiling=.5) == .5 / 2**24
    assert radius(truth=.5, tolerance=0.) == 10.
    assert radius(truth=.5, steps=1) == 10.
    assert radius(truth=.6, steps=1) == 20.


@pytest.mark.parametrize('options, message', [
    (dict(ceiling=0.), 'invalid critical-radius search controls'), (dict(ceiling=-1.), 'invalid critical-radius search controls'),
    (dict(ceiling=float('inf')), 'invalid critical-radius search controls'),
    (dict(ceiling=float('nan')), 'invalid critical-radius search controls'),
    (dict(tolerance=-1.), 'invalid critical-radius search controls'),
    (dict(tolerance=float('nan')), 'invalid critical-radius search controls'),
    (dict(steps=0), 'invalid critical-radius search controls'), (dict(steps=1.5), 'invalid critical-radius search controls'),
    (dict(positions=np.array([0., 1., 2.])), 'positions must be strictly increasing and match the panel'),
    (dict(positions=np.array([0., np.inf])), 'positions must be strictly increasing and match the panel'),
    (dict(positions=np.array([1., 1.])), 'positions must be strictly increasing and match the panel'),
    (dict(positions=np.array([2., 1.])), 'positions must be strictly increasing and match the panel')])
def test_critical_radius_rejects_invalid_controls(options, message):
    with pytest.raises(ValueError) as error:
        radius(truth=.5, **options)
    assert str(error.value) == message


def test_critical_radius_bisection_passes_through_empty_balls():
    # the reference lies 12 log2 units from the sharp set, so radii below 12 give empty balls;
    # covering a tail share of one half costs 0.5 x 12 + 0.5 x 20 = 16
    problem = two_category((1, 2**12, 2**20), minimum_index=1)
    assert radius(problem, reference=(1., 0., 0.), truth=.5, tolerance=0.) == pytest.approx(16., abs=20 / 2**24)


def test_critical_radius_rejects_invalid_truths():
    problem = two_category()
    with pytest.raises(ValueError) as error:
        critical_radius(problem=problem, reference=np.array([1., 0.]), positions=None, objectives=[], truths=[])
    assert str(error.value) == 'objectives and truths must have matching nonzero lengths'
    with pytest.raises(ValueError) as error:
        critical_radius(problem=problem, reference=np.array([1., 0.]), positions=None,
                        objectives=[np.array([0., 1.])], truths=[1., 0.])
    assert str(error.value) == 'objectives and truths must have matching nonzero lengths'
    with pytest.raises(ValueError) as error:
        critical_radius(problem=problem, reference=np.array([1., 0.]), positions=None,
                        objectives=[np.array([0., 1.])], truths=[float('nan')])
    assert str(error.value) == 'truths must be finite'
