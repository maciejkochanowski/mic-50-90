"""Independent integer examples catch false precision in returned information."""
from fractions import Fraction

import pytest

from mic_50_90 import analyse_with_counts, plan_acquisition, plan_decisions
from test_count_updates import calibration, sample_counts, specification


def bounded(low=1, high=2, n=6, threshold=1):
    return dict(threshold=threshold, unit='mg/L', n=n, count_min=low, count_max=high)


def test_interval_retains_both_possible_counts_instead_of_its_midpoint():
    result = analyse_with_counts(specification(), [bounded()], iid=True)
    assert sample_counts(result) == [(1, 2), (1, 2)]
    marginal = result['population_layer']['threshold_results'][0]['exact_count_confidence']['marginal']
    assert marginal['admissible_count_ranges'] == [[1, 2]]


def test_bounded_counts_preserve_original_calibration_event():
    result = analyse_with_counts(specification(), [bounded()], calibration=calibration())
    band = result['assumption_dependent_scenarios']['wasserstein_ambiguity_set']
    # The original calibrated lower bound is 2/6, so the returned range
    # [1,2] intersects it at 2. Truthful ranges cannot enlarge that band.
    assert band['threshold_results'][0]['envelope'] == pytest.approx({'lower': 2/6, 'upper': 2/6})
    assert band['threshold_results'][1]['envelope'] == pytest.approx({'lower': 1/6, 'upper': 2/6})


def test_both_planners_condition_on_the_whole_interval():
    criterion = [dict(threshold=1, unit='mg/L', decision_operator='<', decision_fraction='.5')]
    for planner in (plan_acquisition, plan_decisions):
        result = planner(specification(), criterion, additional_counts=[bounded()])
        assert result['status'] == 'already_resolved'
        assert result['worst_case_cost'] == 0


def test_next_count_search_does_not_discard_an_existing_interval():
    raw = specification()
    raw['question_utility'] = {'enabled': True}
    result = analyse_with_counts(raw, [bounded()])
    # The two tail counts can be (1,1), (2,1), or (2,2). Either exact count
    # removes at least one of the two remaining unit widths.
    assert result['one_question_recovery']['best_question']['minimax_width_reduction'] == pytest.approx(1/6)


@pytest.mark.parametrize('row', [
    bounded(-1, 2), bounded(3, 2), bounded(1, 7), bounded(True, 2), bounded(1.5, 2),
    {**bounded(), 'count': 1}, {k:v for k,v in bounded().items() if k != 'count_max'},
])
def test_invalid_or_ambiguous_count_interval_is_refused(row):
    with pytest.raises(ValueError):
        analyse_with_counts(specification(), [row])


@pytest.mark.parametrize('percentage,places,rule,want', [
    ('12', 0, 'half_up', (23, 24)),
    ('12', 0, 'half_even', (23, 25)),
    ('13', 0, 'half_even', (26, 26)),
    ('12', 0, 'floor', (24, 25)),
    ('12', 0, 'ceiling', (23, 24)),
    ('12.5', 1, 'half_up', (25, 25)),
    ('0', 0, 'half_up', (0, 0)),
    ('100', 0, 'half_even', (199, 200)),
])
def test_percentage_conversion_respects_ties_and_endpoints(percentage, places, rule, want):
    import mic_50_90.count_updates as module
    convert = getattr(module, 'counts_from_percentage', None)
    assert callable(convert), 'Rounded percentages need an exact integer conversion'
    assert convert(percentage, n=200, decimal_places=places, rounding_rule=rule) == want


def test_rounded_percentage_is_used_as_an_interval_in_analysis():
    raw = specification(n=200)
    result = analyse_with_counts(raw, [dict(threshold=1, unit='mg/L', n=200,
        percentage='12', decimal_places=0, rounding_rule='half_up')])
    assert sample_counts(result)[0] == (23, 24)
    assert result['additional_information']['observations'][0]['percentage'] == '12'


@pytest.mark.parametrize('change', [
    {'percentage': '12.1', 'decimal_places': 0}, {'rounding_rule': ''},
    {'percentage': '-1'}, {'percentage': 'nan'}, {'decimal_places': True},
    {'percentage': '12', 'count_min': 22, 'count_max': 24},
])
def test_rounding_requires_a_complete_unambiguous_contract(change):
    row = dict(threshold=1, unit='mg/L', n=200, percentage='12', decimal_places=0, rounding_rule='half_up')
    with pytest.raises(ValueError):
        analyse_with_counts(specification(n=200), [{**row, **change}])


def test_percentage_that_cannot_come_from_denominator_is_refused():
    import mic_50_90.count_updates as module
    convert = getattr(module, 'counts_from_percentage', None)
    assert callable(convert)
    with pytest.raises(ValueError, match='integer count'):
        convert('12.5', n=6, decimal_places=1, rounding_rule='half_up')


def test_independent_histograms_verify_interval_and_prefix_engines():
    raw = specification(n=10)
    histograms = [(a,b,10-a-b) for a in range(5,9) for b in range(9-a)]
    for lo, hi in [(2,4), (3,5), (2,2), (0,10)]:
        compatible = [h for h in histograms if lo <= h[1]+h[2] <= hi]
        result = analyse_with_counts(raw, [bounded(lo, hi, n=10)])
        for j, interval in zip((1,2), sample_counts(result)):
            assert interval == (min(sum(h[j:]) for h in compatible), max(sum(h[j:]) for h in compatible))
        criterion = [dict(threshold=1, unit='mg/L', decision_operator='<', decision_fraction='.3')]
        truth = {Fraction(h[1]+h[2],10) < Fraction(3,10) for h in compatible}
        planned = plan_acquisition(raw, criterion, additional_counts=[bounded(lo,hi,n=10)])
        assert (planned['status'] == 'already_resolved') == (len(truth) == 1)
