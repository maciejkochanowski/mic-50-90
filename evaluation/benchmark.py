"""Shared definitions for the confirmation evaluation (PROTOCOL.md, sections 2-3).

Complete tables are lists of counts on a doubling-dilution panel `<= 2^L, (2^L, 2^(L+1)], ...,
(2^(H-1), 2^H], > 2^H`. A report is built from a table by one of three rules (R1, R2, R3), and the
same rule shortens every simulated sample of that table.
"""
from __future__ import annotations

import math
from fractions import Fraction

import numpy as np

from common import DATA, read_jsonl
from coverage_reporting import coverage_evidence, pooled_coverage_evidence

BENCHMARK = DATA / 'benchmark'
REPORTS = ('R1', 'R2', 'R3')


def level(step):
    """Concentration of a doubling step, as a short decimal (2^-3 -> 0.125)."""
    return float(Fraction(2) ** step)


def label(value):
    return f'{value:g}'


def panel(low, high):
    """Panel categories for steps low..high: <= 2^low, one category per step, > 2^high."""
    values = [level(s) for s in range(low, high + 1)]
    categories = [dict(label=f'<= {label(values[0])}', lower_bound=None, upper_bound=values[0], lower_closed=False,
                       upper_closed=True, panel_value=values[0])]
    for a, b in zip(values, values[1:]):
        categories.append(dict(label=f'({label(a)}, {label(b)}]', lower_bound=a, upper_bound=b, lower_closed=False,
                               upper_closed=True, panel_value=b))
    categories.append(dict(label=f'> {label(values[-1])}', lower_bound=values[-1], upper_bound=None, lower_closed=False,
                           upper_closed=False, panel_value=2 * values[-1]))
    return dict(categories=categories)


def middle(k):
    """Index of the middle category, floor(K/2): the development rule for the disclosed count."""
    return k // 2


def report(cohort_id, counts, low, high, rule, source='Complete table of the cohort'):
    """The incomplete report of a complete table under rule R1, R2 or R3 (PROTOCOL.md, section 3)."""
    counts = np.asarray(counts, dtype=int)
    n, k = int(counts.sum()), len(counts)
    spec_panel = panel(low, high)
    labels = [c['label'] for c in spec_panel['categories']]
    assert len(labels) == k
    cumulative = np.cumsum(counts)
    quantiles = [dict(probability=p, convention='ceiling',
                      category=labels[int(np.searchsorted(cumulative, math.ceil(round(p * n, 9))))]) for p in (0.5, 0.9)]
    spec = dict(cohort_id=cohort_id, n=n, panel=spec_panel, unit='mg/L', iid=True, confidence_level=0.95,
                summaries=dict(quantiles=quantiles))
    j = middle(k)
    if rule == 'R1':
        spec['additional_counts'] = [dict(start_category=labels[j], end_category=labels[j], n=n, count=int(counts[j]),
                                          unit='mg/L', source=source)]
    elif rule == 'R2':
        occupied = np.flatnonzero(counts)
        spec['summaries']['minimum'] = labels[int(occupied[0])]
        spec['summaries']['maximum'] = labels[int(occupied[-1])]
    elif rule == 'R3':
        above = int(counts[j + 1:].sum())
        percentage = (Fraction(100 * above, n) + Fraction(1, 2)).__floor__()
        spec['additional_counts'] = [dict(threshold=spec_panel['categories'][j]['upper_bound'], relation='>',
                                          percentage=str(percentage), n=n, unit='mg/L', decimal_places=0,
                                          rounding_rule='half_up', source=source)]
    else:
        raise ValueError(rule)
    return spec


def cohorts():
    """Confirmation cohorts in their fixed order (prepare_benchmark.py)."""
    return read_jsonl(BENCHMARK / 'cohorts.jsonl.gz')


def units():
    """Unit tables of the calibration datasets (prepare_benchmark.py)."""
    return read_jsonl(BENCHMARK / 'units.jsonl.gz')


def kind(start, stop, k):
    if start == 0 or stop == k:
        return 'cumulative'
    return 'single' if stop - start == 1 else 'internal'


def proper(result):
    k = len(result['category_bounds'])
    return k, [b for b in result['interval_bounds'] if not (b['start_index'] == 0 and b['stop_index'] == k)]


def missed_ranges(result, shares):
    """Proper ranges whose interval does not contain the population share."""
    _, ranges = proper(result)
    return [[b['start_index'], b['stop_index']] for b in ranges
            if not b['lower'] - 1e-12 <= float(shares[b['start_index']:b['stop_index']].sum()) <= b['upper'] + 1e-12]


def undercoverage(covered, total, nominal=0.95, level=0.001):
    """One-sided exact binomial test of coverage >= nominal; True when it rejects at `level`."""
    from scipy.stats import binom
    return bool(total and binom.cdf(covered, total, nominal) < level)


def replicate(shares, n, low, high, rule, rng, time_limit=30):
    """Draw one sample from the population shares, shorten it by `rule`, bound it with Bonferroni and
    range-calibrated at 95% and record whether every proper range contains its population share."""
    from time import perf_counter
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.joint_population import population_distribution
    shares = np.asarray(shares, dtype=float)
    sample = rng.multinomial(n, shares / shares.sum())
    problems, _, _ = distribution_problems(report('replicate', sample, low, high, rule, source='Simulated sample'))
    out = {}
    for method in ('bonferroni', 'range-calibrated'):
        started = perf_counter()
        try:
            result = population_distribution(problems, method=method, confidence_level=.95, time_limit_seconds=time_limit,
                                              tolerance_pp=.1, include_intervals=True)
        except Exception as exc:  # recorded, never dropped
            out[method] = dict(error=f'{type(exc).__name__}: {exc}')
            continue
        missed = missed_ranges(result, shares / shares.sum())
        _, ranges = proper(result)
        out[method] = dict(covered=not missed, missed=missed, precision_reached=bool(result.get('precision_reached')),
                           mean_width_pp=100 * float(np.mean([b['upper'] - b['lower'] for b in ranges])),
                           seconds=perf_counter() - started)
    return out


def _block(task):
    """Replicates start..stop of one configuration, aggregated; missed and failed replicates listed."""
    seed, generator, index, config, start, stop, path = task
    import json
    totals = {m: dict(replicates=0, covered=0, width_sum=0.0, seconds_sum=0.0, precision_reached=0, missed=[], errors=[])
              for m in ('bonferroni', 'range-calibrated')}
    for r in range(start, stop):
        rng = np.random.default_rng([seed, generator, index, r])
        out = replicate(config['shares'], config['n'], config['low'], config['high'], config['report'], rng)
        for method, x in out.items():
            t = totals[method]
            if 'error' in x:
                t['errors'].append([r, x['error']])
                continue
            t['replicates'] += 1
            t['covered'] += x['covered']
            t['width_sum'] += x['mean_width_pp']
            t['seconds_sum'] += x['seconds']
            t['precision_reached'] += x['precision_reached']
            if not x['covered']:
                t['missed'].append([r, x['missed']])
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(totals), encoding='utf-8')
    temporary.replace(path)
    return path.name


def run_configurations(configs, replicates, folder, workers, seed, generator, block=50, shard=None):
    """Run every configuration in blocks (resumable) and return one summary row per configuration.

    With shard=(i, n) only the configurations whose index is i modulo n are run and None is returned;
    a later call without a shard collects all blocks."""
    import json
    from multiprocessing import Pool
    from time import perf_counter
    folder.mkdir(parents=True, exist_ok=True)
    tasks = []
    for index, config in enumerate(configs):
        if shard and index % shard[1] != shard[0]:
            continue
        for start in range(0, replicates, block):
            path = folder / f'{index:05d}-{start:06d}.json'
            if not path.exists():
                tasks.append((seed, generator, index, config, start, min(start + block, replicates), path))
    started = perf_counter()
    print(json.dumps(dict(blocks_to_run=len(tasks), workers=workers)), flush=True)
    with Pool(workers) as pool:
        for done, _ in enumerate(pool.imap_unordered(_block, tasks, chunksize=1), 1):
            if done % max(1, len(tasks) // 20) == 0 or done == len(tasks):
                print(json.dumps(dict(blocks_done=done, of=len(tasks), elapsed=round(perf_counter() - started, 1))), flush=True)
    if shard:
        return None
    rows = []
    for index, config in enumerate(configs):
        parts = [json.loads((folder / f'{index:05d}-{start:06d}.json').read_text()) for start in range(0, replicates, block)]
        row = {k: v for k, v in config.items() if k != 'shares'}
        row['shares'] = [round(float(x), 12) for x in config['shares']]
        for method in ('bonferroni', 'range-calibrated'):
            t = dict(replicates=sum(p[method]['replicates'] for p in parts), covered=sum(p[method]['covered'] for p in parts),
                     errors=[e for p in parts for e in p[method]['errors']], missed=[m for p in parts for m in p[method]['missed']],
                     precision_reached=sum(p[method]['precision_reached'] for p in parts))
            t['block_size'] = block
            t['covered_by_block'] = [p[method]['covered'] for p in parts]
            t.update(coverage_evidence(t['covered'], t['replicates'], failed=len(t['errors']), expected=replicates))
            t['mean_width_pp'] = sum(p[method]['width_sum'] for p in parts) / t['replicates'] if t['replicates'] else None
            t['mean_seconds'] = sum(p[method]['seconds_sum'] for p in parts) / t['replicates'] if t['replicates'] else None
            row[method] = t
        rows.append(row)
    return rows


def shard_argument(text):
    """'i/n' -> (i, n) with 0 <= i < n."""
    if not text:
        return None
    i, n = (int(x) for x in text.split('/'))
    assert 0 <= i < n
    return i, n


def coverage_totals(rows):
    return {method: pooled_coverage_evidence([r[method] for r in rows])
            for method in ('bonferroni', 'range-calibrated')}
