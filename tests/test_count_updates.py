"""Returned counts preserve the sample contract and calibrated tail event."""
import copy
import itertools

import numpy as np
import pytest

from mic_50_90.conformal import calibrate_wasserstein_manifest
from mic_50_90.dro import wasserstein_bounds
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.exact_population import clopper_pearson
from mic_50_90.model import parse_spec


def feature():
    from mic_50_90.count_updates import analyse_with_counts
    return analyse_with_counts


def specification(n=6):
    return dict(contract_version="1.0", mode="empirical", n=n,
                panel=dict(levels=[1, 2, 4], left_censored=False, right_censored=False),
                summaries={"quantiles": [{"probability": .5, "category": "1", "convention": "ceiling"},
                                          {"probability": .9, "category": "4", "convention": "ceiling"}]},
                thresholds=[1, 2], question_utility={"enabled": False})


def returned(threshold=1, count=2, n=6):
    return dict(threshold=threshold, count=count, n=n, unit="mg/L", source="verified aggregate")


def calibration():
    contract = dict(score_kind="simultaneous_tail_intervals", reference_rule="projected",
                    functional_scope="all_panel_tails", transport_unit="log2_mg_L",
                    summary_policy="ceiling_50_90_no_range", reference_protocol="synthetic-fixed",
                    unit_definition="one complete synthetic unit")
    manifest = calibrate_wasserstein_manifest(
        group_scores=[1/6]*9, group_units=[f"cal-{i}" for i in range(9)], alpha=.1,
        grouping={"example": "witness-loss"}, source="synthetic regression",
        data_hashes={"example": "synthetic"}, calibrate_on="units",
        calibration_contract=contract).as_dict()
    return dict(reference_distribution=[.5, 1/3, 1/6],
                wasserstein_calibration_manifest=manifest,
                calibration_context=dict(unit="mg/L", reference_protocol="synthetic-fixed",
                                         grouping={"example": "witness-loss"}))


def sample_counts(result):
    return [(x["panel_recorded_estimand"]["lower"]["count"],
             x["panel_recorded_estimand"]["upper"]["count"])
            for x in result["reporting_uncertainty_envelope"]["envelope"]]


def test_true_returned_count_refines_sample_without_changing_input():
    raw = specification()
    saved = copy.deepcopy(raw)
    result = feature()(raw, [returned()])
    assert raw == saved
    assert sample_counts(result) == [(2, 2), (1, 2)]
    assert result["additional_information"]["status"] == "applied"
    assert result["additional_information"]["observations"][0]["n"] == 6
    # Both original tail widths are 2/6; after the count their sum is 1/6.
    assert result["additional_information"]["observed_width_reduction"] == pytest.approx(3/6)


def test_population_update_retains_extreme_bonferroni_confidence():
    result = feature()(specification(), [returned()], iid=True,
        confidence=np.nextafter(1., 0.))
    assert 'population_unavailable_reason' not in result
    rows = result['population_layer']['threshold_results']
    assert len(rows) == 2
    assert all('confidence_level_exact' in row['exact_count_confidence']['simultaneous_bonferroni'] for row in rows)


def test_safe_update_retains_truth_lost_by_naive_wasserstein_restriction():
    raw = specification()
    result = feature()(raw, [returned()], calibration=calibration())
    conf = result["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"]
    assert conf["threshold_results"][1]["envelope"]["upper"] == pytest.approx(2/6)
    assert conf["threshold_results"][0]["envelope"] == {"lower": 2/6, "upper": 2/6}
    assert conf["update_rule"] == "unchanged_tail_bands_and_truthful_counts"
    spec = parse_spec(raw)
    problem = EmpiricalProblem(n=6, panel=spec.panel, quantiles=spec.quantiles)
    naive = wasserstein_bounds(problem=problem.with_equality(spec.panel.panel_tail(1), 2),
                               reference=np.array([.5, 1/3, 1/6]), radius=1/6,
                               objective=spec.panel.panel_tail(2))
    assert naive.upper == pytest.approx(1/6)
    assert naive.upper < 2/6


def test_count_conflicting_with_calibration_does_not_erase_sharp_answer():
    result = feature()(specification(), [returned(count=1)], calibration=calibration())
    assert sample_counts(result) == [(1, 1), (1, 1)]
    conf = result["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"]
    assert all(row["envelope"] is None for row in conf["threshold_results"])
    assert "incompatible" in result["conformal_unavailable_reason"].lower()
    assert result["additional_information"]["status"] == "applied"


@pytest.mark.parametrize("observation", [
    returned(n=7), returned(count=-1), returned(count=7), returned(count=1.2),
    returned(count=True), returned(threshold=float("nan")), returned(threshold=0),
    {**returned(), "unit": "unknown"}, {**returned(), "n": ""},
    {**returned(), "scale": "latent"},
])
def test_invalid_or_ambiguous_observations_are_rejected(observation):
    with pytest.raises(ValueError):
        feature()(specification(), [observation])


def test_duplicate_equivalent_cuts_and_impossible_counts_are_rejected():
    for observations in ([returned(), returned()],
                         [returned(), returned(threshold=1.5)],
                         [returned(count=5)], []):
        with pytest.raises(ValueError):
            feature()(specification(), observations)


def test_all_declared_variants_receive_the_count_and_incompatible_one_is_retained_as_rejected():
    raw = specification()
    raw["reporting_envelope"] = {"variants": [
        {"id": "other-rank", "summaries": {"quantiles": [
            {"probability": .5, "rank": 4, "category": "1"},
            {"probability": .9, "rank": 6, "category": "4"}]}}]}
    result = feature()(raw, [returned(count=3)])
    assert sample_counts(result)[0] == (3, 3)
    envelope = result["reporting_uncertainty_envelope"]
    assert [x["id"] for x in envelope["per_variant"]] == ["primary"]
    assert any(x["id"] == "other-rank" for x in envelope["rejected_variants"])


def test_iid_population_reuses_realized_count_and_preserves_family_adjustment():
    result = feature()(specification(), [returned()], iid=True)
    exact = result["population_layer"]["threshold_results"][0]["exact_count_confidence"]
    assert exact["marginal"]["admissible_count_ranges"] == [[2, 2]]
    assert exact["marginal"]["confidence_set_hull"] == pytest.approx(clopper_pearson(2, 6, .95))
    assert exact["simultaneous_bonferroni"]["confidence_set_hull"] == pytest.approx(
        clopper_pearson(2, 6, .975))


def test_remaining_question_uses_refined_information_not_stale_recommendation():
    raw = specification()
    raw["question_utility"] = {"enabled": True}
    result = feature()(raw, [returned()])
    best = result["one_question_recovery"]["best_question"]
    assert best["cut_index"] == 1
    assert best["minimax_width_reduction"] == pytest.approx(1/6)


def test_user_radius_is_not_promoted_to_calibrated_guarantee():
    raw = {**specification(), "reference_distribution": [.5, 1/3, 1/6], "wasserstein_radius": 1/6}
    result = feature()(raw, [returned()])
    conf = result["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"]
    assert conf["guarantee_class"] == "assumption_scenario"
    assert "conformal_unavailable_reason" in result
    assert "No coverage guarantee" in conf["update_interpretation"]


def test_refinement_solver_failure_retains_original_results(monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("injected count solver failure")
    monkeypatch.setattr(EmpiricalProblem, "with_equality", failed)
    result = feature()(specification(), [returned()])
    assert sample_counts(result) == [(1, 3), (1, 3)]
    assert result["additional_information"]["status"] == "unavailable"
    assert "injected" in result["additional_information"]["reason"]


def test_two_counts_identify_recorded_histogram_but_preserve_latent_uncertainty():
    raw=specification()
    raw["panel"]={"levels":[1,2,4],"left_censored":True,"right_censored":False}
    raw["summaries"]["quantiles"][0]["category"]="<=1"
    raw["thresholds"]=[.5, 1, 2]
    result=feature()(raw,[returned(),returned(threshold=2,count=2)])
    row=result["reporting_uncertainty_envelope"]["envelope"][0]
    assert row["panel_recorded_estimand"]["width"] == 0
    assert row["latent_interval_estimand"]["width"] > 0


def test_independent_histogram_enumeration_after_two_truthful_counts():
    raw = specification(10)
    # Independent stars-and-bars enumeration and finite rank inequalities.
    compatible = []
    for a in range(11):
        for b in range(11-a):
            c = 10-a-b
            if a >= 5 and a+b <= 8:
                compatible.append((a, b, c))
    for threshold, answer in itertools.product((1, 2), range(2, 6)):
        subset = [h for h in compatible if sum(h[threshold:]) == answer]
        if not subset:
            continue
        result = feature()(raw, [returned(threshold=threshold, count=answer, n=10)])
        expected = [(min(sum(h[j:]) for h in subset), max(sum(h[j:]) for h in subset))
                    for j in (1, 2)]
        assert sample_counts(result) == expected
