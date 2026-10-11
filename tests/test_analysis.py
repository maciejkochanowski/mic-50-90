from __future__ import annotations

import json
from pathlib import Path

from mic_50_90.analysis import analyse_spec
from mic_50_90.cli import main


def test_empirical_analysis_is_strict_json_and_has_expected_bound():
    spec = json.loads(Path("examples/empirical.json").read_text())
    result = analyse_spec(spec)
    serialized = json.dumps(result, allow_nan=False)
    assert "Infinity" not in serialized
    first = result["identification"][0]["panel_recorded_estimand"]
    assert first["lower"]["count"] == 11
    assert first["upper"]["count"] == 50


def test_cli_writes_json_and_html(tmp_path):
    output = tmp_path / "result.json"
    html = tmp_path / "result.html"
    status = main([
        "analyse",
        "examples/empirical.json",
        "--output",
        str(output),
        "--html",
        str(html),
    ])
    assert status == 0
    payload = json.loads(output.read_text())
    assert payload["version"] == "1.0.0"
    assert payload["contract_version"] == "1.0"
    assert "MIC-50-90" in html.read_text()


def test_population_cli_writes_html_with_optional_analyses(tmp_path):
    html = tmp_path / "population.html"
    status = main(["analyse", "examples/population.json", "--html", str(html)])
    assert status == 0
    document = html.read_text(encoding="utf-8")
    assert "Exact iid confidence set" in document
    assert "Optional profile set" in document
    assert "5.62% to 60.17%" in document


def test_population_cli_writes_html_when_profile_and_bayes_are_disabled(tmp_path):
    spec = json.loads(Path("examples/population.json").read_text())
    spec["population"]["profile_likelihood_enabled"] = False
    spec["population"]["bayes_enabled"] = False
    source = tmp_path / "population-minimal.json"
    html = tmp_path / "population-minimal.html"
    source.write_text(json.dumps(spec), encoding="utf-8")
    status = main(["analyse", str(source), "--html", str(html)])
    assert status == 0
    document = html.read_text(encoding="utf-8")
    assert "Exact iid confidence set" in document
    assert "Optional MLE / profile analysis: disabled" in document
    assert "Optional Dirichlet posterior: disabled" in document


def test_v4_input_adapter_preserves_primary_semantics():
    spec = json.loads(Path("examples/empirical.json").read_text())
    spec.pop("contract_version")
    spec.pop("reporting_envelope")
    result = analyse_spec(spec)
    assert result["input_contract_version"] == "4.0"
    assert result["input_adapter"]["semantic_change"] is False
    assert len(result["reporting_uncertainty_envelope"]["per_variant"]) == 1
