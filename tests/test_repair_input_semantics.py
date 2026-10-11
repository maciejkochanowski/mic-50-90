"""Boundary inputs must preserve their declared mathematical meaning."""
import json
from pathlib import Path

import pytest
import jsonschema

from mic_50_90 import parse_spec, plan_decisions
from mic_50_90.cli import main
from mic_50_90.workflows import _integer, read_csv


def specification():
    return {"contract_version": "1.0", "mode": "empirical", "n": 50,
            "panel": {"levels": [1, 2], "left_censored": False, "right_censored": False},
            "summaries": {"quantiles": [{"probability": .14, "category": "1"}]},
            "thresholds": [1], "question_utility": {"enabled": False}}


@pytest.mark.parametrize("probability,rank", [(.14, 7), ("0.14", 7),
    ("0.13999999999999999999999999999999", 7),
    ("0.14000000000000000000000000000001", 8)])
def test_automatic_rank_preserves_decimal_boundary(probability, rank):
    raw = specification()
    raw["summaries"]["quantiles"][0]["probability"] = probability
    assert parse_spec(raw).quantiles[0].rank == rank


def test_false_decision_is_not_certified_and_truthful_answer_is_accepted():
    raw = specification()
    criteria = [{"threshold": 1, "unit": "mg/L", "decision_operator": "<=", "decision_fraction": ".84"}]
    result = plan_decisions(raw, criteria)
    assert result["status"] == "optimal"
    assert result["worst_case_cost"] == 1
    updated = plan_decisions(raw, criteria, additional_counts=[
        {"threshold": 1, "unit": "mg/L", "count": 43, "n": 50}])
    assert updated["status"] == "already_resolved"
    assert updated["criteria"][0]["initial_status"] == "contradicted"


def test_automatic_mic90_matches_exact_large_integer_rank():
    raw = specification()
    raw["n"] = 4503599627370499
    raw["summaries"]["quantiles"][0]["probability"] = .9
    assert parse_spec(raw).quantiles[0].rank == 4053239664633450


@pytest.mark.parametrize("field,value", [("n", "20.000000000000001"),
    ("count", "2.0000000000000001"), ("rank50", "10.0000000000000001"),
    ("rank90", "18.0000000000000001")])
def test_csv_discrete_fields_do_not_round_lexical_fractions(field, value):
    with pytest.raises(ValueError, match="integer"):
        _integer(value, field)


@pytest.mark.parametrize("value", ["20", "20.0", "2e1"])
def test_exact_integer_forms_remain_supported(value):
    assert _integer(value, "n") == 20


def test_analysis_cli_preserves_decimal_n_until_validation(tmp_path):
    raw = specification()
    source = tmp_path / "input.json"
    text = json.dumps(raw).replace('"n": 50', '"n": 50.000000000000001')
    source.write_text(text)
    with pytest.raises(SystemExit) as error:
        main(["analyse", str(source), "--output", str(tmp_path / "output.json")])
    assert error.value.code == 2
    assert not (tmp_path / "output.json").exists()


def test_analysis_cli_renders_exact_quantile_probability_in_html(tmp_path):
    raw = specification()
    token = "0.13999999999999999999999999999999"
    raw["summaries"]["quantiles"][0]["probability"] = token
    source = tmp_path / "input.json"
    output, report = tmp_path / "output.json", tmp_path / "report.html"
    source.write_text(json.dumps(raw))
    assert main(["analyse", str(source), "--output", str(output), "--html", str(report)]) == 0
    assert token in report.read_text(encoding="utf-8")
    assert json.loads(output.read_text())["reported_summaries"]["quantiles"][0]["rank"] == 7


def test_likelihood_distinguishes_exact_neighboring_quantile_probabilities():
    from math import comb
    from mic_50_90.likelihood import order_event_probability
    raw = specification()
    raw["summaries"]["quantiles"] = [
        {"probability": "0.14", "category": "1"},
        {"probability": "0.14000000000000000000000000000001", "category": "2"}]
    spec = parse_spec(raw)
    result = order_event_probability([.5, .5], n=50, quantiles=spec.quantiles)
    assert result == pytest.approx(comb(50, 7) * .5**50, rel=1e-12)
    from mic_50_90.population import fit_population_mle
    fit = fit_population_mle(k=2, n=50, quantiles=spec.quantiles,
                             minimum_index=None, maximum_index=None)
    assert fit.success
    assert fit.probabilities[0] == pytest.approx(.14, abs=1e-5)


def test_analysis_cli_preserves_quantile_token_and_exact_rank_on_roundtrip(tmp_path):
    raw = specification()
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    token = "0.13999999999999999999999999999999"
    source.write_text(json.dumps(raw).replace('"probability": 0.14', '"probability": ' + token))
    assert main(["analyse", str(source), "--output", str(output)]) == 0
    summary = json.loads(output.read_text())["reported_summaries"]["quantiles"][0]
    assert summary["rank"] == 7
    assert summary["probability"] == token


@pytest.mark.parametrize("field", ["lower_closed", "upper_closed"])
def test_json_explicit_category_closure_requires_booleans(field):
    raw = specification()
    raw["panel"] = parse_spec(raw).panel.as_dict()
    raw["panel"]["categories"][0][field] = "false"
    with pytest.raises(ValueError, match=field):
        parse_spec(raw)


@pytest.mark.parametrize("field", ["left_censored", "right_censored"])
@pytest.mark.parametrize("value", ["false", 0, None])
def test_json_panel_flags_require_booleans(field, value):
    raw = specification()
    raw["panel"][field] = value
    with pytest.raises(ValueError, match=field):
        parse_spec(raw)


@pytest.mark.parametrize("area,field", [("question_utility", "enabled"),
    ("question_utility", "exclude_direct_target_questions"),
    ("population", "profile_likelihood_enabled"), ("population", "bayes_enabled")])
def test_optional_json_flags_are_not_truthiness_conversions(area, field):
    raw = specification()
    raw.setdefault(area, {})[field] = "false"
    with pytest.raises(ValueError, match=field):
        parse_spec(raw)


def test_unknown_reference_label_is_rejected_before_normalizing():
    raw = specification()
    raw["reference_distribution"] = {"1": .8, "2_typo": .2}
    with pytest.raises(ValueError, match="2_typo"):
        parse_spec(raw)


def test_omitted_known_reference_label_is_an_explicit_zero_default():
    raw = specification()
    raw["reference_distribution"] = {"1": 1}
    assert parse_spec(raw).reference_distribution.tolist() == [1, 0]


@pytest.mark.parametrize("field", ["cohort_id", "panel_id", "variant_id", "unit_id"])
def test_csv_identifier_whitespace_is_not_a_join_normalization(tmp_path, field):
    path = tmp_path / "identity.csv"
    path.write_text(f"{field},count\n example ,8\n")
    with pytest.raises(ValueError, match="identity.csv.*row 2"):
        read_csv(path)


def test_mismatched_returned_count_does_not_narrow_a_cohort(tmp_path):
    example = Path(__file__).resolve().parents[1] / "examples/csv"
    answers = tmp_path / "answers.csv"
    answers.write_text("cohort_id,threshold,unit,count,n\n example ,2,mg/L,8,20\n")
    output = tmp_path / "out"
    with pytest.raises(SystemExit) as error:
        main(["batch", str(example / "summaries.csv"), "--panels", str(example / "panels.csv"),
              "--targets", str(example / "targets.csv"), "--additional-counts", str(answers),
              "--output-dir", str(output), "--fail-on-refusal"])
    assert error.value.code == 2
    assert not (output / "results.json").exists()


def test_discrete_values_outside_supported_double_integer_range_are_refused():
    raw = specification()
    raw["n"] = 2**53
    with pytest.raises(ValueError, match="supported integer range"):
        parse_spec(raw)


def test_declared_schema_and_parser_accept_exact_decimal_probability():
    raw = specification()
    raw["summaries"]["quantiles"][0]["probability"] = "0.13999999999999999999999999999999"
    schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/input.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(raw)
    assert parse_spec(raw).quantiles[0].rank == 7
