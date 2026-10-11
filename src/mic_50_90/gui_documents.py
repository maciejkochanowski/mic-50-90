"""Text-table and certificate adapters; validation never runs a solver."""
import csv
import io
from html import escape
import json
from types import SimpleNamespace


def validate_document(payload):
    issues, preview, warnings, parsed = [], {}, [], {}
    if not isinstance(payload.get("options", {}), dict):
        issues.append(dict(field="options", message="Options must be a JSON object."))
    mode = payload.get('mode')
    if mode == 'verify-report':
        doc = payload.get('certificate')
        if not isinstance(doc,dict) or doc.get('version') != '1.0.0' or not isinstance(doc.get('certificates'),list) or not doc['certificates']:
            issues.append(dict(field='certificate',message='Supply a nonempty MIC-50-90 1.0.0 reporting_certificates.json document.'))
        else:
            for index,row in enumerate(doc['certificates']):
                if not isinstance(row,dict) or not isinstance(row.get('specification'),dict) or not isinstance(row.get('criteria'),list) or not row['criteria'] or not isinstance(row.get('disclosures'),list):
                    issues.append(dict(field=f'certificate.{index}',message='Each certificate requires specification, nonempty criteria and disclosures.'))
    else:
        if mode not in {'distribution','batch','reporting-audit'}:
            issues.append(dict(field='mode',message='Choose distribution, batch or reporting-audit.'))
        tables=payload.get('tables',{})
        if not isinstance(tables,dict):
            tables={}
        required={'input','panels'} | ({'targets'} if mode != 'distribution' else set())
        for name in required-tables.keys():
            issues.append(dict(field='tables.'+name,message='Supply this text table.'))
        for name,table in tables.items():
            try:
                if name not in {'input','panels','targets','additional_counts'}:
                    raise ValueError('Unsupported table name')
                if not isinstance(table,dict) or not isinstance(table.get('text'),str):
                    raise ValueError('Supply table text, not a filesystem path or spreadsheet file')
                delimiter={'comma':',','semicolon':';','tab':'\t'}[table.get('delimiter')]
                reader=csv.DictReader(io.StringIO(table['text'].lstrip('\ufeff')),delimiter=delimiter)
                columns=reader.fieldnames
                if not columns or len(set(columns))!=len(columns):
                    raise ValueError('Missing or duplicate column names')
                required_columns = {
                    'panels': {'panel_id','unit','category','panel_value','lower_closed','upper_closed'},
                    'targets': ({'cohort_id','unit'} if mode == 'distribution' else {'cohort_id','threshold','unit'}),
                    'additional_counts': {'cohort_id','unit','n'},
                    'input': ({'cohort_id','panel_id','n','variant_id'} if mode == 'distribution' else
                              {'cohort_id','panel_id','category','count','rank_convention'} if mode == 'reporting-audit' else
                              {'cohort_id','panel_id','variant_id','n','mic50','mic90','rank_convention'})}[name]
                missing = required_columns - set(columns)
                if name == 'additional_counts' and 'threshold' not in columns and not {'start_category','end_category'} <= set(columns):
                    raise ValueError('Counts require threshold or both start_category and end_category columns')
                if name == 'targets' and mode == 'distribution' and 'threshold' not in columns and not {'start_category','end_category'} <= set(columns):
                    raise ValueError('Questions require threshold or both start_category and end_category columns')
                if missing:
                    raise ValueError('Missing columns: ' + ', '.join(sorted(missing)))
                rows=list(reader)
                if not rows or any(None in row or None in row.values() for row in rows):
                    raise ValueError('Empty table or row width differs from its column names')
                key='panel_id' if name=='panels' else 'cohort_id'
                if key not in columns or any(not row[key].strip() or row[key]!=row[key].strip() for row in rows):
                    raise ValueError('Every row needs an exact '+key+' without surrounding whitespace')
                preview[name]=dict(rows=len(rows),columns=columns)
                parsed[name]=rows
            except (ValueError,TypeError,KeyError,csv.Error) as exc:
                issues.append(dict(field='tables.'+str(name),message=str(exc) or 'Choose comma, semicolon or tab delimiter explicitly.'))
        if 'input' in parsed and 'panels' in parsed:
            panel_ids = {r['panel_id'] for r in parsed['panels']}
            for row in parsed['input']:
                if row['panel_id'] not in panel_ids:
                    warnings.append(dict(field='tables.input',message='Cohort '+row['cohort_id']+' references missing panel '+row['panel_id']+'; this cohort will be refused.'))
            cohorts = {r['cohort_id'] for r in parsed['input']}
            for name in ('targets','additional_counts'):
                unknown = {r['cohort_id'] for r in parsed.get(name,[])} - cohorts
                if unknown:
                    issues.append(dict(field='tables.'+name,message='Unknown cohort identifiers: '+', '.join(sorted(unknown))))
    return dict(valid=not issues,issues=issues,warnings=warnings,preview=preview,config=None,payload=payload)


def run_tables(payload,work,output):
    from .gui_worker import _table
    from .distribution_workflow import run_distribution
    from .workflows import run_csv_workflow
    paths={}
    for name,table in payload['tables'].items():
        reader=csv.DictReader(io.StringIO(table['text'].lstrip('\ufeff')),delimiter={'comma':',','semicolon':';','tab':'\t'}[table['delimiter']])
        rows=list(reader)
        path=work/(name+'.csv')
        _table(path,rows,reader.fieldnames)
        paths[name]=str(path)
    defaults=dict(population_method='bonferroni',population_time_limit=30.,population_tolerance_pp=.01,precision_pp=None,population_precision_pp=None,population_count_plan=False,population_minimum_bins=None,population_planning_time_limit=10.,
        question_time_limit=10.,report_page_size=50,exclude_direct_targets=False,decision_plan=False,acquisition_plan=False,
        reporting_plan=False,round_cost='0',decision_plan_time_limit=5.,decision_plan_max_states=5000)
    options=payload.get('options',{})
    args=SimpleNamespace(**{key:options.get(key,value) for key,value in defaults.items()},command=payload['mode'],
        input=paths['input'],panels=paths['panels'],targets=paths.get('targets'),additional_counts=paths.get('additional_counts'),
        output_dir=str(output),delimiter='comma',fail_on_refusal=False,previous_output=None,calibrations=None,decision_queries=None)
    (run_distribution if payload['mode']=='distribution' else run_csv_workflow)(args)


def run_verification(payload,output):
    from .sufficient_reporting import verify_reporting
    from .gui_worker import write_json
    from .result_view import VIEW_STYLE, verification_overview, count_text
    records=[]
    body=['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Report verification</title><style>body{font:16px/1.55 system-ui,sans-serif;color:#183448;background:#f3f6f8;max-width:1050px;margin:2rem auto;padding:0 1rem}h1,h2{line-height:1.2;overflow-wrap:anywhere}section{background:white;border:1px solid #d8e1e8;border-radius:8px;padding:1.4rem;margin:1.5rem 0}table{border-collapse:collapse;width:100%;font-size:.94rem}caption{text-align:left;font-weight:700;padding:.7rem 0}th,td{text-align:left;border-bottom:1px solid #dae3e9;padding:.7rem;overflow-wrap:anywhere}th{background:#eaf0f5}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}details{margin-top:1rem}summary{cursor:pointer;font-weight:600}@media(max-width:600px){section{padding:.6rem}th,td{padding:.35rem;font-size:.8rem}}@media print{body{background:white;margin:0}section{border:0}details{display:none}}</style><h1>Report verification</h1><p>Logical checking does not authenticate source records. No original histogram is required. These are recorded-sample decisions, not population guarantees.</p>']
    body[0] = body[0].replace('</style>', VIEW_STYLE + '</style>')
    for row in payload['certificate']['certificates']:
        cid=row.get('cohort_id','cohort')
        try:
            checked=verify_reporting(row['specification'],row['criteria'],row['disclosures'])
            record=dict(cohort_id=cid,status='ok' if checked['sufficient'] else 'refused',reason='' if checked['sufficient'] else 'Disclosures are insufficient to resolve every question.',verification=checked)
        except (ValueError,TypeError,KeyError,RuntimeError,ArithmeticError) as exc:
            record=dict(cohort_id=cid,status='refused',reason=str(exc))
        record.update(criteria=row['criteria'],disclosures=row['disclosures'])
        records.append(record)
        body.append('<section><h2>'+escape(str(cid))+'</h2><p>'+('Logical sufficiency verified.' if record['status']=='ok' else 'Verification refused: '+escape(record['reason']))+'</p>')
        checked = record.get('verification', {})
        if checked:
            initial = verify_reporting(row['specification'],row['criteria'],[])['decisions']
            body.append(verification_overview(checked,row['disclosures'],initial=initial))
            body.append('<p>Sample size: '+escape(str(checked['sample_size']))+'</p><table><caption>Questions and results</caption><thead><tr><th>Recorded MIC</th><th>Criterion</th><th>Compatible count</th><th>Decision</th></tr></thead><tbody>')
            from fractions import Fraction
            for answer in checked['bounds']:
                percentage = str(Fraction(answer['decision_fraction_text']) * 100)
                cells = [f"> {answer['threshold']:g} {answer['unit']}",
                         f"{answer['decision_operator']} {percentage}%",
                         f"{count_text(answer['count_components'])} of {answer['n']}",
                         {'supported':'Condition met','contradicted':'Condition not met','undetermined':'Not enough information'}[answer['status']]]
                body.append('<tr>'+''.join('<td>'+escape(cell)+'</td>' for cell in cells)+'</tr>')
            body.append('</tbody></table>')
        body.append('<h3>Disclosed counts</h3><ul>')
        for item in row['disclosures']:
            amount = str(item['count']) if 'count' in item else (
                str(item['percentage'])+'% with declared rounding' if 'percentage' in item else
                str(item.get('count_min', '?'))+'–'+str(item.get('count_max', '?')))
            relation = item.get('relation', '>')
            body.append('<li>'+escape(f"{amount}; denominator {item.get('n', '?')}; MIC {relation} {item.get('threshold', '?')} {item.get('unit', '')}")+'</li>')
        body.append('</ul><details><summary>Complete calculation record</summary><pre>'+escape(json.dumps(record,indent=2))+'</pre></details></section>')
    body.append('</html>')
    write_json(output/'results.json',dict(software='MIC-50-90',software_version='1.0.0',cohorts=records))
    from .typography import html_with_typography
    (output/'report.html').write_text(html_with_typography(''.join(body)),encoding='utf-8')
