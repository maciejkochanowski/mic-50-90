import pytest
import mic_50_90
from test_decision_planning import specification, criteria


def plan(*args, **kwargs):
    function = getattr(mic_50_90, 'plan_acquisition', None)
    assert callable(function), 'Public acquisition planner is required'
    return function(*args, **kwargs)


def test_round_cost_changes_next_request():
    sequential = plan(specification(), criteria(), round_cost=0)
    together = plan(specification(), criteria(), round_cost=2)
    assert sequential['worst_case_cost'] == 2
    assert len(sequential['next_questions']) == 1
    assert together['worst_case_cost'] == 5
    assert len(together['next_questions']) == 3
    assert together['optimality_verified']


def test_free_counts_make_one_export_sufficient():
    queries = [dict(threshold=t, unit='mg/L', cost=0) for t in (2,4,8)]
    result = plan(specification(), criteria(), queries=queries, round_cost=1)
    assert result['worst_case_cost'] == 1
    assert len(result['next_questions']) == 3
    assert result['fixed_plan_cost'] == 1


def test_zero_total_cost_terminates():
    result = plan(specification(), criteria(), queries=[
        dict(threshold=t, unit='mg/L', cost=0) for t in (2,4,8)], round_cost=0)
    assert result['worst_case_cost_exact'] == '0'
    assert result['optimality_verified']


def test_returned_counts_resolve_questions_without_another_round():
    result = plan(specification(), criteria(), round_cost=2, additional_counts=[
        dict(threshold=2,unit='mg/L',count=0,n=10)])
    assert result['status'] == 'already_resolved'
    assert result['worst_case_cost'] == 0
    assert result['next_questions'] == []


def test_expired_budget_retains_sufficient_one_export():
    result = plan(specification(), criteria(), round_cost=2, time_limit_seconds=0)
    assert result['status'] == 'incomplete'
    assert not result['optimality_verified']
    assert result['worst_case_cost'] == 5
    assert len(result['next_questions']) == 3


def test_missing_allowed_target_produces_witness():
    result = plan(specification(), criteria(), queries=[], round_cost=1)
    assert result['status'] == 'impossible'
    assert result['impossibility_witness']
    assert result['next_questions'] == []


@pytest.mark.parametrize('cost',[-1,True,None,'nan','inf'])
def test_invalid_round_cost(cost):
    with pytest.raises(ValueError, match='cost'):
        plan(specification(), criteria(), round_cost=cost)


def test_inconsistent_joint_answers_refused():
    with pytest.raises(ValueError):
        plan(specification(),criteria(),additional_counts=[
            dict(threshold=2,unit='mg/L',count=0,n=10),
            dict(threshold=4,unit='mg/L',count=1,n=10)])


def test_timeout_without_incumbent_does_not_claim_saved_request():
    result=plan(specification(),criteria(),queries=[],time_limit_seconds=0)
    assert result['policy'] is None
    assert 'no sufficient request' in result['reason'].lower()


@pytest.mark.parametrize('cost',['1e-400','1e308'])
def test_costs_must_have_finite_faithful_exports(cost):
    with pytest.raises(ValueError,match='cost'):
        plan(specification(),criteria(),round_cost=cost,max_batch_size=1)
