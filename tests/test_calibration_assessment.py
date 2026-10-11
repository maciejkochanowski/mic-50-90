"""Prospective denominators and independent unit-level calibration assessment."""
import copy
import json

import pytest
from scipy.optimize import brentq
from scipy.stats import binom

from mic_50_90.calibration_audit import audit_calibration, plan_calibration
from mic_50_90.cli import main
from mic_50_90.conformal import calibrate_wasserstein_manifest


def roster_and_rows():
    roster = [dict(unit_id='A', cohort_id='a', target_id=str(i)) for i in range(20)]
    roster += [dict(unit_id='B', cohort_id='b', target_id='0')]
    rows = [dict(r, status='ok', truth=.2, lower=.1, upper=.3,
                 baseline_lower=0., baseline_upper=.5) for r in roster]
    rows[-1]['truth'] = .4
    return roster, rows


def manifest(kind='simultaneous_tail_intervals'):
    return calibrate_wasserstein_manifest(
        group_scores=[.1] * 9, group_units=[f'cal-{i}' for i in range(9)], alpha=.1,
        grouping={'population': 'example'}, source='frozen example', data_hashes={'roster': 'abc'},
        calibrate_on='units',
        calibration_contract={
            'score_kind': kind, 'reference_rule': 'projected',
            'functional_scope': 'all_panel_tails', 'transport_unit': 'log2_mg_L',
            'summary_policy': 'ceiling_50_90_no_range', 'reference_protocol': 'fixed training',
            'unit_definition': 'one independent site with all planned targets'}).as_dict()


@pytest.mark.parametrize('level,marginal,conditional', [(.9,9,29),(.95,19,59),(.99,99,299)])
def test_planner_distinguishes_three_requirements(level, marginal, conditional):
    result = plan_calibration(level=level, calibration_units=marginal, test_units=conditional)
    assert result['minimum_calibration_units_marginal'] == marginal
    assert result['minimum_calibration_units_pac'] == conditional
    assert result['minimum_test_units_all_success'] == conditional
    assert result['marginal_rank'] == marginal
    assert result['pac_rank'] is None
    assert result['all_success_lower_bound'] >= level
    before = plan_calibration(level=level, test_units=conditional-1)
    assert before['all_success_lower_bound'] < level


def test_planning_current_nine_units_does_not_certify_95_percent():
    result = plan_calibration(level=.95, calibration_units=9, test_units=6)
    assert result['marginal_rank'] is None
    assert result['maximum_supported_marginal_level'] == .9
    assert result['pac_assurance_at_maximum_score'] == pytest.approx(1-.95**9)
    assert plan_calibration(level=.95, calibration_units=59)['pac_rank'] == 59


@pytest.mark.parametrize('kwargs', [{'level':1}, {'assurance':0}, {'level':float('nan')},
                                   {'calibration_units':2.5}, {'test_units':True}])
def test_planner_rejects_invalid_requests(kwargs):
    with pytest.raises(ValueError):
        plan_calibration(**kwargs)


def test_many_easy_targets_do_not_inflate_independent_successes():
    roster, rows = roster_and_rows()
    result = audit_calibration(roster, rows)
    assert result['summary']['intended_units'] == 2
    assert result['summary']['successful_units'] == 1
    assert result['summary']['covered_targets'] == 20
    assert result['summary']['operational_success_fraction'] == .5
    assert result['summary']['one_sided_lower_bound'] is None
    assert result['summary']['mean_unit_width_reduction'] == pytest.approx(.3)


def test_missing_target_stays_in_frozen_denominator():
    roster, rows = roster_and_rows()
    result = audit_calibration(roster, rows[1:])
    assert result['summary']['intended_targets'] == 21
    assert result['summary']['available_targets'] == 20
    assert result['summary']['complete_units'] == 1
    assert result['summary']['successful_units'] == 0
    assert result['targets'][0]['reason'] == 'Missing planned observation'


def test_refusal_is_visible_and_not_counted_as_success():
    roster, rows = roster_and_rows()
    rows[-1] = dict(roster[-1], status='unavailable', reason='Reference absent')
    result = audit_calibration(roster, rows)
    assert result['summary']['successful_units'] == 1
    assert result['summary']['complete_units'] == 1
    assert result['summary']['operational_success_fraction'] == .5


def test_unavailable_row_requires_a_real_explanation():
    roster, rows = roster_and_rows()
    rows[-1] = dict(roster[-1], status='unavailable', reason=None)
    with pytest.raises(ValueError, match='reason'):
        audit_calibration(roster, rows)


@pytest.mark.parametrize('case', ['duplicate', 'foreign', 'cohort_split', 'nan', 'reversed',
                                 'missing_truth', 'bad_baseline', 'not_nested', 'unknown_status'])
def test_inconsistent_observations_cannot_produce_a_favourable_report(case):
    roster, rows = roster_and_rows()
    if case == 'duplicate': rows.append(copy.deepcopy(rows[0]))
    if case == 'foreign': rows.append(dict(rows[0], target_id='absent'))
    if case == 'cohort_split': roster.append(dict(unit_id='C', cohort_id='a', target_id='x'))
    if case == 'nan': rows[0]['upper'] = float('nan')
    if case == 'reversed': rows[0]['lower'] = .4
    if case == 'missing_truth': rows[0].pop('truth')
    if case == 'bad_baseline': rows[0]['baseline_lower'] = .25
    if case == 'not_nested': rows[0]['lower'] = -.01
    if case == 'unknown_status': rows[0]['status'] = 'passed'
    with pytest.raises(ValueError):
        audit_calibration(roster, rows)


def test_confidence_bound_matches_independent_binomial_inversion():
    roster = [dict(unit_id=str(i), cohort_id=str(i), target_id='x') for i in range(10)]
    rows = [dict(r, status='ok', truth=.2, lower=.1, upper=.3) for r in roster]
    rows[-1]['truth'] = .4
    result = audit_calibration(roster, rows, iid_units=True, procedure_frozen=True)
    independent = brentq(lambda p: binom.sf(8, 10, p)-.05, 1e-10, 1-1e-10)
    assert result['summary']['one_sided_lower_bound'] == pytest.approx(independent)
    assert 'declared, not verified' in result['assumptions']['iid_units']


def test_iid_precision_requires_a_fixed_procedure_declaration():
    roster, rows = roster_and_rows()
    with pytest.raises(ValueError, match='frozen'):
        audit_calibration(roster, rows, iid_units=True)


def test_overlap_and_manifest_event_are_checked():
    roster, rows = roster_and_rows()
    result = audit_calibration(roster, rows, manifest=manifest())
    assert result['settings']['level'] == .9
    assert result['assumptions']['training_disjointness'] == 'not checked: no training roster supplied'
    with pytest.raises(ValueError, match='training'):
        audit_calibration(roster, rows, training_units=['A'])
    with pytest.raises(ValueError, match='calibration'):
        audit_calibration([dict(unit_id='cal-0', cohort_id='x', target_id='0')], [], manifest=manifest())
    with pytest.raises(ValueError, match='level'):
        audit_calibration(roster, rows, manifest=manifest(), level=.95)
    with pytest.raises(ValueError, match='distribution-distance'):
        audit_calibration(roster, rows, manifest=manifest('distribution_distance'))
    with pytest.raises(ValueError, match='training'):
        audit_calibration(roster, rows, manifest=manifest(), training_units=['cal-0'])


@pytest.mark.parametrize('successes,expected', [(0,0.), (10,.05**.1)])
def test_binomial_extremes_use_unit_denominators(successes, expected):
    roster = [dict(unit_id=str(i), cohort_id=str(i), target_id='x') for i in range(10)]
    rows = [dict(r, status='ok', truth=.2 if i < successes else .4, lower=.1, upper=.3)
            for i, r in enumerate(roster)]
    result = audit_calibration(roster, rows, iid_units=True, procedure_frozen=True)
    assert result['summary']['one_sided_lower_bound'] == pytest.approx(expected)


def test_exact_original_denominator_cannot_be_changed():
    roster, rows = roster_and_rows()
    rows[0].update(truth_count=1, original_n=5)
    assert audit_calibration(roster, rows)['targets'][0]['original_n'] == 5
    rows[0]['truth_count'] = 1.2
    with pytest.raises(ValueError, match='integer'):
        audit_calibration(roster, rows)
    rows[0]['truth_count'] = 2
    with pytest.raises(ValueError, match='count/original_n'):
        audit_calibration(roster, rows)


def test_baseline_nesting_and_paired_fields():
    roster, rows = roster_and_rows()
    rows[0].update(lower=.1, upper=.6)
    with pytest.raises(ValueError, match='nested'):
        audit_calibration(roster, rows)
    rows[0]['upper'] = .3
    rows[0].pop('baseline_lower')
    with pytest.raises(ValueError, match='both baseline'):
        audit_calibration(roster, rows)


def test_exact_boundary_and_explicit_tolerance():
    roster = [dict(unit_id='A', cohort_id='a', target_id='0')]
    rows = [dict(roster[0], status='ok', truth=.3+1e-10, lower=.1, upper=.3)]
    assert audit_calibration(roster, rows)['summary']['successful_units'] == 0
    result = audit_calibration(roster, rows, tolerance=1e-9)
    assert result['summary']['successful_units'] == 1
    assert result['settings']['tolerance'] == 1e-9


def test_cli_plan_and_audit_are_portable_and_escape_labels(tmp_path):
    roster = tmp_path/'expected.csv'
    roster.write_text('unit_id;cohort_id;target_id\n<script>;a;t\n', encoding='utf-8-sig')
    rows = tmp_path/'observed.csv'
    rows.write_text('unit_id;cohort_id;target_id;status;truth;lower;upper\n<script>;a;t;ok;0.2;0;0.3\n')
    output = tmp_path/'audit'
    assert main(['calibration-audit', str(rows), '--roster', str(roster), '--output-dir', str(output),
                 '--delimiter', 'semicolon']) == 0
    result = json.loads((output/'audit.json').read_text())
    assert result['summary']['successful_units'] == 1
    report = (output/'report.html').read_text()
    assert '&lt;script&gt;' in report and '<script>' not in report
    assert result['summary']['intended_targets'] == 1
    assert main(['calibration-plan', '--level', '.95', '--output-dir', str(tmp_path/'plan')]) == 0
    plan = json.loads((tmp_path/'plan'/'plan.json').read_text())
    assert plan['minimum_test_units_all_success'] == 59
