from __future__ import annotations

from itertools import combinations

import numpy as np
from hypothesis import given, settings, strategies as st

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel, QuantileSummary


def _compositions(n: int, k: int):
    for cuts in combinations(range(n + k - 1), k - 1):
        points = (-1, *cuts, n + k - 1)
        yield np.asarray(
            [points[index + 1] - points[index] - 1 for index in range(k)],
            dtype=int,
        )


@st.composite
def compatible_problem(draw):
    n = draw(st.integers(min_value=3, max_value=9))
    k = draw(st.integers(min_value=2, max_value=5))
    observations = sorted(
        draw(st.lists(st.integers(0, k - 1), min_size=n, max_size=n))
    )
    r1 = draw(st.integers(min_value=1, max_value=n - 1))
    r2 = draw(st.integers(min_value=r1 + 1, max_value=n))
    panel = MICPanel.from_twofold_levels(
        [float(2**index) for index in range(k)],
        left_censored=False,
        right_censored=False,
    )
    quantiles = (
        QuantileSummary(
            probability=r1 / n,
            rank=r1,
            category_index=observations[r1 - 1],
            category_label=panel.labels[observations[r1 - 1]],
            convention="explicit-rank",
        ),
        QuantileSummary(
            probability=r2 / n,
            rank=r2,
            category_index=observations[r2 - 1],
            category_label=panel.labels[observations[r2 - 1]],
            convention="explicit-rank",
        ),
    )
    return n, panel, quantiles


@given(compatible_problem(), st.integers(min_value=0, max_value=4))
@settings(max_examples=60, deadline=None)
def test_lp_is_integral_and_matches_bruteforce_and_milp(payload, raw_cut):
    n, panel, quantiles = payload
    cut = min(raw_cut, len(panel.bins) - 1)
    problem = EmpiricalProblem(n=n, panel=panel, quantiles=quantiles)
    objective = np.zeros(len(panel.bins))
    objective[cut + 1 :] = 1.0
    lower, upper = problem.bounds(objective)
    milp_lower = problem._solve_milp_oracle(objective)
    milp_upper = problem._solve_milp_oracle(objective, maximize=True)

    matrix, bounds_lower, bounds_upper = problem.linear_constraints
    brute = []
    for histogram in _compositions(n, len(panel.bins)):
        values = matrix @ histogram
        if np.all(values >= bounds_lower - 1e-12) and np.all(values <= bounds_upper + 1e-12):
            brute.append(int(objective @ histogram))
    assert brute
    assert (lower.count, upper.count) == (min(brute), max(brute))
    assert (lower.count, upper.count) == (milp_lower.count, milp_upper.count)
    for solution in (lower, upper):
        certificate = solution.certificate
        assert certificate.total_unimodular
        assert certificate.integral_rhs
        assert certificate.optimality_verified
        assert certificate.duality_gap <= 1e-7
        assert certificate.max_integrality_violation <= 1e-6
        assert sum(solution.histogram) == n


def test_noninterval_future_constraint_uses_milp_fallback():
    panel = MICPanel.from_twofold_levels(
        [1, 2, 4], left_censored=False, right_censored=False
    )
    quantile = QuantileSummary(0.5, 2, 1, "2", "explicit-rank")
    problem = EmpiricalProblem(
        n=4,
        panel=panel,
        quantiles=(quantile,),
        equalities=((np.asarray([1.0, 0.0, 1.0]), 2),),
    )
    solution = problem._solve(np.asarray([0.0, 0.0, 1.0]), maximize=True)
    assert not problem.has_total_unimodular_canonical_matrix
    assert solution.certificate.fallback_used
    assert "milp" in solution.certificate.solver
