"""Positive Decimal oracles for rare order events and direct-input contracts."""
from decimal import Decimal, localcontext
from math import factorial, isfinite

import pytest

from mic_50_90.likelihood import log_order_event_probability, order_event_probability
from mic_50_90.model import QuantileSummary


def _summary(rank, category, probability=.5):
    return QuantileSummary(probability, rank, category, str(category))


def _compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for first in range(n + 1):
            for rest in _compositions(n - first, k - 1):
                yield (first, *rest)


def _decimal_event(weights, n, summaries, minimum=None, maximum=None):
    """Sum positive multinomial masses over explicit sorted samples, independently."""
    with localcontext() as context:
        context.prec = 100
        values = [Decimal.from_float(float(x)) for x in weights]
        total = sum(values)
        probabilities = [x / total for x in values]
        answer = Decimal(0)
        for counts in _compositions(n, len(values)):
            ordered = [j for j, count in enumerate(counts) for _ in range(count)]
            if any(ordered[q.rank - 1] != q.category_index for q in summaries):
                continue
            if minimum is not None and ordered[0] != minimum:
                continue
            if maximum is not None and ordered[-1] != maximum:
                continue
            coefficient = factorial(n)
            for count in counts:
                coefficient //= factorial(count)
            mass = Decimal(coefficient)
            for probability, count in zip(probabilities, counts):
                if count:
                    mass *= probability ** count
            answer += mass
        return +answer, float(answer.ln()) if answer else float("-inf")


@pytest.mark.parametrize("weights,n,summaries,minimum,maximum", [
    ([.25, .5, 1e-14, .24999999999999], 2, (_summary(1, 0), _summary(2, 2, .9)), None, None),
    ([.25, .5, 1e-20, .25], 2, (_summary(1, 0), _summary(2, 2, .9)), None, None),
    ([1., 1e-20], 2, (_summary(1, 0), _summary(2, 1, .9)), None, None),
    ([1e-20, .5, .5], 3, (_summary(2, 1),), 0, 2),
    ([.2, 1e-20, .8], 5, (_summary(2, 1), _summary(3, 1, .9)), None, None),
    ([1., 1e-100], 8, (_summary(1, 1),), None, None),
    ([1e308, 1e308], 2, (_summary(1, 0), _summary(2, 1, .9)), None, None),
    ([1e308, 1e-308], 2, (_summary(1, 1),), None, None),
])
def test_rare_positive_event_retains_its_log_probability(weights, n, summaries, minimum, maximum):
    expected, expected_log = _decimal_event(weights, n, summaries, minimum, maximum)
    assert expected > 0
    actual_log = log_order_event_probability(weights, n=n, quantiles=summaries,
        minimum_index=minimum, maximum_index=maximum)
    assert isfinite(actual_log)
    assert actual_log == pytest.approx(expected_log, rel=0, abs=2e-11)
    actual = order_event_probability(weights, n=n, quantiles=summaries,
        minimum_index=minimum, maximum_index=maximum)
    if float(expected):
        assert actual > 0
        assert actual == pytest.approx(float(expected), rel=2e-11, abs=0)
    else:
        # The ordinary probability can underflow; the public log likelihood cannot.
        assert actual == 0


@pytest.mark.parametrize("n", [2.5, True, 0, -2, float("nan"), float("inf")])
def test_likelihood_rejects_invalid_original_denominator(n):
    with pytest.raises(ValueError, match="n.*integer"):
        log_order_event_probability([.5, .5], n=n, quantiles=(_summary(1, 0),))


@pytest.mark.parametrize("fields", [
    (0, 0), (4, 0), (1.5, 0), (True, 0),
    (1, -1), (1, 2), (1, .5),
    (1, 0, 0), (1, 0, 1.1), (1, 0, float("nan")),
])
def test_likelihood_validates_direct_quantile_records(fields):
    with pytest.raises(ValueError):
        summary = _summary(*fields)
        log_order_event_probability([.5, .5], n=3, quantiles=(summary,))


@pytest.mark.parametrize("summaries", [
    (_summary(1, 0), _summary(1, 1, .9)),
    (_summary(1, 1), _summary(2, 0, .9)),
    (_summary(1, 0, .9), _summary(2, 1, .5)),
])
def test_likelihood_rejects_inconsistent_quantile_order(summaries):
    with pytest.raises(ValueError):
        log_order_event_probability([.5, .5], n=3, quantiles=summaries)


@pytest.mark.parametrize("field,value", [
    ("minimum_index", .5), ("maximum_index", True),
    ("minimum_index", -1), ("maximum_index", 2),
])
def test_likelihood_rejects_noncategory_extrema(field, value):
    with pytest.raises(ValueError):
        log_order_event_probability([.5, .5], n=3, quantiles=(_summary(1, 0),), **{field:value})


@pytest.mark.parametrize("weights", [[.3, .7], [0., .4, .6], [.2, .3, .5], [.1, .2, .3, .4]])
@pytest.mark.parametrize("n", [2, 3, 5, 8])
def test_order_event_matches_positive_decimal_oracle_with_zero_masses_and_extrema(weights, n):
    k = len(weights)
    for first in range(k):
        for last in range(first, k):
            summaries = (_summary(1, first), _summary(n, last, .9))
            for minimum, maximum in ((None, None), (first, None), (None, last), (first, last)):
                expected, expected_log = _decimal_event(weights, n, summaries, minimum, maximum)
                observed = log_order_event_probability(weights, n=n, quantiles=summaries,
                    minimum_index=minimum, maximum_index=maximum)
                if expected:
                    assert observed == pytest.approx(expected_log, rel=0, abs=2e-11)
                else:
                    assert observed == float("-inf")
