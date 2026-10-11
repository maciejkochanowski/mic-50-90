from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mic_50_90.bayes import dirichlet_posterior_tail
from mic_50_90.model import parse_spec
from mic_50_90.population import fit_population_mle, profile_likelihood


def test_population_mle_profile_and_bayes_are_finite():
    raw = json.loads(Path("examples/population.json").read_text())
    raw["n"] = 20
    raw["summaries"]["quantiles"][1]["category"] = "4"
    raw["summaries"].pop("minimum")
    raw["summaries"].pop("maximum")
    spec = parse_spec(raw)
    mle = fit_population_mle(
        k=len(spec.panel.bins),
        n=spec.n,
        quantiles=spec.quantiles,
        minimum_index=None,
        maximum_index=None,
    )
    assert np.isfinite(mle.log_likelihood)
    assert abs(sum(mle.probabilities) - 1) < 1e-10
    tail = spec.panel.panel_tail(2)
    profile = profile_likelihood(
        mle=mle,
        tail=tail,
        n=spec.n,
        quantiles=spec.quantiles,
        minimum_index=None,
        maximum_index=None,
        grid_size=11,
    )
    assert profile.confidence_set_lower is not None
    assert profile.confidence_set_upper is not None
    bayes = dirichlet_posterior_tail(
        tail=tail,
        n=spec.n,
        quantiles=spec.quantiles,
        minimum_index=None,
        maximum_index=None,
        draws=1000,
        seed=3,
        concentration=10,
    )
    assert 0 <= bayes.posterior_mean <= 1
    assert bayes.effective_sample_size > 1

