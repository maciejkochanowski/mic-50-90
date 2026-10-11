"""Independent contracts and conjugate controls from the September audit."""

import numpy as np
import pytest
from scipy.stats import beta

from mic_50_90.bayes import dirichlet_posterior_tail
from mic_50_90.model import QuantileSummary, parse_spec
from mic_50_90.analysis import analyse_spec


def _spec():
    return {
        "n": 20,
        "panel": {"levels": [1, 2, 4], "left_censored": False, "right_censored": False},
        "summaries": {"quantiles": [{"probability": 0.5, "category": "1"}]},
        "thresholds": [2],
    }


@pytest.mark.parametrize("variant", [
    {"id": "primary", "summaries": {"quantiles": [{"probability": 0.5, "category": "4"}]}},
    {"id": "alternative", "summaries": {"quantiles": [{"probability": 0.5, "category": "missing"}]}},
    {"id": "alternative", "summaries": {"quantiles": [{"probability": 0.5, "category": "4", "convention": "unknown"}]}},
    {"id": "alternative", "summaries": {}},
])
def test_invalid_declared_interpretation_cannot_silently_narrow_union(variant):
    raw = _spec()
    raw["reporting_envelope"] = {"variants": [variant]}
    with pytest.raises(ValueError):
        parse_spec(raw)


def test_valid_alternative_is_retained():
    raw = _spec()
    raw["reporting_envelope"] = {"variants": [
        {"id": "alternative", "summaries": {"quantiles": [
            {"probability": 0.5, "category": "4"}
        ]}}
    ]}
    assert len(parse_spec(raw).all_reporting_variants) == 2


def test_reference_normalization_is_invariant_to_large_finite_scale():
    raw = _spec()
    raw["reference_distribution"] = [1e308, 1e308, 1e308]
    with np.errstate(over="raise", invalid="raise"):
        actual = parse_spec(raw).reference_distribution
    np.testing.assert_allclose(actual, [1/3, 1/3, 1/3])


@pytest.mark.parametrize("kwargs", [
    {"rank": 1.9}, {"rank": float("nan")}, {"rank": True},
    {"category_index": 0.5}, {"category_index": -1},
    {"probability": float("nan")}, {"probability": 1.1},
])
def test_direct_quantile_constructor_preserves_discrete_contract(kwargs):
    values = dict(probability=0.5, rank=1, category_index=1, category_label="2")
    values.update(kwargs)
    with pytest.raises(ValueError):
        QuantileSummary(**values)


def _bayes_options():
    return dict(
        tail=np.array([0., 1.]), n=8,
        quantiles=(QuantileSummary(0.5, 1, 1, "2"),),
        minimum_index=None, maximum_index=None,
        draws=2000, seed=8675309, concentration=2.,
    )


def test_bayesian_mean_mcse_matches_independent_ratio_estimator():
    options = _bayes_options()
    theta = np.random.default_rng(options["seed"]).dirichlet([1., 1.], size=options["draws"])[:, 1]
    # X_(1) in the upper category means all eight observations are upper.
    weights = theta**8
    weights /= weights.sum()
    mean = weights @ theta
    expected_mcse = np.sqrt(np.sum(weights**2 * (theta - mean)**2))
    result = dirichlet_posterior_tail(**options)
    assert result.posterior_mean == pytest.approx(mean, abs=2e-14)
    assert result.posterior_mcse_mean == pytest.approx(expected_mcse, rel=2e-12)
    # Under the uniform prior the exact posterior is Beta(9, 1).
    assert abs(result.posterior_mean - beta.mean(9, 1)) < 5 * expected_mcse


@pytest.mark.parametrize("extra", [
    {"draws": 1000.5}, {"draws": True}, {"seed": 1.5},
    {"concentration": float("nan")}, {"concentration": float("inf")},
    {"reference": np.array([-1., 2.])}, {"reference": np.array([1., 2., 3.])},
    {"confidence_level": 1.1}, {"tail": np.array([0., float("nan")])},
])
def test_bayesian_invalid_input_is_explicitly_rejected(extra):
    options = _bayes_options()
    options.update(extra)
    with pytest.raises(ValueError):
        dirichlet_posterior_tail(**options)


@pytest.mark.parametrize("options,field", [
    ({"bayes_enabled": True, "bayes_draws": 1000, "dirichlet_concentration": None,
      "profile_likelihood_enabled": False}, "bayesian_sensitivity"),
    ({"profile_grid_size": None}, "optional_efficiency_analysis"),
])
def test_missing_optional_fit_setting_preserves_exact_result(options, field):
    raw = _spec()
    raw.update(mode="population", population=options)
    result = analyse_spec(raw)
    threshold = result["threshold_results"][0]
    assert threshold["exact_count_confidence"]["marginal"]
    assert threshold[field]["available"] is False
    assert threshold[field]["reason"]
