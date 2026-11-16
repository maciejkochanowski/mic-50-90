"""Population comparison of four constructions on twenty incomplete reports.

Each of the twenty cohorts (ten FDA animal-pathogen and ten NORM 2024 human cohorts) is shortened
to the report a laboratory would publish: n, the panel, ceiling-rank MIC50 and MIC90 and one
disclosed category count. The four constructions (bonferroni, joint-exact, range-calibrated and
range-hunter) bound the population share of every contiguous range of categories at 95% with an
endpoint tolerance of 0.1 percentage points.

Each of the 80 jobs runs as its own single-threaded process with a process budget (120 s). The
job first computes the quick conservative result, saves it, and then refines it with the time
left minus a 5-second reserve. If the process reaches the budget, the saved quick result is kept.
Finished jobs are skipped when the command is repeated, so an interrupted run can be resumed.

Questions: for every proper range, is the population share below 5%, 10% and 20%? A question is
resolved when the whole interval lies on one side of the criterion.

Output: OUTPUT/population/runs/*.json (one per job) and OUTPUT/population/summary.json.
"""
from __future__ import annotations

import common

import argparse
import json
import os
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path
from time import perf_counter

from common import METHODS, now, population_cohorts, proper_ranges, range_kind, read_json, write_json

KINDS = ('cumulative', 'single', 'internal', 'all')
CRITERIA = (Fraction(1, 20), Fraction(1, 10), Fraction(1, 5))
PAIRS = (('bonferroni', 'range-calibrated'), ('bonferroni', 'joint-exact'), ('range-calibrated', 'range-hunter'))
# Long jobs first, so that the slowest jobs do not start last.
ORDER = ('joint-exact', 'range-hunter', 'range-calibrated', 'bonferroni')


def run_job(args):
    """Worker process: one cohort and one construction."""
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.joint_population import population_distribution
    started = perf_counter()
    case, method = args.job
    row = next(r for r in population_cohorts() if r['case'] == case)
    folder = args.output / 'population' / 'runs'
    options = dict(method=method, confidence_level=args.confidence, tolerance_pp=args.tolerance, include_intervals=True)
    problems, _, _ = distribution_problems(row['input'])
    result = population_distribution(problems, time_limit_seconds=0, **options)
    record = dict(case=case, method=method, cohort_id=row['cohort_id'], source=row['source'], n=row['n'],
                  process_budget_seconds=args.budget, reserve_seconds=args.reserve,
                  baseline_seconds=perf_counter() - started, result=result)
    write_json(folder / f'{case}-{method}.quick.json', record)
    remaining = args.budget - (perf_counter() - started) - args.reserve
    record['refinement_budget_seconds'] = 0 if method == 'bonferroni' else max(0.0, remaining)
    if method != 'bonferroni' and remaining > 0:
        record['result'] = population_distribution(problems, time_limit_seconds=remaining, **options)
    record.update(seconds=perf_counter() - started, process_status='completed', completed_utc=now())
    write_json(folder / f'{case}-{method}.json', record)
    (folder / f'{case}-{method}.quick.json').unlink()


def execute(args, case, method):
    folder = args.output / 'population' / 'runs'
    path = folder / f'{case}-{method}.json'
    if path.exists():
        return read_json(path), True
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--job', case, method, '--output', str(args.output),
               '--budget', str(args.budget), '--reserve', str(args.reserve),
               '--confidence', str(args.confidence), '--tolerance', str(args.tolerance)]
    environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    started = perf_counter()
    try:
        process = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=args.budget)
        state, log = ('completed' if process.returncode == 0 else 'worker_error'), process.stdout + process.stderr
    except subprocess.TimeoutExpired as exc:
        state, log = 'process_time_limit', str(exc)
    if not path.exists():
        quick = folder / f'{case}-{method}.quick.json'
        if not quick.exists():
            (folder / f'{case}-{method}.log').write_text(log, encoding='utf-8')
            raise RuntimeError(f'{case} {method}: {state} before the quick result was saved; see the log')
        record = read_json(quick)
        record.update(process_status=state, seconds=perf_counter() - started, completed_utc=now())
        write_json(path, record)
        quick.unlink()
    return read_json(path), False


def answers(result):
    k, ranges = proper_ranges(result)
    rows = []
    for b in ranges:
        lower, upper = Fraction(b['lower']), Fraction(b['upper'])
        for criterion in CRITERIA:
            status = 'supported' if upper < criterion else 'contradicted' if lower >= criterion else 'undetermined'
            rows.append((range_kind(b['start_index'], b['stop_index'], k), status != 'undetermined'))
    return rows


def describe(record):
    """Per-job quantities: summed widths and resolved questions for each kind of range."""
    result = record['result']
    k, ranges = proper_ranges(result)
    widths = {kind: 0.0 for kind in KINDS}
    counts = {kind: 0 for kind in KINDS}
    for b in ranges:
        width = 100 * (b['upper'] - b['lower'])
        for kind in (range_kind(b['start_index'], b['stop_index'], k), 'all'):
            widths[kind] += width
            counts[kind] += 1
    resolved = {kind: 0 for kind in KINDS}
    questions = {kind: 0 for kind in KINDS}
    for kind, done in answers(result):
        for key in (kind, 'all'):
            resolved[key] += done
            questions[key] += 1
    return dict(case=record['case'], method=record['method'], source=record['source'], n=record['n'],
                status=result['status'], precision_reached=bool(result.get('precision_reached')),
                endpoint_gap_pp=result.get('endpoint_gap_pp'), process_status=record['process_status'],
                seconds=record['seconds'], summed_width_pp=widths, ranges=counts,
                resolved_questions=resolved, questions=questions)


def summarize(args, cases, methods):
    folder = args.output / 'population'
    rows = []
    for case in cases:
        for method in methods:
            path = folder / 'runs' / f'{case}-{method}.json'
            if path.exists():
                rows.append(describe(read_json(path)))
    index = {(r['case'], r['method']): r for r in rows}
    constructions = {}
    for method in methods:
        group = [r for r in rows if r['method'] == method]
        if not group:
            continue
        entry = dict(cohorts=len(group), cohorts_meeting_endpoint_target=sum(r['precision_reached'] for r in group),
                     median_seconds=statistics.median(r['seconds'] for r in group),
                     maximum_seconds=max(r['seconds'] for r in group),
                     process_statuses={s: sum(r['process_status'] == s for r in group) for s in sorted({r['process_status'] for r in group})})
        for kind in KINDS:
            total = sum(r['ranges'][kind] for r in group)
            entry[kind] = dict(ranges=total, mean_width_pp=sum(r['summed_width_pp'][kind] for r in group) / total,
                               summed_width_pp=sum(r['summed_width_pp'][kind] for r in group),
                               resolved_questions=sum(r['resolved_questions'][kind] for r in group),
                               questions=sum(r['questions'][kind] for r in group))
        constructions[method] = entry
    pairs = []
    for base, candidate in PAIRS:
        shared = [c for c in cases if (c, base) in index and (c, candidate) in index]
        if not shared:
            continue
        entry = dict(baseline=base, candidate=candidate, cohorts=len(shared))
        for kind in KINDS:
            difference = [index[c, candidate]['summed_width_pp'][kind] - index[c, base]['summed_width_pp'][kind] for c in shared]
            before = sum(index[c, base]['summed_width_pp'][kind] for c in shared)
            after = sum(index[c, candidate]['summed_width_pp'][kind] for c in shared)
            entry[kind] = dict(narrower=sum(d < -1e-7 for d in difference), wider=sum(d > 1e-7 for d in difference),
                               equal=sum(abs(d) <= 1e-7 for d in difference),
                               summed_width_change_percent=100 * (after / before - 1),
                               extra_resolved=sum(index[c, candidate]['resolved_questions'][kind] - index[c, base]['resolved_questions'][kind] for c in shared),
                               cohorts_losing_resolution=sum(index[c, candidate]['resolved_questions'][kind] < index[c, base]['resolved_questions'][kind] for c in shared))
        entry['summed_width_reduction_percent'] = -entry['all']['summed_width_change_percent']
        pairs.append(entry)
    expected = len(cases) * len(methods)
    full = len(cases) == 20 and set(methods) == set(METHODS) and args.budget == 120
    record = dict(comparison='population', created_utc=now(), status='complete' if len(rows) == expected else 'incomplete',
                  full_design=full and len(rows) == expected, jobs=len(rows), expected_jobs=expected,
                  settings=settings(args, cases, methods), environment=common.environment(),
                  constructions=constructions, pairs=pairs, cohorts=rows)
    write_json(folder / 'summary.json', record)
    return record


def settings(args, cases, methods):
    return dict(cases=list(cases), methods=list(methods), budget_seconds=args.budget, reserve_seconds=args.reserve,
                confidence_level=args.confidence, tolerance_pp=args.tolerance)


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--budget', type=float, default=120.0, help='process budget per job in seconds (default 120)')
    parser.add_argument('--reserve', type=float, default=5.0, help='seconds kept free for writing the result (default 5)')
    parser.add_argument('--cases', help='comma-separated cohort cases, for example case-01,human-01 (default: all twenty)')
    parser.add_argument('--methods', default=','.join(METHODS), help='comma-separated constructions (default: all four)')
    parser.add_argument('--confidence', type=float, default=.95)
    parser.add_argument('--tolerance', type=float, default=.1, help='endpoint tolerance in percentage points')
    parser.add_argument('--summarize-only', action='store_true', help='write summary.json from the saved jobs')
    parser.add_argument('--job', nargs=2, metavar=('CASE', 'METHOD'), help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.job:
        return run_job(args)
    every = [r['case'] for r in population_cohorts()]
    cases = every if not args.cases else [c.strip() for c in args.cases.split(',')]
    methods = [m.strip() for m in args.methods.split(',')]
    assert set(cases) <= set(every), 'unknown case'
    assert set(methods) <= set(METHODS), 'unknown method'
    folder = args.output / 'population'
    if not args.summarize_only:
        common.check_settings(folder / 'RUN.json', dict(budget_seconds=args.budget, reserve_seconds=args.reserve,
                                                        confidence_level=args.confidence, tolerance_pp=args.tolerance))
        write_json(folder / 'RUN.json', dict(settings=dict(budget_seconds=args.budget, reserve_seconds=args.reserve,
                   confidence_level=args.confidence, tolerance_pp=args.tolerance), started_utc=now(),
                   workers=args.workers, environment=common.environment()))
        (folder / 'runs').mkdir(parents=True, exist_ok=True)
        jobs = sorted(((c, m) for c in cases for m in methods), key=lambda job: ORDER.index(job[1]))
        started = perf_counter()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(execute, args, c, m): (c, m) for c, m in jobs}
            for done, future in enumerate(as_completed(futures), 1):
                record, skipped = future.result()
                print(json.dumps(dict(done=done, of=len(jobs), case=record['case'], method=record['method'],
                                      process_status=record['process_status'], seconds=round(record['seconds'], 3),
                                      resumed=skipped, elapsed=round(perf_counter() - started, 1))), flush=True)
    record = summarize(args, cases, methods)
    print(json.dumps({m: {k: v for k, v in e.items() if k in ('cohorts_meeting_endpoint_target', 'median_seconds')} |
                      {kind: [round(e[kind]['mean_width_pp'], 3), e[kind]['resolved_questions']] for kind in ('cumulative', 'single', 'all')}
                      for m, e in record['constructions'].items()}, indent=1))


if __name__ == '__main__':
    main()
