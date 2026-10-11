"""The packaged original method must preserve its mathematical target."""
from fractions import Fraction as F
from itertools import product

import pytest


def test_kernel_loads_without_research_directories():
    from mic_50_90._hunter import score
    from mic_50_90._hunter.pairwise import HistRegion
    result=score.project(HistRegion(3,3,(((0,1,1,1),(1,2,1,1)),)),time_limit_seconds=0)
    assert result['method']=='pairwise-range-monotone-majorant'
    assert result['status']=='time_limit'
    assert len(result['intervals'])==6
    assert not result['precision_certified']
    assert all(0<=x['lower']<=x['upper']<=1 for x in result['intervals'])


@pytest.mark.parametrize('k',[3,5,8])
def test_package_accepts_empirical_law(k):
    from mic_50_90._hunter.endpoint import certify_witness
    from mic_50_90._hunter.pairwise import HistRegion
    h=[1,1]+[0]*(k-3)+[1]
    r=HistRegion(3,k,(tuple((j,j+1,c,c) for j,c in enumerate(h)),))
    assert certify_witness(r,tuple(F(c,3) for c in h))['accepted']


def test_fast_pair_probabilities_match_ordered_sample_enumeration():
    from mic_50_90._hunter.fast_pairs import exact
    q=(F(1,5),F(3,10),F(0),F(1,2))
    actual=exact(3,q);expected=[[F(0)]*4 for _ in range(4)]
    for sample in product(range(4),repeat=3):
        weight=F(1)
        for j in sample:weight*=q[j]
        expected[sum(j&1 for j in sample)][sum(j>>1 for j in sample)]+=weight
    assert actual==tuple(map(tuple,expected))


def test_probability_proposals_preserve_small_exact_ties():
    from mic_50_90._hunter.endpoint import rational_proposal,certify_witness
    from mic_50_90._hunter.pairwise import HistRegion
    p=(F(37,50),F(13,200),F(13,200),F(13,200),F(0),F(0),F(0),F(13,200))
    assert rational_proposal(p)==p
    r=HistRegion(3,8,(((0,4,3,3),(3,4,2,3)),))
    assert certify_witness(r,p)['accepted']


def test_interval_pair_probability_contains_exact_count():
    from mic_50_90._hunter.calibration import pair_event_probability
    p=(F(1,5),F(3,10),F(1,2))
    exact=pair_event_probability(3,p,(0,1),(0,2),F(1,2),exact=True)
    bounded=pair_event_probability(3,p,(0,1),(0,2),F(1,2),exact=False)
    assert bounded.lower<=exact.lower==exact.upper<=bounded.upper


def test_width_assessment_distinguishes_data_from_numerical_uncertainty():
    from mic_50_90._hunter.score import width_status
    assert width_status(F(0),F(1,10),None,None,F(1,10))=='met'
    assert width_status(F(0),F(1),F(1,5),F(4,5),F(1,10))=='not_met'
    assert width_status(F(0),F(1),F(1,5),F(3,10),F(1,10))=='unresolved'
    assert width_status(F(0),F(1),None,None,F(1,10))=='unresolved'


def test_width_goal_can_be_met_without_precise_endpoints():
    from mic_50_90._hunter import score
    from mic_50_90._hunter.pairwise import HistRegion
    r=HistRegion(3,3,(((0,1,1,1),(1,2,1,1)),))
    result=score.project(r,time_limit_seconds=0,width_target_pp=100)
    assert result['status']=='width_goal_assessed'
    assert result['width_goal']['status']=='met'
    assert result['nodes_visited']==0
    assert not result['precision_certified']
    assert all(x['width_status']=='met' for x in result['intervals'])
    assert result['error'] is None


@pytest.mark.parametrize('target',[float('nan'),float('inf'),-1,101,True])
def test_invalid_width_goal_is_rejected(target):
    from mic_50_90._hunter import score
    from mic_50_90._hunter.pairwise import HistRegion
    with pytest.raises(ValueError,match='width'):
        score.project(HistRegion(3,3,((),)),time_limit_seconds=0,width_target_pp=target)


def test_width_classification_against_all_small_endpoint_brackets():
    from mic_50_90._hunter.score import width_status
    grid=[F(j,4) for j in range(5)]
    for lo,il,iu,hi,target in product(grid,repeat=5):
        if not lo<=il<=iu<=hi:continue
        actual=width_status(lo,hi,il,iu,target)
        possible=[b-a for a,b in product(grid,repeat=2) if lo<=a<=il and iu<=b<=hi]
        if actual=='met':assert all(w<=target for w in possible)
        elif actual=='not_met':assert all(w>target for w in possible)
        else:assert any(w<=target for w in possible) and any(w>target for w in possible)
