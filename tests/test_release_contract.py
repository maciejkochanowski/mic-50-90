"""Regressions derived from independent counterexamples for release 1.1."""
from copy import deepcopy
from itertools import product

import numpy as np
import pytest

from mic_50_90.analysis import analyse_spec
from mic_50_90.conformal import calibrate_wasserstein_manifest
from mic_50_90.dro import critical_radius, wasserstein_1d
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import parse_spec


def raw_spec():
    return {"n": 10, "panel": {"levels": [1, 2, 4, 8, 16],
            "left_censored": False, "right_censored": False},
            "summaries": {"quantiles": [{"probability": .5, "category": "2"},
                                        {"probability": .9, "category": "16"}]},
            "thresholds": [2, 8], "question_utility": {"enabled": False}}


def problem():
    spec = parse_spec(raw_spec())
    return EmpiricalProblem(n=spec.n, panel=spec.panel, quantiles=spec.quantiles)


def contract():
    return {"score_kind": "simultaneous_tail_intervals",
            "reference_rule": "projected", "functional_scope": "all_panel_tails",
            "transport_unit": "log2_mg_L",
            "summary_policy": "ceiling_50_90_no_range",
            "reference_protocol": "fixed-training-pool-v1",
            "unit_definition": "independent study; max over its eligible cohorts"}


def manifest():
    return calibrate_wasserstein_manifest(
        group_scores=[0.0] * 19, group_units=[f"study-{i}" for i in range(19)],
        calibrate_on="units", alpha=.1, grouping={"species": "test"},
        source="controlled calibration", data_hashes={"fixture": "a"*64},
        calibration_contract=contract()).as_dict()


def test_solver_failure_never_becomes_a_zero_calibration_score(monkeypatch):
    def failed(**kwargs):
        raise RuntimeError("controlled solver failure")
    monkeypatch.setattr("mic_50_90.dro.wasserstein_bounds", failed)
    with pytest.raises(RuntimeError, match="controlled solver failure"):
        critical_radius(problem=problem(), reference=np.ones(5), positions=None,
                        objectives=[np.array([0, 0, 0, 0, 1])], truths=[.2])


@pytest.mark.parametrize("objectives,truths", [([], []), ([np.ones(5)], []),
                                              ([np.ones(5)], [float("nan")])])
def test_invalid_score_targets_are_refused(objectives, truths):
    with pytest.raises(ValueError):
        critical_radius(problem=problem(), reference=np.ones(5), positions=None,
                        objectives=objectives, truths=truths)


@pytest.mark.parametrize("p", [[float("nan"), 1], [-1, 2], [0, 0]])
def test_invalid_transport_probabilities_are_refused(p):
    with pytest.raises(ValueError):
        wasserstein_1d(np.array(p), np.array([.5, .5]), np.array([1., 2.]))


def test_independent_100_histogram_oracle_checks_multi_target_gain():
    hist = [(a,b,c,d,10-a-b-c-d) for a,b,c,d in product(range(11), repeat=4)
            if 10-a-b-c-d >= 0 and a < 5 <= a+b and a+b+c+d < 9]
    assert len(hist) == 100
    def width(rows):
        tails = [(c+d+e, e) for a,b,c,d,e in rows]
        return sum(max(x[i] for x in tails)-min(x[i] for x in tails) for i in (0,1))/10
    assert width(hist) == .6
    assert [width([h for h in hist if h[3]+h[4]==answer]) for answer in (2,3,4,5)] == [.3]*4
    raw = raw_spec()
    raw["question_utility"] = {"enabled": True, "exclude_direct_target_questions": True}
    best = analyse_spec(raw)["one_question_recovery"]["best_question"]
    assert best["minimax_width_reduction"] == pytest.approx(.3)
    assert best["worst_case_residual_width"] == pytest.approx(.3)


def test_zero_gain_is_not_recommended_and_direct_counts_are_default():
    raw = raw_spec()
    raw["thresholds"] = [2]
    raw["question_utility"] = {"enabled": True, "exclude_direct_target_questions": True}
    assert analyse_spec(raw)["one_question_recovery"]["best_question"] is None
    raw["question_utility"] = {"enabled": True}
    result = analyse_spec(raw)["one_question_recovery"]
    assert result["direct_target_questions_excluded"] is False
    assert result["best_question"]["minimax_width_reduction"] == pytest.approx(.3)


def test_deadline_preserves_core_bounds_without_claiming_an_optimum():
    raw = raw_spec()
    raw["question_utility"] = {"enabled": True, "time_limit_seconds": 0}
    result = analyse_spec(raw)
    assert result["identification"][0]["panel_recorded_estimand"]["lower"]["count"] == 2
    assert result["one_question_recovery"]["search_complete"] is False
    assert result["one_question_recovery"]["best_question"] is None


def test_manifest_scope_projection_and_fixed_rank_level_with_ties():
    m = manifest()
    assert m["manifest_version"] == "1.2"
    assert m["confidence_level"] == pytest.approx(.9)  # rank 18 / (19+1), not tie count 19/20
    raw = raw_spec()
    raw["reference_distribution"] = [1,0,0,0,0]  # outside sharp set
    raw["wasserstein_calibration_manifest"] = m
    raw["calibration_context"] = {"reference_protocol": "fixed-training-pool-v1",
                                 "grouping": {"species": "test"}, "unit": "mg/L"}
    result = analyse_spec(raw)["assumption_dependent_scenarios"]["wasserstein_ambiguity_set"]
    assert all(x["envelope"] is not None for x in result["threshold_results"])
    assert result["guarantee_class"] == "conformal_new_cohort"
    assert result["distribution_coverage_claimed"] is False
    assert result["reference_rule"] == "projected"
    bad = deepcopy(raw)
    bad["summaries"]["minimum"] = "1"
    with pytest.raises(ValueError, match="summary"):
        analyse_spec(bad)
    bad = deepcopy(raw)
    bad["calibration_context"]["reference_protocol"] = "other"
    with pytest.raises(ValueError, match="reference_protocol"):
        analyse_spec(bad)


def test_legacy_manifest_requires_migration_before_new_guarantee():
    from test_conformal import _legacy_manifest
    raw = raw_spec()
    raw["reference_distribution"] = [1,1,1,1,1]
    raw["wasserstein_calibration_manifest"] = _legacy_manifest('legacy_application')
    with pytest.raises(ValueError, match="migrat"):
        analyse_spec(raw)
