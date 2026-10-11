"""Saved inputs and optional blanks must agree at validation and execution."""
from copy import deepcopy
import json

import pytest

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.gui_forms import canonical_distribution_input, decode_payload, validate_payload
from mic_50_90.gui_worker import execute_job


def payload_for(row):
    return dict(mode="distribution", options={}, config=dict(
        cohort_id="input-repairs", n=20, unit="mg/L", panel={"levels": [1, 2]},
        source="Synthetic count example", source_extension={"table": "A", "note": "retain"},
        additional_counts=[dict(threshold=1, n=20, unit="mg/L", **row)]))


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("kind,row,want", [
    ("exact", dict(count=8, count_min="", count_max=None, percentage="", decimal_places="", rounding_rule=""), (12, 12)),
    ("range", dict(count="", count_min=7, count_max=9, percentage=None, decimal_places=None), (11, 13)),
    ("rounded", dict(count=None, count_min="", count_max="", percentage="40.000000", decimal_places=6, rounding_rule="half_even"), (12, 12)),
    ("zero", dict(count=0, count_min=None, count_max="", decimal_places=""), (20, 20)),
    ("whitespace", dict(count=" \t", count_min="7", count_max="9", decimal_places=" ", percentage=" "), (11, 13)),
])
def test_optional_blanks_validate_and_execute_like_direct_engine(tmp_path, kind, row, want):
    payload = payload_for(row)
    original = deepcopy(payload)
    checked = validate_payload(payload)
    assert checked["valid"], checked["issues"]
    direct = analyse_distribution(payload["config"])
    execute_job(payload, tmp_path / kind)
    status = read_json(tmp_path / kind / "job-status.json")
    assert status["status"] == "completed", status
    result = read_json(tmp_path / kind / "output/results.json")["cohorts"][0]
    first = result["sample"]["cdf"][0]
    assert (first["count_lower"], first["count_upper"]) == want
    assert result["sample"] == direct["sample"]
    assert read_json(tmp_path / kind / "output/gui-input.json") == original
    assert payload == original
    normalized = canonical_distribution_input(payload["config"])
    assert normalized["source_extension"] == {"table": "A", "note": "retain"}
    if kind == "rounded":
        assert normalized["additional_counts"][0]["percentage"] == "40.000000"


@pytest.mark.parametrize("change", [
    {"count": "oops", "count_min": 7, "count_max": 9},
    {"count": 8, "count_min": 7, "count_max": 9},
    {"count": 8, "percentage": "40", "decimal_places": 0, "rounding_rule": "half_even"},
    {"count": "", "count_min": "7.0000000000000001", "count_max": 9},
    {"count": "", "count_min": "", "count_max": None},
    {"count": "", "percentage": "40", "decimal_places": 1.5, "rounding_rule": "half_up"},
    {"count": "", "count_min": 7, "count_max": 9, "percentage": "40", "decimal_places": 0, "rounding_rule": "half_up"},
])
def test_populated_invalid_or_conflicting_count_fields_are_refused(tmp_path, change):
    payload = payload_for(change)
    checked = validate_payload(payload)
    assert not checked["valid"]
    execute_job(payload, tmp_path)
    assert read_json(tmp_path / "job-status.json")["status"] == "failed"
    assert not (tmp_path / "output/results.json").exists()


@pytest.mark.parametrize("field", ["n", "unit"])
@pytest.mark.parametrize("value", [None, "", "missing"])
def test_missing_count_denominator_or_unit_is_never_inferred(tmp_path, field, value):
    payload = payload_for({"count": 8})
    row = payload["config"]["additional_counts"][0]
    if value == "missing":
        del row[field]
    else:
        row[field] = value
    checked = validate_payload(payload)
    assert not checked["valid"]
    execute_job(payload, tmp_path)
    assert read_json(tmp_path / "job-status.json")["status"] == "failed"


def test_normalization_retains_source_metadata_and_exact_decimal_tokens():
    text = '{"mode":"distribution","config":{"n":20,"panel":{"levels":[1,2]},"additional_counts":[{"threshold":1,"n":20,"unit":"mg/L","count":"","percentage":40.000000000000000001,"decimal_places":18,"source_information":{"original_text":"source token","count":8}}]},"options":{}}'
    raw = decode_payload(text)["config"]
    normalized = canonical_distribution_input(raw)
    row = normalized["additional_counts"][0]
    assert row["percentage"] == "40.000000000000000001"
    assert row["source_information"] == {"original_text": "source token", "count": 8}
    assert "count" not in row
    assert raw["additional_counts"][0]["count"] == ""


@pytest.fixture(params=["absent-targets", "implicit-count-defaults", "implicit-target-scale"])
def saved_payload(request, tmp_path):
    payload = payload_for({"count": 8})
    config = payload["config"]
    if request.param != "absent-targets":
        config["targets"] = []
    if request.param == "implicit-target-scale":
        config["additional_counts"][0].update(relation=">", source="")
        config["targets"] = [dict(threshold=1, unit="mg/L", decision_operator="<=",
                                  decision_fraction="0.4000000000000000001")]
    execute_job(payload, tmp_path / "first")
    assert read_json(tmp_path / "first/job-status.json")["status"] == "completed"
    previous = {key: read_json(tmp_path / "first/output" / f"{key}.json")
                for key in ("configuration", "results")}
    restored = dict(mode="distribution", config=deepcopy(previous["configuration"]["inputs"][0]),
                    options={}, previous=previous)
    restored["config"]["additional_counts"].append(dict(threshold=2, count=2, n=20, unit="mg/L"))
    return restored


def test_saved_input_shapes_allow_truthful_append(saved_payload, tmp_path):
    checked = validate_payload(saved_payload)
    assert checked["valid"], checked["issues"]
    execute_job(saved_payload, tmp_path / "updated")
    assert read_json(tmp_path / "updated/job-status.json")["status"] == "completed"
    result = read_json(tmp_path / "updated/output/results.json")["cohorts"][0]
    assert result["saved_count_update"]
    assert [(row["count_lower"], row["count_upper"]) for row in result["sample"]["cdf"]] == [(12, 12), (18, 18)]


@pytest.mark.parametrize("edit", ["denominator", "panel", "target", "old-count", "convention"])
def test_saved_update_still_refuses_changed_prior_information(saved_payload, tmp_path, edit):
    config = saved_payload["config"]
    if edit == "denominator":
        config["n"] = 21
    elif edit == "panel":
        config["panel"]["levels"].append(4)
    elif edit == "target":
        if config.get("targets"):
            config["targets"][0]["decision_fraction"] = "0.4000000000000000002"
        else:
            config["targets"] = [dict(threshold=2, unit="mg/L")]
    elif edit == "old-count":
        config["additional_counts"][0]["count"] = 9
    else:
        config["summaries"]["quantiles"] = [dict(probability="0.5", category="<=1", convention="ceiling")]
    checked = validate_payload(saved_payload)
    assert any(issue["field"] == "previous" for issue in checked["issues"])
    execute_job(saved_payload, tmp_path / "refused")
    assert read_json(tmp_path / "refused/job-status.json")["status"] == "failed"
    assert not (tmp_path / "refused/output/results.json").exists()
