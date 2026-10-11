"""Assumption-dependent point scenarios over the empirical feasible polytope."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog

from .empirical import EmpiricalProblem


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    probabilities: tuple[float, ...]
    objective: float
    success: bool
    message: str

    def tail(self, coefficients: np.ndarray) -> float:
        return float(np.asarray(coefficients, dtype=float) @ np.asarray(self.probabilities))

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "name": self.name,
            "probabilities": dict(zip(labels, self.probabilities)),
            "objective": self.objective,
            "success": self.success,
            "message": self.message,
            "assumption_dependent": True,
        }


def _independent_rows(matrix: np.ndarray) -> list[int]:
    """Indices of a linearly independent subset of rows spanning the same row space."""
    keep: list[int] = []
    for i in range(matrix.shape[0]):
        if np.linalg.matrix_rank(matrix[keep + [i]]) > len(keep):
            keep.append(i)
    return keep


def _extreme_tables(problem: EmpiricalProblem) -> list[np.ndarray]:
    """The tables that make each category as small and as large as possible."""
    tables = []
    for j in range(problem.k):
        unit = np.zeros(problem.k)
        unit[j] = 1.0
        for maximize in (False, True):
            tables.append(np.asarray(problem._solve(unit, maximize=maximize).histogram, dtype=float))
    return tables


def _split_constraints(matrix: np.ndarray, lower: np.ndarray, upper: np.ndarray):
    """Equality rows and one-sided inequality rows (a x <= b) of two-sided restrictions."""
    equal = np.isfinite(lower) & np.isfinite(upper) & (np.abs(lower - upper) <= 1e-12)
    rows, rhs = [], []
    for a, lb, ub in zip(matrix[~equal], lower[~equal], upper[~equal]):
        if np.isfinite(ub):
            rows.append(a)
            rhs.append(ub)
        if np.isfinite(lb):
            rows.append(-a)
            rhs.append(-lb)
    size = matrix.shape[1]
    return (matrix[equal], lower[equal], np.asarray(rows, dtype=float).reshape(-1, size),
            np.asarray(rhs, dtype=float))


def _linear_minimum(c: np.ndarray, equal: np.ndarray, equal_rhs: np.ndarray, rows: np.ndarray,
                    rhs: np.ndarray) -> tuple[float, np.ndarray]:
    lp = linprog(c, A_ub=rows if len(rows) else None, b_ub=rhs if len(rows) else None,
                 A_eq=equal if len(equal) else None, b_eq=equal_rhs if len(equal) else None,
                 bounds=[(0.0, 1.0)] * c.size, method="highs")
    if not lp.success:
        raise RuntimeError(f"linear program over the compatible shares failed: {lp.message}")
    return float(lp.fun), np.asarray(lp.x, dtype=float)


def _optimality_gap(x: np.ndarray, gradient: np.ndarray, equal: np.ndarray, equal_rhs: np.ndarray,
                    rows: np.ndarray, rhs: np.ndarray) -> float:
    """Upper bound on the distance of a convex objective from its minimum (Frank-Wolfe gap) over the polytope.

    For a convex objective f and a feasible point x, f(x) - min f <= g.x - min over feasible y of g.y with g the gradient
    at x; the minimum is a linear program.
    """
    return float(gradient @ x - _linear_minimum(gradient, equal, equal_rhs, rows, rhs)[0])


def _minimize_over_tables(problem: EmpiricalProblem, reference: np.ndarray, label: str) -> tuple[np.ndarray, float]:
    """Minimize sum x log(x / r) over the continuous relaxation of the compatible tables (r = 1 gives largest entropy).

    The optimization runs over the categories that some compatible table occupies. Each inequality is classified by two
    linear programs: one whose value cannot vary is an equality, otherwise the two solutions leave slack on its sides.
    The average of these solutions and of the extreme tables is strictly feasible, so a log-barrier Newton method
    started there converges to the minimum, which is positive in every occupied category. The result is accepted only
    with a Frank-Wolfe optimality gap below 1e-9.
    """
    tables = _extreme_tables(problem)
    support = np.max(tables, axis=0) > 0
    columns = np.flatnonzero(support)
    r = np.asarray(reference, dtype=float)[columns]
    matrix, lower, upper = problem.linear_constraints
    matrix, lower, upper = matrix[:, columns], lower / problem.n, upper / problem.n
    informative = np.any(np.abs(matrix) > 0, axis=1)
    equal, equal_rhs, rows, rhs = _split_constraints(matrix[informative], lower[informative], upper[informative])

    points = [table[columns] / problem.n for table in tables]
    fixed, value = np.zeros(len(rows), dtype=bool), np.zeros(len(rows))
    for i, a in enumerate(rows):
        value[i], x_small = _linear_minimum(a, equal, equal_rhs, rows, rhs)
        negated, x_large = _linear_minimum(-a, equal, equal_rhs, rows, rhs)
        fixed[i] = -negated - value[i] <= 1e-12
        points.extend((x_small, x_large))
    inequality, inequality_rhs = rows[~fixed], rhs[~fixed]
    affine, affine_rhs = np.vstack([equal, rows[fixed]]), np.r_[equal_rhs, value[fixed]]
    independent = _independent_rows(affine)
    affine, affine_rhs = affine[independent], affine_rhs[independent]

    x = np.mean(points, axis=0)
    if len(affine):
        x = x - affine.T @ np.linalg.lstsq(affine @ affine.T, affine @ x - affine_rhs, rcond=None)[0]

    def merit(z: np.ndarray, t: float) -> float:
        return float(np.sum(z * np.log(z / r)) - (np.sum(np.log(inequality_rhs - inequality @ z))
                                                  + np.sum(np.log(z))) / t)

    def inside(z: np.ndarray) -> bool:
        return bool(np.all(z > 0) and np.all(inequality_rhs - inequality @ z > 0))

    if not inside(x):
        raise RuntimeError(f"{label} found no strictly feasible starting point")
    # Directions that keep every equality: the null space of the independent equality rows.
    null = np.linalg.svd(affine)[2][len(affine):].T if len(affine) else np.eye(x.size)
    barriers = inequality.shape[0] + x.size
    t = 1.0
    while null.shape[1]:
        for _ in range(200):
            slack = inequality_rhs - inequality @ x
            gradient = np.log(x / r) + 1.0 + (inequality.T @ (1.0 / slack) - 1.0 / x) / t
            hessian = np.diag(1.0 / x + 1.0 / (t * x * x)) + (inequality.T * (1.0 / (t * slack * slack))) @ inequality
            step = null @ np.linalg.solve(null.T @ hessian @ null, -(null.T @ gradient))
            decrement = float(-gradient @ step)
            if t * decrement <= 1e-14:
                break
            if t * decrement <= 0.05 and inside(x + step):
                # Quadratic convergence region of the self-concordant barrier problem: full Newton steps.
                x = x + step
                continue
            length, current = 1.0, merit(x, t)
            while length > 1e-12 and not (inside(x + length * step)
                                          and merit(x + length * step, t) <= current - 0.25 * length * decrement):
                length *= 0.5
            if length <= 1e-12:
                break
            x = x + length * step
        if barriers / t <= 1e-12:
            break
        t *= 10.0

    gap = _optimality_gap(x, np.log(x / r) + 1.0, equal, equal_rhs, rows, rhs)
    if gap > 1e-9:
        raise RuntimeError(f"{label} did not reach the optimum (optimality gap {gap:.3g})")
    p = np.zeros(problem.k)
    p[support] = x
    return p / p.sum(), float(np.sum(x * np.log(x / r)))


def maximum_entropy(problem: EmpiricalProblem) -> ScenarioResult:
    """Largest-entropy shares over the continuous relaxation of the compatible tables."""
    p, value = _minimize_over_tables(problem, np.ones(problem.k), "Maximum-entropy optimization")
    return ScenarioResult(
        name="maximum_entropy_continuous_relaxation",
        probabilities=tuple(float(value) for value in p),
        objective=value,
        success=True,
        message="Entropy maximized over the continuous relaxation of compatible empirical histograms.",
    )


def kl_projection(problem: EmpiricalProblem, reference: np.ndarray) -> ScenarioResult:
    q = np.asarray(reference, dtype=float)
    if q.shape != (problem.k,) or np.any(q < 0) or q.sum() <= 0:
        raise ValueError("reference distribution must be nonnegative and match the panel")
    q = q / q.sum()
    zero_support = q <= 0
    restricted = problem
    if np.any(zero_support):
        feasibility = problem._solve(zero_support.astype(float))
        if feasibility.count > 0:
            raise ValueError(
                "Reference support conflicts with the reported summaries; MIC-50-90 does not silently smooth zero cells."
            )
        restricted = problem.with_count_interval(zero_support.astype(float), 0, 0)
    p, value = _minimize_over_tables(restricted, q, "KL projection")
    return ScenarioResult(
        name="forward_KL_projection_D_p_parallel_q",
        probabilities=tuple(float(value) for value in p),
        objective=value,
        success=True,
        message=(
            "Minimized D_KL(p || q) without smoothing structural zeros; this is a sensitivity scenario, not data."
        ),
    )
