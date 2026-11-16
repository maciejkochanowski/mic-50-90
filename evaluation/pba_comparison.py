"""Comparison with an independent probability-bounds (PBA) implementation on a finite domain.

Four methods receive the same information: n, the point panel (1, 2, 4, 8 mg/L), the ranks and
categories of the two order statistics that define MIC50 and MIC90, and optionally one cumulative
count. The domain covers n = 2 to 12, all sixteen category pairs, two rank conventions (ceiling and
upper-adjacent), no count or every possible count at each internal cut, and nine thresholds:
8800 inputs in all.

  oracle      exhaustive enumeration of every histogram (1815 in all) and its ordered sample;
  cdf         an independent monotone cumulative-count calculation;
  mic-50-90   EmpiricalProblem.bounds from the installed package;
  pba         unmodified PBA-for-Python 0.90.4 (pip install pba==0.90.4): every restriction
              becomes a p-box of interval-valued ordered observations; boxes are combined with
              the library's own imposition and tail probabilities are read from the result.

Each method must refuse exactly the infeasible inputs and return the oracle's tail-count interval
for every threshold of every feasible input. The comparison tests agreement, not interval width.

Output: OUTPUT/pba_comparison/summary.json, tasks.csv.gz and targets.csv.gz.
"""
from __future__ import annotations

import common

import csv
import gzip
import importlib.metadata
import json
from collections import Counter
from itertools import product
from time import perf_counter

import numpy as np

from common import now, write_json

VALUES = np.asarray([1, 2, 4, 8])
THRESHOLDS = (0.5, 1, 1.5, 2, 3, 4, 6, 8, 9)
TOLERANCE = 1e-12
PBA_VERSION = '0.90.4'


def compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for first in range(n + 1):
            for rest in compositions(n - first, k - 1):
                yield (first,) + rest


def oracle_summaries(histograms, ranks, categories):
    """Check the expanded ordered sample; no prefix inequalities are built."""
    result = []
    for h in histograms:
        ordered = [j for j, count in enumerate(h) for _ in range(count)]
        if all(ordered[r - 1] == j for r, j in zip(ranks, categories)):
            result.append(h)
    return result


def cdf_bounds(n, ranks, categories, query):
    lower, upper = [0] * 5, [n] * 5
    lower[4], upper[0] = n, 0
    for r, j in zip(ranks, categories):
        upper[j] = min(upper[j], r - 1)
        lower[j + 1] = max(lower[j + 1], r)
    if query is not None:
        j, count = query
        lower[j + 1] = max(lower[j + 1], count)
        upper[j + 1] = min(upper[j + 1], count)
    for j in range(1, 5):
        lower[j] = max(lower[j], lower[j - 1])
    for j in range(3, -1, -1):
        upper[j] = min(upper[j], upper[j + 1])
    if any(lo > hi for lo, hi in zip(lower, upper)):
        return None
    return [(n - upper[int(np.sum(VALUES <= t))], n - lower[int(np.sum(VALUES <= t))]) for t in THRESHOLDS]


def pba_constraint(pba, n, rank=None, category=None, query=None):
    """A rank-grid p-box for one restriction, from its quantile inequalities."""
    left, right = np.ones(n + 1), np.full(n + 1, 8.0)
    right[0] = 1.0  # zero-probability support sentinel; no empirical mass
    if rank is not None:
        left[rank:] = VALUES[category]
        right[1:rank + 1] = VALUES[category]
    if query is not None:
        category, count = query
        left[count + 1:] = VALUES[category + 1]
        right[1:count + 1] = VALUES[category]
    # The library's own evenly spaced grid avoids float-key mismatches.
    percentiles = {float(p): pba.Interval(float(lo), float(hi)) for p, lo, hi in zip(np.linspace(0, 1, n + 1), left, right)}
    return pba.from_percentiles(percentiles, steps=n + 1)


def pba_bounds(box):
    result = []
    for t in THRESHOLDS:
        # The native method gives P(X < value); the next float above t includes equality on this discrete panel.
        cdf = box.get_probability(float(np.nextafter(t, np.inf)))
        result.append((1.0 - float(cdf.right), 1.0 - float(cdf.left)))
    return result


def package_bounds(n, ranks, categories, query):
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICBin, MICPanel, QuantileSummary
    panel = MICPanel(tuple(MICBin(str(x), int(x), int(x), True, True, int(x)) for x in VALUES))
    quantiles = tuple(QuantileSummary(p, r, j, str(VALUES[j]), 'explicit-rank') for p, r, j in zip((0.5, 0.9), ranks, categories))
    equalities = [] if query is None else [(np.asarray([int(j <= query[0]) for j in range(4)]), query[1])]
    problem = EmpiricalProblem(n=n, panel=panel, quantiles=quantiles, equalities=equalities)
    cache, result = {}, []
    for t in THRESHOLDS:
        objective = tuple(int(x > t) for x in VALUES)
        if objective not in cache:
            low, high = problem.bounds(np.asarray(objective, dtype=float))
            cache[objective] = (low.count, high.count)
        result.append(cache[objective])
    return result


def main():
    parser = common.parser(__doc__, workers=False)
    parser.add_argument('--max-n', type=int, default=12, help='largest sample size (default 12; smaller values give a quick check)')
    args = parser.parse_args()
    try:
        import pba
    except ImportError:
        raise SystemExit(f'This comparison needs the external comparator: python -m pip install pba=={PBA_VERSION}')
    if importlib.metadata.version('pba') != PBA_VERSION:
        raise SystemExit(f'Expected pba {PBA_VERSION}, found {importlib.metadata.version("pba")}')
    folder = args.output.resolve() / 'pba_comparison'
    folder.mkdir(parents=True, exist_ok=True)
    task_fields = ['task_id', 'n', 'convention', 'rank50', 'rank90', 'category50', 'category90', 'query_category',
                   'query_cumulative_count', 'oracle_histograms', 'oracle_status', 'cdf_status', 'package_status', 'pba_status',
                   'package_error', 'pba_error']
    target_fields = ['task_id', 'n', 'threshold', 'oracle_lower_count', 'oracle_upper_count', 'lower_witness', 'upper_witness',
                     'cdf_lower_count', 'cdf_upper_count', 'package_lower_count', 'package_upper_count', 'pba_lower_fraction',
                     'pba_upper_fraction', 'pba_max_abs_error', 'cdf_matches', 'package_matches', 'pba_matches', 'count_width_gain']
    counts, gains, timing = Counter(), Counter(), Counter()
    discrepancies, largest, task_id = [], 0.0, 0
    started = perf_counter()
    with gzip.open(folder / 'tasks.csv.gz', 'wt', newline='', encoding='utf-8') as tf, \
            gzip.open(folder / 'targets.csv.gz', 'wt', newline='', encoding='utf-8') as gf:
        task_writer, target_writer = csv.DictWriter(tf, task_fields), csv.DictWriter(gf, target_fields)
        task_writer.writeheader()
        target_writer.writeheader()
        for n in range(2, args.max_n + 1):
            histograms = list(compositions(n, 4))
            counts['oracle_histograms'] += len(histograms)
            schemes = {'ceiling': ((n + 1) // 2, (9 * n + 9) // 10),
                       'upper-adjacent': (min(n, n // 2 + 1), min(n, 9 * n // 10 + 1))}
            for convention, ranks in schemes.items():
                for categories in product(range(4), repeat=2):
                    base = oracle_summaries(histograms, ranks, categories)
                    try:
                        base_box = pba_constraint(pba, n).imp(pba_constraint(pba, n, rank=ranks[0], category=categories[0])) \
                            .imp(pba_constraint(pba, n, rank=ranks[1], category=categories[1]))
                        base_error = ''
                    except Exception as exc:
                        base_box, base_error = None, f'{type(exc).__name__}: {exc}'
                    base_intervals = None
                    for query in [None] + [(j, c) for j in range(3) for c in range(n + 1)]:
                        task_id += 1
                        counts['tasks'] += 1
                        feasible = base if query is None else [h for h in base if sum(h[:query[0] + 1]) == query[1]]
                        counts['oracle_feasible' if feasible else 'oracle_infeasible'] += 1
                        clock = perf_counter()
                        cdf = cdf_bounds(n, ranks, categories, query)
                        timing['cdf'] += perf_counter() - clock
                        clock = perf_counter()
                        package, package_error = None, ''
                        try:
                            package = package_bounds(n, ranks, categories, query)
                        except Exception as exc:
                            package_error = f'{type(exc).__name__}: {exc}'
                        timing['package'] += perf_counter() - clock
                        clock = perf_counter()
                        result, pba_error = None, base_error
                        if base_box is not None:
                            try:
                                box = base_box if query is None else base_box.imp(pba_constraint(pba, n, query=query))
                                result = pba_bounds(box)
                            except Exception as exc:
                                pba_error = f'{type(exc).__name__}: {exc}'
                        timing['pba'] += perf_counter() - clock
                        for method, available in (('cdf', cdf is not None), ('package', package is not None), ('pba', result is not None)):
                            counts[f'{method}_feasibility_matches'] += int(available == bool(feasible))
                            if available != bool(feasible):
                                discrepancies.append(dict(task_id=task_id, method=method, kind='feasibility'))
                        task_writer.writerow(dict(zip(task_fields, [task_id, n, convention, *ranks, *categories,
                            '' if query is None else query[0], '' if query is None else query[1], len(feasible),
                            'feasible' if feasible else 'infeasible', 'feasible' if cdf else 'infeasible',
                            'feasible' if package else 'refused', 'feasible' if result else 'refused', package_error, pba_error])))
                        if not feasible:
                            continue
                        intervals = []
                        for i, threshold in enumerate(THRESHOLDS):
                            tails = [sum(c for x, c in zip(VALUES, h) if x > threshold) for h in feasible]
                            low, high = min(tails), max(tails)
                            intervals.append((low, high))
                            error = max(abs(result[i][0] - low / n), abs(result[i][1] - high / n)) if result is not None else None
                            largest = max(largest, error or 0.0)
                            matches = [cdf is not None and cdf[i] == (low, high), package is not None and package[i] == (low, high),
                                       error is not None and error <= TOLERANCE]
                            counts['target_comparisons'] += 1
                            counts['positive_width_targets' if high > low else 'zero_width_targets'] += 1
                            for method, match in zip(('cdf', 'package', 'pba'), matches):
                                counts[f'{method}_endpoint_matches'] += int(match)
                                if not match:
                                    discrepancies.append(dict(task_id=task_id, threshold=threshold, method=method, kind='endpoint'))
                            gain = '' if query is None else (base_intervals[i][1] - base_intervals[i][0]) - (high - low)
                            if query is not None:
                                gains['positive' if gain > 0 else 'zero' if gain == 0 else 'negative'] += 1
                            target_writer.writerow(dict(zip(target_fields, [task_id, n, threshold, low, high,
                                ';'.join(map(str, feasible[tails.index(low)])), ';'.join(map(str, feasible[tails.index(high)])),
                                *(cdf[i] if cdf else ('', '')), *(package[i] if package else ('', '')),
                                *(result[i] if result else ('', '')), error, *matches, gain])))
                        if query is None:
                            base_intervals = intervals
            print(json.dumps(dict(completed_n=n, tasks=task_id, discrepancies=len(discrepancies))), flush=True)
    write_json(folder / 'summary.json', dict(comparison='pba_comparison', created_utc=now(), status='complete',
               full_design=args.max_n == 12, settings=dict(max_n=args.max_n, thresholds=list(THRESHOLDS), panel=VALUES.tolist()),
               elapsed_seconds=perf_counter() - started, environment=common.environment() | dict(pba=importlib.metadata.version('pba')),
               counts=dict(counts), count_width_gain_from_additional_count=dict(gains),
               maximum_pba_fraction_error=largest, timing_seconds=dict(timing), discrepancies=discrepancies,
               all_agree=not discrepancies))
    print(json.dumps(dict(counts=dict(counts), gains=dict(gains), maximum_pba_fraction_error=largest), indent=1))
    if discrepancies:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
