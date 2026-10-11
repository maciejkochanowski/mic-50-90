"""Focused population questions retain the fixed joint region and full outputs."""
from fractions import Fraction as F
from time import monotonic

import numpy as np
import pytest

from mic_50_90.population_questions import certify_questions


QUESTION = dict(cut_index=0, fraction='1/10')


def test_decimal_boundary_is_enclosed_outward_before_rejection():
    seen=[]
    def bound(n, matrices, lo, hi, **kwargs):
        seen.append((lo.copy(),hi.copy()))
        return 0.
    result=certify_questions(5, [], [.88,.9], [.98,.99], [QUESTION],
        alpha=F(1,20), deadline=monotonic()+1, bound=bound)
    assert result[0]['status']=='excluded'
    assert result[0]['tail_relation']=='<'
    assert F(seen[0][1][0]) >= F(9,10)


@pytest.mark.parametrize('error',[TimeoutError,ArithmeticError,MemoryError])
def test_failure_keeps_question_unresolved(error):
    def fail(*args,**kwargs):raise error('injected')
    result=certify_questions(5, [], [.8,.9], [.95,.99], [QUESTION],
        alpha=F(1,20),deadline=monotonic()+1,bound=fail)
    assert result[0]['status']=='unresolved'
    assert result[0]['remaining_boxes']==1


def test_expired_budget_is_not_a_certificate():
    result=certify_questions(5, [], [.8,.9], [.95,.99], [QUESTION],
        alpha=F(1,20),deadline=monotonic()-1,bound=lambda *a,**kw:0)
    assert result[0]['status']=='unresolved'


def test_workflow_supplies_questions_and_preserves_all_distribution_outputs():
    from mic_50_90.distribution_workflow import analyse_distribution
    raw=dict(n=20,unit='mg/L',iid=True,panel={'levels':[1,2]},additional_counts=[
        dict(threshold=1,count=8,n=20,unit='mg/L'),dict(threshold=2,count=2,n=20,unit='mg/L')],
        targets=[dict(threshold=2,unit='mg/L',decision_operator='<',decision_fraction='.348')])
    result=analyse_distribution(raw,population_method='joint-exact',population_time_limit=3)
    assert result['sample']['status']=='complete'
    assert len(result['population']['categories'])==3
    assert len(result['population']['cdf'])==2
    search=result['population']['question_certificates']
    assert search and search[0]['fraction']=='87/250'
    assert result['population']['requested_method']=='joint-exact'
    decision=result['decisions'][0]['population']
    assert decision['status']=='supported'
    assert decision['decision_certificate']['status']=='excluded'
    assert decision['decision_certificate']['constraint_signature']==result['population']['constraint_signature']


def test_invalid_cut_is_rejected():
    with pytest.raises(ValueError,match='cut'):
        certify_questions(5, [], [.8,.9], [.95,.99], [dict(cut_index=2,fraction='.1')],
            alpha=F(1,20),deadline=monotonic()+1,bound=lambda *a,**kw:0)


def test_equality_to_rejection_level_cannot_certify_exclusion():
    # A point box cannot split. Equality must remain in the region.
    result = certify_questions(5, [], [.5], [.5],
        [dict(cut_index=0, fraction='1/2')], alpha=F(1,2),
        deadline=monotonic()+1, bound=lambda *a, **kw: .5)
    assert result[0]['status'] == 'unresolved'
    assert result[0]['remaining_boxes'] == 1


def test_completed_trace_covers_every_child_and_replays_box_bound():
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICBin, MICPanel
    from mic_50_90.joint_population import population_distribution, box_pvalue_upper
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in (1,2,3)))
    p = EmpiricalProblem(n=20, panel=panel, quantiles=[], count_intervals=[
        (np.array([1.,0.,0.]),12,12), (np.array([0.,1.,0.]),6,6)])
    result = population_distribution({'a':p}, method='joint-exact',
        time_limit_seconds=2, questions=[dict(cut_index=1,fraction='87/250')])
    cert = result['question_certificates'][0]
    assert cert['status'] == 'excluded'
    nodes = {0: (cert['initial_box']['cdf_lower'], cert['initial_box']['cdf_upper'])}
    consumed = set()
    # Replay topology independently, rather than trusting a leaf count.
    events = {x['node']: ('split', x) for x in cert['splits']}
    for leaf in cert['excluded_boxes']:
        assert leaf['node'] not in events
        events[leaf['node']] = ('exclude', leaf)
    while nodes:
        node, (lower, upper) = nodes.popitem()
        assert node not in consumed
        consumed.add(node)
        kind, event = events[node]
        if kind == 'exclude':
            assert lower == event['cdf_lower'] and upper == event['cdf_upper']
            assert F(event['pvalue_upper']) < F(cert['alpha_fraction'])
            assert F(box_pvalue_upper({'a':p}, lower, upper)) < F(cert['alpha_fraction'])
            continue
        dim, cut = event['dimension'], event['cut']
        assert lower[dim] < cut < upper[dim]
        assert len(event['children']) == 2
        for right, child in enumerate(event['children']):
            lo, hi = list(lower), list(upper)
            (lo if right else hi)[dim] = cut
            lo = [max(lo[:j+1]) for j in range(len(lo))]
            hi = [min(hi[j:]) for j in range(len(hi))]
            empty = any(a>b for a,b in zip(lo,hi))
            assert child['empty'] == empty
            if not empty:
                assert child['node'] not in nodes and child['node'] not in consumed
                nodes[child['node']] = (lo,hi)
    assert consumed == set(events)


@pytest.mark.parametrize('changed,value', [
    ('constraint_signature','different-data'), ('method','bonferroni'),
    ('confidence_level',.9), ('status','unresolved'), ('fraction','1/3')])
def test_incompatible_certificate_cannot_resolve_question(changed,value):
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICBin, MICPanel
    from mic_50_90.joint_population import _constraint_signature
    from mic_50_90.distribution_decisions import distribution_decisions
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in (1,2,3)))
    problems = {'a': EmpiricalProblem(n=5,panel=panel,quantiles=[])}
    raw = {'targets':[dict(threshold=2,unit='mg/L',decision_operator='<',decision_fraction='.5')]}
    cert = dict(status='excluded',cut_index=1,fraction='1/2',method='joint-exact',
        confidence_level=.95,constraint_signature=_constraint_signature(problems),tail_relation='<')
    layer = dict(method='joint-exact',confidence_level=.95,
        cdf=[dict(lower=0,upper=1),dict(lower=0,upper=1)],question_certificates=[cert])
    assert distribution_decisions(raw,problems,layer,{})[0]['population']['status']=='supported'
    cert[changed] = value
    assert distribution_decisions(raw,problems,layer,{})[0]['population']['status']=='undetermined'
