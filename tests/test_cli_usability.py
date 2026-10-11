import csv
import json
from pathlib import Path
import subprocess
import sys

import pytest

from mic_50_90.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "published_summaries"


def command(tmp_path, *, refusal=False):
    for name in ("summaries.csv", "panels.csv", "targets.csv"):
        (tmp_path / name).write_bytes((EXAMPLES / name).read_bytes())
    if refusal:
        path = tmp_path / "summaries.csv"
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        for row in rows:
            if row["cohort_id"] == rows[0]["cohort_id"]:
                row["panel_id"] = "missing-panel"
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return ["batch", str(tmp_path / "summaries.csv"), "--panels",
            str(tmp_path / "panels.csv"), "--targets", str(tmp_path / "targets.csv"),
            "--output-dir", str(tmp_path / "out")]


@pytest.mark.parametrize(("option", "delimiter"), [("comma", ","), ("semicolon", ";"), ("tab", "\t")])
def test_explicit_delimiter_preserves_scientific_results_and_quoted_fields(tmp_path, option, delimiter):
    args = command(tmp_path)
    assert main(args) == 0
    expected = json.loads((tmp_path / "out/results.json").read_bytes())
    for name in ("summaries.csv", "panels.csv", "targets.csv"):
        path = tmp_path / name
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        # Use a free provenance column to exercise CSV quoting without changing joins.
        if name == "summaries.csv":
            for row in rows:
                row["source_location"] = 'Table; row, "total"\tlabel'
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
    assert main(args + ["--delimiter", option, "--fail-on-refusal"]) == 0
    actual = json.loads((tmp_path / "out/results.json").read_bytes())
    assert [r["result"] for r in actual] == [r["result"] for r in expected]
    assert actual[0]["provenance"]["source_location"] == 'Table; row, "total"\tlabel'
    config = json.loads((tmp_path / "out/configuration.json").read_bytes())
    assert config["csv_delimiter"] == option
    assert config["fail_on_refusal"] is True


def test_fail_on_refusal_keeps_reports_and_successful_cohorts(tmp_path):
    args = command(tmp_path, refusal=True)
    assert main(args + ["--fail-on-refusal"]) == 2
    records = json.loads((tmp_path / "out/results.json").read_bytes())
    assert [r["status"] for r in records] == ["refused", "ok", "ok"]
    assert (tmp_path / "out/report.html").is_file()
    assert (tmp_path / "out/results.csv").is_file()
    assert main(args) == 0  # Existing callers retain the completion-status default.


def test_version_without_subcommand(capsys):
    with pytest.raises(SystemExit) as stopped:
        main(["--version"])
    assert stopped.value.code == 0
    assert capsys.readouterr().out.strip() == "MIC-50-90 1.0.0"


def test_module_entry_point_outside_checkout(tmp_path):
    completed = subprocess.run([sys.executable, "-m", "mic_50_90", "--version"],
                               cwd=tmp_path, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "MIC-50-90 1.0.0"


@pytest.mark.parametrize("invalid", ["missing_hashes", "empty_hashes", "empty_source"])
def test_calibration_creation_rejects_missing_provenance_without_overwriting(tmp_path, capsys, invalid):
    raw = json.loads((EXAMPLES.parent / "csv/calibration-scores.json").read_bytes())
    if invalid == "missing_hashes":
        del raw["data_hashes"]
    elif invalid == "empty_hashes":
        raw["data_hashes"] = {}
    else:
        raw["source"] = ""
    source = tmp_path / "scores.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    destination = tmp_path / "manifest.json"
    destination.write_text("previous verified manifest", encoding="utf-8")
    with pytest.raises(SystemExit) as stopped:
        main(["calibrate-wasserstein", str(source), "--output", str(destination)])
    assert stopped.value.code == 2
    message = capsys.readouterr().err
    assert ("source" if invalid == "empty_source" else "data_hashes") in message
    assert destination.read_text(encoding="utf-8") == "previous verified manifest"
