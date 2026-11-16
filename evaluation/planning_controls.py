"""Finite controls of request planning: independent decision-tree enumeration against plan_decisions.

The oracle enumerates every nonnegative integer histogram compatible with a report, checks the
order statistics on the expanded observations, compares tail fractions as exact fractions and
computes the optimal worst-case decision tree over the explicit set of histograms (and the
cheapest fixed set of counts). It does not use the package. The package result must agree on
status (already resolved, optimal or impossible), initial criterion statuses and exact costs.
Every returned policy is then followed for every compatible histogram: each path must end in a
leaf whose decisions are true for that histogram, every node must carry the enumerated statuses
and remaining cost, and the longest path must cost the oracle optimum. Every impossibility
witness must be a pair of compatible histograms with the same answer at every allowed count and
opposite decisions.

  controlled  panel 1, 2, 4, 8 mg/L; n = 2 to 6; every ordered MIC50/MIC90 category pair under
              ceiling ranks (50 reports); fractions 0.1, 0.4, 0.5; operators < and <=; all three
              cuts or each one-cut omission; costs 1, 1, 1 or 1, 3, 1: 2400 tasks.
  stress      120 seeded reports (n = 2 to 6, K = 4, one to three summary variants, optional
              exact extrema, mixed operators and fractions, random allowed counts and costs, and a
              returned count in every fourth case) and eight constructed cases: 128 tasks.
  contract    31 input and contract controls: invalid costs, time limits and state budgets,
              foreign or conflicting counts, duplicate cuts, exhausted budgets that must keep a
              valid fixed plan, refused population and latent scopes, a censored category, no
              numerical solver, and very large finite costs.

Output: OUTPUT/planning_controls/summary.json, controlled.csv.gz, stress.csv.gz and contract.json.
"""
from __future__ import annotations

import common

import json
import traceback
from collections import Counter
from copy import deepcopy
from fractions import Fraction
from functools import lru_cache
from itertools import combinations, product
from operator import ge, gt, le, lt
from random import Random
from time import perf_counter
from unittest.mock import patch

from common import now, write_csv, write_json

PANEL = (1, 2, 4, 8)
OPS = {'<': lt, '<=': le, '>': gt, '>=': ge}
STRESS_SEED = 2026092802
LIMITS = dict(time_limit_seconds=5, max_states=5000)


def compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for first in range(n + 1):
            for rest in compositions(n - first, k - 1):
                yield (first, *rest)


def statuses(labels, count):
    return ['supported' if all(row[j] for row in labels) else 'contradicted' if not any(row[j] for row in labels) else 'undetermined'
            for j in range(count)]


def as_text(labels):
    return ['supported' if value else 'contradicted' for value in labels]


def minimax(labels, tails, costs):
    """Optimal worst-case cost over explicit hypotheses (None if impossible) and the cheapest complete fixed set of counts."""
    @lru_cache(None)
    def solve(ids):
        if len({labels[i] for i in ids}) == 1:
            return Fraction(0)
        best = None
        for j, cost in enumerate(costs):
            groups = {}
            for i in ids:
                groups.setdefault(tails[i][j], []).append(i)
            if len(groups) == 1:
                continue
            children = [solve(tuple(group)) for group in groups.values()]
            if any(child is None for child in children):
                continue
            candidate = cost + max(children)
            best = candidate if best is None else min(best, candidate)
        return best

    ids = tuple(range(len(labels)))
    optimum, fixed = solve(ids), None
    for size in range(len(costs) + 1):
        for chosen in combinations(range(len(costs)), size):
            groups = {}
            for i in ids:
                groups.setdefault(tuple(tails[i][j] for j in chosen), set()).add(labels[i])
            if all(len(group) == 1 for group in groups.values()):
                cost = sum((costs[j] for j in chosen), Fraction(0))
                fixed = cost if fixed is None else min(fixed, cost)
    status = 'already_resolved' if optimum == 0 else 'impossible' if optimum is None else 'optimal'
    return status, optimum, fixed


def follow_policy(result, histograms, truth, cut_cost, panel_values, n):
    """Follow the policy for every hypothesis; return paths, reached leaves and the longest path cost."""
    policy = result['policy']
    nodes = policy['nodes']
    assert policy['root'] in nodes
    reached, remaining, leaves, longest = {}, {}, {}, Fraction(0)
    for histogram in histograms:
        node_id, spent, seen, entered = policy['root'], Fraction(0), set(), []
        while True:
            assert node_id not in seen, 'policy contains a reachable cycle'
            seen.add(node_id)
            entered.append((node_id, spent))
            reached.setdefault(node_id, []).append(histogram)
            node = nodes[node_id]
            if 'question' not in node:
                assert node['decisions'] == as_text(truth(histogram)), 'leaf decision is not true for the histogram'
                assert Fraction(str(node['worst_case_cost'])) == 0
                leaves.setdefault(node_id, set()).add(truth(histogram))
                longest = max(longest, spent)
                for previous, entry in entered:
                    remaining[previous] = max(remaining.get(previous, Fraction(0)), spent - entry)
                break
            question = node['question']
            q = sum(value <= float(question['threshold']) for value in panel_values)
            assert question['cut_index'] + 1 == q, 'question threshold and cut index disagree'
            assert q in cut_cost, 'policy requests a count that is not allowed'
            assert Fraction(str(question.get('cost_exact', question['cost']))) == cut_cost[q], 'question cost differs from the declared cost'
            spent += cut_cost[q]
            answer = sum(histogram[q:])
            for branch in node['branches']:
                assert isinstance(branch['count_min'], int) and isinstance(branch['count_max'], int)
                assert 0 <= branch['count_min'] <= branch['count_max'] <= n and branch['next_node'] in nodes
            matches = [b for b in node['branches'] if b['count_min'] <= answer <= b['count_max']]
            assert len(matches) == 1, 'a feasible answer has a missing or overlapping branch'
            node_id = matches[0]['next_node']
    for node_id, group in reached.items():
        node = nodes[node_id]
        assert node['decisions'] == statuses([truth(h) for h in group], len(node['decisions'])), 'node status differs from enumeration'
        assert Fraction(str(node.get('worst_case_cost_exact', node['worst_case_cost']))) == remaining[node_id], 'node cost differs'
    assert all(len(labels) == 1 for labels in leaves.values())
    return dict(histogram_paths=len(histograms), reached_nodes=len(reached), feasible_leaves=len(leaves), longest=longest)


def check_witness(result, histograms, truth, allowed, strict=False):
    witness = result.get('impossibility_witness')
    assert isinstance(witness, dict) and len(witness['states']) == 2, 'missing impossibility witness'
    pair = [state['histogram'] for state in witness['states']]
    for state, histogram in zip(witness['states'], pair):
        assert all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in histogram)
        assert histogram in histograms, 'witness histogram is not compatible with the report'
        if strict or 'decisions' in state:
            assert state['decisions'] == as_text(truth(histogram))
    assert truth(pair[0]) != truth(pair[1]), 'witness does not give opposite decisions'
    assert all(sum(pair[0][q:]) == sum(pair[1][q:]) for q in allowed), 'witness answers differ at an allowed count'
    if strict or 'criterion_index' in witness:
        j = witness['criterion_index']
        assert truth(pair[0])[j] != truth(pair[1])[j]


# Controlled grid ----------------------------------------------------------------------------------

def controlled_tasks():
    reports, tasks = {}, []
    for n in range(2, 7):
        rank50, rank90 = (n + 1) // 2, (9 * n + 9) // 10
        for c50 in range(len(PANEL)):
            for c90 in range(c50, len(PANEL)):
                histograms = []
                for h in compositions(n, len(PANEL)):
                    expanded = [j for j, count in enumerate(h) for _ in range(count)]
                    if expanded[rank50 - 1] == c50 and expanded[rank90 - 1] == c90:
                        histograms.append(list(h))
                report = f'n{n}-c50_{c50}-c90_{c90}'
                reports[report] = dict(n=n, category50=c50, category90=c90, histograms=histograms)
                for fraction, operator, omission, costs in product(('0.1', '0.4', '0.5'), ('<', '<='), (None, 1, 2, 3),
                                                                   ((1, 1, 1), (1, 3, 1))):
                    allowed = [q for q in range(1, len(PANEL)) if q != omission]
                    tasks.append(dict(id=f'task-{len(tasks) + 1:04d}', report=report, fraction=fraction, operator=operator,
                                      allowed=allowed, costs=list(costs)))
    assert len(reports) == 50 and len(tasks) == 2400
    return reports, tasks


def controlled_truth(task):
    limit, op = Fraction(task['fraction']), OPS[task['operator']]
    return lambda h: tuple(op(Fraction(sum(h[q:]), sum(h)), limit) for q in range(1, len(PANEL)))


def controlled_oracle(report, task):
    histograms = report['histograms']
    if not histograms:
        return dict(status='refused', cost=None, fixed_cost=None, initial_statuses=None)
    truth = controlled_truth(task)
    labels = tuple(truth(h) for h in histograms)
    tails = tuple(tuple(sum(h[q:]) for q in task['allowed']) for h in histograms)
    status, cost, fixed = minimax(labels, tails, [Fraction(task['costs'][q - 1]) for q in task['allowed']])
    return dict(status=status, cost=cost, fixed_cost=fixed, initial_statuses=statuses(labels, len(PANEL) - 1))


def controlled_specification(report):
    n = report['n']
    categories = [dict(label=str(v), lower=v, upper=v, lower_closed=True, upper_closed=True, panel_value=v) for v in PANEL]
    return dict(n=n, panel=dict(categories=categories), summaries=dict(quantiles=[
        dict(probability=.5, category=str(PANEL[report['category50']]), rank=(n + 1) // 2),
        dict(probability=.9, category=str(PANEL[report['category90']]), rank=(9 * n + 9) // 10)]),
        thresholds=list(PANEL[:-1]), question_utility=dict(enabled=False))


def controlled():
    from mic_50_90 import plan_decisions
    reports, tasks = controlled_tasks()
    expected = {task['id']: controlled_oracle(reports[task['report']], task) for task in tasks}
    rows = []
    for task in tasks:
        report, oracle = reports[task['report']], expected[task['id']]
        row = dict(id=task['id'], report=task['report'], fraction=task['fraction'], operator=task['operator'],
                   allowed=' '.join(map(str, task['allowed'])), costs=' '.join(map(str, task['costs'])),
                   oracle_status=oracle['status'], oracle_cost='' if oracle['cost'] is None else str(oracle['cost']))
        try:
            criteria = [dict(threshold=v, unit='mg/L', decision_operator=task['operator'], decision_fraction=task['fraction']) for v in PANEL[:-1]]
            queries = [dict(threshold=PANEL[q - 1], unit='mg/L', cost=str(task['costs'][q - 1])) for q in task['allowed']]
            try:
                result = plan_decisions(controlled_specification(report), criteria, queries=queries, **LIMITS)
            except ValueError as exc:
                assert oracle['status'] == 'refused', f'unexpected refusal: {exc}'
                row.update(status='refused', agrees=True)
            else:
                row.update(status=result['status'], package_cost=result.get('worst_case_cost_exact') or '')
                assert result['status'] == oracle['status'], 'status differs from enumeration'
                assert [r['initial_status'] for r in result['criteria']] == oracle['initial_statuses']
                truth = controlled_truth(task)
                if oracle['cost'] is None:
                    assert result['worst_case_cost'] is None
                    check_witness(result, report['histograms'], truth, task['allowed'])
                    row['witness_checked'] = True
                else:
                    assert result['optimality_verified'] is True and result['cost_interpretation'] == 'exact_minimax'
                    assert Fraction(str(result['worst_case_cost_exact'])) == oracle['cost']
                    assert Fraction(str(result['worst_case_cost'])) == oracle['cost']
                    assert Fraction(str(result['fixed_plan_cost'])) == oracle['fixed_cost']
                    assert result['fixed_plan_optimality_verified'] is True
                    policy = result['policy']
                    if result['status'] == 'already_resolved':
                        assert policy['kind'] == 'fixed_order' and policy['questions'] == [] and result['next_question'] is None
                        assert len({truth(tuple(h)) for h in report['histograms']}) == 1
                        assert as_text(truth(tuple(report['histograms'][0]))) == [r['initial_status'] for r in result['criteria']]
                        row['histogram_paths'] = len(report['histograms'])
                    else:
                        assert policy['kind'] == 'adaptive_tree', 'optimal result lacks an adaptive tree'
                        cut_cost = {q: Fraction(task['costs'][q - 1]) for q in task['allowed']}
                        path = follow_policy(result, report['histograms'], truth, cut_cost, PANEL, report['n'])
                        assert path['longest'] == oracle['cost'], 'returned policy is not minimax'
                        assert Fraction(str(result['worst_case_cost_exact'])) == path['longest']
                        row['histogram_paths'] = path['histogram_paths']
                row['agrees'] = True
        except Exception as exc:
            row.update(agrees=False, failure=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        rows.append(row)
    oracle_counts = Counter(e['status'] for e in expected.values())
    assert oracle_counts == Counter(r['oracle_status'] for r in rows)
    return rows, dict(reports=len(reports),
                      compatible_histogram_task_pairs=sum(len(reports[t['report']]['histograms']) for t in tasks))


# Stress set ---------------------------------------------------------------------------------------

def raw_spec(n, k, variant_summaries):
    values = [2**j for j in range(k)]
    return dict(n=n, panel=dict(categories=[dict(label=str(v), lower=v, upper=v, lower_closed=True, upper_closed=True, panel_value=v)
                                            for v in values]),
                summaries=variant_summaries[0],
                reporting_envelope=dict(variants=[dict(id=f'alternative_{j}', summaries=s) for j, s in enumerate(variant_summaries[1:], 1)]),
                thresholds=values[:-1], question_utility=dict(enabled=False))


def summary_from_histogram(histogram, minimum=False, maximum=False):
    n = sum(histogram)
    expanded = [j for j, count in enumerate(histogram) for _ in range(count)]
    summaries = dict(quantiles=[dict(probability=p, rank=rank, category=str(2**expanded[rank - 1]))
                                for p, rank in ((.5, (n + 1) // 2), (.9, (9 * n + 9) // 10))])
    if minimum:
        summaries['minimum'] = str(2**expanded[0])
    if maximum:
        summaries['maximum'] = str(2**expanded[-1])
    return summaries


def histograms_from_raw(raw, returned):
    bins, n = raw['panel']['categories'], raw['n']
    labels = [row['label'] for row in bins]
    variants = [raw['summaries'], *(row['summaries'] for row in raw.get('reporting_envelope', {}).get('variants', []))]
    kept = []
    for histogram in compositions(n, len(bins)):
        sample = [labels[j] for j, count in enumerate(histogram) for _ in range(count)]
        if not any(all(sample[q['rank'] - 1] == q['category'] for q in v['quantiles'])
                   and ('minimum' not in v or sample[0] == v['minimum'])
                   and ('maximum' not in v or sample[-1] == v['maximum']) for v in variants):
            continue
        if any(sum(c for c, b in zip(histogram, bins) if b['panel_value'] > row['threshold']) != row['count'] for row in returned):
            continue
        kept.append(histogram)
    return kept


def stress_truth(bins, criteria):
    return lambda h: tuple(OPS[r['decision_operator']](Fraction(sum(c for c, b in zip(h, bins) if b['panel_value'] > r['threshold']), sum(h)),
                                                       Fraction(r['decision_fraction'])) for r in criteria)


def stress_oracle(case):
    raw, criteria, queries = case['specification'], case['criteria'], case['queries']
    bins = raw['panel']['categories']
    histograms = histograms_from_raw(raw, case.get('additional_counts', []))
    assert histograms
    truth = stress_truth(bins, criteria)
    labels = tuple(truth(h) for h in histograms)
    cuts = [sum(b['panel_value'] <= row['threshold'] for b in bins) for row in queries]
    tails = tuple(tuple(sum(h[q:]) for q in cuts) for h in histograms)
    status, cost, fixed = minimax(labels, tails, [Fraction(row['cost']) for row in queries])
    return dict(histograms=[list(h) for h in histograms], status=status, cost=None if cost is None else str(cost),
                minimum_fixed_cost=None if fixed is None else str(fixed), initial_statuses=statuses(labels, len(criteria)))


def criteria_for(cuts, fraction='.05', operator='<'):
    return [dict(threshold=2**(q - 1), unit='mg/L', decision_operator=operator, decision_fraction=fraction) for q in cuts]


def queries_for(costs):
    return [dict(threshold=2**(q - 1), unit='mg/L', cost=str(cost)) for q, cost in costs.items()]


def stress_cases():
    rng = Random(STRESS_SEED)
    cases = []
    for number in range(120):
        n, k = rng.randrange(2, 7), 4
        every = list(compositions(n, k))
        variant_count = rng.randrange(1, 4)
        summaries = [summary_from_histogram(rng.choice(every), rng.random() < .35, rng.random() < .35) for _ in range(variant_count)]
        raw = raw_spec(n, k, summaries)
        criteria = [dict(threshold=2**(q - 1), unit='mg/L', decision_operator=rng.choice(tuple(OPS)),
                         decision_fraction=rng.choice(('0', '.1', '.25', '.4', '.5', '.75', '.9', '1'))) for q in range(1, k)]
        costs = {q: rng.choice(('.2', '1', '3', '7')) for q in range(1, k) if rng.random() < .8}
        returned = []
        if number % 4 == 0:
            histogram = rng.choice(histograms_from_raw(raw, []))
            q = rng.randrange(1, k)
            returned = [dict(threshold=2**(q - 1), unit='mg/L', count=sum(histogram[q:]), n=n)]
        cases.append(dict(id=f'seeded-{number + 1:03d}', label='seeded', specification=raw, criteria=criteria,
                          queries=queries_for(costs), additional_counts=returned))
    ordinary = raw_spec(10, 5, [dict(quantiles=[dict(probability=.5, category='1', rank=5), dict(probability=.9, category='2', rank=9)])])
    cases.extend([
        dict(id='ordinary-three-targets', label='constructed', specification=ordinary,
             criteria=criteria_for((2, 3, 4)), queries=queries_for({1: 1, 2: 1, 3: 1, 4: 1})),
        dict(id='ordinary-cheap-off-target', label='constructed', specification=ordinary,
             criteria=criteria_for((2, 4)), queries=queries_for({2: 10, 3: 1, 4: 10})),
        dict(id='single-expensive-target', label='constructed', specification=ordinary,
             criteria=criteria_for((3,)), queries=queries_for({1: '.1', 2: '.1', 3: 7, 4: '.1'})),
        dict(id='single-forbidden-target', label='constructed', specification=ordinary,
             criteria=criteria_for((3,)), queries=queries_for({1: '.1', 2: '.1', 4: '.1'})),
        dict(id='truthful-count-update', label='constructed', specification=ordinary,
             criteria=criteria_for((2, 3, 4)), queries=queries_for({1: 1, 2: 1, 3: 1, 4: 1}),
             additional_counts=[dict(threshold=4, unit='mg/L', count=0, n=10)]),
        dict(id='no-questions', label='constructed', specification=ordinary, criteria=criteria_for((2, 3, 4)), queries=[]),
    ])
    xor = [(0, 1, 1, 1), (0, 2, 1, 0), (1, 1, 0, 1), (1, 0, 2, 0)]
    cases.append(dict(id='complete-category-variant-synergy', label='constructed',
                      specification=raw_spec(3, 4, [summary_from_histogram(h, minimum=True) for h in xor]),
                      criteria=criteria_for((2,), '.5', '<='), queries=queries_for({1: 1, 2: 3, 3: 1})))
    strict = raw_spec(11, 5, [dict(quantiles=[dict(probability=.5, category='1', rank=6), dict(probability=.9, category='2', rank=10)])])
    cases.append(dict(id='strict-exact-decimal', label='constructed', specification=strict,
                      criteria=criteria_for((2,), '0.090909090909090905', '<='), queries=queries_for({1: 1, 2: 1, 3: 1, 4: 1})))
    for case in cases:
        case['expected'] = stress_oracle(case)
    return json.loads(json.dumps(cases))


def stress_check(case, result):
    expected = case['expected']
    assert result['status'] == expected['status'], (result['status'], expected['status'])
    assert [r['initial_status'] for r in result['criteria']] == expected['initial_statuses']
    assert result['scope'] == 'recorded_sample_decisions' and result['sample_size'] == case['specification']['n']
    bins, criteria = case['specification']['panel']['categories'], case['criteria']
    cut_cost = {sum(b['panel_value'] <= row['threshold'] for b in bins): Fraction(row['cost']) for row in case['queries']}
    histograms, truth = expected['histograms'], stress_truth(bins, criteria)
    if expected['status'] == 'impossible':
        check_witness(result, histograms, truth, cut_cost, strict=True)
        return dict(witness_checked=True)
    assert result['optimality_verified'] is True
    assert Fraction(result['worst_case_cost_exact']) == Fraction(expected['cost'])
    assert Fraction(result['fixed_plan_cost_exact']) >= Fraction(expected['minimum_fixed_cost'])
    if result['fixed_plan_optimality_verified']:
        assert Fraction(result['fixed_plan_cost_exact']) == Fraction(expected['minimum_fixed_cost'])
    if expected['status'] == 'already_resolved':
        assert result['next_question'] is None and result['policy']['questions'] == []
        assert len({truth(h) for h in histograms}) == 1
        return dict(histogram_paths=len(histograms))
    assert result['policy']['kind'] == 'adaptive_tree'
    path = follow_policy(result, histograms, truth, cut_cost, [b['panel_value'] for b in bins], case['specification']['n'])
    assert path['longest'] == Fraction(expected['cost'])
    return dict(histogram_paths=path['histogram_paths'])


def stress(cases):
    from mic_50_90 import plan_decisions
    rows = []
    for case in cases:
        row = dict(id=case['id'], label=case['label'], oracle_status=case['expected']['status'], oracle_cost=case['expected']['cost'] or '')
        try:
            result = plan_decisions(case['specification'], case['criteria'], queries=case['queries'],
                                    additional_counts=case.get('additional_counts'), **LIMITS)
            row.update(status=result['status'], method=result['method'], package_cost=result['worst_case_cost_exact'] or '')
            row.update(stress_check(case, result), agrees=True)
        except Exception as exc:
            row.update(agrees=False, failure=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        rows.append(row)
    return rows


# Input and contract controls ----------------------------------------------------------------------

def fixed_bound(result, case):
    """Follow a fixed order with exact stopping over all explicit hypotheses; its cost must not exceed the reported bound."""
    if result['policy'] is None:
        assert result['worst_case_cost'] is None and result['cost_interpretation'] == 'unavailable'
        return dict(verified_policy_available=False)
    assert result['policy']['kind'] == 'fixed_order'
    hypotheses = case['expected']['histograms']
    bins, criteria = case['specification']['panel']['categories'], case['criteria']
    truth = stress_truth(bins, criteria)
    allowed = {sum(b['panel_value'] <= row['threshold'] for b in bins): Fraction(row['cost']) for row in case['queries']}
    worst = Fraction(0)
    for actual in hypotheses:
        current, cost = hypotheses[:], Fraction(0)
        for question in result['policy']['questions']:
            if len({truth(h) for h in current}) == 1:
                break
            q = question['cut_index'] + 1
            assert q in allowed and Fraction(question['cost_exact']) == allowed[q]
            cost += allowed[q]
            current = [h for h in current if sum(h[q:]) == sum(actual[q:])]
        assert current and len({truth(h) for h in current}) == 1
        worst = max(worst, cost)
    assert worst <= Fraction(result['worst_case_cost_exact'])
    return dict(verified_policy_available=True, histogram_paths=len(hypotheses), attained_cost=str(worst),
                reported_upper_bound=result['worst_case_cost_exact'])


def contract(cases):
    from mic_50_90 import plan_decisions
    cases = {row['id']: row for row in cases}
    ordinary, synergy = cases['ordinary-three-targets'], cases['complete-category-variant-synergy']
    records = []

    def call(case=ordinary, **overrides):
        arguments = dict(queries=case['queries'], additional_counts=case.get('additional_counts'))
        arguments.update(overrides)
        return plan_decisions(case['specification'], case['criteria'], **arguments)

    def record(name, check):
        try:
            records.append(dict(id=name, passed=True, detail=check()))
        except Exception as exc:
            records.append(dict(id=name, passed=False, failure=f'{type(exc).__name__}: {exc}'))

    def refused(case=ordinary, **overrides):
        try:
            call(case, **overrides)
        except ValueError as exc:
            return dict(refused_with='ValueError', reason=str(exc))
        raise AssertionError('invalid input was not refused')

    for bad in (0, -1, 'nan', 'inf', True, None, '1e-1000', '1e1000'):
        record(f'invalid-cost-{bad!r}', lambda bad=bad: refused(queries=[dict(threshold=2, unit='mg/L', cost=bad)]))
    for bad in (-1, 'nan', 'inf', None):
        record(f'invalid-time-{bad!r}', lambda bad=bad: refused(time_limit_seconds=bad))
    for bad in (0, -1, 1.5, True, None):
        record(f'invalid-state-budget-{bad!r}', lambda bad=bad: refused(max_states=bad))
    record('empty-mapping-is-not-no-counts', lambda: refused(additional_counts={}))
    record('foreign-denominator', lambda: refused(additional_counts=[dict(threshold=4, unit='mg/L', count=0, n=11)]))
    record('conflicting-count', lambda: refused(additional_counts=[dict(threshold=2, unit='mg/L', count=2, n=10)]))
    record('duplicate-equivalent-cut', lambda: refused(queries=[dict(threshold=t, unit='mg/L', cost=1) for t in (2, 3)]))

    def budget(case, seconds, states):
        result = call(case, time_limit_seconds=seconds, max_states=states)
        assert result['status'] == 'incomplete' and not result['optimality_verified']
        assert result['impossibility_witness'] is None
        return dict(status=result['status'], **fixed_bound(result, case))

    record('zero-time-valid-fixed-plan', lambda: budget(ordinary, 0, 5000))
    record('one-state-valid-fixed-plan', lambda: budget(ordinary, 5, 1))
    record('union-one-state-valid-fixed-plan', lambda: budget(synergy, 5, 1))
    forbidden = deepcopy(synergy)
    forbidden['queries'] = [row for row in forbidden['queries'] if row['threshold'] != 2]
    record('union-budget-no-false-impossibility', lambda: budget(forbidden, 5, 1))
    record('union-complete-certificate-valid-fixed-plan', lambda: budget(forbidden, 5, 4))

    def unsupported(scope):
        case = deepcopy(ordinary)
        if scope == 'population':
            case['specification']['mode'] = 'population'
        else:
            case['criteria'][0]['estimand'] = 'latent'
        return refused(case)

    record('population-scope-refusal', lambda: unsupported('population'))
    record('latent-scope-refusal', lambda: unsupported('latent'))

    def censored():
        case = deepcopy(cases['seeded-001'])
        raw = case['specification']
        raw['n'] = 2
        raw['panel']['categories'] = [
            dict(label='1', lower=None, upper=1, lower_closed=False, upper_closed=True, panel_value=1),
            dict(label='2', lower=1, upper=2, lower_closed=False, upper_closed=True, panel_value=2),
            dict(label='4', lower=2, upper=None, lower_closed=False, upper_closed=False, panel_value=4)]
        raw['summaries'] = dict(quantiles=[dict(probability=.5, category='2', rank=1), dict(probability=.9, category='2', rank=2)])
        raw['reporting_envelope'] = dict(variants=[])
        case['criteria'] = [dict(threshold=1.5, unit='mg/L', decision_operator='<', decision_fraction='.5')]
        case['queries'], case['additional_counts'] = [], []
        result = call(case)
        assert result['status'] == 'already_resolved' and result['criteria'][0]['initial_status'] == 'contradicted'
        assert result['scope'] == 'recorded_sample_decisions'
        return dict(status=result['status'], recorded_decision='contradicted',
                    note='both observations may lie below or above 1.5 inside (1, 2]; no latent claim is made')

    record('censored-category-stays-recorded', censored)

    def no_solver():
        with patch('scipy.optimize.linprog', side_effect=AssertionError('planner called linprog')), \
             patch('scipy.optimize.milp', side_effect=AssertionError('planner called milp')), \
             patch('mic_50_90.empirical.linprog', side_effect=AssertionError('planner called linprog')), \
             patch('mic_50_90.empirical.milp', side_effect=AssertionError('planner called milp')):
            results = [call(ordinary), call(synergy), call(cases['single-forbidden-target'])]
        assert [r['status'] for r in results] == ['optimal', 'optimal', 'impossible']
        return dict(statuses=[r['status'] for r in results])

    record('no-numerical-solver-required', no_solver)

    def large_costs():
        try:
            result = call(queries=[dict(threshold=t, unit='mg/L', cost='1e308') for t in (2, 4, 8)])
        except ValueError as exc:
            return dict(explicit_refusal=str(exc))
        assert result['status'] in {'optimal', 'incomplete'}
        assert Fraction(result['worst_case_cost_exact']) >= 2 * Fraction('1e308')
        return dict(status=result['status'], cost=result['worst_case_cost_exact'])

    record('large-finite-costs-exact-sum', large_costs)
    return records


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    folder = args.output.resolve() / 'planning_controls'
    started = perf_counter()
    clock = perf_counter()
    controlled_rows, design = controlled()
    controlled_seconds = perf_counter() - clock
    clock = perf_counter()
    cases = stress_cases()
    stress_rows = stress(cases)
    stress_seconds = perf_counter() - clock
    clock = perf_counter()
    records = contract(cases)
    contract_seconds = perf_counter() - clock

    def part(rows, seconds, **extra):
        return dict(tasks=len(rows), agreements=sum(r['agrees'] for r in rows), disagreements=sum(not r['agrees'] for r in rows),
                    status_counts=dict(Counter(r.get('status', 'raised') for r in rows)),
                    oracle_status_counts=dict(Counter(r['oracle_status'] for r in rows)),
                    checked_histogram_paths=sum(r.get('histogram_paths', 0) for r in rows),
                    checked_witnesses=sum(bool(r.get('witness_checked')) for r in rows),
                    seconds=seconds, failures=[r for r in rows if not r['agrees']][:10], **extra)

    summary = dict(comparison='planning_controls', created_utc=now(), status='complete', full_design=True,
                   elapsed_seconds=perf_counter() - started, environment=common.environment(),
                   limits=LIMITS, stress_seed=STRESS_SEED,
                   controlled=part(controlled_rows, controlled_seconds, **design),
                   stress=part(stress_rows, stress_seconds, method_counts=dict(Counter(r.get('method', 'raised') for r in stress_rows))),
                   contract=dict(controls=len(records), passed=sum(r['passed'] for r in records),
                                 failed=[r for r in records if not r['passed']], seconds=contract_seconds))
    summary['all_agree'] = (not summary['controlled']['disagreements'] and not summary['stress']['disagreements']
                            and not summary['contract']['failed'])
    write_csv(folder / 'controlled.csv.gz', controlled_rows)
    write_csv(folder / 'stress.csv.gz', stress_rows)
    write_json(folder / 'contract.json', records)
    write_json(folder / 'summary.json', summary)
    print(json.dumps({key: {k: v for k, v in summary[key].items() if k != 'failures'} for key in ('controlled', 'stress', 'contract')}, indent=1))


if __name__ == '__main__':
    main()
