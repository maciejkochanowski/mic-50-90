"""Independent public-boundary regressions from the 2026-09-27 audit."""
import numpy as np
import pytest

from mic_50_90 import clopper_pearson, empirical_bounds
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.exact_population import exact_count_confidence
from mic_50_90.model import MICPanel, QuantileSummary


def panel(levels=(1, 2, 4)):
    return MICPanel.from_twofold_levels(levels, left_censored=False, right_censored=False)


@pytest.mark.parametrize("count,n", [(1.9, 10), (-.5, 10), (True, 10),
                                    (np.bool_(False), 10), (1, 10.5), (0, True)])
def test_exact_binomial_inputs_do_not_silently_change_the_observation(count, n):
    with pytest.raises(ValueError, match="integer"):
        clopper_pearson(count, n, .95)


@pytest.mark.parametrize("n", [4.9, True, np.bool_(True)])
def test_empirical_denominator_cannot_be_truncated_or_boolean(n):
    with pytest.raises(ValueError, match="integer"):
        EmpiricalProblem(n=n, panel=panel(), quantiles=[])


@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), -float("inf")])
def test_missing_or_nonfinite_threshold_is_not_converted_to_a_tail(threshold):
    with pytest.raises(ValueError, match="finite"):
        empirical_bounds(n=4, panel=panel(), quantiles=[], threshold=threshold)


def test_count_confidence_refuses_noncanonical_gapped_support():
    # The full integer feasible set is {(0,6,0),(2,3,1),(4,0,2)}.
    # The target count is respectively 6,4,2: endpoints cannot certify 3 or 5.
    problem = EmpiricalProblem(n=6, panel=panel(), quantiles=[],
        equalities=[(np.array([1., 0., -2.]), 0)])
    assert problem.bounds(np.array([0., 1., 1.]))[0].count == 2
    with pytest.raises(ValueError, match="canonical"):
        exact_count_confidence(problems={"custom": problem},
            objective=np.array([0., 1., 1.]), confidence_level=.95)


def test_count_confidence_refuses_non_tail_binary_objective_even_on_tu_problem():
    # Consecutive-ones equalities make a TU problem, but a disconnected
    # objective can still take only 0 or 2 on its integer histograms.
    problem = EmpiricalProblem(n=2, panel=panel((1, 2, 4, 8)), quantiles=[],
        equalities=[(np.array([1., 1., 0., 0.]), 1),
                    (np.array([0., 1., 1., 0.]), 1)])
    assert problem.has_total_unimodular_canonical_matrix
    with pytest.raises(ValueError, match="monotone binary"):
        exact_count_confidence(problems={"custom": problem},
            objective=np.array([1., 0., 1., 0.]), confidence_level=.95)


@pytest.mark.parametrize("objective", [np.array([0., .5, 1.]), np.array([0., np.nan, 1.])])
def test_count_confidence_requires_a_finite_binary_count_objective(objective):
    problem = EmpiricalProblem(n=4, panel=panel(), quantiles=[])
    with pytest.raises(ValueError, match="monotone binary"):
        exact_count_confidence(problems={"primary": problem},
            objective=objective, confidence_level=.95)


def test_count_confidence_requires_one_shared_panel_event():
    left = EmpiricalProblem(n=4, panel=panel(), quantiles=[])
    right = EmpiricalProblem(n=4, panel=panel((2, 4, 8)), quantiles=[])
    with pytest.raises(ValueError, match="panel"):
        exact_count_confidence(problems={"left": left, "right": right},
            objective=np.array([0., 1., 1.]), confidence_level=.95)


def test_valid_integer_equivalents_and_extreme_binomial_counts_are_preserved():
    assert clopper_pearson(np.int64(0), np.int64(10), .95) == clopper_pearson(0., 10., .95)
    assert clopper_pearson(0, 10, .95)[0] == 0
    assert clopper_pearson(10, 10, .95)[1] == 1
    assert clopper_pearson(0, 10, .95)[1] == pytest.approx(1 - .025**.1)


@pytest.mark.parametrize("objective,count", [(np.zeros(3), 0), (np.ones(3), 4)])
def test_fixed_tail_and_equivalent_separate_panels_remain_supported(objective, count):
    problems = {name: EmpiricalProblem(n=4, panel=panel(), quantiles=[])
                for name in ("first", "same-geometry")}
    result = exact_count_confidence(problems=problems, objective=objective, confidence_level=.95)
    assert result.count_ranges == ((count, count),)
    assert result.hull == pytest.approx(clopper_pearson(count, 4, .95))


def test_kl_projection_uses_feasible_support_witness_when_initial_point_has_zero_mass():
    from mic_50_90.scenarios import kl_projection
    problem = EmpiricalProblem(n=20, panel=panel(), quantiles=[])
    reference = np.array([0., .5, .5])
    # The reference is itself feasible: Gibbs' inequality gives minimum KL=0.
    result = kl_projection(problem, reference)
    assert result.probabilities == pytest.approx(reference, abs=1e-6)
    assert result.objective == pytest.approx(0., abs=1e-10)


@pytest.mark.parametrize("summary,message", [
    (QuantileSummary(.5, 5, 1, "2"), "rank"),
    (QuantileSummary(.5, 2, 3, "8"), "category"),
    (QuantileSummary(.5, 2, 1, "4"), "label"),
])
def test_empirical_summary_must_match_its_denominator_and_panel(summary, message):
    with pytest.raises(ValueError, match=message):
        EmpiricalProblem(n=4, panel=panel(), quantiles=[summary])


def test_negative_minimum_index_cannot_silently_mean_the_last_panel_category():
    with pytest.raises(ValueError, match="minimum_index"):
        EmpiricalProblem(n=4, panel=panel(), quantiles=[], minimum_index=-1)
