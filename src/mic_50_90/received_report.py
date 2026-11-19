"""Check a received reporting certificate without the laboratory's complete counts.

The check recomputes, from the declared summaries and the disclosed counts alone, the
smallest and largest number of isolates above each declared threshold and whether each
declared answer is established. It assumes that the disclosed counts are true; it does
not authenticate the source.
"""
import csv
import json
from decimal import Decimal
from fractions import Fraction
from html import escape
from pathlib import Path

from ._version import COMPATIBLE_REPORT_VERSIONS, __version__
from .file_safety import check_output_paths
from .sufficient_reporting import verify_reporting

FIELDS = ('cohort_id', 'question', 'count_min', 'count_max', 'n', 'answer', 'collection_status')
NOTE = 'The check assumes that the disclosed counts are true; it does not authenticate the source.'
EXACT = {'decision_fraction', 'n', 'rank', 'probability', 'count', 'count_min', 'count_max',
         'percentage', 'decimal_places'}
DECISIONS = {'supported': 'Condition met', 'contradicted': 'Condition not met',
             'undetermined': 'Not enough information'}
STYLE = ('body{font:16px/1.55 system-ui,sans-serif;color:#183448;background:#f3f6f8;max-width:1050px;'
         'margin:2rem auto;padding:0 1rem}h1,h2{line-height:1.2;overflow-wrap:anywhere}section{background:white;'
         'border:1px solid #d8e1e8;border-radius:8px;padding:1.4rem;margin:1.5rem 0}table{border-collapse:collapse;'
         'width:100%;font-size:.94rem}caption{text-align:left;font-weight:700;padding:.7rem 0}th,td{text-align:left;'
         'border-bottom:1px solid #dae3e9;padding:.7rem;overflow-wrap:anywhere}th{background:#eaf0f5}pre{white-space:'
         'pre-wrap;overflow-wrap:anywhere;font-size:.85rem}details{margin-top:1rem}summary{cursor:pointer;'
         'font-weight:600}@media(max-width:600px){section{padding:.6rem}th,td{padding:.35rem;font-size:.8rem}}'
         '@media print{body{background:white;margin:0}section{border:0}details{display:none}}')


def load_certificate_json(text):
    """Read a certificate and keep the exact decimal tokens of counts, sizes and fractions."""
    def convert(value, key=None):
        if isinstance(value, dict):
            return {name: convert(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [convert(item, key) for item in value]
        if isinstance(value, Decimal):
            return str(value) if key in EXACT else float(value)
        return value
    return convert(json.loads(text, parse_float=Decimal))


def check_certificates(document):
    """Check every collection of a certificate document.

    Returns one record per collection with status ``established`` (every declared answer
    follows from the disclosures), ``undetermined`` (more information is required) or
    ``refused`` (the disclosures contradict the summaries or the input is invalid).
    """
    if not isinstance(document, dict) or document.get('version') not in COMPATIBLE_REPORT_VERSIONS:
        raise ValueError('The input is not a MIC-50-90 reporting certificate (reporting_certificates.json)')
    records = document.get('certificates') or []
    if not isinstance(records, list) or not records:
        raise ValueError('The certificate lists no collections')
    checked = []
    for row in records:
        if not isinstance(row, dict):
            raise ValueError('Every certificate entry must be an object')
        record = dict(cohort_id=str(row.get('cohort_id', 'Collection')), criteria=row.get('criteria'),
                      disclosures=row.get('disclosures'))
        try:
            result = verify_reporting(row['specification'], row['criteria'], row['disclosures'])
        except (ValueError, TypeError, KeyError, RuntimeError, ArithmeticError) as exc:
            record.update(status='refused', reason=str(exc))
        else:
            record.update(status='established' if result['sufficient'] else 'undetermined',
                          reason='' if result['sufficient'] else 'The disclosures do not settle every declared question.',
                          verification=result,
                          initial=verify_reporting(row['specification'], row['criteria'], [])['decisions'])
        checked.append(record)
    return checked


def _question(item):
    return (f"share with MIC > {item['threshold']:g} {item['unit']} "
            f"{item['decision_operator']} {item['decision_fraction_text']}")


def table_rows(records):
    return [dict(cohort_id=record['cohort_id'], question=_question(item), count_min=item['count_min'],
                 count_max=item['count_max'], n=item['n'], answer=item['status'], collection_status=record['status'])
            for record in records for item in record.get('verification', {}).get('bounds', [])]


def summary_lines(records):
    lines = []
    for record in records:
        status = record['status']
        lines.append(f"{record['cohort_id']}: " + {'established': 'all declared answers are established',
                                                   'undetermined': 'more information is required',
                                                   'refused': 'refused: ' + record['reason']}[status])
        for item in record.get('verification', {}).get('bounds', []):
            lines.append(f"  MIC > {item['threshold']:g} {item['unit']}: {item['count_min']} to {item['count_max']} "
                         f"of {item['n']} isolates; {item['status']}")
    return lines + ['', NOTE]


def render_html(records):
    from .result_view import VIEW_STYLE, count_text, verification_overview
    from .typography import html_with_typography
    body = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>Report verification</title><style>'
            + STYLE + VIEW_STYLE + '</style><h1>Report verification</h1><p>Logical checking does not authenticate '
            'source records. No original histogram is required. These are recorded-sample decisions, not '
            'population guarantees.</p>']
    for record in records:
        message = {'established': 'Logical sufficiency verified.',
                   'undetermined': 'Not every declared answer is established: ' + record['reason'],
                   'refused': 'Verification refused: ' + record['reason']}[record['status']]
        body.append('<section><h2>' + escape(record['cohort_id']) + '</h2><p>' + escape(message) + '</p>')
        checked = record.get('verification')
        if checked:
            body.append(verification_overview(checked, record['disclosures'], initial=record['initial']))
            body.append('<p>Sample size: ' + escape(str(checked['sample_size'])) + '</p><table><caption>Questions and '
                        'results</caption><thead><tr><th>Recorded MIC</th><th>Criterion</th><th>Compatible count</th>'
                        '<th>Decision</th></tr></thead><tbody>')
            for answer in checked['bounds']:
                percentage = str(Fraction(answer['decision_fraction_text']) * 100)
                cells = [f"> {answer['threshold']:g} {answer['unit']}", f"{answer['decision_operator']} {percentage}%",
                         f"{count_text(answer['count_components'])} of {answer['n']}", DECISIONS[answer['status']]]
                body.append('<tr>' + ''.join('<td>' + escape(cell) + '</td>' for cell in cells) + '</tr>')
            body.append('</tbody></table>')
        body.append('<h3>Disclosed counts</h3><ul>')
        for item in record['disclosures'] or []:
            amount = (str(item['count']) if 'count' in item else
                      str(item['percentage']) + '% with declared rounding' if 'percentage' in item else
                      str(item.get('count_min', '?')) + '–' + str(item.get('count_max', '?')))
            body.append('<li>' + escape(f"{amount}; denominator {item.get('n', '?')}; MIC {item.get('relation', '>')} "
                                        f"{item.get('threshold', '?')} {item.get('unit', '')}") + '</li>')
        body.append('</ul><details><summary>Complete calculation record</summary><pre>'
                    + escape(json.dumps(record, indent=2, ensure_ascii=False)) + '</pre></details></section>')
    body.append('<p>' + escape(NOTE) + '</p></html>')
    return html_with_typography(''.join(body))


def run_verify_report(args):
    source, destination = Path(args.input), Path(args.output_dir)
    outputs = [destination / name for name in ('verification.csv', 'verification.txt', 'results.json', 'report.html')]
    check_output_paths([source], outputs)
    try:
        document = load_certificate_json(source.read_text(encoding='utf-8'))
    except ValueError as error:
        raise ValueError(f'{source} is not a readable JSON file: {error}') from None
    records = check_certificates(document)
    destination.mkdir(parents=True, exist_ok=True)
    with outputs[0].open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(table_rows(records))
    lines = summary_lines(records)
    outputs[1].write_text('\n'.join(lines) + '\n', encoding='utf-8')
    outputs[2].write_text(json.dumps(dict(software='MIC-50-90', software_version=__version__, cohorts=records),
                                     indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    outputs[3].write_text(render_html(records), encoding='utf-8')
    print('\n'.join(lines))
    settled = all(record['status'] == 'established' for record in records)
    return 2 if args.fail_on_insufficient and not settled else 0
