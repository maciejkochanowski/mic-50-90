"""A reported bound must not become a measurement.

These tests used to import from scripts/run_external_validation.py, which put a campaign
script on the import path of the library's own suite. The rule they check is the library's.
"""

from __future__ import annotations

from mic_50_90.censoring import censoring_record, parse_numeric_mic


def test_mic_parser_preserves_operator_instead_of_coercing_to_exact():
    assert parse_numeric_mic("<=0.25") == (0.25, "<=")
    assert parse_numeric_mic("0.5", ">") == (0.5, ">")
    assert parse_numeric_mic("1", "==") == (1.0, None)
    assert parse_numeric_mic("<=1", ">=") is None


def test_censoring_record_exposes_the_latent_interval_and_exclusion_policy():
    left = censoring_record("<=0.25", 7)
    assert left == {
        "label": "<=0.25",
        "operator": "<=",
        "value": 0.25,
        "lower_bound": None,
        "upper_bound": 0.25,
        "lower_closed": False,
        "upper_closed": True,
        "count": 7,
        "analysis_status": "excluded_from_exact_value_analysis",
    }
    right = censoring_record(">2", 3)
    assert right["lower_bound"] == 2.0
    assert right["upper_bound"] is None
    assert right["lower_closed"] is False
