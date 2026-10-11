"""Small independent null laws and interrupted-cover safety controls."""
from fractions import Fraction as F
from functools import lru_cache
from itertools import product
from math import comb, factorial, prod

import pytest

from mic_50_90._hunter import endpoint, score, upper_score
from mic_50_90._hunter.pairwise import HistRegion


@lru_cache(maxsize=None)
def histograms(n, k):
    return tuple((*first, n - sum(first))
                 for first in product(range(n + 1), repeat=k - 1) if sum(first) <= n)


def compatible(region, histogram):
    return any(all(low <= sum(histogram[a:b]) <= high for a, b, low, high in variant)
               for variant in region.variants)


def contains(cell, law):
    cumulative = (F(0), *[sum(law[:j]) for j in range(1, len(law) + 1)])
    return all(cumulative[b] - cumulative[a] <= cell[a][b]
               for a in range(len(cumulative)) for b in range(len(cumulative)))


@lru_cache(maxsize=None)
def null_scores(n, law):
    """Direct binomial sums on all proper contiguous ranges, including complements."""
    k = len(law)
    tails = {}
    for a in range(k):
        for b in range(a + 1, k + 1):
            if (a, b) == (0, k):
                continue
            q = sum(law[a:b])
            masses = tuple(F(comb(n, c)) * q**c * (1 - q)**(n - c) for c in range(n + 1))
            tails[a, b] = tuple(min(F(1), 2 * sum(masses[:c + 1]), 2 * sum(masses[c:]))
                                for c in range(n + 1))
    return {h: min(values[sum(h[a:b])] for (a, b), values in tails.items())
            for h in histograms(n, k)}


def true_null_probability(region, law):
    """Multinomial probability of a min-score at most the observed max-score."""
    scores = null_scores(region.n, law)
    threshold = max(value for h, value in scores.items() if compatible(region, h))
    return sum((F(factorial(region.n), prod(factorial(c) for c in h))
                * prod(q**c for q, c in zip(law, h))
                for h, value in scores.items() if value <= threshold), F(0))


def probability_cell(law, radius):
    k = len(law)
    cell = [[min(F(1), sum(law[a:b]) + radius) if a < b else
             -max(F(0), sum(law[b:a]) - radius) if a > b else F(0)
             for b in range(k + 1)] for a in range(k + 1)]
    cell[0][k], cell[k][0] = F(1), F(-1)
    return endpoint.close(cell)


@pytest.mark.parametrize("variants,center,denominator,radius,excluded", [
    ((((0, 1, 0, 0), (1, 2, 0, 0)),), (16, 2, 2), 20, F(1, 20), True),
    ((((0, 1, 0, 0), (1, 2, 0, 0)), ((0, 1, 3, 3),)), (2, 16, 2), 20, F(1, 20), True),
    ((((0, 1, 0, 0), (1, 2, 0, 0)),), (4, 4, 4), 12, F(1, 12), False),
    ((((0, 1, 1, 1), (1, 2, 1, 1)),), (4, 4, 4), 12, F(1, 12), False),
])
def test_uniform_exclusion_bound_dominates_independent_null_enumeration(
        variants, center, denominator, radius, excluded):
    region = HistRegion(3, 3, variants)
    cell = probability_cell(tuple(F(c, denominator) for c in center), radius)
    alpha = F(1, 20)
    bound = endpoint.uniform_bound(region, cell, alpha=alpha)
    checked = 0
    for counts in histograms(denominator, 3):
        law = tuple(F(c, denominator) for c in counts)
        if contains(cell, law):
            # The true null CDF is a lower bound on the fixed monotone majorant.
            # An exclusion certificate must therefore dominate it everywhere.
            assert true_null_probability(region, law) <= bound
            checked += 1
    assert checked >= 4
    assert (bound < alpha) is excluded  # Includes actual exclusions, not only 1.


def two_variant_region():
    return HistRegion(3, 3, (((0, 1, 0, 0), (1, 2, 1, 1)),
                             ((0, 1, 2, 2), (1, 2, 1, 1))))


def test_joint_score_narrowing_retains_inclusive_ties_after_anchor_reuse():
    region = two_variant_region()
    cell = probability_cell((F(1, 3),) * 3, F(1))
    checked = boundary = 0
    for low, high in [(F(1, 16), F(1, 4)), (F(1, 4), F(1, 2)), (F(1, 2), F(1))]:
        children = score.narrow(region, cell, low, high)
        # Exercise a second narrowing with the actual anchor chosen by the first.
        descendants = [child for node in children for child in score.narrow(
            node.region, node.cell, node.score_lo, node.score_hi, anchor=node.anchor)]
        for counts in histograms(4, 3):
            law = tuple(F(c, 4) for c in counts)
            for h, value in null_scores(3, law).items():
                if compatible(region, h) and low <= value <= high:
                    assert any(compatible(node.region, h) and contains(node.cell, law)
                               and node.score_lo <= value <= node.score_hi for node in descendants)
                    checked += 1
                    boundary += value in (low, high)
    assert checked > 10 and boundary > 0


@pytest.mark.parametrize("failure,status", [(TimeoutError, "time_limit"),
    (MemoryError, "calculation_incomplete"), (ArithmeticError, "calculation_incomplete"),
    (RuntimeError, "calculation_incomplete")])
def test_interrupted_sibling_replacement_retains_parent_and_certified_inner_work(monkeypatch, failure, status):
    region = two_variant_region()
    baseline = score.project(region, time_limit_seconds=0)
    actual_bound, visits = score.bound, []

    def interrupt_second_sibling(node, alpha, deadline):
        visits.append(node)
        if len(visits) == 2:
            raise failure("audit interruption during sibling replacement")
        return actual_bound(node, alpha, deadline)

    # Only the failure boundary is injected; the first child's bounds,
    # membership checks, witnesses and proposed replacements are real.
    monkeypatch.setattr(score, "bound", interrupt_second_sibling)
    result = score.project(region, time_limit_seconds=10, seed_seconds=0)
    assert result["status"] == status and "audit interruption" in result["error"]
    assert not result["precision_certified"]
    assert result["accepted_witnesses"]
    assert [(row["lower"], row["upper"]) for row in result["intervals"]] == [
        (row["lower"], row["upper"]) for row in baseline["intervals"]]
    for law in ((F(0), F(1, 3), F(2, 3)), (F(2, 3), F(1, 3), F(0))):
        assert true_null_probability(region, law) == 1
        for row in result["intervals"]:
            assert F(row["lower"]) <= sum(law[row["start"]:row["stop"]]) <= F(row["upper"])
    assert all(row["inner_lower"] is not None and row["inner_upper"] is not None
               for row in result["intervals"])


def test_timeout_after_real_exclusions_keeps_every_independently_accepted_grid_law(monkeypatch):
    region = HistRegion(3, 3, (((0, 1, 0, 0), (1, 2, 0, 0)),))
    actual_narrow, calls = score.narrow, 0

    def interrupt_after_refinement(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 20:
            raise TimeoutError("audit interruption after committed refinements")
        return actual_narrow(*args, **kwargs)

    monkeypatch.setattr(score, "narrow", interrupt_after_refinement)
    result = score.project(region, time_limit_seconds=10, seed_seconds=0)
    assert result["status"] == "time_limit" and "audit interruption" in result["error"]
    assert not result["precision_certified"]
    assert result["nodes_discarded"] > 0
    assert result["score_splits"] > 0 and result["probability_splits"] > 0
    checked = 0
    for counts in histograms(8, 3):
        law = tuple(F(c, 8) for c in counts)
        if true_null_probability(region, law) >= F(1, 20):
            checked += 1
            for row in result["intervals"]:
                assert F(row["lower"]) <= sum(law[row["start"]:row["stop"]]) <= F(row["upper"])
    assert checked >= 10


def test_unresolved_tail_inversion_cannot_remove_upper_score_possibilities(monkeypatch):
    region = two_variant_region()
    cell = probability_cell((F(1, 3),) * 3, F(1))
    # An optional numerical root bracket is unavailable, rather than a rejection.
    monkeypatch.setattr(upper_score, "tail_outer", lambda *args: None)
    branches = upper_score.upper_branches(region, cell, F(1, 4))
    checked = 0
    for counts in histograms(4, 3):
        law = tuple(F(c, 4) for c in counts)
        for h, value in null_scores(3, law).items():
            if compatible(region, h) and value <= F(1, 4):
                checked += 1
                assert any(compatible(branch.region, h) and contains(branch.cell, law)
                           for branch in branches)
    assert checked > 10


def test_dominance_exclusions_preserve_events_on_all_null_histograms():
    ranges = ((0, 1), (0, 2), (1, 2))
    events = ((0,), (0,), (0,))
    active, edges = endpoint.dominance_forest(3, 3, ranges, events, events)
    assert len(active) < len(ranges) and edges
    for h in histograms(3, 3):
        occurs = [sum(h[a:b]) in allowed for (a, b), allowed in zip(ranges, events)]
        assert any(occurs) == any(occurs[j] for j in active)
        assert all(not occurs[left] or occurs[right] for left, right in edges)
