from __future__ import annotations


import numpy as np

from mic_50_90.empirical import EmpiricalProblem, empirical_bounds
from mic_50_90.model import parse_spec


def _base_spec(n: int = 100):
    return {
        "mode": "empirical",
        "n": n,
        "panel": {
            "levels": [0.125, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64],
            "left_censored": True,
            "right_censored": True,
        },
        "summaries": {
            "quantiles": [
                {"probability": 0.5, "category": "0.5"},
                {"probability": 0.9, "category": "16"},
            ]
        },
        "thresholds": [2],
    }


def test_sharp_integer_bounds_use_n():
    spec = parse_spec(_base_spec())
    result = empirical_bounds(
        n=spec.n,
        panel=spec.panel,
        quantiles=spec.quantiles,
        threshold=2,
    )
    assert result.panel_lower.count == 11
    assert result.panel_upper.count == 50
    assert result.closed_form_verified
    assert sum(result.panel_lower.histogram) == 100
    assert sum(result.panel_upper.histogram) == 100


def test_small_n_bound_is_three_not_two():
    raw = _base_spec(n=20)
    raw["summaries"]["quantiles"][1]["category"] = "4"
    spec = parse_spec(raw)
    result = empirical_bounds(
        n=20,
        panel=spec.panel,
        quantiles=spec.quantiles,
        threshold=2,
    )
    assert (result.panel_lower.count, result.panel_upper.count) == (3, 10)


def test_right_censored_category_is_strictly_above_boundary():
    raw = {
        "mode": "empirical",
        "n": 20,
        "panel": {"levels": [0.25, 0.5, 1, 2, 4, 8]},
        "summaries": {
            "quantiles": [
                {"probability": 0.5, "category": "0.5"},
                {"probability": 0.9, "category": ">8"},
            ]
        },
        "thresholds": [8],
    }
    spec = parse_spec(raw)
    result = empirical_bounds(
        n=spec.n,
        panel=spec.panel,
        quantiles=spec.quantiles,
        threshold=8,
    )
    assert result.panel_lower.count == 3
    assert result.panel_upper.count == 10
    assert spec.panel.bins[-1].latent_status(8) == "above"


def test_latent_threshold_cutting_bin_expands_identification_set():
    raw = {
        "mode": "empirical",
        "n": 10,
        "panel": {
            "categories": [
                {"label": "<=1", "lower_bound": None, "upper_bound": 1, "lower_closed": False, "upper_closed": True, "panel_value": 1},
                {"label": "2", "lower_bound": 1, "upper_bound": 2, "lower_closed": False, "upper_closed": True, "panel_value": 2},
                {"label": ">2", "lower_bound": 2, "upper_bound": None, "lower_closed": False, "upper_closed": False, "panel_value": 4}
            ]
        },
        "summaries": {"quantiles": [{"probability": 0.5, "category": "2"}]},
        "thresholds": [1.5]
    }
    spec = parse_spec(raw)
    result = empirical_bounds(
        n=10,
        panel=spec.panel,
        quantiles=spec.quantiles,
        threshold=1.5,
    )
    assert result.ambiguous_categories == ("2",)
    assert result.latent_lower.fraction <= result.panel_lower.fraction
    assert result.latent_upper.fraction >= result.panel_upper.fraction


def test_milp_matches_complete_enumeration_for_small_problem():
    raw = {
        "mode": "empirical",
        "n": 7,
        "panel": {"levels": [1, 2, 4], "left_censored": False, "right_censored": False},
        "summaries": {
            "quantiles": [
                {"probability": 0.5, "category": "2"},
                {"probability": 0.9, "category": "4"},
            ],
            "minimum": "1",
            "maximum": "4",
        },
        "thresholds": [2],
    }
    spec = parse_spec(raw)
    problem = EmpiricalProblem(
        n=spec.n,
        panel=spec.panel,
        quantiles=spec.quantiles,
        minimum_index=spec.minimum_index,
        maximum_index=spec.maximum_index,
    )
    tail = spec.panel.panel_tail(2)
    lower, upper = problem.bounds(tail)
    feasible_counts = []
    for x0 in range(8):
        for x1 in range(8 - x0):
            x2 = 7 - x0 - x1
            counts = np.asarray([x0, x1, x2])
            if x0 < 1 or x2 < 1:
                continue
            ordered = np.repeat(np.arange(3), counts)
            if ordered[3] == 1 and ordered[6] == 2:
                feasible_counts.append(int(tail @ counts))
    assert lower.count == min(feasible_counts)
    assert upper.count == max(feasible_counts)

