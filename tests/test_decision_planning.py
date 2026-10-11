"""Decision costs and witnesses are derived from explicit small histogram sets."""
from fractions import Fraction

import pytest
import mic_50_90


def planner(*args, **kwargs):
    function = getattr(mic_50_90, "plan_decisions", None)
    assert callable(function), "The public decision planner must be available"
    return function(*args, **kwargs)


def specification(n=10, k=5):
    return {"n": n, "panel": {"levels": [2**j for j in range(k)],
                              "left_censored": False, "right_censored": False},
            "summaries": {"quantiles": [
                {"probability": .5, "category": "1", "rank": (n+1)//2},
                {"probability": .9, "category": "2", "rank": (9*n+9)//10}]},
            "thresholds": [2, 4, 8], "question_utility": {"enabled": False}}


def criteria(thresholds=(2, 4, 8), fraction=".05", op="<"):
    return [{"threshold": t, "unit": "mg/L", "decision_operator": op,
             "decision_fraction": fraction} for t in thresholds]


def test_common_boundary_needs_two_adaptive_counts_instead_of_three():
    result = planner(specification(), criteria())
    assert result["status"] == "optimal"
    assert result["worst_case_cost"] == 2
    assert result["fixed_plan_cost"] == 3
    assert result["next_question"]["threshold"] == 4
    assert result["scope"] == "recorded_sample_decisions"
    assert result["optimality_verified"]


def test_one_mandatory_expensive_direct_count_cannot_be_replaced():
    result = planner(specification(), criteria((4,)), queries=[
        {"threshold": t, "unit": "mg/L", "cost": str(c)}
        for t, c in [(1, .1), (2, .1), (4, 7), (8, .1)]])
    assert result["worst_case_cost"] == 7
    assert result["next_question"]["threshold"] == 4
    assert result["optimality_verified"]


def test_cheap_intermediate_query_can_reduce_weighted_cost():
    result = planner(specification(), criteria((2, 8)), queries=[
        {"threshold": t, "unit": "mg/L", "cost": c}
        for t, c in [(2, 10), (4, 1), (8, 10)]])
    assert result["worst_case_cost"] == 11
    assert result["fixed_plan_cost"] == 20
    assert result["next_question"]["threshold"] == 4


def test_no_questions_needed_when_every_criterion_already_resolved():
    result = planner(specification(), criteria(fraction=".1", op="<="))
    assert result["status"] == "already_resolved"
    assert result["worst_case_cost"] == 0
    assert result["next_question"] is None


def test_impossibility_witness_has_same_allowed_answers_and_opposite_decisions():
    result = planner(specification(), criteria((4,)), queries=[
        {"threshold": t, "unit": "mg/L", "cost": 1} for t in (1, 2, 8)])
    assert result["status"] == "impossible"
    left, right = [row["histogram"] for row in result["impossibility_witness"]["states"]]
    assert sum(left) == sum(right) == 10
    for cut in (1, 2, 4):
        assert sum(left[cut:]) == sum(right[cut:])
    assert (sum(left[3:]) == 0) != (sum(right[3:]) == 0)
    for histogram in (left, right):
        ordered = [j for j, count in enumerate(histogram) for _ in range(count)]
        assert ordered[4] == 0 and ordered[8] == 1


def test_empty_query_whitelist_is_not_replaced_by_defaults():
    assert planner(specification(), criteria(), queries=[])["status"] == "impossible"


def test_truthful_returned_count_reduces_remaining_plan_and_preserves_denominator():
    result = planner(specification(), criteria(), additional_counts=[
        {"threshold": 4, "unit": "mg/L", "count": 0, "n": 10}])
    assert result["worst_case_cost"] == 1
    assert result["next_question"]["threshold"] == 2
    assert result["sample_size"] == 10


def test_strict_decimal_boundary_uses_exact_arithmetic():
    spec = specification(n=11)
    result = planner(spec, criteria((2,), fraction="0.090909090909090905", op="<="))
    assert result["status"] == "optimal"
    assert result["criteria"][0]["initial_status"] == "undetermined"
    assert Fraction("0.090909090909090905") < Fraction(1, 11)


@pytest.mark.parametrize("cost", [0, -1, "nan", "inf", True, None])
def test_bad_cost_is_refused(cost):
    with pytest.raises(ValueError, match="cost"):
        planner(specification(), criteria(), queries=[{"threshold": 2, "unit": "mg/L", "cost": cost}])


def test_time_exhaustion_does_not_claim_optimality_or_impossibility():
    result = planner(specification(), criteria(), time_limit_seconds=0)
    assert result["status"] == "incomplete"
    assert not result["optimality_verified"]
    assert result["worst_case_cost"] == 3
    assert result["impossibility_witness"] is None


def test_duplicate_equivalent_query_cuts_are_rejected():
    with pytest.raises(ValueError, match="equivalent"):
        planner(specification(), criteria(), queries=[
            {"threshold": t, "unit": "mg/L", "cost": 1} for t in (2, 3)])


def test_count_from_another_sample_cannot_inform_the_plan():
    with pytest.raises(ValueError, match="original n"):
        planner(specification(), criteria(), additional_counts=[
            {"threshold": 4, "unit": "mg/L", "count": 0, "n": 11}])


def test_common_boundary_plan_does_not_expand_sample_histograms():
    result = planner(specification(n=1000000, k=8),
                     criteria((2, 4, 8, 16, 32, 64), fraction=".0000005"))
    assert result["status"] == "optimal"
    assert result["worst_case_cost"] == 3
    assert result["fixed_plan_cost"] == 6
    assert result["search"]["states"] <= 21


def test_an_empty_object_is_not_a_list_of_returned_counts():
    with pytest.raises(ValueError, match="additional count"):
        planner(specification(), criteria(), additional_counts={})


def test_total_query_cost_must_be_representable_in_exports():
    with pytest.raises(ValueError, match="cost"):
        planner(specification(), criteria(), queries=[
            {"threshold": t, "unit": "mg/L", "cost": "1e308"} for t in (2, 4, 8)])


def test_large_panel_capacity_limit_preserves_verified_fixed_plan():
    spec = specification()
    spec['panel']['levels'] = list(range(1, 1101))
    result = planner(spec, criteria(range(2, 1100)), time_limit_seconds=2)
    assert result['status'] == 'incomplete'
    assert result['worst_case_cost'] == 1098
    assert result['cost_interpretation'] == 'verified_upper_bound'
    assert not result['optimality_verified']


def test_variant_union_can_be_resolved_by_two_cheap_off_target_counts():
    # Each complete variant fixes one of these histograms through its three ranks.
    histograms = [(0, 1, 1, 1), (0, 2, 1, 0), (1, 1, 0, 1), (1, 0, 2, 0)]
    summaries = []
    for histogram in histograms:
        ordered = [str(2**j) for j, count in enumerate(histogram) for _ in range(count)]
        summaries.append({'minimum': ordered[0], 'quantiles': [
            {'probability': .5, 'rank': 2, 'category': ordered[1]},
            {'probability': .9, 'rank': 3, 'category': ordered[2]}]})
    spec = specification(n=3, k=4)
    spec['summaries'] = summaries[0]
    spec['reporting_envelope'] = {'variants': [
        {'id': str(j), 'summaries': summary} for j, summary in enumerate(summaries[1:])]}
    result = planner(spec, criteria((2,), fraction='.5', op='<='), queries=[
        {'threshold': t, 'unit': 'mg/L', 'cost': c} for t, c in [(1, 1), (2, 3), (4, 1)]])
    assert result['status'] == 'optimal' and result['worst_case_cost'] == 2
    assert result['fixed_plan_cost'] == 3  # A feasible baseline, not the minimum fixed set.
    assert not result['fixed_plan_optimality_verified']
    for histogram in histograms:
        policy = result['policy']
        node = policy['nodes'][policy['root']]
        cost = 0
        while 'question' in node:
            query = node['question']
            count = sum(histogram[query['cut_index']+1:])
            cost += query['cost']
            branch, = [b for b in node['branches'] if b['count_min'] <= count <= b['count_max']]
            node = policy['nodes'][branch['next_node']]
        expected = 'supported' if Fraction(sum(histogram[2:]), 3) <= Fraction(1, 2) else 'contradicted'
        assert node['decisions'] == [expected] and cost == 2
