from fractions import Fraction

from mic_50_90 import plan_acquisition
from test_decision_planning import specification, criteria


def test_timeout_retains_a_proved_cost_bracket():
    result = plan_acquisition(specification(), criteria(), round_cost=2, time_limit_seconds=0)
    assert result.get('cost_lower_bound') == 3
    assert result.get('cost_upper_bound') == 5
    assert result.get('cost_gap') == 2
    assert not result['optimality_verified']
    assert result['lower_bound_certificate']['method'] == 'feasible_pair_separation'


def test_pair_certificate_detects_a_mandatory_expensive_cut():
    queries = [dict(threshold=t, unit='mg/L', cost=c) for t,c in [(1,1),(2,1),(4,7),(8,1)]]
    result = plan_acquisition(specification(), criteria((4,)), queries=queries,
                              round_cost=2, time_limit_seconds=0)
    assert result.get('cost_lower_bound') == 9
    assert result.get('cost_upper_bound') == 9
    assert result.get('cost_gap') == 0


def test_pair_lower_bound_is_never_larger_than_exact_cost():
    for cost in ('0','1/3','2','5'):
        for fraction in ('.05','.1','.2'):
            raw = specification()
            early = plan_acquisition(raw, criteria(fraction=fraction), round_cost=cost, time_limit_seconds=0)
            complete = plan_acquisition(raw, criteria(fraction=fraction), round_cost=cost)
            lower = early.get('cost_lower_bound_exact')
            assert lower is not None
            assert Fraction(lower) <= Fraction(complete['worst_case_cost_exact'])
            assert complete.get('cost_gap_exact') == '0'


def test_witness_pairs_really_need_one_of_the_charged_counts():
    result = plan_acquisition(specification(), criteria(), round_cost=2, time_limit_seconds=0)
    certificate = result.get('lower_bound_certificate')
    assert certificate is not None
    for pair in certificate['pairs']:
        a,b = pair['histograms']
        assert sum(a) == sum(b) == 10
        for h in (a,b):
            assert h[0] >= 5 and h[0] <= 8 and h[0]+h[1] >= 9
        cut = pair['criterion_cut']
        assert (sum(a[cut:]) == 0) != (sum(b[cut:]) == 0)
        separating = [q for q in result['allowed_queries']
                      if sum(a[q['cut_index']+1:]) != sum(b[q['cut_index']+1:])]
        assert pair['separating_cut_indices'] == [q['cut_index'] for q in separating]
        assert Fraction(pair['cost_lower_bound_exact']) == 2+min(Fraction(q['cost_exact']) for q in separating)


def test_incomplete_report_retains_lower_bound_without_a_sufficient_policy():
    from mic_50_90.decision_report import render_acquisition_plan

    raw = specification(n=6, k=3)
    raw['summaries']['quantiles'] = [dict(probability=.5, category='1', rank=4),
                                   dict(probability=.9, category='2', rank=6)]
    raw['reporting_envelope'] = dict(variants=[dict(id='alternative', summaries=dict(quantiles=[
        dict(probability=.5, category='2', rank=4),
        dict(probability=.9, category='4', rank=6)]))])
    result = plan_acquisition(raw, criteria((1,), fraction='.5'),
        queries=[dict(threshold=2, unit='mg/L', cost=1)], round_cost=2, time_limit_seconds=0)
    assert result['policy'] is None and result['cost_lower_bound_exact'] == '3'
    report = render_acquisition_plan(result)
    assert 'Verified lower bound: 3 declared cost units' in report
    assert 'no cost or round bound is available' not in report
    assert 'No upper cost bound or complete request plan has been verified' in report
