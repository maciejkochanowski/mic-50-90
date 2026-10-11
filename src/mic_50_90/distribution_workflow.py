"""Whole recorded MIC distributions from explicit summaries and same-sample counts.

This workflow intentionally does not infer a quantile convention or an unobserved
panel. Counts-only inputs use the same integer constraint engine as summaries.
"""
from __future__ import annotations

import csv
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np

from ._version import __version__
from .count_updates import available_observations, observation_coefficients
from .empirical import EmpiricalProblem
from .exact_population import _merge_integer_ranges
from .file_safety import check_output_paths
from .model import MICPanel, QuantileSummary
from .result_schema import DISTRIBUTION_SCHEMA, validate_distribution_schema
from .validation import boolean, exact_integer, identifier, load_analysis_json
from .workflows import _boolean, _groups, _summary, _unit, load_panels, read_csv


def _provenance(raw):
    """Keep supplied cohort context separate from the calculation inputs."""
    if not isinstance(raw, dict):
        return {}
    from .input_context import add_context
    provenance = {key: deepcopy(raw[key]) for key in ("organism", "antimicrobial", "source", "source_doi",
        "source_location", "metadata_basis", "rank_basis", "panel_basis", "panel_id")
        if key in raw and raw[key] not in (None, "")}
    return add_context(provenance, raw, raw.get('targets', []))


def distribution_problems(raw):
    """Validate a distribution input and retain every feasible reporting variant."""
    if not isinstance(raw, dict):
        raise ValueError("A distribution input must be a JSON object")
    missing = [key for key in ("n", "panel", "unit") if raw.get(key) in (None, "")]
    if missing:
        raise ValueError("Missing required information: " + ", ".join(missing) +
                         "; provide the original denominator, explicit categories and MIC unit")
    n = exact_integer(raw["n"], "n", 1)
    _unit(raw["unit"])
    panel = MICPanel.from_dict(raw["panel"])
    if any(x <= 0 for x in panel.panel_values):
        raise ValueError("MIC panel values must be positive")
    envelope = raw.get("reporting_envelope", {})
    if not isinstance(envelope, dict) or not isinstance(envelope.get("variants", []), list):
        raise ValueError("reporting_envelope must contain a variants list")
    declared = [{"id": "primary", "summaries": raw.get("summaries", {})}, *envelope.get("variants", [])]
    if any(not isinstance(v, dict) or not isinstance(v.get("summaries", {}), dict) for v in declared):
        raise ValueError("Every reporting variant and its summaries must be objects")
    if "additional_counts" in raw and not isinstance(raw["additional_counts"], list):
        raise ValueError("additional_counts must be a list of original-sample counts")
    observations, _ = available_observations(raw.get('additional_counts', []), SimpleNamespace(n=n, panel=panel))
    if not observations and not any(v.get("summaries", {}).get("quantiles") or any(
            v.get("summaries", {}).get(key) is not None for key in ("minimum", "maximum")) for v in declared):
        raise ValueError("Supply MIC summaries, an observed range, or additional_counts from the original sample")
    problems, rejected, seen = {}, [], set()
    for variant in declared:
        if not isinstance(variant, dict):
            raise ValueError("Every reporting variant must be an object")
        key = identifier(variant.get("id"), "variant_id")
        if key in seen:
            raise ValueError("Duplicate reporting variant identifier: " + key)
        seen.add(key)
        summaries = variant.get("summaries", {})
        if not isinstance(summaries, dict) or not isinstance(summaries.get("quantiles", []), list):
            raise ValueError("summaries must be an object with a quantiles list")
        quantiles = []
        for quantile in summaries.get("quantiles", []):
            if not isinstance(quantile, dict) or not ("rank" in quantile or "convention" in quantile):
                raise ValueError("Every quantile requires an explicit convention or rank; neither is guessed")
            quantiles.append(QuantileSummary.from_dict(quantile, n=n, panel=panel))
        quantiles.sort(key=lambda item: item.rank)
        if any(a.rank >= b.rank for a, b in zip(quantiles, quantiles[1:])):
            raise ValueError("Reported quantile ranks must be strictly increasing")
        indices = {name + "_index": None if summaries.get(name) is None else panel.index(summaries[name])
                   for name in ("minimum", "maximum")}
        intervals = [(observation_coefficients(item, panel), item.get("count", item.get("count_min")),
                      item.get("count", item.get("count_max"))) for item in observations]
        try:
            problems[key] = EmpiricalProblem(n=n, panel=panel, quantiles=quantiles,
                                             count_intervals=intervals, **indices)
        except ValueError as exc:
            rejected.append({"id": key, "reason": str(exc)})
    if not problems:
        raise ValueError("Every reporting variant is incompatible with the supplied summaries and counts: " +
                         "; ".join(x["reason"] for x in rejected))
    return problems, observations, rejected


def _sample_rows(problems):
    first = next(iter(problems.values()))
    cdf, categories = [], []
    for kind, count, destination in (("cdf", first.k - 1, cdf), ("category", first.k, categories)):
        for index in range(count):
            objective = np.zeros(first.k)
            objective[:index + 1] = 1 if kind == "cdf" else 0
            if kind == "category":
                objective[index] = 1
            ranges = {key: [x.count for x in problem.bounds(objective)] for key, problem in problems.items()}
            lower = min(value[0] for value in ranges.values())
            upper = max(value[1] for value in ranges.values())
            components = _merge_integer_ranges([tuple(value) for value in ranges.values()])
            destination.append({"index": index, "label": first.panel.labels[index],
                "count_lower": lower, "count_upper": upper,
                "fraction_lower": lower / first.n, "fraction_upper": upper / first.n,
                "count_components": [list(value) for value in components],
                "fraction_components": [[lo / first.n, hi / first.n] for lo, hi in components],
                "variant_count_ranges": ranges})
    return {"status": "complete", "guarantee": "Sharp sample bounds conditional on the supplied information",
            "joint_compatibility_required": True, "cdf": cdf, "categories": categories}


def _category_envelope(cdf, panel):
    all_bounds = [[0., 0.], *[[row["lower"], row["upper"]] for row in cdf], [1., 1.]]
    return [{"index": index, "label": label,
             "lower": max(0., all_bounds[index + 1][0] - all_bounds[index][1]),
             "upper": min(1., all_bounds[index + 1][1] - all_bounds[index][0])}
            for index, label in enumerate(panel.labels)]


def _population_result(problems, confidence, *, method="bonferroni", time_limit=30., tolerance_pp=.01, include_intervals=False, questions=(), width_target_pp=None):
    from .joint_population import population_distribution
    result = population_distribution(problems, method=method, confidence_level=confidence,
        time_limit_seconds=time_limit, tolerance_pp=tolerance_pp, include_intervals=include_intervals, questions=questions,
        width_target_pp=width_target_pp)
    panel = next(iter(problems.values())).panel
    return _format_population_result(result, panel)


def _format_population_result(result, panel):
    result["cdf"] = [{"index": index, "label": panel.labels[index], "lower": float(bounds[0]),
                      "upper": float(bounds[1])} for index, bounds in enumerate(result["cdf_bounds"])]
    result["categories"] = [{"index": index, "label": panel.labels[index], "lower": float(bounds[0]),
                             "upper": float(bounds[1])} for index, bounds in enumerate(result["category_bounds"])]
    result["numerical_status"] = (
        "Binomial endpoints checked with directed probability bounds" if result["requested_method"] == "bonferroni" else
        "Requested outer-bound precision reached" if result.get("precision_reached") else
        "Conservative outer bounds retained; requested numerical precision was not reached")
    goal = result.get('width_goal', {})
    if goal.get('status') == 'met':
        result['numerical_status'] = 'Requested interval width confirmed. More precise endpoints are not needed to establish this width target.'
    elif goal.get('all_ranges_assessed'):
        result['numerical_status'] = ('Width assessment complete. Some MIC ranges remain wider than requested; '
            'more endpoint refinement alone cannot meet the width target for those ranges. Review the displayed grouping or add available counts.')
    if result["status"] == "unavailable":
        result.update(engine_status="unavailable", status="baseline_retained")
    result["fixed_family"] = ([str(panel.labels[a]) + ' through ' + str(panel.labels[b-1])
        for a in range(len(panel.bins)) for b in range(a+1, len(panel.bins))]
        if result.get('family_kind') == 'all_contiguous_ranges_up_to_complements'
        else list(panel.labels[:-1]))
    return result


def _joint_population(problems, confidence, time_limit, tolerance_pp, include_intervals=False, questions=()):
    return _population_result(problems, confidence, method="joint-exact", time_limit=time_limit, tolerance_pp=tolerance_pp, include_intervals=include_intervals, questions=questions)


def _validate_saved_update(raw, previous, population_method):
    old = previous["input"]
    if {key: value for key, value in old.items() if key != "additional_counts"} != {
            key: value for key, value in raw.items() if key != "additional_counts"}:
        raise ValueError("A saved update must retain the original input, denominator, panel, reporting conventions and confidence; only additional_counts may change")
    if previous["population_method"] != population_method:
        raise ValueError("A saved update must retain the original population method")
    old_counts, new_counts = old.get("additional_counts", []), raw.get("additional_counts", [])
    if new_counts[:len(old_counts)] != old_counts:
        raise ValueError("A saved update must retain every previous count and append only new truthful counts")
    if previous["result"].get("status") != "ok":
        raise ValueError("A saved update requires a successful previous analysis for this cohort")


def _calibration(raw, panel, observations):
    if not raw.get("wasserstein_calibration_manifest"):
        return {"status": "unavailable", "reason": "No compatible reference and calibration manifest supplied"}
    try:
        from .analysis import analyse_spec
        from .count_updates import analyse_with_counts
        from .calibration_binding import validate_prepared_calibration
        prepared = {key: raw[key] for key in ("reference_distribution", "wasserstein_calibration_manifest", "calibration_context")}
        analysis = {key: deepcopy(raw[key]) for key in ("n", "panel", "summaries", "reporting_envelope") if key in raw}
        analysis.update(mode="empirical", contract_version="1.0", thresholds=panel.panel_values[:-1].tolist(),
                        question_utility={"enabled": False})
        validate_prepared_calibration(analysis, prepared,
            cohort_id=identifier(raw.get("cohort_id", "cohort"), "cohort_id"), panel_id=raw.get("panel_id"))
        if observations:
            result = analyse_with_counts(analysis, observations, calibration=prepared)
        else:
            result = analyse_spec({**analysis, **prepared})
        band = result["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"]
        if prepared["wasserstein_calibration_manifest"]["calibration_contract"].get("functional_scope") != "all_panel_tails":
            raise ValueError("The manifest must cover all panel tails for a whole recorded distribution")
        if [row["threshold"] for row in band["threshold_results"]] != panel.panel_values[:-1].tolist():
            raise ValueError("The calibrated output does not contain the complete fixed panel tail family")
        if any(row.get("envelope") is None for row in band["threshold_results"]):
            raise ValueError("At least one calibrated threshold is unavailable")
        cdf = [{"index": index, "label": panel.labels[index], "lower": 1 - row["envelope"]["upper"],
                "upper": 1 - row["envelope"]["lower"]} for index, row in enumerate(band["threshold_results"])]
        manifest = band["calibration_manifest"]
        return {"status": "complete", "cdf": cdf, "categories": _category_envelope(cdf, panel),
                "guarantee": band["interpretation"], "guarantee_class": band["guarantee_class"],
                "confidence_level": manifest["confidence_level"], "requested_level": manifest["requested_level"],
                "guarantee_scope": manifest["guarantee_scope"], "coverage_scope": band["coverage_scope"],
                "family_size": len(cdf), "method": "split-conformal",
                "calibration_units": manifest["exchangeable_units"],
                "calibration_unit_definition": manifest["exchangeable_unit_definition"],
                "calibration_contract": deepcopy(manifest["calibration_contract"]),
                "reference_rule": band["reference_rule"], "radius": band["radius"],
                **({key: band[key] for key in ("normalized_radius", "transport_scale")} if "normalized_radius" in band else {}),
                "update_interpretation": band.get("update_interpretation"),
                "assumptions": [
                    "Calibration and future study units must be exchangeable under the fixed training and reference protocol.",
                    "The score, summary and selection rules, target family and complete unit composition must match calibration.",
                    "The marginal guarantee averages over calibration and future units; it is not conditional on a realised calibration set or covariates.",
                    "Category ranges follow from the simultaneous cumulative intervals; they do not reconstruct concentrations inside categories."],
                "details": band}
    except (ValueError, KeyError, TypeError, RuntimeError, ArithmeticError) as exc:
        return {"status": "unavailable", "reason": "Calibration unavailable: " + str(exc)}


def analyse_distribution(raw, *, population_method="bonferroni", population_time_limit=30.,
                         population_tolerance_pp=.01, precision_pp=None, previous_analysis=None,
                         population_precision_pp=None, population_count_plan=False,
                         population_minimum_bins=None, population_planning_time_limit=10.):
    """Return sample, simultaneous iid population and optional calibration layers.

Additional counts always concern the same original denominator and strict
recorded-category tails. The returned ranges are projections of a constrained
set; arbitrary choices of individual endpoints need not form one distribution.
"""
    started = perf_counter()
    problems, observations, rejected = distribution_problems(raw)
    if previous_analysis is not None:
        _validate_saved_update(raw, previous_analysis, population_method)
    first = next(iter(problems.values()))
    iid = boolean(raw.get("iid", False), "iid")
    confidence = raw.get("confidence_level", .95)
    if isinstance(confidence, bool) or not isfinite(float(confidence)) or not 0 < float(confidence) < 1:
        raise ValueError("confidence_level must lie strictly between 0 and 1")
    confidence = float(confidence)
    sample = _sample_rows(problems)
    from .distribution_options import option_issues
    option_errors = option_issues(dict(population_method=population_method,
        population_time_limit=population_time_limit, population_tolerance_pp=population_tolerance_pp,
        precision_pp=precision_pp, population_precision_pp=population_precision_pp,
        population_count_plan=population_count_plan, population_minimum_bins=population_minimum_bins,
        population_planning_time_limit=population_planning_time_limit), categories=first.k)
    hunter_width_target = (population_precision_pp if population_method == 'range-hunter'
        and 'population_precision_pp' not in option_errors else None)
    resolution = {"status": "not_requested", "reason": "No sample precision target was supplied"}
    if precision_pp is not None:
        from .distribution_resolution import maximum_resolvable_partition
        try:
            resolution = maximum_resolvable_partition(problems, precision_pp=precision_pp)
        except (ValueError, RuntimeError, ArithmeticError) as exc:
            resolution = {"status": "unavailable", "reason": "Sample resolution unavailable: " + str(exc)}
    population = {"status": "unavailable", "reason": "iid sampling was not declared; no population guarantee"}
    old_population = previous_analysis["result"].get("population", {}) if previous_analysis is not None else {}
    include_population_intervals = population_precision_pp is not None or bool(raw.get('targets'))
    from .distribution_targets import read_targets
    population_questions = []
    for target, _, criterion in read_targets(raw.get('targets', []), first.panel):
        if criterion is not None and target['question_type'] == 'threshold' and not target['measurement_ambiguous_categories']:
            cut = target['start_index']-1
            if 0 <= cut < first.k-1:
                population_questions.append(dict(cut_index=cut,fraction=criterion['decision_fraction_text']))
    if iid and 'population_method' in option_errors:
        population = {"status": "unavailable", "reason": "Population settings: " + option_errors['population_method']}
    elif iid and "cdf_bounds" in old_population:
        from .joint_population import update_population_distribution
        previous_problems, _, _ = distribution_problems(previous_analysis["input"])
        try:
            refined = update_population_distribution(previous_problems, problems, old_population,
                method=population_method, confidence_level=confidence,
                time_limit_seconds=population_time_limit, tolerance_pp=population_tolerance_pp,
                include_intervals=include_population_intervals, questions=population_questions,
                width_target_pp=hunter_width_target)
            population = _format_population_result(refined, first.panel)
        except (ValueError, TypeError, RuntimeError, ArithmeticError, TimeoutError, MemoryError) as exc:
            # A failure may occur before saved numerical bounds are validated.
            # Do not attach them to new constraints or claim a successful update.
            population = dict(status="unavailable", precision_reached=False,
                reason="Population update unavailable: " + str(exc) +
                ". The sample result is available; check the saved files and retry.")
    elif iid:
        try:
            if population_method in ('range-calibrated','range-hunter'):
                invalid_refinement = {key: option_errors[key] for key in
                    ('population_time_limit', 'population_tolerance_pp') if key in option_errors}
                population = _population_result(problems, confidence, method=population_method,
                    time_limit=0. if invalid_refinement else population_time_limit,
                    tolerance_pp=.01 if invalid_refinement else population_tolerance_pp,
                    include_intervals=include_population_intervals, width_target_pp=hunter_width_target)
                if invalid_refinement:
                    population.update(status='baseline_retained',
                        reason='Invalid optional refinement settings: ' + '; '.join(invalid_refinement.values()) +
                        '. Safe bounds from the selected range method are retained.')
            else:
                population = _population_result(problems, confidence, include_intervals=include_population_intervals)
        except (ValueError, TypeError, RuntimeError, ArithmeticError, TimeoutError, MemoryError) as exc:
            population = {"status": "unavailable", "reason": "Population calculation unavailable: " + str(exc)}
        if population_method == "joint-exact" and population["status"] != "unavailable":
            population["requested_method"] = "joint-exact"
            try:
                refined = _joint_population(problems, confidence, population_time_limit, population_tolerance_pp,
                    include_intervals=include_population_intervals, questions=population_questions)
                population.update(refined)
            except (ImportError, ValueError, TypeError, RuntimeError, ArithmeticError, TimeoutError, MemoryError) as exc:
                population.update(status="baseline_retained", reason="Joint refinement did not finish: " + str(exc),
                                  precision_reached=False,
                                  numerical_status="Basic simultaneous bounds retained; no additional precision claimed")
                for row in population.get('interval_bounds', []):
                    row.update(inner_lower=None, inner_upper=None)
    population_resolution = {"status": "not_requested"}
    if population_precision_pp is not None:
        from .population_precision import maximum_population_partition
        if not iid or 'interval_bounds' not in population:
            population_resolution = dict(status='unavailable', reason=population.get('reason', 'Population intervals unavailable; iid sampling must be declared'))
        else:
            try:
                if 'population_precision_pp' in option_errors:
                    raise ValueError(option_errors['population_precision_pp'])
                population_resolution = maximum_population_partition(population, first.panel,
                    precision_pp=population_precision_pp, required_cuts=raw.get('required_population_cuts', []))
            except (ValueError, RuntimeError, ArithmeticError, TypeError, KeyError, TimeoutError, MemoryError) as exc:
                population_resolution = dict(status='unavailable', reason='Population grouping unavailable: '+str(exc))
    count_plan = {'status':'not_requested'}
    if population_count_plan:
        if not iid or population_precision_pp is None:
            count_plan = dict(status='unavailable',reason='Count planning requires an iid declaration and a population precision target')
        else:
            from .population_acquisition import plan_population_precision
            try:
                if option_errors:
                    raise ValueError('; '.join(option_errors.values()))
                count_plan = plan_population_precision(problems,precision_pp=population_precision_pp,
                    confidence_level=confidence,method=population_method,minimum_bins=population_minimum_bins,
                    required_cuts=raw.get('required_population_cuts',[]),queries=raw.get('population_count_queries'),
                    time_limit_seconds=population_planning_time_limit)
            except (ValueError,RuntimeError,ArithmeticError,TypeError,KeyError,TimeoutError,MemoryError) as exc:
                count_plan = dict(status='unavailable',reason='Count planning unavailable: '+str(exc))
    from .distribution_decisions import distribution_decisions
    calibration = _calibration(raw, first.panel, observations)
    decisions = distribution_decisions(raw, problems, population, calibration)
    result = {"cohort_id": identifier(raw.get("cohort_id", "cohort"), "cohort_id"), "status": "ok",
            "decisions": decisions,
            "n": first.n, "unit": "mg/L", "panel": first.panel.as_dict(),
            "provenance": _provenance(raw),
            "question_note": str(raw.get("question_note", "")),
            "sample": sample, "population": population,
            "resolution": resolution, "population_resolution": population_resolution, 'population_count_plan':count_plan,
            "calibration": calibration,
            "retained_variants": list(problems), "rejected_variants": rejected,
            "reported_summaries": [{"id": "primary", "summaries": deepcopy(raw.get("summaries", {}))},
                                   *deepcopy(raw.get("reporting_envelope", {}).get("variants", []))],
            "additional_counts": observations,
            "input_information_issues": available_observations(raw.get('additional_counts', []), first)[1],
            "saved_count_update": previous_analysis is not None,
            "option_issues": option_errors,
            "assumptions": ["All counts and summaries concern the same original sample and denominator.",
                "Panel categories and reporting conventions are explicitly supplied.",
                "These results describe recorded MIC categories, not exact concentrations inside a category.",
                "A displayed range is a projection; all original constraints must hold together.",
                "Population coverage requires iid sampling and a panel threshold family fixed independently of the observed counts."],
            "runtime_seconds": perf_counter() - started,
            "inference_requested": {"population": iid, "calibration": any(raw.get(key) for key in (
                "reference_distribution", "wasserstein_calibration_manifest", "calibration_context"))}}
    if previous_analysis is not None:
        before, before_counts, _ = distribution_problems(previous_analysis["input"])
        previous_count = len(before_counts)
        result["sample_comparison"] = {"status": "complete", "before": _sample_rows(before),
            "added_counts": deepcopy(observations[previous_count:]),
            "scope": "Same original sample, panel and assumptions; only added count information differs"}
    if boolean(raw.get("explain_counts", False), "explain_counts"):
        supplied = raw.get("additional_counts", [])
        if len(supplied) > 20:
            result["count_explanation"] = {"status": "unavailable", "reason": "Step-by-step display supports up to 20 count rows; the complete analysis remains available."}
        else:
            stages = []
            deferred = {issue['observation_number'] for issue in result['input_information_issues']}
            try:
                for number in range(1, len(supplied) + 1):
                    if number in deferred:
                        continue
                    subset = deepcopy(raw)
                    subset["additional_counts"] = supplied[:number]
                    stage_problems, stage_counts, _ = distribution_problems(subset)
                    not_run = {"status": "unavailable", "reason": "This demonstration describes the same observed sample"}
                    stages.append({"count_rows": len(stage_counts), "source_row": number, "added_count": stage_counts[-1],
                        "sample": _sample_rows(stage_problems),
                        "decisions": distribution_decisions(subset, stage_problems, not_run, not_run)})
                result["count_explanation"] = {"status": "complete", "stages": stages,
                    "scope": "Demonstration of using the supplied counts in entry order, not an independent evaluation"}
            except (ValueError, RuntimeError, ArithmeticError) as exc:
                result["count_explanation"] = {"status": "unavailable", "reason": str(exc)}
    from .result_view import distribution_guidance
    result["interpretation"] = distribution_guidance(result, problems)
    result["runtime_seconds"] = perf_counter() - started
    return result


def _csv_inputs(args, delimiter):
    if not args.panels:
        raise ValueError("CSV distribution input requires --panels with the explicit category table")
    panels, errors = load_panels(args.panels, delimiter)
    grouped = _groups(read_csv(args.input, delimiter), "cohort_id")
    counts = _groups(read_csv(args.additional_counts, delimiter), "cohort_id") if args.additional_counts else {}
    targets = _groups(read_csv(args.targets, delimiter), "cohort_id") if getattr(args, "targets", None) else {}
    unknown = (set(counts) | set(targets)) - set(grouped)
    if unknown:
        raise ValueError("Additional counts refer to unknown cohorts: " + ", ".join(sorted(unknown)))
    inputs = []
    for cohort, rows in grouped.items():
        try:
            missing = [f"row {index}: {key}" for index, row in enumerate(rows, 1)
                       for key in ("panel_id", "n", "variant_id") if not row.get(key, "").strip()]
            if missing:
                raise ValueError("Missing " + "; ".join(missing))
            pids = {row["panel_id"] for row in rows}
            sizes = {exact_integer(row["n"], "n", 1) for row in rows}
            if len(pids) != 1 or len(sizes) != 1:
                raise ValueError("panel_id and original n must agree across reporting variants")
            pid, n = pids.pop(), sizes.pop()
            if pid in errors:
                raise ValueError(errors[pid])
            if pid not in panels:
                raise ValueError("Missing panel " + pid + "; complete panels.csv")
            summaries = {}
            for row in rows:
                key = identifier(row["variant_id"], "variant_id")
                if key in summaries:
                    raise ValueError("Duplicate variant_id " + key)
                has_quantiles = any(row.get(key, "").strip() for key in ("mic50", "mic90"))
                summaries[key] = _summary(row, n) if has_quantiles else {
                    key: row[key].strip() for key in ("minimum", "maximum") if row.get(key, "").strip()}
            if "primary" not in summaries:
                raise ValueError("variant_id=primary is required")
            iid_values = {_boolean(row.get("iid", "false") or "false", "iid") for row in rows}
            confidence_values = {float(row.get("confidence_level", ".95") or ".95") for row in rows}
            if len(iid_values) != 1 or len(confidence_values) != 1:
                raise ValueError("iid and confidence_level must agree across reporting variants")
            raw = {"cohort_id": cohort, "unit": "mg/L", "panel": panels[pid].as_dict(), "n": n,
                   "summaries": summaries.pop("primary"),
                   "reporting_envelope": {"variants": [{"id": key, "summaries": value} for key, value in summaries.items()]},
                   "iid": iid_values.pop(), "confidence_level": confidence_values.pop()}
            # Keep optional source context in the saved input as well as the report.
            # Blank columns retain the legacy input shape and never imply iid.
            from .input_context import sample_context
            from .workflows import _consistent
            for name in ('organism', 'antimicrobial', 'source', 'source_doi', 'source_location',
                         'metadata_basis', 'rank_basis', 'panel_basis', 'sample_context'):
                value = _consistent(rows, name, '')
                if value:
                    raw[name] = sample_context(value) if name == 'sample_context' else value
            if cohort in counts:
                raw["additional_counts"] = [{key: value for key, value in row.items() if key != "cohort_id" and value != ""}
                                            for row in counts[cohort]]
            if cohort in targets:
                raw["targets"] = [{k:v for k,v in row.items() if k != "cohort_id" and v != ""} for row in targets[cohort]]
            inputs.append((raw, None))
        except (ValueError, KeyError, TypeError) as exc:
            inputs.append(({"cohort_id": cohort}, str(exc)))
    return inputs


def _load_previous_output(directory):
    previous = Path(directory)
    configuration = json.loads((previous / "configuration.json").read_text(encoding="utf-8-sig"))
    results = json.loads((previous / "results.json").read_text(encoding="utf-8-sig"))
    if not isinstance(configuration, dict) or not isinstance(results, dict):
        raise ValueError("Previous configuration and results must be JSON objects")
    if results.get("software") != "MIC-50-90" or results.get("software_version") != __version__:
        raise ValueError("Previous output must be a MIC-50-90 1.0.0 distribution analysis")
    validate_distribution_schema(results)

    def keyed(rows):
        if not isinstance(rows, list):
            raise ValueError("Previous output must contain a list of cohort records")
        by_id = {}
        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("Previous cohort records must be JSON objects")
            key = identifier(raw.get("cohort_id", "cohort"), "cohort_id")
            if key in by_id:
                raise ValueError("Previous output contains duplicate cohort identifiers")
            by_id[key] = raw
        return by_id

    inputs, records = keyed(configuration["inputs"]), keyed(results["cohorts"])
    if inputs.keys() != records.keys():
        raise ValueError("Previous configuration and results do not contain the same cohorts")
    return {key: {"input": raw, "result": records[key], "population_method": configuration["population_method"]}
            for key, raw in inputs.items()}


def run_distribution(args):
    """Read a JSON input or explicit joined CSVs and write portable outputs."""
    from .distribution_report import render_distribution_html
    output = Path(args.output_dir)
    destinations = [output / name for name in ("results.json", "configuration.json", "distribution.csv", "report.html", "decisions.csv")]
    sources = [args.input, args.panels, args.additional_counts, getattr(args, "targets", None)]
    if args.previous_output:
        sources.extend(Path(args.previous_output) / name for name in ("configuration.json", "results.json"))
    check_output_paths(sources, destinations)
    previous = _load_previous_output(args.previous_output) if args.previous_output else None
    delimiter = {"comma": ",", "semicolon": ";", "tab": "\t"}[args.delimiter]
    if Path(args.input).suffix.lower() == ".json":
        if args.panels or args.additional_counts or getattr(args, "targets", None):
            raise ValueError("For JSON inputs include panel and additional_counts in the input object")
        raw = load_analysis_json(Path(args.input).read_text(encoding="utf-8-sig"))
        inputs = [(raw, None)]
    else:
        inputs = _csv_inputs(args, delimiter)
    records = []
    for raw, refusal in inputs:
        try:
            if refusal:
                raise ValueError(refusal)
            saved = None
            if previous is not None:
                key = raw.get("cohort_id", "cohort")
                if key not in previous:
                    raise ValueError("The previous output has no matching cohort: " + str(key))
                saved = previous[key]
            records.append(analyse_distribution(raw, population_method=args.population_method,
                population_time_limit=args.population_time_limit, population_tolerance_pp=args.population_tolerance_pp,
                precision_pp=args.precision_pp, previous_analysis=saved,
                population_precision_pp=getattr(args, 'population_precision_pp', None),
                population_count_plan=getattr(args,'population_count_plan',False),
                population_minimum_bins=getattr(args,'population_minimum_bins',None),
                population_planning_time_limit=getattr(args,'population_planning_time_limit',10.)))
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            records.append({"cohort_id": raw.get("cohort_id", "cohort") if isinstance(raw, dict) else "cohort",
                            "status": "refused", "reason": str(exc), "provenance": _provenance(raw)})
    result = {"software": "MIC-50-90", "software_version": __version__, "result_schema": DISTRIBUTION_SCHEMA, "cohorts": records}
    configuration = {"population_method": args.population_method, "population_time_limit": args.population_time_limit,
                     "population_tolerance_pp": args.population_tolerance_pp,
                     "precision_pp": args.precision_pp,
                     "population_precision_pp": getattr(args, 'population_precision_pp', None),
                     "population_count_plan": getattr(args,'population_count_plan',False),
                     "population_minimum_bins": getattr(args,'population_minimum_bins',None),
                     "population_planning_time_limit": getattr(args,'population_planning_time_limit',10.),
                     "previous_output": None if args.previous_output is None else str(Path(args.previous_output).resolve()),
                     "inputs": [raw for raw, _ in inputs]}
    # Invalid optional numeric settings are reported by the refinement layer.
    # Preserve their spelling without letting non-JSON numbers discard valid
    # sample and baseline results during export.
    for key in ("population_time_limit", "population_tolerance_pp"):
        value = configuration[key]
        if isinstance(value, float) and not isfinite(value):
            configuration[key] = str(value)
    # Serialise before writing: malformed optional values must not leave a
    # plausible partial report or replace a previous complete result.
    result_text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    config_text = json.dumps(configuration, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=True)
    destinations[0].write_text(result_text, encoding="utf-8")
    destinations[1].write_text(config_text, encoding="utf-8")
    columns = ["cohort_id", "status", "reason", "layer", "quantity", "category", "n", "unit",
               "lower", "upper", "lower_count", "upper_count", "count_components", "confidence_level", "method", "precision_pp",
               "guarantee_class", "guarantee_scope", "calibration_units", "calibration_unit_definition", "assumptions",
               "requested_level", "family_size", "coverage_scope", "reference_rule", "radius", "normalized_radius", "transport_scale"]
    with destinations[2].open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        def write_row(row):
            # This export is for spreadsheets; JSON retains original labels.
            writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
                             else value for key, value in row.items()})
        for record in records:
            common = {"cohort_id": record["cohort_id"], "n": record.get("n"), "unit": record.get("unit")}
            if record["status"] != "ok":
                write_row({**common, "status": "refused", "reason": record["reason"]})
                continue
            resolution = record.get("resolution", {})
            for row in resolution.get("bins", []):
                write_row({**common, "status": resolution["status"], "layer": "sample_resolution", "quantity": "categories",
                    "category": row["label"], "lower": row["fraction_lower"], "upper": row["fraction_upper"],
                    "lower_count": row["count_lower"], "upper_count": row["count_upper"],
                    "count_components": json.dumps(row["count_components"]), "precision_pp": resolution["precision_pp_decimal"]})
            population_resolution = record.get('population_resolution', {})
            for row in population_resolution.get('bins', []):
                write_row({**common,'status':population_resolution['status'],'layer':'population_resolution',
                    'quantity':'categories','category':row['label'],'lower':row['lower'],'upper':row['upper'],
                    'confidence_level':population_resolution['confidence_level'],'precision_pp':population_resolution['precision_pp'],
                    'method':record['population'].get('method')})
            for layer in ("sample", "population", "calibration"):
                current = record[layer]
                for quantity in ("cdf", "categories"):
                    for row in current.get(quantity, []):
                        write_row({**common, "status": current["status"], "layer": layer, "quantity": quantity,
                            "category": row["label"], "lower": row.get("lower", row.get("fraction_lower")),
                            "upper": row.get("upper", row.get("fraction_upper")),
                            "lower_count": row.get("count_lower"), "upper_count": row.get("count_upper"),
                            "count_components": json.dumps(row["count_components"]) if "count_components" in row else "",
                            "confidence_level": current.get("confidence_level"), "method": current.get("method"),
                            "guarantee_class": current.get("guarantee_class"), "guarantee_scope": current.get("guarantee_scope"),
                            "calibration_units": current.get("calibration_units"),
                            "calibration_unit_definition": current.get("calibration_unit_definition"),
                            "assumptions": " ".join(current.get("assumptions", [])),
                            **{key: current.get(key) for key in ("requested_level", "family_size", "coverage_scope", "reference_rule",
                                                               "radius", "normalized_radius", "transport_scale")}})
                if current["status"] == "unavailable":
                    write_row({**common, "status": "unavailable", "layer": layer, "reason": current["reason"]})
    with destinations[4].open("w", encoding="utf-8", newline="") as stream:
        fields = ["cohort_id", "threshold", "start_category", "end_category", "question_type", "target_scale", "measurement_explanation", "unit", "decision_operator", "decision_fraction_text", "layer", "status", "count_components", "lower", "upper", "confidence_level", "scope", "guarantee", "calculation_assessment", "further_computation_may_change_answer", "interpretation", "assessment_scope"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            for decision in record.get("decisions", []):
                for layer in ("sample", "population", "calibration"):
                    row = {k: decision[k] for k in fields if k in decision}
                    row.update(cohort_id=record["cohort_id"], layer=layer, **{k:v for k,v in decision[layer].items() if k in fields})
                    if "count_components" in row:
                        row["count_components"] = json.dumps(row["count_components"])
                    writer.writerow({k: "'"+v if isinstance(v,str) and v.startswith(("=","+","-","@","\t","\r","\n")) else v for k,v in row.items()})
    render_distribution_html(result, destinations[3])
    return 2 if args.fail_on_refusal and any(row["status"] == "refused" for row in records) else 0
