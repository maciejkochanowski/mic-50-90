"""Portable HTML explanation of the recorded MIC distribution and its uncertainty."""
from __future__ import annotations

from html import escape
from pathlib import Path
from .result_view import VIEW_STYLE, counted, distribution_overview
from .typography import html_with_typography, display_status
from .report_status import inference_status, status_paragraph
from .report_checks import population_checks


def _percent(value):
    return f"{100 * value:.2f}%"


def _explain_sampling(text):
    return text.replace("iid sampling", "independent sampling from the same population")


def _interval(row):
    if len(row.get("fraction_components", [])) > 1:
        return " or ".join(_percent(lo) if lo == hi else f"{_percent(lo)}–{_percent(hi)}"
                           for lo, hi in row["fraction_components"])
    lower = row.get("lower", row.get("fraction_lower"))
    upper = row.get("upper", row.get("fraction_upper"))
    return _percent(lower) if lower == upper else f"{_percent(lower)}–{_percent(upper)}"


def _band_chart(sample, population):
    rows = sample["cdf"]
    width, left, plot, top, height = 700, 75, 540, 35, 220
    x = lambda i: left + plot * i / max(1, len(rows) - 1)
    y = lambda value: top + height * (1 - value)
    svg = [f'<svg viewBox="0 0 {width} 330" role="img" aria-label="Cumulative recorded MIC distribution intervals">',
           '<title>Cumulative recorded MIC distribution: sample ranges and population confidence bounds</title>',
           '<rect width="700" height="330" fill="white"/>']
    for tick in (0, .25, .5, .75, 1):
        svg.append(f'<line x1="{left}" x2="{left+plot}" y1="{y(tick)}" y2="{y(tick)}" stroke="#e5e7eb"/>')
        svg.append(f'<text x="{left-9}" y="{y(tick)+4}" text-anchor="end" font-size="12">{100*tick:g}%</text>')
    pop = population.get("cdf", [])
    for i, row in enumerate(rows):
        if i < len(pop):
            p = pop[i]
            svg.append(f'<line x1="{x(i)}" x2="{x(i)}" y1="{y(p["lower"])}" y2="{y(p["upper"])}" stroke="#b9cbe4" stroke-width="16"><title>Population {_interval(p)}</title></line>')
        for low, high in row.get("fraction_components", [[row["fraction_lower"], row["fraction_upper"]]]):
            svg.append(f'<line x1="{x(i)}" x2="{x(i)}" y1="{y(low)}" y2="{y(high)}" stroke="#163a62" stroke-width="5"><title>Sample {_interval(row)}</title></line>')
            if low == high:
                svg.append(f'<circle cx="{x(i)}" cy="{y(low)}" r="4" fill="#163a62"/>')
        svg.append(f'<text x="{x(i)}" y="280" text-anchor="middle" font-size="12">{escape(row["label"])}</text>')
    svg.extend(['<text x="350" y="307" text-anchor="middle" font-size="12">Through the indicated recorded MIC category (mg/L)</text>', '</svg>'])
    return "".join(svg)


def _table(layer, quantity, *, sample=False):
    rows = layer.get(quantity, [])
    if not rows:
        return ""
    heading = "Recorded MIC category" if quantity == "categories" else "Cumulative through category"
    cells = [f'<table><thead><tr><th>{heading}</th><th>Percentage</th>' +
             ('<th>Admissible isolates</th>' if sample else '') + '</tr></thead><tbody>']
    for row in rows:
        counts = ""
        if sample:
            lo, hi = row["count_lower"], row["count_upper"]
            components = row.get("count_components", [[lo, hi]])
            text = " or ".join(str(lo) if lo == hi else f"{lo}–{hi}" for lo, hi in components)
            counts = f'<td>{text}</td>'
        cells.append(f'<tr><th>{escape(row["label"])}</th><td>{_interval(row)}</td>{counts}</tr>')
    cells.append('</tbody></table>')
    return "".join(cells)


def _layer(title, layer, sample=False, requested=True):
    result = [f'<section class="layer"><h3>{title}</h3>']
    status = inference_status(layer, requested=requested)
    if not requested:
        result.append(status_paragraph(status, 'This optional analysis was not selected. The sample results above remain valid under their stated inputs.'))
    elif layer["status"] == "unavailable":
        result.append(status_paragraph(status, _explain_sampling(layer["reason"])))
    else:
        result.append(status_paragraph(status, 'The returned outer bounds retain unresolved possibilities.' if status == 'incomplete' else 'Results are shown below with their interpretation.'))
        guarantee = _explain_sampling(layer.get("guarantee", "")).rstrip().rstrip(".")
        if guarantee:
            result.append(f'<p>{escape(guarantee)}.</p>')
        calibrated = layer.get("guarantee_class") == "conformal_new_cohort"
        if layer.get("confidence_level"):
            label = "Marginal calibration level" if calibrated else "Simultaneous confidence level"
            family_label = ('range comparisons' if layer.get('family_kind') == 'all_contiguous_ranges_up_to_complements'
                            else 'cumulative panel boundaries')
            result.append(f'<p>{label}: {_percent(layer["confidence_level"])}; '
                          f'{layer.get("family_size", "all")} {family_label} covered together.</p>')
        if calibrated:
            scope = {"declared_group_marginal": "new unit in the declared calibration group",
                     "global_marginal": "new unit from the pooled calibration population"}.get(
                         layer["guarantee_scope"], layer["guarantee_scope"])
            result.append(f'<p>Requested calibration level: {_percent(layer["requested_level"])}. '
                          f'Calibration units: {layer["calibration_units"]}. '
                          f'Unit definition: {escape(layer["calibration_unit_definition"])}.</p>')
            result.append(f'<p>Reference rule: {escape(layer["reference_rule"])}; '
                          f'applied radius: {layer["radius"]:.9g} log2 dilution steps. '
                          f'Guarantee scope: {escape(scope)}.</p>')
            if "normalized_radius" in layer:
                result.append(f'<p>Normalized calibration radius: {layer["normalized_radius"]:.9g}; '
                              f'fixed training scale: {layer["transport_scale"]:.9g}.</p>')
            result.append('<ul>' + ''.join(f'<li>{escape(item)}</li>' for item in layer["assumptions"]) + '</ul>')
            if layer.get("update_interpretation"):
                result.append(f'<p>{escape(layer["update_interpretation"])}</p>')
        if layer.get("method"):
            method = {"bonferroni": "Bonferroni simultaneous binomial bounds", "joint-exact": "Joint finite-sample calculation",
                      "range-calibrated": "Simultaneous bounds for all MIC ranges",
                      "range-hunter": "Joint refinement across MIC ranges",
                      "split-conformal": "Split-conformal calibration for a new study unit"}.get(layer["method"], layer["method"])
            result.append(f'<p>Method: {escape(method)}.</p>')
        if layer.get("requested_method") in ("joint-exact", "range-calibrated", "range-hunter"):
            if "baseline_seconds" in layer and "refinement_seconds" in layer:
                refinement_label = ('Optional joint refinement time' if layer['requested_method'] in ('joint-exact','range-hunter')
                                    else 'Optional compatible-count search time')
                result.append(f'<p>Baseline calculation time: {float(layer["baseline_seconds"]):.3f} s. '
                              f'{refinement_label}: {float(layer["refinement_seconds"]):.3f} s. '
                              'The cooperative time budget applies to optional refinement; total execution includes the baseline and reporting.</p>')
            tolerance = layer.get("numerical_tolerance_pp")
            if tolerance is not None:
                result.append(f'<p>Requested endpoint precision: {float(tolerance):g} percentage point.</p>')
            gap = layer.get("endpoint_gap_pp")
            if gap is not None:
                result.append(f'<p>Largest remaining certified endpoint gap: {float(gap):.4g} percentage points.</p>')
        if layer.get("reason"):
            result.append(f'<p class="notice">{escape(layer["reason"])}</p>')
        if layer.get("numerical_status"):
            result.append(f'<p>{escape(layer["numerical_status"])}</p>')
        if layer.get("previous_outer_bounds_preserved"):
            result.append('<p>The previous same-sample population bounds were retained and intersected with this update. '
                          'A shorter numerical search cannot widen the saved result.</p>')
        result.append('<h4>Share in each category</h4>' + _table(layer, "categories", sample=sample))
        result.append('<h4>Cumulative share</h4>' + _table(layer, "cdf", sample=sample))
        if not sample and not calibrated:
            result.append(population_checks(layer))
    result.append('</section>')
    return "".join(result)


def render_distribution_html(result, destination):
    """Write a self-contained, escaped report with a page size of 50 cohorts."""
    body = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>MIC-50-90 distribution report</title><style>', VIEW_STYLE,
        'body{font:16px/1.55 system-ui,sans-serif;color:#172b3e;background:#f4f6f8;margin:0}main{max-width:1100px;margin:auto;padding:24px}',
        'h1,h2,h3{line-height:1.25}article{background:white;padding:24px;margin:24px 0;border:1px solid #d5dde4;border-radius:8px}',
        '.layer{border-top:1px solid #d5dde4;padding-top:12px;margin-top:24px}table{border-collapse:collapse;width:100%;margin:12px 0}',
        'th,td{padding:9px;border-bottom:1px solid #e0e5e9;text-align:left}thead{background:#edf2f7}svg{display:block;max-width:850px;width:100%;margin:auto}',
        '.chart-scroll{overflow-x:auto;max-width:100%}.chart-scroll:focus{outline:2px solid #154e85}.mobile-chart-help{display:none}',
        '.notice,.unavailable{padding:12px;background:#fff4dc;border-left:4px solid #b77f14}a{color:#154e85}',
        '.metadata{overflow-wrap:anywhere}.metadata dt{font-weight:600}.metadata dd{margin:0 0 8px}',
        '.legend{font-size:14px;text-align:center}.pager{display:flex;gap:14px;align-items:center}button{font:inherit;padding:8px 14px}',
        '@media(max-width:600px){.chart-scroll svg{min-width:700px}.mobile-chart-help{display:block;font-size:14px}}',
        '@media print{.pager,.mobile-chart-help{display:none}.chart-scroll{overflow:visible}.chart-scroll svg{min-width:0}article[hidden]{display:block}}',
        '</style></head><body><main><h1>What does this report tell us about the MIC distribution?</h1>',
        f'<p>MIC-50-90 {escape(result["software_version"])}. Input and full numerical results are saved alongside this report.</p>',
        '<p>Start with the sample answer and graph. Open the details for cumulative results, assumptions and other kinds of inference.</p>',
        '<p><a href="distribution.csv">Distribution table</a> · <a href="results.json">Full numerical results</a> · '
        '<a href="configuration.json">Input and settings</a></p>']
    if len(result["cohorts"]) > 50:
        body.append('<nav class="pager" aria-label="Cohort pages"><button id="previous">Previous</button><span id="page"></span><button id="next">Next</button></nav>')
    for record in result["cohorts"]:
        body.append(f'<article><h2>{escape(str(record["cohort_id"]))}</h2>')
        labels = {"organism": "Organism", "antimicrobial": "Antimicrobial", "source": "Source",
                  "source_doi": "Source DOI", "source_location": "Source location", "metadata_basis": "Metadata basis",
                  "rank_basis": "Rank convention basis", "panel_basis": "Panel basis", "panel_id": "Panel identifier"}
        metadata = [(labels[key], value) for key, value in record.get("provenance", {}).items() if key in labels]
        if metadata:
            body.append('<details><summary>Sample context and source</summary><dl class="metadata" aria-label="Sample context and source">' + ''.join(
                f'<dt>{label}</dt><dd>{escape(str(value))}</dd>' for label, value in metadata) + '</dl></details>')
        if record["status"] != "ok":
            body.append(f'<p class="unavailable"><strong>Analysis refused.</strong> {escape(record["reason"])}. Correct the input and run the analysis again.</p></article>')
            continue
        body.append(distribution_overview(record))
        requested = record.get('inference_requested', {})
        body.append('<div class="result-layers"><p><strong>What do these isolates show?</strong>Sample bounds, conditional on the supplied information.</p>')
        for key, title in [('population', 'What can we infer about the population?'), ('calibration', 'What does calibration cover for a new study?')]:
            layer = record[key]
            status = inference_status(layer, requested=requested.get(key, True))
            text = ('The sample analysis does not require this layer.' if status == 'not_requested' else
                    _explain_sampling(layer.get('reason', 'Required information is missing.')) if status == 'unavailable' else
                    f'{100*layer["confidence_level"]:g}% ' + ('simultaneous confidence under independent sampling from the same population on a fixed panel.' if key == 'population' else 'calibration level for a new compatible study unit; exchangeability is required.'))
            body.append(status_paragraph(status, text, title))
        body.append('</div><details class="result-details"><summary>Detailed results, cumulative distribution and assumptions</summary>')
        body.append(f'<p><strong>Question:</strong> What proportions occupy the recorded MIC categories, and what is their uncertainty?</p><p><strong>Denominator:</strong> {counted(record["n"], "isolate")}. <strong>MIC unit:</strong> mg/L.</p>')
        if record.get("decisions"):
            from .result_view import criterion_text
            body.append('<section><h3>Questions about MIC groups</h3><p><a href="decisions.csv">Download decisions</a></p>')
            for decision in record["decisions"]:
                question = criterion_text(decision)
                body.append('<h4>' + escape(question) + '</h4>')
                for name in ("sample", "population", "calibration"):
                    layer = decision[name]
                    body.append('<p><strong>' + escape(name.title()) + ': ' + escape(display_status(layer, requested=requested.get(name, True))) + '</strong>. ' + escape(layer.get('guarantee', layer.get('reason',''))) + '</p>')
                    if layer.get('interpretation'):
                        body.append('<p>'+escape(layer['interpretation'])+'</p>')
                    if 'lower' in layer and 'upper' in layer:
                        body.append(f'<p>Possible share: {100*layer["lower"]:.2f}–{100*layer["upper"]:.2f}%.</p>')
            body.append('</section>')
        for variant in record.get("reported_summaries", []):
            declarations = []
            for quantile in variant["summaries"].get("quantiles", []):
                rank = ("rank " + str(quantile["rank"])) if "rank" in quantile else ("convention " + quantile["convention"])
                declarations.append(f'MIC{100 * float(quantile["probability"]):g} = {quantile["category"]} mg/L ({rank})')
            for name in ("minimum", "maximum"):
                if variant["summaries"].get(name) is not None:
                    declarations.append(f'observed {name}: {variant["summaries"][name]} mg/L')
            if declarations:
                body.append(f'<p><strong>Declared summaries ({escape(variant["id"])}):</strong> ' + escape("; ".join(declarations)) + '.</p>')
        body.append('<div class="chart-scroll" tabindex="0" role="region" aria-label="Cumulative distribution chart; scroll horizontally on a narrow screen">' +
                    _band_chart(record["sample"], record["population"]) + '</div>')
        body.append('<p class="mobile-chart-help">Scroll the chart sideways to read all category labels. The same numerical ranges are listed in the tables below.</p>')
        body.append('<p class="legend">Dark marks: possible sample proportions. Pale bars, when available: simultaneous population bounds. '
                    'Separate endpoints must still satisfy the original constraints together.</p>')
        body.append(_layer("Sample distribution", record["sample"], sample=True))
        population_resolution = record.get('population_resolution', {'status':'not_requested'})
        if population_resolution['status'] != 'not_requested':
            body.append('<section class="layer"><h3>Population precision requested</h3>')
            if population_resolution['status'] == 'unavailable':
                body.append('<p>'+escape(population_resolution['reason'])+'</p>')
            else:
                pr = population_resolution
                body.append(f'<p>At {100*pr["confidence_level"]:g}% simultaneous confidence, each group and retained cumulative boundary must have an interval at most {pr["precision_pp"]:g} percentage points wide.</p>')
                confirmed = pr["guaranteed_number_of_bins"]
                body.append(f'<p><strong>{counted(confirmed, "group")} {"is" if confirmed == 1 else "are"} confirmed.</strong> The possible maximum is {pr["possible_number_of_bins"]}. '+
                    ('The maximum number is verified.' if pr['maximum_number_verified'] else 'Further numerical refinement is needed to establish the maximum.')+'</p>')
                body.append('<p>'+escape(pr['interpretation'])+'</p>')
                if pr['bins']:
                    body.append(_table({'categories':pr['bins']},'categories'))
                else:
                    body.append('<p>No partition meeting your required boundaries is confirmed. This does not establish that more original-sample counts would be insufficient.</p>')
                body.append('<p>Next step: retain this grouping, or add a count for a group that matters to your question and repeat the same analysis.</p>')
            body.append('</section>')
        plan = record.get('population_count_plan', {'status':'not_requested'})
        if plan['status'] != 'not_requested':
            body.append('<section class="layer"><h3>Which existing count would help?</h3>')
            messages = {'achieved':'The requested groups already meet the precision target.',
                'achievable_with_counts':'A sufficient sequence of additional counts was found.',
                'no_guaranteed_plan':'No plan guarantees the target for every possible answer under the selected method and allowed questions.',
                'numerically_unresolved':'The search did not establish a sufficient plan or impossibility.',
                'unavailable':plan.get('reason','The optional planning calculation is unavailable.')}
            body.append('<p>'+escape(messages[plan['status']])+'</p>')
            if plan.get('plan') and not plan['plan'].get('goal_reached'):
                q=plan['plan']['query']
                span = ('category '+escape(q['start_category'])+' mg/L' if q['start_category'] == q['end_category'] else
                        'categories '+escape(q['start_category'])+' through '+escape(q['end_category'])+' mg/L, including both endpoints')
                body.append('<p><strong>Next count to request:</strong> How many of these same '+counted(record['n'], 'isolate')+' are in '+span+'?</p>')
                body.append('<p>Worst-case cost of the sufficient plan: '+escape(plan['cost_upper'])+'. '+('Minimum cost verified.' if plan['optimality_verified'] else 'Minimum cost is not verified.')+'</p>')
            if plan.get('full_counts_failure_witness'):
                body.append('<p>A compatible complete histogram fails the goal. This proves that success cannot be guaranteed for every possible answer; it does not mean all compatible histograms fail.</p>')
            body.append('</section>')
        resolution = record.get("resolution", {"status": "not_requested"})
        if resolution["status"] == "complete":
            body.append('<section class="layer"><h3>Most detailed sample description</h3>')
            precision_text = escape(resolution.get("precision_pp_decimal", f'{resolution["precision_pp"]:g}'))
            body.append(f'<p>Required width: at most {precision_text} {"percentage point" if float(precision_text) == 1 else "percentage points"} for both each category share and each retained cumulative boundary. '
                        f'The information supports {counted(resolution["number_of_bins"], "contiguous bin")} from {resolution["original_number_of_categories"]} recorded categories.</p>')
            body.append(_table({"categories": resolution["bins"]}, "categories", sample=True))
            body.append('<p>This is the largest number of bins meeting your stated width requirement. '
                        'It describes uncertainty about the observed sample, not population confidence. '
                        'The full category results remain above.</p></section>')
        elif resolution["status"] == "unavailable":
            body.append(f'<section class="layer"><h3>Most detailed sample description</h3><p class="unavailable">{escape(resolution["reason"])}</p></section>')
        body.append(_layer("Population distribution", record["population"], requested=requested.get('population', True)))
        body.append(_layer("Calibration for a new study unit", record["calibration"], requested=requested.get('calibration', True)))
        body.append('<section class="layer"><h3>How to interpret these ranges</h3><ul>')
        body.extend(f'<li>{escape(_explain_sampling(item))}</li>' for item in record["assumptions"])
        body.append('</ul><p>A full category histogram still does not reveal the exact MIC concentration inside a censored or interval category.</p>')
        if all(row["count_lower"] == row["count_upper"] for row in record["sample"]["categories"]):
            body.append('<p><strong>Next step:</strong> All category counts are determined. Additional counts for these same categories cannot improve the sample description. '
                        'Remaining population uncertainty concerns sampling; it is not missing category information.</p>')
        else:
            body.append('<p><strong>Next step:</strong> If a range is too wide for your question, obtain a count from the same original sample at a relevant panel boundary. '
                        'Add that count to the input, retaining earlier counts, and run the analysis again. No new isolates are implied.</p>')
        if record["additional_counts"]:
            body.append('<h4>Additional information used</h4><ul>')
            for observation in record["additional_counts"]:
                lo = observation.get("count", observation.get("count_min"))
                hi = observation.get("count", observation.get("count_max"))
                text = str(lo) if lo == hi else f'{lo}–{hi}'
                source = observation.get("source") or "source not supplied"
                from .count_updates import observation_label
                body.append(f'<li>{text}/{record["n"]} recorded results {escape(observation_label(observation))}. '
                            f'Source: {escape(source)}.</li>')
            body.append('</ul>')
        body.append('<p>Retained reporting variants: ' + escape(", ".join(record["retained_variants"])) + '.</p>')
        if record["rejected_variants"]:
            body.append('<h4>Incompatible reporting variants</h4><ul>')
            body.extend(f'<li>{escape(row["id"])}: {escape(row["reason"])}</li>' for row in record["rejected_variants"])
            body.append('</ul>')
        body.append('</section></details></article>')
    if len(result["cohorts"]) > 50:
        body.append('''<script>(()=>{const rows=[...document.querySelectorAll('article')];let page=0;const pages=Math.ceil(rows.length/50);
function render(){rows.forEach((r,i)=>r.hidden=Math.floor(i/50)!==page);document.getElementById('page').textContent=`Page ${page+1} of ${pages}`;
document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=page===pages-1;}
document.getElementById('previous').onclick=()=>{page--;render();};document.getElementById('next').onclick=()=>{page++;render();};render();})();</script>''')
    body.append('</main></body></html>')
    Path(destination).write_text(html_with_typography("".join(body)), encoding="utf-8")
