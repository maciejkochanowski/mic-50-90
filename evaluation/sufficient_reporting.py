"""Counts sufficient to verify a report: direct reporting, greedy deletion and minimal sufficient reports.

Sixty complete-category drug cohorts (30 FDA animal-pathogen, 30 NORM 2024 human) are summarized
by ceiling-rank MIC50 and MIC90. For each cohort and each criterion (below 5%, 10% and 20%) the
task asks, for every internal panel boundary, whether the share strictly above it lies below the
criterion: 180 tasks and 1809 threshold answers. Three rules choose which cumulative counts to send:

  direct   a count for every threshold the summaries leave unresolved;
  greedy   the direct counts, deleting each one that the others make redundant (ascending cut order);
  minimal  the minimum-cost sufficient report found by plan_reporting (unit cost per count).

Every report is checked by the recipient (verify_reporting, without the histogram) and against the
exact answers from the complete counts. A constructed ten-isolate example with unequal costs shows
that greedy deletion need not minimise cost.

Output: OUTPUT/sufficient_reporting/summary.json and tasks.csv.
"""
from __future__ import annotations

import common

import json
from collections import Counter
from fractions import Fraction
from time import perf_counter

from common import DATA, now, read_json, write_csv, write_json

FRACTIONS = ('0.05', '0.10', '0.20')


def tasks(cohorts):
    from mic_50_90 import plan_reporting, verify_reporting
    from mic_50_90.model import parse_spec
    records, totals = [], Counter()
    for item in cohorts:
        spec, h = item['specification'], item['histogram']
        parsed = parse_spec(spec)
        tail = {t: int(parsed.panel.panel_tail(t) @ h) for t in spec['thresholds']}
        for fraction in FRACTIONS:
            criteria = [dict(threshold=t, unit='mg/L', decision_operator='<', decision_fraction=fraction) for t in spec['thresholds']]
            initial = verify_reporting(spec, criteria, [])
            direct = [dict(threshold=t, unit='mg/L', n=spec['n'], count=tail[t])
                      for t, status in zip(spec['thresholds'], initial['decisions']) if status == 'undetermined']
            greedy = list(direct)
            for candidate in direct:
                trial = [r for r in greedy if r is not candidate]
                if verify_reporting(spec, criteria, trial)['sufficient']:
                    greedy = trial
            plan = plan_reporting(spec, h, criteria, time_limit_seconds=10, max_states=50000)
            check = verify_reporting(spec, criteria, plan['disclosures'])
            truth = ['supported' if Fraction(tail[t], spec['n']) < Fraction(fraction) else 'contradicted' for t in spec['thresholds']]
            row = dict(cohort_id=item['cohort_id'], source=item['source'], n=spec['n'], fraction=fraction, answers=len(criteria),
                       direct_fields=len(direct), greedy_fields=len(greedy), minimal_fields=len(plan['disclosures']),
                       optimality_verified=plan['optimality_verified'], recipient_sufficient=check['sufficient'],
                       minimal_correct=check['decisions'] == truth,
                       direct_correct=verify_reporting(spec, criteria, direct)['decisions'] == truth,
                       greedy_correct=verify_reporting(spec, criteria, greedy)['decisions'] == truth,
                       disclosures=json.dumps(plan['disclosures']))
            records.append(row)
            totals.update(tasks=1, answers=len(criteria), direct_fields=len(direct), greedy_fields=len(greedy),
                          minimal_fields=len(plan['disclosures']), summaries_only=int(not direct),
                          needing_counts=int(bool(direct)), fewer=int(len(plan['disclosures']) < len(direct)),
                          same=int(bool(direct) and len(plan['disclosures']) == len(direct)),
                          answers_preserved=len(criteria) * (row['minimal_correct'] and row['direct_correct'] and row['greedy_correct']),
                          optimality_verified=int(plan['optimality_verified']))
    return records, dict(totals)


def unequal_cost_example():
    """Ten isolates, ceiling MIC50 = 1 and MIC90 = 2 mg/L, one <5% question at 8 mg/L; counts at 2, 4 and 8 cost 1, 10, 10."""
    from mic_50_90 import plan_reporting, verify_reporting
    spec = {'n': 10, 'panel': {'levels': [1, 2, 4, 8, 16], 'left_censored': False, 'right_censored': False},
            'summaries': {'quantiles': [{'probability': .5, 'category': '1', 'rank': 5}, {'probability': .9, 'category': '2', 'rank': 9}]},
            'thresholds': [8], 'question_utility': {'enabled': False}}
    questions = [{'threshold': 8, 'unit': 'mg/L', 'decision_operator': '<', 'decision_fraction': '.05'}]
    h, costs, levels = [5, 5, 0, 0, 0], {2: 1, 4: 10, 8: 10}, [1, 2, 4, 8, 16]
    queries = [dict(threshold=t, unit='mg/L', cost=str(c)) for t, c in costs.items()]
    fields = [dict(threshold=t, unit='mg/L', count=sum(h[j] for j, v in enumerate(levels) if v > t), n=10) for t in costs]
    held = fields[:]
    for field in fields:
        reduced = [f for f in held if f['threshold'] != field['threshold']]
        if verify_reporting(spec, questions, reduced)['sufficient']:
            held = reduced
    optimal = plan_reporting(spec, h, questions, queries=queries)
    assert verify_reporting(spec, questions, held)['sufficient'] and optimal['optimality_verified']
    return dict(greedy_cost=sum(costs[f['threshold']] for f in held), greedy_disclosures=held,
                minimal_cost=float(optimal['report_cost']), minimal_disclosures=optimal['disclosures'])


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    folder = args.output.resolve() / 'sufficient_reporting'
    cohorts = read_json(DATA / 'reporting_cohorts.json')
    assert len(cohorts) == 60
    started = perf_counter()
    records, totals = tasks(cohorts)
    example = unequal_cost_example()
    sources = {}
    for source in sorted({r['source'] for r in records}):
        mine = [r for r in records if r['source'] == source and r['minimal_fields'] < r['direct_fields']]
        sources[source] = dict(tasks_with_fewer_fields=len(mine), direct_fields=sum(r['direct_fields'] for r in mine),
                               minimal_fields=sum(r['minimal_fields'] for r in mine))
    write_csv(folder / 'tasks.csv', records)
    write_json(folder / 'summary.json', dict(comparison='sufficient_reporting', created_utc=now(), status='complete', full_design=True,
               elapsed_seconds=perf_counter() - started, environment=common.environment(), cohorts=len(cohorts),
               totals=totals, all_answers_preserved=totals['answers_preserved'] == totals['answers'],
               improvements_by_source=sources, unequal_cost_example=example))
    print(json.dumps(dict(totals=totals, example={k: v for k, v in example.items() if 'cost' in k}), indent=1))


if __name__ == '__main__':
    main()
