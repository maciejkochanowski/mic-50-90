"""Explicitly prior-dependent Bayesian sensitivity analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.special import logsumexp

from .likelihood import log_order_event_probability
from .model import QuantileSummary, _nonnegative_integer, _positive_integer


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, probabilities: np.ndarray) -> np.ndarray:
    order = np.argsort(values)
    sorted_values = values[order]
    sorted_weights = weights[order]
    cumulative = np.cumsum(sorted_weights)
    cumulative /= cumulative[-1]
    return np.interp(probabilities, cumulative, sorted_values)


@dataclass(frozen=True)
class BayesianTailResult:
    prior_alpha: tuple[float, ...]
    draws: int
    effective_sample_size: float
    prior_predictive_log_probability: float
    prior_mean: float
    prior_interval: tuple[float, float]
    posterior_mean: float
    posterior_median: float
    posterior_interval: tuple[float, float]
    posterior_mcse_mean: float
    warnings: tuple[str, ...]

    def as_dict(self, labels: list[str]) -> dict[str, object]:
        return {
            "method": "self-normalized importance sampling from a Dirichlet prior",
            "prior_alpha": dict(zip(labels, self.prior_alpha)),
            "draws": self.draws,
            "effective_sample_size": self.effective_sample_size,
            "prior_predictive_log_probability_of_reported_event": self.prior_predictive_log_probability,
            "prior_tail": {
                "mean": self.prior_mean,
                "equal_tail_interval": list(self.prior_interval),
            },
            "posterior_tail": {
                "mean": self.posterior_mean,
                "median": self.posterior_median,
                "equal_tail_interval": list(self.posterior_interval),
                "mcse_of_mean": self.posterior_mcse_mean,
            },
            "warnings": list(self.warnings),
        }


def dirichlet_posterior_tail(
    *,
    tail: np.ndarray,
    n: int,
    quantiles: Iterable[QuantileSummary],
    minimum_index: int | None,
    maximum_index: int | None,
    draws: int = 10000,
    seed: int = 20260809,
    concentration: float = 10.0,
    reference: np.ndarray | None = None,
    confidence_level: float = 0.95,
) -> BayesianTailResult:
    tail = np.asarray(tail, dtype=float)
    if tail.ndim != 1 or len(tail) < 2 or not np.all(np.isin(tail, [0., 1.])):
        raise ValueError("tail must be a finite binary vector matching the panel")
    k = len(tail)
    draws = _positive_integer(draws, "bayes_draws")
    if draws < 1000:
        raise ValueError("bayes_draws must be at least 1000")
    seed = _nonnegative_integer(seed, "seed")
    if not np.isfinite(concentration) or concentration <= 0:
        raise ValueError("dirichlet_concentration must be finite and positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must lie in (0, 1)")
    if reference is None:
        center = np.full(k, 1.0 / k)
    else:
        center = np.asarray(reference, dtype=float)
        if (center.shape != (k,) or np.any(~np.isfinite(center))
                or np.any(center < 0) or not np.any(center > 0)):
            raise ValueError("reference must be finite, nonnegative and match the panel")
        center = center / np.max(center)
        center = center / center.sum()
        center = np.maximum(center, 1e-8)
        center /= center.sum()
    alpha = np.maximum(concentration * center, 1e-6)
    rng = np.random.default_rng(int(seed))
    samples = rng.dirichlet(alpha, size=int(draws))
    summaries = tuple(quantiles)
    log_likelihood = np.asarray(
        [
            log_order_event_probability(
                sample,
                n=n,
                quantiles=summaries,
                minimum_index=minimum_index,
                maximum_index=maximum_index,
            )
            for sample in samples
        ],
        dtype=float,
    )
    finite = np.isfinite(log_likelihood)
    if not np.any(finite):
        raise RuntimeError("All Bayesian importance weights are zero")
    normalizer = float(logsumexp(log_likelihood[finite]))
    weights = np.zeros(draws, dtype=float)
    weights[finite] = np.exp(log_likelihood[finite] - normalizer)
    weights /= weights.sum()
    ess = float(1.0 / np.sum(weights**2))
    theta = samples @ tail
    alpha_tail = (1.0 - confidence_level) / 2.0
    probabilities = np.asarray([alpha_tail, 0.5, 1.0 - alpha_tail])
    prior_quantiles = np.quantile(theta, probabilities)
    posterior_quantiles = _weighted_quantile(theta, weights, probabilities)
    posterior_mean = float(weights @ theta)
    # Ratio-estimator influence variance for self-normalized importance sampling.
    # Posterior variance / ESS is not the variance of this weighted estimator.
    mean_mcse = float(np.sqrt(np.sum(weights**2 * (theta - posterior_mean)**2)))
    warnings: list[str] = []
    if ess < 200:
        warnings.append(
            "Importance-sampling ESS is below 200; increase draws or use a better-matched prior."
        )
    if ess / draws < 0.01:
        warnings.append(
            "Importance weights are highly concentrated; posterior tail summaries may be unstable."
        )
    return BayesianTailResult(
        prior_alpha=tuple(float(value) for value in alpha),
        draws=int(draws),
        effective_sample_size=ess,
        prior_predictive_log_probability=float(logsumexp(log_likelihood) - np.log(draws)),
        prior_mean=float(np.mean(theta)),
        prior_interval=(float(prior_quantiles[0]), float(prior_quantiles[2])),
        posterior_mean=posterior_mean,
        posterior_median=float(posterior_quantiles[1]),
        posterior_interval=(float(posterior_quantiles[0]), float(posterior_quantiles[2])),
        posterior_mcse_mean=mean_mcse,
        warnings=tuple(warnings),
    )
