from fractions import Fraction as F
from itertools import product
from math import comb
from time import monotonic

import numpy as np
import pytest

from mic_50_90.utility import _prefix_distances
from test_range_population import make_problem


def exact_accepted(h, p, cutoff):
    n = sum(h)
    for a in range(len(h)):
        for b in range(a+1, len(h)):
            x, q = sum(h[a:b]), sum(p[a:b])
            mass = [F(comb(n,j))*q**j*(1-q)**(n-j) for j in range(n+1)]
            if min(1, 2*sum(mass[:x+1]), 2*sum(mass[x:])) < cutoff:
                return False
    return True


@pytest.mark.parametrize('p', [(F(1,4),F(1,4),F(1,2)), (F(0),F(1,3),F(2,3)), (F(1),F(0),F(0))])
def test_certificate_membership_against_exact_exhaustive_test(p):
    from mic_50_90.range_certificates import compatible_probability_witness
    obj = make_problem(4, 3, constraints=[(np.array([0,1,0]),1,2)])
    d = _prefix_distances(obj).astype(int).tolist()
    cutoff = F(1,20)
    witness = compatible_probability_witness(d, p, cutoff, monotonic()+20)
    possible = [h for h in product(range(5), repeat=3) if sum(h)==4 and 1<=h[1]<=2 and exact_accepted(h,p,cutoff)]
    assert (witness is not None) == bool(possible)
    if witness is not None:
        assert tuple(witness) in possible


def test_count_partition_is_disjoint_and_exhaustive():
    from mic_50_90.range_certificates import split_count_cell
    d = _prefix_distances(make_problem(5, 3)).astype(int).tolist()
    children = split_count_cell(d)
    def contains(matrix,h):
        s=np.r_[0,np.cumsum(h)]
        return all(s[b]-s[a]<=matrix[a][b] for a in range(4) for b in range(4))
    for h in product(range(6), repeat=3):
        if sum(h)==5:
            assert sum(contains(c,h) for c in children) == 1


def test_certificate_timeout_is_not_an_exclusion():
    from mic_50_90.range_certificates import compatible_probability_witness
    d = _prefix_distances(make_problem(5, 3)).astype(int).tolist()
    with pytest.raises(TimeoutError):
        compatible_probability_witness(d, [F(1,3)]*3, F(1,20), monotonic()-1)


def test_shape_certificate_and_row_lift_against_independent_lps():
    from mic_50_90.range_certificates import binomial_shape_certificate
    from mic_50_90.range_population import critical_score
    from mic_50_90.joint_population import population_distribution
    from test_range_population import histograms, independent_lp
    cutoff=critical_score(4,3,1-F(.95))
    assert binomial_shape_certificate(4,cutoff,monotonic()+10)['status']=='certified'
    obj=make_problem(4,3,constraints=[(np.array([0,1,0]),1,2)])
    answer=population_distribution({'a':obj},method='range-calibrated',include_intervals=True)
    for row in answer['interval_bounds']:
        lps=[independent_lp(h,cutoff,row['start_index'],row['stop_index']) for h in histograms(4,3) if 1<=h[1]<=2]
        assert row['lower']==pytest.approx(min(x[0] for x in lps),abs=2e-9)
        assert row['upper']==pytest.approx(max(x[1] for x in lps),abs=2e-9)
