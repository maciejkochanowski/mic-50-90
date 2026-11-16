"""Coverage of the population bounds on synthetic populations (PROTOCOL.md, section 5, G2-G4).

Panels have K = 3, 5, 8 or 12 categories (steps 0..K-2: <= 1, (1, 2], ..., > 2^(K-2) mg/L); sample
sizes n = 10, 30, 100, 300 and 1000; reports R1, R2 and R3; 1000 replicates per configuration.

G2 mixture: log2 MIC is a wild-type normal component centred in the second category (log2 = 0.5),
standard deviation 0.5 or 1 dilution, plus a non-wild-type component 3 or 6 dilutions higher with
the same spread and weight 0, 0.05, 0.2 or 0.5. A category's probability is the probability of its
log2 interval.
G3 Dirichlet: category probabilities from a symmetric Dirichlet distribution with concentration
0.3, 1 or 3; three populations per concentration (seeded).
G4 rare categories: a Dirichlet(1) population in which one or two categories (chosen with the
population seed) have expected count 0.5, 2 or 5 isolates at the given n; the rest is rescaled.

A replicate covers when every proper contiguous range contains its population share; undercoverage
is declared when the one-sided exact binomial test of coverage >= 95% rejects at level 0.001.
Random numbers: populations default_rng([20261102, 2, shape, K, n]); replicates
default_rng([20261102, 3, configuration index, replicate index]).
Output: OUTPUT/synthetic_coverage/configurations.json.gz and summary.json.
"""
from __future__ import annotations

import common

import gzip
import itertools
import json
import shutil

import numpy as np
from scipy.stats import norm

import benchmark
from common import now, write_json

SEED, GENERATOR = 20261102, 3
SIZES = (10, 30, 100, 300, 1000)
PANELS = (3, 5, 8, 12)


def mixture(k, spread, weight, shift):
    """Category probabilities of the G2 mixture on a panel of k categories (log2 cut points 0..k-2)."""
    cuts = np.arange(k - 1, dtype=float)
    def probabilities(centre):
        cdf = norm.cdf(cuts, loc=centre, scale=spread)
        return np.diff(np.r_[0.0, cdf, 1.0])
    return (1 - weight) * probabilities(0.5) + weight * probabilities(0.5 + shift)


def shapes():
    """(shape label, function of k, n and seed giving the population)."""
    out = []
    for spread in (0.5, 1.0):
        out.append((f'G2|sd={spread}|weight=0', lambda k, n, s, spread=spread: mixture(k, spread, 0.0, 0.0)))
        for weight, shift in itertools.product((0.05, 0.2, 0.5), (3, 6)):
            out.append((f'G2|sd={spread}|weight={weight}|shift={shift}',
                        lambda k, n, s, spread=spread, weight=weight, shift=shift: mixture(k, spread, weight, shift)))
    for concentration in (0.3, 1.0, 3.0):
        for draw in range(3):
            out.append((f'G3|concentration={concentration}|draw={draw}',
                        lambda k, n, s, c=concentration: s.dirichlet(np.full(k, c))))
    for rare, expected in itertools.product((1, 2), (0.5, 2.0, 5.0)):
        def population(k, n, s, rare=rare, expected=expected):
            p = s.dirichlet(np.ones(k))
            chosen = s.choice(k, size=rare, replace=False)
            fixed = expected / n
            rest = [j for j in range(k) if j not in chosen]
            p[rest] = p[rest] / p[rest].sum() * (1 - rare * fixed)
            p[chosen] = fixed
            return p
        out.append((f'G4|rare={rare}|expected={expected}', population))
    return out


def configurations():
    configs = []
    for shape_index, (name, make) in enumerate(shapes()):
        for k, n in itertools.product(PANELS, SIZES):
            shares = make(k, n, np.random.default_rng([SEED, 2, shape_index, k, n]))
            assert abs(shares.sum() - 1) < 1e-9 and (shares >= 0).all()
            for rule in benchmark.REPORTS:
                configs.append(dict(config=f'{name}|K={k}|n={n}|{rule}', generator=name.split('|')[0], shape=name, k=k, n=n,
                                    low=0, high=k - 2, report=rule, shares=shares.tolist()))
    return configs


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--replicates', type=int, default=1000, help='replicates per configuration (default 1000)')
    parser.add_argument('--generators', default='G2,G3,G4')
    parser.add_argument('--sizes', help='comma-separated sample sizes (default: all five)')
    parser.add_argument('--block', type=int, default=50)
    parser.add_argument('--shard', help='run only part i of n of the configurations (i/n); a run without --shard collects them')
    args = parser.parse_args()
    folder = args.output.resolve() / 'synthetic_coverage'
    chosen = set(args.generators.split(','))
    sizes = set(int(x) for x in args.sizes.split(',')) if args.sizes else set(SIZES)
    configs = [c for c in configurations() if c['generator'] in chosen and c['n'] in sizes]
    settings = dict(generators=sorted(chosen), sizes=sorted(sizes), configurations=len(configs), replicates=args.replicates,
                    seed=SEED, block=args.block)
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
    by_generator = {g: benchmark.coverage_totals([r for r in rows if r['generator'] == g]) for g in sorted(chosen)}
    by_size = {str(n): benchmark.coverage_totals([r for r in rows if r['n'] == n]) for n in sorted(sizes)}
    full = chosen == {'G2', 'G3', 'G4'} and sizes == set(SIZES) and args.replicates == 1000
    write_json(folder / 'summary.json', dict(comparison='synthetic_coverage', created_utc=now(), status='complete', full_design=full,
               settings=settings, environment=common.environment(), generators=by_generator, sizes=by_size,
               overall=benchmark.coverage_totals(rows)))
    print(json.dumps(by_generator, indent=1))


if __name__ == '__main__':
    main()
