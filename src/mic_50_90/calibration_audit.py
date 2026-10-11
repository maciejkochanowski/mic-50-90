"""Planning and held-out assessment at the declared calibration-unit level."""
from __future__ import annotations

from collections import defaultdict
import csv
from hashlib import sha256
import html
import json
from math import ceil, isfinite, log
from pathlib import Path
from statistics import mean

from scipy.stats import beta, binom

from ._version import __version__
from .conformal import conformal_rank, minimum_calibration_size, validate_calibration_manifest
from .report import STYLE
from .validation import exact_integer


def _fraction(value, name, *, open_interval=False):
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a number, not a boolean')
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be a finite fraction') from exc
    valid = 0 < value < 1 if open_interval else 0 <= value <= 1
    if not isfinite(value) or not valid:
        raise ValueError(f'{name} must lie in ' + ('(0, 1)' if open_interval else '[0, 1]'))
    return value


def _integer(value, name):
    return exact_integer(value, name)


def _interval(row, names, key, corrections):
    """Normalize only bounded endpoint arithmetic error, preserving evidence."""
    values = []
    identifiers = dict(zip(('unit_id', 'cohort_id', 'target_id'), key))
    for name in names:
        raw = row.get(name)
        if isinstance(raw, bool):
            raise ValueError(f'{key}: {name} must be a number, not a boolean')
        try:
            raw = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{key}: {name} must be a finite endpoint') from exc
        if not isfinite(raw):
            raise ValueError(f'{key}: {name} must be a finite endpoint')
        value = min(1., max(0., raw))
        if abs(value-raw) > 1e-12:
            raise ValueError(f'{key}: {name} must lie in [0, 1]')
        if value != raw:
            corrections.append({**identifiers, 'kind':'domain_boundary', 'field':name,
                                'original':raw, 'normalized':value})
        values.append(value)
    lower, upper = values
    if lower > upper:
        if lower-upper > 1e-12:
            raise ValueError(f'{key}: lower endpoint exceeds upper endpoint')
        corrections.append({**identifiers, 'kind':'tiny_reversal', 'field':' / '.join(names),
                            'original_lower':lower, 'original_upper':upper,
                            'normalized_lower':upper, 'normalized_upper':lower})
        lower, upper = upper, lower
    return lower, upper


def plan_calibration(*, level=.95, assurance=.95, calibration_units=0, test_units=0):
    """Separate marginal rank feasibility, PAC planning and test precision.

    PAC means that coverage reaches ``level`` with probability ``assurance``
    over iid calibration samples. This planner does not upgrade a manifest.
    The test minimum assumes zero failures and is not a powered study design.
    """
    level = _fraction(level, 'level', open_interval=True)
    assurance = _fraction(assurance, 'assurance', open_interval=True)
    m = _integer(calibration_units, 'calibration_units')
    n = _integer(test_units, 'test_units')
    rank = conformal_rank(m, 1-level) if m else 1
    zero_failure_minimum = ceil(log(1-assurance) / log(level) - 1e-12)
    pac_rank = None
    # Monotone binomial CDF permits an integer search even for a large roster.
    if m and binom.cdf(m-1, m, level) >= assurance:
        low, high = 1, m
        while low < high:
            middle = (low + high) // 2
            if binom.cdf(middle-1, m, level) >= assurance:
                high = middle
            else:
                low = middle + 1
        pac_rank = low
    return {
        'software_version': __version__, 'level': level, 'assurance': assurance,
        'calibration_units': m, 'test_units': n,
        'minimum_calibration_units_marginal': minimum_calibration_size(1-level),
        'maximum_supported_marginal_level': m / (m+1),
        'marginal_rank': rank if rank <= m else None,
        'minimum_calibration_units_pac': zero_failure_minimum,
        'pac_rank': pac_rank,
        'pac_assurance_at_maximum_score': 1-level**m,
        'minimum_test_units_all_success': zero_failure_minimum,
        'all_success_lower_bound': (1-assurance)**(1/n) if n else None,
        'assumptions': {
            'marginal': 'Exchangeable calibration and future units; fixed training and score rule',
            'pac': 'iid calibration and future units; fixed training and score rule',
            'test': 'iid held-out units; procedure and test size fixed before outcomes',
        },
        'interpretation': 'Planning calculations, not observed performance. The zero-failure test '
                          'minimum is optimistic; failures require a larger prespecified study. '
                          'Isolates, drugs and repeated years are not additional independent units.',
    }


def _key(row):
    values = []
    for name in ('unit_id', 'cohort_id', 'target_id'):
        value = row.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} must be a nonempty identifier')
        if value != value.strip():
            raise ValueError(f'{name} must not contain surrounding whitespace')
        values.append(value)
    return tuple(values)


def _index(rows, label):
    result, owners = {}, {}
    for row in rows:
        key = _key(row)
        if key in result:
            raise ValueError(f'{label}: duplicate unit/cohort/target identifier {key}')
        if key[1] in owners and owners[key[1]] != key[0]:
            raise ValueError(f'{label}: cohort {key[1]} belongs to more than one unit')
        owners[key[1]] = key[0]
        result[key] = row
    return result


def _labels(values, name):
    if isinstance(values, (str, bytes)):
        raise ValueError(f'{name} must be a list of unique unit identifiers')
    values = list(values)
    if any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in values):
        raise ValueError(f'{name} contains an invalid unit identifier')
    if len(values) != len(set(values)):
        raise ValueError(f'{name} contains duplicate identifiers')
    return set(values)


def audit_calibration(roster, observations, *, level=None, assurance=.95,
                      iid_units=False, procedure_frozen=False, manifest=None,
                      training_units=None, tolerance=0.):
    """Audit a fixed, complete intended target roster against held-out intervals.

    The roster must be frozen independently of the observed results. Missing
    planned observations remain in the operational-success denominator. The
    function checks identifiers, not biological independence or source validity.
    All-target unit containment is distinct from drug- or cut-level containment.
    Binomial precision is optional and requires explicit iid/frozen declarations.
    """
    if not isinstance(iid_units, bool) or not isinstance(procedure_frozen, bool):
        raise ValueError('iid_units and procedure_frozen must be boolean declarations')
    if iid_units and not procedure_frozen:
        raise ValueError('iid confidence limits require a frozen procedure and test size declaration')
    assurance = _fraction(assurance, 'assurance', open_interval=True)
    tolerance = _fraction(tolerance, 'tolerance')
    if tolerance > 1e-6:
        raise ValueError('tolerance must not exceed 1e-6; it is for numerical error, not missed coverage')
    intended = _index(roster, 'roster')
    observed = _index(observations, 'observations')
    if not intended:
        raise ValueError('roster must contain every intended target and cannot be empty')
    if observed.keys() - intended.keys():
        raise ValueError('observations contain foreign targets outside the intended roster')
    units = {key[0] for key in intended}
    assumptions = {
        'roster': 'User-supplied intended roster; prospective freezing and completeness require source verification',
        'iid_units': 'declared, not verified' if iid_units else 'not declared; descriptive assessment only',
        'procedure_frozen': 'declared, not verified' if procedure_frozen else 'not declared',
        'calibration_disjointness': 'not checked: no manifest supplied',
        'training_disjointness': 'not checked: no training roster supplied',
        'event': 'Every planned recorded-category tail in a complete unit is contained',
    }
    if manifest is not None:
        validate_calibration_manifest(manifest)
        if manifest['manifest_version'] not in {'1.2', '1.3'}:
            raise ValueError('calibration audit requires manifest 1.2 or 1.3 with an explicit score contract')
        scaled_training = manifest['calibration_contract'].get('transport_scaling', {}).get('training_unit_labels', [])
        if units & set(scaled_training):
            raise ValueError('test units overlap the training unit labels in the manifest')
        if scaled_training:
            assumptions['training_disjointness'] = 'No exact unit-label overlap; biological overlap is not verified'
        if manifest['calibration_contract']['score_kind'] != 'simultaneous_tail_intervals':
            raise ValueError('tail rows cannot verify distribution-distance containment')
        if units & set(manifest['exchangeable_unit_labels']):
            raise ValueError('test units overlap calibration unit labels')
        if level is not None and abs(float(level)-float(manifest['confidence_level'])) > 1e-12:
            raise ValueError('audit level conflicts with the supplied manifest coverage level')
        level = float(manifest['confidence_level'])
        assumptions['calibration_disjointness'] = 'No exact unit-label overlap; biological overlap is not verified'
        assumptions['calibration_contract'] = dict(manifest['calibration_contract'])
    if training_units is not None:
        training = _labels(training_units, 'training_units')
        if units & training:
            raise ValueError('test units overlap training unit labels')
        if manifest is not None and training & set(manifest['exchangeable_unit_labels']):
            raise ValueError('training units overlap calibration unit labels')
        assumptions['training_disjointness'] = 'No exact unit-label overlap; biological overlap is not verified'
    level = _fraction(.95 if level is None else level, 'level', open_interval=True)
    targets, corrections = [], []
    for key in intended:
        row = observed.get(key)
        item = dict(zip(('unit_id', 'cohort_id', 'target_id'), key))
        item.update(status='unavailable', reason='Missing planned observation', available=False,
                    covered=False, truth=None, lower=None, upper=None, width=None,
                    baseline_lower=None, baseline_upper=None, width_reduction=None)
        if row is None:
            targets.append(item)
            continue
        status = row.get('status')
        if status not in {'ok', 'unavailable'}:
            raise ValueError(f'{key}: status must be ok or unavailable')
        if status == 'unavailable':
            reason = row.get('reason', '')
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f'{key}: unavailable observations require a reason')
            item['reason'] = reason.strip()
            targets.append(item)
            continue
        truth = _fraction(row.get('truth'), f'{key}: truth')
        lower, upper = _interval(row, ('lower', 'upper'), key, corrections)
        item.update(status='ok', reason='', available=True, truth=truth, lower=lower,
                    upper=upper, width=upper-lower, covered=lower-tolerance <= truth <= upper+tolerance)
        count_present = [row.get(name) not in (None, '') for name in ('truth_count', 'original_n')]
        if any(count_present):
            if not all(count_present):
                raise ValueError(f'{key}: truth_count and original_n must occur together')
            count = _integer(row['truth_count'], 'truth_count')
            n = _integer(row['original_n'], 'original_n')
            if n < 1 or count > n or abs(count/n-truth) > 1e-12:
                raise ValueError(f'{key}: truth does not match count/original_n')
            item.update(truth_count=count, original_n=n)
        baseline_present = [row.get(name) not in (None, '') for name in ('baseline_lower', 'baseline_upper')]
        if any(baseline_present):
            if not all(baseline_present):
                raise ValueError(f'{key}: both baseline endpoints are required')
            bl, bu = _interval(row, ('baseline_lower', 'baseline_upper'), key, corrections)
            if bl > bu or not bl-tolerance <= truth <= bu+tolerance:
                raise ValueError(f'{key}: baseline must be ordered and contain the same truth')
            if lower < bl-tolerance or upper > bu+tolerance:
                raise ValueError(f'{key}: calibrated interval is not nested within the baseline')
            item.update(baseline_lower=bl, baseline_upper=bu, width_reduction=(bu-bl)-(upper-lower))
        targets.append(item)

    def aggregate(field):
        groups = defaultdict(list)
        for row in targets:
            groups[row[field]].append(row)
        records = []
        for label, rows in groups.items():
            complete = all(r['available'] for r in rows)
            paired = complete and all(r['width_reduction'] is not None for r in rows)
            denominators = {r['original_n'] for r in rows if 'original_n' in r}
            if field == 'cohort_id' and len(denominators) > 1:
                raise ValueError(f'{label}: original_n differs between targets of one cohort')
            records.append({field: label, 'intended_targets': len(rows),
                            'available_targets': sum(r['available'] for r in rows),
                            'covered_targets': sum(r['covered'] for r in rows),
                            'complete': complete, 'success': complete and all(r['covered'] for r in rows),
                            'mean_width': mean(r['width'] for r in rows) if complete else None,
                            'mean_width_reduction': mean(r['width_reduction'] for r in rows) if paired else None,
                            'reason': '; '.join(sorted({r['reason'] for r in rows if r['reason']}))})
        return records

    cohort_records, unit_records = aggregate('cohort_id'), aggregate('unit_id')
    n = len(unit_records)
    success = sum(r['success'] for r in unit_records)
    complete = sum(r['complete'] for r in unit_records)
    widths = [r['mean_width'] for r in unit_records if r['mean_width'] is not None]
    gains = [r['mean_width_reduction'] for r in unit_records if r['mean_width_reduction'] is not None]
    lower_bound = float(beta.ppf(1-assurance, success, n-success+1)) if iid_units and success else (0. if iid_units else None)
    summary = {
        'intended_units': n, 'complete_units': complete, 'successful_units': success,
        'operational_success_fraction': success/n,
        'containment_among_complete_units': success/complete if complete else None,
        'one_sided_lower_bound': lower_bound,
        'lower_bound_reaches_target': lower_bound >= level if lower_bound is not None else None,
        'intended_cohorts': len(cohort_records),
        'complete_cohorts': sum(r['complete'] for r in cohort_records),
        'successful_cohorts': sum(r['success'] for r in cohort_records),
        'intended_targets': len(targets), 'available_targets': sum(r['available'] for r in targets),
        'covered_targets': sum(r['covered'] for r in targets),
        'mean_unit_width': mean(widths) if widths else None,
        'mean_unit_width_reduction': mean(gains) if gains else None,
        'units_with_paired_widths': len(gains),
        'zero_gain_targets': sum(r['width_reduction'] is not None and abs(r['width_reduction']) <= tolerance for r in targets),
    }
    return {'software_version': __version__, 'summary': summary, 'units': unit_records,
            'cohorts': cohort_records, 'targets': targets, 'assumptions': assumptions,
            'numeric_normalization': {'endpoint_limit':1e-12, 'corrections':corrections,
                                      'rule':'Clip tiny domain overflows and sort tiny reversed endpoints; '
                                             'truths are never normalized; larger errors are rejected'},
            'settings': {'level': level, 'assurance': assurance, 'tolerance': tolerance,
                         'endpoint_normalization_limit':1e-12,
                         'iid_units': iid_units, 'procedure_frozen': procedure_frozen},
            'planning': plan_calibration(level=level, assurance=assurance, test_units=n,
                                        calibration_units=manifest['exchangeable_units'] if manifest else 0),
            'interpretation': 'Operational success requires both availability and containment of every '
                              'planned target in a unit. The binomial lower bound, when requested, '
                              'concerns this event under the declared iid assumptions. A roster and '
                              'matching labels do not establish independence, prospective selection '
                              'or validity in another population. Widths include zero gains and are '
                              'averaged within complete units before averaging across units.'}


def _pct(value):
    return 'not available' if value is None else f'{100*value:.2f}%'


def _page(title, body):
    from .typography import html_with_typography
    return html_with_typography('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main>'
            f'<h1>{html.escape(title)}</h1><p class="subtitle">MIC-50-90 {__version__}</p>'
            + body + '</main></body></html>')


def _planning_html(result):
    rows = [
        ('Finite marginal conformal radius', result['minimum_calibration_units_marginal'], 'Calibration units',
         'Exchangeability; average over calibration and the future unit'),
        ('Coverage target reached with the requested assurance', result['minimum_calibration_units_pac'], 'Calibration units',
         'iid units; maximum-score PAC rule; separate from the ordinary manifest'),
        ('One-sided test bound reaches the target if every unit succeeds', result['minimum_test_units_all_success'], 'Held-out test units',
         'iid units; fixed procedure and sample size; optimistic zero-failure minimum'),
    ]
    content = '<p>Target coverage: '+_pct(result['level'])+'; assurance: '+_pct(result['assurance'])+'.</p>'
    content += '<div class="table-scroll"><table><tr><th>Question</th><th>Minimum</th><th>Denominator</th><th>Assumption</th></tr>'
    content += ''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</table></div>'
    content += ('<p>Supplied calibration units: '+str(result['calibration_units'])+
                '; supplied test units: '+str(result['test_units'])+'. Maximum supported marginal level: '+
                _pct(result['maximum_supported_marginal_level'])+'.</p>'
                '<p>Current finite marginal rank: '+str(result['marginal_rank'] or 'not available')+
                '; current PAC rank: '+str(result['pac_rank'] or 'not available')+'.</p>'
                '<p>If all supplied test units succeeded, the one-sided lower bound would be '+
                _pct(result['all_success_lower_bound'])+'.</p><p>'+html.escape(result['interpretation'])+'</p>')
    return content


def _audit_html(result):
    s, settings = result['summary'], result['settings']
    qualification = ('The lower bound assumes your declared iid units and frozen procedure; these declarations are not verified.'
                     if settings['iid_units'] else
                     'A binomial lower bound is unavailable because iid units were not declared; this assessment is descriptive.')
    style = 'card callout' if s['lower_bound_reaches_target'] is True else 'card callout warning'
    content = ('<section class="'+style+'"><h2>Does the fixed procedure cover every planned target?</h2><p><strong>'+
               str(s['successful_units'])+' / '+str(s['intended_units'])+' intended units succeeded ('+
               _pct(s['operational_success_fraction'])+').</strong> '+str(s['complete_units'])+
               ' units had every planned result available.</p><p>Target: '+_pct(settings['level'])+
               '; one-sided '+_pct(settings['assurance'])+' lower bound: '+_pct(s['one_sided_lower_bound'])+'.</p><p>'+
               qualification+'</p></section>')
    gain = ('not available' if s['mean_unit_width_reduction'] is None else
            f"{100*s['mean_unit_width_reduction']:.4f} percentage points")
    content += ('<p>Complete-unit containment: '+_pct(s['containment_among_complete_units'])+
                '. Secondary counts: '+str(s['successful_cohorts'])+' / '+str(s['intended_cohorts'])+
                ' cohorts and '+str(s['covered_targets'])+' / '+str(s['intended_targets'])+
                ' planned targets. These are not additional independent units.</p>'
                '<p>Mean interval width: '+_pct(s['mean_unit_width'])+'; mean paired width reduction: '+
                gain+' ('+str(s['units_with_paired_widths'])+
                ' complete units with baselines). Zero-gain targets: '+str(s['zero_gain_targets'])+'.</p>')
    content += ('<p>Endpoint normalization: '+str(len(result['numeric_normalization']['corrections']))+
                ' recorded corrections; limit 1e-12. Raw values and corrections are retained in audit.json and numeric-corrections.csv. '
                'This is separate from the containment comparison tolerance '+str(settings['tolerance'])+'.</p>')
    content += '<h2>Unit results</h2><div class="table-scroll"><table><tr><th>Unit</th><th>Available / planned</th><th>All targets contained</th><th>Reason</th></tr>'
    for row in result['units']:
        content += ('<tr><td>'+html.escape(row['unit_id'])+'</td><td>'+str(row['available_targets'])+' / '+
                    str(row['intended_targets'])+'</td><td>'+('yes' if row['success'] else 'no')+
                    '</td><td>'+html.escape(row['reason'] or ('A truth lies outside its interval' if not row['success'] else 'Complete and contained'))+'</td></tr>')
    content += '</table></div><h2>Assumptions and interpretation</h2><ul>'
    for key, value in result['assumptions'].items():
        if isinstance(value, dict):
            value = '; '.join(k.replace('_', ' ')+': '+str(v) for k, v in value.items())
        content += '<li>'+html.escape(key.replace('_', ' '))+': '+html.escape(str(value))+'</li>'
    content += '</ul><p>Numerical comparison tolerance: '+str(settings['tolerance'])+'</p><p>'+html.escape(result['interpretation'])+'</p>'
    content += '<h2>Planning the next evaluation</h2>'+_planning_html(result['planning'])
    return _page('Calibration assessment', content)


def _dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')


def _csv(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        # JSON retains exact identifiers; spreadsheet exports neutralise formulas.
        for row in rows:
            writer.writerow({key: "'"+v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v
                             for key, v in row.items()})


def run_calibration_plan(args):
    from .file_safety import check_output_paths
    output = Path(args.output_dir)
    check_output_paths([], [output / 'plan.json', output / 'report.html'])
    result = plan_calibration(level=args.level, assurance=args.assurance,
                              calibration_units=args.calibration_units, test_units=args.test_units)
    output.mkdir(parents=True, exist_ok=True)
    _dump(output/'plan.json', result)
    (output/'report.html').write_text(_page('Calibration and test planning', _planning_html(result)), encoding='utf-8')
    return 0


def run_calibration_audit(args):
    from .file_safety import check_output_paths
    output = Path(args.output_dir)
    check_output_paths(
        [args.input, args.roster, args.manifest, args.training_units],
        [output / name for name in ("audit.json", "configuration.json", "units.csv", "cohorts.csv",
         "targets.csv", "numeric-corrections.csv", "intended-roster.csv", "report.html")])
    from .workflows import read_csv
    delimiter = {'comma': ',', 'semicolon': ';', 'tab': '\t'}[args.delimiter]
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8')) if args.manifest else None
    training = json.loads(Path(args.training_units).read_text(encoding='utf-8')) if args.training_units else None
    result = audit_calibration(read_csv(args.roster, delimiter), read_csv(args.input, delimiter),
                               level=args.level, assurance=args.assurance, iid_units=args.iid_units,
                               procedure_frozen=args.procedure_frozen, manifest=manifest,
                               training_units=training, tolerance=args.tolerance)
    inputs = {name: {'path': str(Path(value).resolve()), 'sha256': sha256(Path(value).read_bytes()).hexdigest()}
              for name, value in [('observations', args.input), ('roster', args.roster),
                                  ('manifest', args.manifest), ('training_units', args.training_units)] if value}
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _dump(output/'audit.json', result)
    _dump(output/'configuration.json', {'software_version': __version__, 'inputs': inputs, 'settings': result['settings']})
    for name in ('units', 'cohorts', 'targets'):
        _csv(output/(name+'.csv'), result[name])
    _csv(output/'numeric-corrections.csv', result['numeric_normalization']['corrections'])
    _csv(output/'intended-roster.csv', read_csv(args.roster, delimiter))
    (output/'report.html').write_text(_audit_html(result), encoding='utf-8')
    return 0
