import json

import pytest
from pathlib import Path

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.distribution_report import render_distribution_html
from mic_50_90.result_view import distribution_overview

ROOT = Path(__file__).resolve().parents[1]


def ampicillin():
    return json.loads((ROOT / 'examples/biological_cases/ampicillin-67-summaries.json').read_text(encoding='utf-8'))


def test_next_count_follows_the_declared_question():
    # Category 0.5 mg/L below 15%: the count at or below 0.25 mg/L settles 22 of 27 possible answers,
    # the count at or below 0.12 mg/L only 5 of 27 (exhaustive check over the 7938 compatible tables).
    guidance = analyse_distribution(ampicillin())['interpretation']
    suggestion = guidance['suggested_count']
    assert suggestion['through_label'] == '0.25'
    assert (suggestion['count_lower'], suggestion['count_upper']) == (34, 60)
    assert 'declared question' in suggestion['selection_rule']
    assert '0.25' in guidance['next_step'] and 'first 1' not in guidance['next_step']


def test_next_count_without_questions_keeps_the_widest_cumulative_rule():
    raw = {'n': 20, 'unit': 'mg/L', 'panel': {'levels': [1, 2]},
           'additional_counts': [{'threshold': 1, 'count': 8, 'n': 20, 'unit': 'mg/L'}]}
    guidance = analyse_distribution(raw)['interpretation']
    assert guidance['suggested_count']['through_label'] == '2'
    assert guidance['suggested_count']['selection_rule'].startswith('Largest unresolved cumulative count range')


def test_next_count_wording_names_the_categories():
    raw = {'n': 20, 'unit': 'mg/L', 'panel': {'levels': [1, 2, 4]},
           'summaries': {'minimum': '<=1', 'maximum': '>4'}}
    step = analyse_distribution(raw)['interpretation']['next_step']
    assert 'first 1 recorded' not in step and 'groups,' not in step


def test_range_hunter_unfinished_refinement_is_reported():
    raw = {'n': 20, 'unit': 'mg/L', 'panel': {'levels': [1, 2]}, 'iid': True,
           'additional_counts': [{'threshold': 1, 'count': 8, 'n': 20, 'unit': 'mg/L'}]}
    result = analyse_distribution(raw, population_method='range-hunter', population_time_limit=0)
    if not result['population'].get('precision_reached', False):
        assert result['interpretation']['numerical_refinement_unfinished']
        assert 'Numerical refinement' in distribution_overview(result)


def test_singular_counts_read_correctly(tmp_path):
    raw = ampicillin()
    raw['iid'] = True
    result = analyse_distribution(raw, population_method='range-calibrated', population_precision_pp=2)
    output = tmp_path / 'report.html'
    render_distribution_html({'software_version': '1.0.0', 'cohorts': [result]}, output)
    text = output.read_text(encoding='utf-8')
    for wrong in ('1 groups are confirmed', 'supports 1 contiguous bins', 'at most 2 percentage point '):
        assert wrong not in text


def _generated_reports(count, seed):
    import math
    import random
    rng = random.Random(seed)
    for index in range(count):
        n = rng.choice([5, 8, 12, 20, 33, 60])
        levels = sorted(rng.sample([0.12, 0.25, 0.5, 1, 2, 4, 8, 16], rng.randint(1, 4)))
        labels = ['<=%g' % levels[0]] + ['%g' % x for x in levels[1:]] + ['>%g' % levels[-1]]
        k = len(labels)
        histogram = [0] * k
        for _ in range(n):
            histogram[min(k - 1, int(rng.random() ** rng.choice([0.5, 1, 2]) * k))] += 1
        cumulative = [sum(histogram[:j + 1]) for j in range(k)]
        quantiles = []
        for p in sorted(rng.sample([.25, .5, .75, .9], rng.randint(1, 2))):
            rank = math.ceil(p * n)
            quantiles.append({'probability': str(p), 'category': labels[next(j for j in range(k) if cumulative[j] >= rank)],
                              'convention': 'ceiling'})
        raw = {'cohort_id': f'generated-{index}', 'n': n, 'unit': 'mg/L', 'panel': {'levels': levels},
               'summaries': {'quantiles': quantiles}}
        if rng.random() < .5:
            raw['additional_counts'] = [{'threshold': t, 'count': n - cumulative[levels.index(t)], 'n': n, 'unit': 'mg/L'}
                                        for t in rng.sample(levels, rng.randint(1, len(levels)))]
        a = rng.randrange(k)
        b = rng.randrange(a, k)
        raw['targets'] = [{'start_category': labels[a], 'end_category': labels[b], 'unit': 'mg/L',
                           'decision_operator': '<', 'decision_fraction': '0.3'}]
        yield raw


def test_range_question_ranking_equals_the_linear_programming_ranking():
    import numpy as np
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.utility import _rank_robust_tail_count_questions_lp, rank_robust_tail_count_questions
    compared = 0
    for raw in _generated_reports(80, 11):
        try:
            problems, _, _ = distribution_problems(raw)
        except ValueError:
            continue
        k = next(iter(problems.values())).k
        a = [b.label for b in next(iter(problems.values())).panel.bins].index(raw['targets'][0]['start_category'])
        b = [x.label for x in next(iter(problems.values())).panel.bins].index(raw['targets'][0]['end_category']) + 1
        if b - a == k or (a == 0 or b == k):
            continue
        target = np.zeros(k)
        target[a:b] = 1.
        closed_order = rank_robust_tail_count_questions(problems=problems, target_objectives=[target])
        linear_order = _rank_robust_tail_count_questions_lp(problems=problems, target_objectives=[target])
        closed = {s.cut_index: (s.minimax_width_reduction, s.mean_width_reduction, s.feasible_answer_min, s.feasible_answer_max,
                                s.boundaries_from_targets, s.boundaries_from_median) for s in closed_order}
        linear = {s.cut_index: (s.minimax_width_reduction, s.mean_width_reduction, s.feasible_answer_min, s.feasible_answer_max,
                                s.boundaries_from_targets, s.boundaries_from_median) for s in linear_order}
        assert closed.keys() == linear.keys()
        for cut in closed:
            assert abs(closed[cut][0] - linear[cut][0]) < 1e-12 and abs(closed[cut][1] - linear[cut][1]) < 1e-9
            assert closed[cut][2:] == linear[cut][2:]
        compared += 1
    assert compared >= 10


def test_next_count_for_a_large_report_is_fast_and_question_based():
    from time import perf_counter
    raw = ampicillin()
    raw['n'] = 6700
    started = perf_counter()
    first = analyse_distribution(raw)['interpretation']
    assert perf_counter() - started < 3
    assert first['suggested_count']['through_label'] == '0.25'
    assert 'declared question' in first['suggested_count']['selection_rule']
    assert analyse_distribution(raw)['interpretation'] == first


def test_next_count_also_serves_a_question_without_a_criterion():
    raw = ampicillin()
    for target in raw['targets']:
        target.pop('decision_operator')
        target.pop('decision_fraction')
    result = analyse_distribution(raw)
    assert result['decisions'][0]['sample']['status'] == 'available'
    assert result['interpretation']['suggested_count']['through_label'] == '0.25'


def _range_report(n, labels, median, ninetieth, lowest, highest):
    levels = [float(x) for x in labels[:-1]]
    return {'n': n, 'unit': 'mg/L', 'panel': {'levels': levels, 'left_censored': False},
            'summaries': {'quantiles': [{'probability': '0.5', 'category': median, 'convention': 'ceiling'},
                                        {'probability': '0.9', 'category': ninetieth, 'convention': 'ceiling'}],
                          'minimum': lowest, 'maximum': highest}}


def _compatible_tables(n, k, median, ninetieth, lowest, highest):
    """Every table of k categories that gives the stated ceiling-rank MIC50 and MIC90 and observed range."""
    import math
    from itertools import product
    r50, r90 = math.ceil(n / 2), math.ceil(0.9 * n)
    for head in product(range(n + 1), repeat=k - 1):
        last = n - sum(head)
        if last < 0:
            continue
        table = head + (last,)
        prefix = [sum(table[:i]) for i in range(k + 1)]
        occupied = [i for i, c in enumerate(table) if c]
        if (occupied[0], occupied[-1]) != (lowest, highest):
            continue
        if not (prefix[median] < r50 <= prefix[median + 1] and prefix[ninetieth] < r90 <= prefix[ninetieth + 1]):
            continue
        yield table, prefix


def test_average_reduction_and_tie_breaks_equal_an_exhaustive_enumeration():
    # MIC50 in category 1, MIC90 in category 4, range 0..5; six categories, twelve isolates.
    import numpy as np
    from fractions import Fraction
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.utility import rank_robust_tail_count_questions
    n, labels = 12, ['1', '2', '4', '8', '16', '>16']
    raw = _range_report(n, labels, '2', '16', '1', '>16')
    problems, _, _ = distribution_problems(raw)
    k = next(iter(problems.values())).k
    assert [b.label for b in next(iter(problems.values())).panel.bins] == labels
    tables = list(_compatible_tables(n, k, 1, 4, 0, 5))
    assert len(tables) > 100
    for j in range(k):
        target = np.zeros(k)
        target[j] = 1.
        scores = rank_robust_tail_count_questions(problems=problems, target_objectives=[target])
        baseline = max(t[j] for t, _ in tables) - min(t[j] for t, _ in tables)
        expected = {}
        for q in range(1, k):
            by_answer = {}
            for table, prefix in tables:
                by_answer.setdefault(prefix[q], []).append(table[j])
            widths = [max(v) - min(v) for v in by_answer.values()]
            expected[q - 1] = (baseline - max(widths), baseline - Fraction(sum(widths), len(widths)), len(widths))
        assert {s.cut_index for s in scores} == set(expected)
        for s in scores:
            worst, mean, answers = expected[s.cut_index]
            assert s.feasible_answers_evaluated == answers
            assert s.minimax_width_reduction * n == pytest.approx(worst, abs=1e-9)
            assert s.mean_width_reduction * n == pytest.approx(float(mean), abs=1e-9)
            assert s.boundaries_from_targets == min(abs(s.cut_index + 1 - j), abs(s.cut_index + 1 - (j + 1)))
            # boundary 2 is the first with at least half of the isolates at or below it, boundary 1 the last without
            assert s.boundaries_from_median == (s.cut_index + 1 - 1 if s.cut_index + 1 >= 2 else 1)
        order = [s.cut_index for s in scores]
        assert order == sorted(expected, key=lambda q: (-expected[q][0], -expected[q][1],
                                                        min(abs(q + 1 - j), abs(q + 1 - (j + 1))),
                                                        q + 1 - 1 if q + 1 >= 2 else 1, q))


@pytest.mark.parametrize('category, through', [('4', '2'), ('8', '4'), ('1', '1')])
def test_next_count_without_a_guarantee_is_the_adjacent_count_on_the_side_of_the_median(category, through):
    # n = 60: MIC50 in 2 mg/L, MIC90 in 16 mg/L. No single count is certain to narrow categories 4 and 8,
    # which lie above the median: the count just below the category is named. The lowest category lies
    # below the median: the count through that category is named.
    labels = ['1', '2', '4', '8', '16', '>16'] if category != '1' else ['0.5', '1', '2', '4', '8', '16', '>16']
    raw = (_range_report(60, labels, '2', '16', '1', '>16') if category != '1' else
           _range_report(60, labels, '4', '16', '0.5', '>16'))
    raw['targets'] = [{'start_category': category, 'end_category': category, 'unit': 'mg/L'}]
    guidance = analyse_distribution(raw)['interpretation']
    suggestion = guidance['suggested_count']
    assert suggestion['selection_rule'].startswith('Largest average reduction')
    assert suggestion['through_label'] == through
    assert 'most on average over its possible values' in guidance['next_step']


def test_boundaries_from_the_median_and_from_the_question():
    import numpy as np
    from mic_50_90.utility import _boundaries_from_median, _boundaries_from_targets
    # F_0..F_5 for n = 10: the median (rank 5) may lie in category 1 or 2.
    lower, upper = [0, 0, 3, 5, 9, 10], [0, 4, 7, 9, 9, 10]
    assert list(_boundaries_from_median(lower, upper, 10)) == [2, 1, 0, 1, 2, 3]
    tail, middle = np.array([0., 0., 1., 1., 1.]), np.array([0., 1., 1., 0., 0.])
    assert [_boundaries_from_targets(q, [tail]) for q in range(1, 5)] == [1, 0, 1, 2]
    assert [_boundaries_from_targets(q, [middle]) for q in range(1, 5)] == [0, 1, 0, 1]
    assert _boundaries_from_targets(2, [tail, middle]) == 1


def test_width_planning_names_the_best_average_count_when_none_is_guaranteed():
    from mic_50_90.analysis import analyse_spec
    raw = {'n': 60, 'panel': {'levels': [1, 2, 4, 8, 16], 'left_censored': False},
           'summaries': {'quantiles': [{'probability': .5, 'category': '2'}, {'probability': .9, 'category': '16'}]},
           'thresholds': [4], 'question_utility': {'enabled': True, 'exclude_direct_target_questions': True}}
    recovery = analyse_spec(raw)['one_question_recovery']
    # The count above 4 mg/L is the question. The counts above 2 and above 8 mg/L narrow it equally on
    # average and are equally near; the count above 2 mg/L lies on the side of the median.
    assert recovery['best_question'] is None
    average = recovery['best_average_question']
    assert 'above category 2 ' in average['question']
    assert average['minimax_width_reduction'] == 0 and average['mean_width_reduction'] == pytest.approx(11.5 / 60)
    raw['question_utility'] = {'enabled': True}
    recovery = analyse_spec(raw)['one_question_recovery']
    assert 'above category 4 ' in recovery['best_question']['question'] and recovery['best_average_question'] is None
