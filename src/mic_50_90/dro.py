"""Panel-geometry-aware Wasserstein sensitivity bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.optimize import linprog

from .empirical import EmpiricalProblem
from .validation import normalized_mass


class EmptyWassersteinSet(ValueError):
    """Mathematically infeasible radius, distinct from a numerical solver failure."""


class CriticalRadiusSearchLimit(RuntimeError):
    """The declared search ceiling is too small to obtain a feasible score."""


@dataclass(frozen=True)
class WassersteinBound:
    lower: float
    upper: float
    lower_distribution: tuple[float, ...]
    upper_distribution: tuple[float, ...]
    lower_distance: float
    upper_distance: float
    radius: float
    cost_unit: str

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "radius": self.radius,
            "cost_unit": self.cost_unit,
            "lower_witness": dict(zip(labels, self.lower_distribution)),
            "upper_witness": dict(zip(labels, self.upper_distribution)),
            "lower_witness_distance": self.lower_distance,
            "upper_witness_distance": self.upper_distance,
            "assumption_dependent": True,
        }


def wasserstein_1d(
    probabilities: np.ndarray,
    reference: np.ndarray,
    positions: np.ndarray,
) -> float:
    p = np.asarray(probabilities, dtype=float)
    q = np.asarray(reference, dtype=float)
    x = np.asarray(positions, dtype=float)
    if p.shape != q.shape or p.shape != x.shape:
        raise ValueError("probabilities, reference, and positions must have matching shapes")
    if p.ndim != 1 or len(p) < 2 or any(np.any(~np.isfinite(v)) for v in (p, q, x)):
        raise ValueError("transport inputs must be finite one-dimensional arrays")
    if np.any(np.diff(x) <= 0):
        raise ValueError("positions must be strictly increasing")
    p = normalized_mass(p, "transport probabilities")
    q = normalized_mass(q, "transport reference")
    return float(np.sum(np.abs(np.cumsum(p - q)[:-1]) * np.diff(x)))


def _linprog_constraints(problem: EmpiricalProblem, total_variables: int):
    matrix, lower, upper = problem.linear_constraints
    lower = lower / problem.n
    upper = upper / problem.n
    a_eq: list[np.ndarray] = []
    b_eq: list[float] = []
    a_ub: list[np.ndarray] = []
    b_ub: list[float] = []
    for row, lo, hi in zip(matrix, lower, upper):
        expanded = np.zeros(total_variables)
        expanded[: problem.k] = row
        if np.isfinite(lo) and np.isfinite(hi) and abs(lo - hi) <= 1e-12:
            a_eq.append(expanded)
            b_eq.append(float(lo))
        else:
            if np.isfinite(hi):
                a_ub.append(expanded)
                b_ub.append(float(hi))
            if np.isfinite(lo):
                a_ub.append(-expanded)
                b_ub.append(float(-lo))
    return a_eq, b_eq, a_ub, b_ub


def wasserstein_bounds(
    *,
    problem: EmpiricalProblem,
    reference: np.ndarray,
    radius: float,
    objective: np.ndarray,
    positions: np.ndarray | None = None,
) -> WassersteinBound:
    q = np.asarray(reference, dtype=float)
    if q.shape != (problem.k,) or np.any(~np.isfinite(q)) or np.any(q < 0) or not np.any(q > 0):
        raise ValueError("reference must be nonnegative and match the panel")
    q = normalized_mass(q, "transport reference")
    if not np.isfinite(radius) or radius < 0:
        raise ValueError("Wasserstein radius must be nonnegative")
    if positions is None:
        positions = np.log2(problem.panel.panel_values)
    positions = np.asarray(positions, dtype=float)
    if positions.shape != (problem.k,) or np.any(~np.isfinite(positions)) or np.any(np.diff(positions) <= 0):
        raise ValueError("positions must be strictly increasing and match the panel")
    tail = np.asarray(objective, dtype=float)
    if tail.shape != (problem.k,) or np.any(~np.isfinite(tail)):
        raise ValueError("objective must match the panel")

    k = problem.k
    total_variables = k + k * k
    a_eq, b_eq, a_ub, b_ub = _linprog_constraints(problem, total_variables)

    # gamma[i, j] transports reference mass at i to candidate mass at j.
    for i in range(k):
        row = np.zeros(total_variables)
        row[k + i * k : k + (i + 1) * k] = 1.0
        a_eq.append(row)
        b_eq.append(float(q[i]))
    for j in range(k):
        row = np.zeros(total_variables)
        row[j] = 1.0
        for i in range(k):
            row[k + i * k + j] -= 1.0
        a_eq.append(row)
        b_eq.append(0.0)

    costs = np.abs(positions[:, None] - positions[None, :])
    cost_row = np.zeros(total_variables)
    cost_row[k:] = costs.ravel()
    a_ub.append(cost_row)
    b_ub.append(float(radius))
    variable_bounds = [(0.0, 1.0)] * k + [(0.0, None)] * (k * k)

    def solve(sign: float):
        c = np.zeros(total_variables)
        c[:k] = sign * tail
        result = linprog(
            c,
            A_ub=np.asarray(a_ub),
            b_ub=np.asarray(b_ub),
            A_eq=np.asarray(a_eq),
            b_eq=np.asarray(b_eq),
            bounds=variable_bounds,
            method="highs",
        )
        if not result.success:
            if result.status == 2:
                raise EmptyWassersteinSet("The Wasserstein ambiguity set is empty at this radius: " + str(result.message))
            raise RuntimeError("Wasserstein solver failed: " + str(result.message))
        p = np.maximum(result.x[:k], 0.0)
        p /= p.sum()
        gamma = result.x[k:].reshape(k, k)
        distance = float(np.sum(gamma * costs))
        return float(tail @ p), p, distance

    lower, p_lower, d_lower = solve(+1.0)
    upper, p_upper, d_upper = solve(-1.0)
    return WassersteinBound(
        lower=lower,
        upper=upper,
        lower_distribution=tuple(float(value) for value in p_lower),
        upper_distribution=tuple(float(value) for value in p_upper),
        lower_distance=d_lower,
        upper_distance=d_upper,
        radius=float(radius),
        cost_unit="absolute log2 MIC difference (twofold dilution steps)",
    )


def critical_radius(*, problem, reference: np.ndarray, positions: np.ndarray | None,
                    objectives: Iterable[np.ndarray], truths: Iterable[float],
                    ceiling: float | None = None, tolerance: float = 1e-9,
                    steps: int = 24) -> float:
    """The smallest radius at which the reported interval still covers the truth.

    The guarantee this work states is about the interval it publishes, not about the
    ambiguity set that helps produce it. Those are different events, and the difference is
    not small: the interval is the ambiguity set intersected with the sharp identified set
    of the reported summary, so it can contain the true tail fraction long after the true
    distribution has left the ball. Scoring a calibration cohort by its transport distance
    therefore charges the calibration for failures that never happened, and buys a level
    with a radius far larger than the reported quantity needs.

    Returned is the worst threshold's critical radius, so one accepted radius certifies
    every threshold on the panel at once -- the simultaneity the coverage statement claims.
    ``inf`` means the truth lies outside the sharp identified set. The default search
    ceiling covers the panel diameter, retaining 8 for narrower panels. An explicit
    insufficient ceiling raises CriticalRadiusSearchLimit instead of implying that no
    radius could work.

    Found by bisection on a monotone event: the interval only widens as the radius grows,
    so once it covers it keeps covering.
    """
    objectives, truths = list(objectives), list(truths)
    if not objectives or len(objectives) != len(truths):
        raise ValueError("objectives and truths must have matching nonzero lengths")
    if not np.all(np.isfinite(truths)):
        raise ValueError("truths must be finite")
    coordinates = np.log2(problem.panel.panel_values) if positions is None else np.asarray(positions, dtype=float)
    if coordinates.shape != (problem.k,) or np.any(~np.isfinite(coordinates)) or np.any(np.diff(coordinates) <= 0):
        raise ValueError("positions must be strictly increasing and match the panel")
    diameter = float(coordinates[-1] - coordinates[0])
    ceiling = max(8.0, diameter) if ceiling is None else ceiling
    if (not np.isfinite(ceiling) or ceiling <= 0 or not np.isfinite(tolerance)
            or tolerance < 0 or not isinstance(steps, (int, np.integer)) or steps < 1):
        raise ValueError("invalid critical-radius search controls")
    worst = 0.0
    for objective, truth in zip(objectives, truths):
        try:
            widest = wasserstein_bounds(problem=problem, reference=reference,
                                        radius=ceiling, objective=objective, positions=positions)
            covered = widest.lower - tolerance <= truth <= widest.upper + tolerance
        except EmptyWassersteinSet:
            covered = False
        if not covered:
            complete = wasserstein_bounds(problem=problem, reference=reference,
                                          radius=max(float(ceiling), diameter),
                                          objective=objective, positions=positions)
            if not (complete.lower - tolerance <= truth <= complete.upper + tolerance):
                return float("inf")
            raise CriticalRadiusSearchLimit(
                "critical-radius search ceiling is insufficient; use the default panel-diameter bound")
        low, high = 0.0, float(ceiling)
        for _ in range(steps):
            middle = 0.5 * (low + high)
            try:
                bound = wasserstein_bounds(problem=problem, reference=reference,
                                           radius=middle, objective=objective, positions=positions)
            except EmptyWassersteinSet:
                low = middle
                continue
            if bound.lower - tolerance <= truth <= bound.upper + tolerance:
                high = middle
            else:
                low = middle
        worst = max(worst, high)
    return float(worst)


def project_onto_sharp_set(
    *,
    problem: EmpiricalProblem,
    reference: np.ndarray,
    positions: np.ndarray | None = None,
) -> tuple[float, np.ndarray]:
    """The point of the sharp identified set closest to the reference, and how far it is.

    The reported interval is the sharp identified set of the published summary intersected
    with a Wasserstein ball around a reference pooled from other studies. Nothing forces
    that reference into the sharp set, and usually it is not in it: it is another study's
    histogram, and the target's own reported MIC50 and MIC90 constrain where the target's
    distribution may sit. So the ball is centred outside the set it is intersected with,
    and the intersection stays empty until the radius reaches the distance between them.

    That distance is therefore an additive floor under every calibrated radius, and it is
    paid for nothing. It is not uncertainty about the truth -- for any candidate `P` in the
    sharp set, `W1(P, reference) >= this distance` by definition, so the floor is charged
    to every unit before a single question about the organisms is asked. Measured on the
    training cohorts of the repaired corpus it is a median of 0.049 dilution steps but 0.865
    at the worst unit, against a worst unit score of 1.710 -- half the number that set the
    radius was the cost of centring.

    Re-centring on this projection removes the floor exactly, without touching what the
    ball is asked to cover: the projection is a function of the published summary and the
    training pool, both of which the method already reads, so a score computed from it is
    still a fixed measurable function of the target's observables.

    Returns the transport distance and the projected distribution on the panel.
    """
    q = np.asarray(reference, dtype=float)
    if q.shape != (problem.k,) or np.any(~np.isfinite(q)) or np.any(q < 0) or not np.any(q > 0):
        raise ValueError("reference must be nonnegative and match the panel")
    q = normalized_mass(q, "projection reference")
    if positions is None:
        positions = np.log2(problem.panel.panel_values)
    positions = np.asarray(positions, dtype=float)
    if positions.shape != (problem.k,) or np.any(~np.isfinite(positions)) or np.any(np.diff(positions) <= 0):
        raise ValueError("positions must be strictly increasing and match the panel")

    k = problem.k
    total_variables = k + k * k
    a_eq, b_eq, a_ub, b_ub = _linprog_constraints(problem, total_variables)
    for i in range(k):
        row = np.zeros(total_variables)
        row[k + i * k : k + (i + 1) * k] = 1.0
        a_eq.append(row)
        b_eq.append(float(q[i]))
    for j in range(k):
        row = np.zeros(total_variables)
        row[j] = 1.0
        for i in range(k):
            row[k + i * k + j] -= 1.0
        a_eq.append(row)
        b_eq.append(0.0)

    costs = np.abs(positions[:, None] - positions[None, :])
    objective = np.zeros(total_variables)
    objective[k:] = costs.ravel()
    result = linprog(
        objective,
        A_ub=np.asarray(a_ub) if a_ub else None,
        b_ub=np.asarray(b_ub) if b_ub else None,
        A_eq=np.asarray(a_eq),
        b_eq=np.asarray(b_eq),
        bounds=[(0.0, 1.0)] * k + [(0.0, None)] * (k * k),
        method="highs",
    )
    if not result.success:
        if result.status == 2:
            raise EmptyWassersteinSet("the sharp identified set is empty: " + str(result.message))
        raise RuntimeError("Wasserstein projection solver failed: " + str(result.message))
    projected = np.maximum(result.x[:k], 0.0)
    projected /= projected.sum()
    return float(result.fun), projected
