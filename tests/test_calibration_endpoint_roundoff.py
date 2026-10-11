"""Audit public solver outputs without silently discarding numerical evidence."""
import json

import pytest

from mic_50_90.calibration_audit import audit_calibration
from mic_50_90.cli import main


def inputs(**kwargs):
    key = dict(unit_id='site', cohort_id='drug', target_id='cut')
    return [key], [dict(key, status='ok', truth=1/3, lower=.2, upper=.5, **kwargs)]


def test_probability_boundary_normalization_is_logged_and_truth_is_strict():
    roster, rows = inputs()
    rows[0].update(lower=-1e-16, upper=1+2e-16)
    result = audit_calibration(roster, rows)
    assert result['summary']['successful_units'] == 1
    assert result['targets'][0]['lower'] == 0 and result['targets'][0]['upper'] == 1
    corrections = result['numeric_normalization']['corrections']
    assert len(corrections) == 2
    assert {r['field'] for r in corrections} == {'lower','upper'}
    assert corrections[0]['original'] == -1e-16
    rows[0]['truth'] = 1+2e-16
    with pytest.raises(ValueError, match='truth'):
        audit_calibration(roster, rows)


def test_tiny_reversed_interval_is_sorted_without_using_truth():
    roster, rows = inputs()
    rows[0].update(lower=.33333333333333337, upper=1/3)
    result = audit_calibration(roster, rows)
    assert result['targets'][0]['lower'] == 1/3
    assert result['targets'][0]['upper'] == .33333333333333337
    assert result['summary']['successful_units'] == 1
    assert result['numeric_normalization']['corrections'][0]['kind'] == 'tiny_reversal'
    rows[0]['truth'] = .4
    miss = audit_calibration(roster, rows)
    assert miss['summary']['successful_units'] == 0
    assert miss['targets'][0]['lower'] == result['targets'][0]['lower']
    assert miss['targets'][0]['upper'] == result['targets'][0]['upper']


@pytest.mark.parametrize('changes', [{'upper':1.0001}, {'lower':-.0001},
                                    {'lower':.5,'upper':.49}])
def test_large_endpoint_errors_are_not_normalized(changes):
    roster, rows = inputs()
    rows[0].update(changes)
    with pytest.raises(ValueError):
        audit_calibration(roster, rows)


def test_valid_interval_is_unchanged_and_normalization_is_not_containment_tolerance():
    roster, rows = inputs()
    rows[0].update(truth=.50000000000001)
    result = audit_calibration(roster, rows)
    assert result['numeric_normalization']['corrections'] == []
    assert result['targets'][0]['upper'] == .5
    assert result['summary']['successful_units'] == 0
    assert result['settings']['tolerance'] == 0


def test_public_csv_audit_writes_corrections_and_visible_qualification(tmp_path):
    roster = tmp_path/'roster.csv'
    observations = tmp_path/'observed.csv'
    roster.write_text('unit_id,cohort_id,target_id\nA,a,t\n')
    observations.write_text('unit_id,cohort_id,target_id,status,truth,lower,upper,baseline_lower,baseline_upper\n'
                            'A,a,t,ok,0.2,0,0.5,0,1.0000000000000002\n')
    output = tmp_path/'audit'
    assert main(['calibration-audit',str(observations),'--roster',str(roster),
                 '--output-dir',str(output)]) == 0
    result = json.loads((output/'audit.json').read_text())
    assert len(result['numeric_normalization']['corrections']) == 1
    assert (output/'numeric-corrections.csv').is_file()
    report = (output/'report.html').read_text()
    opening = report.split('</section>',1)[0]
    assert 'iid units were not declared' in opening
    assert 'card callout warning' in opening
    assert '50.0000 percentage points' in report
    assert 'Endpoint normalization' in report
