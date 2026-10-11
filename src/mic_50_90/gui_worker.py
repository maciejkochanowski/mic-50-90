"""Child-process desktop execution; all statistics use existing workflows."""
from __future__ import annotations

import csv
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace


def write_json(path, value):
    """Publish a complete JSON file atomically within a job directory."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _table(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _distribution(payload, work, output):
    from .distribution_workflow import run_distribution
    from .gui_forms import canonical_distribution_input
    source = work / "input.json"
    write_json(source, canonical_distribution_input(payload["config"]))
    options = payload.get("options", {})
    previous = None
    if payload.get("previous"):
        previous = work / "previous"
        previous.mkdir()
        for name in ("configuration", "results"):
            value = deepcopy(payload["previous"][name])
            if name == "configuration":
                value["inputs"] = [canonical_distribution_input(raw) for raw in value["inputs"]]
            write_json(previous / (name + ".json"), value)
    defaults = {"population_method": "bonferroni", "population_time_limit": 30.,
                "population_tolerance_pp": .01, "precision_pp": None, "population_precision_pp": None, "population_count_plan": False, "population_minimum_bins": None, "population_planning_time_limit": 10.}
    run_distribution(SimpleNamespace(input=str(source), output_dir=str(output), panels=None,
        additional_counts=None, previous_output=previous, delimiter="comma", fail_on_refusal=True,
        **{key: options.get(key, default) for key, default in defaults.items()}))


def _reporting(payload, work, output):
    from .model import MICPanel, QuantileSummary
    from .validation import exact_integer
    from .workflows import run_csv_workflow
    raw, options = payload["config"], payload.get("options", {})
    panel = MICPanel.from_dict(raw["panel"])
    cid, pid = raw.get("cohort_id", "cohort"), raw.get("panel_id", "desktop-panel")
    panel_rows = [{"panel_id": pid, "unit": raw["unit"], "category": item.label,
        "panel_value": item.panel_value, "lower": item.lower, "upper": item.upper,
        "lower_closed": str(item.lower_closed).lower(), "upper_closed": str(item.upper_closed).lower()}
        for item in panel.bins]
    provenance = {key: raw.get(key, "") for key in ("organism", "antimicrobial", "source_doi", "source_location",
                                                   "metadata_basis", "rank_basis", "panel_basis")}
    if 'sample_context' in raw:
        provenance['sample_context'] = json.dumps(raw['sample_context'], ensure_ascii=False)
    source_note = "" if raw.get("source") is None else str(raw["source"]).strip()
    source_location = "" if provenance["source_location"] is None else str(provenance["source_location"]).strip()
    if source_note and source_note != source_location:
        provenance["source_location"] = "; ".join(x for x in (source_location, source_note) if x)
    shared = {**provenance, "cohort_id": cid, "panel_id": pid,
              "iid": str(raw.get("iid", False)).lower(), "confidence_level": raw.get("confidence_level", .95)}
    counts = [{**row, **shared, "rank_convention": payload["rank_convention"],
        "iid": str(raw.get("iid", False)).lower(), "confidence_level": raw.get("confidence_level", .95)}
        for row in (payload.get("histogram", []) if payload["mode"] == "reporting-audit" else [])]
    source = work / "counts.csv"
    if payload["mode"] == "batch":
        source = work / "summaries.csv"
        counts = []
        for variant in [{"id": "primary", "summaries": raw["summaries"]}, *raw.get("reporting_envelope", {}).get("variants", [])]:
            summaries = variant["summaries"]
            quantiles = sorted((QuantileSummary.from_dict(q, n=exact_integer(raw["n"], "n", 2), panel=panel)
                                for q in summaries["quantiles"]), key=lambda q: q.probability)
            counts.append({**shared, "variant_id": variant["id"], "n": raw["n"],
                "mic50": quantiles[0].category_label, "mic90": quantiles[1].category_label,
                "rank50": quantiles[0].rank, "rank90": quantiles[1].rank,
                "rank_convention": "ceiling" if all(q.convention == "ceiling" for q in quantiles) else "explicit",
                "minimum": summaries.get("minimum", ""), "maximum": summaries.get("maximum", "")})
    targets = [{**row, "cohort_id": cid} for row in payload["targets"]]
    _table(work / "panels.csv", panel_rows, list(panel_rows[0]))
    _table(source, counts, list(counts[0]))
    from .input_context import THRESHOLD_FIELDS
    _table(work / "targets.csv", targets, ["cohort_id", "threshold", "unit", "decision_operator", "decision_fraction", *THRESHOLD_FIELDS])
    calibration = None
    if raw.get("wasserstein_calibration_manifest"):
        calibration = work / "calibrations.json"
        write_json(calibration, {cid: {key: raw.get(key) for key in (
            "reference_distribution", "wasserstein_calibration_manifest", "calibration_context")}})
    additional = None
    if payload["mode"] == "batch" and raw.get("additional_counts"):
        additional = work / "additional-counts.csv"
        rows = [{"cohort_id": cid, **row} for row in raw["additional_counts"]]
        # Preserve the validated count contract, including whole-category ranges
        # and source annotations. A table adapter must not discard information.
        fields = list(dict.fromkeys(key for row in rows for key in row))
        _table(additional, rows, fields)
    defaults = {"question_time_limit": 10., "report_page_size": 50, "exclude_direct_targets": False,
        "decision_plan": False, "acquisition_plan": False, "reporting_plan": False, "round_cost": "0",
        "decision_plan_time_limit": 5., "decision_plan_max_states": 5000}
    run_csv_workflow(SimpleNamespace(command=payload["mode"], input=str(source),
        panels=str(work / "panels.csv"), targets=str(work / "targets.csv"), output_dir=str(output),
        calibrations=calibration, additional_counts=additional, decision_queries=None, delimiter="comma", fail_on_refusal=True,
        **{key: options.get(key, default) for key, default in defaults.items()}))


def execute_job(payload, directory):
    """Write outputs and final status; refusal is never labelled successful."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    work, output = root / "input", root / "output"
    work.mkdir(exist_ok=True)
    output.mkdir(exist_ok=True)
    try:
        from .gui_forms import validate_payload
        validation = validate_payload(payload)
        if not validation["valid"]:
            raise ValueError("; ".join(item["message"] for item in validation["issues"]))
        write_json(output / "gui-input.json", payload)
        effective = validation["payload"]
        if effective.get("mode") == "verify-report":
            from .gui_documents import run_verification
            run_verification(effective, output)
        elif effective.get("input_format") == "tables":
            from .gui_documents import run_tables
            run_tables(effective, work, output)
        elif effective.get("mode", "distribution") == "distribution":
            _distribution(effective, work, output)
        else:
            _reporting(effective, work, output)
        result = json.loads((output / "results.json").read_text(encoding="utf-8"))
        cohorts = result if isinstance(result, list) else result.get("cohorts", [])
        refused = [row for row in cohorts if row.get("status") == "refused"]
        status = "refused" if refused else "completed"
        message = ("Analysis refused: " + "; ".join(str(row.get("reason", "Input requirements were not met.")) for row in refused)
                   if refused else "Analysis completed. Open the report to interpret the results and assumptions.")
        write_json(root / "job-status.json", {"status": status, "message": message})
    except Exception as exc:
        write_json(root / "job-status.json", {"status": "failed", "message": "Analysis could not complete: " + str(exc)})
