"""Shared deterministic explanations and graphics of already computed results.

This module does not fit a distribution, select a midpoint or classify a new
statistical claim. It displays the engine's counts and decision statuses.
"""
from fractions import Fraction
from html import escape
import re
import textwrap
from urllib.parse import quote
from .typography import portable_svg


VIEW_STYLE = """
.result-overview{background:white;border-top:2px solid #35638a;border-bottom:1px solid #cbd4da;padding:20px 0;margin:18px 0}
.result-overview h3{font-size:1.35rem;margin:0 0 12px;line-height:1.3}.result-overview h4{margin:16px 0 6px}
.result-answer{font-size:1.17rem;font-weight:650;color:#183448}.result-context{color:#43576a;overflow-wrap:anywhere}
.result-note{border-left:2px solid #cbd4da;padding:6px 12px;background:white}.result-next{font-weight:550}
.result-chart{overflow-x:auto}.result-chart svg{width:100%;min-width:620px;max-width:1100px;height:auto;display:block}
.result-actions{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.result-actions a,.result-actions button{font:inherit;padding:6px 10px;border:1px solid #b8cbd2;border-radius:5px;background:white;color:#174f62;text-decoration:none;cursor:pointer}
.result-layers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:16px 0}.result-layers p{background:white;border-top:2px solid #cbd4da;padding:12px 0;margin:0}
.result-layers strong{display:block}.result-steps>div{padding:12px 0;border-bottom:1px solid #cbdadd}
details.result-details{border-top:1px solid #ccd9df;margin-top:20px;padding-top:14px}summary{cursor:pointer;font-weight:600}
.result-flow{display:flex;flex-wrap:wrap;gap:20px}.result-flow span{background:white;border-bottom:2px solid #00746c;padding:10px 0}
.result-question{background:white;border-left:3px solid #35638a;padding:8px 12px;margin:10px 0}.result-question strong{display:block}
.embedded-report main{padding:0!important}.embedded-report main>h1,.embedded-report main>header,.embedded-report main>p{display:none}.embedded-report article{margin:0!important;padding:12px!important;border:0!important}.embedded-report article>h2{font-size:1rem;color:#43576a;margin:0 0 8px}.embedded-report .result-overview{margin-top:10px}
@media(max-width:700px){.result-layers{grid-template-columns:1fr}.result-overview{padding:12px}.result-answer{font-size:1.1rem}}
@media print{.result-actions,.report-controls{display:none!important}.result-chart{overflow:visible}.result-chart svg{min-width:0}.result-overview{break-inside:avoid}details{display:block}details::details-content{content-visibility:visible!important}details>summary{display:block}article[hidden]{display:block!important}}
"""

STATUS_LABELS = {'supported': 'Condition met', 'contradicted': 'Condition not met',
                 'undetermined': 'Not enough information', 'unavailable': 'Result unavailable',
                 'available': 'Possible share'}


def counted(value, singular, plural=None):
    return f'{value} {singular if value == 1 else (plural or singular + "s")}'


def count_text(components):
    return ' or '.join(str(lo) if lo == hi else f'{lo}–{hi}' for lo, hi in components)


def percent_text(components, n):
    return ' or '.join(f'{100*lo/n:.2f}%' if lo == hi else f'{100*lo/n:.2f}–{100*hi/n:.2f}%'
                       for lo, hi in components)


def category_label(text):
    text = str(text).replace('<=', '≤').replace('>=', '≥')
    match = re.fullmatch(r'\(([^,]+),\s*([^]]+)\]', text)
    return f'>{match[1]} to {match[2]}' if match else text


def count_chart(rows, n, *, kind='category', title='MIC groups in the observed sample'):
    """Use a full 0–100% scale; keep all disconnected count components visible."""
    prepared = []
    for row in rows:
        components = row.get('count_components', [[row['count_lower'], row['count_upper']]])
        labels = textwrap.wrap(category_label(row['label']), 27) or ['']
        counts = textwrap.wrap(count_text(components), 31) or ['']
        shares = textwrap.wrap(percent_text(components, n), 31) or ['']
        prepared.append((components, labels, counts, shares, max(74, 22*(len(counts)+len(shares))+16, 22*len(labels)+24)))
    height = 102 + sum(item[-1] for item in prepared)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 {height}" role="img" data-chart="{escape(kind, quote=True)}" aria-label="{escape(title, quote=True)}">',
           f'<title>{escape(title)}; {counted(n, "isolate")}. Bars show exact shares. Capped lines show possible ranges, with every gap retained.</title>',
           f'<rect width="1000" height="{height}" fill="white"/>']
    def label(x, y, value, *, size=16, color='#183448', anchor='start', weight='normal'):
        svg.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="DejaVu Sans,Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(str(value))}</text>')
    label(12, 23, 'MIC group (mg/L)' if kind == 'category' else 'MIC condition (mg/L)', weight='bold')
    label(470, 23, 'Sample share (%)', anchor='middle', weight='bold')
    label(714, 23, f'Count / {n}', weight='bold')
    x = lambda value: 250 + 440 * value / n
    for value in (0, 25, 50, 75, 100):
        at = 250 + 4.4 * value
        svg.append(f'<line x1="{at}" x2="{at}" y1="60" y2="{height-39}" stroke="#e4e8eb"/>')
        label(at, 49, value, size=14, anchor='middle', color='#52616d')
    top = 64
    for components, labels, counts, shares, row_height in prepared:
        y = top + row_height / 2
        for j, value in enumerate(labels):
            label(12, y + 5 + 22*(j-(len(labels)-1)/2), value)
        for lo, hi in components:
            attrs = f'data-count-lower="{lo}" data-count-upper="{hi}"'
            if lo == hi and len(components) == 1:
                svg.append(f'<rect {attrs} x="250" y="{y-9}" width="{440*lo/n:.9g}" height="18" fill="#00746c"/>')
                svg.append(f'<line x1="{x(lo):.9g}" x2="{x(lo):.9g}" y1="{y-9}" y2="{y+9}" stroke="#005b55" stroke-width="2"/>')
            else:
                svg.append(f'<line {attrs} x1="{x(lo):.9g}" x2="{x(hi):.9g}" y1="{y}" y2="{y}" stroke="#35638a" stroke-width="4"/>')
                for endpoint in (lo, hi):
                    svg.append(f'<line x1="{x(endpoint):.9g}" x2="{x(endpoint):.9g}" y1="{y-9}" y2="{y+9}" stroke="#35638a" stroke-width="2"/>')
        for j, value in enumerate(counts + shares):
            label(714, top+24+22*j, value, color='#183448' if j < len(counts) else '#52616d')
        top += row_height
        svg.append(f'<line x1="12" x2="985" y1="{top}" y2="{top}" stroke="#e4e8eb"/>')
    label(12, height-13, 'Bar: known share. Capped line: possible range. Separate segments: separate possibilities.', size=14, color='#52616d')
    svg.append('</svg>')
    return ''.join(svg)


def chart_block(rows, n, **kwargs):
    svg = count_chart(rows, n, **kwargs)
    return ('<div class="result-chart-block"><div class="result-chart" tabindex="0">'+svg+
            '</div><div class="result-actions"><a data-save-svg download="MIC-50-90-chart.svg" href="data:image/svg+xml;charset=utf-8,'+
            quote(portable_svg(svg), safe='')+'">Save SVG</a><button type="button" data-save-png hidden>Save PNG</button>'
            '<button type="button" data-print-report hidden>Print / save as PDF</button></div></div>')


def context_text(provenance, n):
    names = [str(provenance[key]) for key in ('organism', 'antimicrobial') if provenance.get(key)]
    text = escape(' · '.join([*names, counted(n, 'isolate'), 'MIC in mg/L']))
    source = provenance.get('source') or provenance.get('source_location')
    if source:
        text += '<br>Source: ' + escape(str(source))
    return text


def interpretation_context(provenance):
    """Separate supplied source descriptions from declarations and clinical use."""
    from .input_context import SAMPLING_GUIDANCE, threshold_note
    context = provenance.get('sample_context', {})
    facts = [(label, context.get(key)) for key, label in (
        ('host_species', 'Host species'), ('specimen', 'Specimen'),
        ('repeat_sampling', 'Repeated sampling of the same animal or person'), ('grouping_notes', 'Sampling groups'))]
    if not context.get('repeat_sampling'):
        facts[2] = (facts[2][0], 'unknown')
    for key, label in [('source', 'Source'), ('source_location', 'Source location'), ('source_doi', 'Source DOI'),
                       ('panel_basis', 'Panel basis')]:
        if provenance.get(key):
            facts.append((label, provenance[key]))
    parts = ['<div class="result-note"><h4>Source facts supplied with the input</h4>',
        '<p>Source descriptions are retained as supplied; the program does not independently authenticate them.</p><ul>']
    parts.extend('<li><strong>'+escape(label)+':</strong> '+escape(str(value or 'Not supplied'))+'</li>' for label, value in facts)
    parts.append('</ul><h4>User assumptions and interpretation</h4><p>Intended population: '+
                 escape(str(context.get('intended_population') or 'Not supplied'))+'. '+
                 ('Population inference was explicitly requested under independent sampling from the same population.'
                 if provenance.get('iid_declared') else 'Population inference was not requested.')+'</p>')
    if provenance.get('rank_basis'):
        parts.append('<p>Quantile rule basis (source evidence or declared assumption): '+escape(str(provenance['rank_basis']))+'</p>')
    parts.append('<p>'+escape(SAMPLING_GUIDANCE)+'</p>')
    for row in provenance.get('threshold_context', []):
        try:
            note = threshold_note(row)
        except (TypeError, ValueError):
            note = 'Threshold context is incomplete or unrecognised. Use neutral MIC wording; no clinical classification is assigned.'
        parts.append('<p><strong>Threshold '+escape(str(row.get('threshold', '')))+' '+escape(str(row.get('unit') or 'mg/L'))+':</strong> '+escape(note))
        for key, label in [('threshold_source', 'Source'), ('threshold_version', 'Version'), ('threshold_applicability', 'Applicability')]:
            if row.get(key):
                parts.append('<br>'+label+': '+escape(str(row[key])))
        parts.append('</p>')
    return ''.join(parts)+'</div>'


def count_request(record, start_category, end_category):
    """A copyable request for an existing selected count, with exact categories."""
    categories = record.get('panel', {}).get('categories', [])
    labels = [row['label'] for row in categories]
    if start_category not in labels or end_category not in labels:
        return ''
    selected = categories[labels.index(start_category):labels.index(end_category)+1]
    descriptions = []
    for row in selected:
        bounds = []
        for side, signs in [('lower', ('>', '>=')), ('upper', ('<', '<='))]:
            value = row.get(side+'_bound')
            if value is not None:
                bounds.append(f'MIC {signs[bool(row.get(side+"_closed"))]} {value:g}')
        descriptions.append(str(row['label'])+' ('+(' and '.join(bounds) or 'all positive MIC values')+' mg/L)')
    return (f'For sample {record.get("cohort_id", "[sample identifier]")}, n = {record["n"]}, please provide the exact integer '
        'count among these same original isolates in the following recorded MIC categories, including both endpoint categories: '
        +'; '.join(descriptions)+'. Retain the original denominator, panel, organism and antimicrobial. '
        'Return the count, sample identifier, denominator and source record; do not add newly sampled isolates.')


def count_request_html(request):
    if not request:
        return ''
    return '<h4>Ready-to-copy count request</h4><p class="result-note" style="user-select:all">'+escape(request)+'</p>'


def criterion_text(row):
    from .distribution_targets import event_text
    if not row.get('decision_operator'):
        return 'Proportion with ' + event_text(row)
    wording = {'<': 'Fewer than', '<=': 'At most', '>': 'More than', '>=': 'At least'}
    value = Fraction(str(row['decision_fraction_text'])) * 100
    # Exact rational arithmetic supplies the displayed criterion, not a rounded
    # value from the calculated endpoints. The engine alone decides its status.
    limit = f'{float(value):.12g}'
    if Fraction(limit) != value:
        limit = str(value)
    return f"{wording[row['decision_operator']]} {limit}% have {event_text(row)}"


def decision_cards(decisions, n):
    parts = []
    for row in decisions:
        sample = row['sample']
        parts.append('<div class="result-question"><strong>'+escape(STATUS_LABELS[sample['status']])+': '+
                     escape(criterion_text(row))+'.</strong>')
        components = sample.get('count_components', [])
        if components:
            parts.append(escape(f'{count_text(components)} of {n} isolates ({percent_text(components,n)}).'))
        parts.append(' This answer concerns the observed sample.</div>')
        if row.get('measurement_explanation'):
            parts.append('<div class="result-note"><strong>Measurement limit:</strong> '+escape(row['measurement_explanation'])+'</div>')
        population = row.get('population', {})
        if population.get('status') == 'available':
            confidence = population.get('confidence_level')
            level = f' ({100*confidence:g}% simultaneous confidence)' if confidence is not None else ''
            parts.append('<div class="result-question"><strong>Population'+escape(level)+': '+
                f'{100*population["lower"]:.2f}–{100*population["upper"]:.2f}%.</strong> '+
                escape(population.get('guarantee', ''))+'</div>')
        if population.get('calculation_assessment'):
            confidence = population.get('confidence_level')
            level = f' ({100*confidence:g}% simultaneous confidence)' if confidence is not None else ''
            parts.append('<div class="result-question"><strong>Population'+escape(level)+': '+
                escape(STATUS_LABELS[population['status']])+'.</strong> '+
                (f'Possible share: {100*population["lower"]:.2f}–{100*population["upper"]:.2f}%. '
                 if 'lower' in population and 'upper' in population else '')+
                escape(population['interpretation'])+'</div>')
    return ''.join(parts)


def question_ranked_cut(record, problems):
    """Index of the cumulative count that most reduces the declared questions' sample ranges.

    Uses the exact minimax ranking of single counts by difference-constraint closure, so the
    result does not depend on computing time. Open questions are unresolved criteria and
    questions without a criterion whose count is not yet fixed. Returns None when no open
    sample question exists, the report has constraints outside that exact class, or no count has a positive
    guaranteed reduction.
    """
    if not problems or not all(p._canonical_tu and p._integral_rhs for p in problems.values()):
        return None
    k = len(record['sample']['categories'])
    targets = []
    for row in record.get('decisions', []):
        sample = row.get('sample', {})
        components = sample.get('count_components', [])
        # A question without a criterion is still open while its count is not fixed.
        open_question = sample.get('status') == 'undetermined' or (
            sample.get('status') == 'available' and (any(lo < hi for lo, hi in components) or len(components) > 1))
        if not open_question or row.get('measurement_ambiguous_categories'):
            continue
        start, stop = row.get('start_index'), row.get('stop_index')
        if isinstance(start, int) and isinstance(stop, int) and 0 <= start < stop <= k and stop - start < k:
            target = [0.] * k
            target[start:stop] = [1.] * (stop - start)
            targets.append(target)
    if not targets:
        return None
    from .utility import rank_robust_tail_count_questions
    try:
        ranked = rank_robust_tail_count_questions(problems=problems, target_objectives=targets)
    except (ValueError, RuntimeError, ArithmeticError, MemoryError):
        return None
    if not ranked or ranked[0].minimax_width_reduction <= 0:
        return None
    return ranked[0].cut_index, len(targets)


def distribution_guidance(record, problems=None):
    """Explain existing bounds and name one transparent count to request.

    With declared questions, the count is the cumulative count with the largest
    guaranteed reduction of those questions' sample ranges (exact minimax ranking).
    Otherwise, or if that ranking gives no positive reduction, it is the largest
    unresolved cumulative range: a truthful cumulative count fixes that coordinate.
    Neither rule is a minimum-cost plan; the planning functions provide those.
    """
    sample, n = record['sample'], record['n']
    missing = any(r['count_lower'] != r['count_upper'] for r in sample['categories'])
    unresolved = [r for r in sample['cdf'] if r['count_lower'] < r['count_upper']]
    ranked = question_ranked_cut(record, problems)
    ranked_cut, questions = ranked if ranked is not None else (None, 0)
    if ranked_cut is not None and sample['cdf'][ranked_cut]['count_lower'] < sample['cdf'][ranked_cut]['count_upper']:
        candidate = sample['cdf'][ranked_cut]
        rule = ('Largest guaranteed reduction of the declared question ranges (exact minimax ranking of single '
                'cumulative counts); not a minimum-cost plan')
    else:
        candidate = max(unresolved, key=lambda r: r['count_upper']-r['count_lower']) if unresolved else None
        rule = 'Largest unresolved cumulative count range; not a minimum-cost plan'
    suggestion = None
    if candidate is not None:
        suggestion = dict(recorded_groups=candidate['index']+1, through_label=candidate['label'],
            count_lower=candidate['count_lower'], count_upper=candidate['count_upper'],
            count_components=candidate.get('count_components', [[candidate['count_lower'], candidate['count_upper']]]),
            selection_rule=rule)
        first = category_label(sample['categories'][0]['label'])
        groups = (f'recorded MIC group {first}' if candidate['index'] == 0 else
                  f'recorded MIC groups {first} through {category_label(candidate["label"])}')
        reason = (' Of the single counts that could be requested, this one narrows the answer'
                  + (' to the declared question' if questions == 1 else 's to the declared questions')
                  + ' most in the worst case.' if ranked_cut is not None and candidate is sample['cdf'][ranked_cut] else '')
        next_step = (f'Ask for the total number of the same {counted(n, "isolate")} in the {groups}. '
                     f'That total is currently {count_text(suggestion["count_components"])}.{reason} '
                     'One exact count fixes this cumulative share; other MIC groups may still be uncertain.')
    else:
        next_step = 'Save or report these group counts. Further counts for the same groups cannot improve this sample description.'
    population = record.get('population', {})
    requested = record.get('inference_requested', {}).get('population', False)
    unfinished = bool(requested and population.get('requested_method') in ('joint-exact', 'range-calibrated', 'range-hunter')
                      and not population.get('precision_reached', False))
    request = count_request(record, sample['categories'][0]['label'], candidate['label']) if candidate else ''
    measurement = [r for r in record.get('decisions', []) if r.get('measurement_ambiguous_categories')
                   and r.get('sample', {}).get('status') in ('undetermined', 'available')
                   and any(lo < hi for lo, hi in r['sample'].get('count_components', []))]
    if measurement:
        next_step += (' For questions that cut a measured category, category counts alone cannot remove the within-category ambiguity. '
                      'Check documented original readings or consider a measurement with a suitable concentration range.')
    return dict(missing_count_information=missing, population_requested=requested, count_request=request,
                measurement_limitation=bool(measurement),
                numerical_refinement_unfinished=unfinished, suggested_count=suggestion, next_step=next_step)


def guidance_html(record):
    guidance = record.get('interpretation') or distribution_guidance(record)
    notes = ['<div class="result-note"><strong>What limits this answer?</strong><ul>']
    notes.append('<li><strong>Missing counts:</strong> '+(
        'some recorded group counts are unknown. A larger sample alone does not recover these missing counts.'
        if guidance['missing_count_information'] else
        'the displayed group counts are known. Concentrations within each group are not identified.')+'</li>')
    if guidance['population_requested']:
        population=record.get('population', {})
        if population.get('cdf_bounds'):
            notes.append('<li><strong>Sampling uncertainty:</strong> population intervals allow for observing a sample. They require independent observations from the same population and a fixed panel.</li>')
        else:
            notes.append('<li><strong>Population analysis unavailable:</strong> '+escape(str(population.get('reason','No population result available.')).rstrip('.'))+'.</li>')
    else:
        notes.append('<li><strong>Population analysis:</strong> not requested. The sample result above is complete for the supplied information.</li>')
    if guidance['numerical_refinement_unfinished']:
        notes.append('<li><strong>Numerical refinement:</strong> the requested endpoint precision was not certified. Retained population bounds remain valid under their stated assumptions; they may be wider than the method could ultimately produce.</li>')
    if guidance.get('measurement_limitation'):
        notes.append('<li><strong>Measurement limit:</strong> a requested threshold cuts a measured MIC category. A complete histogram of those categories still cannot locate MIC within that category.</li>')
    for issue in record.get('input_information_issues', []):
        notes.append('<li><strong>Unused percentage:</strong> '+escape(issue['reason'])+'</li>')
    notes.append('</ul></div>')
    return ''.join(notes)


def evidence_html(record):
    rows=[]
    provenance=record.get('provenance',{})
    for key,label in [('panel_basis','Panel'),('rank_basis','Quantile convention'),('metadata_basis','Other metadata')]:
        if provenance.get(key): rows.append((label,str(provenance[key])))
    for index,count in enumerate(record.get('additional_counts',[]),1):
        rows.append((f'Additional count {index}',str(count.get('source') or 'Source not supplied')))
    if not rows:return ''
    return ('<details class="result-details"><summary>Where the input information came from</summary>'
            '<p>These descriptions were supplied with the input; the program does not independently authenticate them.</p><ul>'+
            ''.join('<li><strong>'+escape(label)+':</strong> '+escape(value)+'</li>' for label,value in rows)+'</ul></details>')


def distribution_overview(record):
    sample, n = record['sample'], record['n']
    rows = sample['categories']
    fixed = sum(r['count_lower'] == r['count_upper'] for r in rows)
    conclusion = (f'All {len(rows)} MIC group counts are determined.' if fixed == len(rows) else
                  f'The information fixes {fixed} of {len(rows)} MIC group counts. The remaining counts are ranges.')
    parts = ['<section class="result-overview"><h3>What do these isolates show?</h3>',
             '<p class="result-context">'+context_text(record.get('provenance',{}), n)+'</p>',
             '<h4>Result for this collection</h4><p class="result-answer">'+conclusion+'</p>', decision_cards(record.get('decisions',[]), n),
             chart_block(rows, n),
             '<h4>Reading the graph</h4><p class="result-note">Each row is one MIC group. A bar shows its known share. A capped line shows the smallest and largest shares allowed by the supplied data. '
             'The rows describe the same collection and must satisfy its information together. These are sample bounds, not population confidence intervals. MIC within a measured interval remains unspecified.</p>']
    precision = record.get('population_resolution', {})
    if precision.get('bins'):
        groups = precision['bins']
        noun = 'group' if len(groups)==1 else 'groups'
        parts.append(f'<div class="result-guidance"><h3>Population: how much detail is supported?</h3><p><strong>{len(groups)} confirmed MIC {noun}; requested width of {precision["precision_pp"]:g} percentage points at {100*precision["confidence_level"]:g}% simultaneous confidence.</strong></p>')
        if precision.get('maximum_number_verified'):
            parts.append('<p>The maximum number of groups is confirmed for this information and population method.</p>')
        else:
            parts.append(f'<p>Up to {precision["possible_number_of_bins"]} groups have not been ruled out. Further numerical work is needed to confirm the maximum.</p>')
        if len(groups)==1:
            parts.append('<p>Only the whole panel is confirmed at this width. This does not describe how MIC values are distributed within the panel.</p>')
        height=75+50*len(groups)
        parts.append(f'<svg viewBox="0 0 760 {height}" style="font-family:DejaVu Sans,Arial,sans-serif" role="img" aria-label="Population confidence intervals for the confirmed MIC groups"><title>Simultaneous population intervals, not observed sample percentages</title>')
        for tick in [0,25,50,75,100]:
            x=210+4*tick
            parts.append(f'<line x1="{x}" x2="{x}" y1="30" y2="{height-25}" stroke="#ddd"/><text x="{x}" y="20" text-anchor="middle" font-size="12">{tick}%</text>')
        for i,row in enumerate(groups):
            y=55+50*i;lo=100*row['lower'];hi=100*row['upper']
            parts.append(f'<text x="200" y="{y+4}" text-anchor="end" font-size="13">{escape(row["label"])} mg/L</text><line x1="{210+4*lo}" x2="{210+4*hi}" y1="{y}" y2="{y}" stroke="#285c86" stroke-width="6"/><circle cx="{210+4*lo}" cy="{y}" r="4" fill="#285c86"/><circle cx="{210+4*hi}" cy="{y}" r="4" fill="#285c86"/><text x="625" y="{y+4}" font-size="13">{lo:.2f}–{hi:.2f}%</text>')
        parts.append('</svg><p>Each line spans compatible population shares. No most likely midpoint is implied. Combining categories reduces detail.</p></div>')
    if record.get('question_note'):
        parts.append('<p>'+escape(record['question_note'])+'</p>')
    guidance = record.get('interpretation') or distribution_guidance(record)
    parts.append(guidance_html(record))
    next_step = guidance['next_step']
    count_plan = record.get('population_count_plan',{})
    query = (count_plan.get('plan') or {}).get('query')
    if query:
        span = (f'category {query["start_category"]}' if query['start_category'] == query['end_category'] else
                f'categories {query["start_category"]} through {query["end_category"]}, inclusive')
        next_step = (f'For the requested population precision, ask how many of these same {counted(n, "isolate")} lie in {span}. '
            'Add that count to this analysis.')
        parts.append(count_request_html(count_request(record, query['start_category'], query['end_category'])))
    elif count_plan.get('status') == 'no_guaranteed_plan':
        next_step = 'The permitted counts cannot guarantee this population precision for every possible answer. Review the precision target or the number of groups; the sample results remain valid.'
    elif count_plan.get('status') == 'numerically_unresolved':
        next_step = 'Count planning did not finish. No population-precision recommendation is confirmed; retain these results or rerun with a longer planning limit.'
    if not query:
        parts.append(count_request_html(guidance.get('count_request', '')))
    parts.append('<h4>What to do next</h4><p class="result-next">Next step: '+escape(next_step)+'</p></section>')
    parts.append('<details class="result-details"><summary>Source information and interpretation assumptions</summary>'+interpretation_context(record.get('provenance', {}))+'</details>')
    parts.append(evidence_html(record))
    comparison = record.get('sample_comparison', {})
    if comparison.get('status') == 'complete':
        parts.append('<details class="result-details"><summary>Compare before and after the added counts</summary><h4>Before these counts</h4>')
        parts.append(chart_block(comparison['before']['categories'], n))
        parts.append('<h4>After these counts</h4>'+chart_block(rows, n))
        parts.append('<p>Added information: '+escape(counts_description(comparison['added_counts']))+'. Same sample and assumptions; the chart scale is unchanged.</p></details>')
    explanation = record.get('count_explanation', {})
    if explanation.get('status') == 'complete' and explanation['stages']:
        parts.append('<details class="result-details result-steps"><summary>Show what each count adds</summary><p>This demonstrates using the available counts in entry order. The main result uses all supplied information.</p>')
        for stage in explanation['stages']:
            parts.append(f'<div><h4>After {counted(stage["count_rows"], "count row")}</h4><p>Added: '+escape(counts_description([stage['added_count']]))+'.</p>')
            parts.append(chart_block(stage['sample']['categories'], n))
            parts.append(decision_cards(stage['decisions'], n)+'</div>')
        parts.append('</details>')
    return ''.join(parts)


def counts_description(counts):
    from .count_updates import observation_label
    return '; '.join(f'{r.get("count", str(r.get("count_min"))+" to "+str(r.get("count_max")))} of {r["n"]} recorded results {observation_label(r)}' for r in counts)


def verification_overview(checked, disclosures, *, initial=None, provenance=None):
    n = checked['sample_size']
    bounds = checked['bounds']
    resolved = sum(row['status'] in ('supported', 'contradicted') for row in bounds)
    parts = ['<section class="result-overview"><h3>What can the reader conclude?</h3>',
             '<p class="result-context">'+context_text(provenance or {}, n)+'</p>',
             f'<h4>What we know</h4><p class="result-answer">{resolved} of {counted(len(bounds), "question")} {"is" if resolved == 1 else "are"} settled by the supplied report.</p>']
    if initial is not None:
        unresolved = sum(value == 'undetermined' for value in initial)
        parts.append(f'<div class="result-flow"><span>{counted(unresolved, "initially unresolved question")}</span><span>{counted(len(disclosures), "disclosed count field")}</span><span>{counted(resolved, "settled answer")}</span></div>')
    if disclosures:
        descriptions = []
        for row in disclosures:
            lo = row.get('count', row.get('count_min'))
            hi = row.get('count', row.get('count_max'))
            amount = (f'{row["percentage"]}% with declared rounding' if 'percentage' in row else
                      count_text([[lo, hi]])+' results')
            descriptions.append(f'{amount} with MIC {category_label(row.get("relation", ">"))} {row["threshold"]} mg/L')
        parts.append('<p>Disclosed: '+escape('; '.join(descriptions))+'.</p>')
    rows = [dict(label=f'MIC >{r["threshold"]:g}', count_lower=r['count_min'], count_upper=r['count_max'],
                 count_components=r.get('count_components', [[r['count_min'],r['count_max']]])) for r in bounds]
    parts.append(chart_block(rows, n, kind='threshold', title='Possible exceedance counts after disclosure'))
    for row in bounds:
        parts.append('<p>'+escape(STATUS_LABELS[row['status']])+': '+escape(criterion_text(row))+'.</p>')
    parts.append('<h4>What remains unknown</h4><p class="result-note">These answers follow for every histogram compatible with the supplied information. They assume truthful counts from this sample; they do not identify its full histogram or establish population prevalence.</p>')
    parts.append('<h4>What to do next</h4><p class="result-next">Next step: keep the summaries, questions and disclosed counts together so the recipient can check the conclusions. Retain the complete histogram when it is available.</p></section>')
    return ''.join(parts)+interpretation_context(provenance or {})


def threshold_overview(result, provenance=None):
    from .report import _sample_count_ranges
    n = result['sample_size']
    plan = result.get('reporting_plan', {})
    if plan.get('sufficient'):
        return verification_overview(plan['verification'], plan['disclosures'], initial=plan['initial_decisions'], provenance=provenance)+threshold_layer_cards(result)
    items = result.get('reporting_uncertainty_envelope', {}).get('envelope', result.get('identification', []))
    rows = []
    for item in items:
        components = _sample_count_ranges(result, item)
        rows.append(dict(label=f'MIC >{item["threshold"]:g}', count_lower=components[0][0],
                         count_upper=components[-1][1], count_components=components))
    decisions = []
    for decision in result.get('decision_results', []):
        row = next(item for item in items if item['threshold'] == decision['threshold'])
        decisions.append({**decision, 'sample':{**decision['sample'], 'count_components':_sample_count_ranges(result,row)}})
    parts = ['<section class="result-overview"><h3>What do these isolates show?</h3><p class="result-context">',
             context_text(provenance or {}, n), '</p><h4>What we know</h4><p class="result-answer">The chart shows how many observed isolates can exceed each requested concentration.</p>',
             decision_cards(decisions, n),
             chart_block(rows, n, kind='threshold', title='Possible exceedance counts in the observed sample'),
             '<h4>What remains unknown</h4><p class="result-note">These are sample bounds, not population confidence intervals. A range is missing information about existing observations, not an estimate of individual MIC values.</p>',
             '<h4>What to do next</h4><p class="result-next">Next step: read your requested criteria below, or add a relevant existing count if a sample range is too wide.</p></section>']
    return ''.join(parts)+interpretation_context(provenance or {})+threshold_layer_cards(result)


def threshold_layer_cards(result):
    """Expose optional-layer intent without assigning a new coverage claim."""
    from .report_status import threshold_layer_state, status_paragraph
    parts=['<div class="result-layers"><p><strong>What do these isolates show?</strong>Compatible sample counts, conditional on the supplied information.</p>']
    for key, title in [('population', 'What can we infer about the population?'),
                       ('calibration', 'What does calibration cover for a new study?')]:
        status, text = threshold_layer_state(result, key)
        parts.append(status_paragraph(status, text, title))
    return ''.join(parts)+'</div>'
