from __future__ import annotations

import numpy as np
import pytest

from mic_50_90.dro import wasserstein_bounds
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import parse_spec
from mic_50_90.scenarios import kl_projection, maximum_entropy
from mic_50_90.utility import rank_tail_count_questions


def _problem():
    raw = {
        "mode": "empirical",
        "n": 20,
        "panel": {"levels": [0.5, 1, 2, 4, 8], "left_censored": False, "right_censored": False},
        "summaries": {
            "quantiles": [
                {"probability": 0.5, "category": "1"},
                {"probability": 0.9, "category": "4"},
            ]
        },
        "thresholds": [1, 2],
    }
    spec = parse_spec(raw)
    problem = EmpiricalProblem(n=20, panel=spec.panel, quantiles=spec.quantiles)
    return spec, problem


def test_maximum_entropy_is_feasible():
    spec, problem = _problem()
    result = maximum_entropy(problem)
    matrix, lower, upper = problem.linear_constraints
    values = matrix @ np.asarray(result.probabilities) * problem.n
    assert np.all(values[np.isfinite(lower)] >= lower[np.isfinite(lower)] - 1e-6)
    assert np.all(values[np.isfinite(upper)] <= upper[np.isfinite(upper)] + 1e-6)


def test_kl_projection_does_not_silently_smooth_conflicting_zeros():
    spec, problem = _problem()
    reference = np.asarray([0.5, 0.5, 0, 0, 0])
    with pytest.raises(ValueError, match="does not silently smooth"):
        kl_projection(problem, reference)


def test_zero_radius_wasserstein_returns_feasible_reference_point():
    spec, problem = _problem()
    witness = np.asarray(problem._solve(np.zeros(problem.k)).histogram, dtype=float) / problem.n
    tail = spec.panel.panel_tail(2)
    result = wasserstein_bounds(
        problem=problem,
        reference=witness,
        radius=0.0,
        objective=tail,
    )
    truth = float(tail @ witness)
    assert result.lower == pytest.approx(truth, abs=1e-9)
    assert result.upper == pytest.approx(truth, abs=1e-9)


def test_question_ranking_is_nontrivial_and_bounded():
    spec, problem = _problem()
    questions = rank_tail_count_questions(
        problem=problem,
        target_objectives=[spec.panel.panel_tail(1), spec.panel.panel_tail(2)],
        exclude_direct_targets=True,
    )
    assert questions
    assert questions[0].minimax_width_reduction >= 0
    assert questions[0].worst_case_residual_width <= questions[0].baseline_total_width + 1e-9



def _returned_count_problem():
    raw = {
        "mode": "empirical",
        "n": 10,
        "panel": {"levels": [1, 2, 4, 8, 16], "left_censored": False, "right_censored": False},
        "summaries": {"quantiles": [{"probability": 0.5, "category": "1"}, {"probability": 0.9, "category": "2"}]},
        "thresholds": [2],
    }
    spec = parse_spec(raw)
    problem = EmpiricalProblem(n=10, panel=spec.panel, quantiles=spec.quantiles)
    for cut, count in ((2, 1), (4, 0), (8, 0)):
        problem = problem.with_count_interval(spec.panel.panel_tail(cut), count, count)
    return problem


def test_maximum_entropy_reaches_the_optimum_when_counts_fix_the_upper_categories():
    # One result above 2 and none above 4: shares (p1, p2, 0.1, 0, 0) with p1 >= 0.5 and p1 + p2 = 0.9.
    # The entropy is largest at the boundary p1 = 0.5, not at the witness table (0.8, 0.1, 0.1, 0, 0).
    result = maximum_entropy(_returned_count_problem())
    assert result.probabilities == pytest.approx((0.5, 0.4, 0.1, 0.0, 0.0), abs=1e-7)


def test_kl_projection_reaches_the_optimum_from_a_vertex_start():
    problem = _returned_count_problem()
    reference = np.asarray([0.2, 0.2, 0.2, 0.2, 0.2])
    # With a uniform reference the KL projection equals the maximum-entropy shares.
    result = kl_projection(problem, reference)
    assert result.probabilities == pytest.approx((0.5, 0.4, 0.1, 0.0, 0.0), abs=1e-7)
