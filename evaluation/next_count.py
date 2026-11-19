"""The count to request, on real collections (protocols/NEXT_COUNT.md).

Each cohort of one block of the eligible cohorts is shortened to MIC50, MIC90 and the observed range
(report R2). For every category that the report leaves open, the program is asked how many isolates the
category holds and names one cumulative count to request. The complete table supplies that count, and the
category is bounded again. Every other open cumulative count is added in the same way for comparison.

An independent calculation (difference constraints on cumulative counts, closed by Floyd-Warshall; no
program code) recomputes every bound, the largest and the average width that each candidate count can
leave, and the count that the selection rule of the protocol names.

Blocks (hash ranks within a stratum): benchmark 1-10, confirmation 11-20, development 21-30.
Output: OUTPUT/next_count/BLOCK/tasks.jsonl.gz (one line per task) and summary.json.
"""
from __future__ import annotations

import common

import csv
import gzip
import json
import math
import statistics
from fractions import Fraction
from multiprocessing import Pool
from time import perf_counter

import numpy as np

import benchmark
from common import HERE, now, sha256, write_json

PROTOCOL = HERE / 'protocols' / 'NEXT_COUNT.md'
INF = 10 ** 9
BLOCKS = {'benchmark': (1, 10), 'confirmation': (11, 20), 'development': (21, 30)}


def block_cohorts(block):
    """Eligible cohorts of one block, in the order of the eligible list (stratum, then hash rank)."""
    first, last = BLOCKS[block]
    with gzip.open(benchmark.BENCHMARK / 'eligible.csv.gz', 'rt', encoding='utf-8', newline='') as handle:
        rows = [r for r in csv.DictReader(handle) if not r['reason'] and first <= int(r['rank']) <= last]
    return [dict(cohort_id=r['cohort_id'], counts=json.loads(r['counts']), low=int(r['low']), high=int(r['high']))
            for r in rows]


def closure(k, n, constraints):
    """All-pairs tightest bounds for F_v - F_u <= w on prefix counts F_0..F_k (Floyd-Warshall)."""
    d = np.full((k + 1, k + 1), INF, dtype=np.int64)
    np.fill_diagonal(d, 0)
    for u, v, w in constraints:
        d[u, v] = min(d[u, v], w)
    for m in range(k + 1):
        d = np.minimum(d, d[:, m:m + 1] + d[m:m + 1, :])
    if (np.diag(d) < 0).any():
        raise ValueError('no table fits the report')
    return d


def report_constraints(counts):
    """Report R2 of a complete table as difference constraints (u, v, w): F_v - F_u <= w."""
    counts = [int(c) for c in counts]
    n, k = sum(counts), len(counts)
    prefix = [0]
    for c in counts:
        prefix.append(prefix[-1] + c)
    rows = [(0, k, n), (k, 0, -n)]
    rows += [(i + 1, i, 0) for i in range(k)]                      # every count is at least zero
    for p in (0.5, 0.9):
        rank = math.ceil(round(p * n, 9))
        c = next(i for i in range(k) if prefix[i + 1] >= rank)      # category of the rank-th result
        rows += [(0, c, rank - 1), (c + 1, 0, -rank)]               # F_c <= rank - 1 and F_{c+1} >= rank
    occupied = [i for i, c in enumerate(counts) if c]
    a, b = occupied[0], occupied[-1]
    rows += [(0, a, 0), (a + 1, 0, -1)]                             # nothing below category a, at least one in it
    rows += [(b + 1, k, 0), (0, b, n - 1)]                          # nothing above category b, at least one in it
    return n, k, prefix, rows


def widths(d, k):
    """Smallest and largest count of every category from a closed constraint matrix."""
    upper = np.array([d[j, j + 1] for j in range(k)])
    lower = np.array([-d[j + 1, j] for j in range(k)])
    return lower, upper


def independent(counts):
    """Bounds before and after every cumulative count, and what each count can leave over all its values."""
    n, k, prefix, rows = report_constraints(counts)
    base = closure(k, n, rows)
    lower, upper = widths(base, k)
    after, worst, total, values, spread = {}, {}, {}, {}, {}
    for q in range(1, k):                                           # F_q, the count at or below category q-1
        low, high = int(-base[q, 0]), int(base[0, q])
        if low == high:
            continue
        d = closure(k, n, rows + [(0, q, prefix[q]), (q, 0, -prefix[q])])
        lo, hi = widths(d, k)
        after[q - 1] = [[int(x), int(y)] for x, y in zip(lo, hi)]
        answers = np.arange(low, high + 1, dtype=np.int64)
        stack = np.repeat(base[None, :, :], len(answers), axis=0)
        stack[:, 0, q] = np.minimum(stack[:, 0, q], answers)
        stack[:, q, 0] = np.minimum(stack[:, q, 0], -answers)
        for m in range(k + 1):
            stack = np.minimum(stack, stack[:, :, m:m + 1] + stack[:, m:m + 1, :])
        feasible = ~(np.diagonal(stack, axis1=1, axis2=2) < 0).any(axis=1)
        assert feasible.all(), 'every value between the bounds of a cumulative count is reachable'
        index = np.arange(k)
        width = stack[:, index, index + 1] + stack[:, index + 1, index]
        worst[q - 1] = [int(x) for x in width.max(axis=0)]
        total[q - 1] = [int(x) for x in width.sum(axis=0)]
        values[q - 1] = len(answers)
        spread[q - 1] = high - low
    # Boundaries between each prefix index and the median: above it when at least half of the isolates are
    # certainly at or below the boundary, below it when fewer than half can be.
    rank = math.ceil(n / 2)
    above = [i for i in range(k + 1) if -base[i, 0] >= rank]
    below = [i for i in range(k + 1) if base[0, i] < rank]
    from_median = [i - min(above) + 1 if i in above else max(below) - i + 1 if i in below else 0 for i in range(k + 1)]
    return dict(before=[[int(x), int(y)] for x, y in zip(lower, upper)], after=after, worst=worst, total=total,
                values=values, spread=spread, from_median=from_median)


def rule_choice(check, j):
    """The count that the selection rule of the protocol names for category j (independent calculation)."""
    def key(q):                                                     # q is the category index of the cut
        prefix = q + 1
        return (check['worst'][q][j], Fraction(check['total'][q][j], check['values'][q]),
                min(abs(prefix - j), abs(prefix - (j + 1))), check['from_median'][prefix], q)
    return min(check['worst'], key=key)


def bounds(result):
    return [[r['count_lower'], r['count_upper']] for r in result['sample']['categories']]


def cumulative(labels, n, q, value):
    return dict(start_category=labels[0], end_category=labels[q], n=n, count=int(value), unit='mg/L',
                source='Complete table of the cohort')


def cohort_tasks(cohort):
    from mic_50_90.distribution_workflow import analyse_distribution
    counts = [int(c) for c in cohort['counts']]
    spec = benchmark.report(cohort['cohort_id'], counts, cohort['low'], cohort['high'], 'R2')
    spec['iid'] = False
    spec.pop('confidence_level', None)
    labels = [c['label'] for c in spec['panel']['categories']]
    n, k = sum(counts), len(counts)
    prefix = np.cumsum(counts)
    check = independent(counts)
    plain = analyse_distribution(json.loads(json.dumps(spec)))
    before = bounds(plain)
    mismatches = int(before != check['before'])
    open_cuts = [r['index'] for r in plain['sample']['cdf'] if r['count_lower'] < r['count_upper']]
    mismatches += int(sorted(open_cuts) != sorted(check['after']))
    after = {}
    for q in open_cuts:
        updated = json.loads(json.dumps(spec))
        updated['additional_counts'] = [cumulative(labels, n, q, prefix[q])]
        after[q] = bounds(analyse_distribution(updated))
        mismatches += int(after[q] != check['after'].get(q))
    tasks = []
    for j, (low, high) in enumerate(before):
        if low == high:
            continue
        asked = json.loads(json.dumps(spec))
        asked['targets'] = [dict(start_category=labels[j], end_category=labels[j], unit='mg/L')]
        suggestion = analyse_distribution(asked)['interpretation']['suggested_count']
        cut = suggestion['recorded_groups'] - 1
        w0 = high - low
        width = {q: after[q][j][1] - after[q][j][0] for q in open_cuts}
        worst = {q: check['worst'][q][j] for q in open_cuts}
        guaranteed = w0 - min(worst.values())
        text = suggestion['selection_rule']
        rule = ('guaranteed' if text.startswith('Largest guaranteed reduction') else
                'average' if text.startswith('Largest average reduction') else 'widest')
        others = [q for q in open_cuts if q != cut]
        tasks.append(dict(
            cohort=cohort['cohort_id'], n=n, categories=k, category=j, width_before=w0, suggested_cut=cut,
            rule=rule, width_after=width[cut],
            alternatives={str(q): width[q] for q in others},
            worst_width={str(q): worst[q] for q in open_cuts},
            best_guaranteed_reduction=guaranteed,
            suggestion_has_best_guarantee=bool(worst[cut] == min(worst.values())) if guaranteed > 0 else None,
            suggestion_follows_the_rule=bool(cut == rule_choice(check, j) and (rule == 'guaranteed') == (guaranteed > 0)),
            realized_not_wider_than_guaranteed=bool(width[cut] <= worst[cut])))
    return dict(cohort=cohort['cohort_id'], tasks=tasks, mismatches=mismatches,
                comparisons=1 + 1 + len(open_cuts), program_calls=1 + len(open_cuts) + len(tasks))


def quartiles(values):
    q = statistics.quantiles(values, n=4, method='inclusive')
    return dict(median=statistics.median(values), lower_quartile=q[0], upper_quartile=q[2])


def describe(tasks):
    with_others = [t for t in tasks if t['alternatives']]
    reduction = [1 - t['width_after'] / t['width_before'] for t in tasks]
    mean_other = [statistics.fmean(1 - w / t['width_before'] for w in t['alternatives'].values()) for t in with_others]
    best = [1 - min([t['width_after'], *t['alternatives'].values()]) / t['width_before'] for t in tasks]
    return dict(
        tasks=len(tasks), relative_reduction=quartiles(reduction), mean_relative_reduction=statistics.fmean(reduction),
        best_single_count_relative_reduction=quartiles(best),
        fixed_exactly=sum(t['width_after'] == 0 for t in tasks),
        tasks_with_alternatives=len(with_others),
        no_alternative_narrower=sum(t['width_after'] <= min(t['alternatives'].values()) for t in with_others),
        narrower_than_every_alternative=sum(t['width_after'] < min(t['alternatives'].values()) for t in with_others),
        mean_alternative_reduction=quartiles(mean_other) if mean_other else None)


def by_cohort(tasks):
    groups = {}
    for t in tasks:
        groups.setdefault(t['cohort'], []).append(t)
    reduction = [statistics.fmean(1 - t['width_after'] / t['width_before'] for t in rows) for rows in groups.values()]
    fixed = [statistics.fmean(t['width_after'] == 0 for t in rows) for rows in groups.values()]
    other = [statistics.fmean(statistics.fmean(1 - w / t['width_before'] for w in t['alternatives'].values())
                              for t in rows if t['alternatives']) for rows in groups.values()
             if any(t['alternatives'] for t in rows)]
    return dict(cohorts=len(groups), relative_reduction=quartiles(reduction), share_fixed_exactly=quartiles(fixed),
                mean_alternative_reduction=quartiles(other))


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--block', choices=sorted(BLOCKS), required=True)
    parser.add_argument('--limit', type=int, help='first cohorts only (for a trial run; not a result)')
    args = parser.parse_args()
    folder = args.output.resolve() / 'next_count' / args.block
    folder.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    cohorts = block_cohorts(args.block)
    full = args.limit is None
    if not full:
        cohorts = cohorts[:args.limit]
    with Pool(args.workers) as pool:
        rows = pool.map(cohort_tasks, cohorts, chunksize=1)
    tasks = [t for row in rows for t in row['tasks']]
    with gzip.open(folder / 'tasks.jsonl.gz', 'wt', encoding='utf-8') as handle:
        for t in tasks:
            handle.write(json.dumps(t, sort_keys=True) + '\n')
    rules = ('guaranteed', 'average', 'widest')
    guaranteed = [t for t in tasks if t['suggestion_has_best_guarantee'] is not None]
    summary = dict(
        comparison='next_count', created_utc=now(), status='complete', full_design=full,
        elapsed_seconds=perf_counter() - started, environment=common.environment(),
        protocol='protocols/NEXT_COUNT.md', next_count_protocol_sha256=sha256(PROTOCOL),
        block=args.block, hash_ranks=list(BLOCKS[args.block]),
        report='R2', cohorts=len(cohorts), cohorts_with_tasks=len({t['cohort'] for t in tasks}),
        program_calls=sum(row['program_calls'] for row in rows),
        selection_rule={rule: sum(t['rule'] == rule for t in tasks) for rule in rules},
        all_tasks=describe(tasks), cohorts_equal_weight=by_cohort(tasks),
        by_rule={rule: describe([t for t in tasks if t['rule'] == rule]) for rule in rules
                 if any(t['rule'] == rule for t in tasks)},
        independent_check=dict(
            bound_comparisons=sum(row['comparisons'] for row in rows),
            bound_mismatches=sum(row['mismatches'] for row in rows),
            tasks_with_a_guaranteed_reduction=len(guaranteed),
            suggestion_has_best_guarantee=sum(t['suggestion_has_best_guarantee'] for t in guaranteed),
            suggestion_follows_the_rule=sum(t['suggestion_follows_the_rule'] for t in tasks),
            realized_not_wider_than_guaranteed=sum(t['realized_not_wider_than_guaranteed'] for t in tasks)))
    summary['all_agree'] = (summary['independent_check']['bound_mismatches'] == 0
                            and summary['independent_check']['suggestion_has_best_guarantee'] == len(guaranteed)
                            and summary['independent_check']['suggestion_follows_the_rule'] == len(tasks)
                            and summary['independent_check']['realized_not_wider_than_guaranteed'] == len(tasks))
    write_json(folder / 'summary.json', summary)
    print(json.dumps({key: summary[key] for key in ('block', 'cohorts', 'cohorts_with_tasks', 'program_calls', 'selection_rule',
                                                    'all_tasks', 'cohorts_equal_weight', 'independent_check', 'all_agree')}, indent=1))


if __name__ == '__main__':
    main()
