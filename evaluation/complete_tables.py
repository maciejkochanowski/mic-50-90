"""Population bounds from complete tables compared with bounds from the incomplete reports.

For each of the twenty cohorts the input of its incomplete report is kept (panel, quantiles,
confidence level, independent sampling) and every recorded category count is added, so that the
sample table is known exactly. Bonferroni and range-calibrated bounds (95%, 0.1 percentage-point
endpoint tolerance, 30-second time limit) are computed for the complete table and for the
incomplete report. The mean width over the proper contiguous ranges of the complete table is the
width that sampling alone leaves; the ratio report/complete is the cost of the incomplete report.

Output: OUTPUT/complete_tables/summary.json.
"""
from __future__ import annotations

import common

import copy
import json
import statistics
from concurrent.futures import ProcessPoolExecutor
from time import perf_counter

from common import now, population_cohorts, proper_ranges, write_json

METHODS = ('bonferroni', 'range-calibrated')


def complete_input(row):
    spec = copy.deepcopy(row['input'])
    labels = [c['label'] for c in spec['panel']['categories']]
    assert len(labels) == len(row['counts']) and sum(row['counts']) == row['n']
    spec['additional_counts'] = [{'start_category': label, 'end_category': label, 'n': row['n'], 'count': int(count),
                                  'unit': spec['unit'], 'source': 'Complete grouped table of the cohort'}
                                 for label, count in zip(labels, row['counts'])]
    return spec


def bounds(task):
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.joint_population import population_distribution
    case, table, method, time_limit = task
    row = next(r for r in population_cohorts() if r['case'] == case)
    spec = complete_input(row) if table == 'complete' else row['input']
    problems, _, _ = distribution_problems(spec)
    started = perf_counter()
    result = population_distribution(problems, method=method, confidence_level=.95, time_limit_seconds=time_limit,
                                     tolerance_pp=.1, include_intervals=True)
    _, ranges = proper_ranges(result)
    widths = [100 * (b['upper'] - b['lower']) for b in ranges]
    return case, table, method, dict(status=result['status'], precision_reached=result.get('precision_reached'),
                                     ranges=len(widths), mean_width_pp=sum(widths) / len(widths), seconds=perf_counter() - started)


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--time-limit', type=float, default=30, help='seconds per calculation (default 30)')
    args = parser.parse_args()
    folder = args.output.resolve() / 'complete_tables'
    rows = population_cohorts()
    tasks = [(r['case'], table, m, args.time_limit) for r in rows for table in ('complete', 'report') for m in METHODS]
    started = perf_counter()
    with ProcessPoolExecutor(args.workers) as pool:
        outcomes = list(pool.map(bounds, tasks))
    values = {(case, table, method): value for case, table, method, value in outcomes}
    cohorts = []
    for row in rows:
        item = dict(case=row['case'], cohort_id=row['cohort_id'], n=row['n'], counts=row['counts'])
        for method in METHODS:
            complete, report = values[row['case'], 'complete', method], values[row['case'], 'report', method]
            item[method] = dict(complete=complete, report=report, width_ratio=report['mean_width_pp'] / complete['mean_width_pp'])
        cohorts.append(item)
    summary = {}
    for method in METHODS:
        ratios = [c[method]['width_ratio'] for c in cohorts]
        summary[method] = dict(mean_width_complete_pp=statistics.mean(c[method]['complete']['mean_width_pp'] for c in cohorts),
                               mean_width_report_pp=statistics.mean(c[method]['report']['mean_width_pp'] for c in cohorts),
                               median_width_ratio=statistics.median(ratios), minimum_width_ratio=min(ratios), maximum_width_ratio=max(ratios),
                               endpoint_target_met=sum(bool(c[method][t]['precision_reached']) for c in cohorts for t in ('complete', 'report')))
    write_json(folder / 'summary.json', dict(comparison='complete_tables', created_utc=now(), status='complete',
               full_design=args.time_limit == 30, settings=dict(time_limit_seconds=args.time_limit, confidence_level=.95, tolerance_pp=.1),
               elapsed_seconds=perf_counter() - started, environment=common.environment(), summary=summary, cohorts=cohorts))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
