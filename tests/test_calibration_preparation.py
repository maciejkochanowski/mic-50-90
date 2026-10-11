"""Calibration preparation retains planned units and checks independent score examples."""
import csv
from copy import deepcopy
import importlib
import json
from types import SimpleNamespace

import pytest

from mic_50_90.conformal import validate_calibration_manifest
from mic_50_90.model import parse_spec
from mic_50_90.workflows import load_panels, summary_spec


def write_csv(path, rows, fields=None, delimiter=","):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def fixture_inputs(tmp_path):
    panels = []
    for pid, scale in (("P1", 1), ("P2", 2)):
        panels.extend([
            dict(panel_id=pid, unit="mg/L", category=f"<={scale}", lower="", upper=scale,
                 lower_closed="false", upper_closed="true", panel_value=scale),
            dict(panel_id=pid, unit="mg/L", category=str(2*scale), lower=scale, upper=2*scale,
                 lower_closed="false", upper_closed="true", panel_value=2*scale),
            dict(panel_id=pid, unit="mg/L", category=f">{2*scale}", lower=2*scale, upper="",
                 lower_closed="false", upper_closed="false", panel_value=4*scale),
        ])
    roster = [dict(unit_id=uid, cohort_id=f"{uid}-{pid}", panel_id=pid, role=role)
              for uid, role in (("C1", "calibration"), ("C2", "calibration"),
                                ("C3", "calibration"), ("T1", "target"))
              for pid in ("P1", "P2")]
    values = {"C1-P1": [8, 1, 1], "C2-P1": [7, 3, 0], "C3-P1": [5, 4, 1]}
    counts = []
    for item in roster:
        if item["role"] != "calibration":
            continue
        categories = [r["category"] for r in panels if r["panel_id"] == item["panel_id"]]
        counts.extend(dict(cohort_id=item["cohort_id"], panel_id=item["panel_id"],
                           category=category, count=count, rank_convention="ceiling", original_n=10)
                      for category, count in zip(categories, values.get(item["cohort_id"], [5, 4, 1])))
    metadata = dict(protocol_label="synthetic-example-v1", unit_definition="one independent study",
                    cohort_selection_rule="One prespecified cohort on P1 and P2 in every study",
                    roster_provenance="Synthetic roster specified before histograms",
                    counts_provenance="Synthetic complete category counts; not empirical evidence",
                    grouping={"population": "synthetic demonstration"},
                    panel_provenance={"P1": "Explicit synthetic P1 dilution grid",
                                      "P2": "Explicit synthetic P2 dilution grid"})
    return {"counts": counts, "panels": panels, "roster": roster, "metadata": metadata,
            "directory": tmp_path}


def save_inputs(data, delimiter=","):
    root = data["directory"]
    for name in ("counts", "panels", "roster"):
        write_csv(root/f"{name}.csv", data[name], delimiter=delimiter)
    (root/"metadata.json").write_text(json.dumps(data["metadata"]), encoding="utf-8")
    return dict(counts_path=root/"counts.csv", panels_path=root/"panels.csv",
                roster_path=root/"roster.csv", metadata_path=root/"metadata.json")


def prepare(data, *, level=.75, delimiter=","):
    module = importlib.import_module("mic_50_90.calibration_preparation")
    return module.prepare_calibration(**save_inputs(data, delimiter), level=level, delimiter=delimiter)


def test_hand_calculated_scores_rank_all_cohorts_within_each_unit(tmp_path):
    result = prepare(fixture_inputs(tmp_path))
    assert result["status"] == "ready", result["refusals"]
    assert result["summary"]["expected_calibration_units"] == 3
    assert result["summary"]["expected_calibration_cohorts"] == 6
    assert result["summary"]["target_units"] == 1
    assert result["summary"]["target_cohorts"] == 2
    scores = {r["cohort_id"]: r for r in result["cohort_scores"]}
    # Uniform [1/3,1/3,1/3] projects to [.5,.4,.1]. For [8,1,1]/10,
    # moving .3 from category 2 to category 1 covers the worst recorded tail.
    assert scores["C1-P1"]["projected_reference"] == pytest.approx([.5, .4, .1])
    assert scores["C1-P1"]["score"] == pytest.approx(.3, abs=2e-6)
    assert scores["C2-P1"]["score"] == pytest.approx(.2, abs=2e-6)
    assert scores["C3-P1"]["score"] == pytest.approx(0, abs=2e-6)
    assert scores["C1-P1"]["original_n"] == 10
    assert scores["C2-P1"]["counts"] == [7, 3, 0]
    assert scores["C1-P1"]["tail_scores"][0]["truth_count"] == 2
    assert scores["C1-P1"]["tail_scores"][1]["truth_count"] == 1
    assert [r["score"] for r in result["unit_scores"]] == pytest.approx([.3, .2, 0], abs=2e-6)
    manifest = result["manifest"]
    validate_calibration_manifest(manifest)
    assert manifest["manifest_version"] == "1.2"
    assert manifest["rank"] == 3
    assert manifest["calibration_size"] == 3
    assert manifest["radius"] == pytest.approx(.3, abs=2e-6)
    assert manifest["confidence_level"] == .75
    assert manifest["fallback_used"] is False
    assert set(result["calibrations"]) == {"T1-P1", "T1-P2"}
    assert [r["threshold"] for r in result["targets"] if r["cohort_id"] == "T1-P1"] == [1., 2.]


def test_target_mapping_applies_to_future_summaries_without_target_counts(tmp_path):
    data = fixture_inputs(tmp_path)
    result = prepare(data)
    panel = load_panels(tmp_path/"panels.csv")[0]["P1"]
    raw = summary_spec([dict(variant_id="primary", n=10, mic50="<=1", mic90="2",
                             rank_convention="ceiling")], panel, [1, 2], {"enabled": False})
    spec = parse_spec({**raw, **result["calibrations"]["T1-P1"]})
    assert spec.wasserstein_radius == pytest.approx(.3, abs=2e-6)
    assert spec.reference_distribution.tolist() == pytest.approx([1/3]*3)
    assert "minimum" not in raw["summaries"] and "maximum" not in raw["summaries"]


@pytest.mark.parametrize("case", ["missing_cohort", "missing_zero_category", "duplicate_category",
                                   "negative_count", "fractional_count", "nonfinite_count",
                                   "denominator_mismatch", "n_below_two", "rank_policy",
                                   "unknown_count_cohort", "count_panel_mismatch", "target_outcome"])
def test_bad_expected_histogram_never_discards_a_unit_to_issue_calibration(tmp_path, case):
    data = fixture_inputs(tmp_path)
    if case == "missing_cohort":
        data["counts"] = [r for r in data["counts"] if r["cohort_id"] != "C2-P1"]
    elif case == "missing_zero_category":
        data["counts"] = [r for r in data["counts"] if not (r["cohort_id"] == "C2-P1" and r["count"] == 0)]
    elif case == "duplicate_category":
        data["counts"].append(deepcopy(data["counts"][0]))
    elif case in {"negative_count", "fractional_count", "nonfinite_count"}:
        data["counts"][0]["count"] = {"negative_count": -1, "fractional_count": 1.5,
                                      "nonfinite_count": "nan"}[case]
    elif case == "denominator_mismatch":
        data["counts"][0]["original_n"] = 11
    elif case == "n_below_two":
        for row in data["counts"]:
            if row["cohort_id"] == "C2-P1":
                row["count"], row["original_n"] = 0, 0
    elif case == "rank_policy":
        data["counts"][0]["rank_convention"] = "explicit"
    elif case == "unknown_count_cohort":
        data["counts"][0]["cohort_id"] = "unplanned"
    elif case == "count_panel_mismatch":
        data["counts"][0]["panel_id"] = "P2"
    else:
        data["counts"].append(dict(data["counts"][0], cohort_id="T1-P1"))
    result = prepare(data)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None
    assert result["calibrations"] == {}
    assert result["refusals"]
    assert result["summary"]["expected_calibration_units"] == 3
    assert result["summary"]["expected_calibration_cohorts"] == 6
    assert {r["unit_id"] for r in result["unit_scores"]} == {"C1", "C2", "C3"}


@pytest.mark.parametrize("case", ["duplicate_roster", "cohort_split", "role_overlap", "unknown_role",
                                   "missing_slot", "additional_slot", "unknown_panel", "missing_id",
                                   "outcome_in_roster"])
def test_roster_cannot_silently_change_the_prespecified_unit_event(tmp_path, case):
    data = fixture_inputs(tmp_path)
    if case == "duplicate_roster":
        data["roster"].append(deepcopy(data["roster"][0]))
    elif case == "cohort_split":
        data["roster"][2]["cohort_id"] = data["roster"][0]["cohort_id"]
    elif case == "role_overlap":
        for row in data["roster"]:
            if row["role"] == "target": row["unit_id"] = "C1"
    elif case == "unknown_role":
        data["roster"][0]["role"] = "training"
    elif case == "missing_slot":
        data["roster"].pop()
    elif case == "additional_slot":
        data["roster"].append(dict(data["roster"][-1], cohort_id="extra"))
    elif case == "unknown_panel":
        data["roster"][-1]["panel_id"] = "unrecorded"
    elif case == "missing_id":
        data["roster"][0]["cohort_id"] = ""
    else:
        for row in data["roster"]: row["truth"] = ".1"
    result = prepare(data)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None and result["calibrations"] == {}
    assert result["refusals"]


@pytest.mark.parametrize("field", ["protocol_label", "unit_definition", "cohort_selection_rule",
                                    "roster_provenance", "counts_provenance", "grouping", "panel_provenance"])
def test_preparation_requires_explicit_provenance_and_selection_metadata(tmp_path, field):
    data = fixture_inputs(tmp_path)
    data["metadata"].pop(field)
    result = prepare(data)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None
    assert any(field in r["reason"] for r in result["refusals"])


def test_insufficient_units_do_not_lower_requested_level_or_use_fallback(tmp_path):
    result = prepare(fixture_inputs(tmp_path), level=.95)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None
    assert result["summary"]["expected_calibration_units"] == 3
    assert result["summary"]["minimum_calibration_units"] == 19
    assert result["configuration"]["level"] == .95


def test_canonical_bindings_cover_censoring_and_all_internal_cuts(tmp_path):
    module = importlib.import_module("mic_50_90.calibration_preparation")
    data = fixture_inputs(tmp_path)
    result = prepare(data)
    panel = load_panels(tmp_path/"panels.csv")[0]["P1"]
    item = result["calibrations"]["T1-P1"]
    binding = item["calibration_context"]["preparation_binding"]
    assert binding["allowed_tail_vectors"] == [[0., 1., 1.], [0., 0., 1.]]
    assert binding["unit_id"] == "T1" and binding["panel_id"] == "P1"
    assert binding["panel_sha256"] == module.canonical_sha256(panel.as_dict())
    assert binding["reference_sha256"] == module.canonical_sha256([1/3]*3)
    assert result["manifest"]["data_hashes"]["target_binding:T1-P1"] == module.canonical_sha256(binding)
    changed = panel.as_dict()
    changed["categories"][0]["lower_bound"] = .5
    assert module.canonical_sha256(changed) != binding["panel_sha256"]


def test_cli_writer_records_refusal_instead_of_leaving_a_previous_manifest(tmp_path):
    module = importlib.import_module("mic_50_90.calibration_preparation")
    data = fixture_inputs(tmp_path)
    paths = save_inputs(data)
    output = tmp_path/"prepared"
    args = SimpleNamespace(input=paths["counts_path"], panels=paths["panels_path"],
                           roster=paths["roster_path"], metadata=paths["metadata_path"],
                           level=.75, delimiter="comma", output_dir=output)
    assert module.run_calibration_prepare(args) == 0
    assert json.loads((output/"manifest.json").read_text())["manifest_version"] == "1.2"
    assert (output/"report.html").exists()
    # Reusing the same output after incomplete input must not expose stale usable calibration.
    data["counts"] = [r for r in data["counts"] if r["cohort_id"] != "C2-P1"]
    save_inputs(data)
    assert module.run_calibration_prepare(args) == 2
    assert json.loads((output/"manifest.json").read_text()) is None
    assert json.loads((output/"calibrations.json").read_text()) == {}
    assert json.loads((output/"preparation.json").read_text())["status"] == "unavailable"
    assert "C2-P1" in (output/"refusals.csv").read_text()
    assert "unavailable" in (output/"report.html").read_text().lower()


def test_maximum_includes_a_second_panel_without_pooling_histograms(tmp_path):
    data = fixture_inputs(tmp_path)
    changed_counts = iter([8, 2, 0])
    for row in data["counts"]:
        if row["cohort_id"] == "C3-P2": row["count"] = next(changed_counts)
    result = prepare(data)
    assert result["status"] == "ready"
    c3 = next(r for r in result["unit_scores"] if r["unit_id"] == "C3")
    assert c3["score"] == pytest.approx(.3, abs=2e-6)
    p1 = next(r for r in result["cohort_scores"] if r["cohort_id"] == "C3-P1")
    assert p1["score"] == pytest.approx(0, abs=2e-6)
    assert p1["original_n"] == 10


@pytest.mark.parametrize("failure", ["infinite", "disagreement", "solver_error"])
def test_numerical_scoring_failures_cannot_be_replaced_with_zero_or_omitted(tmp_path, monkeypatch, failure):
    module = importlib.import_module("mic_50_90.calibration_preparation")
    real = module.dro.critical_radius
    calls = 0

    def fail_one(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            if failure == "solver_error": raise RuntimeError("Injected numerical failure")
            return float("inf") if failure == "infinite" else .9
        return real(**kwargs)

    monkeypatch.setattr(module.dro, "critical_radius", fail_one)
    result = prepare(fixture_inputs(tmp_path))
    assert result["status"] == "unavailable"
    assert result["manifest"] is None and result["calibrations"] == {}
    assert result["summary"]["expected_calibration_units"] == 3
    assert result["summary"]["complete_calibration_units"] == 2
    assert result["summary"]["available_calibration_cohorts"] == 5
    assert result["unit_scores"][0]["score"] is None


def test_modifying_an_input_during_scoring_refuses_mismatched_provenance(tmp_path, monkeypatch):
    module = importlib.import_module("mic_50_90.calibration_preparation")
    data = fixture_inputs(tmp_path)
    paths = save_inputs(data)
    real = module._score_cohort

    def score_and_change_input(*args):
        result = real(*args)
        with paths["metadata_path"].open("a", encoding="utf-8") as stream:
            stream.write("\n")
        return result

    monkeypatch.setattr(module, "_score_cohort", score_and_change_input)
    result = module.prepare_calibration(**paths, level=.75)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None
    assert any(r["code"] == "input_changed" for r in result["refusals"])


@pytest.mark.parametrize("corruption", ["unknown_field", "duplicate_key", "nonstandard_nan"])
def test_metadata_must_be_unambiguous_standard_json(tmp_path, corruption):
    module = importlib.import_module("mic_50_90.calibration_preparation")
    data = fixture_inputs(tmp_path)
    paths = save_inputs(data)
    if corruption == "unknown_field":
        data["metadata"]["target_truths"] = [.2]
        save_inputs(data)
    else:
        text = paths["metadata_path"].read_text()
        addition = '"protocol_label":"conflicting-protocol",' if corruption == "duplicate_key" else '"unexpected":NaN,'
        paths["metadata_path"].write_text("{"+addition+text[1:])
    result = module.prepare_calibration(**paths, level=.75)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None


@pytest.mark.parametrize("level", [0, 1, float("nan"), True])
def test_invalid_levels_still_produce_json_safe_refusals(tmp_path, level):
    result = prepare(fixture_inputs(tmp_path), level=level)
    assert result["status"] == "unavailable"
    assert result["manifest"] is None
    json.dumps(result, allow_nan=False)


def test_semicolon_csv_input_uses_the_same_fixed_rule(tmp_path):
    result = prepare(fixture_inputs(tmp_path), delimiter=";")
    assert result["status"] == "ready"
    assert result["manifest"]["radius"] == pytest.approx(.3, abs=2e-6)
