from copy import deepcopy

import pytest
import mic_50_90
from test_decision_planning import specification, criteria


def plan(histogram, **kwargs):
    function = getattr(mic_50_90, 'plan_reporting', None)
    assert callable(function), 'The laboratory needs a sufficient-report planner'
    return function(specification(), histogram, criteria(), **kwargs)


def verify(spec, decisions, counts):
    function = getattr(mic_50_90, 'verify_reporting', None)
    assert callable(function), 'The recipient needs a check without the source histogram'
    return function(spec, decisions, counts)


def test_observed_report_uses_two_boundary_counts_and_recipient_can_verify():
    result = plan([5, 4, 1, 0, 0])
    assert result['status'] == 'optimal'
    assert result['report_cost'] == 2
    assert result['optimality_verified']
    assert [r['threshold'] for r in result['disclosures']] == [2, 4]
    assert [r['count'] for r in result['disclosures']] == [1, 0]
    checked = verify(specification(), criteria(), result['disclosures'])
    assert checked['sufficient']
    assert checked['decisions'] == ['contradicted', 'supported', 'supported']
    for omitted in range(2):
        reduced = result['disclosures'][:omitted] + result['disclosures'][omitted+1:]
        assert not verify(specification(), criteria(), reduced)['sufficient']


@pytest.mark.parametrize('histogram', [[5,5,0,0,0],[5,4,0,0,1]])
def test_one_side_needs_only_one_count(histogram):
    result = plan(histogram)
    assert result['report_cost'] == 1
    assert len(result['disclosures']) == 1


def test_weights_and_free_counts_are_used_exactly():
    result = plan([5,4,1,0,0], queries=[
        {'threshold':t,'unit':'mg/L','cost':c} for t,c in [(2,'0.1'),(4,'0'),(8,'5')]])
    assert result['report_cost_exact'] == '1/10'
    assert [r['threshold'] for r in result['disclosures']] == [2,4]


def test_forbidden_counts_and_timeout_do_not_claim_optimum():
    unavailable = plan([5,4,1,0,0], queries=[])
    assert unavailable['status'] == 'impossible'
    assert not unavailable['sufficient']
    interrupted = plan([5,4,1,0,0], time_limit_seconds=0)
    assert interrupted['status'] == 'incomplete'
    assert interrupted['sufficient'] and not interrupted['optimality_verified']
    assert verify(specification(), criteria(), interrupted['disclosures'])['sufficient']


@pytest.mark.parametrize('histogram', [[5,4,0,0,0],[True,4,1,0,4],[0,0,0,0,10],[5,4,-1,1,1],[5,4,.5,.5,0]])
def test_invalid_or_incompatible_histogram_is_rejected(histogram):
    with pytest.raises(ValueError):
        plan(histogram)


def test_population_mode_cannot_be_used_as_empirical_report():
    raw = specification(); raw['mode'] = 'population'
    function = getattr(mic_50_90, 'plan_reporting', None)
    assert callable(function)
    with pytest.raises(ValueError, match='empirical'):
        function(raw, [5,4,1,0,0], criteria())


def test_general_variant_union_keeps_joint_information():
    histograms=[(0,1,1,1),(0,2,1,0),(1,1,0,1),(1,0,2,0)]
    summaries=[]
    for h in histograms:
        ordered=[str(2**j) for j,c in enumerate(h) for _ in range(c)]
        summaries.append({'minimum':ordered[0],'quantiles':[
            {'probability':.5,'rank':2,'category':ordered[1]},
            {'probability':.9,'rank':3,'category':ordered[2]}]})
    raw=specification(3,4);raw['summaries']=summaries[0]
    raw['reporting_envelope']={'variants':[{'id':str(j),'summaries':s} for j,s in enumerate(summaries[1:])]}
    questions=criteria((2,),'.5','<=')
    function=getattr(mic_50_90,'plan_reporting',None);assert callable(function)
    result=function(raw,histograms[0],questions,queries=[
        {'threshold':t,'unit':'mg/L','cost':c} for t,c in [(1,1),(2,3),(4,1)]])
    assert result['report_cost']==2 and result['optimality_verified']
    assert verify(raw,questions,result['disclosures'])['sufficient']
    assert not verify(raw,questions,result['disclosures'][:1])['sufficient']


def test_recipient_rejects_wrong_denominator_and_conflicting_counts():
    result=plan([5,4,1,0,0]);rows=deepcopy(result['disclosures'])
    rows[0]['n']=11
    with pytest.raises(ValueError):verify(specification(),criteria(),rows)
    with pytest.raises(ValueError):verify(specification(),criteria(),[
        {'threshold':2,'unit':'mg/L','count':0,'n':10},
        {'threshold':4,'unit':'mg/L','count':1,'n':10}])
