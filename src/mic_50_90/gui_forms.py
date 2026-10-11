"""Lossless desktop input adapters using the existing scientific contracts."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from math import isfinite
from types import SimpleNamespace

from .count_updates import _observations, available_observations
from .decisions import parse_criterion
from .distribution_workflow import _validate_saved_update
from .model import MICPanel, QuantileSummary
from .validation import boolean, exact_integer, identifier
from .workflows import _unit


def decode_payload(text):
    """Retain exact decimal input tokens before normal JSON floats can round them."""
    def exact_path(path):
        if path[:1] == ("certificate",):
            return path[-1] in {"decision_fraction", "n", "rank", "probability",
                                "count", "count_min", "count_max", "percentage", "decimal_places"}
        if path[:2] == ("config", "targets") and path[-1] == "decision_fraction":
            return True
        if path == ("config", "n"):
            return True
        if path[:1] == ("config",):
            return ((path[1:2] in {("summaries",), ("reporting_envelope",)} and "quantiles" in path and path[-1] in {"rank", "probability"})
                    or (path[1:2] == ("additional_counts",) and path[-1] in {"n", "count", "count_min", "count_max", "percentage", "decimal_places"}))
        return ((path[:1] == ("targets",) and path[-1] == "decision_fraction")
                or (path[:1] == ("histogram",) and path[-1] == "count")
                or (path[:1] == ("options",) and path[-1] in {"precision_pp", "cost", "round_cost", "decision_plan_max_states"}))
    def convert(value, path=()):
        if isinstance(value, dict):
            return {name: convert(item, path + (name,)) for name, item in value.items()}
        if isinstance(value, list):
            return [convert(item, path + (index,)) for index, item in enumerate(value)]
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("Nonfinite JSON numbers are not accepted.")
            if exact_path(path):
                return str(value)
            number = float(value)
            if not isfinite(number):
                raise ValueError("Numeric input exceeds the supported finite range.")
            return number
        return value
    return convert(json.loads(text, parse_float=Decimal, parse_constant=Decimal))


def _canonical_count_row(raw):
    """Share optional-blank and exact-integer handling without guessing evidence."""
    row = deepcopy(raw)
    if not isinstance(row, dict):
        return row  # The count contract reports malformed rows.
    for key in ("count", "count_min", "count_max", "percentage", "decimal_places", "rounding_rule"):
        value = row.get(key)
        if value is None or isinstance(value, str) and not value.strip():
            row.pop(key, None)
    for key in ("n", "count", "count_min", "count_max", "decimal_places"):
        if key in row:
            row[key] = exact_integer(row[key], key)
    return row


def canonical_distribution_input(raw):
    """Normalise exact representations for saved updates, without adding evidence.

    A browser may represent an integer as text. This does not change the sample.
    Unknown fields and source annotations remain intact in both representations;
    the original uploaded payload is also saved separately without modification.
    """
    result = deepcopy(raw)
    result["n"] = exact_integer(result["n"], "n", 1)
    result.setdefault("iid", False)
    result["confidence_level"] = float(result.get("confidence_level", .95))
    summaries = [result.setdefault("summaries", {}),
                 *(v["summaries"] for v in result.get("reporting_envelope", {}).get("variants", []))]
    for summary in summaries:
        summary.setdefault("quantiles", [])
        for quantile in summary["quantiles"]:
            text = format(Decimal(str(quantile["probability"])), "f")
            quantile["probability"] = text.rstrip("0").rstrip(".") if "." in text else text
            if "rank" in quantile:
                quantile["rank"] = exact_integer(quantile["rank"], "rank", 1)
    result["additional_counts"] = [_canonical_count_row(row) for row in result.get("additional_counts", [])]
    return result


def _same_json_semantics(left, right):
    """Allow JSON number spelling changes, but not booleans or changed values."""
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same_json_semantics(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same_json_semantics(a, b) for a, b in zip(left, right))
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    return type(left) is type(right) and left == right


def _original_json(text):
    if not isinstance(text, str):
        raise ValueError("Original input must be uploaded as JSON text.")
    result = json.loads(text)
    json.dumps(result, allow_nan=False)
    if not isinstance(result, dict):
        raise ValueError("Original input must contain a JSON object.")
    return result


def _restore_calibration(payload):
    """Restore uploaded JSON numeric types before checking prepared hashes.

    JavaScript serialises 1.0 as 1. Prepared hash objects must keep their original
    Python JSON representation. The preserved text is used only when every
    value still agrees with the editable form; it cannot override changed data.
    """
    source = _original_json(payload["calibration_input_text"])
    if source.get("format") == "mic-50-90-guided-input":
        source = source["payload"]
    if "config" in source:
        source = source["config"]
    if "inputs" in source:
        key = payload["config"].get("cohort_id", "cohort")
        matches = [row for row in source["inputs"] if row.get("cohort_id", "cohort") == key]
        if len(matches) != 1:
            raise ValueError("Original calibration input must identify the same single cohort.")
        source = matches[0]
    for key in ("reference_distribution", "wasserstein_calibration_manifest", "calibration_context"):
        if key not in source or key not in payload["config"]:
            raise ValueError("Original calibration input must contain the reference, manifest and context.")
        if not _same_json_semantics(source[key], payload["config"][key]):
            raise ValueError("Prepared calibration values differ from the original uploaded input. Reimport a complete matching calibration; no value was replaced.")
    for key in ("reference_distribution", "wasserstein_calibration_manifest", "calibration_context"):
        payload["config"][key] = deepcopy(source[key])


def _restore_previous_configuration(payload):
    source = _original_json(payload["previous_configuration_text"])
    current = payload["previous"]["configuration"]
    left, right = deepcopy(source), deepcopy(current)
    for config in (left, right):
        config["inputs"] = [canonical_distribution_input(raw) for raw in config["inputs"]]
    if not _same_json_semantics(left, right):
        raise ValueError("The previous configuration differs from its uploaded original. Reopen its matching files.")
    payload["previous"]["configuration"] = source


def validate_payload(value):
    """Collect actionable input issues without guessing missing scientific data.

    The config object remains unchanged, including user provenance and advanced
    settings. This adapter validates the supported desktop workflows; actual
    analyses and optional-layer failure handling stay in the existing engine.
    """
    issues, warnings = [], []

    def check(field, action):
        try:
            return action()
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RuntimeError) as exc:
            issues.append({"field": field, "message": str(exc)})
            return None

    if not isinstance(value, dict):
        return {"valid": False, "issues": [{"field": "input", "message": "Supply a JSON object."}],
                "warnings": [], "config": None, "payload": None}
    payload = deepcopy(value)
    if payload.get("mode") == "verify-report" and "certificate_json" in payload:
        def restore_certificate():
            original = payload["certificate_json"]
            if not isinstance(original, str):
                raise ValueError("The original certificate must be JSON text.")
            payload["certificate"] = decode_payload('{"certificate":' + original + '}')["certificate"]
        check("certificate_json", restore_certificate)
        if issues:
            return dict(valid=False, issues=issues, warnings=warnings, config=None, payload=payload)
    if payload.get("input_format") == "tables" or payload.get("mode") == "verify-report":
        from .gui_documents import validate_document
        return validate_document(payload)
    check("input", lambda: json.dumps(payload, allow_nan=False))
    mode = payload.get("mode", "distribution")
    if mode not in {"distribution", "batch", "reporting-audit"}:
        issues.append({"field": "mode", "message": "Choose distribution, batch or reporting-audit."})
    raw = payload.get("config")
    if not isinstance(raw, dict):
        issues.append({"field": "config", "message": "Supply the analysis input as a JSON object."})
        return {"valid": False, "issues": issues, "warnings": warnings, "config": raw, "payload": payload}
    if "calibration_input_text" in payload:
        check("calibration_input_text", lambda: _restore_calibration(payload))
    if "previous_configuration_text" in payload:
        check("previous_configuration_text", lambda: _restore_previous_configuration(payload))
    n = check("config.n", lambda: exact_integer(raw.get("n"), "Sample size n", 1))
    check("config.unit", lambda: _unit(raw.get("unit")))
    panel = check("config.panel", lambda: MICPanel.from_dict(raw.get("panel", {})))
    check("config.cohort_id", lambda: identifier(raw.get("cohort_id", "cohort"), "cohort_id"))
    check("config.iid", lambda: boolean(raw.get("iid", False), "Independent sampling declaration"))
    from .input_context import sample_context, threshold_note
    check("config.sample_context", lambda: sample_context(raw.get("sample_context")))
    confidence = raw.get("confidence_level", .95)
    def check_confidence():
        if isinstance(confidence, bool) or not isfinite(float(confidence)) or not 0 < float(confidence) < 1:
            raise ValueError("Confidence level must lie strictly between 0 and 1.")
    check("config.confidence_level", check_confidence)
    options = payload.get("options", {})
    if not isinstance(options, dict):
        issues.append({"field": "options", "message": "Analysis options must be a JSON object."})
        options = {}
    if mode == 'distribution':
        from .distribution_options import option_issues
        for name, message in option_issues(options, categories=len(panel.bins) if panel is not None else None).items():
            issues.append({'field': 'options.' + name, 'message': message})
    # Options are preserved, but the desktop worker never interprets them as paths.
    distribution_fields = {"population_method", "population_time_limit", "population_tolerance_pp", "precision_pp", "population_precision_pp", "population_count_plan", "population_minimum_bins", "population_planning_time_limit"}
    allowed = distribution_fields if mode == "distribution" else {
        "question_time_limit", "report_page_size", "exclude_direct_targets", "decision_plan", "acquisition_plan",
        "reporting_plan", "round_cost", "decision_plan_time_limit", "decision_plan_max_states"}
    # The guided form keeps the distribution settings of a hidden view; they are not user choices for this workflow.
    ignored = distribution_fields if mode in ("batch", "reporting-audit") else set()
    for name in options.keys() - allowed - ignored:
        warnings.append({"field": "options." + name, "message": "This option is retained in the saved input but is not used by this workflow."})
    if mode in {"distribution", "batch"}:
        summaries = raw.get("summaries", {})
        variants = raw.get("reporting_envelope", {}).get("variants", []) if isinstance(raw.get("reporting_envelope", {}), dict) else []
        if not isinstance(variants, list):
            variants = []  # The engine reports the malformed envelope below.
        for vi, variant in enumerate([{"summaries": summaries}, *variants]):
            source = variant.get("summaries", {}) if isinstance(variant, dict) else {}
            quantiles = source.get("quantiles", []) if isinstance(source, dict) else []
            if not isinstance(quantiles, list):
                issues.append({"field": f"config.quantiles.{vi}", "message": "Quantiles must be a list."})
                continue
            for qi, q in enumerate(quantiles):
                field = f"config.quantiles.{vi}.{qi}"
                if not isinstance(q, dict) or not ("convention" in q or "rank" in q):
                    issues.append({"field": field, "message": "Specify the source quantile convention or an explicit rank; it is not guessed."})
                elif panel is not None and n is not None:
                    check(field, lambda q=q: QuantileSummary.from_dict(q, n=n, panel=panel))
            if mode == "batch":
                def summary_pair():
                    if len(quantiles) != 2 or sorted(Decimal(str(q.get("probability"))) for q in quantiles) != [Decimal("0.5"), Decimal("0.9")]:
                        raise ValueError("Threshold questions require MIC50 and MIC90 in each reporting variant; use the distribution view for counts-only information.")
                check(f"config.quantiles.{vi}", summary_pair)
        observations = raw.get("additional_counts", [])
        if not isinstance(observations, list):
            issues.append({"field": "config.additional_counts", "message": "Additional counts must be a list."})
        elif panel is not None and n is not None:
            for index, row in enumerate(observations):
                if mode == 'distribution':
                    item = check(f"config.additional_counts.{index}", lambda row=row: available_observations([_canonical_count_row(row)], SimpleNamespace(n=n, panel=panel)))
                    if item:
                        warnings.extend(dict(field=f'config.additional_counts.{index}', message=issue['reason']) for issue in item[1])
                else:
                    check(f"config.additional_counts.{index}", lambda row=row: _observations([_canonical_count_row(row)], SimpleNamespace(n=n, panel=panel)))
        if not isinstance(raw.get("reporting_envelope", {}), dict) or not isinstance(raw.get("reporting_envelope", {}).get("variants", []), list):
            issues.append({"field": "config.reporting_envelope", "message": "The reporting envelope must contain a variants list."})
        if not observations and not any(isinstance(v, dict) and isinstance(v.get("summaries", {}), dict) and
            (v.get("summaries", {}).get("quantiles") or v.get("summaries", {}).get("minimum") is not None or
             v.get("summaries", {}).get("maximum") is not None) for v in [{"summaries": summaries}, *variants]):
            issues.append({"field": "config", "message": "Supply summaries, an observed range or additional counts from the original sample."})
        # The solver is deliberately confined to the calculation process.
        # Structural validation in an HTTP handler must not call native solvers.
    elif mode == "reporting-audit":
        rows = payload.get("histogram")
        if not isinstance(rows, list) or not rows:
            issues.append({"field": "histogram", "message": "Supply every panel category and its count, including zeros."})
        else:
            labels, counts = [], []
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    issues.append({"field": f"histogram.{index}", "message": "Each row requires category and count."})
                    continue
                labels.append(row.get("category"))
                count = check(f"histogram.{index}.count", lambda row=row: exact_integer(row.get("count"), "Category count"))
                if count is not None:
                    counts.append(count)
            if panel is not None and (len(set(str(x) for x in labels)) != len(labels) or set(str(x) for x in labels) != set(panel.labels)):
                issues.append({"field": "histogram", "message": "List every panel category exactly once, including explicit zeros."})
            if len(counts) == len(rows) and (sum(counts) != n or sum(counts) < 2):
                issues.append({"field": "histogram", "message": "Counts must sum to the stated sample size, with at least two observations for the reporting audit."})
        if payload.get("rank_convention") != "ceiling":
            # The audit computes summaries; its definition must be explicit.
            issues.append({"field": "rank_convention", "message": "Declare ceiling ranks for summaries generated by the reporting audit."})
    if mode in {"batch", "reporting-audit"} or (mode == "distribution" and raw.get("targets")):
        targets = raw.get("targets") if mode == "distribution" else payload.get("targets")
        if not isinstance(targets, list) or not targets:
            issues.append({"field": "targets", "message": "Add at least one positive MIC threshold for the reporting audit."})
        else:
            seen = set()
            for index, row in enumerate(targets):
                def target(row=row):
                    if mode == 'distribution':
                        if panel is None:
                            return  # The missing panel is reported separately.
                        from .distribution_targets import normalize_target, target_key
                        metadata, _, _ = normalize_target(row, panel)
                        key = target_key(metadata)
                        if key in seen:
                            raise ValueError('Target thresholds and category ranges must be distinct')
                        seen.add(key)
                        if metadata['question_type'] == 'category_range':
                            return
                        note = threshold_note(row)
                        if 'not supplied' in note:
                            warnings.append({'field': f'targets.{index}', 'message': note})
                        return
                    if not isinstance(row, dict):
                        raise ValueError("Each target requires threshold and unit.")
                    if row.get('target_scale', 'recorded') != 'recorded':
                        raise ValueError('Questions within measurement intervals use the distribution workflow.')
                    _unit(row.get("unit"))
                    threshold = float(row.get("threshold"))
                    if isinstance(row.get("threshold"), bool) or not isfinite(threshold) or threshold <= 0 or threshold in seen:
                        raise ValueError("Target thresholds must be positive, finite and distinct.")
                    seen.add(threshold)
                    parse_criterion(row)
                    note = threshold_note(row)
                    if 'not supplied' in note:
                        warnings.append({"field": f"targets.{index}", "message": note})
                check(f"targets.{index}", target)
        if sum(bool(options.get(key, False)) for key in ("decision_plan", "acquisition_plan", "reporting_plan")) > 1:
            issues.append({"field": "options", "message": "Choose only one planning method."})
        for key in ("decision_plan", "acquisition_plan", "reporting_plan", "exclude_direct_targets"):
            if key in options:
                check("options." + key, lambda key=key: boolean(options[key], key))
        if mode == "batch" and options.get("reporting_plan"):
            issues.append({"field": "options.reporting_plan", "message": "Sufficient-report selection requires a full histogram. Choose a decision or acquisition plan for incomplete summaries."})
        unsupported = set(raw) & {"population", "question_utility", "thresholds", "mode", "contract_version", "wasserstein_radius"}
        if unsupported:
            issues.append({"field": "config", "message": "These advanced analysis settings cannot be silently converted to this desktop workflow: " + ", ".join(sorted(unsupported)) + ". Use the original command-line interface or provide the desktop fields explicitly."})
    if payload.get("previous") is not None:
        def previous():
            if mode != "distribution":
                raise ValueError("Saved same-sample updates are supported by the distribution workflow.")
            old = payload["previous"]
            configuration, results = old["configuration"], old["results"]
            if results.get("software") != "MIC-50-90" or results.get("software_version") != "1.0.0":
                raise ValueError("Use configuration and results from MIC-50-90 1.0.0.")
            from .result_schema import validate_distribution_schema
            validate_distribution_schema(results)
            inputs = configuration["inputs"]
            records = results["cohorts"]
            key = raw.get("cohort_id", "cohort")
            matching_input = [r for r in inputs if r.get("cohort_id", "cohort") == key]
            matching_result = [r for r in records if r.get("cohort_id", "cohort") == key]
            if len(matching_input) != 1 or len(matching_result) != 1:
                raise ValueError("The saved files must have one matching cohort with the same identifier.")
            canonical = canonical_distribution_input(raw)
            _validate_saved_update(canonical, {"input": canonical_distribution_input(matching_input[0]), "result": matching_result[0],
                "population_method": configuration["population_method"]}, options.get("population_method", "bonferroni"))
        check("previous", previous)
    return {"valid": not issues, "issues": issues, "warnings": warnings, "config": raw, "payload": payload}


def desktop_examples():
    """Small source-labelled examples shipped within the installed application."""
    summary = {"cohort_id": "controlled-20", "unit": "mg/L", "n": 20, "panel": {"levels": [1, 2]},
        "summaries": {"quantiles": [{"probability": .5, "category": "<=1", "convention": "ceiling"},
                                     {"probability": .9, "category": "2", "convention": "ceiling"}]},
        "iid": False, "confidence_level": .95}
    published = {"cohort_id": "Antibiotics-2023-12-289-coarse-counts", "n": 7133, "unit": "mg/L",
        "panel": {"categories": [
            {"label": "<=0.06", "lower_bound": None, "upper_bound": .06, "lower_closed": False, "upper_closed": True, "panel_value": .06},
            {"label": "(0.06,2]", "lower_bound": .06, "upper_bound": 2, "lower_closed": False, "upper_closed": True, "panel_value": 2},
            {"label": ">2", "lower_bound": 2, "upper_bound": None, "lower_closed": False, "upper_closed": False, "panel_value": 4}]},
        "additional_counts": [{"threshold": c, "count": k, "n": 7133, "unit": "mg/L",
            "source": "https://doi.org/10.3390/antibiotics12020289; verified published category counts"}
            for c, k in ((.06, 1726), (2, 143))], "iid": False, "confidence_level": .95}
    published.update(organism="Streptococcus pneumoniae", antimicrobial="Penicillin",
        source_doi="10.3390/antibiotics12020289", source_location="Table 1 total row, 2007–2021; concentration definitions in Methods",
        source="de Miguel et al. (2023), Madrid invasive isolates; https://doi.org/10.3390/antibiotics12020289",
        panel_basis="Broad groups defined by the published count thresholds; not a fine MIC histogram",
        rank_basis="Counts-only analysis; no quantile convention assumed", explain_counts=True,
        targets=[{"threshold": 2, "unit": "mg/L", "decision_operator": "<", "decision_fraction": "0.05"}],
        question_note="The 5% criterion is an illustrative user question, not a clinical breakpoint or a study endpoint.")
    laboratory = {"cohort_id": "FDA-NAHLN-2024-dogs-amikacin-276", "n": 276, "unit": "mg/L",
        "panel": {"levels": [4, 8, 16, 32]}, "iid": False, "confidence_level": .95,
        "organism": "Escherichia coli", "antimicrobial": "Amikacin",
        "source": "FDA animal-pathogen AMR data, NAHLN 2024; dogs, other tissues/body sites",
        "source_location": "https://www.fda.gov/animal-veterinary/national-antimicrobial-resistance-monitoring-system/2017-2024-animal-pathogen-amr-data",
        "rank_basis": "Ceiling-rank summaries generated from the published category counts for this reporting demonstration"}
    return [
        {"id": "summary20", "label": "Controlled example: summaries for 20 isolates", "payload": {
            "mode": "distribution", "config": summary, "options": {}}},
        {"id": "counts20", "label": "Controlled example: reporting audit for 20 isolates", "payload": {
            "mode": "reporting-audit", "config": {k: v for k, v in summary.items() if k != "summaries"},
            "rank_convention": "ceiling", "histogram": [{"category": label, "count": count} for label, count in (("<=1", 8), ("2", 10), (">2", 2))],
            "targets": [{"threshold": 1, "unit": "mg/L", "decision_operator": "<", "decision_fraction": "0.7"}],
            "options": {"reporting_plan": True}}},
        {"id": "published7133", "label": "Published counts: 7,133 isolates", "payload": {
            "mode": "distribution", "config": published, "options": {}}},
        {"id": "laboratory276", "label": "Real laboratory counts: 276 isolates, four questions", "payload": {
            "mode": "reporting-audit", "config": laboratory, "rank_convention": "ceiling",
            "histogram": [{"category": label, "count": count} for label, count in
                          (("<=4", 268), ("8", 7), ("16", 0), ("32", 0), (">32", 1))],
            "targets": [{"threshold": level, "unit": "mg/L", "decision_operator": "<", "decision_fraction": "0.05"}
                        for level in (4, 8, 16, 32)], "options": {"reporting_plan": True}}},
    ]
