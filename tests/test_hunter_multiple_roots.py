"""Independent arithmetic checks for simultaneous algebraic score witnesses."""
from fractions import Fraction as F
from itertools import product
from math import comb, prod

import pytest


def tails(n, c, q):
    masses = [F(comb(n,j))*q**j*(1-q)**(n-j) for j in range(n+1)]
    return sum(masses[:c+1]), sum(masses[c:])


def test_selected_event_dp_equals_ordered_sample_enumeration():
    from mic_50_90._hunter.multiple_roots import lower_union
    weights = (F(1,10),F(2,10),F(6,10))
    for n in range(1,5):
        for limit in range(n+1):
            assignments = {0:1,2:min(2,n)}
            exact = F(0)
            for sample in product(range(3),repeat=n):
                counts = [sample.count(j) for j in range(3)]
                if counts[1] <= limit or any(counts[j]>=c for j,c in assignments.items()):
                    exact += prod(weights[j] for j in sample)
            assert lower_union(n,weights,assignments,{1},limit) == exact


@pytest.mark.parametrize('h,group,dominant,residual,u,assignments',[
    ((0,2,0,0,1),{2,3},2,0,F(77,100),{1:2,3:2,4:1}),
    ((1,0,0,2,0,0,0,0),{4,5,6,7},5,3,F(161,200),{0:1,1:1,2:1,4:1,6:1,7:1}),
])
def test_algebraic_witness_has_independently_checked_scores_and_union(h,group,dominant,residual,u,assignments):
    from mic_50_90._hunter.multiple_roots import certify, projection
    record = certify(h,dominant,u,residual,assignments,group=group)
    assert record is not None
    n,k=sum(h),len(h);tau=F(record['tau'])
    roots=[tuple(map(F,row)) for row in record['roots']]
    for c,(lo,hi) in zip(record['root_counts'],roots):
        assert tails(n,c,lo)[1] < tau <= tails(n,c,hi)[1]
    A=list(map(F,record['intercept']));B=record['coefficients']
    assert sum(A)==1 and all(sum(row[j] for row in B)==0 for j in range(len(roots)))
    family=[(a,b) for a in range(k) for b in range(a+1,k)]
    for a,b in family:
        lo,hi=projection(record,a,b);count=sum(h[a:b])
        intercept=sum(A[a:b]);coeff=tuple(sum(row[j] for row in B[a:b]) for j in range(len(roots)))
        tagged=False
        for j,c in enumerate(record['root_counts']):
            unit=tuple(int(i==j) for i in range(len(roots)))
            tagged |= intercept==0 and coeff==unit and count==c
            tagged |= intercept==1 and coeff==tuple(-v for v in unit) and count==n-c
        assert tagged or min(tails(n,count,hi)[0],tails(n,count,lo)[1]) >= tau
    lower=[projection(record,j,j+1)[0] for j in range(k)]
    union=F(0)
    for sample in product(range(k),repeat=n):
        if record['union_method']=='selected_root_events_dp':
            event=sum(j in group for j in sample)<=sum(h[j] for j in group) or any(sample.count(j)>=c for j,c in assignments.items() if c)
        else:
            event=any(sum(a<=j<b for j in sample) in allowed for (a,b),allowed in zip(family,record['events']))
        if event: union += prod(lower[j] for j in sample)
    assert union == F(record['union_lower']) and union >= F(1,20)


def test_multiple_root_work_respects_deadline():
    from mic_50_90._hunter.multiple_roots import certify, lower_union
    from mic_50_90._hunter.budget import deadline_scope
    with deadline_scope(0), pytest.raises(TimeoutError):
        certify((8,1,0,0,1),2,F(1,5),0,{1:1,3:1,4:1},group={2,3})
    with deadline_scope(0), pytest.raises(TimeoutError):
        lower_union(100,(F(1,3),)*3,{0:1},{1},0)


def test_generic_seed_search_supplies_multiple_root_witness():
    from mic_50_90._hunter.multiple_roots import proposals
    from mic_50_90._hunter import endpoint
    from mic_50_90._hunter.pairwise import HistRegion
    h=(0,2,0,0,1)
    region=HistRegion(3,5,(tuple((j,j+1,c,c) for j,c in enumerate(h)),))
    records=proposals([h],endpoint.baseline_cell(region,F(1,20)),F(1,20))
    first=next(records)
    assert first['histogram']==list(h) and F(first['union_lower'])>=F(1,20)
    for a in range(5):
        lo,hi=endpoint.witness_range(first,a,a+1)
        assert 0<=lo<=hi<=1


def test_repeated_algebraic_certificate_does_not_inflate_retained_result(monkeypatch):
    from mic_50_90._hunter import endpoint
    from mic_50_90._hunter.multiple_roots import certify
    from mic_50_90._hunter.pairwise import HistRegion
    h=(0,2,0,0,1)
    record=certify(h,2,F(77,100),0,{1:2,3:2,4:1},group={2,3})
    assert record
    monkeypatch.setattr(endpoint,'multiple_root_proposals',lambda *args:iter((record,record)))
    monkeypatch.setattr(endpoint,'tied_witness',lambda *args,**kwargs:None)
    monkeypatch.setattr(endpoint,'support_proposals',lambda *args:iter(()))
    region=HistRegion(3,5,(tuple((j,j+1,c,c) for j,c in enumerate(h)),))
    result=endpoint.project(region,time_limit_seconds=1,max_boxes=1)
    retained=[r for r in result['algebraic_witnesses'] if r.get('coefficients')==record['coefficients'] and r.get('u')==record['u']]
    assert len(retained)==1


def test_event_dp_checks_deadline_while_building_integer_powers(monkeypatch):
    from mic_50_90._hunter import multiple_roots as m
    calls=0
    def check(_):
        nonlocal calls
        calls+=1
        if calls>=2:raise TimeoutError('controlled interrupt')
    class GuardWeight:
        powers=0
        def __pow__(self, exponent):
            self.powers+=1
            if self.powers>2:raise AssertionError('Uninterrupted power construction')
            return 1
    monkeypatch.setattr(m,'_check_deadline',check)
    with pytest.raises(TimeoutError):
        m._group_masses(10,[GuardWeight()],[10])
