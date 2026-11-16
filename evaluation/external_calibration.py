"""Study-unit calibration tested on later data and on synthetic units (PROTOCOL.md, section 6).

Real data. Each dataset of data/benchmark/units.jsonl.gz has state units in a training year T, a
calibration year C and a test year V = C + 1. The public calibration-prepare command calibrates
on the year-C units, with the uniform reference (no training data) and with the reference and
transport scales learned from the year-T units. The public batch command then receives, for each
year-V unit and drug, only n, ceiling MIC50 and MIC90, the panel, the thresholds and the
calibration. A test unit is covered when every tail of every included drug lies inside its
interval; the public calibration-audit command counts the covered units from the saved intervals.
Every returned interval is checked against an independent closed-form calculation of the ball.

Synthetic units. Unit probabilities are drawn around a fixed population p0 (the G2 mixture on six
categories: spread 0.75, non-wild-type weight 0.2, shift 4 dilutions); unit sizes 20, 50 or 100.
Calibration uses the uniform reference on M = 19 or 39 units at 95% (rank ceil(0.95 (M + 1)));
a test unit is covered when its score (the smallest transport radius whose interval contains all
its tails) does not exceed the calibrated radius. 200 repetitions per setting, 100 test units each.
  SU1  test units drawn like the calibration units (Dirichlet concentration c = 20 or 100)
  SU2  test units around p0 with the non-wild-type weight raised by 0.05, 0.1 or 0.2, or shifted
       one dilution up
  SU3  test units from the mixture with a unit-level wild-type center ~ N(0.5, 0.5^2)
Random numbers: default_rng([20261102, 4, setting index, repetition]).

Output: OUTPUT/external_calibration/<dataset>-<reference>/ and synthetic/, and summary.json.
"""
from __future__ import annotations

import common

import gzip
import json
import math
import shutil
from concurrent.futures import ProcessPoolExecutor
from time import perf_counter

import numpy as np

import benchmark
from calibration import TOLERANCE, ball_endpoints, interval, public_batch
from common import DATA, now, read_json, write_csv, write_json

SEED = 20261102
REFERENCES = ('uniform', 'trained')
SYNTHETIC_K = 6


# ---------------------------------------------------------------- real data

def category_labels(low, high):
    values = [benchmark.label(benchmark.level(s)) for s in range(low, high + 1)]
    return [f'<={values[0]}'] + values[1:] + [f'>{values[-1]}']


def panel_rows(panel_id, low, high):
    labels = category_labels(low, high)
    rows = []
    for label, category in zip(labels, benchmark.panel(low, high)['categories']):
        rows.append(dict(panel_id=panel_id, category=label, unit='mg/L',
                         lower='' if category['lower_bound'] is None else category['lower_bound'],
                         upper='' if category['upper_bound'] is None else category['upper_bound'],
                         lower_closed=str(category['lower_closed']).lower(), upper_closed=str(category['upper_closed']).lower(),
                         panel_value=category['panel_value']))
    return rows


def dataset_inputs(name, info, rows, work, reference):
    """CSV and JSON inputs of calibration-prepare for one dataset and reference."""
    panels = {}
    for r in rows:
        panels[f"{name}:{r['drug']}"] = (r['low'], r['high'])
    write_csv(work / 'panels.csv', [row for pid, (lo, hi) in sorted(panels.items()) for row in panel_rows(pid, lo, hi)])
    roles = ('training', 'calibration', 'target') if reference == 'trained' else ('calibration', 'target')
    role_of = {'training': 'training', 'calibration': 'calibration', 'test': 'target'}
    counts, roster = [], []
    for r in rows:
        role = role_of[r['role']]
        if role not in roles:
            continue
        cohort = f"{name}:{r['year']}:{r['unit_id']}:{r['drug']}"
        roster.append(dict(unit_id=f"{r['year']}:{r['unit_id']}", cohort_id=cohort, panel_id=f"{name}:{r['drug']}", role=role))
        if role != 'target':
            for label, count in zip(category_labels(r['low'], r['high']), r['counts']):
                counts.append(dict(cohort_id=cohort, panel_id=f"{name}:{r['drug']}", category=label, count=count,
                                   rank_convention='ceiling', original_n=r['n']))
    write_csv(work / 'counts.csv', counts)
    write_csv(work / 'roster.csv', roster)
    years = info['years']
    write_json(work / 'metadata.json', dict(
        protocol_label=f'MIC-50-90 confirmation {name} {reference}',
        unit_definition=f"State of collection within one year ({info['source']}, {info['agency']}, {info['genus']})",
        cohort_selection_rule='evaluation/PROTOCOL.md section 6: states with at least five isolates for every included drug',
        roster_provenance=f"Training {years['training']}, calibration {years['calibration']}, test {years['test']}; fixed by prepare_benchmark.py",
        counts_provenance=f"Complete isolate-level category counts of {info['source']} (public data); test-year counts are not supplied",
        grouping=dict(program=info['source'], organism=info['genus'], agency=info['agency'], years=f"{years['training']}-{years['test']}"),
        panel_provenance={pid: f'Doubling-dilution panel {benchmark.label(benchmark.level(lo))}-{benchmark.label(benchmark.level(hi))} mg/L '
                          'with censored ends, derived from the recorded signs and values (PROTOCOL.md section 2)'
                          for pid, (lo, hi) in panels.items()}))
    return panels


def real(name, info, rows, reference, folder):
    from mic_50_90.cli import main as cli
    from mic_50_90.model import format_mic
    started = perf_counter()
    work = folder / 'work'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    panels = dataset_inputs(name, info, rows, work, reference)
    arguments = ['calibration-prepare', str(work / 'counts.csv'), '--panels', str(work / 'panels.csv'), '--roster', str(work / 'roster.csv'),
                 '--metadata', str(work / 'metadata.json'), '--level', str(info['level']), '--output-dir', str(work / 'prepared')]
    if reference == 'trained':
        arguments += ['--reference-method', 'training', '--transport-scaling', 'training']
    assert cli(arguments) == 0, f'calibration-prepare refused {name} {reference}'
    prepared = read_json(work / 'prepared' / 'preparation.json')
    manifest = prepared['manifest']
    scales = prepared.get('transport_scales') or {}
    test = [r for r in rows if r['role'] == 'test']
    summaries, targets, truths, roster = [], [], [], []
    for r in test:
        cohort = f"{name}:{r['year']}:{r['unit_id']}:{r['drug']}"
        labels = category_labels(r['low'], r['high'])
        cumulative = np.cumsum(r['counts'])
        mic = [labels[int(np.searchsorted(cumulative, math.ceil(round(p * r['n'], 9))))] for p in (0.5, 0.9)]
        summaries.append(dict(cohort_id=cohort, panel_id=f"{name}:{r['drug']}", variant_id='primary', n=r['n'], mic50=mic[0], mic90=mic[1],
                              rank_convention='ceiling', iid='false', metadata_basis='Confirmation test year; complete table withheld',
                              source_location=f"{info['source']} {r['year']} / {r['unit_id']} / {r['drug']}",
                              rank_basis='Ceiling ranks; complete recorded category denominator; no extrema',
                              panel_basis='Doubling-dilution panel derived from the recorded signs and values'))
        thresholds = [benchmark.level(s) for s in range(r['low'], r['high'] + 1)]
        for t, j in zip(thresholds, range(len(thresholds))):
            targets.append(dict(cohort_id=cohort, threshold=t, unit='mg/L'))
            item = dict(unit_id=f"{r['year']}:{r['unit_id']}", cohort_id=cohort, target_id='gt:' + format_mic(t), drug=r['drug'],
                        threshold=t, original_n=r['n'])
            roster.append(item)
            truths.append(item | dict(truth=sum(r['counts'][j + 1:]) / r['n'], row=r))
    mappings = {s['cohort_id']: prepared['calibrations'][s['cohort_id']] for s in summaries}
    records = public_batch(work, summaries, targets, [row for pid, (lo, hi) in sorted(panels.items()) for row in panel_rows(pid, lo, hi)],
                           mappings, .05)
    observed, largest, cache = [], 0., {}
    for truth in truths:
        record = records[truth['cohort_id']]
        assert record['status'] == 'ok', record
        v = interval(record, truth['threshold'])
        assert v['sample_lower'] - TOLERANCE <= truth['truth'] <= v['sample_upper'] + TOLERANCE
        r = truth['row']
        pid = f"{name}:{r['drug']}"
        if truth['cohort_id'] not in cache:
            panel = dict(categories=[dict(c) for c in benchmark.panel(r['low'], r['high'])['categories']])
            cache[truth['cohort_id']] = ball_endpoints(r, panel, prepared['references'][pid], manifest['radius'] * float(scales.get(pid, 1.0)),
                                                       [benchmark.level(s) for s in range(r['low'], r['high'] + 1)])
        expected = cache[truth['cohort_id']][float(truth['threshold'])]
        largest = max(largest, abs(v['lower'] - expected[0]), abs(v['upper'] - expected[1]))
        observed.append(dict(unit_id=truth['unit_id'], cohort_id=truth['cohort_id'], target_id=truth['target_id'], truth=truth['truth'],
                             status='ok', lower=v['lower'], upper=v['upper'], baseline_lower=v['sample_lower'], baseline_upper=v['sample_upper'],
                             covered=v['lower'] - TOLERANCE <= truth['truth'] <= v['upper'] + TOLERANCE))
    assert largest < 2e-6, largest
    units = {}
    for o in observed:
        units[o['unit_id']] = units.get(o['unit_id'], True) and o['covered']
    write_csv(work / 'observed.csv', [{k: v for k, v in o.items() if k != 'covered'} for o in observed])
    write_csv(work / 'intended-roster.csv', [{k: v for k, v in t.items()} for t in roster])
    write_json(work / 'manifest.json', manifest)
    assert cli(['calibration-audit', str(work / 'observed.csv'), '--roster', str(work / 'intended-roster.csv'), '--manifest',
                str(work / 'manifest.json'), '--tolerance', '1e-7', '--output-dir', str(work / 'audit')]) == 0
    audit = read_json(work / 'audit' / 'audit.json')['summary']
    assert audit['successful_units'] == sum(units.values())
    write_csv(folder / 'intervals.csv.gz', observed)
    write_json(folder / 'manifest.json', manifest)
    return dict(dataset=name, reference=reference, source=info['source'], genus=info['genus'], agency=info['agency'], years=info['years'],
                drugs=info['drugs'], nominal_level=manifest['confidence_level'], calibration_rank=manifest['rank'],
                calibration_units=manifest['calibration_size'], radius=manifest['radius'], test_units=len(units),
                test_units_covered=sum(units.values()), audit_successful_units=audit['successful_units'],
                test_tails=len(observed), test_tails_covered=sum(o['covered'] for o in observed),
                mean_width_pp=100 * float(np.mean([o['upper'] - o['lower'] for o in observed])),
                mean_sample_width_pp=100 * float(np.mean([o['baseline_upper'] - o['baseline_lower'] for o in observed])),
                maximum_independent_endpoint_difference=largest, seconds=perf_counter() - started,
                missed=[{k: v for k, v in o.items() if k != 'covered'} for o in observed if not o['covered']])


# ---------------------------------------------------------------- synthetic units

def mixture(spread, weight, shift, centre=0.5, k=SYNTHETIC_K):
    from scipy.stats import norm
    cuts = np.arange(k - 1, dtype=float)
    def probabilities(c):
        return np.diff(np.r_[0.0, norm.cdf(cuts, loc=c, scale=spread), 1.0])
    return (1 - weight) * probabilities(centre) + weight * probabilities(centre + shift)


P0 = dict(spread=0.75, weight=0.2, shift=4.0)
TESTS = (('SU1', {}), ('SU2', dict(weight=0.05)), ('SU2', dict(weight=0.1)), ('SU2', dict(weight=0.2)), ('SU2', dict(shift_all=1)),
         ('SU3', {}))


def unit_score(counts):
    """Smallest transport radius at which the interval from MIC50 and MIC90 contains every tail (uniform reference)."""
    from mic_50_90 import dro
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import parse_spec
    counts = np.asarray(counts, dtype=int)
    n = int(counts.sum())
    spec_panel = benchmark.panel(0, SYNTHETIC_K - 2)
    labels = [c['label'] for c in spec_panel['categories']]
    cumulative = np.cumsum(counts)
    quantiles = [dict(probability=p, convention='ceiling', category=labels[int(np.searchsorted(cumulative, math.ceil(round(p * n, 9))))])
                 for p in (0.5, 0.9)]
    spec = parse_spec(dict(n=n, panel=spec_panel, unit='mg/L', summaries=dict(quantiles=quantiles),
                           thresholds=[benchmark.level(s) for s in range(0, SYNTHETIC_K - 1)]))
    problem = EmpiricalProblem(n=spec.n, panel=spec.panel, quantiles=spec.quantiles)
    reference = np.full(SYNTHETIC_K, 1 / SYNTHETIC_K)
    _, projected = dro.project_onto_sharp_set(problem=problem, reference=reference)
    objectives = [spec.panel.panel_tail(t) for t in spec.thresholds]
    truths = [float(a @ counts / n) for a in objectives]
    return float(dro.critical_radius(problem=problem, reference=projected, positions=None, objectives=objectives, truths=truths))


def draw_units(rng, count, concentration, kind=None, change=None):
    units = []
    for _ in range(count):
        size = int(rng.choice((20, 50, 100)))
        if kind == 'SU3':
            p = mixture(P0['spread'], P0['weight'], P0['shift'], centre=0.5 + 0.5 * rng.standard_normal())
        else:
            weight = P0['weight'] + (change or {}).get('weight', 0.0)
            centre = 0.5 + (change or {}).get('shift_all', 0.0)
            base = mixture(P0['spread'], weight, P0['shift'], centre=centre)
            p = rng.dirichlet(concentration * base + 1e-9)
        units.append(rng.multinomial(size, p / p.sum()))
    return units


def synthetic_repetition(task):
    setting, index, repetition, concentration, size, path = task
    rng = np.random.default_rng([SEED, 4, index, repetition])
    calibration = [unit_score(u) for u in draw_units(rng, size, concentration)]
    rank = math.ceil(0.95 * (size + 1))
    radius = sorted(calibration)[rank - 1]
    out = dict(setting=setting, repetition=repetition, radius=radius, tests={})
    for test_index, (kind, change) in enumerate(TESTS):
        label = kind + ''.join(f'|{k}={v}' for k, v in change.items())
        units = draw_units(np.random.default_rng([SEED, 5, index, repetition, test_index]), 100, concentration, kind, change)
        scores = [unit_score(u) for u in units]
        out['tests'][label] = sum(s <= radius + 1e-9 for s in scores)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(out), encoding='utf-8')
    temporary.replace(path)
    return path.name


def synthetic(folder, workers, repetitions, shard=None):
    blocks = folder / 'blocks'
    blocks.mkdir(parents=True, exist_ok=True)
    settings = [(f'c={c}|M={m}', i, c, m) for i, (c, m) in enumerate((c, m) for c in (20, 100) for m in (19, 39))]
    tasks = [(name, i, r, c, m, blocks / f'{i}-{r:04d}.json') for name, i, c, m in settings for r in range(repetitions)
             if not (blocks / f'{i}-{r:04d}.json').exists()]
    if shard:
        tasks = [t for t in tasks if (t[1] * repetitions + t[2]) % shard[1] == shard[0]]
    started = perf_counter()
    with ProcessPoolExecutor(workers) as pool:
        for done, _ in enumerate(pool.map(synthetic_repetition, tasks, chunksize=1), 1):
            if done % max(1, len(tasks) // 20) == 0 or done == len(tasks):
                print(json.dumps(dict(synthetic_done=done, of=len(tasks), elapsed=round(perf_counter() - started, 1))), flush=True)
    if shard:
        return None
    results = []
    for name, i, c, m in settings:
        reps = [json.loads((blocks / f'{i}-{r:04d}.json').read_text()) for r in range(repetitions)]
        entry = dict(setting=name, concentration=c, calibration_units=m, nominal_level=0.95, repetitions=repetitions,
                     rank=math.ceil(0.95 * (m + 1)), mean_radius=float(np.mean([x['radius'] for x in reps])), tests={})
        for label in reps[0]['tests']:
            covered = [x['tests'][label] for x in reps]
            entry['tests'][label] = dict(test_units=100 * repetitions, covered=int(sum(covered)), coverage=sum(covered) / (100 * repetitions),
                                         lowest_repetition=min(covered) / 100, highest_repetition=max(covered) / 100)
        results.append(entry)
    with gzip.open(folder / 'repetitions.jsonl.gz', 'wt', encoding='utf-8') as handle:
        for name, i, c, m in settings:
            for r in range(repetitions):
                handle.write((blocks / f'{i}-{r:04d}.json').read_text() + '\n')
    shutil.rmtree(blocks)
    return results


def real_job(task):
    name, reference, info, folder, keep = task
    target = folder / f'{name}-{reference}' / 'summary.json'
    rows = [r for r in benchmark.units() if r['dataset'] == name]
    result = real(name, info, rows, reference, target.parent)
    result.update(created_utc=now(), environment=common.environment())
    write_json(target, result)
    if not keep:
        shutil.rmtree(target.parent / 'work', ignore_errors=True)
    return name, reference


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--parts', default='real,synthetic')
    parser.add_argument('--repetitions', type=int, default=200, help='synthetic repetitions per setting (default 200)')
    parser.add_argument('--keep-work', action='store_true')
    parser.add_argument('--shard', help='run only part i of n of the work (i/n); a run without --shard collects it')
    args = parser.parse_args()
    folder = args.output.resolve() / 'external_calibration'
    parts = args.parts.split(',')
    summary_path = DATA / 'benchmark' / 'summary.json'
    datasets = read_json(summary_path)['calibration_datasets']
    shard = benchmark.shard_argument(args.shard)
    real_results, not_evaluable, jobs = [], [], []
    if 'real' in parts:
        for name, info in datasets.items():
            if not info['level']:
                not_evaluable.append(dict(dataset=name, reason='fewer than nine calibration units', units=info['units']))
                continue
            jobs += [(name, reference) for reference in REFERENCES]
        if shard:
            jobs = [job for i, job in enumerate(jobs) if i % shard[1] == shard[0]]
        # Completed jobs must not change ownership in staggered or resumed shards.
        jobs = [(name, reference) for name, reference in jobs
                if not (folder / f'{name}-{reference}' / 'summary.json').exists()]
        with ProcessPoolExecutor(max(1, min(args.workers, len(jobs) or 1))) as pool:
            for name, reference in pool.map(real_job, [(n, r, datasets[n], folder, args.keep_work) for n, r in jobs]):
                print(json.dumps(dict(real_done=name, reference=reference)), flush=True)
        for name, info in datasets.items() if not shard else ():
            for reference in REFERENCES if info['level'] else ():
                result = read_json(folder / f'{name}-{reference}' / 'summary.json')
                print(json.dumps({k: result[k] for k in ('dataset', 'reference', 'nominal_level', 'test_units', 'test_units_covered',
                                                         'mean_width_pp', 'mean_sample_width_pp')}), flush=True)
                real_results.append({k: v for k, v in result.items() if k not in ('missed', 'environment')})
    if shard and 'synthetic' not in parts:
        return
    synthetic_results = None
    if 'synthetic' in parts:
        target = folder / 'synthetic' / 'summary.json'
        if shard:
            synthetic(target.parent, args.workers, args.repetitions, shard)
            return
        if not target.exists():
            write_json(target, dict(settings=synthetic(target.parent, args.workers, args.repetitions), repetitions=args.repetitions,
                                    created_utc=now(), environment=common.environment()))
        synthetic_results = read_json(target)
    full = set(parts) == {'real', 'synthetic'} and args.repetitions == 200
    write_json(folder / 'summary.json', dict(comparison='external_calibration', created_utc=now(), status='complete', full_design=full,
               real=real_results, not_evaluable=not_evaluable, synthetic=synthetic_results, environment=common.environment()))


if __name__ == '__main__':
    main()
