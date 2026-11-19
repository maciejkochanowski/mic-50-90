"""Boundary and equivalence tests for input contracts, planners, the MILP certificate and exports."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.stats import chi2

from mic_50_90.model import MICPanel, QuantileSummary, parse_spec
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.population import fit_population_mle, profile_likelihood, _group_probabilities
from mic_50_90.decision_planning import plan_decisions
from mic_50_90.acquisition import plan_acquisition

FIXTURES = Path(__file__).parent / 'fixtures/contracts'
def test_count_encodings_give_same_nontrivial_plan_without_mutation():
    raw={'n':20,'panel':{'levels':[1,2,4,8],'left_censored':False,'right_censored':False},
         'summaries':{'quantiles':[{'probability':.5,'category':'2','convention':'ceiling'},
                                  {'probability':.9,'category':'8','convention':'ceiling'}]},'thresholds':[4]}
    criteria=[{'threshold':4,'unit':'mg/L','decision_operator':'<','decision_fraction':'.25'}]
    base={'n':20,'unit':'mg/L'}
    rows=[{'threshold':2,'count':8}, {'threshold':2,'count':8,'source_scale':'recorded'},
          {'threshold':2,'count':12,'source_scale':'recorded','relation':'<='},
          {'start_category':'4','end_category':'8','count':8},
          {'threshold':2,'count_min':8,'count_max':8,'source_scale':'recorded'},
          {'threshold':2,'percentage':'40','decimal_places':0,'rounding_rule':'half_up','source_scale':'recorded'}]
    for planner in [plan_decisions,plan_acquisition]:
        results=[]
        for row in rows:
            item={**base,**row}; original=deepcopy(item)
            r=planner(raw,criteria,additional_counts=[item])
            results.append({k:r.get(k) for k in ['status','worst_case_cost','next_question','next_questions']})
            assert item==original
        assert all(r==results[0] for r in results)
        assert results[0]['status']=='optimal'
        assert results[0]['worst_case_cost']==1

@pytest.mark.parametrize('scale',[1e-12,1e-8,1e8,1e300,-1e-8])
def test_milp_scaled_witness_and_dual_bounds(scale):
    panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
    p=EmpiricalProblem(n=3,panel=panel,quantiles=[],equalities=[(np.array([scale,0.]),0)])
    for maximize in [False,True]:
        b=p._solve_milp_oracle(np.array([-1.,2.]),maximize=maximize)
        assert b.histogram==(0,3)
        assert b.count==6
        assert b.certificate.dual_objective==pytest.approx(6)
        assert b.certificate.duality_gap <= 1e-7
        assert b.certificate.optimality_verified

@pytest.mark.parametrize('field,value',[('mip_gap',None),('mip_gap',float('nan')),('mip_dual_bound',None),('mip_dual_bound',float('nan'))])
def test_milp_missing_or_nonfinite_diagnostics_never_certify(monkeypatch,field,value):
    import mic_50_90.empirical as module
    panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
    p=EmpiricalProblem(n=3,panel=panel,quantiles=[])
    original=module.milp
    def malformed(*args,**kwargs):
        r=original(*args,**kwargs); r[field]=value; return r
    monkeypatch.setattr(module,'milp',malformed)
    with pytest.raises(RuntimeError,match='diagnostics'):
        p._solve_milp_oracle(np.array([1.,0.]))

def test_milp_integrality_is_checked_before_rounding(monkeypatch):
    import mic_50_90.empirical as module
    panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
    p=EmpiricalProblem(n=3,panel=panel,quantiles=[])
    monkeypatch.setattr(module,'milp',lambda **kw: SimpleNamespace(
        x=np.array([1.25,1.75]),success=True,status=0,fun=0.,mip_gap=0.,mip_dual_bound=0.,message='fake'))
    with pytest.raises(RuntimeError,match='invalid histogram'):
        p._solve_milp_oracle(np.array([0.,0.]))

def test_zero_mass_group_keeps_parameter_offsets():
    p=_group_probabilities(np.log([2.,3.,4.]),non_tail_indices=np.array([0,1,2]),
                           tail_indices=np.array([3,4]),theta=1.,k=5)
    np.testing.assert_allclose(p,[0,0,0,.8,.2],rtol=0,atol=1e-15)

@pytest.mark.parametrize('category',[0,1])
def test_profile_at_boundary_matches_exact_likelihood_cutoff(category):
    q=(QuantileSummary(.5, 10 if category==0 else 1, category, str(category+1)),)
    m=fit_population_mle(k=2,n=10,quantiles=q,minimum_index=None,maximum_index=None)
    assert m.success
    r=profile_likelihood(mle=m,tail=np.array([0.,1.]),n=10,quantiles=q,minimum_index=None,maximum_index=None,grid_size=11)
    extent=1-np.exp(-chi2.ppf(.95,1)/20)
    expected=[0.,extent] if category==0 else [1-extent,1.]
    np.testing.assert_allclose([r.confidence_set_lower,r.confidence_set_upper],expected,rtol=0,atol=1e-8)
    assert r.boundary_or_weak_identification_warning
    assert 'zero_event_probability' in r.evaluation_status
    assert all(e['bracket_width']<=r.endpoint_tolerance for e in r.endpoint_diagnostics)
    json.dumps(r.as_dict(),allow_nan=False)

def test_profile_rejects_an_inconsistent_supplied_peak():
    s=parse_spec(json.loads((FIXTURES/'case_audit_unit.json').read_text()))
    m=fit_population_mle(k=2,n=s.n,quantiles=s.quantiles,minimum_index=s.minimum_index,maximum_index=s.maximum_index)
    with pytest.raises(RuntimeError,match='exceeds the supplied MLE'):
        profile_likelihood(mle=replace(m,log_likelihood=m.log_likelihood-.1),tail=np.array([0.,1.]),
                           n=s.n,quantiles=s.quantiles,minimum_index=s.minimum_index,maximum_index=s.maximum_index,grid_size=11)

@pytest.mark.parametrize('coefficients', [[1.,1e-8],[1e16,1.]])
def test_milp_mixed_scale_equalities_cannot_certify_an_invalid_integer_witness(coefficients):
    panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
    # Neither row has an integer solution under h0+h1=3. Row normalisation
    # alone makes the violation smaller than the solver's feasibility tolerance.
    with pytest.raises((ValueError,RuntimeError)):
        p=EmpiricalProblem(n=3,panel=panel,quantiles=[],equalities=[(np.array(coefficients),1)])
        p.bounds(np.array([1.,0.]))

def test_milp_decimal_fractional_equality_remains_usable():
    panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
    p=EmpiricalProblem(n=10,panel=panel,quantiles=[],equalities=[(np.array([.1,0.]),1)])
    lo,hi=p.bounds(np.array([1.,0.]))
    assert lo.histogram==hi.histogram==(10,0)

def test_profile_html_preserves_detected_components_and_endpoint_method():
    from mic_50_90 import analyse_spec
    from mic_50_90.report import result_sections
    from mic_50_90.population import ProfileLikelihoodResult
    raw=json.loads((FIXTURES/'case_audit_unit.json').read_text())
    raw['population'].update(profile_likelihood_enabled=False,bayes_enabled=False)
    result=analyse_spec(raw)
    profile=ProfileLikelihoodResult((0.,.1,.9), (None,-1.,-1.), (None,0.,0.), .95,3.8415,
        .1,.9,'Wilks-cutoff sensitivity',confidence_set_components=((.1,.2),(.8,.9)),
        evaluation_status=('zero_event_probability','finite','finite'),
        endpoint_method='classification bisection',endpoint_tolerance=1e-9)
    result['threshold_results'][0]['optional_efficiency_analysis']={
        'enabled':True,'available':True,'population_tail_mle':.1,'profile_likelihood':profile.as_dict()}
    text=result_sections(result)
    assert '10.00% to 20.00% ∪ 80.00% to 90.00%' in text
    assert 'classification bisection' in text
    assert 'zero_event_probability' in text


def test_profile_nan_is_optimizer_failure_not_zero_event(monkeypatch):
    import mic_50_90.population as population
    mle = population.PopulationMLE((.5,.5), -1., True, 'fixture', 1)
    monkeypatch.setattr(population, 'log_order_event_probability', lambda *a, **kw: float('nan'))
    with pytest.raises(RuntimeError, match='non-finite support'):
        population.profile_likelihood(mle=mle, tail=np.array([0,1]), n=20, quantiles=[],
            minimum_index=None,maximum_index=None,grid_size=11)


def test_paginated_report_writes_its_checksum_directory(tmp_path):
    from mic_50_90 import analyse_spec
    from mic_50_90.report import render_batch_html
    raw=json.loads((FIXTURES/'case_audit_unit.json').read_text())
    raw['mode']='empirical';raw['question_utility']={'enabled':False};raw.pop('population',None)
    result=analyse_spec(raw)
    out=tmp_path/'output';out.mkdir()
    records=[dict(cohort_id=str(i),status='ok',result=result,runtime_seconds=0.) for i in range(2)]
    render_batch_html(records,{'version':'1.0.0'},out/'report.html',page_size=1)
    checksum=next(out.rglob('checksums.sha256'))
    assert checksum.parent.name.startswith('report-pages-')
