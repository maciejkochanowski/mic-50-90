"""Result format identity and explicit compatibility for retained evidence."""
from copy import deepcopy

DISTRIBUTION_SCHEMA = 'mic-50-90.distribution/1'


def validate_distribution_schema(result):
    # Unlabelled 1.0.0 analyses predate the explicit result-format identifier.
    if result.get('result_schema') not in (None, DISTRIBUTION_SCHEMA):
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
