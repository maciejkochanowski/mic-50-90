"""Integer count objectives cannot lose information before certification."""
from decimal import Decimal
from fractions import Fraction
from itertools import product

import numpy as np
import pytest

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel


def fixed_first_category(n=3):
    panel = MICPanel.from_twofold_levels(
        [1, 2], left_censored=False, right_censored=False
    )
    return EmpiricalProblem(
        n=n, panel=panel, quantiles=[], minimum_index=0, maximum_index=0
    )


@pytest.mark.parametrize("method", ["_solve", "_solve_milp_oracle"])
@pytest.mark.parametrize("maximize", [False, True])
@pytest.mark.parametrize("sign", [1, -1])
def test_unrepresentable_weighted_count_is_refused_not_falsely_certified(method, maximize, sign):
    # The only histogram is (3, 0). Its objective magnitude is
    # 13510798882111485, which float64 rounds to 13510798882111484.
    problem = fixed_first_category()
    with pytest.raises(ValueError, match="supported integer range"):
        getattr(problem, method)([sign * (2**52 - 1), 0], maximize=maximize)


@pytest.mark.parametrize("method", ["_solve", "_solve_milp_oracle"])
@pytest.mark.parametrize("weight", [
    Decimal("1.0000000000000000001"),
    Fraction(2**60 + 1, 2**60),
    "1.0000000000000000001",
])
def test_fractional_weight_cannot_be_rounded_to_an_integer_before_validation(method, weight):
    with pytest.raises(ValueError, match="finite integers"):
        getattr(fixed_first_category(), method)([weight, 0])


@pytest.mark.parametrize("method", ["_solve", "_solve_milp_oracle"])
def test_complex_array_cannot_silently_drop_imaginary_coefficients(method):
    with pytest.raises(ValueError, match="finite integers"):
        getattr(fixed_first_category(), method)(np.array([2 + 1j, 0j]))


@pytest.mark.parametrize("weight", [2**53, 2**53 + 1, -(2**53 + 1), 10**400])
def test_oversized_python_integer_is_rejected_without_float_overflow(weight):
    with pytest.raises(ValueError, match="supported integer range"):
        fixed_first_category(n=1).bounds([weight, 0])


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("method", ["_solve", "_solve_milp_oracle"])
def test_product_domain_boundary_has_the_exact_integer_objective(method, sign):
    problem = fixed_first_category()
    weight = sign * 3002399751580330
    expected = sign * 9007199254740990
    for maximize in (False, True):
        solution = getattr(problem, method)([weight, 0], maximize=maximize)
        assert solution.histogram == (3, 0)
        assert solution.count == expected
        assert solution.certificate.objective_count == expected
        assert solution.certificate.primal_objective == expected
        assert solution.certificate.optimality_verified
    with pytest.raises(ValueError, match="supported integer range"):
        getattr(problem, method)([sign * 3002399751580331, 0])


@pytest.mark.parametrize("objective", [
    [Decimal("2.0"), Decimal("-3")],
    [Fraction(2, 1), Fraction(-3, 1)],
    ["2e0", "-3.0"],
    np.array([2, -3], dtype=np.int64),
    np.array([2.0, -3.0]),
])
def test_exact_integral_input_representations_remain_equivalent(objective):
    lo, hi = fixed_first_category().bounds(objective)
    assert lo.count == hi.count == 6
    assert lo.certificate.objective_count == hi.certificate.objective_count == 6


def test_binary_boolean_masks_remain_category_count_objectives():
    lo, hi = fixed_first_category().bounds(np.array([True, False]))
    assert lo.count == hi.count == 3


@pytest.mark.parametrize("method", ["_solve", "_solve_milp_oracle"])
@pytest.mark.parametrize("n", [2**31 + 1, 2**53 - 1])
def test_binary_counts_keep_the_full_supported_sample_size_domain(method, n):
    # Both witness conversions must preserve counts exceeding int32. This also
    # exercises NumPy 1.x/Windows, whose platform-default integer is int32.
    problem = fixed_first_category(n=n)
    for maximize in (False, True):
        solution = getattr(problem, method)([1, 0], maximize=maximize)
        assert solution.histogram == (n, 0)
        assert solution.count == n
        assert solution.certificate.objective_count == n
        assert solution.certificate.optimality_verified
        assert solution.fraction == 1.0


@pytest.mark.parametrize("coupled", [False, True])
@pytest.mark.parametrize("weights", [
    (-2, 0, 3), (3, -2, 0), (0, 0, 0), (1, 0, 1), (2, 2, 2), (-1, -1, -1),
])
def test_signed_weighted_extrema_match_independent_integer_enumeration(coupled, weights):
    panel = MICPanel.from_twofold_levels(
        [1, 2, 4], left_censored=False, right_censored=False
    )
    problem = EmpiricalProblem(
        n=4, panel=panel, quantiles=[],
        equalities=[(np.array([1, 0, 1]), 2)] if coupled else [],
    )
    # Direct reference, with no program matrix or solver used to select tables.
    tables = [h for h in product(range(5), repeat=3)
              if sum(h) == 4 and (not coupled or h[0] + h[2] == 2)]
    values = [sum(w * c for w, c in zip(weights, h, strict=True)) for h in tables]
    lo, hi = problem.bounds(weights)
    assert (lo.count, hi.count) == (min(values), max(values))
    for solution in (lo, hi):
        assert solution.histogram in tables
        assert solution.count == sum(w * c for w, c in zip(weights, solution.histogram, strict=True))
        assert solution.certificate.objective_count == solution.count
        assert solution.certificate.optimality_verified
        assert solution.certificate.fallback_used == coupled
