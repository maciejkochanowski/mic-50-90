"""Check precision-based reporting against exhaustive histograms and partitions."""
from itertools import combinations

import numpy as np
import pytest

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel, QuantileSummary


def histograms(n, k):
    if k == 1:
        yield (n,)
        return
    for first in range(n + 1):
        for rest in histograms(n - first, k - 1):
            yield (first, *rest)


def compatible(problems):
    first = next(iter(problems.values()))
    keep = []
    for histogram in histograms(first.n, first.k):
        h = np.asarray(histogram)
        for problem in problems.values():
            matrix, low, high = problem.linear_constraints
            value = matrix @ h
            if np.all(value >= low) and np.all(value <= high):
                keep.append(h)
                break
    return np.stack(keep)


def reference_partition(problems, precision_pp):
    from fractions import Fraction
    h = compatible(problems)
    n, k = h[0].sum(), h.shape[1]
    tolerance = int(Fraction(str(precision_pp)) * int(n) / 100)
    prefix = np.column_stack((np.zeros(len(h), dtype=int), np.cumsum(h, axis=1)))
    candidates = []
    for count in range(k):
        for middle in combinations(range(1, k), count):
            cuts = (0, *middle, k)
            valid = all(np.ptp(prefix[:, b] - prefix[:, a]) <= tolerance and np.ptp(prefix[:, b]) <= tolerance
                        for a, b in zip(cuts, cuts[1:]))
            if valid:
                candidates.append(cuts)
    return min(candidates, key=lambda cuts: (-len(cuts), cuts)), h


def cases():
    panel = MICPanel.from_twofold_levels([1, 2, 4])
    base = EmpiricalProblem(n=4, panel=panel, quantiles=[])
    interior = base.with_count_interval(np.array([0, 1, 1, 0]), 1, 2)
    left = base.with_equality(np.array([1, 1, 0, 0]), 1)
    right = base.with_equality(np.array([1, 1, 0, 0]), 3)
    summary = EmpiricalProblem(n=4, panel=panel,
        quantiles=[QuantileSummary.from_dict({"probability": .5, "category": "2", "convention": "ceiling"}, n=4, panel=panel)])
    return [{"primary": base}, {"primary": interior}, {"left": left, "right": right}, {"primary": summary}]


@pytest.mark.parametrize("problems", cases())
@pytest.mark.parametrize("precision_pp", [0, 10, 25, 33.3, 50, 100])
def test_maximum_resolution_matches_exhaustive_partitions(problems, precision_pp):
    from mic_50_90.distribution_resolution import maximum_resolvable_partition
    expected, h = reference_partition(problems, precision_pp)
    result = maximum_resolvable_partition(problems, precision_pp=precision_pp)
    assert tuple(result["cut_indices"]) == expected
    assert result["number_of_bins"] == len(expected) - 1
    assert result["optimality_verified"]
    for row, a, b in zip(result["bins"], expected, expected[1:]):
        values = h[:, a:b].sum(axis=1)
        assert row["count_lower"] == values.min()
        assert row["count_upper"] == values.max()
        assert row["width_pp"] <= precision_pp


def test_complete_histogram_preserves_every_category_at_zero_tolerance():
    from mic_50_90.distribution_resolution import maximum_resolvable_partition
    panel = MICPanel.from_twofold_levels([1, 2, 4])
    problem = EmpiricalProblem(n=4, panel=panel, quantiles=[],
        equalities=[(np.eye(4)[i], count) for i, count in enumerate([0, 1, 1, 2])])
    result = maximum_resolvable_partition({"primary": problem}, precision_pp=0)
    assert result["cut_indices"] == [0, 1, 2, 3, 4]
    assert [row["count_lower"] for row in result["bins"]] == [0, 1, 1, 2]


@pytest.mark.parametrize("precision", [-1, 101, float("nan"), float("inf"), True, "bad"])
def test_invalid_precision_is_rejected(precision):
    from mic_50_90.distribution_resolution import maximum_resolvable_partition
    with pytest.raises(ValueError, match="precision"):
        maximum_resolvable_partition(cases()[0], precision_pp=precision)


def test_same_probability_precision_requires_cumulative_and_category_widths():
    from mic_50_90.distribution_resolution import maximum_resolvable_partition
    panel = MICPanel.from_twofold_levels([1, 2])
    problem = EmpiricalProblem(n=20, panel=panel, quantiles=[], count_intervals=[
        (np.array([1, 0, 0]), 8, 9), (np.array([1, 1, 0]), 10, 11)])
    result = maximum_resolvable_partition({"primary": problem}, precision_pp=5)
    # Each CDF boundary has width 5 pp, but the middle cell has width 10 pp.
    assert result["number_of_bins"] == 2
    assert result["cut_indices"] == [0, 1, 3]
