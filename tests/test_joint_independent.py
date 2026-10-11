"""Joint law and incomplete observations checked against rational enumeration."""
import importlib.util
from fractions import Fraction
from pathlib import Path
from math import comb

import numpy as np
import pytest

from mic_50_90.joint_population import (
    joint_minp_probability, joint_report_pvalue, max_compatible_statistic,
    rectangle_probability_bounds, box_pvalue_upper,
    _cp_outer, _functional_bounds, _point_lower,
)
from mic_50_90.utility import _prefix_distances

ROOT=Path(__file__).resolve().parents[1]
CAMPAIGN=ROOT/'reproducibility/v1.0.0/joint-distribution-20260930'


def load_file(name):
    spec=importlib.util.spec_from_file_location('independent_joint_'+name,CAMPAIGN/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oracle=load_file('oracle')
adapter=load_file('production_adapter')


@pytest.mark.parametrize('probabilities',[
    ('1/2','1/2'), ('0','1'), ('1/3','1/3','1/3'),
    ('1/5','3/10','1/2'), ('0','2/5','3/5'), ('1','0','0'),
    ('1/4','1/4','1/4','1/4'), ('1/100','1/100','97/100','1/100'),
])
def test_exact_joint_law_matches_every_rational_histogram(probabilities):
    null=oracle.exact_null(5,probabilities)
    cdf=adapter.cumulative(probabilities)
    for score,expected in zip(null['statistic'],null['minp']):
        actual=joint_minp_probability(5,cdf,float(score))
        assert actual==pytest.approx(float(expected),abs=2e-10,rel=0)


@pytest.mark.parametrize('probabilities',oracle.NULLS[3])
def test_summary_union_and_truthful_counts_preserve_joint_feasibility(probabilities):
    null=oracle.exact_null(5,probabilities)
    groups=oracle.group_indices(null)
    keys=sorted(groups)
    for j,pair in enumerate(keys):
        cases=[([pair],groups[pair],None)]
        if j+1<len(keys):
            other=keys[j+1]
            cases.append(([pair,other],groups[pair]+groups[other],None))
        observed=null['histograms'][groups[pair][0]][0]
        cases.append(([pair],[i for i in groups[pair] if null['histograms'][i][0]==observed],observed))
        for pairs,indices,count in cases:
            problems=adapter.problems_for(5,3,pairs,prefix_count=count)
            statistic=max(null['statistic'][i] for i in indices)
            expected=max(null['minp'][i] for i in indices)
            assert max_compatible_statistic(problems,adapter.cumulative(probabilities))==pytest.approx(float(statistic),abs=2e-10,rel=0)
            actual=joint_report_pvalue(problems,[float(Fraction(p)) for p in probabilities])
            assert actual==pytest.approx(float(expected),abs=2e-10,rel=0)


def test_known_histogram_reduces_to_full_observation():
    probabilities=('1/5','3/10','1/2')
    null=oracle.exact_null(5,probabilities)
    for histogram in [(0,0,5),(1,2,2),(5,0,0)]:
        index=null['histograms'].index(histogram)
        problems=adapter.problems_for(5,3,[],histogram=histogram)
        actual=joint_report_pvalue(problems,[float(Fraction(p)) for p in probabilities])
        assert actual==pytest.approx(float(null['minp'][index]),abs=2e-10,rel=0)


@pytest.mark.parametrize('n',[2,5,10])
@pytest.mark.parametrize('cdf',[(.1,.6),(.25,.5,.75),(0.,.5,1.),(.5,.5)])
def test_directed_rectangle_contains_exact_binary64_null_probability(n,cdf):
    # The production contract treats binary64 coordinates as exact rationals.
    f=[Fraction.from_float(p) for p in cdf]
    probabilities=[b-a for a,b in zip([Fraction(0),*f],[*f,Fraction(1)])]
    null=oracle.exact_null(n,probabilities)
    for lower,upper in [([0]*len(f),[n]*len(f)),([n//3]*len(f),[(2*n)//3]*len(f)),
                        ([0]*len(f),[0]*len(f)),([n]*len(f),[n]*len(f))]:
        exact=sum((mass for h,mass in zip(null['histograms'],null['masses'])
                   if all(lo<=sum(h[:j+1])<=hi for j,(lo,hi) in enumerate(zip(lower,upper)))),Fraction(0))
        lo,hi=rectangle_probability_bounds(n,cdf,lower,upper)
        assert Fraction.from_float(lo)<=exact<=Fraction.from_float(hi)


@pytest.mark.parametrize('histogram',[(0,0,5),(1,2,2),(2,2,1),(5,0,0)])
def test_uniform_box_upper_dominates_exact_values_at_all_dyadic_grid_points(histogram):
    problems=adapter.problems_for(5,3,[oracle.summary_pair(histogram)])
    lower=(.125,.5);upper=(.5,.875)
    bound=Fraction.from_float(box_pvalue_upper(problems,lower,upper))
    for first in (Fraction(1,8),Fraction(5,16),Fraction(1,2)):
        for second in (Fraction(1,2),Fraction(11,16),Fraction(7,8)):
            null=oracle.exact_null(5,(first,second-first,1-second))
            indices=oracle.group_indices(null)[oracle.summary_pair(histogram)]
            exact=max(null['minp'][i] for i in indices)
            assert exact<=bound


@pytest.mark.parametrize('n',[0,-1,1.5,True])
def test_invalid_sample_size_is_rejected(n):
    with pytest.raises(ValueError):joint_minp_probability(n,[.5],.05)


@pytest.mark.parametrize('cdf',[[],[-.1],[1.1],[.8,.2],[float('nan')]])
def test_invalid_candidate_cdf_is_rejected(cdf):
    with pytest.raises(ValueError):joint_minp_probability(5,cdf,.05)


def test_derived_category_bounds_round_outward():
    lower=np.array([.01,.2]);upper=np.array([.4,.9])
    lo,hi=_functional_bounds(lower,upper)
    exact_upper=Fraction.from_float(.9)-Fraction.from_float(.01)
    exact_lower=max(Fraction(0),Fraction.from_float(.2)-Fraction.from_float(.4))
    assert Fraction.from_float(hi[3])>=exact_upper
    assert Fraction.from_float(lo[3])<=exact_lower


@pytest.mark.parametrize('n',[2,5,10])
def test_cp_outer_brackets_exact_tail_equations(n):
    alpha=Fraction(1,60)
    for count in range(n+1):
        lo,hi=_cp_outer(count,n,alpha)
        for x,side in [(lo,'lower'),(hi,'upper')]:
            p=Fraction.from_float(x)
            masses=[comb(n,j)*p**j*(1-p)**(n-j) for j in range(n+1)]
            if side=='lower' and count>0:assert sum(masses[count:])<=alpha/2
            if side=='upper' and count<n:assert sum(masses[:count+1])<=alpha/2


@pytest.mark.parametrize('histogram',[(0,0,5),(1,2,2),(2,2,1),(5,0,0)])
def test_certified_point_witness_never_exceeds_exact_report_pvalue(histogram):
    problems=adapter.problems_for(5,3,[oracle.summary_pair(histogram)])
    matrices=[_prefix_distances(p) for p in problems.values()]
    for cdf in [(.1,.6),(.25,.5),(.5,.5),(0.,1.)]:
        f=[Fraction.from_float(x) for x in cdf]
        null=oracle.exact_null(5,(f[0],f[1]-f[0],1-f[1]))
        indices=oracle.group_indices(null)[oracle.summary_pair(histogram)]
        exact=max(null['minp'][i] for i in indices)
        assert Fraction.from_float(_point_lower(5,matrices,np.array(cdf),None))<=exact


@pytest.mark.parametrize('probabilities',[[.5,.5],[.2,.3,.4],[-.1,.5,.6],[0.,float('nan'),1.],[[.2,.3,.5]]])
def test_invalid_category_probability_vector_is_rejected(probabilities):
    problems=adapter.problems_for(5,3,[],histogram=[1,2,2])
    with pytest.raises(ValueError):joint_report_pvalue(problems,probabilities)


@pytest.mark.parametrize('change',[
    {'unit':'g/L'}, {'n':6}, {'count':6},
])
def test_public_distribution_rejects_wrong_units_denominator_or_count(change):
    from mic_50_90.distribution_workflow import distribution_problems
    count=dict(threshold=1,unit='mg/L',n=5,count=4)
    count.update(change)
    raw=dict(n=5,unit='mg/L',panel=dict(levels=[1,2,4],left_censored=False,right_censored=False),
             additional_counts=[count])
    with pytest.raises(ValueError):distribution_problems(raw)


def test_public_distribution_rejects_summary_count_contradiction():
    from mic_50_90.distribution_workflow import distribution_problems
    raw=dict(n=5,unit='mg/L',panel=dict(levels=[1,2,4],left_censored=False,right_censored=False),
             summaries={'quantiles':[dict(probability=.5,category='1',convention='ceiling')]},
             additional_counts=[dict(threshold=1,unit='mg/L',n=5,count=5)])
    with pytest.raises(ValueError):distribution_problems(raw)
