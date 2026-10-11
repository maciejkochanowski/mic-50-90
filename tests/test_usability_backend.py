from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.count_updates import _observations
from mic_50_90.model import MICPanel
from types import SimpleNamespace
import pytest


def test_counts_only_strict_five_percent():
    raw = dict(n=20,unit='mg/L',panel={'levels':[1,2]},additional_counts=[dict(threshold=2,count=1,n=20,unit='mg/L')],targets=[dict(threshold=2,unit='mg/L',decision_operator='<',decision_fraction='0.05')])
    r = analyse_distribution(raw)
    assert r['decisions'][0]['sample']['status'] == 'contradicted'
    assert r['decisions'][0]['sample']['count_components'] == [[1,1]]


def test_source_relation_safe_and_ambiguous():
    spec=SimpleNamespace(n=20,panel=MICPanel.from_dict({'levels':[1,2]}))
    spec.panel = MICPanel.from_dict({'categories':[{'label':'<2','lower_bound':None,'upper_bound':2,'upper_closed':False,'panel_value':1},{'label':'>=2','lower_bound':2,'upper_bound':None,'lower_closed':True,'panel_value':2}]})
    row=dict(threshold=2,count=5,n=20,unit='mg/L',relation='>=')
    normalized=_observations([row],spec)[0]
    assert normalized['threshold']==1
    assert normalized['count']==5
    assert normalized['source_relation']=='>='
    with pytest.raises(ValueError,match='categor'):
        _observations([{**row,'threshold':1,'relation':'<'}],spec)


def test_complement_percentage_preimage():
    spec=SimpleNamespace(n=7133,panel=MICPanel.from_dict({'levels':[1,2]}))
    row=dict(threshold=2,percentage='2',decimal_places=0,rounding_rule='half_up',n=7133,unit='mg/L',relation='<=')
    from mic_50_90.count_updates import counts_from_percentage
    lo,hi=counts_from_percentage('2',n=7133,decimal_places=0,rounding_rule='half_up')
    r=_observations([row],spec)[0]
    assert (r['count_min'],r['count_max'])==(7133-hi,7133-lo)


def test_table_preview_and_certificate_job(tmp_path):
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    table={'mode':'distribution','input_format':'tables','tables':{'input':{'text':'cohort_id,panel_id,n,variant_id\na,p,1,primary\n','delimiter':'comma'},'panels':{'text':'panel_id,unit,category,panel_value,lower,upper,lower_closed,upper_closed\np,mg/L,<=1,1,,1,false,true\np,mg/L,>1,2,1,,false,false\n','delimiter':'comma'},'additional_counts':{'text':'cohort_id,threshold,unit,n,count\na,1,mg/L,1,0\n','delimiter':'comma'}}}
    checked=validate_payload(table)
    assert checked['valid'],checked
    assert checked['preview']['input']['rows']==1
    execute_job(table,tmp_path/'table')
    import json
    assert json.loads((tmp_path/'table/job-status.json').read_text())['status']=='completed'
    from test_decision_planning import specification,criteria
    payload={'mode':'verify-report','certificate':{'version':'1.0.0','certificates':[{'cohort_id':'<script>','specification':specification(),'criteria':criteria(),'disclosures':[]}]}}
    assert validate_payload(payload)['valid']
    execute_job(payload,tmp_path/'certificate')
    status=json.loads((tmp_path/'certificate/job-status.json').read_text())
    assert status['status']=='refused'
    report=(tmp_path/'certificate/output/report.html').read_text()
    assert '&lt;script&gt;' in report and '<script>' not in report
    assert 'does not authenticate' in report


def test_json_decision_fraction_retains_exact_token():
    from mic_50_90.validation import load_analysis_json
    raw=load_analysis_json('{"targets":[{"decision_fraction":0.050000000000000000000001}]}')
    assert raw['targets'][0]['decision_fraction']=='0.050000000000000000000001'


def test_distribution_form_validates_targets():
    from mic_50_90.gui_forms import validate_payload
    p={'mode':'distribution','config':dict(n=1,unit='mg/L',panel={'levels':[1,2]},additional_counts=[dict(threshold=2,count=0,n=1,unit='mg/L')],targets=[dict(threshold=2,unit='mg/L',decision_operator='<',decision_fraction='5')])}
    assert not validate_payload(p)['valid']


def test_normalized_percentage_can_be_reused():
    spec=SimpleNamespace(n=20,panel=MICPanel.from_dict({'levels':[1,2]}))
    raw=dict(threshold=2,percentage='5',decimal_places=0,rounding_rule='half_up',n=20,unit='mg/L')
    normalized=_observations([raw],spec)
    assert _observations(normalized,spec)==normalized


@pytest.mark.parametrize('operator,status',[('<','contradicted'),('<=','supported'),('>','contradicted'),('>=','supported')])
def test_exact_boundary_operators(operator,status):
    raw=dict(n=20,unit='mg/L',panel={'levels':[1,2]},additional_counts=[dict(threshold=2,count=1,n=20,unit='mg/L')],targets=[dict(threshold=2,unit='mg/L',decision_operator=operator,decision_fraction='0.05')])
    assert analyse_distribution(raw)['decisions'][0]['sample']['status']==status


def test_json_csv_decisions_equivalent_and_mixed_cohorts(tmp_path):
    import json,csv
    from mic_50_90.cli import main
    raw=dict(cohort_id='good',n=1,unit='mg/L',panel={'levels':[1,2]},additional_counts=[dict(threshold=2,count=0,n=1,unit='mg/L')],targets=[dict(threshold=2,unit='mg/L',decision_operator='<',decision_fraction='0.05')])
    source=tmp_path/'source.json';source.write_text(json.dumps(raw))
    assert main(['distribution',str(source),'--output-dir',str(tmp_path/'json')])==0
    (tmp_path/'input.csv').write_text('cohort_id,panel_id,n,variant_id\ngood,p,1,primary\nbad,missing,1,primary\n')
    (tmp_path/'panels.csv').write_text('panel_id,unit,category,panel_value,lower,upper,lower_closed,upper_closed\np,mg/L,<=1,1,,1,false,true\np,mg/L,2,2,1,2,false,true\np,mg/L,>2,4,2,,false,false\n')
    (tmp_path/'counts.csv').write_text('cohort_id,threshold,unit,n,count\ngood,2,mg/L,1,0\n')
    (tmp_path/'targets.csv').write_text('cohort_id,threshold,unit,decision_operator,decision_fraction\ngood,2,mg/L,<,0.05\n')
    assert main(['distribution',str(tmp_path/'input.csv'),'--panels',str(tmp_path/'panels.csv'),'--additional-counts',str(tmp_path/'counts.csv'),'--targets',str(tmp_path/'targets.csv'),'--output-dir',str(tmp_path/'csv')])==0
    a=json.loads((tmp_path/'json/results.json').read_text())['cohorts'][0]
    records=json.loads((tmp_path/'csv/results.json').read_text())['cohorts']
    assert a['decisions']==records[0]['decisions']
    assert records[1]['status']=='refused'
    exported=list(csv.DictReader((tmp_path/'csv/decisions.csv').open()))
    assert exported[0]['status']=='supported'
    assert exported[0]['count_components']=='[[0, 0]]'


def test_certificate_contradictions_refused_and_valid_without_histogram(tmp_path):
    import json
    from test_decision_planning import specification,criteria
    from mic_50_90.gui_worker import execute_job
    rows=[dict(threshold=t,count=k,n=10,unit='mg/L') for t,k in [(2,1),(4,0)]]
    cert=dict(cohort_id='good',specification=specification(),criteria=criteria(),disclosures=rows)
    execute_job(dict(mode='verify-report',certificate=dict(version='1.0.0',certificates=[cert])),tmp_path/'good')
    assert json.loads((tmp_path/'good/job-status.json').read_text())['status']=='completed'
    cert['disclosures'][0]['count']=10
    execute_job(dict(mode='verify-report',certificate=dict(version='1.0.0',certificates=[cert])),tmp_path/'bad')
    assert json.loads((tmp_path/'bad/job-status.json').read_text())['status']=='refused'


@pytest.mark.parametrize('n',[1,7,20,101])
def test_every_integer_rounded_preimage_complement(n):
    from decimal import Decimal,ROUND_HALF_UP
    spec=SimpleNamespace(n=n,panel=MICPanel.from_dict({'levels':[1,2]}))
    for percent in {str((Decimal(k)*100/n).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for k in range(n+1)}:
        compatible=[k for k in range(n+1) if str((Decimal(k)*100/n).quantize(Decimal('1'),rounding=ROUND_HALF_UP))==percent]
        row=dict(threshold=2,percentage=percent,decimal_places=0,rounding_rule='half_up',n=n,unit='mg/L',relation='<=')
        result=_observations([row],spec)[0]
        assert [result['count_min'],result['count_max']]==[n-max(compatible),n-min(compatible)]


def test_table_preview_reports_missing_columns_without_solver():
    from mic_50_90.gui_forms import validate_payload
    p=dict(mode='batch',input_format='tables',tables={k:dict(text='cohort_id\na\n',delimiter='comma') for k in ['input','panels','targets']})
    v=validate_payload(p)
    assert not v['valid']
    assert any('mic50' in issue['message'] for issue in v['issues'])


def test_table_preview_warns_on_panel_mismatch_but_keeps_independent_cohorts():
    from mic_50_90.gui_forms import validate_payload
    p=dict(mode='distribution',input_format='tables',tables={'input':dict(text='cohort_id,panel_id,n,variant_id\na,missing,1,primary\n',delimiter='comma'),'panels':dict(text='panel_id,unit,category,panel_value,lower_closed,upper_closed\np,mg/L,a,1,false,true\n',delimiter='comma')})
    v=validate_payload(p)
    assert v['valid']
    assert any('missing' in warning['message'] for warning in v['warnings'])


def test_certificate_retains_original_decimal_tokens():
    import json
    from mic_50_90.gui_forms import decode_payload, validate_payload
    original = '{"version":"1.0.0","certificates":[{"specification":{"n":20},"criteria":[{"decision_fraction":0.050000000000000000000001}],"disclosures":[]}]}'
    raw = '{"mode":"verify-report","certificate":' + original + '}'
    value = decode_payload(raw)
    assert value['certificate']['certificates'][0]['criteria'][0]['decision_fraction'] == '0.050000000000000000000001'
    payload = dict(mode='verify-report', certificate=json.loads(original), certificate_json=original)
    validated = validate_payload(payload)
    assert validated['valid']
    assert validated['payload']['certificate']['certificates'][0]['criteria'][0]['decision_fraction'] == '0.050000000000000000000001'


def test_population_complement_does_not_change_strict_boundary():
    from mic_50_90.distribution_decisions import distribution_decisions
    from mic_50_90.distribution_workflow import distribution_problems
    raw = dict(n=20, unit='mg/L', panel={'levels':[1,2]},
               additional_counts=[dict(threshold=1,unit='mg/L',n=20,count=1)],
               targets=[dict(threshold=1, unit='mg/L',decision_operator='>',decision_fraction='0.05')])
    problems, _, _ = distribution_problems(raw)
    rows = distribution_decisions(raw, problems, {'cdf':[{'lower':0.9,'upper':0.95}]}, {})
    assert rows[0]['population']['status'] == 'undetermined'


@pytest.mark.parametrize('disclosure',[{'count':19,'relation':'<='}, {'count_min':19,'count_max':19,'relation':'<='}])
def test_certificate_readable_report_keeps_rational_criterion_and_source_relation(tmp_path,disclosure):
    import json
    from mic_50_90.gui_worker import execute_job
    spec=dict(mode='empirical',unit='mg/L',n=20,panel={'levels':[1,2]},summaries={'quantiles':[
        dict(probability=.5,category='<=1',convention='ceiling'),dict(probability=.9,category='<=1',convention='ceiling')]},thresholds=[2])
    # Use the panel's actual generated label rather than assuming its spelling.
    spec['summaries']['quantiles'][0]['category']=MICPanel.from_dict(spec['panel']).bins[0].label
    spec['summaries']['quantiles'][1]['category']=MICPanel.from_dict(spec['panel']).bins[0].label
    cert=dict(specification=spec,criteria=[dict(threshold=2,unit='mg/L',decision_operator='<=',decision_fraction='1/20')],disclosures=[dict(threshold=2,unit='mg/L',n=20,**disclosure)])
    execute_job(dict(mode='verify-report',certificate=dict(version='1.0.0',certificates=[cert])),tmp_path/'job')
    assert json.loads((tmp_path/'job/job-status.json').read_text())['status']=='completed'
    html=(tmp_path/'job/output/report.html').read_text(encoding='utf-8')
    assert 'MIC &lt;= 2' in html and '5%' in html
    assert '19–19' in html if 'count_min' in disclosure else '19; denominator' in html
