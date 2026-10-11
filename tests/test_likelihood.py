from __future__ import annotations

from math import factorial

import numpy as np
import pytest

from mic_50_90.likelihood import order_event_probability
from mic_50_90.model import parse_spec


def _compositions(n: int, k: int):
    if k == 1:
        yield (n,)
        return
    for first in range(n + 1):
        for rest in _compositions(n - first, k - 1):
            yield (first, *rest)


def _multinomial_probability(counts, p):
    coefficient = factorial(sum(counts))
    for value in counts:
        coefficient //= factorial(value)
    result = float(coefficient)
    for count, probability in zip(counts, p):
        result *= probability**count
    return result


@pytest.mark.parametrize("with_range", [False, True])
def test_exact_event_likelihood_matches_multinomial_enumeration(with_range):
    raw = {
        "mode": "population",
        "n": 6,
        "panel": {"levels": [1, 2, 4], "left_censored": False, "right_censored": False},
        "summaries": {
            "quantiles": [
                {"probability": 0.5, "category": "2"},
                {"probability": 0.9, "category": "4"},
            ]
        },
        "thresholds": [2],
    }
    if with_range:
        raw["summaries"].update({"minimum": "1", "maximum": "4"})
    spec = parse_spec(raw)
    p = np.asarray([0.31, 0.42, 0.27])
    expected = 0.0
    for counts in _compositions(spec.n, len(p)):
        ordered = np.repeat(np.arange(len(p)), counts)
        if ordered[2] != 1 or ordered[5] != 2:
            continue
        if with_range and (ordered[0] != 0 or ordered[-1] != 2):
            continue
        expected += _multinomial_probability(counts, p)
    observed = order_event_probability(
        p,
        n=spec.n,
        quantiles=spec.quantiles,
        minimum_index=spec.minimum_index,
        maximum_index=spec.maximum_index,
    )
    assert observed == pytest.approx(expected, abs=2e-14)


def test_same_category_joint_quantiles_match_enumeration():
    raw = {
        "mode": "population",
        "n": 5,
        "panel": {"levels": [1, 2, 4], "left_censored": False, "right_censored": False},
        "summaries": {
            "quantiles": [
                {"probability": 0.5, "category": "2"},
                {"probability": 0.8, "category": "2"},
            ]
        },
        "thresholds": [2],
    }
    spec = parse_spec(raw)
    p = np.asarray([0.2, 0.6, 0.2])
    expected = 0.0
    for counts in _compositions(5, 3):
        ordered = np.repeat(np.arange(3), counts)
        if ordered[2] == 1 and ordered[3] == 1:
            expected += _multinomial_probability(counts, p)
    observed = order_event_probability(p, n=5, quantiles=spec.quantiles)
    assert observed == pytest.approx(expected, abs=2e-14)

