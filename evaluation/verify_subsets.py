"""Recompute a seeded subset of every simulation and compare it with the supplied results.

Every simulated replicate has its own random seed, so any part of a simulation can be recomputed
alone. This script recomputes, for each simulation, a fixed selection of replicates (or blocks of
replicates, or repetitions) and requires the recomputed outcome to equal the stored one exactly:
  coverage                 the first --replicates replicates of every development cohort
  confirmation_coverage    the first block (50 replicates) of every --stride-th configuration
  synthetic_coverage       the first block of every --stride-th configuration
  external_calibration     the first --repetitions synthetic repetitions of every setting
It is the quick reproduction check used by the Code Ocean capsule; the full simulations are run by
the scripts named above.

Output: OUTPUT/verify_subsets/summary.json
"""
from __future__ import annotations

import common

import gzip
import json
import tempfile
from multiprocessing import Pool
from pathlib import Path


import benchmark
from common import RESULTS, now, read_jsonl, write_json


def development(task):
    import coverage_simulation as cs
    index, r, stored = task
    out = cs.replicate(index, r, 30)
    return all(out[m]['covered'] == stored[m]['covered'] and out[m]['missed_ranges'] == stored[m]['missed_ranges']
               for m in cs.METHODS)


def block(task):
    seed, generator, index, config, start, stop, expected = task
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'block.json'
        benchmark._block((seed, generator, index, config, start, stop, path))
        found = json.loads(path.read_text())
    return all(found[m]['covered'] == expected[m] for m in expected)


def repetition(task):
    import external_calibration as ec
    setting, index, r, concentration, size, stored = task
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'r.json'
        ec.synthetic_repetition((setting, index, r, concentration, size, path))
        found = json.loads(path.read_text())
    return found['tests'] == stored['tests'] and abs(found['radius'] - stored['radius']) < 1e-12


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--results', type=Path, default=RESULTS, help='folder with the supplied results (default: evaluation/results)')
    parser.add_argument('--replicates', type=int, default=20, help='development replicates per cohort (default 20)')
    parser.add_argument('--stride', type=int, default=10, help='every n-th configuration of the confirmation simulations (default 10)')
    parser.add_argument('--repetitions', type=int, default=2, help='synthetic calibration repetitions per setting (default 2)')
    args = parser.parse_args()
    results, checks = args.results.resolve(), {}
    with Pool(args.workers) as pool:
        stored = read_jsonl(results / 'coverage' / 'replicates.jsonl.gz')
        index = {r['case']: i for i, r in enumerate(common.population_cohorts())}
        tasks = [(index[x['case']], x['replicate'], x) for x in stored if x['replicate'] < args.replicates]
        checks['coverage'] = dict(checked=len(tasks), equal=sum(pool.map(development, tasks, chunksize=1)))
        for name, module in (('confirmation_coverage', 'confirmation_coverage'), ('synthetic_coverage', 'synthetic_coverage')):
            rows = json.load(gzip.open(results / name / 'configurations.json.gz', 'rt'))
            mod = __import__(module)
            configs = mod.configurations() if name == 'synthetic_coverage' else mod.configurations()
            tasks = []
            for i in range(0, len(rows), args.stride):
                row, config = rows[i], configs[i]
                assert row['config'] == config['config']
                size = row['bonferroni']['block_size']
                expected = {m: row[m]['covered_by_block'][0] for m in ('bonferroni', 'range-calibrated')}
                tasks.append((mod.SEED, mod.GENERATOR, i, config, 0, size, expected))
            checks[name] = dict(checked=len(tasks), equal=sum(pool.map(block, tasks, chunksize=1)))
        saved = [json.loads(line) for line in gzip.open(results / 'external_calibration' / 'synthetic' / 'repetitions.jsonl.gz', 'rt')]
        settings = [(f'c={c}|M={m}', i, c, m) for i, (c, m) in enumerate((c, m) for c in (20, 100) for m in (19, 39))]
        tasks = [(name, i, r, c, m, next(s for s in saved if s['setting'] == name and s['repetition'] == r))
                 for name, i, c, m in settings for r in range(args.repetitions)]
        checks['external_calibration_synthetic'] = dict(checked=len(tasks), equal=sum(pool.map(repetition, tasks, chunksize=1)))
    status = 'match' if all(c['checked'] == c['equal'] for c in checks.values()) else 'differs'
    write_json(args.output.resolve() / 'verify_subsets' / 'summary.json',
               dict(comparison='verify_subsets', created_utc=now(), status=status, checks=checks, environment=common.environment()))
    print(json.dumps(dict(status=status, checks=checks), indent=1))
    raise SystemExit(0 if status == 'match' else 1)


if __name__ == '__main__':
    main()
