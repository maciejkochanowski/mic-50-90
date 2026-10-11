"""CSV workflows with explicit joins, per-cohort refusals and portable reports."""
from __future__ import annotations

import csv
from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from time import perf_counter

import numpy as np

from .analysis import analyse_spec, json_safe
from ._version import __version__
from .empirical import EmpiricalProblem
from .model import MICPanel, parse_spec
from .decisions import parse_criterion, decision_results
from .validation import IDENTIFIER_FIELDS, ceiling_rank, exact_integer, identifier


def _required(row, key):
    if key in IDENTIFIER_FIELDS:
        return identifier(row.get(key), key)
    value = str(row.get(key, "")).strip()
    if not value:
        raise ValueError(f"Missing {key}; complete this field in the CSV template")
    return value


def _number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _integer(value, label, minimum=0):
    return exact_integer(value, label, minimum)


def _boolean(value, label):
    if str(value).lower() not in {"true", "false"}:
        raise ValueError(f"{label} must explicitly be true or false")
    return str(value).lower() == "true"


def _unit(value):
    # These are equal physical units, not an inferred conversion.
    if value not in {"mg/L", "ug/mL", "µg/mL", "μg/mL"}:
        raise ValueError("unit must explicitly be mg/L or its equivalent ug/mL")
    return "mg/L"


def read_csv(path, delimiter=",", *, expected_fields=None):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError(f"{Path(path).name}: missing or duplicate CSV headers")
        if expected_fields is not None and set(reader.fieldnames) != set(expected_fields):
            raise ValueError(f"{Path(path).name}: fields must be {', '.join(expected_fields)}")
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f"{Path(path).name}: row width does not match the header")
    for index, row in enumerate(rows, 2):
        for key in IDENTIFIER_FIELDS.intersection(row):
            if row[key] and row[key] != row[key].strip():
                raise ValueError(f"{Path(path).name}, row {index}: {key} has surrounding whitespace; supply the exact identifier")
    return rows


def _groups(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[_required(row, key)].append(row)
    return dict(groups)


def _missing_join_issues(rows, key, required, filename):
    """An unassignable row needs a complete file-level correction message."""
    if all(str(row.get(key,'')).strip() for row in rows):
        return []
    issues=[]
    for index,row in enumerate(rows,2):
        fields=list(required)
        if row.get('rank_convention')=='explicit':
            fields.extend(('rank50','rank90'))
        for field in fields:
            if not str(row.get(field,'')).strip():
                issues.append(f'{filename}, row {index}: missing {field}')
    return issues


def _consistent(rows, key, default=None):
    if key in IDENTIFIER_FIELDS:
        for row in rows:
            identifier(row.get(key), key)
    values = {str(r.get(key, default if default is not None else "")).strip() for r in rows}
    if len(values) != 1:
        raise ValueError(f"{key} must agree for all rows in a cohort")
    value = values.pop()
    return value


def load_panels(path, delimiter=","):
    panels, errors = {}, {}
    source_rows=read_csv(path, delimiter=delimiter)
    missing=_missing_join_issues(source_rows,'panel_id',
        ('panel_id','unit','category','panel_value','lower_closed','upper_closed'),Path(path).name)
    if missing:
        raise ValueError('; '.join(missing)+'; complete these CSV fields before analysis')
    for pid, rows in _groups(source_rows, "panel_id").items():
        try:
            missing = [f'Missing {key} in panel {pid}, row {index}; complete panels.csv'
                       for index,row in enumerate(rows,1)
                       for key in ('unit','category','panel_value','lower_closed','upper_closed')
                       if not str(row.get(key,'')).strip()]
            if missing:
                raise ValueError('; '.join(missing))
            categories = []
            for row in rows:
                _unit(_required(row, "unit"))
                lo = None if not row.get("lower", "").strip() else _number(row["lower"], "lower")
                hi = None if not row.get("upper", "").strip() else _number(row["upper"], "upper")
                value = _number(_required(row, "panel_value"), "panel_value")
                if value <= 0 or any(x is not None and x < 0 for x in (lo, hi)):
                    raise ValueError("MIC panel values must be positive and bounds nonnegative")
                categories.append(dict(label=_required(row,"category"), lower_bound=lo,
                                       upper_bound=hi, panel_value=value,
                                       lower_closed=_boolean(_required(row,"lower_closed"),"lower_closed"),
                                       upper_closed=_boolean(_required(row,"upper_closed"),"upper_closed")))
            panels[pid] = MICPanel.from_dict({"categories": categories})
        except (ValueError, KeyError, TypeError) as exc:
            errors[pid] = str(exc)
    return panels, errors


def _summary(row, n):
    convention = _required(row, "rank_convention")
    if convention not in {"ceiling", "explicit"}:
        raise ValueError("rank_convention must be ceiling or explicit; no quantile convention is guessed")
    quantiles = []
    for percent in (50, 90):
        q = {"probability": percent/100, "category": _required(row, f"mic{percent}")}
        if convention == "explicit":
            q["rank"] = _integer(_required(row, f"rank{percent}"), f"rank{percent}", 1)
        else:
            q["convention"] = "ceiling"
            supplied = row.get(f"rank{percent}", "").strip()
            if supplied and _integer(supplied, f"rank{percent}", 1) != ceiling_rank(q["probability"], n):
                raise ValueError("explicit rank conflicts with ceiling rank_convention")
        quantiles.append(q)
    result = {"quantiles": quantiles}
    for key in ("minimum","maximum"):
        if row.get(key, "").strip():
            result[key] = row[key].strip()
    return result


def summary_spec(rows, panel, thresholds, options):
    n = _integer(_consistent(rows, "n"), "n", 1)
    if n < 2:
        raise ValueError("MIC50/MIC90 requires at least two observations; this is a technical minimum, not a usefulness guarantee")
    variants = {}
    for row in rows:
        vid = _required(row, "variant_id")
        if vid in variants:
            raise ValueError(f"duplicate variant_id {vid}")
        variants[vid] = _summary(row, n)
    if "primary" not in variants:
        raise ValueError("variant_id=primary is required; other rows declare additional alternatives")
    return dict(contract_version="1.0", mode="empirical", n=n, panel=panel.as_dict(),
                summaries=variants.pop("primary"), thresholds=thresholds,
                reporting_envelope={"variants":[{"id":k,"summaries":v} for k,v in variants.items()]},
                question_utility=options)


def counts_spec(rows, panel, thresholds, options):
    categories = [_required(r,"category") for r in rows]
    if len(categories) != len(set(categories)):
        raise ValueError("duplicate count category; supply one row per category and cohort")
    if set(categories) != set(panel.labels):
        raise ValueError("counts must list every panel category exactly once, including explicit zeros")
    if _consistent(rows,"rank_convention") != "ceiling":
        raise ValueError("reporting-audit requires rank_convention=ceiling for generated summaries")
    by_category = {r["category"]: _integer(r["count"],"count") for r in rows}
    n = exact_integer(sum(by_category.values()), "histogram total n", 2)
    counts = np.array([by_category[label] for label in panel.labels], dtype=np.int64)
    if n < 2:
        raise ValueError("MIC50/MIC90 reporting-audit requires at least two observations")
    cum = np.cumsum(counts)
    summaries = {"quantiles": [
        {"probability":q, "category":panel.labels[int(np.searchsorted(cum,ceiling_rank(q, n)))],
         "convention":"ceiling"} for q in (.5,.9)]}
    return dict(contract_version="1.0",mode="empirical",n=n,panel=panel.as_dict(),
                summaries=summaries,thresholds=thresholds,question_utility=options), counts


def analyse_layers(raw, iid, confidence, calibration=None):
    result = analyse_spec(raw)
    result["inference_requested"] = {"population": bool(iid), "calibration": calibration is not None}
    if iid:
        population = deepcopy(raw)
        population["mode"] = "population"
        population["population"] = {"profile_likelihood_enabled":False,"bayes_enabled":False,
                                  "exact_count_confidence":{"confidence_level":confidence,
                                                            "multiplicity":"bonferroni"}}
        try:
            result["population_layer"] = analyse_spec(population)
        except (ValueError, RuntimeError, KeyError, TypeError, ArithmeticError) as exc:
            result["population_unavailable_reason"] = 'Population analysis failed: '+str(exc)
    else:
        result["population_unavailable_reason"] = "iid sampling was not declared; no source-population guarantee"
    result["conformal_unavailable_reason"] = "No compatible reference and calibration manifest supplied"
    if calibration is not None:
        try:
            from .calibration_binding import validate_prepared_calibration
            validate_prepared_calibration(raw, calibration)
            allowed = {"reference_distribution","wasserstein_calibration_manifest","calibration_context"}
            if set(calibration) != allowed:
                raise ValueError("calibration must supply reference_distribution, wasserstein_calibration_manifest and calibration_context")
            calibrated_raw = {**raw, **calibration, "question_utility":{"enabled":False}}
            calibrated = analyse_spec(calibrated_raw)
            result["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"] = (
                calibrated["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"])
            result.pop("conformal_unavailable_reason")
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            result["conformal_unavailable_reason"] = str(exc)
    return result


def audit_histogram(raw, counts, result):
    spec = parse_spec(raw)
    problem = EmpiricalProblem(n=spec.n,panel=spec.panel,quantiles=spec.quantiles)
    targets = [spec.panel.panel_tail(t) for t in spec.thresholds]
    def total_width(p):
        bounds = [p.bounds(t) for t in targets]
        return sum(hi.fraction-lo.fraction for lo,hi in bounds)
    baseline = total_width(problem)
    recovery = result.get("one_question_recovery") or {}
    best = recovery.get("best_question")
    observed = guaranteed = answer = residual = None
    conditioned = None
    if best:
        candidate = np.zeros(problem.k)
        candidate[int(best["cut_index"])+1:] = 1
        answer = int(candidate @ counts)
        conditioned = problem.with_equality(candidate, answer)
        residual = total_width(conditioned)
        observed = baseline-residual
        guaranteed = best["minimax_width_reduction"]
    all_counts = problem
    for target in targets:
        all_counts = all_counts.with_equality(target,int(target@counts))
    histogram = []
    comparisons = []
    for threshold, target in zip(spec.thresholds,targets):
        histogram.append(dict(threshold=threshold,recorded=float(target@counts/spec.n),
                              latent_lower=float(spec.panel.latent_tail(threshold,upper=False)@counts/spec.n),
                              latent_upper=float(spec.panel.latent_tail(threshold,upper=True)@counts/spec.n)))
        comparisons.append(dict(
            threshold=threshold,
            summary_recorded_bounds=[x.fraction for x in problem.bounds(target)],
            one_count_recorded_bounds=None if conditioned is None else
            [x.fraction for x in conditioned.bounds(target)],
            all_target_recorded_bounds=[x.fraction for x in all_counts.bounds(target)],
            known_recorded_fraction=float(target@counts/spec.n)))
    return dict(summary_only_width=baseline, additional_count_answer=answer,
                one_count_residual_width=residual, guaranteed_gain=guaranteed,observed_gain=observed,
                all_target_counts_width=total_width(all_counts),
                full_histogram_recorded_width=0.0,full_histogram=histogram,
                per_threshold=comparisons,
                interpretation="A full category histogram does not identify concentrations within censored or interval categories.")


def _flatten(records):
    from .report import _sample_count_ranges

    flat = []
    for record in records:
        common = {k:record.get(k) for k in ("cohort_id","panel_id","status","reason","runtime_seconds")}
        if record["status"] != "ok":
            flat.append(common)
            continue
        result = record["result"]
        population = result if result.get('mode') == 'population' else result.get('population_layer', {})
        pop = population.get('threshold_results', [])
        conf = result.get("assumption_dependent_scenarios",{}).get("wasserstein_ambiguity_set",{})
        conf_rows = conf.get("threshold_results",[])
        for i,item in enumerate(result["reporting_uncertainty_envelope"]["envelope"]):
            a = item["panel_recorded_estimand"]; latent = item["latent_interval_estimand"]
            row = dict(common,threshold=item["threshold"],unit="mg/L",n=result["sample_size"],
                       sample_lower_count=a["lower"]["count"],sample_upper_count=a["upper"]["count"],
                       sample_lower=a["lower"]["fraction"],sample_upper=a["upper"]["fraction"],
                       sample_count_components=json.dumps(_sample_count_ranges(result, item)),
                       latent_count_components=json.dumps(_sample_count_ranges(result, item, 'latent_interval_estimand')),
                       latent_lower=latent["lower"]["fraction"],latent_upper=latent["upper"]["fraction"],
                       population_reason=result.get("population_unavailable_reason",""),
                       conformal_reason=result.get("conformal_unavailable_reason",""))
            decision = next((d for d in result.get("decision_results", []) if d["threshold"] == item["threshold"]), None)
            if decision:
                row.update(decision_operator=decision["decision_operator"], decision_fraction=decision["decision_fraction_text"],
                           sample_decision=decision["sample"]["status"], population_decision=decision["population"]["status"],
                           conformal_decision=decision["conformal"]["status"])
            if pop:
                interval = pop[i]["exact_count_confidence"]
                exact = interval.get("simultaneous_bonferroni") or interval["marginal"]
                row.update(population_lower=exact["confidence_set_hull"][0],
                           population_upper=exact["confidence_set_hull"][1],
                           population_confidence_components=json.dumps(exact['confidence_set_components']),
                           population_family_confidence=interval["marginal"]["confidence_level"])
            if conf_rows and conf_rows[i].get("envelope"):
                row.update(conformal_lower=conf_rows[i]["envelope"]["lower"],
                           conformal_upper=conf_rows[i]["envelope"]["upper"],
                           conformal_guarantee_class=conf.get('guarantee_class'),
                           conformal_confidence_level=(conf.get('calibration_manifest') or {}).get('confidence_level'),
                           conformal_scope=(conf.get('calibration_manifest') or {}).get('guarantee_scope'))
            utility = result.get("one_question_recovery") or {}
            best = utility.get("best_question") or {}
            row.update(search_complete=utility.get("search_complete"),question=best.get("question"),
                       guaranteed_gain=best.get("minimax_width_reduction"),
                       observed_gain=record.get("reporting_audit",{}).get("observed_gain"))
            update = result.get("additional_information", {})
            row.update(additional_count_status=update.get("status", "not requested"),
                       returned_count_observed_gain=update.get("observed_width_reduction"),
                       additional_count_reason=update.get("reason", ""))
            if "decision_plan" in result:
                plan = result["decision_plan"]
                next_question = plan.get("next_question") or {}
                row.update(decision_plan_status=plan["status"],
                           decision_plan_scope=plan["scope"],
                           decision_plan_worst_case_cost=plan.get("worst_case_cost"),
                           decision_plan_worst_case_cost_exact=plan.get("worst_case_cost_exact"),
                           decision_plan_fixed_cost=plan.get("fixed_plan_cost"),
                           decision_plan_fixed_optimality_verified=plan.get("fixed_plan_optimality_verified", False),
                           decision_plan_cost_interpretation=plan.get("cost_interpretation"),
                           decision_plan_optimality_verified=plan.get("optimality_verified", False),
                           decision_plan_next_threshold=next_question.get("threshold"),
                           decision_plan_next_unit=next_question.get("unit"),
                           decision_plan_next_cost=next_question.get("cost"),
                           decision_plan_reason=plan.get("reason"))
            flat.append(row)
    return flat


def _input_issues(group, cid, panels, panel_errors, targets, command):
    """Collect independent missing fields before numerical analysis is attempted."""
    issues = []
    def issue(field, message):
        entry = {'field': field, 'message': message}
        if entry not in issues:
            issues.append(entry)
    pids = {str(r.get('panel_id', '')).strip() for r in group}
    if len(pids) != 1:
        issue('panel_id', 'panel_id must agree for all rows in a cohort')
    for pid in pids:
        if pid in panel_errors:
            issue('panel_id', f'panel {pid}: {panel_errors[pid]}')
        elif pid not in panels:
            issue('panel_id', f'Missing panel {pid}; add its explicit categories and unit to panels.csv')
    keys = ('variant_id', 'n', 'mic50', 'mic90', 'rank_convention') if command == 'batch' else ('category', 'count', 'rank_convention')
    for index, row in enumerate(group, 1):
        for key in keys + (('rank50', 'rank90') if row.get('rank_convention') == 'explicit' else ()):
            if not str(row.get(key, '')).strip():
                issue(key, f'Missing {key} in input row {index} for cohort {cid}; complete this field in the CSV template')
    if cid not in targets:
        issue('targets', 'Missing targets; add at least one threshold for this cohort_id')
    for index, row in enumerate(targets.get(cid, []), 1):
        if row.get('target_scale', 'recorded') not in ('', 'recorded'):
            issue('target_scale', 'Questions within measurement intervals use the distribution workflow; no recorded-category substitution was made')
        for key in ('threshold', 'unit'):
            if not str(row.get(key, '')).strip():
                issue(key, f'Missing {key} in target row {index}; complete targets.csv')
        try:
            parse_criterion(row)
        except ValueError as exc:
            issue('decision', str(exc))
    return issues


def _decision_queries(raw, rows, exclude_direct, allow_zero=False):
    """Validate every declared query before applying the acquisition restriction."""
    if rows is None and not exclude_direct:
        return None
    spec = parse_spec(raw)
    if rows is None:
        rows = [dict(threshold=b.panel_value, unit="mg/L", cost="1") for b in spec.panel.bins[:-1]]
    targets = {tuple(spec.panel.panel_tail(t)) for t in spec.thresholds}
    result, seen = [], set()
    for row in rows:
        if set(row) != {"threshold", "unit", "cost"}:
            raise ValueError("Decision query fields must be threshold, unit and cost")
        threshold = _number(_required(row, "threshold"), "Decision query threshold")
        if threshold <= 0:
            raise ValueError("Decision query threshold must be positive")
        unit = _unit(_required(row, "unit"))
        try:
            cost = Fraction(_required(row, "cost"))
            display_cost = float(cost)
            if cost < 0 or (cost == 0 and not allow_zero) or not isfinite(display_cost):
                raise ValueError
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError("Decision query cost must be finite and positive") from exc
        cut = tuple(spec.panel.panel_tail(threshold))
        if cut in seen:
            raise ValueError("Duplicate or equivalent decision query cuts; supply one cost per recorded tail")
        seen.add(cut)
        if not exclude_direct or cut not in targets:
            result.append(dict(threshold=threshold, unit=unit, cost=str(cost)))
    return result


def _attach_decision_plan(result, raw, criteria, rows, observations, settings, error=None):
    """Keep optional acquisition planning failures separate from valid analysis."""
    acquisition = settings.get("acquisition", False)
    key = "acquisition_plan" if acquisition else "decision_plan"
    try:
        if error:
            raise ValueError(error)
        if not settings["enabled"]:
            raise ValueError("--decision-queries requires --decision-plan")
        if observations and result.get("additional_information", {}).get("status") != "applied":
            raise ValueError("Returned-count analysis is unavailable; the displayed basic results use the original summaries")
        queries = _decision_queries(raw, rows, settings["exclude_direct_targets"], allow_zero=acquisition)
        from .decision_planning import plan_decisions
        from .acquisition import plan_acquisition
        planner = plan_acquisition if acquisition else plan_decisions
        extra = dict(round_cost=settings["round_cost"]) if acquisition else {}
        result[key] = planner(
            raw, criteria, queries=queries, additional_counts=observations,
            time_limit_seconds=settings["time_limit_seconds"], max_states=settings["max_states"], **extra)
        if acquisition and result[key]["status"] in {"optimal", "already_resolved"}:
            remaining = max(0, float(settings["time_limit_seconds"])-result[key]["search"]["elapsed_seconds"])
            try:
                comparison = plan_acquisition(raw, criteria, queries=queries, additional_counts=observations,
                    round_cost=settings["round_cost"], time_limit_seconds=remaining,
                    max_states=settings["max_states"], max_batch_size=1)
            except (ValueError, RuntimeError, ArithmeticError) as exc:
                comparison = dict(status="unavailable", reason=str(exc))
            result[key]["sequential_comparison"] = {k:comparison.get(k) for k in
                ("status","worst_case_cost","worst_case_cost_exact","optimality_verified","maximum_rounds","reason")}
    except (ValueError, RuntimeError, TypeError, KeyError, ArithmeticError) as exc:
        result[key] = dict(
            status="unavailable", available=False, scope="recorded_sample_decisions",
            sample_size=result["sample_size"], criteria=criteria,
            worst_case_cost=None, worst_case_cost_exact=None, fixed_plan_cost=None,
            cost_interpretation="unavailable", optimality_verified=False, next_question=None,
            impossibility_witness=None, method="integer_prefix_decision_tree",
            reason="Decision planning unavailable: " + str(exc),
            search=dict(states=0, elapsed_seconds=0, complete=False), policy=None)


def run_csv_workflow(args):
    from .file_safety import check_output_paths
    destination = Path(args.output_dir)
    check_output_paths(
        [args.input, args.panels, args.targets, args.calibrations,
         getattr(args, "additional_counts", None), getattr(args, "decision_queries", None)],
        [destination / name for name in ("configuration.json", "results.json", "results.csv", "report.html", "requested_counts.csv")]
        + ([destination / name for name in ("reporting_counts.csv", "reporting_certificates.json")]
           if getattr(args, "reporting_plan", False) else []))
    from .report_pages import validate_page_size
    page_size = validate_page_size(getattr(args, "report_page_size", 50))
    delimiter_name = getattr(args, "delimiter", "comma")
    delimiter = {"comma": ",", "semicolon": ";", "tab": "\t"}[delimiter_name]
    fail_on_refusal = getattr(args, "fail_on_refusal", False)
    rows = read_csv(args.input, delimiter=delimiter)
    panel_rows=read_csv(args.panels, delimiter=delimiter)
    target_rows=read_csv(args.targets, delimiter=delimiter)
    count_path = getattr(args, "additional_counts", None)
    count_rows = [] if count_path is None else read_csv(count_path, delimiter=delimiter)
    if count_path is not None and not count_rows:
        raise ValueError("Additional counts CSV is empty; supply counts or omit --additional-counts")
    fields=('cohort_id','panel_id','category','count','rank_convention') if args.command=='reporting-audit' else (
        'cohort_id','panel_id','variant_id','n','mic50','mic90','rank_convention')
    missing=_missing_join_issues(rows,'cohort_id',fields,Path(args.input).name)
    missing+=_missing_join_issues(panel_rows,'panel_id',
        ('panel_id','unit','category','panel_value','lower_closed','upper_closed'),Path(args.panels).name)
    missing+=_missing_join_issues(target_rows,'cohort_id',('cohort_id','threshold','unit'),Path(args.targets).name)
    if count_path is not None:
        missing+=_missing_join_issues(count_rows,'cohort_id',('cohort_id','threshold','unit','n'),Path(count_path).name)
    if missing:
        raise ValueError('Input preflight failed: '+'; '.join(missing)+
            '; complete these CSV fields. Rows without join identifiers cannot be assigned; no cohorts were analysed')
    groups = _groups(rows,"cohort_id")
    if not groups:
        raise ValueError("input CSV contains no cohorts")
    query_path = getattr(args, "decision_queries", None)
    planning = dict(enabled=getattr(args, "decision_plan", False) or getattr(args, "acquisition_plan", False)
                            or getattr(args, "reporting_plan", False),
                    acquisition=getattr(args, "acquisition_plan", False),
                    reporting=getattr(args, "reporting_plan", False),
                    round_cost=getattr(args, "round_cost", "0"),
                    time_limit_seconds=getattr(args, "decision_plan_time_limit", 5.0),
                    max_states=getattr(args, "decision_plan_max_states", 5000),
                    exclude_direct_targets=args.exclude_direct_targets)
    planning_requested = planning["enabled"] or query_path is not None
    query_groups, query_error, query_source = None, None, None
    if query_path is not None:
        query_source = dict(filename=Path(query_path).name, sha256=None)
        try:
            query_source["sha256"] = sha256(Path(query_path).read_bytes()).hexdigest()
            query_rows = read_csv(query_path, delimiter=delimiter,
                                  expected_fields=("cohort_id", "threshold", "unit", "cost"))
            query_groups = _groups(query_rows, "cohort_id")
        except (OSError, ValueError, UnicodeError, csv.Error) as exc:
            query_error = str(exc)
            query_source["error"] = query_error
    panels, panel_errors = load_panels(args.panels, delimiter=delimiter)
    targets = _groups(target_rows,"cohort_id")
    counts_by_cohort = _groups(count_rows, "cohort_id")
    calibrations = {} if not args.calibrations else json.loads(Path(args.calibrations).read_text(encoding="utf-8"))
    if not isinstance(calibrations,dict):
        raise ValueError("calibrations must map cohort identifiers to calibration inputs")
    options = dict(enabled=True,exclude_direct_target_questions=args.exclude_direct_targets,
                   time_limit_seconds=args.question_time_limit)
    records, configs = [], []
    for cid, group in groups.items():
        start = perf_counter()
        record = {"cohort_id":cid,"panel_id":group[0].get("panel_id","")}
        try:
            issues = _input_issues(group,cid,panels,panel_errors,targets,args.command)
            if issues:
                record['input_issues'] = issues
                raise ValueError('; '.join(x['message'] for x in issues))
            pid = _consistent(group,"panel_id")
            if pid in panel_errors:
                raise ValueError(f"panel {pid}: {panel_errors[pid]}")
            if pid not in panels:
                raise ValueError(f"Missing panel {pid}; add its explicit categories and unit to panels.csv")
            if cid not in targets:
                raise ValueError("Missing targets; add at least one threshold for this cohort_id")
            thresholds, criteria = [], []
            for row in targets[cid]:
                _unit(_required(row,"unit"))
                t = _number(_required(row,"threshold"),"threshold")
                if t <= 0 or t in thresholds:
                    raise ValueError("thresholds must be positive and unique per cohort")
                thresholds.append(t)
                criteria.append(parse_criterion(row))
            iid_text = _consistent(group,"iid","false") or "false"
            iid = _boolean(iid_text,"iid")
            confidence = _number(_consistent(group,"confidence_level","0.95") or ".95","confidence_level")
            if not 0 < confidence < 1:
                raise ValueError("confidence_level must lie strictly between zero and one")
            if args.command == "reporting-audit":
                raw, counts = counts_spec(group,panels[pid],thresholds,options)
            else:
                raw = summary_spec(group,panels[pid],thresholds,options)
            provenance = {key:_consistent(group,key) for key in ('organism','antimicrobial','source_doi','source_location','metadata_basis','rank_basis','panel_basis')
                          if any(str(row.get(key,'')).strip() for row in group)}
            from .input_context import add_context
            add_context(provenance, dict(cohort_id=cid, iid=iid,
                sample_context=_consistent(group, 'sample_context', '')), targets[cid])
            record['provenance'] = provenance
            configs.append(dict(cohort_id=cid,specification=raw,iid=iid,confidence_level=confidence,
                                calibration=calibrations.get(cid),decisions=criteria,provenance=provenance,
                                additional_counts=[{k:v for k,v in row.items() if k != 'cohort_id'} for row in counts_by_cohort.get(cid,[])]))
            if planning_requested:
                plan_criteria = [dict(threshold=t, unit="mg/L", decision_operator=criterion["decision_operator"],
                                      decision_fraction=criterion["decision_fraction_text"])
                                 for t, criterion in zip(thresholds, criteria) if criterion is not None]
                plan_queries = None if query_path is None else [
                    {k: v for k, v in row.items() if k != "cohort_id"}
                    for row in (query_groups or {}).get(cid, [])]
                configs[-1]["decision_planning"] = dict(criteria=plan_criteria, queries=plan_queries,
                                                        query_input_error=query_error)
            calibration, calibration_error = calibrations.get(cid), None
            if calibration is not None:
                try:
                    from .calibration_binding import validate_prepared_calibration
                    validate_prepared_calibration(raw, calibration, cohort_id=cid, panel_id=pid)
                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                    calibration, calibration_error = None, str(exc)
            if cid in counts_by_cohort:
                from .count_updates import analyse_with_counts
                result = analyse_with_counts(raw, configs[-1]['additional_counts'], iid=iid,
                                             confidence=confidence, calibration=calibration)
            else:
                result = analyse_layers(raw,iid,confidence,calibration)
            if calibration_error:
                result['conformal_unavailable_reason'] = calibration_error
                result['inference_requested']['calibration'] = True
            result['decision_results'] = decision_results(result,criteria)
            if planning_requested:
                optional_error = query_error
                if (planning["acquisition"] or planning["reporting"]) and cid.startswith(("=", "+", "-", "@")):
                    optional_error = ("The cohort identifier cannot be exported safely to the editable request CSV. "
                                      "Use an identifier starting with a letter or digit consistently in the input tables; "
                                      "basic results retain the original identifier.")
                if planning["reporting"]:
                    try:
                        if optional_error:
                            raise ValueError(optional_error)
                        from .sufficient_reporting import plan_reporting
                        permitted = _decision_queries(raw, plan_queries, planning["exclude_direct_targets"], allow_zero=True)
                        result["reporting_plan"] = plan_reporting(raw, counts, plan_criteria, queries=permitted,
                            time_limit_seconds=planning["time_limit_seconds"], max_states=planning["max_states"])
                    except (ValueError, RuntimeError, TypeError, KeyError, ArithmeticError) as exc:
                        result["reporting_plan"] = dict(status="unavailable", sufficient=False,
                            optimality_verified=False, disclosures=[], reason=str(exc))
                else:
                    _attach_decision_plan(result, raw, plan_criteria, plan_queries,
                                          configs[-1]["additional_counts"], planning, optional_error)
            record.update(status="ok",result=result)
            if args.command == "reporting-audit":
                record["reporting_audit"] = audit_histogram(raw,counts,result)
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            record.update(status="refused",reason=str(exc))
            if hasattr(exc, "conflict_details"):
                record['conflict_details'] = exc.conflict_details
        record["runtime_seconds"] = perf_counter()-start
        records.append(record)
    for cid in sorted((set(targets)|set(calibrations)|set(counts_by_cohort))-set(groups)):
        records.append(dict(cohort_id=cid,status="refused",reason="Orphan identifier: no input cohort matches target/calibration/additional-count rows",runtime_seconds=0))
    destination = Path(args.output_dir)
    destination.mkdir(parents=True,exist_ok=True)
    paths = {"input":args.input,"panels":args.panels,"targets":args.targets}
    if args.calibrations:
        paths["calibrations"] = args.calibrations
    if count_path is not None:
        paths["additional_counts"] = count_path
    hashes = {k:{"filename":Path(v).name,"sha256":sha256(Path(v).read_bytes()).hexdigest()} for k,v in paths.items()}
    if query_source is not None:
        hashes["decision_queries"] = query_source
    configuration = dict(version=__version__,command=args.command,inputs=hashes,options=options,cohorts=configs,
                         report_page_size=page_size,
                         csv_delimiter=delimiter_name,fail_on_refusal=fail_on_refusal,
                         records_total=len(records),records_ok=sum(r["status"]=="ok" for r in records))
    if planning_requested:
        configuration["decision_planning"] = dict(
            planning, query_input_error=query_error,
            unmatched_query_cohorts=sorted(set(query_groups or {}) - set(groups)))
    for filename,value in (("configuration.json",configuration),("results.json",records)):
        (destination/filename).write_text(json.dumps(json_safe(value),indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    flat = _flatten(records)
    if planning["reporting"]:
        by_id = {r["cohort_id"]:r for r in records}
        for row in flat:
            plan = by_id[row["cohort_id"]].get("result", {}).get("reporting_plan", {})
            row.update(reporting_plan_status=plan.get("status"), reporting_cost=plan.get("report_cost"),
                       reporting_sufficient=plan.get("sufficient", False),
                       reporting_optimality_verified=plan.get("optimality_verified", False),
                       reporting_count_fields=len(plan.get("disclosures", [])))
        certificates = []
        with (destination/"reporting_counts.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["cohort_id", "threshold", "unit", "count", "n"], delimiter=delimiter)
            writer.writeheader()
            for config in configs:
                plan = by_id[config["cohort_id"]].get("result", {}).get("reporting_plan", {})
                if not plan.get("sufficient"):
                    continue
                for answer in plan["disclosures"]:
                    writer.writerow(dict(cohort_id=config["cohort_id"], **answer))
                certificates.append(dict(cohort_id=config["cohort_id"], specification=config["specification"],
                    criteria=config["decision_planning"]["criteria"], disclosures=plan["disclosures"],
                    verification=plan["verification"]))
        (destination/"reporting_certificates.json").write_text(json.dumps(
            dict(version=__version__, certificates=certificates), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    if planning["acquisition"]:
        for row in flat:
            record = next((r for r in records if r.get("cohort_id") == row.get("cohort_id")), {})
            plan = record.get("result", {}).get("acquisition_plan", {})
            row.update(acquisition_status=plan.get("status"),
                       acquisition_remaining_cost=plan.get("worst_case_cost"),
                       acquisition_optimality_verified=plan.get("optimality_verified"),
                       acquisition_maximum_rounds=plan.get("maximum_rounds"),
                       acquisition_maximum_counts=plan.get("maximum_counts"),
                       acquisition_cost_lower_bound=plan.get("cost_lower_bound"),
                       acquisition_cost_upper_bound=plan.get("cost_upper_bound"),
                       acquisition_cost_gap=plan.get("cost_gap"))
        with (destination/"requested_counts.csv").open("w",encoding="utf-8",newline="") as stream:
            information_fields = ["count", "count_min", "count_max", "percentage", "decimal_places", "rounding_rule", "source"]
            writer = csv.DictWriter(stream,fieldnames=["cohort_id","threshold","unit","count","n",*information_fields[1:]],delimiter=delimiter)
            writer.writeheader()
            for record in records:
                plan = record.get("result",{}).get("acquisition_plan",{})
                for answer in plan.get("additional_counts",[]):
                    information = {k: answer[k] for k in information_fields if k in answer}
                    if "percentage" in answer:
                        information.pop("count_min", None)
                        information.pop("count_max", None)
                    # Sources are annotations; escape formula-like text only in
                    # the editable spreadsheet export. Preserve JSON verbatim.
                    if str(information.get("source", "")).startswith(("=", "+", "-", "@")):
                        information["source"] = "'" + information["source"]
                    writer.writerow(dict(cohort_id=record["cohort_id"],threshold=answer["threshold"],
                                         unit=answer["unit"],n=plan["sample_size"], **information))
                for question in plan.get("next_questions",[]):
                    writer.writerow(dict(cohort_id=record["cohort_id"],threshold=question["threshold"],
                                         unit=question["unit"],count="",n=plan["sample_size"]))
    fields = list(dict.fromkeys(k for r in flat for k in r))
    with (destination/"results.csv").open("w",encoding="utf-8",newline="") as f:
        writer = csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for row in flat:
            # Preserve untrusted identifiers as text when opened in a spreadsheet.
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(("=","+","-","@")) else v)
                             for k,v in row.items()})
    from .report import render_batch_html
    render_batch_html(records,configuration,destination/"report.html",page_size=page_size)
    return 2 if fail_on_refusal and any(r["status"] == "refused" for r in records) else 0
