"""Controlled reports: statistical narrowing by the range-calibrated cutoff and endpoint checks.

The 144 controlled reports combine two panel sizes (K = 5, 8), four sample sizes (n = 10, 20, 50,
100), six histogram profiles and three information patterns (summaries only, summaries with two
cumulative counts, summaries with one interior count).

1. Cutoff comparison. For every report and every proper contiguous range (3528 projections) the
   count bounds implied by the report are kept fixed and only the simultaneous cutoff changes:
   all-range Bonferroni (1/20 divided by the number of ranges) against the range-calibrated
   cutoff. Endpoints are inverted independently with SciPy's beta distribution.
2. Endpoint check. Range-calibrated bounds are computed for every report (0.01 percentage-point
   tolerance) and compared with an independent calculation: the compatible complete-data row
   histograms are rebuilt from the raw report rows, and HiGHS linear programs find the extreme
   range shares inside each histogram's confidence region. A report is confirmed when the
   endpoint target is met; the shape condition or a direct witness confirms it.
3. Scaling probes. Fifteen deterministic uniform-profile reports up to n = 1000 or K = 16.

Output: OUTPUT/controlled_reports/summary.json and records.json.
"""
from __future__ import annotations

import common

import json
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction as F
from functools import lru_cache
from itertools import combinations
from statistics import median
from time import monotonic, perf_counter

import numpy as np

from common import DATA, now, read_json, write_json


def problem(h, mode):
    """Controlled report from a histogram: ceiling MIC50/MIC90 rows plus the counts of the information pattern."""
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICBin, MICPanel
    n, k = sum(h), len(h)
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in range(1, k + 1)))
    rows = []
    if mode == 'full':
        rows = [(np.eye(k)[j], x, x) for j, x in enumerate(h)]
    else:
        for rank in ((n + 1) // 2, (9 * n + 9) // 10):
            index = next(j for j, count in enumerate(np.cumsum(h)) if count >= rank)
            if index:
                rows.append((np.array([int(j < index) for j in range(k)]), 0, rank - 1))
            rows.append((np.array([int(j <= index) for j in range(k)]), rank, n))
        if mode == 'two_counts':
            for b in (max(1, k // 3), min(k - 1, 2 * k // 3)):
                rows.append((np.array([int(j < b) for j in range(k)]), sum(h[:b]), sum(h[:b])))
        elif mode == 'interior':
            a, b = max(1, k // 2 - 1), min(k - 1, k // 2 + 1)
            rows.append((np.array([int(a <= j < b) for j in range(k)]), sum(h[a:b]), sum(h[a:b])))
    return EmpiricalProblem(n=n, panel=panel, quantiles=[], count_intervals=rows)


def count_closure(obj):
    """Integer shortest-path closure built from the raw report rows, independent of the package closure."""
    n, k = obj.n, obj.k
    d = [[0 if b <= a else n for b in range(k + 1)] for a in range(k + 1)]
    d[k][0] = -n
    for row, lo, hi in obj.count_intervals:
        indices = [j for j, x in enumerate(row) if x]
        assert indices == list(range(indices[0], indices[-1] + 1)) and all(row[j] == 1 for j in indices)
        a, b = indices[0], indices[-1] + 1
        d[a][b] = min(d[a][b], int(hi))
        d[b][a] = min(d[b][a], -int(lo))
    for m in range(k + 1):
        for a in range(k + 1):
            for b in range(k + 1):
                d[a][b] = min(d[a][b], d[a][m] + d[m][b])
    assert all(d[j][j] == 0 for j in range(k + 1))
    return d


@lru_cache(None)
def independent_region(h, cutoff):
    from scipy.optimize import linprog
    from scipy.stats import beta
    n, k, c = sum(h), len(h), float(F(cutoff))
    matrix, rhs = [], []
    for a in range(k):
        for b in range(a + 1, k):
            x = sum(h[a:b])
            lo = 0. if x == 0 else float(beta.ppf(c / 2, x, n - x + 1))
            hi = 1. if x == n else float(beta.isf(c / 2, x + 1, n - x))
            row = np.array([int(a <= j < b) for j in range(k)])
            matrix.extend([row, -row])
            rhs.extend([hi, -lo])
    out = []
    for a in range(k):
        for b in range(a + 1, k + 1):
            row = np.array([int(a <= j < b) for j in range(k)])
            options = dict(A_ub=matrix, b_ub=rhs, A_eq=[np.ones(k)], b_eq=[1.], bounds=(0, 1), method='highs')
            low, high = linprog(row, **options), linprog(-row, **options)
            assert low.success and high.success
            out.append([a, b, float(low.fun), float(-high.fun)])
    return out


def endpoint_check(task):
    from mic_50_90.joint_population import population_distribution
    index, item = task
    obj = problem(item['histogram'], item['information'])
    started = perf_counter()
    result = population_distribution({'a': obj}, method='range-calibrated', confidence_level=.95,
                                     time_limit_seconds=15, tolerance_pp=.01, include_intervals=True)
    seconds = perf_counter() - started
    d, k = count_closure(obj), obj.k
    histograms = sorted({tuple(d[a][j + 1] - d[a][j] for j in range(k)) for a in range(k + 1)})
    for h in histograms:
        assert sum(h) == obj.n and min(h) >= 0
        assert all(lo <= sum(x * y for x, y in zip(row, h)) <= hi for row, lo, hi in obj.count_intervals)
    regions = [independent_region(h, result['critical_score_fraction']) for h in histograms]
    largest = 0.
    for i, row in enumerate(result['interval_bounds']):
        assert all(region[i][:2] == [row['start_index'], row['stop_index']] for region in regions)
        lo, hi = min(r[i][2] for r in regions), max(r[i][3] for r in regions)
        largest = max(largest, abs(row['lower'] - lo), abs(row['upper'] - hi))
    certificate = result['population_row_lift_certificate']['status']
    return dict(index=index, case=item['case'], information=item['information'], n=obj.n, k=k, seconds=seconds,
                precision_reached=bool(result['precision_reached']), endpoint_gap_pp=result['endpoint_gap_pp'],
                shape_certificate=certificate, critical_score_fraction=result['critical_score_fraction'],
                compatible_histograms=len(histograms), independent_lp_solves=len(histograms) * k * (k + 1),
                maximum_independent_difference_pp=100 * largest)


def cutoff_comparison(reports):
    from scipy.stats import beta
    from mic_50_90.range_certificates import binomial_shape_certificate
    from mic_50_90.range_population import critical_score
    from mic_50_90.utility import _prefix_distances
    rows, certificates = [], {}
    for item in reports:
        h = item['histogram']
        n, k = sum(h), len(h)
        d = _prefix_distances(problem(h, item['information']))
        cutoff, bonferroni = critical_score(n, k, F(1, 20)), F(1, 20) / (k * (k - 1) // 2)
        for c in (cutoff, bonferroni):
            if (n, k, str(c)) not in certificates:
                certificates[n, k, str(c)] = binomial_shape_certificate(n, c, monotonic() + 120)['status']
                assert certificates[n, k, str(c)] == 'certified'
        widths = []
        for c in (bonferroni, cutoff):
            values = []
            for a, b in combinations(range(k + 1), 2):
                if a == 0 and b == k:
                    continue
                low, high = int(-d[b, a]), int(d[a, b])
                lo = 0. if low == 0 else float(beta.ppf(float(c) / 2, low, n - low + 1))
                hi = 1. if high == n else float(beta.isf(float(c) / 2, high + 1, n - high))
                values.append(hi - lo)
            widths.append(100 * sum(values) / len(values))
        assert widths[1] <= widths[0] + 1e-10
        rows.append(dict(case=item['case'], information=item['information'], n=n, k=k, ranges=k * (k + 1) // 2 - 1,
                         bonferroni_cutoff=str(bonferroni), range_calibrated_cutoff=str(cutoff),
                         bonferroni_mean_width_pp=widths[0], range_calibrated_mean_width_pp=widths[1],
                         relative_reduction_percent=100 * (widths[0] - widths[1]) / widths[0]))
    groups = []
    for k, n in sorted({(r['k'], r['n']) for r in rows}):
        rr = [r for r in rows if (r['k'], r['n']) == (k, n)]
        before = sum(r['bonferroni_mean_width_pp'] * r['ranges'] for r in rr)
        after = sum(r['range_calibrated_mean_width_pp'] * r['ranges'] for r in rr)
        groups.append(dict(k=k, n=n, reports=len(rr), narrower=sum(r['relative_reduction_percent'] > 1e-9 for r in rr),
                           equal=sum(abs(r['relative_reduction_percent']) <= 1e-9 for r in rr),
                           relative_reduction_percent=100 * (before - after) / before))
    before = sum(r['bonferroni_mean_width_pp'] * r['ranges'] for r in rows)
    after = sum(r['range_calibrated_mean_width_pp'] * r['ranges'] for r in rows)
    return dict(reports=len(rows), proper_range_projections=sum(r['ranges'] for r in rows),
                aggregate_relative_reduction_percent=100 * (before - after) / before,
                narrower=sum(g['narrower'] for g in groups), equal=sum(g['equal'] for g in groups),
                shape_certificates_checked=len(certificates), groups=groups), rows


def scaling_probe(task):
    from mic_50_90.joint_population import population_distribution
    n, k, mode = task
    h = [n // k + (j < n % k) for j in range(k)]
    started = perf_counter()
    result = population_distribution({'a': problem(h, mode)}, method='range-calibrated', confidence_level=.95,
                                     time_limit_seconds=15, tolerance_pp=.01, include_intervals=True)
    return dict(n=n, k=k, information=mode, histogram=h, seconds=perf_counter() - started,
                precision_reached=bool(result['precision_reached']), endpoint_gap_pp=result['endpoint_gap_pp'])


def main():
    parser = common.parser(__doc__)
    args = parser.parse_args()
    folder = args.output.resolve() / 'controlled_reports'
    reports = read_json(DATA / 'controlled_reports.json')
    assert len(reports) == 144
    started = perf_counter()
    cutoff, cutoff_rows = cutoff_comparison(reports)
    print(json.dumps(dict(stage='cutoff comparison', seconds=round(perf_counter() - started, 1))), flush=True)
    probes = [(n, k, mode) for n, k in [(200, 5), (200, 8), (1000, 5), (1000, 8), (200, 16)]
              for mode in ('summaries', 'two_counts', 'interior')]
    with ProcessPoolExecutor(args.workers) as pool:
        checks = list(pool.map(endpoint_check, enumerate(reports)))
        print(json.dumps(dict(stage='endpoint checks', seconds=round(perf_counter() - started, 1))), flush=True)
        scaling = list(pool.map(scaling_probe, probes))
    groups = []
    for k, n in sorted({(r['k'], r['n']) for r in checks}):
        rows = [r for r in checks if (r['k'], r['n']) == (k, n)]
        groups.append(dict(k=k, n=n, reports=len(rows), confirmed=sum(r['precision_reached'] for r in rows),
                           shape=sum(r['precision_reached'] and r['shape_certificate'] == 'certified' for r in rows),
                           direct_witness=sum(r['precision_reached'] and r['shape_certificate'] != 'certified' for r in rows),
                           median_seconds=median(r['seconds'] for r in rows), maximum_seconds=max(r['seconds'] for r in rows)))
    endpoint = dict(reports=len(checks), confirmed=sum(r['precision_reached'] for r in checks),
                    shape_condition=sum(g['shape'] for g in groups), direct_witness=sum(g['direct_witness'] for g in groups),
                    maximum_endpoint_gap_pp=max(r['endpoint_gap_pp'] for r in checks),
                    maximum_independent_difference_pp=max(r['maximum_independent_difference_pp'] for r in checks),
                    independent_lp_solves_requested=sum(r['independent_lp_solves'] for r in checks), groups=groups)
    probe = dict(probes=len(scaling), confirmed=sum(r['precision_reached'] for r in scaling),
                 maximum_n=max(r['n'] for r in scaling), maximum_k=max(r['k'] for r in scaling),
                 minimum_seconds=min(r['seconds'] for r in scaling), maximum_seconds=max(r['seconds'] for r in scaling))
    write_json(folder / 'records.json', dict(cutoff_comparison=cutoff_rows, endpoint_checks=checks, scaling_probes=scaling))
    write_json(folder / 'summary.json', dict(comparison='controlled_reports', created_utc=now(), status='complete', full_design=True,
               elapsed_seconds=perf_counter() - started, environment=common.environment(),
               cutoff_comparison=cutoff, endpoint_checks=endpoint, scaling_probes=probe))
    print(json.dumps(dict(cutoff={k: v for k, v in cutoff.items() if k != 'groups'},
                          endpoint={k: v for k, v in endpoint.items() if k != 'groups'}, probes=probe), indent=1))


if __name__ == '__main__':
    main()
