from __future__ import annotations

import pytest

from mic_50_90.model import MICBin


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [
        (0.5, "ambiguous"),
        (1.0, "below"),
        (1.5, "below"),
    ],
)
def test_left_censored_closed_upper_endpoint(threshold, expected):
    category = MICBin("<=1", None, 1.0, False, True, 1.0)
    assert category.latent_status(threshold) == expected


@pytest.mark.parametrize(
    ("lower_closed", "threshold", "expected"),
    [
        (False, 1.0, "above"),
        (True, 1.0, "ambiguous"),
        (False, 1.5, "ambiguous"),
        (True, 1.5, "ambiguous"),
        (False, 2.0, "below"),
        (True, 2.0, "below"),
    ],
)
def test_threshold_at_open_and_closed_interval_endpoints(
    lower_closed, threshold, expected
):
    category = MICBin("interval", 1.0, 2.0, lower_closed, True, 2.0)
    assert category.latent_status(threshold) == expected


@pytest.mark.parametrize(
    ("lower_closed", "expected"),
    [(False, "above"), (True, "ambiguous")],
)
def test_right_unbounded_category_at_boundary(lower_closed, expected):
    category = MICBin(">2", 2.0, None, lower_closed, False, 4.0)
    assert category.latent_status(2.0) == expected
