"""Independent raw-data checks; the oracle does not use the constraint matrix."""
from copy import deepcopy
from decimal import Decimal, localcontext, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING
from fractions import Fraction
from itertools import product

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from mic_50_90.count_updates import counts_from_percentage
from mic_50_90.distribution_workflow import distribution_problems
from mic_50_90.decisions import classify_intervals
from mic_50_90.range_certificates import close_counts, split_count_cell


def compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for x in range(n + 1):
            for tail in compositions(n - x, k - 1):
                yield (x, *tail)


def raw_compatible(h, raw):
    """Evaluate published facts on sorted category labels, not engine objects."""
    labels = [str(x) for x in raw['panel']['levels']]
    ordered = [label for label, count in zip(labels, h) for _ in range(count)]
    summaries = raw['summaries']
    for q in summaries['quantiles']:
        if ordered[q['rank'] - 1] != q['category']:
            return False
    if summaries.get('minimum') is not None and ordered[0] != summaries['minimum']:
        return False
    if summaries.get('maximum') is not None and ordered[-1] != summaries['maximum']:
        return False
    for row in raw.get('additional_counts', []):
        lo, hi = map(int, (row['start_category'], row['end_category']))
        count = sum(lo <= int(label) <= hi for label in ordered)
        if not row['count_min'] <= count <= row['count_max']:
            return False
    return True


@st.composite
def reports(draw):
    n, k = draw(st.integers(2, 8)), draw(st.integers(2, 5))
    obs = sorted(draw(st.lists(st.integers(0, k - 1), min_size=n, max_size=n)))
    levels = [2**j for j in range(k)]
    r1 = draw(st.integers(1, n - 1)); r2 = draw(st.integers(r1 + 1, n))
    summaries = dict(quantiles=[dict(probability=r / n, rank=r, category=str(levels[obs[r-1]])) for r in (r1, r2)])
    for key, index in [('minimum', 0), ('maximum', -1)]:
        if draw(st.booleans()):
            summaries[key] = str(levels[obs[index]])
    a = draw(st.integers(0, k-1)); b = draw(st.integers(a, k-1))
    count = sum(a <= j <= b for j in obs)
    row = dict(start_category=str(levels[a]), end_category=str(levels[b]), n=n, unit='mg/L',
               count_min=draw(st.integers(0, count)), count_max=draw(st.integers(count, n)))
    return dict(n=n, unit='mg/L', panel=dict(levels=levels, left_censored=False, right_censored=False),
                summaries=summaries, additional_counts=[row])


def bounds(raw):
    problems, _, _ = distribution_problems(raw)
    problem = problems['primary']; k = problem.k
    return {(a, b): tuple(s.count for s in problem.bounds(np.array([int(a <= j < b) for j in range(k)])))
            for a in range(k) for b in range(a+1, k+1)}


@given(reports())
@settings(max_examples=120, deadline=None)
def test_raw_facts_match_independent_sorted_sample_enumeration(raw):
    k = len(raw['panel']['levels'])
    feasible = [h for h in compositions(raw['n'], k) if raw_compatible(h, raw)]
    assert feasible
    for (a, b), answer in bounds(raw).items():
        reference = [sum(h[a:b]) for h in feasible]
        assert answer == (min(reference), max(reference))


@given(reports())
@settings(max_examples=80, deadline=None)
def test_count_refinement_order_and_equivalent_repetition(raw):
    original = deepcopy(raw)
    before = deepcopy(raw); before.pop('additional_counts')
    base, after = bounds(before), bounds(raw)
    assert all(base[p][0] <= v[0] <= v[1] <= base[p][1] for p, v in after.items())
    reordered = deepcopy(raw)
    reordered['summaries']['quantiles'].reverse()
    reordered['additional_counts'] *= 2
    assert bounds(reordered) == after
    assert raw == original


ROUNDINGS = {'half_up': ROUND_HALF_UP, 'half_even': ROUND_HALF_EVEN, 'floor': ROUND_FLOOR, 'ceiling': ROUND_CEILING}


@given(st.integers(1, 250), st.integers(0, 1000), st.integers(0, 2), st.sampled_from(list(ROUNDINGS)))
@settings(max_examples=200, deadline=None)
def test_rounded_percentage_preimage_against_decimal_enumeration(n, seed, places, rule):
    with localcontext() as ctx:
        ctx.prec = 50
        quantum = Decimal(1).scaleb(-places)
        observed = (Decimal(100*(seed % (n+1))) / n).quantize(quantum, rounding=ROUNDINGS[rule])
        counts = [x for x in range(n+1) if (Decimal(100*x)/n).quantize(quantum, rounding=ROUNDINGS[rule]) == observed]
    assert counts_from_percentage(str(observed), n=n, decimal_places=places, rounding_rule=rule) == (min(counts), max(counts))


@given(st.integers(1, 50), st.integers(0, 50))
def test_complementary_sample_criteria_include_boundary_ties(n, value):
    x = min(n, value); q = Fraction(x, n)
    assert classify_intervals([[q,q]], '<', q) == 'contradicted'
    assert classify_intervals([[q,q]], '<=', q) == 'supported'
    for op, complement in [('<', '>='), ('<=', '>'), ('>', '<='), ('>=', '<')]:
        a = classify_intervals([[0,q]], op, q)
        b = classify_intervals([[0,q]], complement, q)
        assert (a,b) in [('supported','contradicted'), ('contradicted','supported'), ('undetermined','undetermined')]
    assert classify_intervals([], '<', q) == 'unavailable'


@given(st.integers(2, 8), st.integers(2, 5))
@settings(max_examples=25, deadline=None)
def test_count_partition_is_disjoint_and_exhaustive(n, k):
    # Unrestricted nonnegative counts with fixed total.
    d = [[0 if a >= b else n for b in range(k+1)] for a in range(k+1)]
    d[k][0] = -n
    d = close_counts(d)
    children = split_count_cell(d)
    assert len(children) == 2
    for h in compositions(n,k):
        s = [sum(h[:j]) for j in range(k+1)]
        assert sum(all(s[b]-s[a] <= child[a][b] for a,b in product(range(k+1),repeat=2)) for child in children) == 1


@given(reports())
@settings(max_examples=100, deadline=None)
def test_constrained_count_partition_preserves_every_integer_histogram(raw):
    k, n = len(raw['panel']['levels']), raw['n']
    samples = [h for h in compositions(n,k) if raw_compatible(h,raw)]
    cumulative = [[sum(h[:j]) for j in range(k+1)] for h in samples]
    # Build the difference cell from independent feasible samples.
    d = [[max(s[b]-s[a] for s in cumulative) for b in range(k+1)] for a in range(k+1)]
    def members(cell):
        return {h for h in compositions(n,k) if all(
            sum(h[:b])-sum(h[:a]) <= cell[a][b]
            for a,b in product(range(k+1),repeat=2))}
    parent = members(d)
    children = split_count_cell(d)
    if len(parent) == 1:
        assert children == []
    else:
        assert len(children) == 2
        left, right = map(members, children)
        assert left and right and left < parent and right < parent
        assert left.isdisjoint(right) and left | right == parent
