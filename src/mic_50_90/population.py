"""Population inference from the exact reported-order-statistic likelihood."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, cast

import numpy as np
from scipy.optimize import minimize, minimize_scalar
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


def _closed_simplex_polish(loglike, probabilities, groups, masses, *, pairwise=False):
    """Polish a finite fit on closed simplexes; zero masses are admissible.

    SLSQP supplies an independently constrained fit after the interior fit.
    Pairwise mass transfers sharpen the MLE functional on a flat objective.
    This is a local numerical optimization.
    """
    p = np.asarray(probabilities, dtype=float).copy()
    groups = tuple(np.asarray(group, dtype=int) for group in groups)
    bounds = [(0.0, 0.0)] * len(p)
    constraints = []
    for indices, mass in zip(groups, masses, strict=True):
        if not len(indices):
            continue
        values = np.maximum(p[indices], 0.0)
        p[indices] = mass * (values / values.sum() if values.sum() else np.full(len(indices), 1 / len(indices)))
        for index in indices:
            bounds[index] = (0.0, mass)
        if len(indices) == 1 or mass == 0:
            for index in indices:
                bounds[index] = (float(p[index]), float(p[index]))
        else:
            row = np.zeros(len(p))
            row[indices] = 1.0
            constraints.append({"type": "eq", "fun": lambda x, row=row, mass=mass: float(row @ x) - mass,
                                "jac": lambda x, row=row: row})
    evaluations = 0

    def objective(x):
        nonlocal evaluations
        evaluations += 1
        value = loglike(x)
        return -value if isfinite(value) else 1e100

    if constraints:
        result = minimize(objective, p, method="SLSQP", bounds=bounds,
                          constraints=constraints,
                          options={"maxiter": 1000, "ftol": 1e-14})
        if not result.success:
            # Retry an independent feasible start. If SLSQP still fails on an
            # active face, use feasible pairwise mass transfers below instead
            # of accepting its unsuccessful result or silently dropping a fit.
            uniform = np.zeros(len(p))
            for indices, mass in zip(groups, masses, strict=True):
                if len(indices):
                    uniform[indices] = mass / len(indices)
            result = minimize(objective, uniform, method="SLSQP", bounds=bounds,
                              constraints=constraints,
                              options={"maxiter": 1000, "ftol": 1e-12})
            if not result.success:
                pairwise = True
        if result.success:
            if np.any(~np.isfinite(result.x)):
                raise RuntimeError("Closed-simplex optimizer returned non-finite probabilities")
            candidate = np.asarray(result.x, dtype=float).copy()
            for indices, mass in zip(groups, masses, strict=True):
                if not len(indices):
                    continue
                if (np.any(candidate[indices] < -1e-10)
                        or abs(candidate[indices].sum() - mass) > 1e-8):
                    raise RuntimeError("Closed-simplex optimizer returned an invalid group mass")
                candidate[indices] = np.maximum(candidate[indices], 0.0)
                total = candidate[indices].sum()
                candidate[indices] = candidate[indices] * (mass / total) if total else 0.0
            if objective(candidate) <= objective(p):
                p = candidate
    if pairwise:
        for _ in range(30):
            previous = p.copy()
            for indices in groups:
                for offset, left in enumerate(indices):
                    for right in indices[offset + 1:]:
                        mass = float(p[left] + p[right])
                        if mass == 0:
                            continue

                        def along(value, left=left, right=right, mass=mass):
                            candidate = p.copy()
                            candidate[left], candidate[right] = value, mass - value
                            return objective(candidate)

                        result = minimize_scalar(along, bounds=(0.0, mass), method="bounded",
                                                 options={"xatol": 1e-13, "maxiter": 250})
                        if not result.success:
                            raise RuntimeError("Pairwise simplex polish failed: " + str(result.message))
                        current = objective(p)
                        value, position = min((along(x), x) for x in (0.0, mass, p[left], result.x))
                        # Avoid chasing floating-point noise on nonidentified faces.
                        if value < current - 2e-14:
                            p[left], p[right] = position, mass - position
            if float(np.max(np.abs(p - previous))) <= 5e-8:
                break
        else:
            raise RuntimeError("Pairwise simplex polish did not converge in probability coordinates")
    value = loglike(p)
    if not isfinite(value):
        raise RuntimeError("Closed-simplex optimizer did not produce a finite event likelihood")
    return p, float(value), evaluations


@dataclass(frozen=True)
class PopulationMLE:
    probabilities: tuple[float, ...]
    log_likelihood: float
    success: bool
    message: str
    evaluations: int

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "probabilities": dict(zip(labels, self.probabilities, strict=True)),
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
    success, message = bool(best.success and isfinite(log_likelihood)), str(best.message)
    if isfinite(log_likelihood):
        def loglike(p):
            return log_order_event_probability(p, n=n, quantiles=summaries,
                minimum_index=minimum_index, maximum_index=maximum_index)
        try:
            probabilities, log_likelihood, evaluations = _closed_simplex_polish(
                loglike, probabilities, (np.arange(k),), (1.0,), pairwise=True)
            total_evaluations += evaluations
            success = True
            message = "Closed-simplex SLSQP and pairwise MLE polish converged; local numerical optimization"
        except RuntimeError as exc:
            success, message = False, str(exc)
    return PopulationMLE(
        probabilities=tuple(float(value) for value in probabilities),
        log_likelihood=log_likelihood,
        success=success,
        message=message,
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
            offset += max(0, len(indices) - 1)
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
    confidence_set_components: tuple[tuple[float, float], ...] = ()
    evaluation_status: tuple[str, ...] = ()
    endpoint_diagnostics: tuple[dict[str, object], ...] = ()
    endpoint_method: str = "bisection of the cutoff crossing"
    endpoint_tolerance: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "theta_grid": list(self.theta_grid),
            "profile_log_likelihood": list(self.log_likelihood),
            "likelihood_ratio": list(self.likelihood_ratio),
            "confidence_level": self.confidence_level,
            "chi_square_1_cutoff": self.cutoff,
            "confidence_set": [self.confidence_set_lower, self.confidence_set_upper],
            "confidence_set_is_hull": True,
            "confidence_set_components": [list(c) for c in self.confidence_set_components],
            "evaluation_status": list(self.evaluation_status),
            "endpoint_method": self.endpoint_method,
            "endpoint_tolerance": self.endpoint_tolerance,
            "endpoint_diagnostics": list(self.endpoint_diagnostics),
            "optimization_method": "closed-simplex SLSQP with pairwise mass transfers",
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
            confidence_set_components=((fixed, fixed),),
            evaluation_status=("finite",),
            endpoint_method="fixed functional",
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

    def loglike(p):
        return log_order_event_probability(p, n=n, quantiles=summaries,
            minimum_index=minimum_index, maximum_index=maximum_index)

    def evaluate(theta: float) -> float:
        key = float(theta)
        if key in cache:
            return cache[key]
        uniform = np.zeros(k)
        for indices, mass in ((non_tail_indices, 1.0 - theta), (tail_indices, theta)):
            uniform[indices] = mass / len(indices)
        # Positive weights on every allowed category test support, not convergence.
        # A genuine zero event is distinct from a failed numerical fit.
        support_value = loglike(uniform)
        if support_value == NEG_INF:
            cache[key] = NEG_INF
            return cache[key]
        if not isfinite(support_value):
            raise RuntimeError(f"Profile likelihood returned a non-finite support diagnostic at {theta:g}")

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
            fitted = _group_probabilities(result.x, non_tail_indices=non_tail_indices,
                tail_indices=tail_indices, theta=float(theta), k=k)
            _, value, _ = _closed_simplex_polish(loglike, fitted,
                (non_tail_indices, tail_indices), (1.0 - theta, theta))
        if not isfinite(value) or value <= -1e99:
            raise RuntimeError(f"Profile optimization failed at tail probability {theta:g}")
        if value > mle.log_likelihood + 1e-8:
            raise RuntimeError("Profile likelihood exceeds the supplied MLE; refit the population model before computing a profile")
        cache[key] = value
        return cache[key]

    cutoff = float(chi2.ppf(confidence_level, 1))
    tolerance = 1e-9  # absolute probability units, independent of plotting grid
    endpoints = []

    def statistic(theta):
        value = evaluate(float(theta))
        return float("inf") if not isfinite(value) else max(0.0, 2.0 * (mle.log_likelihood - value))

    def crossing(left, right, left_accepted):
        original = [float(left), float(right)]
        iterations = 0
        # Classification bisection also handles a zero-probability endpoint.
        while right - left > tolerance:
            midpoint = (left + right) / 2.0
            if (statistic(midpoint) <= cutoff) == left_accepted:
                left = midpoint
            else:
                right = midpoint
            iterations += 1
        root = (left + right) / 2.0
        residual = statistic(root) - cutoff
        endpoints.append({"root": root, "initial_bracket": original,
                          "final_bracket": [float(left), float(right)],
                          "bracket_width": float(right - left), "iterations": iterations,
                          "likelihood_ratio_residual": residual if isfinite(residual) else None,
                          "converged": True})
        return root

    accepted = [statistic(float(theta)) <= cutoff for theta in grid]
    components = []
    lower = float(grid[0]) if accepted[0] else None
    for left, right, left_ok, right_ok in zip(grid[:-1], grid[1:], accepted[:-1], accepted[1:], strict=True):
        if left_ok == right_ok:
            continue
        boundary = crossing(float(left), float(right), left_ok)
        if right_ok:
            lower = boundary
        else:
            components.append((float(cast(float, lower)), boundary))
            lower = None
    if accepted[-1]:
        components.append((float(cast(float, lower)), float(grid[-1])))
    grid = np.asarray(sorted(cache), dtype=float)
    profile = [cache[float(theta)] for theta in grid]
    likelihood_ratio = [None if not isfinite(value) else max(0.0, 2.0 * (mle.log_likelihood - value))
                        for value in profile]
    return ProfileLikelihoodResult(
        theta_grid=tuple(float(value) for value in grid),
        log_likelihood=tuple(None if not isfinite(value) else float(value) for value in profile),
        likelihood_ratio=tuple(likelihood_ratio),
        confidence_level=float(confidence_level),
        cutoff=cutoff,
        confidence_set_lower=None if not components else components[0][0],
        confidence_set_upper=None if not components else components[-1][1],
        asymptotic_calibration=(
            "root-refined profile likelihood with a chi-square(1) Wilks cutoff; "
            "boundary and partial-identification settings can be conservative or anti-conservative"
        ),
        adaptive_refinement_rounds=max((row["iterations"] for row in endpoints), default=0),
        optimizer_fallback_count=len(fallback_points),
        boundary_or_weak_identification_warning=bool(
            not components or components[0][0] <= 1e-12
            or components[-1][1] >= 1.0 - 1e-12
            or components[-1][1] - components[0][0] >= 0.8
        ),
        confidence_set_components=tuple(components),
        evaluation_status=tuple("finite" if isfinite(value) else "zero_event_probability" for value in profile),
        endpoint_diagnostics=tuple(endpoints),
        endpoint_method="bisection of the cutoff crossing",
        endpoint_tolerance=tolerance,
    )


NEG_INF = float("-inf")
