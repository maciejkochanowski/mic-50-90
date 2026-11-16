"""Public/core API mapping only; all oracle mathematics remain independent."""
from fractions import Fraction
import numpy as np

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import parse_spec


def problems_for(n, k, rank_categories, prefix_count=None, histogram=None):
    problems=[]
    if histogram is not None:
        rank_categories=[None]
    for pair in rank_categories:
        raw=dict(n=n, panel=dict(levels=[2**j for j in range(k)],left_censored=False,right_censored=False),
                 summaries={'quantiles':[]},thresholds=[1])
        if pair is not None:
            raw['summaries']['quantiles']=[dict(probability=q,category=str(2**j),convention='ceiling')
                                         for q,j in zip((.5,.9),pair)]
        # parse_spec's documented summary contract requires a quantile. A full
        # histogram can use its true MIC50; equalities fix every coordinate.
        if histogram is not None:
            sample=[j for j,h in enumerate(histogram) for _ in range(h)]
            raw['summaries']['quantiles']=[dict(probability=.5,category=str(2**sample[(n+1)//2-1]),convention='ceiling')]
        spec=parse_spec(raw)
        equalities=[]
        if histogram is not None:
            for j in range(1,k):
                equalities.append((np.array([int(i<j) for i in range(k)]),sum(histogram[:j])))
        elif prefix_count is not None:
            equalities.append((np.array([1]+[0]*(k-1)),prefix_count))
        problems.append(EmpiricalProblem(n=n,panel=spec.panel,quantiles=spec.quantiles,equalities=equalities))
    return {f'variant-{index}':problem for index,problem in enumerate(problems)}


def cumulative(probabilities):
    result=[]
    running=Fraction(0)
    for p in probabilities[:-1]:
        running+=Fraction(p)
        result.append(float(running))
    return result
