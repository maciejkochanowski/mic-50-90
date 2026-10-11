import json
from pathlib import Path

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.distribution_report import render_distribution_html
from mic_50_90.gui_forms import validate_payload
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


def test_batch_mode_accepts_any_population_method_left_by_the_distribution_view():
    from copy import deepcopy
    from mic_50_90.gui_forms import desktop_examples
    example = next(item for item in desktop_examples() if item['id'] == 'summary20')
    for method in ('bonferroni', 'joint-exact', 'range-calibrated', 'range-hunter'):
        payload = deepcopy(example['payload'])
        payload['mode'] = 'batch'
        payload['targets'] = [{'threshold': 1, 'unit': 'mg/L', 'decision_operator': '<', 'decision_fraction': '0.3'}]
        payload['options'] = {'population_method': method, 'population_time_limit': 30,
                              'population_tolerance_pp': 0.01, 'precision_pp': None,
                              'population_precision_pp': None, 'population_count_plan': False,
                              'population_minimum_bins': None}
        result = validate_payload(payload)
        assert result['valid'], result['issues']
        assert not [w for w in result['warnings'] if w['field'].startswith('options.population')
                    or w['field'] == 'options.precision_pp']


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
        closed = {s.cut_index: (s.minimax_width_reduction, s.feasible_answer_min, s.feasible_answer_max)
                  for s in rank_robust_tail_count_questions(problems=problems, target_objectives=[target])}
        linear = {s.cut_index: (s.minimax_width_reduction, s.feasible_answer_min, s.feasible_answer_max)
                  for s in _rank_robust_tail_count_questions_lp(problems=problems, target_objectives=[target])}
        assert closed.keys() == linear.keys()
        for cut in closed:
            assert abs(closed[cut][0] - linear[cut][0]) < 1e-12 and closed[cut][1:] == linear[cut][1:]
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
