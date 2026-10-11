import csv

import pytest

from mic_50_90 import analyse_with_counts
from test_count_updates import sample_counts, specification
from test_decision_workflow import _inputs, _run, _write


def test_later_exact_answer_refines_previous_range_without_removing_it():
    rows = [dict(threshold=1, unit='mg/L', n=6, count_min=1, count_max=2),
            dict(threshold=1, unit='mg/L', n=6, count=2)]
    result = analyse_with_counts(specification(), rows)
    assert sample_counts(result) == [(2,2),(1,2)]
    assert len(result['additional_information']['observations']) == 2
    with pytest.raises(ValueError):
        analyse_with_counts(specification(), [rows[0], {**rows[1], 'count': 3}])


def test_interval_template_can_be_completed_without_losing_previous_answer(tmp_path):
    _inputs(tmp_path)
    answer = dict(cohort_id='C', threshold=4, unit='mg/L', n=10, count_min=0, count_max=1)
    _write(tmp_path/'answers.csv', list(answer), [answer])
    records = _run(tmp_path, '--acquisition-plan', '--additional-counts', str(tmp_path/'answers.csv'))
    assert records[0]['status'] == 'ok'
    report = (tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert '0 to 1 / 10' in report
    with (tmp_path/'out/requested_counts.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2
    prior = next(r for r in rows if r['count_min'])
    assert prior['count_min'] == '0' and prior['count_max'] == '1'
    request = next(r for r in rows if not r['count_min'])
    assert request['threshold'] == '4.0'
    request['count'] = '0'
    _write(tmp_path/'completed.csv', list(rows[0]), rows)
    updated = _run(tmp_path, '--acquisition-plan', '--additional-counts', str(tmp_path/'completed.csv'))
    assert updated[0]['status'] == 'ok'
    assert updated[0]['result']['decision_results'][1]['sample']['status'] == 'supported'


def test_percentage_report_explains_denominator_and_rounding(tmp_path):
    _inputs(tmp_path)
    answer = dict(cohort_id='C', threshold=4, unit='mg/L', n=10, percentage='0',
                  decimal_places=0, rounding_rule='half_up')
    _write(tmp_path/'answers.csv', list(answer), [answer])
    result = _run(tmp_path, '--acquisition-plan', '--additional-counts', str(tmp_path/'answers.csv'))[0]
    assert result['status'] == 'ok'
    report = (tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert '0%' in report and 'half_up' in report and '0 to 0 / 10' in report
    with (tmp_path/'out/requested_counts.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    prior = next(r for r in rows if r['percentage'])
    assert prior['count_min'] == '' and prior['rounding_rule'] == 'half_up'
