"""Population inference from the exact reported-order-statistic likelihood."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

import numpy as np
from scipy.optimize import minimize
from scipy.stats import chi2

from .likelihood import log_order_event_probability
from .model import QuantileSummary
from .validation import exact_integer


def _softmax_with_anchor(parameters: np.ndarray) -> np.ndarray:
    logits = np.r_[np.asarray(parameters, dtype=float), 0.0]
    logits -= np.max(logits)
    weights = np.exp(logits)
    return weights / weights.sum()


def _parameters_from_probabilities(probabilities: np.ndarray) -> np.ndarray:
    p = np.maximum(np.asarray(probabilities, dtype=float), 1e-12)
    p = p / p.sum()
    return np.log(p[:-1]) - np.log(p[-1])


@dataclass(frozen=True)
class PopulationMLE:
    probabilities: tuple[float, ...]
    log_likelihood: float
    success: bool
    message: str
    evaluations: int

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "probabilities": dict(zip(labels, self.probabilities)),
            "log_likelihood": self.log_likelihood,
            "success": self.success,
            "message": self.message,
            "evaluations": self.evaluations,
        }


def fit_population_mle(
    *,
    k: int,
    n: int,
    quantiles: Iterable[QuantileSummary],
    minimum_index: int | None,
    maximum_index: int | None,
    reference: np.ndarray | None = None,
) -> PopulationMLE:
    summaries = tuple(quantiles)
    starts: list[np.ndarray] = [np.full(k, 1.0 / k)]
    concentrated = np.full(k, 0.01)
    for summary in summaries:
        concentrated[summary.category_index] += 1.0
    if minimum_index is not None:
        concentrated[minimum_index] += 0.1
    if maximum_index is not None:
        concentrated[maximum_index] += 0.1
    starts.append(concentrated / concentrated.sum())
    if reference is not None:
        starts.append(np.maximum(reference, 1e-8) / np.maximum(reference, 1e-8).sum())

    total_evaluations = 0
    best = None
    for start in starts:
        def objective(parameters: np.ndarray) -> float:
            value = log_order_event_probability(
                _softmax_with_anchor(parameters),
                n=n,
                quantiles=summaries,
                minimum_index=minimum_index,
                maximum_index=maximum_index,
            )
            return 1e100 if not isfinite(value) else -value

        result = minimize(
            objective,
            _parameters_from_probabilities(start),
            method="L-BFGS-B",
            options={"maxiter": 1500, "ftol": 1e-12, "gtol": 1e-8},
        )
        total_evaluations += int(result.nfev)
        if best is None or result.fun < best.fun:
            best = result
    assert best is not None
    probabilities = _softmax_with_anchor(best.x)
    # The optimizer's finite penalty is not the scientific log likelihood.
    log_likelihood = log_order_event_probability(
        probabilities, n=n, quantiles=summaries,
        minimum_index=minimum_index, maximum_index=maximum_index)
    return PopulationMLE(
        probabilities=tuple(float(value) for value in probabilities),
        log_likelihood=log_likelihood,
        success=bool(best.success and isfinite(log_likelihood)),
        message=str(best.message),
        evaluations=total_evaluations,
    )


def _group_probabilities(
    parameters: np.ndarray,
    *,
    non_tail_indices: np.ndarray,
    tail_indices: np.ndarray,
    theta: float,
    k: int,
) -> np.ndarray:
    p = np.zeros(k, dtype=float)
    offset = 0
    for indices, mass in ((non_tail_indices, 1.0 - theta), (tail_indices, theta)):
        if len(indices) == 0:
            if mass > 1e-12:
                raise ValueError("Tail constraint is incompatible with the panel")
            continue
        if mass <= 0:
            continue
        if len(indices) == 1:
            p[indices[0]] = mass
            continue
        count = len(indices) - 1
        proportions = _softmax_with_anchor(parameters[offset : offset + count])
        p[indices] = mass * proportions
        offset += count
    return p


def _group_parameters(probabilities: np.ndarray, indices: np.ndarray) -> np.ndarray:
    if len(indices) <= 1:
        return np.empty(0)
    values = np.maximum(probabilities[indices], 1e-12)
    values = values / values.sum()
    return np.log(values[:-1]) - np.log(values[-1])


@dataclass(frozen=True)
class ProfileLikelihoodResult:
    theta_grid: tuple[float, ...]
    log_likelihood: tuple[float | None, ...]
    likelihood_ratio: tuple[float | None, ...]
    confidence_level: float
    cutoff: float
    confidence_set_lower: float | None
    confidence_set_upper: float | None
    asymptotic_calibration: str
    adaptive_refinement_rounds: int = 0
    boundary_or_weak_identification_warning: bool = False
    optimizer_fallback_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "theta_grid": list(self.theta_grid),
            "profile_log_likelihood": list(self.log_likelihood),
            "likelihood_ratio": list(self.likelihood_ratio),
            "confidence_level": self.confidence_level,
            "chi_square_1_cutoff": self.cutoff,
            "confidence_set": [self.confidence_set_lower, self.confidence_set_upper],
            "calibration": self.asymptotic_calibration,
            "adaptive_refinement_rounds": self.adaptive_refinement_rounds,
            "boundary_or_weak_identification_warning": (
                self.boundary_or_weak_identification_warning
            ),
            "optimizer_fallback_count": self.optimizer_fallback_count,
            "warnings": ([f"Powell fallback was required for {self.optimizer_fallback_count} profile fits after L-BFGS-B failed."]
                         if self.optimizer_fallback_count else []),
        }


def profile_likelihood(
    *,
    mle: PopulationMLE,
    tail: np.ndarray,
    n: int,
    quantiles: Iterable[QuantileSummary],
    minimum_index: int | None,
    maximum_index: int | None,
    grid_size: int = 41,
    confidence_level: float = 0.95,
) -> ProfileLikelihoodResult:
    """Profile a binary categorical probability from a successful fitted model.

    The tail is a finite one-dimensional 0/1 vector matching the MLE panel.
    Grid size is an exact integer; malformed targets are never thresholded or
    reinterpreted as a fixed probability.
    """
    coefficients = np.asarray(tail, dtype=float)
    mle_p = np.asarray(mle.probabilities, dtype=float)
    if (coefficients.ndim != 1 or len(coefficients) < 2
            or not np.all(np.isin(coefficients, (0., 1.)))
            or mle_p.shape != coefficients.shape):
        raise ValueError("profile tail must be a finite binary vector matching the MLE panel")
    if (not mle.success or not isfinite(mle.log_likelihood)
            or np.any(~np.isfinite(mle_p)) or np.any(mle_p < 0)
            or not np.isclose(mle_p.sum(), 1.0, rtol=0, atol=1e-12)):
        raise ValueError("profile likelihood requires a successful finite MLE probability vector")
    n = exact_integer(n, "n", minimum=1)
    grid_size = exact_integer(grid_size, "profile_grid_size", minimum=11)
    tail_mask = coefficients.astype(bool)
    k = len(tail_mask)
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must lie in (0, 1)")
    tail_indices = np.flatnonzero(tail_mask)
    non_tail_indices = np.flatnonzero(~tail_mask)
    if len(tail_indices) == 0 or len(non_tail_indices) == 0:
        fixed = 1.0 if len(non_tail_indices) == 0 else 0.0
        return ProfileLikelihoodResult(
            theta_grid=(fixed,),
            log_likelihood=(mle.log_likelihood,),
            likelihood_ratio=(0.0,),
            confidence_level=confidence_level,
            cutoff=float(chi2.ppf(confidence_level, 1)),
            confidence_set_lower=fixed,
            confidence_set_upper=fixed,
            asymptotic_calibration="fixed functional; no Wilks approximation used",
            adaptive_refinement_rounds=0,
            boundary_or_weak_identification_warning=False,
        )
    summaries = tuple(quantiles)
    base_parameters = np.r_[
        _group_parameters(mle_p, non_tail_indices),
        _group_parameters(mle_p, tail_indices),
    ]
    grid = np.linspace(0.0, 1.0, int(grid_size))
    mle_theta = float(tail_mask @ mle_p)
    grid = np.unique(np.r_[grid, mle_theta])
    cache: dict[float, float] = {}
    fallback_points: set[float] = set()

    def evaluate(theta: float) -> float:
        key = float(theta)
        if key in cache:
            return cache[key]

        def objective(parameters: np.ndarray) -> float:
            p = _group_probabilities(
                parameters,
                non_tail_indices=non_tail_indices,
                tail_indices=tail_indices,
                theta=float(theta),
                k=k,
            )
            value = log_order_event_probability(
                p,
                n=n,
                quantiles=summaries,
                minimum_index=minimum_index,
                maximum_index=maximum_index,
            )
            return 1e100 if not isfinite(value) else -value

        if len(base_parameters) == 0:
            value = -objective(base_parameters)
        else:
            result = minimize(
                objective,
                base_parameters,
                method="L-BFGS-B",
                options={"maxiter": 800, "ftol": 1e-11, "gtol": 1e-7},
            )
            if not result.success:
                first_message = str(result.message)
                result = minimize(
                    objective,
                    result.x if np.all(np.isfinite(result.x)) else base_parameters,
                    method="Powell",
                    options={"maxiter": 800, "ftol": 1e-10, "xtol": 1e-8},
                )
                fallback_points.add(key)
                if not result.success:
                    raise RuntimeError(
                        f"Profile optimization failed at tail probability {theta:g}: "
                        f"L-BFGS-B: {first_message}; Powell: {result.message}"
                    )
            if not isfinite(float(result.fun)):
                raise RuntimeError(
                    f"Profile optimization returned a non-finite objective at tail probability {theta:g}"
                )
            value = -float(result.fun)
        cache[key] = value if isfinite(value) and value > -1e99 else NEG_INF
        return cache[key]

    cutoff = float(chi2.ppf(confidence_level, 1))
    refinement_rounds = 0
    for refinement_rounds in range(4):
        grid = np.asarray(sorted(set(float(value) for value in grid)), dtype=float)
        profile = [evaluate(float(theta)) for theta in grid]
        finite_values = np.asarray([value for value in profile if isfinite(value)])
        peak = max(mle.log_likelihood, float(np.max(finite_values)))
        likelihood_ratio = [
            None if not isfinite(value) else max(0.0, 2.0 * (peak - value))
            for value in profile
        ]
        if refinement_rounds == 3:
            break
        additions: set[float] = set()
        for left, right, left_lr, right_lr in zip(
            grid[:-1], grid[1:], likelihood_ratio[:-1], likelihood_ratio[1:]
        ):
            if left_lr is None or right_lr is None:
                continue
            crosses = (left_lr <= cutoff) != (right_lr <= cutoff)
            near_cutoff = min(abs(left_lr - cutoff), abs(right_lr - cutoff)) <= 0.5
            if crosses or near_cutoff:
                additions.add(float((left + right) / 2.0))
        peak_index = int(np.nanargmin(
            np.asarray([np.inf if value is None else value for value in likelihood_ratio])
        ))
        if peak_index > 0:
            additions.add(float((grid[peak_index - 1] + grid[peak_index]) / 2.0))
        if peak_index < len(grid) - 1:
            additions.add(float((grid[peak_index] + grid[peak_index + 1]) / 2.0))
        additions.difference_update(set(float(value) for value in grid))
        if not additions:
            break
        grid = np.unique(np.r_[grid, list(additions)])

    grid = np.asarray(sorted(cache), dtype=float)
    profile = [cache[float(theta)] for theta in grid]
    finite_values = np.asarray([value for value in profile if isfinite(value)])
    peak = max(mle.log_likelihood, float(np.max(finite_values)))
    likelihood_ratio = [
        None if not isfinite(value) else max(0.0, 2.0 * (peak - value))
        for value in profile
    ]
    accepted = [
        float(theta)
        for theta, statistic in zip(grid, likelihood_ratio)
        if statistic is not None and statistic <= cutoff + 1e-10
    ]
    return ProfileLikelihoodResult(
        theta_grid=tuple(float(value) for value in grid),
        log_likelihood=tuple(None if not isfinite(value) else float(value) for value in profile),
        likelihood_ratio=tuple(likelihood_ratio),
        confidence_level=float(confidence_level),
        cutoff=cutoff,
        confidence_set_lower=None if not accepted else min(accepted),
        confidence_set_upper=None if not accepted else max(accepted),
        asymptotic_calibration=(
            "grid-based profile likelihood with a chi-square(1) Wilks cutoff; "
            "boundary and partial-identification settings can be conservative or anti-conservative"
        ),
        adaptive_refinement_rounds=refinement_rounds,
        optimizer_fallback_count=len(fallback_points),
        boundary_or_weak_identification_warning=bool(
            not accepted
            or min(accepted) <= 1e-12
            or max(accepted) >= 1.0 - 1e-12
            or max(accepted) - min(accepted) >= 0.8
        ),
    )


NEG_INF = float("-inf")
