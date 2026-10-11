"""Independent finite arithmetic controls for low-coverage numerical paths."""
from fractions import Fraction as F
from itertools import product
from math import comb, prod

import pytest


def binomial_tails(n, count, p):
    masses = [F(comb(n, j))*p**j*(1-p)**(n-j) for j in range(n+1)]
    return sum(masses[:count+1]), sum(masses[count:])


def score(n, count, p):
    return min(F(1), 2*min(binomial_tails(n, count, p)))


def compositions(n, k):
    for first in product(range(n+1), repeat=k-1):
        if sum(first) <= n:
            yield (*first, n-sum(first))


@pytest.mark.parametrize('h,e,f', [((1,1,1), {0}, {1}),
    ((1,1,0,0,1), {0}, {1}), ((1,0,0,1,0,0,0,1), {0}, {3})])
def test_tied_root_law_and_union_checked_by_ordered_sample_enumeration(h, e, f):
    from mic_50_90._hunter.tie_witness import tied_witness, witness_range
    record = tied_witness(h, e, f, F(3,4), root_bits=24)
    assert record is not None
    n, k = sum(h), len(h)
    tau = record['tail_probability']; lo, hi = record['root_lower'], record['root_upper']
    ce, cf = sum(h[j] for j in e), sum(h[j] for j in f)
    assert tau == binomial_tails(n, ce, F(3,4))[0]
    assert binomial_tails(n, cf, lo)[1] < tau <= binomial_tails(n, cf, hi)[1]
    A, B = record['intercept'], record['coefficient']
    assert sum(A) == 1 and sum(B) == 0
    upper_root_law = [a+b*hi for a,b in zip(A,B)]
    assert sum(upper_root_law) == 1 and min(upper_root_law) >= 0
    intersection = sum((prod(upper_root_law[j] for j in sample)
        for sample in product(range(k), repeat=n)
        if sum(j in e for j in sample) <= ce and sum(j in f for j in sample) >= cf), F(0))
    assert record['union_lower'] == 2*tau-intersection >= F(1,20)
    for a in range(k):
        for b in range(a+1, k+1):
            lower, upper = witness_range(record, a, b)
            assert 0 <= lower <= upper <= 1
            # Endpoint enclosures are for one affine root law, not a free box.
            assert lower == min(sum(A[a:b])+sum(B[a:b])*v for v in (lo,hi))


def contains_counts(region, h):
    return any(all(lo <= sum(h[a:b]) <= hi for a,b,lo,hi in variant)
               for variant in region.variants)


def contains_law(cell, p):
    prefix = [F(0), *[sum(p[:j]) for j in range(1,len(p)+1)]]
    return all(prefix[b]-prefix[a] <= cell[a][b]
               for a in range(len(prefix)) for b in range(len(prefix)))


def specimen():
    from mic_50_90._hunter.pairwise import HistRegion
    from mic_50_90._hunter.endpoint import close
    region = HistRegion(3, 3, (((0,1,0,1),(1,2,1,2)), ((0,1,2,3),)))
    cell = [[F(int(a < b)) for b in range(4)] for a in range(4)]
    cell[3][0] = F(-1)
    return region, close(cell)


def test_count_probability_propagation_never_removes_a_compatible_grid_pair():
    from mic_50_90._hunter.contractor import propagate
    region, cell = specimen()
    cutoff = F(1,5)
    nodes = propagate(region, cell, cutoff, rounds=4)
    checked = 0
    for h in compositions(3,3):
        if not contains_counts(region,h): continue
        for integers in compositions(8,3):
            p = tuple(F(x,8) for x in integers)
            if all(score(3,sum(h[a:b]),sum(p[a:b])) >= cutoff
                   for a in range(3) for b in range(a+1,4)):
                checked += 1
                assert any(contains_counts(node.region,h) and contains_law(node.cell,p) for node in nodes)
    assert checked > 20


def test_upper_score_branch_union_covers_every_qualifying_histogram_law_pair():
    from mic_50_90._hunter.upper_score import upper_branches
    region, cell = specimen()
    cutoff = F(1,4)
    branches = upper_branches(region,cell,cutoff)
    checked = 0
    for h in compositions(3,3):
        if not contains_counts(region,h): continue
        for integers in compositions(8,3):
            p = tuple(F(x,8) for x in integers)
            if min(score(3,sum(h[a:b]),sum(p[a:b]))
                   for a in range(3) for b in range(a+1,3)) <= cutoff:
                checked += 1
                assert any(contains_counts(branch.region,h) and contains_law(branch.cell,p) for branch in branches)
    assert checked > 100


def test_unfinished_root_or_contraction_cannot_be_mistaken_for_exclusion():
    from mic_50_90._hunter.budget import deadline_scope
    from mic_50_90._hunter.tie_witness import tied_witness
    from mic_50_90._hunter.contractor import propagate
    from mic_50_90._hunter.upper_score import upper_branches
    region, cell = specimen()
    for operation in (lambda: tied_witness((1,1,1),{0},{1},F(3,4)),
                      lambda: propagate(region,cell,F(1,5)),
                      lambda: upper_branches(region,cell,F(1,4))):
        with deadline_scope(0), pytest.raises(TimeoutError):
            operation()
