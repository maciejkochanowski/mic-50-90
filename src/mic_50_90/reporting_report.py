"""Plain-language display of a report selected from a known histogram."""
from html import escape
from .decision_report import _criterion_percent


def render_reporting_plan(plan):
    parts=['<section><h3>Counts to include in your report</h3>',
           '<p>This choice is made after inspecting the complete histogram. '
           'It preserves the listed answers about this sample when a reader receives '
           'the summaries and these counts. It does not preserve the full distribution '
           'or create a population or calibration guarantee.</p>']
    if not plan.get('sufficient'):
        parts.append('<p>'+escape(plan.get('reason') or 'No sufficient report is available.')+'</p></section>')
        return ''.join(parts)
    heading='Cheapest sufficient report' if plan.get('optimality_verified') else 'Sufficient report; minimum cost not established'
    parts.append('<p><strong>'+heading+'</strong>. '+str(len(plan['disclosures']))+
                 ' additional count fields; declared cost '+escape(str(plan['report_cost']))+'.</p>')
    if plan.get('reason'):
        parts.append('<p>'+escape(plan['reason'])+'</p>')
    if plan['disclosures']:
        parts.append('<table><thead><tr><th>Count strictly above</th><th>Count</th><th>Original sample size</th></tr></thead><tbody>')
        for row in plan['disclosures']:
            parts.append('<tr><td>'+escape(str(row['threshold']))+' mg/L</td><td>'+str(row['count'])+
                         '</td><td>'+str(row['n'])+'</td></tr>')
        parts.append('</tbody></table>')
    else:
        parts.append('<p>The declared summaries already answer all these questions; no additional counts are needed.</p>')
    parts.append('<table><thead><tr><th>Threshold (mg/L)</th><th>Criterion for the share above it</th><th>Before adding counts</th><th>After adding counts</th></tr></thead><tbody>')
    labels={'supported':'Criterion established','contradicted':'Criterion ruled out','undetermined':'Not settled'}
    for before,row in zip(plan['initial_decisions'],plan['verification']['bounds']):
        parts.append('<tr><td>'+escape(str(row['threshold']))+'</td><td>'+escape(row['decision_operator'])+' '+
                     escape(_criterion_percent(row))+'</td><td>'+labels[before]+
                     '</td><td>'+labels[row['status']]+'</td></tr>')
    parts.append('</tbody></table><p>Use reporting_counts.csv with the original summaries, panel and questions. '
                 'reporting_certificates.json contains the inputs needed for a logical sufficiency check '
                 'without the complete histogram. Count accuracy remains the reporting laboratory\'s responsibility.</p></section>')
    return ''.join(parts)
