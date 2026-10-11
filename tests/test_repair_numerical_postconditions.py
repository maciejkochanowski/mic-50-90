"""Numerical success must refer to the scientific objective and valid masses."""
import numpy as np
import pytest

from mic_50_90.model import MICPanel, QuantileSummary
from mic_50_90.population import fit_population_mle
from mic_50_90.dro import wasserstein_1d, wasserstein_bounds, project_onto_sharp_set
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.calibration_audit import plan_calibration


def test_mle_does_not_report_success_for_zero_probability_event():
    fit = fit_population_mle(k=2, n=2, quantiles=(QuantileSummary(.5, 2, 0, "1"),),
                             minimum_index=None, maximum_index=1)
    assert not fit.success
    assert fit.log_likelihood == -float("inf")


def test_valid_rare_event_is_not_replaced_by_a_penalty():
    fit = fit_population_mle(k=2, n=100, quantiles=(QuantileSummary(.5, 50, 0, "1"),
                             QuantileSummary(.9, 90, 1, "2")),
                             minimum_index=None, maximum_index=None)
    assert fit.success
    assert np.isfinite(fit.log_likelihood)
    assert -100 < fit.log_likelihood <= 0


@pytest.mark.parametrize("scale", [1., 1e308, 1e-308])
def test_transport_distance_is_invariant_to_finite_common_mass_scale(scale):
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        value = wasserstein_1d(np.array([scale, scale]), np.array([1., 0.]), np.array([0., 1.]))
    assert value == pytest.approx(.5, abs=1e-15)


def test_calibration_planning_does_not_round_fractional_unit_count():
    with pytest.raises(ValueError, match="integer"):
        plan_calibration(calibration_units="20.000000000000001")


def test_transport_bounds_and_projection_accept_large_finite_reference_weights():
    panel = MICPanel.from_twofold_levels([1, 2], left_censored=False, right_censored=False)
    problem = EmpiricalProblem(n=2, panel=panel, quantiles=())
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        bounds = wasserstein_bounds(problem=problem, reference=np.array([1e308, 1e308]),
                                    radius=0., objective=np.array([0., 1.]))
        distance, projected = project_onto_sharp_set(problem=problem, reference=np.array([1e308, 1e308]))
    assert bounds.lower == pytest.approx(.5)
    assert bounds.upper == pytest.approx(.5)
    assert distance == pytest.approx(0.)
    assert projected == pytest.approx([.5, .5])
