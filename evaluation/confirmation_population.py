"""Population bounds on the confirmation cohorts (PROTOCOL.md, section 4).

Every confirmation cohort (data/benchmark/cohorts.jsonl.gz) is shortened by reports R1, R2 and R3.
Bonferroni and range-calibrated bound every proper contiguous range at 95% for all three reports;
joint-exact and range-hunter for R1. Endpoint target 0.1 percentage points; each job runs in its
own single-threaded process with a 120-second budget, saves its quick conservative result first and
refines it with the time left minus a 5-second reserve, as in population_comparison.py.

Questions: is the share of a range below 5%, 10% and 20%; resolved when the interval lies on one
side. Criteria (fixed in PROTOCOL.md): the default rule is confirmed when, for R1, Bonferroni is
narrower for cumulative ranges in at least 80% of cohorts and range-calibrated is narrower for
single categories in at least 80% of cohorts.

Output: OUTPUT/confirmation_population/jobs.jsonl.gz (one line per job) and summary.json.
"""
from __future__ import annotations

import common

import argparse
import gzip
import json
import os
import statistics
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from fractions import Fraction
from pathlib import Path
from time import perf_counter

import benchmark
from common import now, read_json, read_jsonl, write_json

KINDS = ('cumulative', 'single', 'internal', 'all')
CRITERIA = (Fraction(1, 20), Fraction(1, 10), Fraction(1, 5))
PLAN = {'bonferroni': ('R1', 'R2', 'R3'), 'range-calibrated': ('R1', 'R2', 'R3'), 'joint-exact': ('R1',), 'range-hunter': ('R1',)}
ORDER = ('joint-exact', 'range-hunter', 'range-calibrated', 'bonferroni')
PAIRS = (('bonferroni', 'range-calibrated'), ('bonferroni', 'joint-exact'), ('range-calibrated', 'range-hunter'))
THRESHOLD = 0.8


def describe(result):
    k, ranges = benchmark.proper(result)
    widths = {kind: 0.0 for kind in KINDS}
    counts = {kind: 0 for kind in KINDS}
    resolved = {kind: 0 for kind in KINDS}
    for b in ranges:
        kind = benchmark.kind(b['start_index'], b['stop_index'], k)
        lower, upper = Fraction(b['lower']), Fraction(b['upper'])
        done = sum(upper < c or lower >= c for c in CRITERIA)
        for key in (kind, 'all'):
            widths[key] += 100 * (b['upper'] - b['lower'])
            counts[key] += 1
            resolved[key] += done
    return dict(status=result['status'], precision_reached=bool(result.get('precision_reached')),
                endpoint_gap_pp=result.get('endpoint_gap_pp'), summed_width_pp=widths, ranges=counts,
                resolved_questions=resolved, questions={kind: 3 * counts[kind] for kind in KINDS},
                intervals=[[b['start_index'], b['stop_index'], b['lower'], b['upper']] for b in ranges])


def run_job(args):
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.joint_population import population_distribution
    started = perf_counter()
    position, rule, method = int(args.job[0]), args.job[1], args.job[2]
    row = benchmark.cohorts()[position]
    folder = args.output / 'confirmation_population' / 'runs'
    stem = folder / f'{position:04d}-{rule}-{method}'
    options = dict(method=method, confidence_level=.95, tolerance_pp=args.tolerance, include_intervals=True)
    problems, _, _ = distribution_problems(benchmark.report(row['cohort_id'], row['counts'], row['low'], row['high'], rule))
    result = population_distribution(problems, time_limit_seconds=0, **options)
    record = dict(position=position, cohort_id=row['cohort_id'], stratum=row['stratum'], n=row['n'], k=row['k'], report=rule,
                  method=method, baseline_seconds=perf_counter() - started, **describe(result))
    write_json(stem.with_suffix('.quick.json'), record, indent=None)
    remaining = args.budget - (perf_counter() - started) - args.reserve
    if method != 'bonferroni' and remaining > 0:
        record.update(describe(population_distribution(problems, time_limit_seconds=remaining, **options)))
    record.update(seconds=perf_counter() - started, process_status='completed')
    write_json(stem.with_suffix('.json'), record, indent=None)
    stem.with_suffix('.quick.json').unlink()


def execute(args, job):
    position, rule, method = job
    folder = args.output / 'confirmation_population' / 'runs'
    stem = folder / f'{position:04d}-{rule}-{method}'
    if stem.with_suffix('.json').exists():
        return read_json(stem.with_suffix('.json'))
    command = [sys.executable, '-B', str(Path(__file__).resolve()), '--job', str(position), rule, method,
               '--output', str(args.output), '--budget', str(args.budget), '--reserve', str(args.reserve),
               '--tolerance', str(args.tolerance)]
    environment = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    started = perf_counter()
    try:
        process = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=args.budget)
        state, log = ('completed' if process.returncode == 0 else 'worker_error'), process.stdout + process.stderr
    except subprocess.TimeoutExpired as exc:
        state, log = 'process_time_limit', str(exc)
    if not stem.with_suffix('.json').exists():
        quick = stem.with_suffix('.quick.json')
        if not quick.exists():
            stem.with_suffix('.log').write_text(log, encoding='utf-8')
            raise RuntimeError(f'{job}: {state} before the quick result was saved')
        record = read_json(quick)
        record.update(process_status=state, seconds=perf_counter() - started)
        write_json(stem.with_suffix('.json'), record, indent=None)
        quick.unlink()
    return read_json(stem.with_suffix('.json'))


def summarize(records, cohorts):
    by = {(r['position'], r['report'], r['method']): r for r in records}
    constructions = {}
    for method, rules in PLAN.items():
        for rule in rules:
            group = [r for r in records if r['method'] == method and r['report'] == rule]
            if not group:
                continue
            entry = dict(cohorts=len(group), meeting_endpoint_target=sum(r['precision_reached'] for r in group),
                         median_seconds=statistics.median(r['seconds'] for r in group), maximum_seconds=max(r['seconds'] for r in group),
                         process_statuses={s: sum(r['process_status'] == s for r in group) for s in sorted({r['process_status'] for r in group})})
            for kind in KINDS:
                total = sum(r['ranges'][kind] for r in group)
                entry[kind] = dict(ranges=total, mean_width_pp=sum(r['summed_width_pp'][kind] for r in group) / total if total else None,
                                   resolved_questions=sum(r['resolved_questions'][kind] for r in group),
                                   questions=sum(r['questions'][kind] for r in group))
            constructions[f'{method}|{rule}'] = entry
    pairs = []
    for base, other in PAIRS:
        for rule in PLAN[other]:
            shared = [p for p in range(len(cohorts)) if (p, rule, base) in by and (p, rule, other) in by]
            if not shared:
                continue
            entry = dict(baseline=base, candidate=other, report=rule, cohorts=len(shared))
            for kind in KINDS:
                with_kind = [p for p in shared if by[p, rule, base]['ranges'][kind]]
                mean = lambda p, m, rule=rule, kind=kind: by[p, rule, m]["summed_width_pp"][kind] / by[p, rule, m]["ranges"][kind]
                difference = [mean(p, other) - mean(p, base) for p in with_kind]
                before = sum(by[p, rule, base]['summed_width_pp'][kind] for p in with_kind)
                after = sum(by[p, rule, other]['summed_width_pp'][kind] for p in with_kind)
                entry[kind] = dict(cohorts=len(with_kind), candidate_narrower=sum(d < -1e-7 for d in difference),
                                   candidate_wider=sum(d > 1e-7 for d in difference), equal=sum(abs(d) <= 1e-7 for d in difference),
                                   summed_width_change_percent=100 * (after / before - 1) if before else None,
                                   extra_resolved=sum(by[p, rule, other]['resolved_questions'][kind] - by[p, rule, base]['resolved_questions'][kind]
                                                      for p in with_kind))
            pairs.append(entry)
    rule = {}
    for r in ('R1', 'R2', 'R3'):
        pair = next((p for p in pairs if p['baseline'] == 'bonferroni' and p['candidate'] == 'range-calibrated' and p['report'] == r), None)
        if pair:
            cumulative = pair['cumulative']['candidate_wider'] / pair['cumulative']['cohorts']
            single = pair['single']['candidate_narrower'] / pair['single']['cohorts'] if pair['single']['cohorts'] else None
            rule[r] = dict(bonferroni_narrower_cumulative=cumulative, range_calibrated_narrower_single=single,
                           confirmed=bool(cumulative >= THRESHOLD and single is not None and single >= THRESHOLD))
    strata = {}
    for r in records:
        if r['method'] in ('bonferroni', 'range-calibrated') and r['report'] == 'R1':
            s = strata.setdefault(r['stratum'], {})
            s.setdefault(r['method'], []).append(r['summed_width_pp']['all'] / r['ranges']['all'])
    return dict(constructions=constructions, pairs=pairs, default_rule=rule, criterion_threshold=THRESHOLD,
                strata={k: {m: statistics.mean(v) for m, v in s.items()} for k, s in sorted(strata.items())})


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--budget', type=float, default=120.0, help='process budget per job in seconds (default 120)')
    parser.add_argument('--reserve', type=float, default=5.0)
    parser.add_argument('--tolerance', type=float, default=.1, help='endpoint tolerance in percentage points')
    parser.add_argument('--cohorts', type=int, help='only the first N cohorts (a reduced run)')
    parser.add_argument('--methods', default=','.join(PLAN), help='comma-separated constructions (default: all four)')
    parser.add_argument('--shard', help='run only part i of n of the jobs (i/n); a run without --shard collects them')
    parser.add_argument('--job', nargs=3, help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.job:
        return run_job(args)
    cohorts = benchmark.cohorts()
    count = len(cohorts) if args.cohorts is None else min(args.cohorts, len(cohorts))
    methods = [m.strip() for m in args.methods.split(',')]
    assert set(methods) <= set(PLAN)
    folder = args.output / 'confirmation_population'
    settings = dict(cohorts=count, methods=methods, budget_seconds=args.budget, reserve_seconds=args.reserve, tolerance_pp=args.tolerance)
    common.check_settings(folder / 'RUN.json', settings)
    if not (folder / 'RUN.json').exists():
        write_json(folder / 'RUN.json', dict(settings=settings, started_utc=now(), workers=args.workers, environment=common.environment()))
    shard = benchmark.shard_argument(args.shard)
    merged = folder / 'jobs.jsonl.gz'
    jobs = sorted(((p, r, m) for p in range(count) for m in methods for r in PLAN[m]), key=lambda j: (ORDER.index(j[2]), j[0], j[1]))
    if merged.exists():
        records = read_jsonl(merged)
    else:
        (folder / 'runs').mkdir(parents=True, exist_ok=True)
        records, started = [], perf_counter()
        mine = [job for i, job in enumerate(jobs) if not shard or i % shard[1] == shard[0]]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(execute, args, job) for job in mine]
            for done, future in enumerate(as_completed(futures), 1):
                records.append(future.result())
                if done % 200 == 0 or done == len(mine):
                    print(json.dumps(dict(done=done, of=len(mine), elapsed=round(perf_counter() - started, 1))), flush=True)
        if shard:
            return
        records.sort(key=lambda r: (r['position'], r['report'], r['method']))
        with gzip.open(merged.with_name(merged.name + '.tmp'), 'wt', encoding='utf-8') as handle:
            for r in records:
                handle.write(json.dumps(r) + '\n')
        merged.with_name(merged.name + '.tmp').replace(merged)
        for path in (folder / 'runs').glob('*.json'):
            path.unlink()
        (folder / 'runs').rmdir()
    assert len(records) == len(jobs)
    full = count == len(cohorts) and set(methods) == set(PLAN) and args.budget == 120 and args.tolerance == .1
    summary = dict(comparison='confirmation_population', created_utc=now(), status='complete', full_design=full, jobs=len(records),
                   settings=settings, environment=common.environment(), **summarize(records, cohorts[:count]))
    write_json(folder / 'summary.json', summary)
    print(json.dumps(summary['default_rule'], indent=1))


if __name__ == '__main__':
    main()
