from __future__ import annotations

import pytest
import numpy as np
from fractions import Fraction
from scipy.stats import binom

from mic_50_90.analysis import analyse_spec
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.exact_population import clopper_pearson, exact_count_confidence
from mic_50_90.model import parse_spec


def test_clopper_pearson_keeps_the_upper_tail_near_full_confidence():
    confidence = np.nextafter(1., 0.)
    lower, upper = clopper_pearson(0, 4, confidence)
    expected = 1 - ((1-confidence)/2)**.25
    assert lower == 0
    assert upper == pytest.approx(expected, abs=2e-15)
    assert upper < 1


def test_bonferroni_does_not_round_a_valid_family_to_full_confidence():
    confidence = np.nextafter(1., 0.)
    raw = {'mode':'population', 'n':20,
        'panel':{'levels':[1,2,4], 'left_censored':False, 'right_censored':False},
        'summaries':{'quantiles':[{'probability':.5, 'category':'2'}]},
        'thresholds':[1,2], 'population':{'confidence_level':confidence,
            'profile_likelihood_enabled':False}, 'question_utility':{'enabled':False}}
    result = analyse_spec(raw)
    for row in result['threshold_results']:
        simultaneous = row['exact_count_confidence']['simultaneous_bonferroni']
        exact = Fraction(simultaneous['confidence_level_exact'])
        assert exact == 1-(1-Fraction(float(confidence)))/2
        assert exact < 1


def _variant_problem(category: str, probability: float, n: int = 20):
    raw = {
        "contract_version": "1.0",
        "mode": "population",
        "n": n,
        "panel": {"levels": [1, 2, 4], "left_censored": False, "right_censored": False},
        "summaries": {"quantiles": [{"probability": probability, "category": category}]},
        "thresholds": [2],
    }
    spec = parse_spec(raw)
    return spec, EmpiricalProblem(n=n, panel=spec.panel, quantiles=spec.quantiles)


def test_clopper_pearson_edges_are_exact():
    assert clopper_pearson(0, 10, 0.95)[0] == 0.0
    assert clopper_pearson(10, 10, 0.95)[1] == 1.0
    assert clopper_pearson(0, 10, 0.95)[1] == pytest.approx(0.3084971078)
    assert clopper_pearson(10, 10, 0.95)[0] == pytest.approx(0.6915028922)


@pytest.mark.parametrize("n", range(1, 9))
@pytest.mark.parametrize("probability", [0.01, 0.1, 0.3, 0.5, 0.8, 0.99])
def test_clopper_pearson_exhaustive_small_n_coverage(n, probability):
    coverage = 0.0
    for count in range(n + 1):
        lower, upper = clopper_pearson(count, n, 0.95)
        if lower <= probability <= upper:
            coverage += float(binom.pmf(count, n, probability))
    assert coverage >= 0.95 - 1e-12


def test_disconnected_admissible_count_set_across_reporting_variants():
    low_spec, low = _variant_problem("2", 0.9)
    _, high = _variant_problem("4", 0.5)
    result = exact_count_confidence(
        problems={"q90-low": low, "q50-high": high},
        objective=low_spec.panel.panel_tail(2),
        confidence_level=0.95,
    )
    assert result.count_ranges == ((0, 2), (11, 20))
    assert result.probability_components


def test_population_output_separates_marginal_and_bonferroni_sets():
    raw = {
        "contract_version": "1.0",
        "mode": "population",
        "n": 20,
        "panel": {"levels": [1, 2, 4, 8], "left_censored": False, "right_censored": False},
        "summaries": {"quantiles": [{"probability": 0.5, "category": "2"}]},
        "thresholds": [1, 2],
        "population": {
            "exact_count_confidence": {"confidence_level": 0.95, "multiplicity": "bonferroni"},
            "profile_likelihood_enabled": False
        }
    }
    result = analyse_spec(raw)
    for threshold in result["threshold_results"]:
        exact = threshold["exact_count_confidence"]
        assert exact["marginal"]["guarantee_class"] == "exact_iid_population"
        assert exact["simultaneous_bonferroni"] is not None
        marginal = exact["marginal"]["confidence_set_hull"]
        simultaneous = exact["simultaneous_bonferroni"]["confidence_set_hull"]
        assert simultaneous[0] <= marginal[0]
        assert simultaneous[1] >= marginal[1]


def test_impossible_declared_variant_is_reported_not_guessed():
    raw = {
        "contract_version": "1.0",
        "mode": "empirical",
        "n": 10,
        "panel": {"levels": [1, 2, 4], "left_censored": False, "right_censored": False},
        "summaries": {"quantiles": [{"probability": 0.5, "category": "2"}]},
        "reporting_envelope": {"variants": [{
            "id": "impossible-order",
            "summaries": {"quantiles": [
                {"probability": 0.5, "rank": 3, "category": "4"},
                {"probability": 0.9, "rank": 8, "category": "1"}
            ]}
        }]},
        "thresholds": [2]
    }
    result = analyse_spec(raw)
    rejected = result["reporting_uncertainty_envelope"]["rejected_variants"]
    assert rejected[0]["id"] == "impossible-order"
    assert result["reporting_uncertainty_envelope"]["variant_probabilities_assigned"] is False
