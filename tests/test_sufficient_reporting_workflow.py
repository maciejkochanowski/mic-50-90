import csv
import json
import pytest
from test_decision_workflow import _inputs, _write, _run
from mic_50_90 import verify_reporting


def prepare(path):
    _inputs(path)
    rows=[dict(cohort_id='C',panel_id='P',category=str(t),count=c,rank_convention='ceiling')
          for t,c in zip((1,2,4,8,16),(5,4,1,0,0))]
    _write(path/'counts.csv',list(rows[0]),rows)


def test_report_is_readable_and_export_can_be_checked_without_histogram(tmp_path):
    prepare(tmp_path)
    records=_run(tmp_path,'--reporting-plan',command='reporting-audit',filename='counts.csv')
    assert records[0]['result']['reporting_plan']['report_cost']==2
    html=(tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert 'Counts to include in your report' in html
    assert 'after inspecting the complete histogram' in html
    assert 'Cheapest sufficient report' in html
    with (tmp_path/'out/reporting_counts.csv').open() as f:
        counts=list(csv.DictReader(f))
    assert len(counts)==2 and all(r['n']=='10' for r in counts)
    certificate=json.loads((tmp_path/'out/reporting_certificates.json').read_text())['certificates'][0]
    assert 'histogram' not in certificate
    checked=verify_reporting(certificate['specification'],certificate['criteria'],certificate['disclosures'])
    assert checked['sufficient']
    replay=_run(tmp_path,'--additional-counts',str(tmp_path/'out/reporting_counts.csv'))
    assert [r['sample']['status'] for r in replay[0]['result']['decision_results']]==['contradicted','supported','supported']


def test_rational_criterion_exports_a_complete_readable_report(tmp_path):
    prepare(tmp_path)
    _inputs(tmp_path, fraction='1/20')
    record = _run(tmp_path, '--reporting-plan', command='reporting-audit', filename='counts.csv')[0]
    assert record['result']['reporting_plan']['sufficient']
    html = (tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert 'Cheapest sufficient report' in html
    assert '&lt; 5%' in html
    certificate = json.loads((tmp_path/'out/reporting_certificates.json').read_text())['certificates'][0]
    assert verify_reporting(certificate['specification'], certificate['criteria'], certificate['disclosures'])['sufficient']


@pytest.mark.parametrize('extra', [['--decision-plan-time-limit','0'],['--decision-plan-time-limit','bad']])
def test_optional_failure_or_limit_keeps_sample_results(tmp_path,extra):
    prepare(tmp_path)
    record=_run(tmp_path,'--reporting-plan',*extra,command='reporting-audit',filename='counts.csv')[0]
    assert record['status']=='ok'
    assert record['result']['reporting_uncertainty_envelope']['envelope']
    html=(tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert 'Cheapest sufficient report' not in html


def test_unsafe_identifier_is_not_written_as_executable_spreadsheet_content(tmp_path):
    prepare(tmp_path)
    for name in ['counts.csv','targets.csv']:
        p=tmp_path/name;p.write_text(p.read_text().replace('C,','=1+1,'))
    record=_run(tmp_path,'--reporting-plan',command='reporting-audit',filename='counts.csv')[0]
    assert record['status']=='ok'
    assert record['result']['reporting_plan']['status']=='unavailable'
    with (tmp_path/'out/reporting_counts.csv').open() as f:assert not list(csv.DictReader(f))
