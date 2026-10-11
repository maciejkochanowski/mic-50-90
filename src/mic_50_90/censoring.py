"""Reading a MIC without erasing its censoring operator.

A reported MIC is often not a value but a bound: ``<=0.25`` says the true value lies at or
below 0.25 and nothing more. Coercing that to 0.25 turns a bound into a measurement, which
is the single most common way an external dataset silently acquires precision it never had.
These two functions keep the operator and hand back the latent interval it stands for, so a
caller can decide what to do with it rather than discovering the decision was already made.

They lived in ``scripts/run_external_validation.py`` until 2026-08-22, and the library's own
tests imported them from there. That put a campaign script on the import path of the test
suite, and through it into the source distribution, where most of that script cannot run.
The rule they implement is the library's, so it lives here.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from .model import format_mic

__all__ = ["parse_numeric_mic", "censoring_record"]

_MIC = re.compile(r"(<=|>=|<|>)?\s*([0-9]+(?:\.[0-9]+)?)")


def parse_numeric_mic(
    value: Any, operator: Any | None = None
) -> tuple[float, str | None] | None:
    """Parse a MIC while preserving, rather than erasing, its censoring operator.

    The operator may be embedded in the value (``"<=0.25"``) or supplied separately, as the
    two-column layouts do. Returns ``None`` rather than guessing when the two disagree, when
    the text is not a MIC, or when the value is not a positive finite number.
    """
    text = str(value).strip().replace("≤", "<=").replace("≥", ">=")
    match = re.fullmatch(_MIC, text)
    if match is None:
        return None
    numeric = float(match.group(2))
    if not np.isfinite(numeric) or numeric <= 0:
        return None
    embedded = match.group(1)
    separate = None if operator is None else str(operator).strip().replace("≤", "<=").replace("≥", ">=")
    if separate in {"", "=", "=="}:
        separate = None
    if separate not in {None, "<=", "<", ">", ">="}:
        return None
    if embedded is not None and separate is not None and embedded != separate:
        return None
    return numeric, embedded or separate


def censoring_record(label: str, count: int) -> dict[str, Any]:
    """Return the explicit latent interval represented by one operator label.

    Raises rather than returning a record when the label carries no operator: an uncensored
    value has no latent interval and asking for one is a caller error.
    """
    parsed = parse_numeric_mic(label)
    if parsed is None or parsed[1] is None:
        raise ValueError(f"invalid censored MIC label: {label!r}")
    value, operator = parsed
    return {
        "label": f"{operator}{format_mic(value)}",
        "operator": operator,
        "value": value,
        "lower_bound": value if operator in {">", ">="} else None,
        "upper_bound": value if operator in {"<", "<="} else None,
        "lower_closed": operator == ">=",
        "upper_closed": operator == "<=",
        "count": int(count),
        "analysis_status": "excluded_from_exact_value_analysis",
    }
