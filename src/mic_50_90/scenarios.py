"""Assumption-dependent point scenarios over the empirical feasible polytope."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, minimize
from scipy.special import rel_entr, xlogy

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


def _continuous_constraints(problem: EmpiricalProblem, columns: np.ndarray | None = None) -> list[LinearConstraint]:
    """Linear restrictions on category shares, optionally restricted to the given columns (the others are zero).

    Rows without coefficients carry no restriction for a feasible problem, and repeated or dependent equalities
    make the multipliers of a local method singular; both are removed before optimization.
    """
    matrix, lower, upper = problem.linear_constraints
    lower = lower / problem.n
    upper = upper / problem.n
    if columns is not None:
        matrix = matrix[:, columns]
    informative = np.any(np.abs(matrix) > 0, axis=1)
    matrix, lower, upper = matrix[informative], lower[informative], upper[informative]
    equality = np.isfinite(lower) & np.isfinite(upper) & (np.abs(lower - upper) <= 1e-12)
    constraints: list[LinearConstraint] = []
    if np.any(equality):
        rows = np.flatnonzero(equality)[_independent_rows(matrix[equality])]
        constraints.append(LinearConstraint(matrix[rows], lower[rows], upper[rows]))
    if np.any(~equality):
        constraints.append(LinearConstraint(matrix[~equality], lower[~equality], upper[~equality]))
    return constraints


def _optimality_gap(x: np.ndarray, gradient: np.ndarray, constraints: list[LinearConstraint]) -> float:
    """Upper bound on the distance of a convex objective from its minimum (Frank-Wolfe gap) over the polytope.

    For a convex objective f and a feasible point x, f(x) - min f <= g.x - min over feasible y of g.y with g the gradient
    at x; the minimum is a linear program.
    """
    rows, rhs = [], []
    equal_rows, equal_rhs = [], []
    for c in constraints:
        for a, lb, ub in zip(np.atleast_2d(c.A), np.atleast_1d(c.lb), np.atleast_1d(c.ub)):
            if np.isfinite(lb) and np.isfinite(ub) and abs(lb - ub) <= 1e-12:
                equal_rows.append(a)
                equal_rhs.append(lb)
                continue
            if np.isfinite(ub):
                rows.append(a)
                rhs.append(ub)
            if np.isfinite(lb):
                rows.append(-a)
                rhs.append(-lb)
    lp = linprog(gradient, A_ub=np.asarray(rows) if rows else None, b_ub=np.asarray(rhs) if rhs else None,
                 A_eq=np.asarray(equal_rows) if equal_rows else None, b_eq=np.asarray(equal_rhs) if equal_rhs else None,
                 bounds=[(0.0, 1.0)] * x.size, method="highs")
    if not lp.success:
        return float("inf")
    return float(gradient @ x - lp.fun)


def _extreme_tables(problem: EmpiricalProblem) -> list[np.ndarray]:
    """The tables that make each category as small and as large as possible."""
    tables = []
    for j in range(problem.k):
        unit = np.zeros(problem.k)
        unit[j] = 1.0
        for maximize in (False, True):
            tables.append(np.asarray(problem._solve(unit, maximize=maximize).histogram, dtype=float))
    return tables


def _minimize_over_tables(problem: EmpiricalProblem, objective, gradient, label: str) -> tuple[np.ndarray, float]:
    """Minimize a convex function of the category shares over the continuous relaxation of the compatible tables.

    A single witness table is a vertex of the feasible set, where entropy-type gradients are unbounded and a local
    method can stop. The optimization therefore starts from the average of the tables that make each category as
    small and as large as possible, runs only over the categories that some compatible table occupies, and accepts
    the result only when its Frank-Wolfe optimality gap is negligible; otherwise an interior-point method is used.
    """
    tables = _extreme_tables(problem)
    support = np.max(tables, axis=0) > 0
    columns = np.flatnonzero(support)
    start = (np.mean(tables, axis=0) / problem.n)[support]
    constraints = _continuous_constraints(problem, columns)
    bounds = Bounds(np.zeros(start.size), np.ones(start.size))
    f = lambda x: objective(x, columns)
    g = lambda x: gradient(x, columns)
    result = minimize(f, start, jac=g, method="SLSQP", bounds=bounds, constraints=constraints,
                      options={"maxiter": 3000, "ftol": 1e-12})
    if not result.success or _optimality_gap(result.x, g(result.x), constraints) > 1e-9:
        result = minimize(f, start, jac=g, method="trust-constr", bounds=bounds, constraints=constraints,
                          options={"gtol": 1e-12, "xtol": 1e-14, "maxiter": 5000})
    gap = _optimality_gap(result.x, g(result.x), constraints)
    if gap > 1e-7:
        raise RuntimeError(f"{label} did not reach the optimum (optimality gap {gap:.3g})")
    p = np.zeros(problem.k)
    p[support] = np.maximum(result.x, 0.0)
    return p / p.sum(), float(result.fun)


def maximum_entropy(problem: EmpiricalProblem) -> ScenarioResult:
    """Largest-entropy shares over the continuous relaxation of the compatible tables."""
    p, value = _minimize_over_tables(
        problem,
        lambda x, columns: float(np.sum(xlogy(x, x))),
        lambda x, columns: np.log(np.maximum(x, 1e-12)) + 1.0,
        "Maximum-entropy optimization")
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
    p, value = _minimize_over_tables(
        restricted,
        lambda x, columns: float(np.sum(rel_entr(x, q[columns]))),
        lambda x, columns: np.log(np.maximum(x, 1e-12) / q[columns]) + 1.0,
        "KL projection")
    return ScenarioResult(
        name="forward_KL_projection_D_p_parallel_q",
        probabilities=tuple(float(value) for value in p),
        objective=value,
        success=True,
        message=(
            "Minimized D_KL(p || q) without smoothing structural zeros; this is a sensitivity scenario, not data."
        ),
    )
