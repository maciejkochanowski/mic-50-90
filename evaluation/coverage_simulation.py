"""Simulated simultaneous coverage of the population bounds from incomplete reports.

Each of the twenty cohorts serves as a population with the shares of its complete grouped table.
A replicate draws a multinomial sample of the cohort's size, shortens it exactly as the cohort
report was shortened (ceiling-rank MIC50 and MIC90 and the count of the same disclosed category),
and computes Bonferroni and range-calibrated bounds at 95% from this report alone (0.1 percentage-
point endpoint tolerance, 30-second time limit per report). A replicate covers when every proper
contiguous range contains its population share.

Random numbers: numpy default_rng([20261011, cohort index, replicate index]), so every replicate
can be recomputed alone. Work is split into blocks of replicates; finished blocks are skipped when
the command is repeated.

Output: OUTPUT/coverage/replicates.jsonl.gz (one line per replicate) and OUTPUT/coverage/summary.json.
"""
from __future__ import annotations

import common

import copy
import gzip
import json
import math
from multiprocessing import Pool
from time import perf_counter

import numpy as np

from common import now, population_cohorts, proper_ranges, read_jsonl, write_json
from coverage_reporting import coverage_evidence, pooled_coverage_evidence

METHODS = ('bonferroni', 'range-calibrated')
SEED = 20261011


def shortened(row, sample):
    """The cohort report recomputed from a sample: same panel, quantiles, convention and disclosed category."""
    spec = copy.deepcopy(row['input'])
    labels = [c['label'] for c in spec['panel']['categories']]
    cumulative = np.cumsum(sample)
    for q in spec['summaries']['quantiles']:
        assert q['convention'] == 'ceiling'
        rank = math.ceil(round(q['probability'] * row['n'], 9))
        q['category'] = labels[int(np.searchsorted(cumulative, rank))]
    for count in spec.get('additional_counts', []):
        a, b = labels.index(count['start_category']), labels.index(count['end_category'])
        count['count'] = int(sample[a:b + 1].sum())
        count['source'] = 'Simulated sample'
    return spec


def replicate(index, r, time_limit):
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.joint_population import population_distribution
    row = population_cohorts()[index]
    shares = np.asarray(row['counts'], dtype=float) / row['n']
    sample = np.random.default_rng([SEED, index, r]).multinomial(row['n'], shares)
    problems, _, _ = distribution_problems(shortened(row, sample))
    out = {'case': row['case'], 'replicate': r}
    for method in METHODS:
        started = perf_counter()
        try:
            result = population_distribution(problems, method=method, confidence_level=.95, time_limit_seconds=time_limit,
                                              tolerance_pp=.1, include_intervals=True)
        except Exception as exc:  # recorded, never dropped
            out[method] = {'error': f'{type(exc).__name__}: {exc}'}
            continue
        _, ranges = proper_ranges(result)
        missed = [[b['start_index'], b['stop_index']] for b in ranges
                  if not b['lower'] - 1e-12 <= float(shares[b['start_index']:b['stop_index']].sum()) <= b['upper'] + 1e-12]
        out[method] = {'covered': not missed, 'missed_ranges': missed, 'precision_reached': result.get('precision_reached'),
                       'status': result['status'], 'ranges': len(ranges),
                       'mean_width_pp': 100 * float(np.mean([b['upper'] - b['lower'] for b in ranges])),
                       'seconds': perf_counter() - started}
    return out


def block(task):
    index, start, stop, time_limit, path = task
    rows = [replicate(index, r, time_limit) for r in range(start, stop)]
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(''.join(json.dumps(x) + '\n' for x in rows), encoding='utf-8')
    temporary.replace(path)
    return path.name, len(rows)


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--replicates', type=int, default=5000, help='replicates per cohort (default 5000)')
    parser.add_argument('--cases', help='comma-separated cohort cases (default: all twenty)')
    parser.add_argument('--block', type=int, default=50, help='replicates per work block (default 50)')
    parser.add_argument('--time-limit', type=float, default=30, help='seconds per report and construction (default 30)')
    args = parser.parse_args()
    folder = args.output.resolve() / 'coverage'
    rows = population_cohorts()
    cases = [r['case'] for r in rows] if not args.cases else [c.strip() for c in args.cases.split(',')]
    settings = dict(cases=cases, replicates=args.replicates, time_limit_seconds=args.time_limit, seed=SEED, block=args.block)
    common.check_settings(folder / 'RUN.json', settings)
    write_json(folder / 'RUN.json', dict(settings=settings, started_utc=now(), workers=args.workers, environment=common.environment()))
    blocks = folder / 'blocks'
    merged = folder / 'replicates.jsonl.gz'
    blocks.mkdir(parents=True, exist_ok=True)
    tasks = []
    for index, row in enumerate(rows if not merged.exists() else []):
        if row['case'] not in cases:
            continue
        for start in range(0, args.replicates, args.block):
            path = blocks / f"{row['case']}-{start:06d}.jsonl"
            if not path.exists():
                tasks.append((index, start, min(start + args.block, args.replicates), args.time_limit, path))
    started = perf_counter()
    print(json.dumps(dict(blocks_to_run=len(tasks), workers=args.workers)), flush=True)
    with Pool(args.workers) as pool:
        for done, (name, count) in enumerate(pool.imap_unordered(block, tasks), 1):
            if done % max(1, len(tasks) // 20) == 0 or done == len(tasks):
                print(json.dumps(dict(blocks_done=done, of=len(tasks), last=name, elapsed=round(perf_counter() - started, 1))), flush=True)
    if merged.exists():
        records = read_jsonl(merged)
    else:
        records = []
        for row in rows:
            if row['case'] in cases:
                for start in range(0, args.replicates, args.block):
                    records += read_jsonl(blocks / f"{row['case']}-{start:06d}.jsonl")
        with gzip.open(merged.with_name(merged.name + '.tmp'), 'wt', encoding='utf-8') as handle:
            for record in records:
                handle.write(json.dumps(record) + '\n')
        merged.with_name(merged.name + '.tmp').replace(merged)
        for path in blocks.glob('*.jsonl'):
            path.unlink()
    if blocks.exists():
        blocks.rmdir()
    assert len(records) == len(cases) * args.replicates
    cohorts = []
    for row in rows:
        if row['case'] not in cases:
            continue
        mine = [x for x in records if x['case'] == row['case']]
        item = dict(case=row['case'], cohort_id=row['cohort_id'], n=row['n'], categories=len(row['counts']), replicates=len(mine))
        for method in METHODS:
            good = [x[method] for x in mine if 'error' not in x[method]]
            covered = sum(x['covered'] for x in good)
            item[method] = dict(errors=len(mine) - len(good), covered=covered,
                                precision_reached=sum(bool(x['precision_reached']) for x in good),
                                mean_width_pp=float(np.mean([x['mean_width_pp'] for x in good])) if good else None)
            item[method].update(coverage_evidence(covered, len(good), failed=len(mine) - len(good), expected=args.replicates))
        cohorts.append(item)
    totals = {m: pooled_coverage_evidence([c[m] for c in cohorts]) for m in METHODS}
    for total in totals.values():
        total['lowest_cohort_coverage'] = total['lowest_coverage']
    full = len(cases) == 20 and args.replicates == 5000 and args.time_limit == 30
    write_json(folder / 'summary.json', dict(comparison='coverage', created_utc=now(), status='complete', full_design=full,
               settings=settings, seed_scheme='numpy default_rng([seed, cohort index, replicate index])',
               elapsed_seconds_this_invocation=perf_counter() - started, workers=args.workers,
               environment=common.environment(), totals=totals, cohorts=cohorts))
    print(json.dumps(totals, indent=1))


if __name__ == '__main__':
    main()
