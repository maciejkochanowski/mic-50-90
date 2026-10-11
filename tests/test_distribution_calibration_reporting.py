"""Calibration identity and guarantees must survive the distribution adapter."""
from copy import deepcopy
import csv
import json
from pathlib import Path

import pytest

from mic_50_90.calibration_preparation import prepare_calibration
from mic_50_90.cli import main
from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.workflows import load_panels, read_csv, summary_spec


@pytest.fixture(scope="module")
def prepared_input():
    source = Path(__file__).resolve().parents[1] / "examples/calibration_preparation"
    preparation = prepare_calibration(source / "counts.csv", panels_path=source / "panels.csv",
        roster_path=source / "roster.csv", metadata_path=source / "metadata.json", level=.75)
    assert preparation["status"] == "ready"
    panels, errors = load_panels(source / "panels.csv")
    assert not errors
    row = read_csv(source / "future-summaries.csv")[0]
    raw = summary_spec([row], panels[row["panel_id"]], [1, 2], {"enabled": False})
    raw.update(cohort_id=row["cohort_id"], panel_id=row["panel_id"], unit="mg/L", iid=True,
               **preparation["calibrations"][row["cohort_id"]])
    return raw


@pytest.mark.parametrize("change", [{"cohort_id": "C1-P1"}, {"panel_id": "other"}])
def test_prepared_calibration_identity_mismatch_preserves_basic_layers(prepared_input, change):
    baseline = analyse_distribution(prepared_input)
    result = analyse_distribution({**deepcopy(prepared_input), **change})
    assert result["sample"] == baseline["sample"]
    assert result["population"]["cdf"] == baseline["population"]["cdf"]
    assert result["calibration"]["status"] == "unavailable"
    assert "does not match" in result["calibration"]["reason"]


def test_calibration_metadata_visible_in_json_csv_and_html(prepared_input, tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(prepared_input), encoding="utf-8")
    output = tmp_path / "output"
    assert main(["distribution", str(source), "--output-dir", str(output)]) == 0
    result = json.loads((output / "results.json").read_text())["cohorts"][0]
    layer = result["calibration"]
    assert layer["confidence_level"] == .75
    assert layer["guarantee_class"] == "conformal_new_cohort"
    assert layer["calibration_units"] == 3
    assert layer["family_size"] == 2
    assert layer["calibration_contract"]["functional_scope"] == "all_panel_tails"
    assert "exchangeable" in " ".join(layer["assumptions"]).lower()
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "Marginal calibration level: 75.00%" in html
    assert "Calibration units: 3" in html
    assert layer["calibration_unit_definition"] in html
    assert "new unit in the declared calibration group" in html
    assert "declared_group_marginal" not in html
    with (output / "distribution.csv").open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["layer"] == "calibration"]
    assert rows and all(row["confidence_level"] == "0.75" for row in rows)
    assert all(row["guarantee_class"] == "conformal_new_cohort" for row in rows)
    assert all("exchangeable" in row["assumptions"].lower() for row in rows)
    assert all(row["requested_level"] == "0.75" and row["family_size"] == "2" for row in rows)
    assert all(row["reference_rule"] == "projected" for row in rows)
    assert all(float(row["radius"]) == layer["radius"] for row in rows)


def test_saved_population_update_preserves_calibration_event(prepared_input, tmp_path):
    raw = deepcopy(prepared_input)
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    before, after = tmp_path / "before", tmp_path / "after"
    assert main(["distribution", str(source), "--output-dir", str(before)]) == 0
    old = json.loads((before / "results.json").read_text())["cohorts"][0]
    raw["additional_counts"] = [{"threshold": 2, "count": 1, "n": 10, "unit": "mg/L"}]
    source.write_text(json.dumps(raw), encoding="utf-8")
    assert main(["distribution", str(source), "--previous-output", str(before),
                 "--output-dir", str(after), "--fail-on-refusal"]) == 0
    current = json.loads((after / "results.json").read_text())["cohorts"][0]
    assert current["population"]["previous_outer_bounds_preserved"]
    assert current["calibration"]["status"] == "complete"
    for key in ("confidence_level", "guarantee_class", "calibration_units", "calibration_contract"):
        assert current["calibration"][key] == old["calibration"][key]
    assert "original simultaneous tail event is preserved" in current["calibration"]["update_interpretation"]
    for old_row, new_row in zip(old["calibration"]["cdf"], current["calibration"]["cdf"]):
        assert new_row["lower"] >= old_row["lower"] - 1e-12
        assert new_row["upper"] <= old_row["upper"] + 1e-12


def test_spreadsheet_formula_like_labels_are_text_but_json_is_unchanged(prepared_input, tmp_path):
    raw = deepcopy(prepared_input)
    raw["cohort_id"] = "=1+1"
    for key in ("reference_distribution", "wasserstein_calibration_manifest", "calibration_context"):
        raw.pop(key)
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "output"
    assert main(["distribution", str(source), "--output-dir", str(output)]) == 0
    with (output / "distribution.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert all(row["cohort_id"] == "'=1+1" for row in rows)
    assert json.loads((output / "results.json").read_text())["cohorts"][0]["cohort_id"] == "=1+1"


@pytest.mark.parametrize("option,value", [("--population-time-limit", "nan"), ("--population-tolerance-pp", "inf")])
def test_invalid_optional_numeric_setting_still_exports_basic_results(prepared_input, tmp_path, option, value):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(prepared_input), encoding="utf-8")
    output = tmp_path / "output"
    assert main(["distribution", str(source), "--population-method", "joint-exact", option, value,
                 "--output-dir", str(output)]) == 0
    result = json.loads((output / "results.json").read_text())["cohorts"][0]
    assert result["sample"]["status"] == "complete"
    assert result["population"]["status"] == "baseline_retained"
    assert "Joint refinement did not finish" in result["population"]["reason"]
    configuration = json.loads((output / "configuration.json").read_text())
    assert configuration[option[2:].replace("-", "_")] == value


def test_unselected_population_is_distinct_from_failed_sampling_analysis(prepared_input, tmp_path):
    from mic_50_90.distribution_report import render_distribution_html
    result = analyse_distribution({**prepared_input, "iid": False})
    render_distribution_html({"software_version": "1.0.0", "cohorts": [result]}, tmp_path / "report.html")
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "iid sampling" not in html
    assert 'data-layer-status="not_requested"' in html
    assert 'This optional analysis was not selected' in html
