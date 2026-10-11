"""Decision acquisition stays optional and uses the existing count workflow."""

import csv
import json

import pytest

from mic_50_90.cli import main
from mic_50_90.report import result_sections


def _write(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _inputs(tmp_path, *, fraction=".05", iid=False, n=10):
    panels = [dict(panel_id="P", unit="mg/L", category=str(value), lower=value,
                   upper=value, lower_closed="true", upper_closed="true", panel_value=value)
              for value in (1, 2, 4, 8, 16)]
    summaries = [dict(cohort_id="C", panel_id="P", variant_id="primary", n=n,
                      mic50="1", mic90="2", rank_convention="ceiling", iid=str(iid).lower())]
    targets = [dict(cohort_id="C", threshold=value, unit="mg/L", decision_operator="<",
                    decision_fraction=fraction) for value in (2, 4, 8)]
    for filename, rows in (("panels.csv", panels), ("summaries.csv", summaries), ("targets.csv", targets)):
        _write(tmp_path / filename, list(rows[0]), rows)


def _run(tmp_path, *extra, command="batch", filename="summaries.csv"):
    assert main([command, str(tmp_path / filename), "--panels", str(tmp_path / "panels.csv"),
                 "--targets", str(tmp_path / "targets.csv"), "--output-dir", str(tmp_path / "out"),
                 *extra]) == 0
    return json.loads((tmp_path / "out/results.json").read_text(encoding="utf-8"))


def test_csv_plan_exports_action_cost_scope_and_complete_policy(tmp_path):
    _inputs(tmp_path)
    result = _run(tmp_path, "--decision-plan")[0]["result"]
    plan = result["decision_plan"]
    assert plan["status"] == "optimal"
    assert plan["worst_case_cost"] == 2 and plan["fixed_plan_cost"] == 3
    assert plan["next_question"]["threshold"] == 4
    assert plan["scope"] == "recorded_sample_decisions"
    assert plan["policy"]["kind"] == "adaptive_tree"
    assert len(plan["policy"]["nodes"]) > 1
    report = (tmp_path / "out/report.html").read_text(encoding="utf-8")
    for text in ("Counts to resolve your criteria", "original cohort", "population", "strictly above", "Stop"):
        assert text in report
    assert "width" in report and "Additional information" in report
    with (tmp_path / "out/results.csv").open(encoding="utf-8", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["decision_plan_status"] == "optimal"
    assert float(row["decision_plan_worst_case_cost"]) == 2
    assert float(row["decision_plan_next_threshold"]) == 4
    configuration = json.loads((tmp_path / "out/configuration.json").read_text())
    assert configuration["decision_planning"]["enabled"] is True
    assert configuration["cohorts"][0]["decision_planning"]["criteria"][0]["decision_fraction"] == ".05"


def test_plan_is_opt_in_and_criterion_decimal_is_not_rounded(tmp_path):
    _inputs(tmp_path, n=11, fraction="0.090909090909090905")
    assert "decision_plan" not in _run(tmp_path)[0]["result"]
    result = _run(tmp_path, "--decision-plan")[0]["result"]
    assert result["decision_plan"]["criteria"][0]["decision_fraction_text"] == "0.090909090909090905"


def test_whitelist_missing_cohort_means_no_allowed_questions(tmp_path):
    _inputs(tmp_path)
    _write(tmp_path / "queries.csv", ["cohort_id", "threshold", "unit", "cost"],
           [dict(cohort_id="other", threshold=4, unit="mg/L", cost=1)])
    record = _run(tmp_path, "--decision-plan", "--decision-queries", str(tmp_path / "queries.csv"))[0]
    assert record["status"] == "ok"
    assert record["result"]["decision_plan"]["status"] == "impossible"
    assert record["result"]["decision_plan"]["next_question"] is None


def test_excluded_direct_targets_apply_to_decision_plan(tmp_path):
    _inputs(tmp_path)
    result = _run(tmp_path, "--decision-plan", "--exclude-direct-targets")[0]["result"]
    assert result["decision_plan"]["status"] == "impossible"
    assert result["one_question_recovery"]["direct_target_questions_excluded"]


@pytest.mark.parametrize("field,value", [("cost", "-1"), ("cost", "nan"), ("unit", "unknown"), ("cohort_id", "")])
def test_bad_optional_query_preserves_sample_results(tmp_path, field, value):
    _inputs(tmp_path)
    query = dict(cohort_id="C", threshold=4, unit="mg/L", cost="1")
    query[field] = value
    _write(tmp_path / "queries.csv", list(query), [query])
    record = _run(tmp_path, "--decision-plan", "--decision-queries", str(tmp_path / "queries.csv"))[0]
    assert record["status"] == "ok"
    result = record["result"]
    assert result["reporting_uncertainty_envelope"]["envelope"]
    assert result["decision_plan"]["status"] == "unavailable"
    assert result["decision_plan"]["reason"]
    assert result["decision_plan"]["next_question"] is None


@pytest.mark.parametrize("option,value", [("--decision-plan-time-limit", "bad"),
                                           ("--decision-plan-time-limit", "nan"),
                                           ("--decision-plan-max-states", "1.5")])
def test_bad_optional_cli_setting_isolated_after_base_analysis(tmp_path, option, value):
    _inputs(tmp_path)
    record = _run(tmp_path, "--decision-plan", option, value)[0]
    assert record["status"] == "ok"
    assert record["result"]["decision_plan"]["status"] == "unavailable"


def test_missing_optional_file_preserves_outputs_and_records_reason(tmp_path):
    _inputs(tmp_path)
    record = _run(tmp_path, "--decision-plan", "--decision-queries", str(tmp_path / "missing.csv"))[0]
    assert record["status"] == "ok"
    assert record["result"]["decision_plan"]["status"] == "unavailable"
    configuration = json.loads((tmp_path / "out/configuration.json").read_text())
    assert configuration["inputs"]["decision_queries"]["sha256"] is None


def test_incomplete_search_displays_upper_bound_without_optimality_claim(tmp_path):
    _inputs(tmp_path)
    result = _run(tmp_path, "--decision-plan", "--decision-plan-time-limit", "0")[0]["result"]
    plan = result["decision_plan"]
    assert plan["status"] == "incomplete" and not plan["optimality_verified"]
    assert plan["worst_case_cost"] == 3
    report = (tmp_path / "out/report.html").read_text(encoding="utf-8")
    assert "verified upper bound" in report.lower()
    assert "minimum is not established" in report.lower()


def test_returned_counts_replan_remaining_sample_questions_only(tmp_path):
    _inputs(tmp_path, iid=True)
    _write(tmp_path / "answers.csv", ["cohort_id", "threshold", "unit", "count", "n"],
           [dict(cohort_id="C", threshold=4, unit="mg/L", count=0, n=10)])
    result = _run(tmp_path, "--decision-plan", "--additional-counts", str(tmp_path / "answers.csv"))[0]["result"]
    assert result["decision_plan"]["worst_case_cost"] == 1
    assert result["decision_plan"]["next_question"]["threshold"] == 2
    assert result["additional_information"]["status"] == "applied"
    assert result["population_layer"]["threshold_results"]
    assert result["decision_results"][1]["sample"]["status"] == "supported"
    assert result["decision_results"][1]["population"]["status"] == "undetermined"


def test_laboratory_plan_does_not_consume_known_histogram_answers(tmp_path):
    _inputs(tmp_path)
    rows = [dict(cohort_id="C", panel_id="P", category=str(value), count=count, rank_convention="ceiling")
            for value, count in zip((1, 2, 4, 8, 16), (5, 4, 0, 0, 1))]
    _write(tmp_path / "counts.csv", list(rows[0]), rows)
    result = _run(tmp_path, "--decision-plan", command="reporting-audit", filename="counts.csv")[0]
    assert result["result"]["decision_plan"]["worst_case_cost"] == 2
    assert result["reporting_audit"]["full_histogram"]


def test_report_escapes_planner_reason_and_query_metadata(tmp_path):
    _inputs(tmp_path)
    result = _run(tmp_path)[0]["result"]
    result["decision_plan"] = dict(status="unavailable", reason="<script>bad</script>",
                                   scope="recorded_sample_decisions", next_question=None)
    report = result_sections(result)
    assert "<script>bad</script>" not in report
    assert "&lt;script&gt;bad&lt;/script&gt;" in report


def test_already_resolved_plan_stops_without_changing_population_status(tmp_path):
    _inputs(tmp_path, fraction=".2", iid=True)
    result = _run(tmp_path, "--decision-plan")[0]["result"]
    assert result["decision_plan"]["status"] == "already_resolved"
    assert result["decision_plan"]["worst_case_cost"] == 0
    assert result["decision_plan"]["next_question"] is None
    assert any(row["population"]["status"] == "undetermined" for row in result["decision_results"])
    report = (tmp_path / "out/report.html").read_text(encoding="utf-8")
    assert "No further counts are needed" in report
    assert "Next request:" not in report


def test_query_costs_and_whitelist_are_used_instead_of_defaults(tmp_path):
    _inputs(tmp_path)
    _write(tmp_path / "targets.csv", ["cohort_id", "threshold", "unit", "decision_operator", "decision_fraction"],
           [dict(cohort_id="C", threshold=4, unit="mg/L", decision_operator="<", decision_fraction=".05")])
    queries = [dict(cohort_id="C", threshold=t, unit="mg/L", cost=c)
               for t, c in ((2, "1/3"), (4, "7"), (8, ".1"))]
    _write(tmp_path / "queries.csv", list(queries[0]), queries)
    result = _run(tmp_path, "--decision-plan", "--decision-queries", str(tmp_path / "queries.csv"))[0]["result"]
    assert result["decision_plan"]["worst_case_cost_exact"] == "7"
    assert result["decision_plan"]["next_question"]["threshold"] == 4
    configuration = json.loads((tmp_path / "out/configuration.json").read_text())
    assert configuration["cohorts"][0]["decision_planning"]["queries"][0]["cost"] == "1/3"
    assert configuration["inputs"]["decision_queries"]["sha256"]


@pytest.mark.parametrize("problem", ["unknown_field", "equivalent_cuts", "excluded_bad_cost"])
def test_malformed_query_contract_cannot_be_hidden_by_filtering(tmp_path, problem):
    _inputs(tmp_path)
    queries = [dict(cohort_id="C", threshold=4, unit="mg/L", cost="1")]
    extra = []
    if problem == "unknown_field":
        queries[0]["scope"] = "population"
    elif problem == "equivalent_cuts":
        queries.append({**queries[0], "threshold": 5})
    else:
        queries[0]["cost"] = "-1"
        extra = ["--exclude-direct-targets"]
    _write(tmp_path / "queries.csv", list(queries[0]), queries)
    result = _run(tmp_path, "--decision-plan", "--decision-queries", str(tmp_path / "queries.csv"), *extra)[0]
    assert result["status"] == "ok"
    assert result["result"]["decision_plan"]["status"] == "unavailable"


def test_planner_does_not_consume_counts_that_failed_basic_refinement(tmp_path, monkeypatch):
    from mic_50_90 import count_updates
    from mic_50_90.workflows import analyse_layers

    def failed_update(raw, observations, *, iid, confidence, calibration):
        result = analyse_layers(raw, iid, confidence, calibration)
        result["additional_information"] = dict(
            status="unavailable", reason="controlled solver failure",
            observations=[dict(row, source="controlled test") for row in observations])
        return result

    monkeypatch.setattr(count_updates, "analyse_with_counts", failed_update)
    _inputs(tmp_path)
    _write(tmp_path / "answers.csv", ["cohort_id", "threshold", "unit", "count", "n"],
           [dict(cohort_id="C", threshold=4, unit="mg/L", count=0, n=10)])
    record = _run(tmp_path, "--decision-plan", "--additional-counts", str(tmp_path / "answers.csv"))[0]
    assert record["status"] == "ok"
    assert record["result"]["decision_plan"]["status"] == "unavailable"
    assert "Returned-count analysis" in record["result"]["decision_plan"]["reason"]


def test_no_criterion_preserves_bounds_and_explains_planner_unavailability(tmp_path):
    _inputs(tmp_path)
    _write(tmp_path / "targets.csv", ["cohort_id", "threshold", "unit"],
           [dict(cohort_id="C", threshold=4, unit="mg/L")])
    record = _run(tmp_path, "--decision-plan")[0]
    assert record["status"] == "ok"
    assert record["result"]["decision_plan"]["status"] == "unavailable"
    assert "criterion" in record["result"]["decision_plan"]["reason"]
