"""Dependency-free, publication-oriented HTML result report."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .decision_report import render_decision_plan, _criterion_percent
from .exact_population import _merge_integer_ranges
from .result_view import VIEW_STYLE, threshold_overview
from .typography import html_with_typography
from .report_status import threshold_layer_state, status_paragraph


STYLE = """
body{font-family:Inter,Arial,sans-serif;margin:0;background:#f5f7fa;color:#172033;line-height:1.5}
main{max-width:1050px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:2.1rem;margin:.1rem 0}.subtitle{color:#536079;margin:0 0 28px}
h2{margin-top:32px;border-bottom:1px solid #d9e0ea;padding-bottom:7px;overflow-wrap:anywhere}
.card{background:white;border:1px solid #dce3ec;border-radius:10px;padding:18px 20px;margin:14px 0;box-shadow:0 2px 10px #1720330b}
.callout{border-left:5px solid #1e6b5c;background:#eef8f5}.warning{border-left-color:#b26a00;background:#fff7e8}
table{width:100%;border-collapse:collapse;font-size:.94rem}th,td{padding:9px 10px;border-bottom:1px solid #e5e9ef;text-align:left}th{background:#f3f6f9}
.table-scroll{max-width:100%;overflow-x:auto}td{overflow-wrap:anywhere}
.bar{height:12px;background:#e8edf3;border-radius:8px;position:relative;margin:8px 0}.interval{position:absolute;height:12px;background:#247a6b;border-radius:8px}.mono{font-family:ui-monospace,Consolas,monospace;font-size:.85rem;white-space:pre-wrap;overflow-wrap:anywhere}
.tag{display:inline-block;padding:3px 8px;border-radius:20px;background:#e5eefb;color:#184d88;font-size:.78rem;margin-right:5px}
.layers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.layers section{background:#f3f6f9;padding:14px;border-radius:8px}.layers h3{margin-top:0}
.interval-chart{width:100%;height:auto;min-width:620px}.supported{color:#185b4e}.undetermined{color:#825000}.contradicted{color:#933d30}
@media(max-width:760px){.layers{grid-template-columns:1fr}main{padding:20px 12px}}@media print{body{background:white}.card{box-shadow:none;break-inside:auto}details{display:block}.table-scroll{overflow:visible}main{max-width:none;padding:0}h2,h3{break-after:avoid}tr{break-inside:avoid}}
"""


def _fmt(value: Any) -> str:
    if value is None:
        return "not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return "; ".join(html.escape(str(k))+": "+_fmt(v) for k,v in value.items())
    if isinstance(value, (list, tuple)):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return html.escape(str(value))


def _pct(value):
    return "not available" if value is None else f"{100*float(value):.2f}%"


def _table(headers, rows):
    return ('<div class="table-scroll"><table><thead><tr>' + "".join("<th>"+html.escape(str(x))+"</th>" for x in headers)
            + "</tr></thead><tbody>" + "".join("<tr>"+"".join("<td>"+str(x)+"</td>" for x in row)+"</tr>" for row in rows)
            + "</tbody></table></div>")


def _range(interval):
    return "not available" if interval is None else f"{_pct(interval[0])} to {_pct(interval[1])}"


def _sample_count_ranges(result, item, estimand='panel_recorded_estimand'):
    """Union of variant-specific integer ranges; do not fill excluded gaps."""
    variants = result.get('reporting_uncertainty_envelope', {}).get('per_variant', [])
    values = [row[estimand] for variant in variants for row in variant['identification']
              if row['threshold'] == item['threshold']]
    if not values:
        values = [item[estimand]]
    return _merge_integer_ranges([(value['lower']['count'], value['upper']['count'])
                                  for value in values])


def _count_set_text(ranges, n):
    return ' union '.join(f'{lo}/{n}' if lo == hi else f'{lo}/{n} to {hi}/{n}'
                          for lo, hi in ranges)


def _sample_percent_text(ranges, n):
    return ' union '.join(_pct(lo/n) if lo == hi else _range([lo/n, hi/n])
                          for lo, hi in ranges)


def _diagnostics(envelope):
    variants = envelope.get("per_variant", [])
    parts = ["<details><summary>Per-variant bounds and numerical checks</summary>"]
    bounds, certificates, witnesses = [], [], []
    for variant in variants:
        for item in variant["identification"]:
            p, latent = item["panel_recorded_estimand"], item["latent_interval_estimand"]
            label = html.escape(variant["id"])
            bounds.append([label, _fmt(item["threshold"]),
                           f"{p['lower']['count']} to {p['upper']['count']}",
                           _range([latent['lower']['fraction'],latent['upper']['fraction']]),
                           _fmt(item.get("closed_form_panel_bound_verified"))])
            for estimand, values in (("Recorded",p),("Latent",latent)):
                for side in ("lower","upper"):
                    endpoint = values[side]
                    c = endpoint["certificate"]
                    certificates.append([label,_fmt(item["threshold"]),estimand+" "+side,
                                         _fmt(c["solver"]),_fmt(c["optimality_verified"]),
                                         _fmt(c["duality_gap"]),_fmt(c["max_primal_violation"]),
                                         _fmt(c["fallback_used"])])
                    nonzero = "; ".join(str(k)+": "+str(v) for k,v in endpoint["compatible_histogram"].items() if v)
                    witnesses.append([label,_fmt(item["threshold"]),estimand+" "+side,html.escape(nonzero)])
    parts += [_table(["Variant","Threshold","Recorded counts","Latent fraction","Closed-form agreement"],bounds),
              "<h3>Solver certificates</h3><p>Optimization checks establish extrema of the declared model. They do not validate the input measurements or sampling assumptions. Unrounded certificates and dual multipliers are in the JSON output.</p>",
              _table(["Variant","Threshold","Endpoint","Solver","Optimality verified","Duality gap","Constraint violation","Fallback"],certificates),
              "<h3>Compatible histogram witnesses</h3><p>Nonzero category counts in a mathematical witness for each endpoint. These are not reconstructed observations.</p>",
              _table(["Variant","Threshold","Endpoint","Compatible histogram"],witnesses),"</details>"]
    return "".join(parts) if variants else ""


def _optional_population(population):
    parts = ["<details><summary>Optional population sensitivity analyses</summary>",
             "<p>These calculations concern the explicitly selected reporting variant. Profile likelihood uses an asymptotic calibration; Bayesian results depend on the displayed prior. Neither replaces the exact iid confidence set over all variants.</p>"]
    mle = population.get("population_mle")
    if mle:
        parts.append("<p>Optional MLE: optimizer success="+_fmt(mle["success"])+
                     "; log likelihood="+_fmt(mle["log_likelihood"])+"; evaluations="+
                     _fmt(mle["evaluations"])+"; message="+_fmt(mle["message"])+".</p>")
        parts.append(_table(["Category","MLE probability"],[[html.escape(k),_pct(v)] for k,v in mle["probabilities"].items()]))
    for item in population["threshold_results"]:
        efficiency = item.get("optional_efficiency_analysis", {})
        bayes = item.get("bayesian_sensitivity", {})
        parts.append("<h3>Threshold "+_fmt(item["threshold"])+" mg/L</h3>")
        if efficiency.get("enabled") and efficiency.get("available",True):
            profile = efficiency.get("profile_likelihood",{})
            parts.append("<p>Optional MLE tail="+_pct(efficiency.get("population_tail_mle"))+
                         "; reporting variant="+_fmt(efficiency.get("reporting_variant"))+
                         "; Optional profile set="+_range(profile.get("confidence_set"))+".</p>")
            parts.append("<p>"+_fmt(profile.get("calibration"))+"; confidence="+
                         _pct(profile.get("confidence_level"))+"; likelihood-ratio cutoff="+_fmt(profile.get("chi_square_1_cutoff"))+
                         "; adaptive refinements="+_fmt(profile.get("adaptive_refinement_rounds"))+
                         "; boundary or weak identification warning="+_fmt(profile.get("boundary_or_weak_identification_warning"))+".</p>")
            grid = zip(profile.get("theta_grid",[]),profile.get("profile_log_likelihood",[]),profile.get("likelihood_ratio",[]))
            parts.append(_table(["Tail probability grid","Log likelihood","Likelihood ratio"],
                                [[_pct(t),_fmt(l),_fmt(r)] for t,l,r in grid]))
            for warning in profile.get("warnings",[]):
                parts.append("<p class='warning'>"+html.escape(warning)+"</p>")
        else:
            parts.append("<p>Optional MLE / profile analysis: "+html.escape(efficiency.get("reason","disabled"))+".</p>")
        if bayes.get("enabled") and bayes.get("available",True):
            posterior, prior = bayes["posterior_tail"], bayes["prior_tail"]
            parts.append(_table(["Bayesian quantity","Value"],[
                ["Reporting variant",_fmt(bayes.get("reporting_variant"))],
                ["Prior alpha",_fmt(bayes["prior_alpha"])],
                ["Prior tail mean",_pct(prior["mean"])],
                ["Prior equal-tail interval",_range(prior["equal_tail_interval"])],
                ["Posterior mean",_pct(posterior["mean"])],
                ["Posterior median",_pct(posterior["median"])],
                ["Optional Dirichlet posterior interval",_range(posterior["equal_tail_interval"])],
                ["Monte Carlo standard error of mean",_pct(posterior["mcse_of_mean"])],
                ["Draws",_fmt(bayes["draws"])],
                ["Effective sample size",_fmt(bayes["effective_sample_size"])],
                ["Prior predictive log probability",_fmt(bayes.get("prior_predictive_log_probability_of_reported_event"))]]))
            for warning in bayes.get("warnings",[]):
                parts.append("<p class='warning'>"+html.escape(warning)+"</p>")
        else:
            parts.append("<p>Optional Dirichlet posterior: "+html.escape(bayes.get("reason","disabled"))+".</p>")
    return "".join(parts)+"</details>"


def _scenarios(result):
    scenarios = result.get("assumption_dependent_scenarios",{})
    if not scenarios:
        return ""
    parts = ["<details><summary>Assumption-dependent scenarios</summary><p>These are illustrative calculations under additional assumptions. Point values are not uniquely identified data and carry no frequentist coverage guarantee.</p>"]
    for name,label in (("maximum_entropy","Maximum entropy"),("kl_reference_projection","KL reference projection")):
        scenario=scenarios.get(name)
        if scenario is None:
            continue
        parts.append("<h3>"+label+"</h3>")
        if not scenario.get("available",True):
            parts.append("<p>Unavailable: "+_fmt(scenario.get("conflict"))+".</p>")
            continue
        parts.append("<p>Reporting variant="+_fmt(scenario.get("reporting_variant"))+
                     "; objective="+_fmt(scenario["objective"])+"; optimizer success="+_fmt(scenario["success"])+".</p>")
        parts.append("<p>"+_fmt(scenario["message"])+"</p>")
        parts.append(_table(["Threshold","Scenario tail fraction"],[[html.escape(k),_pct(v)] for k,v in scenario["tail_estimates"].items()]))
        parts.append(_table(["Category","Scenario probability"],[[html.escape(k),_pct(v)] for k,v in scenario["probabilities"].items()]))
    conf=scenarios.get("wasserstein_ambiguity_set")
    if conf and conf.get("guarantee_class")=="assumption_scenario":
        parts.append("<h3>Uncalibrated Wasserstein scenario</h3><p>User-specified radius="+_fmt(conf["radius"])+". No calibrated coverage is claimed.</p>")
        rows=[]
        for x in conf["threshold_results"]:
            e=x.get("envelope")
            rows.append([_fmt(x["threshold"]),_range(None if e is None else [e["lower"],e["upper"]])])
        parts.append(_table(["Threshold","Assumed-radius interval"],rows))
    return "".join(parts)+"</details>"


def _interval_chart(result):
    """Plot complete confidence components, retaining unavailable layers and gaps."""
    rows = []
    pop = result.get('population_layer', {})
    if result.get('mode') == 'population':
        pop = result
    conf = result.get('assumption_dependent_scenarios', {}).get('wasserstein_ambiguity_set', {})
    calibrated = conf.get('guarantee_class') == 'conformal_new_cohort'
    sharp = result.get('reporting_uncertainty_envelope', {}).get('envelope', result.get('identification', []))
    for i, item in enumerate(sharp):
        label = f"> {item['threshold']:g} mg/L"
        sample = [[lo/result['sample_size'], hi/result['sample_size']]
                  for lo, hi in _sample_count_ranges(result, item)]
        rows.append((label+' | sample', sample, '#26776B'))
        intervals = []
        population_item = next((x for x in pop.get('threshold_results', []) if x['threshold'] == item['threshold']), None)
        if population_item:
            exact = population_item['exact_count_confidence']
            intervals = (exact.get('simultaneous_bonferroni') or exact['marginal'])['confidence_set_components']
        rows.append((label+' | iid population', intervals, '#286090'))
        conformal_item = next((x for x in conf.get('threshold_results', []) if x['threshold'] == item['threshold']), None)
        envelope = conformal_item.get('envelope') if calibrated and conformal_item else None
        rows.append((label+' | new cohort', [] if envelope is None else [[envelope['lower'], envelope['upper']]], '#8B5797'))
    row_heights = [max(30, 18*len(intervals)+12) for _, intervals, _ in rows]
    height = 75+sum(row_heights)
    svg = [f'<div class="table-scroll"><svg class="interval-chart" viewBox="0 0 960 {height}" role="img" aria-label="Recorded-tail intervals for three distinct inference layers">',
           '<title>Intervals for recorded values above each MIC threshold. Unavailable is not zero.</title>']
    for tick in (0, .25, .5, .75, 1):
        x = 280+440*tick
        svg.append(f'<line x1="{x}" x2="{x}" y1="25" y2="{height-35}" stroke="#dce3ec"/><text x="{x}" y="17" text-anchor="middle" font-size="13">{100*tick:g}%</text>')
    y = 43
    for (label, intervals, color), row_height in zip(rows, row_heights):
        svg.append(f'<text x="4" y="{y+4}" font-size="13">{html.escape(label)}</text>')
        for lo, hi in intervals:
            x1, x2 = 280+440*lo, 280+440*hi
            svg.append(f'<line x1="{x1}" x2="{x2}" y1="{y}" y2="{y}" stroke="{color}" stroke-width="7"/><circle cx="{x1}" cy="{y}" r="3.5" fill="{color}"/><circle cx="{x2}" cy="{y}" r="3.5" fill="{color}"/>')
        texts = ['not available'] if not intervals else [_range(pair) for pair in intervals]
        for index, text in enumerate(texts):
            prefix = '\u222a ' if index else ''
            svg.append(f'<text x="740" y="{y+4+18*index}" font-size="12">{html.escape(prefix+text)}</text>')
        y += row_height
    svg.append(f'<text x="280" y="{height-5}" font-size="12">Different questions and guarantees; these are not interchangeable estimates.</text></svg></div>')
    return ''.join(svg)


def _question_summary(result):
    parts = ['<h2>Your questions</h2>', f'<p>Observed denominator: {result["sample_size"]} isolates. Each threshold asks about recorded panel values strictly above that concentration.</p>']
    update_unavailable = result.get('additional_information', {}).get('status') == 'unavailable'
    if update_unavailable:
        parts.append('<p class="warning"><strong>The supplied additional counts could not be applied.</strong> '
                     'The results and hypothetical examples below use the original summaries only. '
                     'They do not incorporate the additional answers. Check the returned-count explanation below before using them.</p>')
    for decision in result.get('decision_results', []):
        index = next(i for i, row in enumerate(result['reporting_uncertainty_envelope']['envelope'])
                     if row['threshold'] == decision['threshold'])
        item = result['reporting_uncertainty_envelope']['envelope'][index]
        question = (f"Is the recorded fraction above {decision['threshold']:g} mg/L "
                    f"{decision['decision_operator']} {_criterion_percent(decision)}?")
        parts.append('<h3>'+html.escape(question)+'</h3><div class="layers">')
        for key, title in (('sample','This sample'), ('population','The population sampled'), ('conformal','A new group of isolates')):
            layer = decision[key]
            status = layer['status']
            meaning = {'supported':'Yes: every compatible percentage meets this criterion', 'contradicted':'No: every compatible percentage fails this criterion',
                       'undetermined':'More information is needed to answer', 'unavailable':'No result is available for this question'}[status]
            explanation = layer.get('guarantee', layer.get('reason', ''))
            if key == 'sample':
                explanation = 'The union of count ranges allowed by the supplied reporting interpretations. Gaps remain excluded. This result describes the isolates in this sample.'
            elif key == 'population' and 'iid sampling was not declared' in explanation:
                explanation = 'This result requires independent observations from the same population. That sampling assumption has not been declared.'
            parts.append(f'<section><h3>{title}</h3><p class="{status}"><strong>{meaning}</strong></p>')
            if key == 'sample':
                ranges = _sample_count_ranges(result, item)
                parts.append('<p><strong>'+_count_set_text(ranges, result['sample_size'])+' isolates</strong><br>'
                             +_sample_percent_text(ranges, result['sample_size'])+'</p>')
            elif status != 'unavailable' and key == 'population':
                exact = result['population_layer']['threshold_results'][index]['exact_count_confidence']
                confidence = exact.get('simultaneous_bonferroni') or exact['marginal']
                parts.append('<p>'+ ' ∪ '.join(_range(pair) for pair in confidence['confidence_set_components'])+'</p>')
            elif status != 'unavailable' and key == 'conformal':
                band = result['assumption_dependent_scenarios']['wasserstein_ambiguity_set']['threshold_results'][index]['envelope']
                parts.append('<p>'+_range([band['lower'], band['upper']])+'</p>')
            parts.append('<p>'+html.escape(explanation)+'</p>')
            if 'confidence_level' in layer:
                parts.append('<p>Level: '+_pct(layer['confidence_level'])+'. '+html.escape(layer.get('multiplicity',layer.get('scope','')))+ '</p>')
            parts.append('</section>')
        parts.append('</div>')
        examples = decision['sample'].get('compatible_examples', [])
        if examples:
            basis = ('the original summaries only' if update_unavailable else
                     'the supplied summaries and additional counts' if result.get('additional_information', {}).get('status') == 'applied'
                     else 'the supplied summaries')
            parts.append('<h3>Two possible samples</h3><p>Both examples agree with '+basis+
                         ', but they give opposite answers. These are hypothetical '
                         'examples, not observed or reconstructed isolate data.</p>')
            labels = [b['label'] for b in result['panel']['categories']]
            rows = [[html.escape(label), str(examples[0]['histogram'][label]), str(examples[1]['histogram'][label])]
                    for label in labels]
            rows += [['Count above this threshold', *[str(e['count'])+' / '+str(result['sample_size']) for e in examples]],
                     ['Does the criterion hold?', *['Yes' if e['criterion_satisfied'] else 'No' for e in examples]],
                     ['Declared reporting variant', *[html.escape(e['reporting_variant']) for e in examples]]]
            parts.append(_table(['Recorded MIC category (mg/L)', 'Possible sample A', 'Possible sample B'], rows))
            parts.append('<p>Next step: obtain the count of isolates strictly above '+_fmt(decision['threshold'])+
                         ' mg/L in the same sample, or use the request plan below if one is available.</p>')
    if not result.get('decision_results'):
        parts.append('<p>No fraction criterion was supplied. The intervals below show what each available layer can establish. Optionally add decision_operator and decision_fraction to targets.csv, for example &lt; and 0.05 for a fraction below 5%.</p>')
    parts.append(_interval_chart(result))
    return ''.join(parts)


def result_sections(result, provenance=None):
    n = result["sample_size"]
    envelope = result.get("reporting_uncertainty_envelope", {})
    sharp = envelope.get("envelope", result.get("identification", []))
    rows = []
    for item in sharp:
        recorded = _sample_count_ranges(result, item)
        latent = _sample_count_ranges(result, item, 'latent_interval_estimand')
        rows.append([_fmt(item["threshold"]),
                     _sample_percent_text(recorded, n), _count_set_text(recorded, n),
                     _sample_percent_text(latent, n)])
    parts = ['<h2>What is being analysed?</h2><p>'+str(n)+' isolates; concentrations in mg/L. Recorded categories: '+
             html.escape(', '.join(b['label'] for b in result['panel']['categories']))+'.</p>']
    if provenance:
        parts.append(_table(['Source and sample', 'Information supplied'],
            [[html.escape(k.replace('_',' ').capitalize()),_fmt(v)] for k,v in provenance.items()]))
    parts += [_question_summary(result), render_decision_plan(result), _returned_counts(result), f"<h2>Finite sample</h2><p>Denominator: {n} observed isolates. These are unions of ranges compatible with the declared reporting variants; gaps are excluded. Counts are integers, and sample percentages change in steps of 100/{n} percentage points. They describe this sample only.</p>",
             _table(["Threshold (mg/L)","Recorded-panel fraction","Admissible counts","Latent MIC fraction"],rows),
             "<p>Latent bounds retain uncertainty inside interval and censored categories. Compatible histograms are witnesses, not reconstructed observations.</p>"]
    variants = envelope.get("per_variant", [])
    summary_rows = []
    for variant in variants:
        summary = variant.get("declared_summary", {})
        text = "; ".join(
            f"q={q['probability'] if isinstance(q['probability'], str) else format(q['probability'], 'g')}, "
            f"rank={q['rank']}, category={q['category']}"
            for q in summary.get("quantiles", []))
        text += f"; minimum={summary.get('minimum') or 'not reported'}; maximum={summary.get('maximum') or 'not reported'}"
        summary_rows.append([html.escape(variant["id"]),html.escape(text)])
    if summary_rows:
        parts += ["<h3>Declared reporting assumptions</h3><p>The displayed bounds span their union; no probabilities or preferred convention are assigned.</p>",_table(["Variant","Summary and ranks"],summary_rows)]
    for rejected in envelope.get("rejected_variants",[]):
        parts.append("<p class='warning'>Rejected variant "+html.escape(str(rejected))+"</p>")
    parts.append(_diagnostics(envelope))
    panel_rows = [[html.escape(b["label"]),_fmt(b.get("lower_bound")) if b.get("lower_bound") is not None else 'unbounded',
                   _fmt(b.get("upper_bound")) if b.get("upper_bound") is not None else 'unbounded',_fmt(b.get("lower_closed")),
                   _fmt(b.get("upper_closed")),_fmt(b["panel_value"])]
                  for b in result["panel"]["categories"]]
    parts += ["<details><summary>Declared panel geometry (mg/L)</summary>",
              _table(["Category","Lower","Upper","Lower included","Upper included","Recorded representative"],panel_rows),"</details>"]
    parts.append("<h2>Exact iid population</h2>")
    parts.append(status_paragraph(*threshold_layer_state(result, "population")))
    population = result if result.get("mode")=="population" else result.get("population_layer")
    if population:
        rows = []
        for item in population["threshold_results"]:
            confidence = item["exact_count_confidence"]
            exact = confidence.get("simultaneous_bonferroni") or confidence["marginal"]
            marginal_components = confidence['marginal']['confidence_set_components']
            family_components = exact['confidence_set_components']
            rows.append([_fmt(item["threshold"]),' ∪ '.join(_range(x) for x in marginal_components),
                         ' ∪ '.join(_range(x) for x in family_components),
                         _pct(confidence["marginal"]["confidence_level"]),
                         "Bonferroni family" if confidence.get("simultaneous_bonferroni") else "marginal"])
        parts += ["<p>Source-population probability for recorded categories under iid sampling. Exact binomial intervals are united over admissible counts. The union symbol ∪ retains any excluded gaps; these are confidence sets, not sample fractions.</p>",
                  _table(["Threshold","Exact iid confidence set (marginal)","Confidence set for requested family","Requested confidence","Multiplicity"],rows)]
        if any((row['exact_count_confidence'].get('simultaneous_bonferroni') or {}).get('confidence_level_is_rounded')
               for row in population['threshold_results']):
            parts.append('<p>The adjusted per-threshold confidence is extremely close to 100%. '
                'Calculations retain its exact value; results.json records confidence_level_exact '
                'alongside the rounded display value. This is not a 100% confidence claim.</p>')
        parts.append(_optional_population(population))
    parts.append("<h2>New cohort: conformal calibration</h2>")
    parts.append(status_paragraph(*threshold_layer_state(result, "calibration")))
    conf = result.get("assumption_dependent_scenarios",{}).get("wasserstein_ambiguity_set")
    if conf and conf.get("guarantee_class")=="conformal_new_cohort":
        m = conf["calibration_manifest"]
        parts += ["<p>"+html.escape(m["coverage_statement"])+"</p>",
                  f"<p>Guaranteed marginal level: {_pct(m['confidence_level'])}; calibration units: {m.get('exchangeable_units')}; radius: {_fmt(m['radius'])}; reference: {html.escape(conf['reference_rule'])}. Scope: {html.escape(m['guarantee_scope'])}.</p>"]
        if 'normalized_radius' in conf:
            parts.append(f"<p>Normalized calibration radius: {_fmt(conf['normalized_radius'])}; "
                         f"fixed training scale for this panel: {_fmt(conf['transport_scale'])}; "
                         f"applied physical radius: {_fmt(conf['radius'])} log2 dilution steps.</p>")
        rows=[]
        for x in conf["threshold_results"]:
            e=x.get("envelope")
            rows.append([_fmt(x["threshold"]),f"{_pct(e['lower'])} to {_pct(e['upper'])}" if e else html.escape(result.get("conformal_unavailable_reason", "Unavailable: at least one variant could not be evaluated"))])
        parts.append(_table(["Threshold","Calibrated recorded-tail interval"],rows))
        if conf.get("update_interpretation"):
            parts.append("<p>"+html.escape(conf["update_interpretation"])+"</p>")
        parts += ["<details><summary>Calibration contract</summary>",
                  _table(["Field","Declared value"],[[html.escape(k),_fmt(v)] for k,v in m.get("calibration_contract",{}).items()]),"</details>"]
    else:
        if conf:
            parts.append("<p>A user-specified radius is displayed only as an assumption scenario; it has no calibrated coverage.</p>")
    utility=result.get("one_question_recovery") or {}
    if utility:
        parts.append("<h2>Additional information</h2><p>This separate calculation seeks narrower intervals. Loss is the sum of recorded-tail interval widths across the requested thresholds. Gains below are percentage points summed across those questions; they do not promise that a fraction criterion will be resolved.</p>")
        if not utility.get("search_complete",True):
            parts.append("<p>Search incomplete. Basic results are retained; no optimum or best-question recommendation is claimed.</p>")
        best=utility.get("best_question")
        if best and best["minimax_width_reduction"]>1e-12:
            parts += ["<p>Recommended count for reducing interval widths: "+html.escape(best["question"])+"</p>",
                      f"<p>Guaranteed reduction: {100*best['minimax_width_reduction']:.2f} percentage points; worst residual width: {100*best['worst_case_residual_width']:.2f}. Actual benefit depends on the answer.</p>"]
        elif utility.get("search_complete",True):
            parts.append("<p>No allowed question has a positive guaranteed width reduction. This width calculation makes no count recommendation.</p>")
        parts.append("<p>Direct target counts excluded: "+_fmt(utility.get("direct_target_questions_excluded",False))+".</p>")
        rows=[]
        for q in utility.get("ranked_questions",[]):
            rows.append([html.escape(q["question"]),_fmt(q["cost"]),
                         f"{100*q['minimax_width_reduction']:.2f}",
                         f"{100*q['score_per_cost']:.2f}",
                         f"{100*q['worst_case_residual_width']:.2f}",
                         _fmt(q["feasible_answer_range"]),_fmt(q["feasible_answers_evaluated"])])
        parts += ["<details><summary>Evaluated questions (up to ten highest ranked)</summary><p>Ranking uses guaranteed gain per acquisition cost. Zero-gain rows are comparisons, not recommendations. If the search is incomplete, this is only the evaluated subset.</p>",
                  _table(["Question","Acquisition cost","Guaranteed gain (pp)","Gain per cost (pp)","Worst residual (pp)","Feasible answers","Answers evaluated"],rows),"</details>"]
    else:
        parts.append("<h2>Additional information</h2><p>Additional-count search was not requested in this analysis mode or configuration.</p>")
    parts.append(_scenarios(result))
    notes=result.get("warnings",[])+result.get("interpretation_notes",[])
    if notes:
        parts.append("<h3>Interpretation and limitations</h3><ul>"+"".join("<li>"+html.escape(str(x))+"</li>" for x in notes)+"</ul>")
    return "".join(parts)


def _returned_counts(result):
    update = result.get("additional_information")
    if not update:
        return ""
    rows = []
    for item in update['observations']:
        count = (f"{item['count']}/{item['n']}" if 'count' in item else
                 f"{item['count_min']} to {item['count_max']} / {item['n']}")
        supplied = (f"{item['percentage']}%; {item['decimal_places']} decimal places; {item['rounding_rule']}"
                    if 'percentage' in item else 'Exact count' if 'count' in item else 'Inclusive count range')
        from .count_updates import observation_label
        rows.append([html.escape(observation_label(item)), count, html.escape(supplied), html.escape(item['source'])])
    parts = ["<h2>Returned counts</h2><p>Counts refer to the specified recorded MIC categories in the original cohort and denominator. A range retains every compatible integer count; no midpoint is substituted.</p>",
             _table(["Recorded MIC group", "Count / original n", "Information supplied", "Source"], rows)]
    if update['status'] != 'applied':
        parts.append("<p>Update unavailable: "+html.escape(update['reason'])+". Results below use the original summaries only.</p>")
    else:
        n = result['sample_size']
        parts.append(_table(["Target (mg/L)", "Before: extreme count bounds", "After: extreme count bounds"],
            [[_fmt(x['threshold']), f"{x['before_counts'][0]}/{n} to {x['before_counts'][1]}/{n}",
              f"{x['after_counts'][0]}/{n} to {x['after_counts'][1]}/{n}"] for x in update['per_threshold']]))
        parts.append('<p>This comparison uses the outer endpoints. Any excluded gaps after the update remain visible in the finite-sample table.</p>')
        parts.append(f"<p>Observed reduction in summed interval widths: {100*update['observed_width_reduction']:.2f} percentage points. This is the benefit of these answers; any recommendation below concerns a further count.</p>")
    return ''.join(parts)


def audit_section(audit):
    rows=[["MIC50/MIC90 only",_pct(audit["summary_only_width"])],
          ["One recommended count",_pct(audit["one_count_residual_width"])],
          ["Counts at every target",_pct(audit["all_target_counts_width"])],
          ["Full category histogram (recorded scale)",_pct(audit["full_histogram_recorded_width"])]]
    parts=["<h2>Laboratory reporting audit</h2><p>Sum of widths; 100% corresponds to 100 percentage points across all targets.</p>",
           _table(["Reporting content","Residual width"],rows),
           f"<p>Guaranteed gain: {_pct(audit['guaranteed_gain'])}; observed gain with this histogram: {_pct(audit['observed_gain'])}. Answer to the extra count: {_fmt(audit['additional_count_answer'])}.</p>",
           "<p>"+html.escape(audit["interpretation"])+"</p>"]
    rows=[[x["threshold"],_pct(x["recorded"]),f"{_pct(x['latent_lower'])} to {_pct(x['latent_upper'])}"] for x in audit["full_histogram"]]
    parts.append(_table(["Threshold","Known recorded fraction","Latent interval with full histogram"],rows))
    rows=[[x["threshold"],_range(x["summary_recorded_bounds"]),
           _range(x["one_count_recorded_bounds"]),_range(x["all_target_recorded_bounds"])]
          for x in audit.get("per_threshold",[])]
    if rows:
        parts.append(_table(["Threshold","Summaries alone","After the observed answer","Counts at all targets"],rows))
    return "".join(parts)


def _document(content, version):
    return html_with_typography('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>MIC-50-90 report</title><style>'+STYLE+VIEW_STYLE+'</style></head><body><main><h1>MIC-50-90 '+html.escape(str(version))+'</h1>'
            '<p class="subtitle">Sample bounds, iid population inference and new-cohort calibration</p>'+content+'</main></body></html>')


def render_html(result, destination):
    path=Path(destination); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(_document(threshold_overview(result)+'<details class="result-details"><summary>Detailed calculations and guarantees</summary>'+result_sections(result)+'</details>',result["version"]),encoding="utf-8")
    return path


def _render_batch_page(records, configuration, destination, pagination=None):
    total=len(records); accepted=sum(x["status"]=="ok" for x in records)
    parts=([pagination.navigation_html(), pagination.summary_html()] if pagination else
           [f"<p>Numerical analyses: {accepted}/{total}; refusals: {total-accepted}/{total}. Refusals remain in the denominator.</p>"])
    for index, record in enumerate(records):
        anchor = '' if pagination is None else ' id="'+pagination.cohort_anchor(index)+'"'
        parts.append('<article class="card"'+anchor+'><h2>Cohort '+html.escape(record["cohort_id"])+"</h2>")
        if record["status"]!="ok":
            parts.append('<p class="warning">Analysis refused: '+html.escape(record["reason"])+"</p>")
        else:
            parts.append(threshold_overview(record["result"],record.get('provenance')))
            if "reporting_plan" in record["result"]:
                from .reporting_report import render_reporting_plan
                parts.append(render_reporting_plan(record["result"]["reporting_plan"]))
            parts.append('<details class="result-details"><summary>Detailed calculations and guarantees</summary>')
            parts.append(result_sections(record["result"],record.get('provenance')))
            if "reporting_audit" in record:
                parts.append(audit_section(record["reporting_audit"]))
            parts.append('</details>')
        parts.append(f"<p>Runtime: {record['runtime_seconds']:.3f} seconds.</p></article>")
    parts.append("<p>Reproduction inputs, hashes and exact normalized settings are saved in configuration.json. The flat summary is in results.csv; results.json retains all calculations and unrounded numerical diagnostics.</p>")
    if pagination:
        parts.append(pagination.navigation_html())
    path=Path(destination)
    path.write_text(_document("".join(parts),configuration["version"]),encoding="utf-8")
    return path


def render_batch_html(records, configuration, destination, *, page_size=50):
    """Write a complete report, paginating large batches without dropping records."""
    from .report_pages import render_paginated_batch_html
    return render_paginated_batch_html(records, configuration, destination,
                                       page_size=page_size, render_page=_render_batch_page)
