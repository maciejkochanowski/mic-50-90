"""Quadratic trinomial shortcut for nested/disjoint MIC range counts.

At least one of the four membership probabilities must be a structural zero.
The generic four-corner recurrence remains the fallback. No independence of
the two overlapping counts is introduced.
"""
from fractions import Fraction as F
from functools import lru_cache
from math import comb,lcm
import numpy as np
from . import pairwise as original


def corners(q):
    active=[j for j,v in enumerate(q) if v]
    if len(active)>3:return None
    active += [j for j in range(4) if j not in active][:3-len(active)]
    return tuple(active)


@lru_cache(maxsize=32)
def geometry(n,states):
    i,j=np.tril_indices(n+1)
    # tril produces (total, second); use counts (first, second, remainder).
    a=i-j;b=j;c=n-i
    x=a*(states[0]&1)+b*(states[1]&1)+c*(states[2]&1)
    y=a*(states[0]>>1)+b*(states[1]>>1)+c*(states[2]>>1)
    coefficients=tuple(comb(n,int(u))*comb(n-int(u),int(v)) for u,v in zip(a,b))
    lo=[];hi=[]
    for coefficient in coefficients:
        value=float(coefficient);actual=F(value)
        lo.append(np.nextafter(value,-np.inf) if actual>coefficient else value)
        hi.append(np.nextafter(value,np.inf) if actual<coefficient else value)
    return a,b,c,x,y,np.asarray(lo),np.asarray(hi),coefficients


def power_bounds(n,low,high):
    lo=np.ones(n+1);hi=np.ones(n+1)
    for r in range(1,n+1):
        lo[r]=original._out_product(lo[r-1:r],low,False)[0]
        hi[r]=original._out_product(hi[r-1:r],high,True)[0]
    return lo,hi


def box(n,lower,upper,*,deadline=None):
    n=original._integer(n,'n',1)
    lower=tuple(map(original._fraction,lower));upper=tuple(map(original._fraction,upper))
    if len(lower)!=4 or len(upper)!=4 or any(not 0<=a<=b<=1 for a,b in zip(lower,upper)):
        raise ValueError('four valid membership probability intervals required')
    if sum(lower)>1 or sum(upper)<1:raise ValueError('membership box misses the simplex')
    original._check_deadline(deadline)
    states=corners(upper)
    if states is None or n>500:
        return original.pair_count_distribution_box_bounds(n,lower,upper,deadline=deadline)
    a,b,c,x,y,cl,ch,_=geometry(n,states)
    lower_value=cl.copy();upper_value=ch.copy()
    for state,counts in zip(states,(a,b,c)):
        original._check_deadline(deadline)
        qlo=original._float_interval(lower[state])[0]
        qhi=original._float_interval(upper[state])[1]
        pl,ph=power_bounds(n,qlo,qhi)
        lower_value=original._out_product(lower_value,pl[counts],False)
        upper_value=original._out_product(upper_value,ph[counts],True)
    low=np.zeros((n+1,n+1));high=np.zeros_like(low)
    low[x,y]=np.minimum(1.,lower_value);high[x,y]=np.minimum(1.,upper_value)
    low.setflags(write=False);high.setflags(write=False)
    return low,high


def bounds(n,q,*,deadline=None):
    q=original._probabilities(q,4)
    if len(q)!=4:raise ValueError('four membership probabilities required')
    if corners(q) is None:return original.pair_count_distribution_bounds(n,q,deadline=deadline)
    return box(n,q,q,deadline=deadline)


def exact(n,q):
    original._check_deadline(None)
    n=original._integer(n,'n',1);q=original._probabilities(q,4)
    if len(q)!=4:raise ValueError('four membership probabilities required')
    states=corners(q)
    if states is None or n>500:return original.pair_count_distribution_exact(n,q)
    a,b,c,x,y,_,_,coefficients=geometry(n,states)
    denominator=lcm(*(v.denominator for v in q))
    weights=[int(q[j]*denominator) for j in states]
    powers=[]
    for weight in weights:
        values=[1]
        for _ in range(n):values.append(values[-1]*weight)
        powers.append(values)
    common=denominator**n;cells=[[F(0)]*(n+1) for _ in range(n+1)]
    for index,(u,v,w,i,j,coefficient) in enumerate(zip(a,b,c,x,y,coefficients)):
        if index%128==0:original._check_deadline(None)
        cells[i][j]=F(coefficient*powers[0][u]*powers[1][v]*powers[2][w],common)
    return tuple(map(tuple,cells))
