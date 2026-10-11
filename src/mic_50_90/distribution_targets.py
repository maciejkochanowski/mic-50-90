"""The category event shared by distribution questions and their displays."""
from math import isfinite

from .count_updates import observation_coefficients
from .decisions import parse_criterion
from .workflows import _unit


def normalize_target(row, panel):
    """Validate one threshold or inclusive category range without running a solver."""
    if not isinstance(row, dict):
        raise ValueError('Each question must be an object with a threshold or category range')
    _unit(row.get('unit'))
    scale = row.get('target_scale', 'recorded') or 'recorded'
    if scale not in ('recorded', 'interval'):
        raise ValueError('target_scale must be recorded or interval')
    has_threshold = row.get('threshold') not in (None, '')
    has_range = any(row.get(key) not in (None, '') for key in ('start_category', 'end_category'))
    if has_threshold == has_range:
        raise ValueError('Supply either threshold or both start_category and end_category, not both')
    if has_range:
        if any(row.get(key) in (None, '') or isinstance(row.get(key), bool)
               for key in ('start_category', 'end_category')):
            raise ValueError('start_category and end_category must name whole panel categories')
        a, end = panel.index(row['start_category']), panel.index(row['end_category'])
        if a > end:
            raise ValueError('start_category must not follow end_category')
        meta = dict(question_type='category_range', start_category=panel.labels[a],
                    end_category=panel.labels[end], start_index=a, stop_index=end+1, unit='mg/L')
    else:
        try:
            threshold = float(row['threshold'])
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError('Target thresholds must be positive and finite') from exc
        if isinstance(row['threshold'], bool) or not isfinite(threshold) or threshold <= 0:
            raise ValueError('Target thresholds must be positive and finite')
        objective = panel.panel_tail(threshold)
        meta = dict(question_type='threshold', threshold=threshold,
                    start_index=sum(int(x == 0) for x in objective), stop_index=len(panel.bins), unit='mg/L')
    meta['target_scale'] = scale
    meta['measurement_ambiguous_categories'] = []
    objective = observation_coefficients(meta, panel)
    if scale == 'interval' and not has_range:
        objective = panel.latent_tail(threshold, upper=False)
        possible = panel.latent_tail(threshold, upper=True)
        meta['start_index'] = sum(int(x == 0) for x in objective)
        meta['possible_start_index'] = sum(int(x == 0) for x in possible)
        meta['measurement_ambiguous_categories'] = [
            b.label for b in panel.bins if b.latent_status(threshold) == 'ambiguous']
    return meta, objective, parse_criterion(row)


def possible_objective(meta, panel):
    """Categories which can contribute, without placing MIC at a coded value."""
    if meta.get('target_scale') == 'interval' and meta['question_type'] == 'threshold':
        return panel.latent_tail(meta['threshold'], upper=True)
    return observation_coefficients(meta, panel)


def target_key(meta):
    event = (('threshold', meta['threshold']) if meta['question_type'] == 'threshold'
             else ('category_range', meta['start_index'], meta['stop_index']))
    return (meta.get('target_scale', 'recorded'), *event)


def read_targets(targets, panel):
    if not isinstance(targets, list):
        raise ValueError('targets must be a list')
    parsed, seen = [], set()
    for target in targets:
        item = normalize_target(target, panel)
        key = target_key(item[0])
        if key in seen:
            raise ValueError('Target thresholds and category ranges must be distinct')
        seen.add(key)
        parsed.append(item)
    return parsed


def event_text(row):
    """Describe the recorded-category event, never infer clinical susceptibility."""
    if 'start_category' not in row:
        name = 'MIC within the measurement intervals' if row.get('target_scale') == 'interval' else 'recorded MIC'
        return f"{name} above {row['threshold']:g} mg/L"
    start, end = row['start_category'], row['end_category']
    if start == end:
        return f'recorded MIC category {start} mg/L'
    return f'recorded MIC categories {start} through {end} mg/L (both included)'
