import csv
import json
import pytest
from test_decision_workflow import _inputs, _run, _write


def test_batch_request_template_and_plain_report(tmp_path):
    _inputs(tmp_path)
    result = _run(tmp_path,'--acquisition-plan','--round-cost','2')[0]['result']
    assert result['acquisition_plan']['worst_case_cost'] == 5
    assert result['acquisition_plan']['sequential_comparison']['worst_case_cost'] == 6
    with (tmp_path/'out/requested_counts.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3 and all(r['count'] == '' for r in rows)
    assert all(r['n'] == '10' for r in rows)
    report = (tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert 'existing laboratory records' in report
    assert 'not new susceptibility tests' in report
    assert 'Request together' in report
    assert 'Remaining work' in report
    configuration = json.loads((tmp_path/'out/configuration.json').read_text())
    assert configuration['decision_planning']['round_cost'] == '2'


def test_zero_cost_csv_allowed_only_in_acquisition_mode(tmp_path):
    _inputs(tmp_path)
    _write(tmp_path/'queries.csv',['cohort_id','threshold','unit','cost'],
           [dict(cohort_id='C',threshold=t,unit='mg/L',cost=0) for t in (2,4,8)])
    result = _run(tmp_path,'--acquisition-plan','--round-cost','1',
                  '--decision-queries',str(tmp_path/'queries.csv'))[0]['result']
    assert result['acquisition_plan']['worst_case_cost'] == 1


def test_bad_round_cost_preserves_basic_results(tmp_path):
    _inputs(tmp_path)
    result = _run(tmp_path,'--acquisition-plan','--round-cost','bad')[0]['result']
    assert result['acquisition_plan']['status'] == 'unavailable'
    assert result['reporting_uncertainty_envelope']['envelope']


def test_request_template_retains_previous_answers(tmp_path):
    _inputs(tmp_path)
    _write(tmp_path/'answers.csv',['cohort_id','threshold','unit','count','n'],
           [dict(cohort_id='C',threshold=4,unit='mg/L',count=0,n=10)])
    _run(tmp_path,'--acquisition-plan','--additional-counts',str(tmp_path/'answers.csv'))
    with (tmp_path/'out/requested_counts.csv').open() as stream:
        rows=list(csv.DictReader(stream))
    assert any(r['threshold']=='4.0' and r['count']=='0' for r in rows)
    assert sum(r['count']=='' for r in rows)==1


@pytest.mark.parametrize('name,delimiter',[('semicolon',';'),('tab','\t')])
def test_template_roundtrip_uses_selected_delimiter(tmp_path,name,delimiter):
    _inputs(tmp_path)
    for filename in ['summaries.csv','panels.csv','targets.csv']:
        p=tmp_path/filename
        with p.open(newline='') as f:rows=list(csv.reader(f))
        with p.open('w',newline='') as f:csv.writer(f,delimiter=delimiter).writerows(rows)
    _run(tmp_path,'--acquisition-plan','--round-cost','2','--delimiter',name)
    with (tmp_path/'out/requested_counts.csv').open(newline='') as f:
        rows=list(csv.DictReader(f,delimiter=delimiter))
    assert len(rows)==3 and 'count' in rows[0]
    for row in rows:row['count']='1' if float(row['threshold'])==2 else '0'
    with (tmp_path/'completed.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=delimiter);w.writeheader();w.writerows(rows)
    result=_run(tmp_path,'--acquisition-plan','--delimiter',name,'--additional-counts',str(tmp_path/'completed.csv'))[0]['result']
    assert result['acquisition_plan']['status']=='already_resolved'


def test_formula_identifier_preserves_analysis_without_unsafe_template(tmp_path):
    _inputs(tmp_path)
    for filename in ['summaries.csv','targets.csv']:
        p=tmp_path/filename
        p.write_text(p.read_text().replace('C,','=1+1,'))
    result=_run(tmp_path,'--acquisition-plan')[0]['result']
    assert result['reporting_uncertainty_envelope']['envelope']
    assert result['acquisition_plan']['status']=='unavailable'
    assert 'identifier' in result['acquisition_plan']['reason'].lower()
    with (tmp_path/'out/requested_counts.csv').open() as f:assert len(list(csv.DictReader(f)))==0


def test_report_does_not_present_unverified_cost_as_bound(tmp_path):
    from mic_50_90 import plan_acquisition
    from mic_50_90.decision_report import render_acquisition_plan
    from test_decision_planning import specification,criteria
    result=plan_acquisition(specification(),criteria(),queries=[],time_limit_seconds=0)
    html=render_acquisition_plan(result)
    assert 'No sufficient request has been verified' in html
    assert 'at most not available' not in html
