"""Calibration of the optional Wasserstein-ball intervals on held-out surveillance units.

Two designs use Salmonella MIC tables measured on the CMV5AGNF panel (14 drugs):

NARMS retail 2021. Nineteen collection blocks (a collection region or laboratory, all 14 drugs)
are split by a fixed hash order into 4 training, 9 calibration and 6 test blocks. The reference
for each drug is the pooled training table. Each calibration block is scored by the largest
transport radius needed to contain every true tail of all its drugs; the 9th of 9 block scores
gives a nominal 90% radius. The public batch command then receives only summaries (n, ceiling
MIC50 and MIC90), panels, targets and the calibration, and a test block is covered when every
tail of all its 14 drug cohorts lies inside its interval.

FSIS raw poultry 2020-2021. Plant groups (establishments under one owner) with at least five
isolates, 19 for calibration and 30 for evaluation, all 14 drugs (95%, rank 19 of 19). Two
references are compared:
  uniform  a fixed uniform reference with unit transport scale (no training data);
  trained  the calibration-prepare command: a reference learned from four NARMS training blocks
           with training-only transport scaling.
A test group is covered when all 92 tails of its 14 drug cohorts lie inside their intervals.
Mean widths are averaged over the 2760 test tails (92 per group, so groups weigh equally).

Every calibration score is checked against an independent transport linear program, and every
returned interval against an independent closed-form calculation of the ball's endpoints.

Output: OUTPUT/calibration/{narms,fsis-uniform,fsis-trained}/ (summary.json, intervals.csv.gz,
manifest.json) and OUTPUT/calibration/summary.json. Each part is skipped when its summary exists.
"""
from __future__ import annotations

import common

import json
import shutil
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from time import perf_counter

import numpy as np

from common import DATA, now, read_csv, read_json, read_jsonl, sha256, write_csv, write_json

INPUT = DATA / 'calibration'
TOLERANCE = 1e-7
NARMS_PROTOCOL = 'MIC5090-NARMS2021|training-reference|ceiling50-90|all14'
FSIS_PROTOCOL = 'MIC5090-FSIS|fixed-uniform|ceiling50-90|all14'
FSIS_GROUPING = {'program': 'USDA-FSIS raw poultry, FDA-linked signs', 'years': '2020-2021',
                 'organism': 'Salmonella spp.', 'panel': 'CMV5AGNF'}
FSIS_UNIT = ('Conservative FSIS plant group: establishments linked by ownership, pooled over every included year, project and all fourteen drugs; '
             'dependence not proven absent')
NARMS_UNIT = 'Conservative NARMS collection-region/laboratory block; all 14 drugs'


# ---------------------------------------------------------------- scores and independent checks

def specification(row, panels, thresholds):
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICPanel, parse_spec
    from mic_50_90.workflows import counts_spec
    panel = MICPanel.from_dict(panels[row['panel_id']])
    raw, counts = counts_spec([{'category': label, 'count': count, 'rank_convention': 'ceiling'}
                               for label, count in zip(row['labels'], row['counts'])], panel, thresholds, {'enabled': False})
    assert raw['n'] == row['original_n'] == row['counted_n']
    spec = parse_spec(raw)
    return raw, spec, EmpiricalProblem(n=spec.n, panel=panel, quantiles=spec.quantiles), counts


def direct_score(spec, reference, counts):
    """Independent k*k transport LP with each true tail imposed as an equality."""
    from scipy.optimize import linprog
    k = len(reference)
    positions = np.log2(spec.panel.panel_values)
    costs = np.abs(positions[:, None] - positions[None, :]).ravel()
    margins = np.array([np.repeat(np.eye(k)[i], k) for i in range(k)])
    cumulative = [np.tile(np.arange(k) <= j, k).astype(float) for j in range(k)]
    rows, values = [], []
    for q in spec.quantiles:
        rows.append(-cumulative[q.category_index])
        values.append(-q.rank / spec.n)
        if q.category_index > 0:
            rows.append(cumulative[q.category_index - 1])
            values.append((q.rank - 1) / spec.n)
    scores = []
    for t in spec.thresholds:
        objective = spec.panel.panel_tail(t)
        truth = float(objective @ counts / spec.n)
        fit = linprog(costs, A_ub=np.array(rows), b_ub=values, A_eq=np.vstack([margins, np.tile(objective, k)]),
                      b_eq=np.r_[reference, truth], bounds=(0, None), method='highs')
        if not fit.success:
            raise RuntimeError('Independent transport LP failed: ' + fit.message)
        scores.append(float(fit.fun))
    return max(scores)


def score(task):
    """Critical radius of one calibration cohort (package bisection), checked by the independent LP."""
    from mic_50_90 import dro
    row, panels, reference, thresholds, steps = task
    started = perf_counter()
    _, spec, problem, counts = specification(row, panels, thresholds)
    distance, projected = dro.project_onto_sharp_set(problem=problem, reference=np.array(reference))
    objectives = [spec.panel.panel_tail(t) for t in spec.thresholds]
    truths = [float(a @ counts / spec.n) for a in objectives]
    options = dict(steps=steps) if steps else {}
    value = dro.critical_radius(problem=problem, reference=projected, positions=None, objectives=objectives, truths=truths, **options)
    independent = direct_score(spec, projected, counts)
    if not np.isfinite(value) or abs(value - independent) > 2e-6:
        raise RuntimeError(f"{row['cohort_id']}: critical radius {value} differs from the independent value {independent}")
    return dict(cohort_id=row['cohort_id'], unit_id=row.get('unit_id', row.get('block_id')), drug=row['drug'], score=float(value),
                independent_score=independent, projection_distance=distance, seconds=perf_counter() - started)


def ball_endpoints(row, panel, reference, radius, thresholds):
    """Closed-form endpoints of the transport ball around the projected reference, for every cut."""
    counts = np.array(row['counts'], dtype=int)
    n = int(counts.sum())
    cum, m = counts.cumsum(), len(counts) - 1
    lower, upper = np.zeros(m), np.ones(m)
    for rank in ((n + 1) // 2, (9 * n + 9) // 10):
        category = int(np.searchsorted(cum, rank))
        lower[category:] = np.maximum(lower[category:], rank / n)
        upper[:category] = np.minimum(upper[:category], (rank - 1) / n)
    centre = np.clip(np.cumsum(reference)[:-1], lower, upper)
    weights = np.diff(np.log2([b['panel_value'] for b in panel['categories']]))

    def cost(j, value):
        return float(np.maximum(centre[:j + 1] - value, 0) @ weights[:j + 1] + np.maximum(value - centre[j:], 0) @ weights[j:])
    lo, hi = lower.copy(), upper.copy()
    for j in range(m):
        if cost(j, lo[j]) > radius:
            a, b = lo[j], centre[j]
            for _ in range(48):
                a, b = ((a + b) / 2, b) if cost(j, (a + b) / 2) > radius else (a, (a + b) / 2)
            lo[j] = a
        if cost(j, hi[j]) > radius:
            a, b = centre[j], hi[j]
            for _ in range(48):
                a, b = (a, (a + b) / 2) if cost(j, (a + b) / 2) > radius else ((a + b) / 2, b)
            hi[j] = b
    return {float(cut): (1 - hi[j], 1 - lo[j]) for j, cut in enumerate(thresholds)}


def scores(rows, panels, references, thresholds, steps, workers, checkpoint):
    """Scores for all calibration cohorts, saved line by line so that an interrupted part resumes."""
    done = {r['cohort_id']: r for r in read_jsonl(checkpoint)} if checkpoint.exists() else {}
    pending = [r for r in rows if r['cohort_id'] not in done]
    tasks = [(r, panels, references(r), thresholds(r), steps) for r in pending]
    with checkpoint.open('a', encoding='utf-8') as handle, ProcessPoolExecutor(workers) as pool:
        for i, result in enumerate(pool.map(score, tasks, chunksize=1), 1):
            done[result['cohort_id']] = result
            handle.write(json.dumps(result) + '\n')
            handle.flush()
            if i % 28 == 0 or i == len(tasks):
                print(json.dumps(dict(stage=checkpoint.parent.name, scored=len(done), of=len(rows))), flush=True)
    return [done[r['cohort_id']] for r in rows]


def public_batch(work, summaries, targets, panels_csv, mappings, limit):
    """Apply the calibration through the public batch command, which sees no histogram and no truth."""
    from mic_50_90.cli import main as cli
    source = work / 'public-inputs'
    source.mkdir(parents=True, exist_ok=True)
    write_csv(source / 'summaries.csv', summaries)
    write_csv(source / 'targets.csv', targets)
    if isinstance(panels_csv, list):
        write_csv(source / 'panels.csv', panels_csv)
    else:
        shutil.copyfile(panels_csv, source / 'panels.csv')
    write_json(source / 'calibrations.json', mappings, indent=None)
    status = cli(['batch', str(source / 'summaries.csv'), '--panels', str(source / 'panels.csv'), '--targets', str(source / 'targets.csv'),
                  '--calibrations', str(source / 'calibrations.json'), '--question-time-limit', str(limit),
                  '--output-dir', str(work / 'public-report')])
    assert status == 0, 'batch command failed'
    return {r['cohort_id']: r for r in read_json(work / 'public-report/results.json')}


def summary_row(row, raw, source_location, panel_basis, metadata_basis):
    return dict(cohort_id=row['cohort_id'], panel_id=row['panel_id'], variant_id='primary', n=raw['n'],
                mic50=raw['summaries']['quantiles'][0]['category'], mic90=raw['summaries']['quantiles'][1]['category'],
                rank_convention='ceiling', iid='false', source_doi='10.1128/spectrum.03485-23', metadata_basis=metadata_basis,
                source_location=source_location, rank_basis='Ceiling ranks; complete recorded category denominator; no extrema',
                panel_basis=panel_basis)


def interval(record, threshold):
    """Calibrated and sharp sample interval for one tail from a batch record."""
    result = record['result']
    scenario = result['assumption_dependent_scenarios'].get('wasserstein_ambiguity_set')
    assert scenario, result.get('conformal_unavailable_reason')
    bound = next(x['envelope'] for x in scenario['threshold_results'] if float(x['threshold']) == float(threshold))
    basic = next(x['panel_recorded_estimand'] for x in result['reporting_uncertainty_envelope']['envelope']
                 if float(x['threshold']) == float(threshold))
    values = dict(lower=bound['lower'], upper=bound['upper'], sample_lower=basic['lower']['fraction'], sample_upper=basic['upper']['fraction'])
    for key, value in values.items():
        assert -1e-12 <= value <= 1 + 1e-12
        values[key] = min(1., max(0., value))
    if values['lower'] > values['upper']:
        assert values['lower'] - values['upper'] <= 1e-12
        values['lower'], values['upper'] = values['upper'], values['lower']
    return values


# ---------------------------------------------------------------- NARMS

def narms(folder, workers):
    from mic_50_90.conformal import calibrate_wasserstein_manifest
    started = perf_counter()
    work = folder / 'work'
    work.mkdir(parents=True, exist_ok=True)
    panels = read_json(INPUT / 'panels.json')
    rows = read_jsonl(INPUT / 'narms_histograms.jsonl')
    assert len(rows) == 266 and all(r['status'] == 'eligible' for r in rows)
    references = {}
    for drug in sorted({r['drug'] for r in rows}):
        training = [r for r in rows if r['split'] == 'training' and r['drug'] == drug]
        assert len(training) == 4
        counts = np.sum([r['counts'] for r in training], axis=0)
        references[drug] = (counts / counts.sum()).tolist()
    calibration = [r for r in rows if r['split'] == 'calibration']
    levels = lambda r: panels[r['panel_id']]['levels']
    scored = scores(calibration, panels, lambda r: references[r['drug']], levels, None, workers, work / 'calibration-scores.jsonl')
    grouping = {'program': 'NARMS retail', 'year': '2021', 'species': 'Salmonella enterica', 'panel': 'CMV5AGNF'}
    manifest = calibrate_wasserstein_manifest(
        group_scores=[r['score'] for r in scored], group_units=[r['unit_id'] for r in scored], alpha=.1, grouping=grouping,
        source=NARMS_PROTOCOL, data_hashes={'narms_histograms': sha256(INPUT / 'narms_histograms.jsonl'), 'panels': sha256(INPUT / 'panels.json')},
        calibrate_on='units', unit_aggregation='max',
        calibration_contract=dict(score_kind='simultaneous_tail_intervals', reference_rule='projected', functional_scope='all_panel_tails',
                                  transport_unit='log2_mg_L', summary_policy='ceiling_50_90_no_range', reference_protocol=NARMS_PROTOCOL,
                                  unit_definition=NARMS_UNIT)).as_dict()
    assert manifest['rank'] == manifest['calibration_size'] == 9 and manifest['confidence_level'] == .9
    write_json(folder / 'manifest.json', manifest)
    test = [r for r in rows if r['split'] == 'test']
    summaries, targets, mappings, truths = [], [], {}, {}
    for row in test:
        raw, spec, _, counts = specification(row, panels, levels(row))
        summaries.append(summary_row(row, raw, f"NARMS retail 2021 / {row['block_id']} / {row['drug']}",
                                     panels[row['panel_id']]['axis_label'] + '; independent CMV5AGNF grid; program-year assignment; plate field blank',
                                     'NARMS 2021 withheld full-category validation'))
        targets += [dict(cohort_id=row['cohort_id'], threshold=t, unit='mg/L') for t in spec.thresholds]
        mappings[row['cohort_id']] = dict(reference_distribution=references[row['drug']], wasserstein_calibration_manifest=manifest,
                                          calibration_context=dict(unit='mg/L', reference_protocol=NARMS_PROTOCOL, grouping=grouping))
        truths[row['cohort_id']] = {float(t): float(spec.panel.panel_tail(t) @ counts / spec.n) for t in spec.thresholds}
    panel_rows = [dict(panel_id=pid, category=b['label'], unit='mg/L', lower=b['lower_bound'], upper=b['upper_bound'],
                       lower_closed=str(b['lower_closed']).lower(), upper_closed=str(b['upper_closed']).lower(), panel_value=b['panel_value'])
                  for pid, panel in panels.items() for b in panel['categories']]
    records = public_batch(work, summaries, targets, panel_rows, mappings, .05)
    observed, blocks, largest = [], {}, 0.
    for row in test:
        record = records[row['cohort_id']]
        assert record['status'] == 'ok', record
        expected = ball_endpoints(row, panels[row['panel_id']], references[row['drug']], manifest['radius'], levels(row))
        for t, truth in truths[row['cohort_id']].items():
            v = interval(record, t)
            assert v['sample_lower'] - TOLERANCE <= truth <= v['sample_upper'] + TOLERANCE
            largest = max(largest, abs(v['lower'] - expected[t][0]), abs(v['upper'] - expected[t][1]))
            covered = v['lower'] - TOLERANCE <= truth <= v['upper'] + TOLERANCE
            observed.append(dict(cohort_id=row['cohort_id'], block_id=row['block_id'], drug=row['drug'], n=row['original_n'],
                                 threshold=t, truth=truth, **v, covered=covered))
            blocks.setdefault(row['block_id'], []).append(covered)
    assert largest < 2e-6, largest
    write_csv(folder / 'intervals.csv.gz', observed)
    cohorts = {}
    for r in observed:
        cohorts[r['cohort_id']] = cohorts.get(r['cohort_id'], True) and r['covered']
    result = dict(part='narms', test_blocks=len(blocks), test_blocks_covered=sum(all(v) for v in blocks.values()),
                  blocks={b: all(v) for b, v in sorted(blocks.items())}, test_cohorts=len(test), test_cohorts_returned=len(records),
                  test_cohorts_covered=sum(cohorts.values()), test_tails=len(observed), test_tails_covered=sum(r['covered'] for r in observed),
                  tails_narrowed=sum(r['sample_upper'] - r['sample_lower'] - r['upper'] + r['lower'] > TOLERANCE for r in observed),
                  mean_sample_width_pp=100 * float(np.mean([r['sample_upper'] - r['sample_lower'] for r in observed])),
                  mean_width_pp=100 * float(np.mean([r['upper'] - r['lower'] for r in observed])),
                  radius=manifest['radius'], nominal_level=manifest['confidence_level'], calibration_blocks=manifest['calibration_size'],
                  maximum_independent_score_difference=max(abs(r['score'] - r['independent_score']) for r in scored),
                  maximum_independent_endpoint_difference=largest,
                  missed=[r for r in observed if not r['covered']], seconds=perf_counter() - started)
    return result


# ---------------------------------------------------------------- FSIS

def fsis_rows():
    split = read_csv(INPUT / 'fsis_split.csv')
    rows = read_jsonl(INPUT / 'fsis_histograms.jsonl')
    roles = {r['unit_id']: r['role'] for r in split}
    assert sum(v == 'calibration' for v in roles.values()) == 19 and sum(v == 'test' for v in roles.values()) == 30
    ordered = sorted(rows, key=lambda r: (int(r['unit_id']), r['drug']))
    return [r for r in ordered if roles[r['unit_id']] == 'calibration'], [r for r in rows if roles[r['unit_id']] == 'test']


def fsis_apply(folder, method, manifest, refs, scales, mappings):
    """Public batch on the thirty test groups, coverage by group, and the independent endpoint check."""
    from mic_50_90.cli import main as cli
    from mic_50_90.model import format_mic
    work = folder / 'work'
    panels = read_json(INPUT / 'panels.json')
    _, test = fsis_rows()
    summaries, targets, truths, roster = [], [], [], []
    for row in test:
        raw, spec, _, counts = specification(row, panels, row['thresholds'])
        summaries.append(summary_row(row, raw, f"FSIS 2020-2021 plant group {row['unit_id']} / {row['drug']}",
                                     panels[row['panel_id']]['axis_label'] + '; CMV5AGNF program-year grid, not lot-level verification',
                                     'FSIS full-denominator validation; program-year panel assignment'))
        for t in spec.thresholds:
            targets.append(dict(cohort_id=row['cohort_id'], threshold=t, unit='mg/L'))
            numerator = int(spec.panel.panel_tail(t) @ counts)
            item = dict(unit_id=row['unit_id'], cohort_id=row['cohort_id'], target_id='gt:' + format_mic(t), drug=row['drug'],
                        threshold=t, original_n=spec.n)
            roster.append(item)
            truths.append(item | dict(truth=numerator / spec.n))
    assert len(truths) == 30 * 92
    if mappings is None:
        mappings = {row['cohort_id']: dict(reference_distribution=refs[row['panel_id']], wasserstein_calibration_manifest=manifest,
                    calibration_context=dict(unit='mg/L', reference_protocol=manifest['calibration_contract']['reference_protocol'],
                                             grouping=manifest['grouping'])) for row in test}
    else:
        mappings = {row['cohort_id']: mappings[row['cohort_id']] for row in test}
    records = public_batch(work, summaries, targets, INPUT / 'fsis_panels.csv', mappings, .01)
    rows = {r['cohort_id']: r for r in test}
    observed, endpoints, largest = [], {}, 0.
    for truth in truths:
        record = records[truth['cohort_id']]
        assert record['status'] == 'ok', record
        v = interval(record, truth['threshold'])
        if truth['cohort_id'] not in endpoints:
            row = rows[truth['cohort_id']]
            endpoints[truth['cohort_id']] = ball_endpoints(row, panels[row['panel_id']], refs[row['panel_id']],
                                                           manifest['radius'] * scales[row['panel_id']], row['thresholds'])
        expected = endpoints[truth['cohort_id']][float(truth['threshold'])]
        largest = max(largest, abs(v['lower'] - expected[0]), abs(v['upper'] - expected[1]))
        observed.append(dict(unit_id=truth['unit_id'], cohort_id=truth['cohort_id'], target_id=truth['target_id'], truth=truth['truth'],
                             status='ok', lower=v['lower'], upper=v['upper'], baseline_lower=v['sample_lower'], baseline_upper=v['sample_upper'],
                             covered=v['lower'] - TOLERANCE <= truth['truth'] <= v['upper'] + TOLERANCE))
    assert largest < 2e-6, largest
    units = {}
    for r in observed:
        units[r['unit_id']] = units.get(r['unit_id'], True) and r['covered']
    # The public audit command must count the same successes from the saved intervals and the intended roster.
    write_csv(work / 'observed.csv', [{k: v for k, v in r.items() if k != 'covered'} for r in observed])
    write_csv(work / 'intended-roster.csv', roster)
    write_json(work / 'manifest.json', manifest)
    assert cli(['calibration-audit', str(work / 'observed.csv'), '--roster', str(work / 'intended-roster.csv'), '--manifest',
                str(work / 'manifest.json'), '--tolerance', '1e-7', '--output-dir', str(work / 'audit')]) == 0
    audit = read_json(work / 'audit/audit.json')['summary']
    assert audit['successful_units'] == sum(units.values())
    write_csv(folder / 'intervals.csv.gz', observed)
    write_json(folder / 'manifest.json', manifest)
    return dict(part='fsis-' + method, reference=method, radius=manifest['radius'], nominal_level=manifest['confidence_level'],
                calibration_rank=manifest['rank'], calibration_groups=manifest['calibration_size'],
                test_groups=len(units), test_groups_covered=sum(units.values()), audit_successful_groups=audit['successful_units'],
                test_cohorts=len(test), test_tails=len(observed), test_tails_covered=sum(r['covered'] for r in observed),
                mean_width_pp=100 * float(np.mean([r['upper'] - r['lower'] for r in observed])),
                mean_sample_width_pp=100 * float(np.mean([r['baseline_upper'] - r['baseline_lower'] for r in observed])),
                maximum_independent_endpoint_difference=largest,
                missed=[r for r in observed if not r['covered']])


def fsis_uniform(folder, workers):
    from mic_50_90.conformal import calibrate_wasserstein_manifest
    started = perf_counter()
    (folder / 'work').mkdir(parents=True, exist_ok=True)
    panels = read_json(INPUT / 'panels.json')
    references = read_json(INPUT / 'fsis_uniform_references.json')
    calibration, _ = fsis_rows()
    assert len(calibration) == 19 * 14
    scored = scores(calibration, panels, lambda r: references[r['drug']], lambda r: r['thresholds'], 24, workers,
                    folder / 'work' / 'calibration-scores.jsonl')
    manifest = calibrate_wasserstein_manifest(
        group_scores=[r['score'] for r in scored], group_units=[r['unit_id'] for r in scored], alpha=.05, grouping=FSIS_GROUPING,
        source=FSIS_PROTOCOL + '|primary95', data_hashes={'fsis_histograms': sha256(INPUT / 'fsis_histograms.jsonl'),
                                                         'references': sha256(INPUT / 'fsis_uniform_references.json')},
        calibrate_on='units', unit_aggregation='max',
        calibration_contract=dict(score_kind='simultaneous_tail_intervals', reference_rule='projected', functional_scope='all_panel_tails',
                                  transport_unit='log2_mg_L', summary_policy='ceiling_50_90_no_range', reference_protocol=FSIS_PROTOCOL,
                                  unit_definition=FSIS_UNIT)).as_dict()
    assert manifest['rank'] == manifest['calibration_size'] == 19
    refs = {'CMV5AGNF:' + k: v for k, v in references.items()}
    result = fsis_apply(folder, 'uniform', manifest, refs, {k: 1. for k in refs}, None)
    result.update(maximum_independent_score_difference=max(abs(r['score'] - r['independent_score']) for r in scored),
                  seconds=perf_counter() - started)
    return result


def fsis_trained(folder, workers):
    from mic_50_90.cli import main as cli
    from mic_50_90.conformal import calibrate_wasserstein_manifest
    started = perf_counter()
    prepared_folder = folder / 'work' / 'prepared'
    if not (prepared_folder / 'preparation.json').exists():
        shutil.rmtree(prepared_folder, ignore_errors=True)
        assert cli(['calibration-prepare', str(INPUT / 'trained_counts.csv'), '--panels', str(INPUT / 'fsis_panels.csv'),
                    '--roster', str(INPUT / 'trained_roster.csv'), '--metadata', str(INPUT / 'trained_metadata.json'),
                    '--reference-method', 'training', '--transport-scaling', 'training', '--level', '.95',
                    '--output-dir', str(prepared_folder)]) == 0, 'calibration-prepare refused'
    prepared = read_json(prepared_folder / 'preparation.json')
    original = prepared['manifest']
    manifest = calibrate_wasserstein_manifest(
        group_scores=[r['score'] for r in prepared['cohort_scores']], group_units=[r['unit_id'] for r in prepared['cohort_scores']],
        alpha=.05, grouping=original['grouping'], source=original['source'], data_hashes=original['data_hashes'],
        calibrate_on='units', unit_aggregation='max', calibration_contract=original['calibration_contract']).as_dict()
    assert manifest['rank'] == manifest['calibration_size'] == 19 and manifest['radius'] == original['radius']
    mappings = deepcopy(prepared['calibrations'])
    for item in mappings.values():
        item['wasserstein_calibration_manifest'] = manifest
    result = fsis_apply(folder, 'trained', manifest, prepared['references'], prepared['transport_scales'], mappings)
    result.update(training_score_checks=len(prepared['training_scores']), calibration_scores=len(prepared['cohort_scores']),
                  maximum_independent_score_difference=max(r['absolute_disagreement'] for r in prepared['cohort_scores']),
                  transport_scales=prepared['transport_scales'], seconds=perf_counter() - started)
    return result


def main():
    parser = common.parser(__doc__)
    parser.add_argument('--parts', default='narms,fsis-uniform,fsis-trained', help='comma-separated parts (default: all three)')
    parser.add_argument('--keep-work', action='store_true', help='keep the batch reports and public inputs in each part/work folder')
    args = parser.parse_args()
    folder = args.output.resolve() / 'calibration'
    functions = {'narms': narms, 'fsis-uniform': fsis_uniform, 'fsis-trained': fsis_trained}
    parts = [p.strip() for p in args.parts.split(',')]
    assert set(parts) <= set(functions)
    for part in parts:
        target = folder / part / 'summary.json'
        if target.exists():
            print(json.dumps(dict(part=part, status='already complete')), flush=True)
            continue
        result = functions[part](folder / part, args.workers)
        result.update(created_utc=now(), environment=common.environment())
        write_json(target, result)
        if not args.keep_work:
            shutil.rmtree(folder / part / 'work', ignore_errors=True)
        print(json.dumps({k: v for k, v in result.items() if k not in ('missed', 'environment', 'transport_scales', 'blocks')}), flush=True)
    found = {p: read_json(folder / p / 'summary.json') for p in functions if (folder / p / 'summary.json').exists()}
    write_json(folder / 'summary.json', dict(comparison='calibration', created_utc=now(), status='complete' if len(found) == 3 else 'incomplete',
               full_design=len(found) == 3, environment=common.environment(),
               parts={p: {k: v for k, v in s.items() if k not in ('missed', 'environment')} for p, s in found.items()}))


if __name__ == '__main__':
    main()
