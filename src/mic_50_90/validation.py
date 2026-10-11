"""Shared validation of exact counts, decimal ranks and declared input types."""
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json

import numpy as np

MAX_EXACT_INTEGER = 2**53 - 1
IDENTIFIER_FIELDS = frozenset({"cohort_id", "panel_id", "variant_id", "unit_id"})


def decimal_number(value, name):
    try:
        if isinstance(value, (bool, np.bool_)):
            raise ValueError
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f"{name} must be a finite decimal number") from None
    return result


def exact_integer(value, name, minimum=0):
    try:
        number = decimal_number(value, name)
        if number != number.to_integral_value() or (minimum is not None and number < minimum):
            raise ValueError
    except ValueError:
        requirement = "" if minimum is None else f" >= {minimum}"
        raise ValueError(f"{name} must be an exact integer{requirement}") from None
    if abs(number) > MAX_EXACT_INTEGER:
        raise ValueError(f"{name} exceeds the exact supported integer range (maximum {MAX_EXACT_INTEGER})")
    return int(number)


def positive_concentration(value, name="threshold"):
    """A positive finite concentration, never a JSON or NumPy boolean."""
    number = decimal_number(value, name)
    result = float(number)
    if number <= 0 or not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite, positive and representable")
    return result


def decimal_probability(value):
    result = decimal_number(value, "quantile probability")
    if not 0 < result <= 1 or not 0 < float(result) <= 1:
        raise ValueError("quantile probability must lie in (0, 1] and be representable")
    return result


def ceiling_rank(probability, n):
    fraction = Fraction(decimal_probability(probability))
    size = exact_integer(n, "n", 1)
    return (fraction.numerator * size + fraction.denominator - 1) // fraction.denominator


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean (true or false), not text or a number")
    return value


def identifier(value, name):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty exact identifier without surrounding whitespace")
    return value


def normalized_mass(values, name="probabilities"):
    weights = np.asarray(values, dtype=float)
    if (weights.ndim != 1 or not weights.size or np.any(~np.isfinite(weights))
            or np.any(weights < 0) or not np.any(weights > 0)):
        raise ValueError(f"{name} must be finite nonnegative weights with positive mass")
    scaled = weights / np.max(weights)
    return scaled / scaled.sum()


def load_analysis_json(text):
    """Preserve sample-size and quantile tokens before their exact validation.

    Continuous values and calibration records keep their ordinary JSON numeric
    representation, including existing reference hashes. Exact decimal strings
    in the analysis contract also work for direct Python callers.
    """
    def convert(value, path=()):
        if isinstance(value, dict):
            return {key: convert(item, path + (key,)) for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item, path + (index,)) for index, item in enumerate(value)]
        if isinstance(value, Decimal):
            if path == ("n",) or ("targets" in path and path[-1] == "decision_fraction") or ("additional_counts" in path and path[-1] in {"n", "count", "count_min", "count_max", "percentage", "decimal_places"}) or ("quantiles" in path and path[-1] in {"rank", "probability"}):
                return str(value)
            return float(value)
        return value
    return convert(json.loads(text, parse_float=Decimal))
