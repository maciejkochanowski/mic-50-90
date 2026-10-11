"""Desktop adapters must preserve the scientific engine and local boundaries."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import threading
import time

import pytest


def sample_payload():
    return {"mode": "distribution", "config": {"cohort_id": "desktop-20", "n": 20,
        "unit": "mg/L", "panel": {"levels": [1, 2]}, "iid": False,
        "summaries": {"quantiles": [
            {"probability": .5, "category": "<=1", "convention": "ceiling"},
            {"probability": .9, "category": "2", "convention": "ceiling"}]}},
        "options": {"precision_pp": "20"}}


def test_validation_collects_required_fields_and_preserves_advanced_input():
    from mic_50_90.gui_forms import validate_payload
    invalid = validate_payload({"mode": "distribution", "config": {}})
    assert not invalid["valid"]
    assert {"config.n", "config.panel", "config.unit"} <= {x["field"] for x in invalid["issues"]}
    payload = sample_payload()
    payload["config"]["source_metadata"] = {"note": "Retain this exact provenance"}
    original = deepcopy(payload)
    result = validate_payload(payload)
    assert result["valid"], result
    assert result["payload"]["config"] == payload["config"]
    assert payload == original


def test_unknown_quantile_convention_is_never_filled_in():
    from mic_50_90.gui_forms import validate_payload
    payload = sample_payload()
    for q in payload["config"]["summaries"]["quantiles"]:
        q.pop("convention")
    result = validate_payload(payload)
    assert not result["valid"]
    assert len([x for x in result["issues"] if "quantile" in x["field"]]) == 2


def test_histogram_must_include_zeros_and_match_denominator():
    from mic_50_90.gui_forms import validate_payload
    payload = {"mode": "reporting-audit", "rank_convention": "ceiling", "config": {"cohort_id": "lab", "n": 20,
        "unit": "mg/L", "panel": {"levels": [1, 2]}, "iid": False},
        "histogram": [{"category": "<=1", "count": 8}, {"category": "2", "count": 10}],
        "targets": [{"threshold": 1, "unit": "mg/L"}]}
    assert not validate_payload(payload)["valid"]
    payload["histogram"].append({"category": ">2", "count": 2})
    assert validate_payload(payload)["valid"]
    payload["config"]["n"] = 21
    assert not validate_payload(payload)["valid"]


def test_worker_distribution_matches_existing_engine(tmp_path):
    from mic_50_90.gui_worker import execute_job
    from mic_50_90.distribution_workflow import analyse_distribution
    payload = sample_payload()
    execute_job(payload, tmp_path)
    status = json.loads((tmp_path / "job-status.json").read_text())
    result = json.loads((tmp_path / "output/results.json").read_text())["cohorts"][0]
    expected = analyse_distribution(payload["config"], precision_pp="20")
    assert status["status"] == "completed"
    for key in ("sample", "population", "resolution", "calibration"):
        assert result[key] == expected[key]
    assert (tmp_path / "output/report.html").is_file()
    assert json.loads((tmp_path / "output/gui-input.json").read_text()) == payload


def test_reporting_adapter_retains_histogram_and_populates_existing_report(tmp_path):
    from mic_50_90.gui_forms import desktop_examples
    from mic_50_90.gui_worker import execute_job
    payload = next(item["payload"] for item in desktop_examples() if item["id"] == "counts20")
    execute_job(payload, tmp_path)
    status = json.loads((tmp_path / "job-status.json").read_text())
    assert status["status"] == "completed", status
    results = json.loads((tmp_path / "output/results.json").read_text())
    assert results[0]["status"] == "ok"
    assert results[0]["result"]["sample_size"] == 20
    assert (tmp_path / "output/reporting_counts.csv").is_file()
    assert "reporting_plan" in results[0]["result"]
    from mic_50_90.model import MICPanel
    config = json.loads((tmp_path / "output/configuration.json").read_text())
    assert config["cohorts"][0]["specification"]["panel"] == MICPanel.from_dict(payload["config"]["panel"]).as_dict()


def test_batch_questions_use_original_counts_and_preserve_variants(tmp_path):
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    payload = sample_payload()
    payload.update(mode="batch", targets=[{"threshold": 1, "unit": "mg/L", "decision_operator": "<=", "decision_fraction": "0.5"}],
                   options={"acquisition_plan": True})
    payload["histogram"] = [{"category": "<=1", "count": None}]
    payload["config"]["n"] = "20"
    payload["config"]["additional_counts"] = [{"threshold": 1, "count": "10", "n": "20", "unit": "mg/L"}]
    payload["config"]["reporting_envelope"] = {"variants": [{"id": "explicit", "summaries": {
        "quantiles": [{"probability": .5, "category": "<=1", "rank": 10}, {"probability": .9, "category": "2", "rank": 18}]}}]}
    assert validate_payload(payload)["valid"]
    execute_job(payload, tmp_path)
    status = json.loads((tmp_path / "job-status.json").read_text())
    assert status["status"] == "completed", status
    results = json.loads((tmp_path / "output/results.json").read_text())[0]["result"]
    assert results["decision_results"][0]["sample"]["status"] == "supported"
    envelope = results["reporting_uncertainty_envelope"]["envelope"][0]["panel_recorded_estimand"]
    assert envelope["lower"]["count"] == envelope["upper"]["count"] == 10
    assert "acquisition_plan" in results
    config = json.loads((tmp_path / "output/configuration.json").read_text())
    assert config["cohorts"][0]["specification"]["reporting_envelope"]["variants"][0]["id"] == "explicit"


def test_saved_update_appends_counts_and_rejects_changed_denominator(tmp_path):
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    original = sample_payload()
    execute_job(original, tmp_path / "first")
    payload = deepcopy(original)
    payload["previous"] = {key: json.loads((tmp_path / "first/output" / (key + ".json")).read_text())
                           for key in ("configuration", "results")}
    payload["config"]["additional_counts"] = [{"threshold": 1, "count": 10, "n": 20, "unit": "mg/L"}]
    assert validate_payload(payload)["valid"]
    execute_job(payload, tmp_path / "second")
    results = json.loads((tmp_path / "second/output/results.json").read_text())
    assert results["cohorts"][0]["saved_count_update"]
    assert results["cohorts"][0]["sample"]["cdf"][0]["count_lower"] == 10
    payload["config"]["n"] = 21
    assert any(item["field"] == "previous" for item in validate_payload(payload)["issues"])


def test_browser_saved_update_accepts_equivalent_integer_strings(tmp_path):
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    original = sample_payload()
    execute_job(original, tmp_path / "first")
    payload = deepcopy(original)
    payload["previous"] = {key: json.loads((tmp_path / "first/output" / (key + ".json")).read_text())
                           for key in ("configuration", "results")}
    payload["config"] = deepcopy(payload["previous"]["configuration"]["inputs"][0])
    payload["config"]["n"] = "20"
    payload["config"]["confidence_level"] = .95
    payload["config"]["additional_counts"] = [{"threshold": 1, "count": "10", "n": "20", "unit": "mg/L"}]
    assert validate_payload(payload)["valid"]
    execute_job(payload, tmp_path / "second")
    status = json.loads((tmp_path / "second/job-status.json").read_text())
    assert status["status"] == "completed", status
    results = json.loads((tmp_path / "second/output/results.json").read_text())
    assert results["cohorts"][0]["saved_count_update"]


def test_guided_source_is_visible_in_reporting_audit(tmp_path):
    from mic_50_90.gui_forms import desktop_examples
    from mic_50_90.gui_worker import execute_job
    payload = next(item["payload"] for item in desktop_examples() if item["id"] == "counts20")
    payload["config"]["source"] = "Lab register: specimen series A"
    payload["config"]["source_location"] = "Table 2"
    execute_job(payload, tmp_path)
    result = json.loads((tmp_path / "output/results.json").read_text())
    assert "Lab register: specimen series A" in result[0]["provenance"]["source_location"]
    assert "Table 2" in result[0]["provenance"]["source_location"]
    assert "Lab register: specimen series A" in (tmp_path / "output/report.html").read_text(encoding="utf-8")


def test_distribution_report_identifies_organism_antimicrobial_and_source(tmp_path):
    from mic_50_90.gui_worker import execute_job
    payload = sample_payload()
    metadata = {"organism": "E. coli", "antimicrobial": "Ampicillin", "source": "Source <script>unsafe()</script>"}
    payload["config"].update(metadata)
    execute_job(payload, tmp_path)
    result = json.loads((tmp_path / "output/results.json").read_text())["cohorts"][0]
    assert result["provenance"] == metadata
    html = (tmp_path / "output/report.html").read_text(encoding="utf-8")
    assert "E. coli" in html and "Ampicillin" in html
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in html
    assert "<script>unsafe()</script>" not in html


@pytest.mark.parametrize("broken", [
    {"n": 1.1}, {"n": True}, {"panel": None}, {"iid": "true"},
    {"confidence_level": False}, {"additional_counts": [{"count": 1}]},
    {"summaries": {"quantiles": None}}, {"reporting_envelope": {"variants": "bad"}},
])
def test_malformed_fields_return_issues_without_crashing(broken):
    from mic_50_90.gui_forms import validate_payload
    payload = sample_payload()
    payload["config"].update(broken)
    result = validate_payload(payload)
    assert not result["valid"] and result["issues"]


def test_http_decoder_preserves_exact_scientific_numbers():
    from mic_50_90.gui_forms import decode_payload, validate_payload
    text = json.dumps(sample_payload()).replace('"n": 20', '"n": 2.0000000000000001')
    payload = decode_payload(text)
    assert payload["config"]["n"] == "2.0000000000000001"
    assert not validate_payload(payload)["valid"]
    payload = decode_payload('{"config":{"n":9007199254740991},"targets":[{"decision_fraction":0.1000000000000000001}]}')
    assert payload["config"]["n"] == 9007199254740991
    assert payload["targets"][0]["decision_fraction"] == "0.1000000000000000001"
    opaque = {"config": {"calibration_context": {"probability": .5, "n": 20.0},
                          "source_metadata": {"count": 20.0, "probability": .5}}}
    assert decode_payload(json.dumps(opaque)) == opaque
    assert isinstance(decode_payload(json.dumps(opaque))["config"]["calibration_context"]["n"], float)


def test_incompatible_summaries_are_a_documented_refusal(tmp_path):
    from mic_50_90.gui_worker import execute_job
    payload = sample_payload()
    payload["config"]["summaries"]["quantiles"][0]["category"] = ">2"
    execute_job(payload, tmp_path)
    status = json.loads((tmp_path / "job-status.json").read_text())
    assert status["status"] == "refused"
    result = json.loads((tmp_path / "output/results.json").read_text())
    assert result["cohorts"][0]["status"] == "refused"
    assert (tmp_path / "output/report.html").is_file()


def test_optional_calibration_failure_keeps_basic_results(tmp_path):
    from mic_50_90.gui_worker import execute_job
    payload = sample_payload()
    payload["config"].update(wasserstein_calibration_manifest={"invalid": True}, reference_distribution=[.2, .6, .2], calibration_context={})
    execute_job(payload, tmp_path)
    status = json.loads((tmp_path / "job-status.json").read_text())
    assert status["status"] == "completed", status
    result = json.loads((tmp_path / "output/results.json").read_text())["cohorts"][0]
    assert result["sample"]["status"] == "complete"
    assert result["calibration"]["status"] == "unavailable"


@pytest.mark.parametrize("browser_numbers", [False, True])
def test_prepared_calibration_survives_desktop_transport(tmp_path, browser_numbers):
    from mic_50_90.calibration_preparation import prepare_calibration
    from mic_50_90.gui_forms import decode_payload
    from mic_50_90.gui_worker import execute_job
    from mic_50_90.workflows import load_panels, read_csv, summary_spec
    source = Path(__file__).resolve().parents[1] / "examples/calibration_preparation"
    preparation = prepare_calibration(source / "counts.csv", panels_path=source / "panels.csv",
        roster_path=source / "roster.csv", metadata_path=source / "metadata.json", level=.75)
    panels, _ = load_panels(source / "panels.csv")
    row = read_csv(source / "future-summaries.csv")[0]
    raw = summary_spec([row], panels[row["panel_id"]], [1, 2], {"enabled": False})
    raw.update(cohort_id=row["cohort_id"], panel_id=row["panel_id"], unit="mg/L", iid=True,
               **preparation["calibrations"][row["cohort_id"]])
    payload = decode_payload(json.dumps({"mode": "distribution", "config": raw, "options": {}}))
    def browser_serialization(value):
        if isinstance(value, dict):
            return {key: browser_serialization(item) for key, item in value.items()}
        if isinstance(value, list):
            return [browser_serialization(item) for item in value]
        return int(value) if isinstance(value, float) and value.is_integer() else value
    if browser_numbers:
        payload = browser_serialization(payload)
        payload["calibration_input_text"] = json.dumps(raw)
    execute_job(payload, tmp_path)
    result = json.loads((tmp_path / "output/results.json").read_text())["cohorts"][0]
    assert result["calibration"]["status"] == "complete", result["calibration"]
    assert result["calibration"]["confidence_level"] == .75
    if browser_numbers:
        previous_text = (tmp_path / "output/configuration.json").read_text()
        previous_result = json.loads((tmp_path / "output/results.json").read_text())
        payload["previous"] = {"configuration": browser_serialization(json.loads(previous_text)), "results": browser_serialization(previous_result)}
        payload["previous_configuration_text"] = previous_text
        payload["config"]["additional_counts"] = [{"threshold": 2, "count": 1, "n": 10, "unit": "mg/L"}]
        execute_job(payload, tmp_path / "updated")
        updated = json.loads((tmp_path / "updated/output/results.json").read_text())["cohorts"][0]
        assert updated["saved_count_update"]
        assert updated["calibration"]["status"] == "complete", updated["calibration"]


def test_opaque_calibration_cannot_overwrite_changed_semantic_values():
    from mic_50_90.gui_forms import validate_payload
    payload = sample_payload()
    fields = {"reference_distribution": [.1, .2, .7], "wasserstein_calibration_manifest": {}, "calibration_context": {}}
    payload["config"].update(fields)
    payload["calibration_input_text"] = json.dumps({**fields, "reference_distribution": [.2, .1, .7]})
    result = validate_payload(payload)
    assert not result["valid"]
    assert any(row["field"] == "calibration_input_text" for row in result["issues"])


def test_unsupported_batch_settings_are_not_silently_dropped():
    from mic_50_90.gui_forms import validate_payload
    payload = sample_payload()
    payload.update(mode="batch", targets=[{"threshold": 1, "unit": "mg/L"}])
    payload["config"]["population"] = {"profile_likelihood_enabled": True}
    result = validate_payload(payload)
    assert not result["valid"]
    assert any("cannot be silently converted" in row["message"] for row in result["issues"])


def test_structural_validation_never_calls_native_solver(monkeypatch):
    from mic_50_90.gui_forms import validate_payload
    import mic_50_90.empirical as empirical
    def unexpected(*args, **kwargs):
        pytest.fail("HTTP preflight must not invoke a native solver")
    monkeypatch.setattr(empirical.EmpiricalProblem, "__init__", unexpected)
    assert validate_payload(sample_payload())["valid"]


@pytest.fixture
def desktop_server(tmp_path):
    from mic_50_90.gui import create_server
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "index.html").write_text("<html><body>Local interface</body></html>")
    server = create_server(output_root=tmp_path / "jobs", assets=assets)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield server
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


def request(server, method, path, data=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=20)
    content = None if data is None else json.dumps(data)
    all_headers = {"Content-Type": "application/json", **(headers or {})}
    conn.request(method, path, body=content, headers=all_headers)
    result = conn.getresponse()
    body = result.read()
    conn.close()
    return result.status, body, dict(result.headers)


def test_server_rejects_untrusted_hosts_origins_and_missing_tokens(desktop_server):
    server = desktop_server
    assert request(server, "GET", "/api/session")[0] == 403
    auth = {"Authorization": "Bearer " + server.token}
    assert request(server, "GET", "/api/session", headers=auth)[0] == 200
    assert request(server, "GET", "/api/session", headers={**auth, "Host": "attacker.example"})[0] == 403
    assert request(server, "POST", "/api/validate", sample_payload(),
                   {**auth, "Origin": "https://attacker.example"})[0] == 403
    assert request(server, "GET", "/../../pyproject.toml", headers=auth)[0] == 404


def test_shutdown_requires_token_and_stops_listener(desktop_server):
    server = desktop_server
    assert request(server, "POST", "/api/shutdown", {})[0] == 403
    assert request(server, "POST", "/api/shutdown", {}, {"Authorization": "Bearer " + server.token})[0] == 200


def test_static_asset_routes_are_explicit(desktop_server):
    server = desktop_server
    (server.assets / "model.js").write_text("window.MicFormModel = {};")
    assert request(server, "GET", "/assets/model.js")[0] == 200
    assert request(server, "GET", "/assets/../gui.py")[0] == 404


def test_job_runs_in_child_and_serves_only_completed_allowed_outputs(desktop_server):
    server = desktop_server
    auth = {"Authorization": "Bearer " + server.token}
    code, body, _ = request(server, "POST", "/api/jobs", sample_payload(), auth)
    assert code == 202, body
    job = json.loads(body)
    for _ in range(150):
        code, body, _ = request(server, "GET", "/api/jobs/" + job["job_id"], headers=auth)
        result = json.loads(body)
        if result["status"] != "running":
            break
        time.sleep(.1)
    assert result["status"] == "completed", result
    assert any(item["name"] == "report.html" for item in result["files"])
    code, html, headers = request(server, "GET", f"/api/jobs/{job['job_id']}/files/report.html?token={server.token}")
    assert code == 200 and b"MIC-50-90" in html
    assert "sandbox" in headers["Content-Security-Policy"]
    assert 'allow-scripts' not in headers["Content-Security-Policy"]
    assert request(server, "GET", f"/api/jobs/{job['job_id']}/files/../payload.json", headers=auth)[0] == 404
    assert request(server, "GET", f"/api/jobs/{job['job_id']}/files/job-status.json", headers=auth)[0] == 404
    assert request(server, "GET", f"/api/jobs/{job['job_id']}/archive", headers=auth)[0] == 200


def test_failed_and_cancelled_jobs_never_look_completed(desktop_server):
    server = desktop_server
    auth = {"Authorization": "Bearer " + server.token}
    code, _, _ = request(server, "POST", "/api/jobs", {"config": {}}, auth)
    assert code == 422
    code, body, _ = request(server, "POST", "/api/jobs", sample_payload(), auth)
    job = json.loads(body)
    code, body, _ = request(server, "POST", f"/api/jobs/{job['job_id']}/cancel", {}, auth)
    assert code == 200
    assert json.loads(body)["status"] == "cancelled"
    assert request(server, "GET", f"/api/jobs/{job['job_id']}/archive", headers=auth)[0] == 409
