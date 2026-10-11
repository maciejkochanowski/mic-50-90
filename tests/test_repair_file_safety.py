"""A completed analysis must never replace its own source data."""
import json
import os
from pathlib import Path
import shutil

import pytest

from mic_50_90.cli import main

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def exit_code(arguments):
    try:
        return main([str(value) for value in arguments])
    except SystemExit as error:
        return error.code


@pytest.mark.parametrize("alias", [False, True])
def test_batch_rejects_input_output_collision_before_writing(tmp_path, capsys, alias):
    source = tmp_path / "input.csv"
    shutil.copyfile(EXAMPLES / "csv/summaries.csv", source)
    output = tmp_path / "results.csv"
    if alias:
        os.link(source, output)
    else:
        source.rename(output)
        source = output
    before = source.read_bytes()
    code = exit_code(["batch", source, "--panels", EXAMPLES / "csv/panels.csv",
                      "--targets", EXAMPLES / "csv/targets.csv", "--output-dir", tmp_path])
    assert source.read_bytes() == before
    assert code == 2
    assert "collid" in capsys.readouterr().err.lower()
    assert not (tmp_path / "configuration.json").exists()


@pytest.mark.parametrize("destination_flag", ["--output", "--html"])
def test_json_input_is_preserved_for_both_output_formats(tmp_path, destination_flag):
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"n": 10, "panel": {"levels": [1, 2],
                      "left_censored": False, "right_censored": False},
                      "summaries": {"quantiles": [{"probability": .5, "category": "1"}]},
                      "thresholds": [1]}))
    before = source.read_bytes()
    code = exit_code(["analyse", source, destination_flag, source])
    assert source.read_bytes() == before
    assert code == 2


def test_preparation_metadata_cannot_be_replaced_by_output_configuration(tmp_path):
    source = tmp_path / "configuration.json"
    shutil.copyfile(EXAMPLES / "calibration_preparation/metadata.json", source)
    before = source.read_bytes()
    base = EXAMPLES / "calibration_preparation"
    code = exit_code(["calibration-prepare", base / "counts.csv", "--panels", base / "panels.csv",
                      "--roster", base / "roster.csv", "--metadata", source,
                      "--level", ".75", "--output-dir", tmp_path])
    assert source.read_bytes() == before
    assert code == 2
    assert not (tmp_path / "manifest.json").exists()


def test_calibration_assessment_preserves_aliased_input_roster(tmp_path):
    source = tmp_path / "intended-roster.csv"
    shutil.copyfile(EXAMPLES / "calibration_audit/expected.csv", source)
    before = source.read_bytes()
    code = exit_code(["calibration-audit", EXAMPLES / "calibration_audit/observed.csv",
                      "--roster", source, "--output-dir", tmp_path])
    assert code == 2
    assert source.read_bytes() == before
    assert not (tmp_path / "audit.json").exists()


def test_json_and_html_outputs_cannot_replace_each_other(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps({"n": 10, "panel": {"levels": [1, 2],
                      "left_censored": False, "right_censored": False},
                      "summaries": {"quantiles": [{"probability": .5, "category": "1"}]},
                      "thresholds": [1]}))
    target = tmp_path / "report"
    assert exit_code(["analyse", source, "--output", target, "--html", target]) == 2
    assert not target.exists()


def test_existing_output_can_be_replaced_when_all_inputs_are_separate(tmp_path):
    target = tmp_path / "results.csv"
    target.write_text("old report\n")
    assert exit_code(["batch", EXAMPLES / "csv/summaries.csv",
                      "--panels", EXAMPLES / "csv/panels.csv",
                      "--targets", EXAMPLES / "csv/targets.csv", "--output-dir", tmp_path]) == 0
    assert "cohort_id" in target.read_text()


def test_calibration_plan_outputs_cannot_alias_each_other(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text("previous output")
    os.link(plan, tmp_path / "report.html")
    assert exit_code(["calibration-plan", "--level", ".95", "--output-dir", tmp_path]) == 2
    assert plan.read_text() == "previous output"
