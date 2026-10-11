"""Sharp finite-sample identification for empirical MIC tail fractions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from .model import MICPanel, QuantileSummary, _positive_integer
from .validation import exact_integer


@dataclass(frozen=True)
class SolverCertificate:
    solver: str
    status: int
    success: bool
    message: str
    primal_objective: float
    dual_objective: float
    duality_gap: float
    max_primal_violation: float
    max_integrality_violation: float
    objective_count: int
    total_unimodular: bool
    integral_rhs: bool
    optimality_verified: bool
    dual_multipliers: dict[str, float]
    fallback_used: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "solver": self.solver,
            "status": self.status,
            "success": self.success,
            "message": self.message,
            "primal_objective": self.primal_objective,
            "dual_objective": self.dual_objective,
            "duality_gap": self.duality_gap,
            "max_primal_violation": self.max_primal_violation,
            "max_integrality_violation": self.max_integrality_violation,
            "objective_count": self.objective_count,
            "total_unimodular": self.total_unimodular,
            "integral_rhs": self.integral_rhs,
            "optimality_verified": self.optimality_verified,
            "dual_multipliers": self.dual_multipliers,
            "fallback_used": self.fallback_used,
        }


@dataclass(frozen=True)
class BoundSolution:
    count: int
    fraction: float
    histogram: tuple[int, ...]
    certificate: SolverCertificate

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "count": self.count,
            "fraction": self.fraction,
            "compatible_histogram": dict(zip(labels, self.histogram)),
            "certificate": self.certificate.as_dict(),
        }


@dataclass(frozen=True)
class EmpiricalIdentification:
    threshold: float
    panel_lower: BoundSolution
    panel_upper: BoundSolution
    latent_lower: BoundSolution
    latent_upper: BoundSolution
    ambiguous_categories: tuple[str, ...]
    closed_form_verified: bool

    @property
    def panel_width(self) -> float:
        return self.panel_upper.fraction - self.panel_lower.fraction

    @property
    def latent_width(self) -> float:
        return self.latent_upper.fraction - self.latent_lower.fraction

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "threshold": self.threshold,
            "panel_recorded_estimand": {
                "definition": "sample fraction of recorded panel MIC categories with panel_value > threshold",
                "lower": self.panel_lower.as_dict(labels),
                "upper": self.panel_upper.as_dict(labels),
                "width": self.panel_width,
                "sharp": True,
            },
            "latent_interval_estimand": {
                "definition": "sample fraction of latent MIC values > threshold under category intervals",
                "lower": self.latent_lower.as_dict(labels),
                "upper": self.latent_upper.as_dict(labels),
                "width": self.latent_width,
                "ambiguous_categories": list(self.ambiguous_categories),
                "sharp": True,
            },
            "closed_form_panel_bound_verified": self.closed_form_verified,
        }


class EmpiricalProblem:
    """Integer feasibility set implied by sample order-statistic summaries."""

    def __init__(
        self,
        *,
        n: int,
        panel: MICPanel,
        quantiles: Iterable[QuantileSummary],
        minimum_index: int | None = None,
        maximum_index: int | None = None,
        equalities: Iterable[tuple[np.ndarray, int]] | None = None,
        count_intervals: Iterable[tuple[np.ndarray, int, int]] | None = None,
    ) -> None:
        self.n = _positive_integer(n, "n")
        self.panel = panel
        self.quantiles = tuple(quantiles)
        self.minimum_index = minimum_index
        self.maximum_index = maximum_index
        self.k = len(panel.bins)
        for summary in self.quantiles:
            if summary.rank > self.n:
                raise ValueError("quantile rank must lie in 1..n")
            if summary.category_index >= self.k:
                raise ValueError("quantile category index is outside the panel")
            if summary.category_label != panel.bins[summary.category_index].label:
                raise ValueError("quantile category label does not match its panel index")
        for name, index in (("minimum_index", minimum_index), ("maximum_index", maximum_index)):
            if index is not None and (isinstance(index, (bool, np.bool_))
                    or not isinstance(index, (int, np.integer)) or not 0 <= index < self.k):
                raise ValueError(f"{name} must be an integer category index inside the panel")
        self.equalities = tuple(equalities or ())
        self.count_intervals = tuple(count_intervals or ())
        self._matrix, self._lower, self._upper = self._build_constraints()
        self._canonical_tu = self._has_interval_rows(self._matrix)
        self._integral_rhs = self._has_integral_rhs(self._lower, self._upper)
        self._assert_feasible()

    @staticmethod
    def _has_interval_rows(matrix: np.ndarray) -> bool:
        """Check the row consecutive-ones condition used by the TU theorem.

        Every non-zero canonical row is the indicator of a contiguous interval.
        Hence the transpose has the consecutive-ones property for columns and is
        totally unimodular; total unimodularity is invariant under transpose and
        row sign changes.
        """
        for row in np.asarray(matrix, dtype=float):
            if not np.all(np.isin(row, (0.0, 1.0))):
                return False
            support = np.flatnonzero(row)
            if len(support) and support[-1] - support[0] + 1 != len(support):
                return False
        return True

    @staticmethod
    def _has_integral_rhs(lower: np.ndarray, upper: np.ndarray) -> bool:
        finite = np.r_[lower[np.isfinite(lower)], upper[np.isfinite(upper)]]
        return bool(np.all(np.abs(finite - np.rint(finite)) <= 1e-12))

    def _build_constraints(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        rows: list[np.ndarray] = []
        lower: list[float] = []
        upper: list[float] = []

        rows.append(np.ones(self.k))
        lower.append(float(self.n))
        upper.append(float(self.n))

        for summary in self.quantiles:
            before = np.zeros(self.k)
            before[: summary.category_index] = 1.0
            rows.append(before)
            lower.append(-np.inf)
            upper.append(float(summary.rank - 1))

            through = np.zeros(self.k)
            through[: summary.category_index + 1] = 1.0
            rows.append(through)
            lower.append(float(summary.rank))
            upper.append(np.inf)

        if self.minimum_index is not None:
            if self.minimum_index > 0:
                below = np.zeros(self.k)
                below[: self.minimum_index] = 1.0
                rows.append(below)
                lower.append(0.0)
                upper.append(0.0)
            present = np.zeros(self.k)
            present[self.minimum_index] = 1.0
            rows.append(present)
            lower.append(1.0)
            upper.append(np.inf)

        if self.maximum_index is not None:
            if self.maximum_index < self.k - 1:
                above = np.zeros(self.k)
                above[self.maximum_index + 1 :] = 1.0
                rows.append(above)
                lower.append(0.0)
                upper.append(0.0)
            present = np.zeros(self.k)
            present[self.maximum_index] = 1.0
            rows.append(present)
            lower.append(1.0)
            upper.append(np.inf)

        for coefficients, value in self.equalities:
            coefficients = np.asarray(coefficients, dtype=float)
            if coefficients.shape != (self.k,) or not np.all(np.isfinite(coefficients)):
                raise ValueError("Additional equality coefficients must be finite and match the panel")
            value = exact_integer(value, "Additional equality value", minimum=None)
            rows.append(coefficients)
            lower.append(float(value))
            upper.append(float(value))

        for coefficients, lo, hi in self.count_intervals:
            coefficients = np.asarray(coefficients, dtype=float)
            if coefficients.shape != (self.k,) or not np.all(np.isin(coefficients, (0, 1))):
                raise ValueError("Count interval coefficients must select panel categories")
            lo = exact_integer(lo, "count_min", minimum=0)
            hi = exact_integer(hi, "count_max", minimum=0)
            if not lo <= hi <= self.n:
                raise ValueError("Count interval must satisfy 0 <= count_min <= count_max <= n")
            rows.append(coefficients)
            lower.append(float(lo))
            upper.append(float(hi))

        return np.vstack(rows), np.asarray(lower), np.asarray(upper)

    def _linprog_form(
        self,
    ) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, np.ndarray | None, list[str], list[str]]:
        a_eq: list[np.ndarray] = []
        b_eq: list[float] = []
        a_ub: list[np.ndarray] = []
        b_ub: list[float] = []
        eq_labels: list[str] = []
        ub_labels: list[str] = []
        for index, (row, lower, upper) in enumerate(
            zip(self._matrix, self._lower, self._upper)
        ):
            if np.isfinite(lower) and np.isfinite(upper) and abs(lower - upper) <= 1e-12:
                a_eq.append(row)
                b_eq.append(float(lower))
                eq_labels.append(f"row_{index}:equality")
            else:
                if np.isfinite(upper):
                    a_ub.append(row)
                    b_ub.append(float(upper))
                    ub_labels.append(f"row_{index}:upper")
                if np.isfinite(lower):
                    a_ub.append(-row)
                    b_ub.append(float(-lower))
                    ub_labels.append(f"row_{index}:lower_as_negative")
        return (
            None if not a_eq else np.asarray(a_eq, dtype=float),
            None if not b_eq else np.asarray(b_eq, dtype=float),
            None if not a_ub else np.asarray(a_ub, dtype=float),
            None if not b_ub else np.asarray(b_ub, dtype=float),
            eq_labels,
            ub_labels,
        )

    def _violations(self, histogram: np.ndarray) -> tuple[float, float]:
        values = self._matrix @ histogram
        lower_violation = np.where(
            np.isfinite(self._lower), np.maximum(self._lower - values, 0), 0
        )
        upper_violation = np.where(
            np.isfinite(self._upper), np.maximum(values - self._upper, 0), 0
        )
        primal = float(max(np.max(lower_violation), np.max(upper_violation)))
        integrality = float(np.max(np.abs(histogram - np.rint(histogram))))
        return primal, integrality

    def _solve_milp_oracle(
        self, objective: np.ndarray, *, maximize: bool = False, fallback_used: bool = False
    ) -> BoundSolution:
        """Independent integer oracle and fallback for non-interval constraints."""
        coefficients = self._count_objective(objective)
        sign = -1.0 if maximize else 1.0
        result = milp(
            c=sign * coefficients,
            integrality=np.ones(self.k, dtype=int),
            bounds=Bounds(np.zeros(self.k), np.full(self.k, float(self.n))),
            constraints=LinearConstraint(self._matrix, self._lower, self._upper),
            options={"mip_rel_gap": 0.0, "presolve": True},
        )
        if not result.success or result.x is None:
            if result.status == 2:
                raise ValueError(f"Incompatible MIC summaries: {result.message}")
            raise RuntimeError(f"MIC solver failed (status {result.status}): {result.message}")
        histogram = np.rint(result.x).astype(int)
        violation, integrality = self._violations(histogram)
        count = int(round(float(coefficients @ histogram)))
        primal = float(coefficients @ histogram)
        certificate = SolverCertificate(
            solver="scipy.optimize.milp/HiGHS",
            status=int(result.status),
            success=bool(result.success and violation <= 1e-7),
            message=str(result.message),
            primal_objective=primal,
            dual_objective=primal,
            duality_gap=float(getattr(result, "mip_gap", 0.0) or 0.0),
            max_primal_violation=violation,
            max_integrality_violation=integrality,
            objective_count=count,
            total_unimodular=self._canonical_tu,
            integral_rhs=self._integral_rhs,
            optimality_verified=bool(
                result.success
                and violation <= 1e-7
                and float(getattr(result, "mip_gap", 0.0) or 0.0) <= 1e-9
            ),
            dual_multipliers={},
            fallback_used=fallback_used,
        )
        if not certificate.success:
            raise RuntimeError("MILP returned a numerically invalid histogram witness")
        return BoundSolution(
            count=count,
            fraction=count / self.n,
            histogram=tuple(int(value) for value in histogram),
            certificate=certificate,
        )

    def _solve(self, objective: np.ndarray, *, maximize: bool = False) -> BoundSolution:
        """Solve the canonical integer problem as an LP and certify the result.

        Canonical MIC-50-90 constraints have interval rows and integral right-hand
        sides. Total unimodularity therefore guarantees an integral optimal
        basic feasible solution. Future non-interval equalities are routed to
        the MILP fallback rather than being covered by that theorem.
        """
        coefficients = self._count_objective(objective)
        if not (self._canonical_tu and self._integral_rhs):
            return self._solve_milp_oracle(
                coefficients, maximize=maximize, fallback_used=True
            )
        sign = -1.0 if maximize else 1.0
        a_eq, b_eq, a_ub, b_ub, eq_labels, ub_labels = self._linprog_form()
        result = linprog(
            sign * coefficients,
            A_ub=a_ub,
            b_ub=b_ub,
            A_eq=a_eq,
            b_eq=b_eq,
            bounds=[(0.0, float(self.n))] * self.k,
            method="highs-ds",
            options={"presolve": True},
        )
        if not result.success or result.x is None:
            if result.status == 2:
                raise ValueError(f"Incompatible MIC summaries: {result.message}")
            raise RuntimeError(f"MIC solver failed (status {result.status}): {result.message}")

        raw = np.asarray(result.x, dtype=float)
        rounded = np.rint(raw)
        raw_primal_violation, raw_integrality = self._violations(raw)
        rounded_violation, _ = self._violations(rounded)
        if raw_integrality > 1e-6 or rounded_violation > 1e-7:
            return self._solve_milp_oracle(
                coefficients, maximize=maximize, fallback_used=True
            )
        histogram = rounded.astype(int)
        primal = float(coefficients @ histogram)

        eq_marginals = (
            np.empty(0)
            if a_eq is None
            else np.asarray(result.eqlin.marginals, dtype=float)
        )
        ub_marginals = (
            np.empty(0)
            if a_ub is None
            else np.asarray(result.ineqlin.marginals, dtype=float)
        )
        lower_marginals = np.asarray(result.lower.marginals, dtype=float)
        upper_marginals = np.asarray(result.upper.marginals, dtype=float)
        dual_solver = 0.0
        if b_eq is not None:
            dual_solver += float(np.asarray(b_eq) @ eq_marginals)
        if b_ub is not None:
            dual_solver += float(np.asarray(b_ub) @ ub_marginals)
        dual_solver += float(self.n * np.sum(upper_marginals))
        dual = dual_solver / sign
        gap = abs(primal - dual)
        duals = {
            **{label: float(value) for label, value in zip(eq_labels, eq_marginals)},
            **{label: float(value) for label, value in zip(ub_labels, ub_marginals)},
            **{
                f"variable_{index}:lower": float(value)
                for index, value in enumerate(lower_marginals)
                if abs(value) > 1e-14
            },
            **{
                f"variable_{index}:upper": float(value)
                for index, value in enumerate(upper_marginals)
                if abs(value) > 1e-14
            },
        }
        optimal = bool(
            result.success
            and raw_primal_violation <= 1e-7
            and raw_integrality <= 1e-6
            and rounded_violation <= 1e-7
            and gap <= 1e-7
        )
        certificate = SolverCertificate(
            solver="scipy.optimize.linprog/HiGHS dual simplex",
            status=int(result.status),
            success=optimal,
            message=str(result.message),
            primal_objective=primal,
            dual_objective=dual,
            duality_gap=gap,
            max_primal_violation=max(raw_primal_violation, rounded_violation),
            max_integrality_violation=raw_integrality,
            objective_count=int(round(primal)),
            total_unimodular=True,
            integral_rhs=True,
            optimality_verified=optimal,
            dual_multipliers=duals,
        )
        if not optimal:
            return self._solve_milp_oracle(
                coefficients, maximize=maximize, fallback_used=True
            )
        return BoundSolution(
            count=int(round(primal)),
            fraction=int(round(primal)) / self.n,
            histogram=tuple(int(value) for value in histogram),
            certificate=certificate,
        )

    def _assert_feasible(self) -> None:
        self._solve(np.zeros(self.k))

    def _count_objective(self, objective: np.ndarray) -> np.ndarray:
        """Validate the integer-valued objective stored in BoundSolution.count."""
        coefficients = np.asarray(objective, dtype=float)
        if (coefficients.shape != (self.k,) or not np.all(np.isfinite(coefficients))
                or np.any(coefficients != np.rint(coefficients))):
            raise ValueError("Count objective coefficients must be finite integers matching the MIC panel")
        return coefficients

    def bounds(self, objective: np.ndarray) -> tuple[BoundSolution, BoundSolution]:
        """Sharp bounds for a finite integral linear count objective.

        Ordinary category/tail objectives are binary. Integral weighted counts
        are also supported; fractional weights are refused because the result
        stores an integer count. Transport bounds accept real objectives through
        their separate API.
        """
        return self._solve(objective), self._solve(objective, maximize=True)

    def with_equality(self, coefficients: np.ndarray, value: int) -> "EmpiricalProblem":
        """Add an equality with an exact integer right-hand side, without coercion."""
        return EmpiricalProblem(
            n=self.n,
            panel=self.panel,
            quantiles=self.quantiles,
            minimum_index=self.minimum_index,
            maximum_index=self.maximum_index,
            equalities=(*self.equalities, (np.asarray(coefficients, dtype=float), value)),
            count_intervals=self.count_intervals,
        )

    def with_count_interval(self, coefficients: np.ndarray, lower: int, upper: int) -> "EmpiricalProblem":
        """Intersect with an inclusive integer count range; retain earlier answers."""
        return EmpiricalProblem(n=self.n, panel=self.panel, quantiles=self.quantiles,
            minimum_index=self.minimum_index, maximum_index=self.maximum_index,
            equalities=self.equalities,
            count_intervals=(*self.count_intervals, (np.asarray(coefficients, dtype=float), lower, upper)))

    @property
    def linear_constraints(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return self._matrix.copy(), self._lower.copy(), self._upper.copy()

    @property
    def has_total_unimodular_canonical_matrix(self) -> bool:
        return self._canonical_tu


def closed_form_tail_counts(
    *,
    n: int,
    tail: np.ndarray,
    quantiles: Iterable[QuantileSummary],
    minimum_index: int | None,
    maximum_index: int | None,
) -> tuple[int, int]:
    """Closed-form sharp count bounds for a monotone binary panel tail."""
    n = _positive_integer(n, "n")
    tail = np.asarray(tail, dtype=float)
    if (tail.ndim != 1 or len(tail) < 2 or not np.all(np.isin(tail, (0., 1.)))
            or np.any(np.diff(tail) < 0)):
        raise ValueError("closed_form_tail_counts requires a monotone binary tail")
    tail = tail.astype(int)
    if np.all(tail == 0):
        return 0, 0
    if np.all(tail == 1):
        return int(n), int(n)
    lower, upper = 0, int(n)
    for summary in quantiles:
        if tail[summary.category_index]:
            lower = max(lower, n - summary.rank + 1)
        else:
            upper = min(upper, n - summary.rank)
    if minimum_index is not None:
        if tail[minimum_index]:
            lower = upper = n
        else:
            upper = min(upper, n - 1)
    if maximum_index is not None:
        if tail[maximum_index]:
            lower = max(lower, 1)
        else:
            lower = upper = 0
    if lower > upper:
        raise ValueError("MIC summaries imply an empty identification set")
    return int(lower), int(upper)


def empirical_bounds(
    *,
    n: int,
    panel: MICPanel,
    quantiles: Iterable[QuantileSummary],
    threshold: float,
    minimum_index: int | None = None,
    maximum_index: int | None = None,
) -> EmpiricalIdentification:
    threshold = float(threshold)
    if not np.isfinite(threshold):
        raise ValueError("threshold must be finite")
    quantiles = tuple(quantiles)
    problem = EmpiricalProblem(
        n=n,
        panel=panel,
        quantiles=quantiles,
        minimum_index=minimum_index,
        maximum_index=maximum_index,
    )
    panel_tail = panel.panel_tail(threshold)
    panel_lower, panel_upper = problem.bounds(panel_tail)
    latent_definite = panel.latent_tail(threshold, upper=False)
    latent_possible = panel.latent_tail(threshold, upper=True)
    latent_lower = problem._solve(latent_definite)
    latent_upper = problem._solve(latent_possible, maximize=True)
    closed_lower, closed_upper = closed_form_tail_counts(
        n=n,
        tail=panel_tail,
        quantiles=quantiles,
        minimum_index=minimum_index,
        maximum_index=maximum_index,
    )
    ambiguous = tuple(
        item.label for item in panel.bins if item.latent_status(float(threshold)) == "ambiguous"
    )
    return EmpiricalIdentification(
        threshold=float(threshold),
        panel_lower=panel_lower,
        panel_upper=panel_upper,
        latent_lower=latent_lower,
        latent_upper=latent_upper,
        ambiguous_categories=ambiguous,
        closed_form_verified=(
            panel_lower.count == closed_lower and panel_upper.count == closed_upper
        ),
    )
