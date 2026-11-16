"""Coverage evidence must expose its denominator and finite simulation uncertainty."""
from __future__ import annotations

import importlib
import json
import math
from pathlib import Path

import pytest


@pytest.fixture
def evaluation(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / 'evaluation'
    monkeypatch.syspath_prepend(str(folder))
    return folder


def reporting(evaluation):
    return importlib.import_module('coverage_reporting')


def test_actual_configuration_records_attempts_and_mc_uncertainty(evaluation, tmp_path):
    benchmark = importlib.import_module('benchmark')
    config = dict(config='tiny', n=2, k=2, low=0, high=0, report='R1', shares=[.5, .5])
    rows = benchmark.run_configurations([config], 2, tmp_path / 'blocks', 1, 15, 1, block=2)
    for method in ('bonferroni', 'range-calibrated'):
        result = rows[0][method]
        assert result['replicates_attempted'] == 2
        assert result['replicates_completed'] == 2
        assert result['replicates_failed'] == 0
        assert result['coverage_denominator'] == 'completed_replicates'
        assert result['monte_carlo_interval']['level'] == .95
        assert result['monte_carlo_interval']['denominator'] == 2
        assert result['coverage_assessment'] == 'no_undercoverage_detected'
        assert result['empirical_check_confirms_guarantee'] is False


@pytest.mark.parametrize('covered', [0, 2])
def test_exact_interval_has_uncertainty_at_extreme_results(evaluation, covered):
    result = reporting(evaluation).coverage_evidence(covered, 2)
    interval = result['monte_carlo_interval']
    if covered == 0:
        assert interval['lower'] == 0
        assert interval['upper'] == pytest.approx(1 - math.sqrt(.025))
    else:
        assert interval['lower'] == pytest.approx(math.sqrt(.025))
        assert interval['upper'] == 1
    assert interval['method'] == 'Clopper-Pearson'
    assert interval['unit'] == 'fraction'
    assert interval['lower'] < interval['upper']


def test_interior_interval_matches_binomial_closed_form(evaluation):
    result = reporting(evaluation).coverage_evidence(1, 2)
    interval = result['monte_carlo_interval']
    assert interval['lower'] == pytest.approx(1 - math.sqrt(.975))
    assert interval['upper'] == pytest.approx(math.sqrt(.975))
    assert result['monte_carlo_standard_error'] == pytest.approx(math.sqrt(.25 / 2))


def test_errors_remain_in_attempted_denominator_and_preclude_coverage_claim(evaluation):
    result = reporting(evaluation).coverage_evidence(8, 8, failed=2, expected=10)
    assert result['coverage'] == 1
    assert result['replicates_attempted'] == 10
    assert result['replicates_failed'] == 2
    assert result['coverage_over_attempted_replicates'] == .8
    assert result['monte_carlo_interval'] is None
    assert result['monte_carlo_standard_error'] is None
    assert result['coverage_assessment'] == 'execution_errors_present'
    assert result['empirical_check_confirms_guarantee'] is False


def test_all_failed_run_is_reported_without_division_by_zero(evaluation):
    result = reporting(evaluation).coverage_evidence(0, 0, failed=4, expected=4)
    assert result['coverage'] is None
    assert result['coverage_over_attempted_replicates'] == 0
    assert result['undercoverage_pvalue'] is None
    assert result['monte_carlo_interval'] is None
    assert result['coverage_assessment'] == 'execution_errors_present'
    json.dumps(result, allow_nan=False)


def test_no_replicates_cannot_supply_evidence_of_coverage(evaluation):
    result = reporting(evaluation).coverage_evidence(0, 0)
    assert result['coverage'] is None
    assert result['coverage_assessment'] == 'no_replicates'
    assert result['empirical_check_confirms_guarantee'] is False


def test_undercoverage_rule_retains_original_strict_test_boundary(evaluation):
    helper = reporting(evaluation).coverage_evidence
    boundary = helper(0, 2, nominal=.5, test_level=.25)
    above = helper(0, 2, nominal=.5, test_level=.25001)
    assert boundary['undercoverage_pvalue'] == .25
    assert boundary['undercoverage'] is False
    assert above['undercoverage'] is True
    assert boundary['undercoverage_rule'] == 'one_sided_exact_binomial_pvalue < test_level'


def test_nonrejection_is_not_a_confirmed_guarantee(evaluation):
    result = reporting(evaluation).coverage_evidence(940, 1000)
    assert result['coverage'] == .94
    assert result['undercoverage'] is False
    assert result['coverage_assessment'] == 'no_undercoverage_detected'
    assert result['empirical_check_confirms_guarantee'] is False


@pytest.mark.parametrize('args,kwargs', [
    ((True, 2), {}), ((1, 2.0), {}), ((-1, 2), {}), ((3, 2), {}),
    ((1, 2), {'failed': -1}), ((1, 2), {'expected': 3}),
    ((1, 2), {'nominal': float('nan')}), ((1, 2), {'nominal': 1}),
    ((1, 2), {'test_level': 0}), ((1, 2), {'mc_level': 1}),
])
def test_invalid_counts_or_probability_settings_are_rejected(evaluation, args, kwargs):
    with pytest.raises((TypeError, ValueError)):
        reporting(evaluation).coverage_evidence(*args, **kwargs)


def test_pooled_heterogeneous_configuration_summary_is_descriptive(evaluation):
    benchmark = importlib.import_module('benchmark')
    rows = []
    for covered, completed, errors in [(2, 2, []), (0, 0, [[0, 'failure'], [1, 'failure']])]:
        row = dict(replicates=completed, covered=covered, errors=errors,
                   coverage=covered / completed if completed else None, undercoverage=False)
        rows.append({method: dict(row) for method in ('bonferroni', 'range-calibrated')})
    for result in benchmark.coverage_totals(rows).values():
        assert result['replicates'] == 2
        assert result['replicates_attempted'] == 4
        assert result['errors'] == 2
        assert result['coverage'] == 1
        assert result['coverage_over_attempted_replicates'] == .5
        assert result['configurations_with_execution_errors'] == 1
        assert result['pooled_interval'] is None
        assert result['coverage_assessment'] == 'execution_errors_present'
        assert result['empirical_check_confirms_guarantee'] is False


def test_empty_configuration_collection_has_no_coverage_claim(evaluation):
    benchmark = importlib.import_module('benchmark')
    for result in benchmark.coverage_totals([]).values():
        assert result['coverage'] is None
        assert result['lowest_coverage'] is None
        assert result['coverage_assessment'] == 'no_configurations'
