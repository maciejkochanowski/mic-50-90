"""End-to-end distribution reports must retain the observed data and guarantees."""
from __future__ import annotations

import json

import pytest

from mic_50_90.cli import main


def specimen():
    return {
        "cohort_id": "published-table", "unit": "mg/L", "n": 20,
        "panel": {"levels": [1, 2]},
        "additional_counts": [
            {"threshold": 1, "count": 8, "n": 20, "unit": "mg/L", "source": "Table 1"},
            {"threshold": 2, "count": 2, "n": 20, "unit": "mg/L", "source": "Table 1"},
        ],
    }


def analyse(raw, **options):
    from mic_50_90.distribution_workflow import analyse_distribution
    return analyse_distribution(raw, **options)


def test_counts_without_quantiles_determine_categories_and_cdf():
    result = analyse(specimen())
    assert result["n"] == 20
    assert [x["count_lower"] for x in result["sample"]["categories"]] == [12, 6, 2]
    assert [x["count_upper"] for x in result["sample"]["categories"]] == [12, 6, 2]
    assert [x["count_lower"] for x in result["sample"]["cdf"]] == [12, 18]
    assert result["population"]["status"] == "unavailable"
    assert "iid" in result["population"]["reason"]
    assert result["calibration"]["status"] == "unavailable"


def test_population_ranges_cover_three_category_truth_and_identify_family():
    raw = specimen()
    raw["iid"] = True
    result = analyse(raw)
    pop = result["population"]
    assert pop["status"] == "complete"
    assert pop["confidence_level"] == .95
    assert pop["family_size"] == 2
    for row, value in zip(pop["cdf"], [.6, .9]):
        assert row["lower"] < value < row["upper"]
    for row, value in zip(pop["categories"], [.6, .3, .1]):
        assert row["lower"] <= value <= row["upper"]


def test_invalid_additional_information_is_not_silently_dropped():
    raw = specimen()
    raw["additional_counts"][1]["count"] = 12
    with pytest.raises(ValueError, match="incompatible|impossible|infeasible"):
        analyse(raw)


def test_explicit_convention_is_required_for_quantiles():
    raw = specimen()
    raw["summaries"] = {"quantiles": [{"probability": .5, "category": "<=1"}]}
    with pytest.raises(ValueError, match="convention|rank"):
        analyse(raw)


def test_missing_information_is_collected_before_analysis():
    with pytest.raises(ValueError) as error:
        analyse({})
    assert all(field in str(error.value) for field in ("n", "panel", "unit"))


def test_rounded_percentages_and_original_denominator_are_retained():
    raw = specimen()
    raw["additional_counts"] = [{"threshold": 1, "percentage": "40.0", "decimal_places": 1,
        "rounding_rule": "half_up", "n": 20, "unit": "mg/L", "source": "Table 1"}]
    result = analyse(raw)
    assert result["sample"]["cdf"][0]["count_lower"] == 12
    raw["additional_counts"][0]["n"] = 200
    with pytest.raises(ValueError, match="original n|denominator"):
        analyse(raw)


def test_single_isolate_is_allowed_for_counts_but_not_duplicate_quantile_ranks():
    raw = specimen()
    raw["n"] = 1
    raw["additional_counts"] = [{"threshold": 1, "count": 0, "n": 1, "unit": "mg/L"}]
    assert analyse(raw)["sample"]["categories"][0]["count_lower"] == 1
    raw["summaries"] = {"quantiles": [
        {"probability": p, "category": "<=1", "convention": "ceiling"} for p in (.5, .9)]}
    with pytest.raises(ValueError, match="ranks"):
        analyse(raw)


def test_cli_json_exports_useful_html_csv_and_saved_configuration(tmp_path):
    raw = specimen()
    raw["iid"] = True
    raw["cohort_id"] = "<script>alert(1)</script>"
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "report"
    assert main(["distribution", str(source), "--output-dir", str(output)]) == 0
    result = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert result["software_version"] == "1.0.0"
    assert len(result["cohorts"]) == 1
    assert (output / "distribution.csv").exists()
    assert (output / "configuration.json").exists()
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "Sample distribution" in html and "Population distribution" in html
    assert "Calibration for a new study unit" in html
    assert "<script>alert(1)</script>" not in html
    assert "20 isolates" in html
    assert "<svg" in html
    assert 'data-layer-status="not_requested"' in html


def test_cli_never_overwrites_input_with_output(tmp_path):
    source = tmp_path / "results.json"
    original = json.dumps(specimen())
    source.write_text(original, encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["distribution", str(source), "--output-dir", str(tmp_path)])
    assert source.read_text(encoding="utf-8") == original


def test_reporting_union_is_retained_in_sample_bounds():
    raw = {"n": 10, "unit": "mg/L", "panel": {"levels": [1, 2]},
        "summaries": {"quantiles": [{"probability": .5, "category": "<=1", "rank": 5}]},
        "reporting_envelope": {"variants": [{"id": "alternative", "summaries": {
            "quantiles": [{"probability": .5, "category": "2", "rank": 5}]}}]}}
    result = analyse(raw)
    assert result["sample"]["cdf"][0]["count_lower"] == 0
    assert result["sample"]["cdf"][0]["count_upper"] == 10
    assert set(result["retained_variants"]) == {"primary", "alternative"}
    assert result["sample"]["joint_compatibility_required"]


def test_optional_engine_failure_preserves_sample_and_simultaneous_baseline(monkeypatch):
    import mic_50_90.distribution_workflow as workflow
    raw = specimen()
    raw["iid"] = True
    baseline = analyse(raw)

    def unavailable(*args, **kwargs):
        raise RuntimeError("controlled numerical failure")

    monkeypatch.setattr(workflow, "_joint_population", unavailable)
    result = analyse(raw, population_method="joint-exact")
    assert result["sample"] == baseline["sample"]
    assert result["population"]["cdf"] == baseline["population"]["cdf"]
    assert result["population"]["status"] == "baseline_retained"
    assert "controlled numerical failure" in result["population"]["reason"]


def test_csv_counts_only_plus_refusal_exports_both_records(tmp_path):
    import csv
    from mic_50_90.model import MICPanel

    def write(name, fields, rows):
        with (tmp_path / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    panel = MICPanel.from_dict(specimen()["panel"])
    write("panels.csv", ["panel_id", "unit", "category", "panel_value", "lower", "upper", "lower_closed", "upper_closed"],
        [{"panel_id": "P", "unit": "mg/L", "category": x.label, "panel_value": x.panel_value,
          "lower": x.lower, "upper": x.upper, "lower_closed": str(x.lower_closed).lower(),
          "upper_closed": str(x.upper_closed).lower()} for x in panel.bins])
    write("summaries.csv", ["cohort_id", "panel_id", "variant_id", "n", "iid"],
        [{"cohort_id": "A", "panel_id": "P", "variant_id": "primary", "n": 20, "iid": "true"},
         {"cohort_id": "B", "panel_id": "missing", "variant_id": "primary", "n": 20, "iid": "false"}])
    write("counts.csv", ["cohort_id", "threshold", "count", "n", "unit", "source"],
          [{"cohort_id": "A", **row} for row in specimen()["additional_counts"]])
    assert main(["distribution", str(tmp_path / "summaries.csv"), "--panels", str(tmp_path / "panels.csv"),
        "--additional-counts", str(tmp_path / "counts.csv"), "--output-dir", str(tmp_path / "out"),
        "--fail-on-refusal"]) == 2
    records = json.loads((tmp_path / "out/results.json").read_text())["cohorts"]
    assert [row["status"] for row in records] == ["ok", "refused"]
    assert [row["count_lower"] for row in records[0]["sample"]["categories"]] == [12, 6, 2]
    assert "panel" in records[1]["reason"]


def test_incompatible_calibration_does_not_replace_valid_distribution():
    raw = specimen()
    raw["wasserstein_calibration_manifest"] = {"manifest_version": "1.3"}
    result = analyse(raw)
    assert result["sample"]["status"] == "complete"
    assert result["calibration"]["status"] == "unavailable"
    assert "Calibration unavailable" in result["calibration"]["reason"]


def test_population_engine_failure_does_not_discard_correct_sample(monkeypatch):
    import mic_50_90.distribution_workflow as workflow
    raw = specimen()
    raw["iid"] = True

    def unavailable(*args, **kwargs):
        raise RuntimeError("controlled confidence calculation failure")

    monkeypatch.setattr(workflow, "_population_result", unavailable)
    result = analyse(raw)
    assert result["sample"]["status"] == "complete"
    assert result["population"]["status"] == "unavailable"
    assert "controlled confidence" in result["population"]["reason"]


def test_joint_timeout_is_visible_with_retained_valid_bounds():
    raw = specimen()
    raw["iid"] = True
    result = analyse(raw, population_method="joint-exact", population_time_limit=0)
    assert result["population"]["status"] == "time_limit"
    assert result["population"]["cdf_bounds"] == result["population"]["baseline_cdf_bounds"]
    assert not result["population"]["precision_reached"]


@pytest.mark.parametrize("mutation", [
    {"additional_counts": False, "summaries": {"minimum": "<=1"}},
    {"reporting_envelope": {"variants": ["wrong"]}, "additional_counts": []},
    {"summaries": {"quantiles": []}, "additional_counts": []},
])
def test_malformed_or_empty_evidence_is_refused(mutation):
    with pytest.raises(ValueError):
        analyse({**specimen(), **mutation})


def test_disconnected_reporting_union_is_not_printed_as_all_intermediate_counts(tmp_path):
    from mic_50_90.distribution_report import render_distribution_html
    raw = {"n": 10, "unit": "mg/L", "panel": {"levels": [1, 2]},
           "summaries": {"minimum": "<=1", "maximum": "<=1"},
           "reporting_envelope": {"variants": [{"id": "other", "summaries": {
               "minimum": ">2", "maximum": ">2"}}]}}
    result = analyse(raw)
    assert result["sample"]["cdf"][0]["count_components"] == [[0, 0], [10, 10]]
    render_distribution_html({"software_version": "1.0.0", "cohorts": [result]}, tmp_path / "report.html")
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "0 or 10" in html
    assert "0.00% or 100.00%" in html


def test_sample_precision_is_optional_and_separate_from_population_tolerance(tmp_path):
    raw = specimen()
    assert analyse(raw)["resolution"]["status"] == "not_requested"
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    assert main(["distribution", str(source), "--precision-pp", "0", "--population-tolerance-pp", ".05",
                 "--output-dir", str(tmp_path / "out")]) == 0
    result = json.loads((tmp_path / "out/results.json").read_text())["cohorts"][0]
    assert result["resolution"]["number_of_bins"] == 3
    assert result["resolution"]["precision_pp"] == 0
    assert not result["resolution"]["population_confidence_claimed"]
    html = (tmp_path / "out/report.html").read_text(encoding="utf-8")
    assert "Most detailed sample description" in html
    assert "0 percentage point" in html
    table = (tmp_path / "out/distribution.csv").read_text(encoding="utf-8")
    assert "sample_resolution" in table


def test_saved_count_update_preserves_previous_outer_bounds_with_zero_budget(tmp_path):
    import numpy as np
    raw = specimen()
    raw["iid"] = True
    first = {**raw, "additional_counts": raw["additional_counts"][:1]}
    source = tmp_path / "input.json"
    source.write_text(json.dumps(first), encoding="utf-8")
    old_output, new_output = tmp_path / "first", tmp_path / "updated"
    assert main(["distribution", str(source), "--population-method", "joint-exact", "--population-time-limit", ".05",
                 "--output-dir", str(old_output)]) == 0
    previous = json.loads((old_output / "results.json").read_text())["cohorts"][0]
    source.write_text(json.dumps(raw), encoding="utf-8")
    assert main(["distribution", str(source), "--population-method", "joint-exact", "--population-time-limit", "0",
        "--previous-output", str(old_output), "--output-dir", str(new_output), "--fail-on-refusal"]) == 0
    current = json.loads((new_output / "results.json").read_text())["cohorts"][0]
    assert current["population"]["previous_outer_bounds_preserved"]
    for key in ("cdf_bounds", "category_bounds"):
        a, b = np.asarray(previous["population"][key]), np.asarray(current["population"][key])
        assert np.all(b[:, 0] >= a[:, 0])
        assert np.all(b[:, 1] <= a[:, 1])
    assert [row["count_lower"] for row in current["sample"]["categories"]] == [12, 6, 2]


@pytest.mark.parametrize("change", ["denominator", "method", "deleted_count"])
def test_saved_update_refuses_changed_original_analysis(tmp_path, change):
    raw = specimen()
    raw["iid"] = True
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    previous = tmp_path / "previous"
    assert main(["distribution", str(source), "--output-dir", str(previous)]) == 0
    if change == "denominator":
        raw["n"] = 21
        for row in raw["additional_counts"]:
            row["n"] = 21
    if change == "deleted_count":
        raw["additional_counts"] = raw["additional_counts"][:1]
    source.write_text(json.dumps(raw), encoding="utf-8")
    args = ["distribution", str(source), "--previous-output", str(previous),
            "--output-dir", str(tmp_path / "updated"), "--fail-on-refusal"]
    if change == "method":
        args.extend(["--population-method", "joint-exact", "--population-time-limit", "0"])
    assert main(args) == 2
    result = json.loads((tmp_path / "updated/results.json").read_text())["cohorts"][0]
    assert result["status"] == "refused"


def test_saved_update_cannot_overwrite_previous_configuration_or_results(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(specimen()), encoding="utf-8")
    previous = tmp_path / "previous"
    assert main(["distribution", str(source), "--output-dir", str(previous)]) == 0
    saved = (previous / "results.json").read_bytes()
    with pytest.raises(SystemExit):
        main(["distribution", str(source), "--previous-output", str(previous), "--output-dir", str(previous)])
    assert (previous / "results.json").read_bytes() == saved


def test_cli_sample_precision_preserves_the_original_decimal_boundary(tmp_path):
    raw = {"n": 3, "unit": "mg/L", "panel": {"levels": [1, 2]}, "additional_counts": [
        {"threshold": 1, "count_min": 2, "count_max": 3, "n": 3, "unit": "mg/L"},
        {"threshold": 2, "count": 0, "n": 3, "unit": "mg/L"}]}
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    precision = "33.333333333333333333"
    assert main(["distribution", str(source), "--precision-pp", precision,
                 "--output-dir", str(tmp_path / "out")]) == 0
    record = json.loads((tmp_path / "out/results.json").read_text())["cohorts"][0]
    assert record["resolution"]["maximum_count_width"] == 0
    assert record["resolution"]["number_of_bins"] == 2
    assert record["resolution"]["precision_pp_decimal"] == precision
    configuration = json.loads((tmp_path / "out/configuration.json").read_text())
    assert configuration["precision_pp"] == precision


def test_html_explains_population_sampling_without_duplicate_punctuation(tmp_path):
    from mic_50_90.distribution_report import render_distribution_html
    raw = specimen()
    raw["iid"] = True
    result = analyse(raw)
    render_distribution_html({"software_version": "1.0.0", "cohorts": [result]}, tmp_path / "report.html")
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "independent sampling from the same population" in html
    assert "iid sampling" not in html
    assert "reconstruction.." not in html
