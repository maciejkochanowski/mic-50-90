"""Coverage of the population bounds on resampled confirmation cohorts (PROTOCOL.md, section 5, G1).

Each confirmation cohort serves as a population with the shares of its complete table. A replicate
draws a multinomial sample of the cohort's n, shortens it by report R1, R2 or R3 and computes
Bonferroni and range-calibrated bounds at 95% (0.1-point endpoint target, 30 seconds per report).
A replicate covers when every proper contiguous range contains its population share. Undercoverage
of a configuration (cohort and report) is declared when the one-sided exact binomial test of
coverage >= 95% rejects at level 0.001.

Random numbers: numpy default_rng([20261102, 1, configuration index, replicate index]).
Output: OUTPUT/confirmation_coverage/configurations.json.gz and summary.json.
"""
from __future__ import annotations

import common

import gzip
import json
import shutil

import benchmark
from common import now, write_json

SEED, GENERATOR = 20261102, 1


def configurations(count=None):
    rows = benchmark.cohorts()[:count]
    return [dict(config=f"{r['position']:04d}-{rule}", position=r['position'], cohort_id=r['cohort_id'], stratum=r['stratum'],
                 n=r['n'], k=r['k'], low=r['low'], high=r['high'], report=rule, shares=[c / r['n'] for c in r['counts']])
            for r in rows for rule in benchmark.REPORTS]


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--replicates', type=int, default=2000, help='replicates per cohort and report (default 2000)')
    parser.add_argument('--cohorts', type=int, help='only the first N cohorts (a reduced run)')
    parser.add_argument('--block', type=int, default=50)
    parser.add_argument('--shard', help='run only part i of n of the configurations (i/n); a run without --shard collects them')
    args = parser.parse_args()
    folder = args.output.resolve() / 'confirmation_coverage'
    configs = configurations(args.cohorts)
    settings = dict(cohorts=len(configs) // 3, replicates=args.replicates, seed=SEED, block=args.block)
    common.check_settings(folder / 'RUN.json', settings)
    if not (folder / 'RUN.json').exists():
        write_json(folder / 'RUN.json', dict(settings=settings, started_utc=now(), workers=args.workers, environment=common.environment()))
    rows = benchmark.run_configurations(configs, args.replicates, folder / 'blocks', args.workers, SEED, GENERATOR, args.block,
                                        benchmark.shard_argument(args.shard))
    if rows is None:
        return
    with gzip.open(folder / 'configurations.json.gz', 'wt', encoding='utf-8') as handle:
        json.dump(rows, handle)
    shutil.rmtree(folder / 'blocks')
    totals = {rule: benchmark.coverage_totals([r for r in rows if r['report'] == rule]) for rule in benchmark.REPORTS}
    full = settings['cohorts'] == len(benchmark.cohorts()) and args.replicates == 2000
    write_json(folder / 'summary.json', dict(comparison='confirmation_coverage', created_utc=now(), status='complete', full_design=full,
               settings=settings, seed_scheme='numpy default_rng([seed, 1, configuration index, replicate index])',
               environment=common.environment(), totals=totals, overall=benchmark.coverage_totals(rows)))
    print(json.dumps(totals, indent=1))


if __name__ == '__main__':
    main()
