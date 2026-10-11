"""Optional provenance and interpretation notes; never evidence for the solver."""
from copy import deepcopy
import json


SAMPLE_TEXT_FIELDS = ('host_species', 'specimen', 'grouping_notes', 'intended_population')
THRESHOLD_FIELDS = ('threshold_kind', 'threshold_source', 'threshold_version', 'threshold_applicability')
SAMPLING_GUIDANCE = (
    'Repeated isolates from the same animal or person may be related. Isolates from the same '
    'herd, farm or hospital may also share exposures. One isolate per host does not by itself '
    'establish independence. Independence is separate from representativeness: a convenience '
    'or referral sample need not represent the intended population. These notes do not '
    'confirm independent, identically distributed (iid) sampling or correct for clustering.'
)


def sample_context(value):
    """Read JSON metadata, including its lossless CSV representation."""
    if value in (None, ''):
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('Sample context must be an object with optional source notes.')
    if value.get('repeat_sampling', 'unknown') not in ('yes', 'no', 'unknown'):
        raise ValueError('Repeat sampling must be yes, no or unknown; it never selects population inference automatically.')
    for key in SAMPLE_TEXT_FIELDS:
        if key in value and not isinstance(value[key], str):
            raise ValueError(f'{key} must be text copied from the source or a stated user assumption.')
    return deepcopy(value)


def threshold_note(row):
    """Explain a declared threshold without assigning a clinical classification."""
    kind = row.get('threshold_kind') or 'custom'
    if kind not in ('custom', 'ecoff', 'clinical'):
        raise ValueError('Threshold kind must be custom, ecoff or clinical.')
    for key in THRESHOLD_FIELDS[1:]:
        if key in row and not isinstance(row[key], str):
            raise ValueError(f'{key} must be text.')
    meaning = ('Results retain uncertainty about MIC within the measurement intervals.'
               if row.get('target_scale') == 'interval'
               else 'Results describe recorded MIC above the stated concentration.')
    if kind == 'custom':
        return 'Custom threshold. ' + meaning
    missing = [key for key in THRESHOLD_FIELDS[1:] if not str(row.get(key, '')).strip()]
    label = 'ECOFF' if kind == 'ecoff' else 'Clinical breakpoint'
    if missing:
        return (f'{label} declared, but '+', '.join(missing)+
                ' not supplied. Use neutral MIC wording; descriptive analysis remains available.')
    return (f'{label} context supplied by the user; applicability has not been independently verified. '
            + meaning + ' '
            + ('An ECOFF concerns wild-type distributions and is not a clinical susceptibility classification.'
               if kind == 'ecoff' else 'A clinical resistance classification requires the applicable organism, host, infection site, method and breakpoint rule.'))


def add_context(provenance, raw, targets):
    """Preserve optional notes beside results, without modifying analysis inputs."""
    if raw.get('sample_context') not in (None, ''):
        provenance['sample_context'] = sample_context(raw['sample_context'])
    if raw.get('iid') is True:
        provenance['iid_declared'] = True
    if targets:
        provenance['threshold_context'] = [
            {key: deepcopy(row[key]) for key in ('threshold', 'unit', 'target_scale', *THRESHOLD_FIELDS) if key in row}
            for row in targets if isinstance(row, dict) and 'threshold' in row]
    return provenance
