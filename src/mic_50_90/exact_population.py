"""Exact iid population inference induced by partially identified tail counts."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy.stats import beta

from .empirical import EmpiricalProblem
from .model import _positive_integer


def clopper_pearson(count: int, n: int, confidence_level: float) -> tuple[float, float]:
    """Two-sided equal-tailed Clopper-Pearson interval for a binomial probability."""
    n = _positive_integer(n, "n")
    try:
        m = int(count)
        if isinstance(count, (bool, np.bool_)) or float(count) != m or not 0 <= m <= n:
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise ValueError("count must be an exact integer in 0..n") from None
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must lie in (0, 1)")
    alpha = float(1-confidence_level) if isinstance(confidence_level, Fraction) else 1.0-float(confidence_level)
    lower = 0.0 if m == 0 else float(beta.ppf(alpha / 2.0, m, n - m + 1))
    upper_quantile = 1.0-alpha/2.0
    upper = (1.0 if m == n else float(beta.isf(alpha/2.0, m+1, n-m))
             if upper_quantile == 1.0 else float(beta.ppf(upper_quantile, m+1, n-m)))
    return lower, upper


def _bonferroni_level(confidence_level: float, family_size: int):
    """Keep the family error probability when subtraction would round to one."""
    adjusted = 1.0-(1.0-confidence_level)/family_size
    if adjusted == 1.0:
        return 1-(1-Fraction(float(confidence_level)))/family_size
    return adjusted


def _merge_integer_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for lower, upper in sorted(ranges):
        if not merged or lower > merged[-1][1] + 1:
            merged.append([int(lower), int(upper)])
        else:
            merged[-1][1] = max(merged[-1][1], int(upper))
    return [(lower, upper) for lower, upper in merged]


def _merge_probability_intervals(
    intervals: list[tuple[float, float]], tolerance: float = 1e-14
) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for lower, upper in sorted(intervals):
        if not merged or lower > merged[-1][1] + tolerance:
            merged.append([float(lower), float(upper)])
        else:
            merged[-1][1] = max(merged[-1][1], float(upper))
    return [(lower, upper) for lower, upper in merged]


@dataclass(frozen=True)
class ExactCountConfidenceResult:
    confidence_level: float
    count_ranges: tuple[tuple[int, int], ...]
    probability_components: tuple[tuple[float, float], ...]
    variant_count_ranges: dict[str, tuple[int, int]]
    endpoint_certificates: dict[str, dict[str, object]]
    confidence_level_exact: str | None = None

    @property
    def hull(self) -> tuple[float, float]:
        return (
            min(item[0] for item in self.probability_components),
            max(item[1] for item in self.probability_components),
        )

    def as_dict(self) -> dict[str, object]:
        result = {
            "guarantee_class": "exact_iid_population",
            "confidence_level": self.confidence_level,
            "admissible_count_ranges": [list(item) for item in self.count_ranges],
            "variant_count_ranges": {
                key: list(value) for key, value in self.variant_count_ranges.items()
            },
            "confidence_set_components": [
                list(item) for item in self.probability_components
            ],
            "confidence_set_hull": list(self.hull),
            "endpoint_certificates": self.endpoint_certificates,
            "coverage_statement": (
                "At least the stated finite-sample coverage for P(recorded panel MIC > threshold) "
                "under iid sampling because the realised binomial count is contained in the "
                "declared reporting-envelope count set."
            ),
        }
        if self.confidence_level_exact is not None:
            result['confidence_level_exact'] = self.confidence_level_exact
            result['confidence_level_is_rounded'] = True
        return result


def exact_count_confidence(
    *,
    problems: dict[str, EmpiricalProblem],
    objective: np.ndarray,
    confidence_level: float,
) -> ExactCountConfidenceResult:
    """Union exact binomial intervals over all reporting-compatible tail counts.

    For each canonical reporting variant, the tail-count projection is every
    integer between the LP extrema: adding a tail-count equality preserves the
    interval-row TU property. The union across variants may be disconnected.

    Raises ValueError for custom noncanonical/nonintegral constraints or a
    non-tail objective, where extrema alone do not identify the attainable
    integer count set. Such problems remain supported for deterministic MILP
    bounds, but their interior count support must be established separately.
    """
    if not problems:
        raise ValueError("at least one feasible reporting variant is required")
    sample_sizes = {problem.n for problem in problems.values()}
    if len(sample_sizes) != 1:
        raise ValueError("all reporting variants must have the same sample size")
    n = sample_sizes.pop()
    first = next(iter(problems.values()))
    if any(problem.panel != first.panel for problem in problems.values()):
        raise ValueError("all reporting variants must share the same panel geometry")
    objective = np.asarray(objective, dtype=float)
    if (objective.shape != (first.k,) or not np.all(np.isin(objective, (0., 1.)))
            or np.any(np.diff(objective) < 0)):
        raise ValueError("exact count confidence requires a finite monotone binary tail objective")
    if any(not problem.has_total_unimodular_canonical_matrix or not problem._integral_rhs
           for problem in problems.values()):
        raise ValueError("exact count confidence requires canonical integral interval-row constraints")
    ranges: list[tuple[int, int]] = []
    by_variant: dict[str, tuple[int, int]] = {}
    certificates: dict[str, dict[str, object]] = {}
    for identifier, problem in problems.items():
        lower, upper = problem.bounds(objective)
        run = (lower.count, upper.count)
        by_variant[identifier] = run
        ranges.append(run)
        certificates[identifier] = {
            "lower": lower.certificate.as_dict(),
            "upper": upper.certificate.as_dict(),
            "count_projection_contiguous_by_tu": bool(
                problem.has_total_unimodular_canonical_matrix
            ),
        }
    merged_ranges = _merge_integer_ranges(ranges)
    probability_intervals: list[tuple[float, float]] = []
    for lower_count, upper_count in merged_ranges:
        lower_probability = clopper_pearson(lower_count, n, confidence_level)[0]
        upper_probability = clopper_pearson(upper_count, n, confidence_level)[1]
        probability_intervals.append((lower_probability, upper_probability))
    merged_probabilities = _merge_probability_intervals(probability_intervals)
    return ExactCountConfidenceResult(
        confidence_level=float(confidence_level),
        count_ranges=tuple(merged_ranges),
        probability_components=tuple(merged_probabilities),
        variant_count_ranges=by_variant,
        endpoint_certificates=certificates,
        confidence_level_exact=str(confidence_level) if isinstance(confidence_level, Fraction) else None,
    )
