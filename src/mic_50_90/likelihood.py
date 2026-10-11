"""Exact event likelihood for reported categorical sample quantiles and range."""

from __future__ import annotations

from itertools import combinations
from math import exp, fsum, isfinite, log, log1p
from typing import Iterable

import numpy as np
from scipy.special import gammaln, logsumexp
from scipy.stats import binom

from .model import QuantileSummary
from .validation import decimal_probability


NEG_INF = float("-inf")


class _LikelihoodPrecisionError(ArithmeticError):
    """The fast expression needs a positive-sum evaluation."""


def _exact_integer(value, name, *, minimum=0):
    try:
        integer = int(value)
        if isinstance(value, (bool, np.bool_)) or integer != value or integer < minimum:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be an exact integer >= {minimum}") from None
    return integer


def _log_binomial_mass(count, n, success, failure):
    """Binomial mass using both supplied sides, without 1-p cancellation."""
    count = np.asarray(count)
    if success == 0:
        return np.where(count == 0, 0.0, NEG_INF)
    if failure == 0:
        return np.where(count == n, 0.0, NEG_INF)
    if success >= failure:
        log_p = -log1p(failure / success)
        log_q = log(failure) - log(success) + log_p
    else:
        log_q = -log1p(success / failure)
        log_p = log(success) - log(failure) + log_q
    return (gammaln(n + 1) - gammaln(count + 1) - gammaln(n - count + 1)
            + count * log_p + (n - count) * log_q)


def _log_binomial_tail(required, n, success, failure):
    """P(Bin(n,p)>=required), reflecting to retain a small complementary mass."""
    if success <= failure:
        return binom.logsf(np.asarray(required) - 1, n, success / (success + failure))
    return binom.logcdf(np.asarray(n) - required, n, failure / (success + failure))


def _log_same_category_event(
    probabilities: np.ndarray,
    n: int,
    *,
    category: int,
    first_rank: int,
    last_rank: int,
) -> float:
    """Probability that one or more order statistics equal one category."""
    p_before = fsum(probabilities[:category])
    p_at = float(probabilities[category])
    p_after = fsum(probabilities[category + 1:])
    if p_at <= 0:
        return NEG_INF
    below_count = np.arange(first_rank, dtype=int)
    log_below = _log_binomial_mass(below_count, n, p_before, fsum((p_at, p_after)))
    required_at = last_rank - below_count
    log_at = _log_binomial_tail(required_at, n - below_count, p_at, p_after)
    terms = np.asarray(log_below + log_at, dtype=float)
    finite = np.isfinite(terms)
    return NEG_INF if not np.any(finite) else float(logsumexp(terms[finite]))


def _logdiffexp_array(log_x: np.ndarray, log_y: np.ndarray) -> np.ndarray:
    """Vectorized stable log(exp(log_x) - exp(log_y))."""
    x = np.asarray(log_x, dtype=float)
    y = np.asarray(log_y, dtype=float)
    result = np.full(np.broadcast_shapes(x.shape, y.shape), NEG_INF, dtype=float)
    x, y = np.broadcast_arrays(x, y)
    only_x = np.isfinite(x) & ~np.isfinite(y)
    result[only_x] = x[only_x]
    valid = np.isfinite(x) & np.isfinite(y) & (y < x)
    delta = y[valid] - x[valid]
    result[valid] = x[valid] + np.log(-np.expm1(delta))
    return result


def _log_two_category_event(
    probabilities: np.ndarray,
    n: int,
    *,
    first_category: int,
    first_rank: int,
    second_category: int,
    second_rank: int,
) -> float:
    """Joint event for two order statistics in distinct categories.

    The calculation is O(n). Conditional on the count at or below the first
    category, the second factor is the difference of two nested binomial tail
    probabilities.
    """
    p_before_first = fsum(probabilities[:first_category])
    p_first = float(probabilities[first_category])
    p_at_or_below_first = fsum((p_before_first, p_first))
    p_middle = fsum(probabilities[first_category + 1 : second_category])
    p_second = float(probabilities[second_category])
    p_above_second = fsum(probabilities[second_category + 1:])
    p_above_first = fsum((p_middle, p_second, p_above_second))
    if p_first <= 0 or p_second <= 0:
        return NEG_INF

    count_through_first = np.arange(first_rank, second_rank, dtype=int)
    log_count = _log_binomial_mass(count_through_first, n, p_at_or_below_first, p_above_first)
    log_first_order = _log_binomial_tail(
        count_through_first - first_rank + 1, count_through_first, p_first, p_before_first
    )
    remaining = n - count_through_first
    needed = second_rank - count_through_first
    log_through_second = _log_binomial_tail(
        needed, remaining, fsum((p_middle, p_second)), p_above_second
    )
    log_middle_only = _log_binomial_tail(needed, remaining, p_middle, fsum((p_second, p_above_second)))
    # The equivalent CDF difference avoids subtracting two survival probabilities
    # close to one. A genuinely tiny category may defeat both orientations.
    log_before_cdf = _log_binomial_tail(remaining - needed + 1, remaining,
                                       fsum((p_second, p_above_second)), p_middle)
    log_through_cdf = _log_binomial_tail(remaining - needed + 1, remaining,
                                        p_above_second, fsum((p_middle, p_second)))
    with np.errstate(invalid="ignore"):
        sf_delta = log_middle_only - log_through_second
        cdf_delta = log_through_cdf - log_before_cdf
    use_sf = np.nan_to_num(sf_delta, nan=0.) <= np.nan_to_num(cdf_delta, nan=0.)
    leading = np.where(use_sf, log_through_second, log_before_cdf)
    trailing = np.where(use_sf, log_middle_only, log_through_cdf)
    log_second_order = _logdiffexp_array(leading, trailing)
    with np.errstate(invalid="ignore"):
        unresolved = ~(trailing - leading < -1e-4)
    # This threshold selects an algorithm; it never turns a positive event into
    # zero. Negligible terms may be omitted only using their positive upper bound.
    good_terms = log_count + log_first_order + np.where(unresolved, NEG_INF, log_second_order)
    good_sum = float(logsumexp(good_terms))
    if np.any(unresolved):
        tail_bound = np.minimum(log_through_second, log_before_cdf)
        tail_bound = np.where(np.isfinite(tail_bound), tail_bound, log(np.finfo(float).tiny))
        upper = float(logsumexp((log_count + log_first_order + tail_bound)[unresolved]))
        if not isfinite(good_sum) or upper - good_sum > log(4*np.finfo(float).eps):
            raise _LikelihoodPrecisionError("Order-event tail subtraction is unresolved")
        log_second_order = np.where(unresolved, NEG_INF, log_second_order)
    terms = np.asarray(log_count + log_first_order + log_second_order, dtype=float)
    finite = np.isfinite(terms)
    return NEG_INF if not np.any(finite) else float(logsumexp(terms[finite]))


def _log_quantile_event_normalized(
    probabilities: np.ndarray,
    n: int,
    quantiles: tuple[QuantileSummary, ...],
) -> float:
    if len(quantiles) == 1:
        summary = quantiles[0]
        return _log_same_category_event(
            probabilities,
            n,
            category=summary.category_index,
            first_rank=summary.rank,
            last_rank=summary.rank,
        )
    if len(quantiles) != 2:
        raise ValueError("Exact population likelihood supports one or two quantiles")
    first, second = quantiles
    if first.category_index == second.category_index:
        return _log_same_category_event(
            probabilities,
            n,
            category=first.category_index,
            first_rank=first.rank,
            last_rank=second.rank,
        )
    return _log_two_category_event(
        probabilities,
        n,
        first_category=first.category_index,
        first_rank=first.rank,
        second_category=second.category_index,
        second_rank=second.rank,
    )


def _log_quantile_event_unnormalized(
    probabilities: np.ndarray,
    n: int,
    quantiles: tuple[QuantileSummary, ...],
) -> float:
    total_mass = fsum(probabilities)
    if total_mass <= 0:
        return NEG_INF
    normalized = probabilities / total_mass
    event = _log_quantile_event_normalized(normalized, n, quantiles)
    if not isfinite(event):
        return NEG_INF
    return n * log(total_mass) + event


def _log_event_positive(log_probabilities, n, summaries, minimum_index, maximum_index):
    """Positive multinomial recurrence for cancellation/underflow cases.

    A coefficient of z**s is the sum of products p_j**h_j / h_j!, retaining
    only cumulative counts consistent with the reported event. Multiplication
    by n! gives its multinomial probability. Every operation is a positive sum
    in log space; required extrema are constraints, not inclusion-exclusion.
    Unconstrained adjacent categories are merged. Worst-case cost is quadratic
    in n per retained category, so ordinary inputs use the O(n) formula above.
    """
    k = len(log_probabilities)
    lower = np.zeros(k + 1, dtype=int)
    upper = np.full(k + 1, n, dtype=int)
    lower[-1], upper[0] = n, 0
    for q in summaries:
        upper[q.category_index] = min(upper[q.category_index], q.rank - 1)
        lower[q.category_index + 1] = max(lower[q.category_index + 1], q.rank)
    if minimum_index is not None:
        upper[minimum_index] = 0
        lower[minimum_index + 1] = max(lower[minimum_index + 1], 1)
    if maximum_index is not None:
        lower[maximum_index + 1] = n
        upper[maximum_index] = min(upper[maximum_index], n - 1)
    boundaries = [0] + [j for j in range(1, k) if lower[j] or upper[j] < n] + [k]
    lower = np.maximum.accumulate(lower)
    upper = np.minimum.accumulate(upper[::-1])[::-1]
    if np.any(lower > upper):
        return NEG_INF
    log_factorials = gammaln(np.arange(n + 1, dtype=float) + 1)
    previous = np.full(n + 1, NEG_INF)
    previous[0] = 0.0
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        log_mass = float(logsumexp(log_probabilities[left:right]))
        current = np.full(n + 1, NEG_INF)
        prior_counts = np.flatnonzero(np.isfinite(previous))
        if not len(prior_counts):
            return NEG_INF
        if not isfinite(log_mass):
            current[lower[right]:upper[right]+1] = previous[lower[right]:upper[right]+1]
        else:
            for total in range(int(lower[right]), int(upper[right]) + 1):
                selected = prior_counts[prior_counts <= total]
                if len(selected):
                    added = total - selected
                    current[total] = logsumexp(previous[selected] + added * log_mass - log_factorials[added])
        previous = current
    value = float(previous[n] + log_factorials[n])
    if np.isnan(value):
        raise ArithmeticError("Order-event log probability exceeds the supported floating-point arithmetic")
    return min(0.0, value)


def log_order_event_probability(
    probabilities: np.ndarray | Iterable[float],
    *,
    n: int,
    quantiles: Iterable[QuantileSummary],
    minimum_index: int | None = None,
    maximum_index: int | None = None,
) -> float:
    """Exact log-probability of the reported order-statistic event.

    Sample extrema require observed draws in the reported endpoint categories;
    they do not assert zero population mass outside the observed range. The
    ordinary O(n) conditional-binomial calculation switches to a positive
    log-domain multinomial recurrence if subtraction or tail underflow becomes
    unresolved. The fallback can cost O(n**2) per constrained category. Results
    use floating-point arithmetic, not certified interval arithmetic. The log
    interface retains events whose ordinary probability underflows to zero.
    """
    p = np.asarray(list(probabilities), dtype=float)
    if p.ndim != 1 or len(p) < 2 or np.any(~np.isfinite(p)) or np.any(p < 0):
        raise ValueError("probabilities must be a finite nonnegative vector")
    scale = float(np.max(p))
    if scale <= 0:
        raise ValueError("probabilities must have positive mass")
    with np.errstate(divide="ignore"):
        log_probabilities = np.log(p)
    log_probabilities -= logsumexp(log_probabilities)
    scaled = p / scale
    normalized = scaled / fsum(scaled)
    lost_mass = np.any((p > 0) & (normalized == 0))
    p = normalized
    n = _exact_integer(n, "n", minimum=1)
    summaries = []
    for q in quantiles:
        if not isinstance(q, QuantileSummary):
            raise ValueError("quantiles must contain QuantileSummary records")
        rank = _exact_integer(q.rank, "quantile rank", minimum=1)
        category = _exact_integer(q.category_index, "quantile category_index")
        probability = decimal_probability(q.as_dict()["probability"])
        if rank > n or category >= len(p):
            raise ValueError("quantile rank or category_index is outside the declared sample/panel")
        summaries.append(QuantileSummary(probability, rank, category, q.category_label, q.convention))
    summaries = tuple(sorted(summaries, key=lambda item: item.rank))
    if not 1 <= len(summaries) <= 2:
        raise ValueError("Exact population likelihood supports one or two quantiles")
    if len(summaries) == 2:
        first, second = summaries
        if (first.rank == second.rank
                or decimal_probability(first.as_dict()["probability"]) >= decimal_probability(second.as_dict()["probability"])
                or first.category_index > second.category_index):
            raise ValueError("quantile ranks/probabilities must increase and categories must be nondecreasing")
    if minimum_index is not None:
        minimum_index = _exact_integer(minimum_index, "minimum_index")
        if minimum_index >= len(p):
            raise ValueError("minimum_index is outside the probability vector")
    if maximum_index is not None:
        maximum_index = _exact_integer(maximum_index, "maximum_index")
        if maximum_index >= len(p):
            raise ValueError("maximum_index is outside the probability vector")
    lower = 0 if minimum_index is None else minimum_index
    upper = len(p) - 1 if maximum_index is None else maximum_index
    if lower > upper:
        return NEG_INF

    if lost_mass:
        return _log_event_positive(log_probabilities, n, summaries, minimum_index, maximum_index)

    allowed = np.zeros(len(p), dtype=bool)
    allowed[lower : upper + 1] = True
    required = sorted(
        set(
            index
            for index in (minimum_index, maximum_index)
            if index is not None
        )
    )
    logs: list[float] = []
    signs: list[float] = []
    try:
        for subset_size in range(len(required) + 1):
            for removed in combinations(required, subset_size):
                restricted = np.where(allowed, p, 0.0)
                if removed:
                    restricted[list(removed)] = 0.0
                logs.append(_log_quantile_event_unnormalized(restricted, n, summaries))
                signs.append(-1.0 if subset_size % 2 else 1.0)
    except _LikelihoodPrecisionError:
        return _log_event_positive(log_probabilities, n, summaries, minimum_index, maximum_index)
    finite = np.isfinite(logs)
    if not np.any(finite):
        return _log_event_positive(log_probabilities, n, summaries, minimum_index, maximum_index)
    value, sign = logsumexp(
        np.asarray(logs)[finite],
        b=np.asarray(signs)[finite],
        return_sign=True,
    )
    if (sign <= 0 or not isfinite(value)
            or value - logsumexp(np.asarray(logs)[finite]) < log(1e-4)
            or value < log(np.finfo(float).tiny) + log(n) + 40):
        return _log_event_positive(log_probabilities, n, summaries, minimum_index, maximum_index)
    return min(0.0, float(value))


def order_event_probability(
    probabilities: np.ndarray | Iterable[float],
    *,
    n: int,
    quantiles: Iterable[QuantileSummary],
    minimum_index: int | None = None,
    maximum_index: int | None = None,
) -> float:
    value = log_order_event_probability(
        probabilities,
        n=n,
        quantiles=quantiles,
        minimum_index=minimum_index,
        maximum_index=maximum_index,
    )
    return 0.0 if not isfinite(value) else float(exp(value))
