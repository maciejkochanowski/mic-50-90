"""Selected tables against every compatible table: the ampicillin example of Section 3.1.

The two ampicillin reports (67 canine staphylococci; MIC50, MIC90 and the observed range, then
with the published count of 59 results at or below 0.25 mg/L) are analyzed with the
range-calibrated construction at 95%. The program's result uses the selected count tables of the
endpoint theorem (P6). The exhaustive calculation enumerates every complete count table compatible
with the report, computes the population region of each (the same Clopper-Pearson cutoff) and takes
the union of their projections onto every contiguous range. The script reports the number of
compatible tables, the largest endpoint difference over all ranges, and the median of five timed
runs of each calculation.

Output: OUTPUT/endpoint_selection/summary.json
"""
from __future__ import annotations

import common

import json
import statistics
from fractions import Fraction
from pathlib import Path
from time import monotonic, perf_counter

import numpy as np

from common import HERE, now, read_json, write_json

INPUTS = {
    'summaries': HERE.parent / 'examples' / 'appendix' / 'inputs' / 'ampicillin-67-summaries-conditional-population.json',
    'with count': HERE.parent / 'examples' / 'appendix' / 'inputs' / 'ampicillin-67-with-count-conditional-population.json',
}
RUNS = 5


def selected(problems):
    from mic_50_90.joint_population import population_distribution
    return population_distribution(problems, method='range-calibrated', confidence_level=.95, time_limit_seconds=120,
                                   tolerance_pp=1e-7, include_intervals=True)


def exhaustive(problems):
    """Union over every compatible table of its range-calibrated region, projected on every range."""
    from mic_50_90.joint_population import _cp_outer, _validate
    from mic_50_90.range_population import _histograms, _probability_cell, _project, critical_score
    from mic_50_90.utility import _prefix_distances
    n, k = _validate(problems)
    cutoff = critical_score(n, k, 1 - Fraction(0.95))
    family = [(a, b) for a in range(k) for b in range(a + 1, k)]
    pairs = [(a, b) for a in range(k) for b in range(a + 1, k + 1)]
    lo, hi = np.ones(len(pairs)), np.zeros(len(pairs))
    tables, cache = set(), {}
    for problem in problems.values():
        for h in _histograms(_prefix_distances(problem), monotonic() + 3600):
            if h in tables:
                continue
            tables.add(h)
            cumulative = np.r_[0, np.cumsum(h)].astype(int).tolist()
            limits = []
            for a, b in family:
                x = cumulative[b] - cumulative[a]
                if x not in cache:
                    cache[x] = _cp_outer(x, n, cutoff)
                limits.append((a, b, *cache[x]))
            cell = _probability_cell(k, limits)
            if cell is None:
                continue
            low, high = _project(cell, pairs)
            np.minimum(lo, low, out=lo)
            np.maximum(hi, high, out=hi)
    return len(tables), {(a, b): (float(l), float(u)) for (a, b), l, u in zip(pairs, lo, hi)}


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    from mic_50_90.distribution_workflow import distribution_problems
    folder = args.output.resolve() / 'endpoint_selection'
    reports = {}
    for name, path in INPUTS.items():
        spec = read_json(path)
        problems, _, _ = distribution_problems(spec)
        timings = {'selected': [], 'exhaustive': []}
        for _ in range(RUNS):
            started = perf_counter()
            result = selected(problems)
            timings['selected'].append(perf_counter() - started)
            started = perf_counter()
            count, union = exhaustive(problems)
            timings['exhaustive'].append(perf_counter() - started)
        program = {(b['start_index'], b['stop_index']): (b['lower'], b['upper']) for b in result['interval_bounds']}
        assert set(program) == set(union)
        difference = max(max(abs(program[r][0] - union[r][0]), abs(program[r][1] - union[r][1])) for r in union)
        category = [c['label'] for c in spec['panel']['categories']].index('0.5') if 'categories' in spec['panel'] else 2
        reports[name] = dict(input=str(Path(path).relative_to(HERE.parent)), compatible_tables=count, ranges=len(union),
                             endpoints=2 * len(union), largest_endpoint_difference_pp=100 * difference,
                             certificate=result.get('population_row_lift_certificate', {}).get('status'),
                             evaluated_histograms=result.get('evaluated_histograms'),
                             category_05=dict(lower_pp=100 * program[(category, category + 1)][0],
                                              upper_pp=100 * program[(category, category + 1)][1]),
                             median_seconds_selected=statistics.median(timings['selected']),
                             median_seconds_exhaustive=statistics.median(timings['exhaustive']), timings=timings)
        print(json.dumps({k: v for k, v in reports[name].items() if k != 'timings'}), flush=True)
    write_json(folder / 'summary.json', dict(comparison='endpoint_selection', created_utc=now(), status='complete', full_design=True,
               runs=RUNS, environment=common.environment(), reports=reports,
               all_endpoints=sum(r['endpoints'] for r in reports.values()),
               largest_endpoint_difference_pp=max(r['largest_endpoint_difference_pp'] for r in reports.values())))


if __name__ == '__main__':
    main()
