"""Result format identity and explicit compatibility for saved results."""
from copy import deepcopy

from . import _version

DISTRIBUTION_SCHEMA = 'mic-50-90.distribution/1'


def validate_distribution_schema(result):
    """Accept explicitly compatible patch versions; refuse unknown producers.

    Results written by 1.0.0 may lack the schema field; later results must name it.
    """
    if not isinstance(result, dict) or result.get('software') != 'MIC-50-90':
        raise ValueError('Previous output must be a MIC-50-90 distribution analysis')
    version = result.get('software_version')
    schema = result.get('result_schema')
    if version not in _version.COMPATIBLE_REPORT_VERSIONS:
        raise ValueError('Unsupported distribution producer version; use a known compatible result')
    if schema is None:
        if version != '1.0.0':
            raise ValueError('Only results written by version 1.0.0 may omit the distribution result schema')
    elif schema != DISTRIBUTION_SCHEMA:
        raise ValueError('Unsupported distribution result schema; use matching results and configuration')


def normalize_reporting_verification(result):
    """Compare old contiguous bounds with explicitly represented components.

    Only this known format addition is filled. A gap, changed endpoint,
    decision or other field remains a scientific difference, not a migration.
    """
    normalized = deepcopy(result)
    for row in normalized['bounds']:
        row.setdefault('count_components', [[row['count_min'], row['count_max']]])
    return normalized
