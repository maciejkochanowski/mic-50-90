"""Choice of the selection rule for the count to request, on the development block (protocols/NEXT_COUNT.md).

Candidate rules are compared with the independent calculation of next_count.py only; the program is not
run. Every rule first takes the count with the largest guaranteed reduction. The rules differ in what they
do when counts are equal on that measure, which includes every task in which no count guarantees a reduction.

Output: OUTPUT/next_count/rule_comparison.json.
"""
from __future__ import annotations

import common

import statistics
from fractions import Fraction
from multiprocessing import Pool

import next_count
from common import HERE, now, sha256, write_json

BLOCK = 'development'


def keys(check, j):
    """Per candidate count: largest width left, average width left, boundaries from the category and from the median."""
    out = {}
    for q in check['worst']:
        prefix = q + 1
        out[q] = dict(worst=check['worst'][q][j], mean=Fraction(check['total'][q][j], check['values'][q]),
                      near=min(abs(prefix - j), abs(prefix - (j + 1))), median=check['from_median'][prefix],
                      spread=check['spread'][q])
    return out


def widest_when_no_guarantee(k, w0):
    if min(v['worst'] for v in k.values()) < w0:
        return min(k, key=lambda q: (k[q]['worst'], q))
    return max(k, key=lambda q: (k[q]['spread'], -q))


RULES = {
    'guarantee, then the widest open count': widest_when_no_guarantee,
    'guarantee, average': lambda k, w0: min(k, key=lambda q: (k[q]['worst'], k[q]['mean'], q)),
    'guarantee, average, nearest (lower count on ties)': lambda k, w0: min(k, key=lambda q: (k[q]['worst'], k[q]['mean'], k[q]['near'], q)),
    'guarantee, average, nearest (higher count on ties)': lambda k, w0: min(k, key=lambda q: (k[q]['worst'], k[q]['mean'], k[q]['near'], -q)),
    'guarantee, average, nearest, side of the median': lambda k, w0: min(k, key=lambda q: (k[q]['worst'], k[q]['mean'], k[q]['near'], k[q]['median'], q)),
}
SELECTED = 'guarantee, average, nearest, side of the median'


def cohort_rows(cohort):
    counts = [int(c) for c in cohort['counts']]
    check = next_count.independent(counts)
    rows = []
    for j, (low, high) in enumerate(check['before']):
        w0 = high - low
        if not w0 or not check['worst']:
            continue
        k = keys(check, j)
        realized = {q: check['after'][q][j][1] - check['after'][q][j][0] for q in k}
        best = min(realized.values())
        row = dict(guaranteed=min(v['worst'] for v in k.values()) < w0, best=1 - best / w0)
        for name, rule in RULES.items():
            q = rule(k, w0)
            row[name] = (1 - realized[q] / w0, realized[q] == 0, realized[q] == best)
        rows.append(row)
    return rows


def describe(rows, name):
    values = [r[name][0] for r in rows]
    q = statistics.quantiles(values, n=4, method='inclusive')
    return dict(tasks=len(rows), median=statistics.median(values), lower_quartile=q[0], upper_quartile=q[2],
                mean=statistics.fmean(values), fixed_exactly=sum(r[name][1] for r in rows),
                best_single_count=sum(r[name][2] for r in rows))


def main():
    args = common.parser(__doc__).parse_args()
    folder = args.output.resolve() / 'next_count'
    folder.mkdir(parents=True, exist_ok=True)
    cohorts = next_count.block_cohorts(BLOCK)
    with Pool(args.workers) as pool:
        rows = [r for part in pool.map(cohort_rows, cohorts, chunksize=4) for r in part]
    open_rows = [r for r in rows if not r['guaranteed']]
    best = [r['best'] for r in rows]
    summary = dict(
        comparison='next_count_rules', created_utc=now(), environment=common.environment(),
        protocol='protocols/NEXT_COUNT.md', next_count_protocol_sha256=sha256(HERE / 'protocols' / 'NEXT_COUNT.md'),
        block=BLOCK, hash_ranks=list(next_count.BLOCKS[BLOCK]), report='R2', cohorts=len(cohorts), tasks=len(rows),
        tasks_without_a_guaranteed_reduction=len(open_rows), selected_rule=SELECTED,
        rules={name: dict(all_tasks=describe(rows, name), without_a_guaranteed_reduction=describe(open_rows, name))
               for name in RULES},
        best_single_count_known_afterwards=dict(median=statistics.median(best), mean=statistics.fmean(best)))
    write_json(folder / 'rule_comparison.json', summary)
    for name in RULES:
        a, b = summary['rules'][name]['all_tasks'], summary['rules'][name]['without_a_guaranteed_reduction']
        print('%-52s median %.3f  best count in %4d of %d | no guarantee: median %.3f' % (
            name, a['median'], a['best_single_count'], a['tasks'], b['median']))


if __name__ == '__main__':
    main()
