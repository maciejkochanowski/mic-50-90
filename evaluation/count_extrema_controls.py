"""Finite controls of count extrema and P5 rows against explicit histogram enumeration.

Count reports. For n = 1 to 6 isolates and K = 2 to 4 categories, every histogram gives one
report of its ceiling-rank MIC50 and MIC90 categories, once without and once with the exact
lowest and highest categories (268 distinct nonempty reports). The oracle lists the compatible
histograms by indexing the sorted observations. For every report and every contiguous range of
categories (2086 range-endpoint pairs) the package must return the enumerated minimum and maximum
count, with compatible attaining histograms, from both the integer program (EmpiricalProblem.bounds)
and the closed difference bounds; the P5 rows (the attaining tables built from the cumulative-count
closure, one per boundary, 1182 in all) must be compatible histograms that attain both extrema.
Cumulative tails are also compared with the closed-form tail counts. Every MIC50/MIC90 category
pair (154 feasibility decisions, 50 of them infeasible) must be accepted exactly when some
histogram matches it.

Additional count constraints. 160 seeded reports (K <= 5), each with two extra count intervals
on random subsets of categories. For every cumulative tail and one alternating weighted objective
(720 objective pairs) the integer extrema must equal enumeration, and where the constraint matrix
is totally unimodular a split of the count cell must partition the compatible histograms.

Output: OUTPUT/count_extrema/summary.json.
"""
from __future__ import annotations

import common

import json
from collections import Counter, defaultdict
from decimal import Decimal
from functools import lru_cache
from itertools import product
from time import perf_counter

import numpy as np

from common import now, write_json

SEED = 61007


@lru_cache(None)
def histograms(n, k):
    if k == 1:
        return ((n,),)
    return tuple((x,) + h for x in range(n + 1) for h in histograms(n - x, k - 1))


@lru_cache(None)
def panel(k):
    from mic_50_90.model import MICBin, MICPanel
    return MICPanel(tuple(MICBin(str(2**j), 2**j, 2**j, True, True, 2**j) for j in range(k)))


def range_mask(k, a, b):
    return np.array([int(a <= j < b) for j in range(k)])


def ranks(n):
    return sorted({(n + 1) // 2, (9 * n + 9) // 10})


def report_key(h, with_extrema=False):
    ordered = [j for j, count in enumerate(h) for _ in range(count)]
    base = tuple((r, ordered[r - 1]) for r in ranks(sum(h)))
    return (base, ordered[0], ordered[-1]) if with_extrema else (base, None, None)


def matches(h, key):
    summaries, lo, hi = key
    ordered = [j for j, count in enumerate(h) for _ in range(count)]
    return (all(ordered[r - 1] == j for r, j in summaries) and (lo is None or ordered[0] == lo) and (hi is None or ordered[-1] == hi))


def make_problem(n, k, key, rows=()):
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import QuantileSummary
    summaries, lo, hi = key
    quantiles = [QuantileSummary(probability=str(Decimal(r) / Decimal(n)), rank=r, category_index=j,
                                 category_label=panel(k).bins[j].label, convention='explicit-rank') for r, j in summaries]
    return EmpiricalProblem(n=n, panel=panel(k), quantiles=quantiles, minimum_index=lo, maximum_index=hi, count_intervals=rows)


class Checks:
    def __init__(self):
        self.stats, self.failures = Counter(), []

    def __call__(self, condition, message, context):
        self.stats['checks'] += 1
        if not condition:
            self.failures.append(dict(message=message, context=json.loads(json.dumps(context, default=str))))


def count_reports(check):
    from mic_50_90.empirical import closed_form_tail_counts
    from mic_50_90.utility import _prefix_distances
    stats = check.stats
    for n in range(1, 7):
        for k in range(2, 5):
            hs = histograms(n, k)
            grouped = defaultdict(list)
            for h in hs:
                for extrema in (False, True):
                    grouped[report_key(h, extrema)].append(h)
            for key, feasible in grouped.items():
                problem = make_problem(n, k, key)
                stats['nonempty_reports'] += 1
                d = _prefix_distances(problem)
                rows = [tuple(int(x) for x in np.diff(row)) for row in d]
                for row in rows:
                    check(row in feasible, 'P5 row is not compatible with the report', [n, k, key, row])
                    stats['P5_rows'] += 1
                check(rows[0] == rows[-1] and len(set(rows)) <= k, 'P5 rows: first and last differ or too many distinct rows', [n, k, key])
                for a in range(k):
                    for b in range(a + 1, k + 1):
                        values = [sum(h[a:b]) for h in feasible]
                        expected = min(values), max(values)
                        got = problem.bounds(range_mask(k, a, b))
                        check(tuple(x.count for x in got) == expected, 'integer range extrema differ from enumeration', [n, k, key, a, b])
                        check(all(x.histogram in feasible for x in got), 'attaining histogram is not compatible', [n, k, key, a, b])
                        check((-int(d[b, a]), int(d[a, b])) == expected, 'closed difference bounds differ from enumeration', [n, k, key, a, b])
                        check(sum(rows[a][a:b]) == expected[1] and sum(rows[b][a:b]) == expected[0],
                              'P5 rows do not attain the count extrema', [n, k, key, a, b])
                        stats['range_endpoint_pairs'] += 1
                        if b == k:
                            closed = closed_form_tail_counts(n=n, tail=range_mask(k, a, b), quantiles=problem.quantiles,
                                                             minimum_index=key[1], maximum_index=key[2])
                            check(closed == expected, 'closed-form tail differs from enumeration', [n, k, key, a])
                            stats['closed_form_tail_pairs'] += 1
            for cats in product(range(k), repeat=len(ranks(n))):
                key = (tuple(zip(ranks(n), cats)), None, None)
                feasible = [h for h in hs if matches(h, key)]
                try:
                    make_problem(n, k, key)
                    accepted = True
                except ValueError:
                    accepted = False
                check(accepted == bool(feasible), 'report feasibility differs from enumeration', [n, k, key])
                stats['feasibility_decisions'] += 1
                stats['infeasible_reports'] += not feasible


def additional_counts(check):
    from mic_50_90.range_certificates import split_count_cell
    from mic_50_90.utility import _prefix_distances
    stats = check.stats
    rng = np.random.default_rng(SEED)
    for case in range(160):
        n, k = 1 + case % 6, 2 + case % 4
        hs = histograms(n, k)
        truth = hs[int(rng.integers(len(hs)))]
        key = report_key(truth, bool(case % 2))
        rows = []
        for _ in range(2):
            mask = rng.integers(0, 2, k)
            value = sum(x * y for x, y in zip(mask, truth))
            lo, hi = max(0, value - int(rng.integers(3))), min(n, value + int(rng.integers(3)))
            rows.append((mask, lo, hi))
        feasible = [h for h in hs if matches(h, key) and all(lo <= sum(x * y for x, y in zip(mask, h)) <= hi for mask, lo, hi in rows)]
        problem = make_problem(n, k, key, rows)
        stats['augmented_reports'] += 1
        stats['augmented_noncanonical_reports'] += not problem.has_total_unimodular_canonical_matrix
        for mask in [range_mask(k, a, k) for a in range(k)] + [np.array([(-1)**j * (j + 1) for j in range(k)])]:
            values = [sum(x * y for x, y in zip(mask, h)) for h in feasible]
            got = problem.bounds(mask)
            check(tuple(x.count for x in got) == (min(values), max(values)), 'extrema under extra counts differ from enumeration',
                  [case, n, k, mask.tolist()])
            check(all(x.histogram in feasible for x in got), 'attaining histogram under extra counts is not compatible', case)
            stats['augmented_objective_pairs'] += 1
        if problem.has_total_unimodular_canonical_matrix:
            d = _prefix_distances(problem)
            children = split_count_cell(d.astype(int).tolist())
            if children:
                supports = []
                for child in children:
                    support = set()
                    for h in hs:
                        s = [0] + list(np.cumsum(h))
                        if all(s[b] - s[a] <= child[a][b] for a in range(k + 1) for b in range(k + 1)):
                            support.add(h)
                    supports.append(support)
                check(set.union(*supports) == set(feasible) and not set.intersection(*supports),
                      'count-cell split is not an exact partition', case)
                stats['count_partitions'] += 1


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    folder = args.output.resolve() / 'count_extrema'
    started = perf_counter()
    check = Checks()
    count_reports(check)
    additional_counts(check)
    counts = dict(check.stats)
    checks = counts.pop('checks')
    write_json(folder / 'summary.json', dict(
        comparison='count_extrema', created_utc=now(), status='complete', full_design=True,
        elapsed_seconds=perf_counter() - started, environment=common.environment(), seed=SEED,
        counts=counts, checks=checks, failed_checks=len(check.failures), all_agree=not check.failures, failures=check.failures[:50]))
    print(json.dumps(dict(counts=counts, checks=checks, failed_checks=len(check.failures), seconds=round(perf_counter() - started, 1)), indent=1))


if __name__ == '__main__':
    main()
