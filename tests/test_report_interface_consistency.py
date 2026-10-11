"""Request intent and endpoint evidence must survive the HTML boundary."""
from copy import deepcopy
from html.parser import HTMLParser

import pytest

from mic_50_90 import analyse_spec
from mic_50_90.workflows import analyse_layers
from mic_50_90.report import result_sections
from mic_50_90.result_view import threshold_overview
from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.distribution_report import render_distribution_html


def spec():
    return dict(mode="empirical", n=20, unit="mg/L", panel={"levels": [1, 2, 4]},
                thresholds=[2], question_utility={"enabled": False}, summaries={"quantiles": [
                    {"probability": .5, "category": "<=1", "convention": "ceiling"},
                    {"probability": .9, "category": "2", "convention": "ceiling"}]})


class StatusMarkup(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.statuses = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-layer-status" in attrs:
            self.statuses.append(attrs["data-layer-status"])


def test_threshold_report_uses_same_unrequested_status_in_overview_and_details():
    result = analyse_layers(spec(), False, .95)
    assert result.get("inference_requested") == {"population": False, "calibration": False}
    assert StatusMarkup(threshold_overview(result)).statuses == ["not_requested", "not_requested"]
    details = result_sections(result)
    assert StatusMarkup(details).statuses == ["not_requested", "not_requested"]
    assert "Unavailable:" not in details


def test_invalid_requested_calibration_is_unavailable_in_both_locations():
    result = analyse_layers(spec(), False, .95, calibration={})
    assert result.get("inference_requested", {}).get("calibration") is True
    assert StatusMarkup(threshold_overview(result)).statuses == ["not_requested", "unavailable"]
    assert StatusMarkup(result_sections(result)).statuses == ["not_requested", "unavailable"]


def test_failed_requested_population_keeps_sample_and_intent(monkeypatch):
    import mic_50_90.workflows as workflows
    original = workflows.analyse_spec
    def fail_population(raw):
        if raw["mode"] == "population":
            raise RuntimeError("controlled solver failure")
        return original(raw)
    monkeypatch.setattr(workflows, "analyse_spec", fail_population)
    result = analyse_layers(spec(), True, .95)
    assert result.get("inference_requested", {}).get("population") is True
    assert result["reporting_uncertainty_envelope"]["envelope"]
    for text in (threshold_overview(result), result_sections(result)):
        assert StatusMarkup(text).statuses == ["unavailable", "not_requested"]
        assert "controlled solver failure" in text


def test_old_result_without_intent_keeps_readable_status():
    result = analyse_layers(spec(), False, .95)
    result.pop("inference_requested", None)
    assert StatusMarkup(result_sections(result)).statuses == ["not_requested", "not_requested"]


def test_direct_population_analysis_records_requested_layer():
    raw = spec()
    raw.update(mode="population", population={"profile_likelihood_enabled": False, "bayes_enabled": False})
    result = analyse_spec(raw)
    assert result.get("inference_requested", {}).get("population") is True


def test_calibration_conflict_is_unavailable_without_hiding_sample_answer():
    from test_count_updates import feature, specification, returned, calibration, sample_counts
    result = feature()(specification(), [returned(count=1)], calibration=calibration())
    assert sample_counts(result) == [(1, 1), (1, 1)]
    for text in (threshold_overview(result), result_sections(result)):
        assert StatusMarkup(text).statuses == ["not_requested", "unavailable"]
        assert "incompatible" in text.lower()


def test_partial_calibration_is_explicitly_incomplete():
    from test_count_updates import feature, specification, returned, calibration
    result = feature()(specification(), [returned()], calibration=calibration())
    result["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"]["threshold_results"][1]["envelope"] = None
    result["conformal_unavailable_reason"] = "A requested tail could not be evaluated"
    for text in (threshold_overview(result), result_sections(result)):
        assert StatusMarkup(text).statuses == ["not_requested", "incomplete"]
        assert "A requested tail could not be evaluated" in text


@pytest.fixture
def population_record():
    raw = dict(cohort_id="endpoint-evidence", n=20, unit="mg/L", panel={"levels": [1, 2, 4]},
               iid=True, additional_counts=[dict(n=20, unit="mg/L", threshold=1, count=5)])
    return analyse_distribution(raw, population_method="range-calibrated", population_time_limit=1.)


def test_population_endpoint_evidence_is_readable_without_json(population_record, tmp_path):
    result = population_record
    assert result["population"]["population_row_lift_certificate"]["status"] == "certified"
    target = tmp_path / "report.html"
    render_distribution_html(dict(software_version="1.0.0", cohorts=[result]), target)
    text = target.read_text(encoding="utf-8")
    assert "How this result was checked" in text
    assert 'data-check="p6" data-status="certified"' in text
    assert 'data-check="evaluated-histograms"' in text
    assert 'data-check="endpoint-gap"' in text


def test_unconfirmed_endpoint_condition_is_never_displayed_as_certified(population_record, tmp_path):
    record = deepcopy(population_record)
    layer = record["population"]
    layer["population_row_lift_certificate"] = {"status": "not_certified", "reason": "condition unresolved"}
    layer.update(precision_reached=False, endpoint_gap_pp=2., numerical_status="time budget reached")
    target = tmp_path / "report.html"
    render_distribution_html(dict(software_version="1.0.0", cohorts=[record]), target)
    text = target.read_text(encoding="utf-8")
    assert 'data-check="p6" data-status="not_certified"' in text
    assert 'data-check="p6" data-status="certified"' not in text
    assert 'data-layer-status="incomplete"' in text
    assert "condition unresolved" in text
