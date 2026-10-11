"""Validated panel geometry and input models for MIC-50-90."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Iterable, Literal

import numpy as np
from .validation import boolean, ceiling_rank, decimal_probability, exact_integer, identifier, normalized_mass, positive_concentration


def _positive_integer(value: Any, name: str) -> int:
    return exact_integer(value, name, 1)


def _nonnegative_integer(value: Any, name: str) -> int:
    return exact_integer(value, name)


def format_mic(value: float) -> str:
    """Return a compact, deterministic MIC label."""
    return f"{float(value):.12g}"


@dataclass(frozen=True)
class MICBin:
    """One ordered panel category represented as an interval.

    ``None`` denotes an infinite endpoint. Panel values are recorded-category
    representatives used only for the panel-scale estimand; latent threshold
    classification uses the interval endpoints and closure flags.
    """

    label: str
    lower: float | None
    upper: float | None
    lower_closed: bool = False
    upper_closed: bool = True
    panel_value: float | None = None

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("MIC bin labels must be non-empty")
        if self.lower is not None and not isfinite(float(self.lower)):
            raise ValueError("Use null, not an infinite number, for an open endpoint")
        if self.upper is not None and not isfinite(float(self.upper)):
            raise ValueError("Use null, not an infinite number, for an open endpoint")
        if self.lower is not None and self.upper is not None:
            if self.lower > self.upper:
                raise ValueError(f"Invalid interval for {self.label}: lower exceeds upper")
            if self.lower == self.upper and not (self.lower_closed and self.upper_closed):
                raise ValueError(f"Point category {self.label} must be closed at both ends")

    def latent_status(self, threshold: float) -> Literal["below", "above", "ambiguous"]:
        """Classify whether every latent value is above a strict threshold."""
        c = float(threshold)
        if self.upper is not None and self.upper <= c:
            return "below"
        if self.lower is not None:
            if self.lower > c or (self.lower == c and not self.lower_closed):
                return "above"
        return "ambiguous"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "lower_bound": self.lower,
            "upper_bound": self.upper,
            "lower_closed": self.lower_closed,
            "upper_closed": self.upper_closed,
            "panel_value": self.panel_value,
        }


@dataclass(frozen=True)
class MICPanel:
    bins: tuple[MICBin, ...]

    def __post_init__(self) -> None:
        if len(self.bins) < 2:
            raise ValueError("A MIC panel requires at least two ordered categories")
        labels = [item.label for item in self.bins]
        if len(labels) != len(set(labels)):
            raise ValueError("MIC panel labels must be unique")
        for previous, current in zip(self.bins, self.bins[1:]):
            if previous.upper is None:
                raise ValueError("Only the last MIC category may be right-unbounded")
            if current.lower is None:
                raise ValueError("Only the first MIC category may be left-unbounded")
            if current.lower < previous.upper:
                raise ValueError(
                    f"Overlapping MIC bins: {previous.label!r} and {current.label!r}"
                )
            if current.lower == previous.upper and previous.upper_closed and current.lower_closed:
                raise ValueError(
                    f"MIC bins double-include boundary {current.lower:g}: "
                    f"{previous.label!r} and {current.label!r}"
                )
        values = [item.panel_value for item in self.bins]
        if any(value is None or not isfinite(float(value)) for value in values):
            raise ValueError("Every MIC category needs a finite panel_value")
        if np.any(np.diff(np.asarray(values, dtype=float)) <= 0):
            raise ValueError("panel_value must be strictly increasing across MIC categories")

    @classmethod
    def from_twofold_levels(
        cls,
        levels: Iterable[float],
        *,
        left_censored: bool = True,
        right_censored: bool = True,
    ) -> "MICPanel":
        values = np.asarray(list(levels), dtype=float)
        if len(values) < 2 or np.any(~np.isfinite(values)):
            raise ValueError("levels must contain at least two finite values")
        if np.any(values <= 0) or np.any(np.diff(values) <= 0):
            raise ValueError("levels must be strictly increasing and positive")
        bins: list[MICBin] = []
        if left_censored:
            bins.append(
                MICBin(
                    label=f"<={format_mic(values[0])}",
                    lower=None,
                    upper=float(values[0]),
                    lower_closed=False,
                    upper_closed=True,
                    panel_value=float(values[0]),
                )
            )
        else:
            bins.append(
                MICBin(
                    label=format_mic(values[0]),
                    lower=float(values[0]),
                    upper=float(values[0]),
                    lower_closed=True,
                    upper_closed=True,
                    panel_value=float(values[0]),
                )
            )
        for lower, upper in zip(values[:-1], values[1:]):
            bins.append(
                MICBin(
                    label=format_mic(upper),
                    lower=float(lower),
                    upper=float(upper),
                    lower_closed=False,
                    upper_closed=True,
                    panel_value=float(upper),
                )
            )
        if right_censored:
            bins.append(
                MICBin(
                    label=f">{format_mic(values[-1])}",
                    lower=float(values[-1]),
                    upper=None,
                    lower_closed=False,
                    upper_closed=False,
                    panel_value=float(values[-1] * 2.0),
                )
            )
        return cls(tuple(bins))

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MICPanel":
        if "levels" in value:
            return cls.from_twofold_levels(
                value["levels"],
                left_censored=boolean(value.get("left_censored", True), "left_censored"),
                right_censored=boolean(value.get("right_censored", True), "right_censored"),
            )
        categories = value.get("categories")
        if not isinstance(categories, list):
            raise ValueError("panel must define either levels or categories")
        bins: list[MICBin] = []
        for raw in categories:
            lower = raw.get("lower_bound", raw.get("lower"))
            upper = raw.get("upper_bound", raw.get("upper"))
            panel_value = raw.get("panel_value")
            if panel_value is None:
                if upper is not None:
                    panel_value = upper
                elif lower is not None:
                    panel_value = float(lower) * 2.0
            bins.append(
                MICBin(
                    label=str(raw["label"]),
                    lower=None if lower is None else float(lower),
                    upper=None if upper is None else float(upper),
                    lower_closed=boolean(raw.get("lower_closed", False), "lower_closed"),
                    upper_closed=boolean(raw.get("upper_closed", True), "upper_closed"),
                    panel_value=None if panel_value is None else float(panel_value),
                )
            )
        return cls(tuple(bins))

    def index(self, label: str | float | int) -> int:
        text = format_mic(float(label)) if isinstance(label, (float, int)) else str(label).strip()
        labels = [item.label for item in self.bins]
        if text in labels:
            return labels.index(text)
        normalized = text.replace("≤", "<=").replace("≥", ">=")
        if normalized in labels:
            return labels.index(normalized)
        raise ValueError(f"MIC category {label!r} is absent from the panel")

    def panel_tail(self, threshold: float) -> np.ndarray:
        return np.asarray(
            [float(item.panel_value > float(threshold)) for item in self.bins], dtype=float
        )

    def latent_tail(self, threshold: float, *, upper: bool) -> np.ndarray:
        result = []
        for item in self.bins:
            status = item.latent_status(float(threshold))
            result.append(float(status == "above" or (upper and status == "ambiguous")))
        return np.asarray(result, dtype=float)

    @property
    def labels(self) -> list[str]:
        return [item.label for item in self.bins]

    @property
    def panel_values(self) -> np.ndarray:
        return np.asarray([float(item.panel_value) for item in self.bins], dtype=float)

    def as_dict(self) -> dict[str, Any]:
        return {"categories": [item.as_dict() for item in self.bins]}


@dataclass(frozen=True)
class QuantileSummary:
    probability: float
    rank: int
    category_index: int
    category_label: str
    convention: str = "ceiling"
    probability_decimal: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        declared = decimal_probability(self.probability)
        numeric = float(declared)
        object.__setattr__(self, "probability", numeric)
        if decimal_probability(numeric) != declared:
            object.__setattr__(self, "probability_decimal", str(declared))
        object.__setattr__(self, "rank", _positive_integer(self.rank, "quantile rank"))
        object.__setattr__(self, "category_index", _nonnegative_integer(
            self.category_index, "quantile category_index"
        ))

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], *, n: int, panel: MICPanel
    ) -> "QuantileSummary":
        probability = decimal_probability(value["probability"])
        convention = str(value.get("convention", "ceiling"))
        if "rank" in value:
            rank = _positive_integer(value["rank"], "quantile rank")
            convention = "explicit-rank"
        elif convention == "ceiling":
            rank = ceiling_rank(probability, n)
        else:
            raise ValueError(
                "Only convention='ceiling' is automatic; provide an explicit rank "
                "for any other sample-quantile definition"
            )
        if rank < 1 or rank > n:
            raise ValueError(f"quantile rank {rank} is outside 1..n")
        category_index = panel.index(value["category"])
        return cls(
            probability=probability,
            rank=rank,
            category_index=category_index,
            category_label=panel.bins[category_index].label,
            convention=convention,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "probability": self.probability_decimal or self.probability,
            "rank": self.rank,
            "category": self.category_label,
            "convention": self.convention,
        }


@dataclass(frozen=True)
class ReportingVariant:
    """One complete, explicitly declared interpretation of reported summaries."""

    identifier: str
    quantiles: tuple[QuantileSummary, ...]
    minimum_index: int | None
    maximum_index: int | None

    def as_dict(self, panel: MICPanel) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "summaries": {
                "quantiles": [item.as_dict() for item in self.quantiles],
                "minimum": (
                    None
                    if self.minimum_index is None
                    else panel.bins[self.minimum_index].label
                ),
                "maximum": (
                    None
                    if self.maximum_index is None
                    else panel.bins[self.maximum_index].label
                ),
            },
        }


@dataclass(frozen=True)
class ParsedSpec:
    mode: Literal["empirical", "population"]
    n: int
    panel: MICPanel
    quantiles: tuple[QuantileSummary, ...]
    minimum_index: int | None
    maximum_index: int | None
    thresholds: tuple[float, ...]
    reference_distribution: np.ndarray | None = None
    wasserstein_radius: float | None = None
    population_options: dict[str, Any] = field(default_factory=dict)
    question_options: dict[str, Any] = field(default_factory=dict)
    reporting_variants: tuple[ReportingVariant, ...] = field(default_factory=tuple)
    rejected_reporting_variants: tuple[dict[str, str], ...] = field(default_factory=tuple)
    wasserstein_calibration_manifest: dict[str, Any] | None = None
    input_contract_version: str = "4.0"
    calibration_transport_scale: float = 1.0
    representative_variant_id: str = "primary"
    declared_reporting_summaries: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def all_reporting_variants(self) -> tuple[ReportingVariant, ...]:
        primary = ReportingVariant(
            identifier=self.representative_variant_id,
            quantiles=self.quantiles,
            minimum_index=self.minimum_index,
            maximum_index=self.maximum_index,
        )
        return (primary, *self.reporting_variants)


def _legacy_to_v4(spec: dict[str, Any]) -> dict[str, Any]:
    if "panel" in spec:
        return spec
    if "levels" not in spec:
        return spec
    converted = dict(spec)
    converted["panel"] = {
        "levels": spec["levels"],
        "left_censored": str(spec.get("mic_min", "")).startswith(("<=", "≤")),
        "right_censored": str(spec.get("mic_max", "")).startswith(">"),
    }
    quantiles = []
    if "mic50" in spec:
        quantiles.append({"probability": 0.5, "category": spec["mic50"]})
    if "mic90" in spec:
        quantiles.append({"probability": 0.9, "category": spec["mic90"]})
    converted["summaries"] = {
        "quantiles": quantiles,
        "minimum": spec.get("mic_min"),
        "maximum": spec.get("mic_max"),
    }
    converted["thresholds"] = [spec["threshold"]]
    return converted


class _InfeasibleReportingVariant(ValueError):
    """A well-formed interpretation whose summary constraints contradict."""


def _parse_reporting_variant(
    *,
    identifier: str,
    summaries: dict[str, Any],
    n: int,
    panel: MICPanel,
    mode: str,
) -> ReportingVariant:
    if not identifier.strip():
        raise ValueError("reporting variant id must be non-empty")
    if not isinstance(summaries, dict):
        raise ValueError("reporting variant summaries must be an object")
    quantile_raw = summaries.get("quantiles", [])
    if not quantile_raw:
        raise ValueError("at least one reported quantile is required")
    quantiles = tuple(
        sorted(
            (QuantileSummary.from_dict(item, n=n, panel=panel) for item in quantile_raw),
            key=lambda item: item.rank,
        )
    )
    if len(quantiles) > 2 and mode == "population":
        raise ValueError("population exact likelihood currently supports at most two quantiles")
    for left, right in zip(quantiles, quantiles[1:]):
        if left.rank >= right.rank:
            raise ValueError("reported quantile ranks must be strictly increasing")
        if left.category_index > right.category_index:
            raise _InfeasibleReportingVariant("reported quantile categories must be nondecreasing")
    minimum = summaries.get("minimum")
    maximum = summaries.get("maximum")
    minimum_index = None if minimum is None else panel.index(minimum)
    maximum_index = None if maximum is None else panel.index(maximum)
    if minimum_index is not None and maximum_index is not None and minimum_index > maximum_index:
        raise _InfeasibleReportingVariant("minimum category cannot exceed maximum category")
    if minimum_index is not None and any(q.category_index < minimum_index for q in quantiles):
        raise _InfeasibleReportingVariant("a reported quantile cannot be below the reported minimum")
    if maximum_index is not None and any(q.category_index > maximum_index for q in quantiles):
        raise _InfeasibleReportingVariant("a reported quantile cannot exceed the reported maximum")
    return ReportingVariant(
        identifier=identifier,
        quantiles=quantiles,
        minimum_index=minimum_index,
        maximum_index=maximum_index,
    )


def parse_spec(raw_spec: dict[str, Any]) -> ParsedSpec:
    """Parse and validate a MIC-50-90 input mapping."""
    spec = _legacy_to_v4(raw_spec)
    declared_contract = str(spec.get("contract_version", "")).strip()
    if declared_contract and declared_contract not in {"4.0", "1.0"}:
        raise ValueError("contract_version must be '4.0' or '1.0'")
    schema_identifier = str(spec.get("$schema", ""))
    input_contract_version = declared_contract or (
        "1.0" if ":1.0" in schema_identifier else "4.0"
    )
    mode = str(spec.get("mode", "empirical"))
    if mode not in {"empirical", "population"}:
        raise ValueError("mode must be 'empirical' or 'population'")
    n = _positive_integer(spec["n"], "n")
    for section, fields in (("question_utility", ("enabled", "exclude_direct_target_questions")),
                            ("population", ("profile_likelihood_enabled", "bayes_enabled"))):
        options = spec.get(section, {})
        if not isinstance(options, dict):
            raise ValueError(f"{section} must be an object")
        for name in fields:
            if name in options:
                boolean(options[name], f"{section}.{name}")
    panel = MICPanel.from_dict(spec["panel"])
    parsed_variants: list[ReportingVariant] = []
    rejected_variants: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    envelope = spec.get("reporting_envelope")
    if envelope is None:
        envelope = {}
    if not isinstance(envelope, dict) or not isinstance(envelope.get("variants", []), list):
        raise ValueError("reporting_envelope must be an object with a variants list")
    declared = [{"id": "primary", "summaries": spec.get("summaries", {})}, *envelope.get("variants", [])]
    for position, raw_variant in enumerate(declared):
        if not isinstance(raw_variant, dict):
            raise ValueError("each reporting variant must be an object")
        variant_id = identifier(raw_variant.get("id", f"variant_{position}"), "reporting variant id")
        if variant_id in seen_ids:
            raise ValueError(f"reporting variant ids must be unique: {variant_id!r}")
        seen_ids.add(variant_id)
        try:
            parsed_variants.append(
                _parse_reporting_variant(
                    identifier=variant_id,
                    summaries=raw_variant.get("summaries", {}),
                    n=n,
                    panel=panel,
                    mode=mode,
                )
            )
        except _InfeasibleReportingVariant as exc:
            rejected_variants.append({"id": variant_id, "reason": str(exc)})
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid reporting variant {variant_id!r}: {exc}") from exc
    if not parsed_variants:
        raise ValueError("Every reporting variant is incompatible: " +
                         "; ".join(x['id'] + ": " + x['reason'] for x in rejected_variants))
    primary, *reporting_variants = parsed_variants
    quantiles = primary.quantiles
    minimum_index = primary.minimum_index
    maximum_index = primary.maximum_index
    thresholds_raw = spec.get("thresholds")
    if thresholds_raw is None and "threshold" in spec:
        thresholds_raw = [spec["threshold"]]
    if not thresholds_raw:
        raise ValueError("At least one threshold is required")
    thresholds = tuple(positive_concentration(value, "threshold") for value in thresholds_raw)

    reference_raw = spec.get("reference_distribution")
    reference: np.ndarray | None = None
    if reference_raw is not None:
        if isinstance(reference_raw, dict):
            unknown = set(reference_raw) - set(panel.labels)
            if unknown:
                raise ValueError(f"reference_distribution has unknown panel labels: {sorted(map(str, unknown))}")
            reference = np.asarray(
                [float(reference_raw.get(label, 0.0)) for label in panel.labels], dtype=float
            )
        else:
            reference = np.asarray(reference_raw, dtype=float)
        if reference.shape != (len(panel.bins),) or np.any(~np.isfinite(reference)) or np.any(reference < 0) or not np.any(reference > 0):
            raise ValueError("reference_distribution must be nonnegative and match the panel")
        reference = normalized_mass(reference, "reference_distribution")

    radius = spec.get("wasserstein_radius")
    if radius is not None:
        radius = float(radius)
        if radius < 0 or not isfinite(radius):
            raise ValueError("wasserstein_radius must be finite and nonnegative")

    manifest_raw = spec.get("wasserstein_calibration_manifest")
    manifest: dict[str, Any] | None = None
    calibration_scale = 1.0
    if manifest_raw is not None:
        from .conformal import validate_calibration_manifest

        manifest = dict(manifest_raw)
        from .conformal import _MANIFEST_VERSIONS

        if str(manifest.get("manifest_version", "")) not in _MANIFEST_VERSIONS:
            raise ValueError(
                "wasserstein_calibration_manifest.manifest_version must be one of "
                f"{list(_MANIFEST_VERSIONS)}"
            )
        manifest_radius = manifest.get("radius")
        if manifest_radius is None or not isfinite(float(manifest_radius)) or float(manifest_radius) < 0:
            raise ValueError("wasserstein calibration manifest requires a finite nonnegative radius")
        validate_calibration_manifest(manifest)
        if manifest["manifest_version"] not in {"1.2", "1.3"}:
            raise ValueError("legacy calibration manifest requires migration from original scores to version 1.2 before a coverage guarantee")
        if reference is None:
            raise ValueError("calibration requires reference_distribution from the declared training protocol")
        contract = manifest["calibration_contract"]
        context = spec.get("calibration_context", {})
        if not isinstance(context, dict):
            raise ValueError("calibration_context must be an object")
        if context.get("unit") != "mg/L":
            raise ValueError("calibration_context.unit must explicitly be mg/L")
        if context.get("reference_protocol") != contract["reference_protocol"]:
            raise ValueError("calibration_context.reference_protocol does not match the manifest")
        if not manifest["fallback_used"] and context.get("grouping") != manifest["grouping"]:
            raise ValueError("calibration_context.grouping does not match the manifest")
        from .conformal import _calibration_transport_scale
        calibration_scale = _calibration_transport_scale(contract, context, panel)
        effective_radius = float(manifest_radius) * calibration_scale
        if not isfinite(effective_radius) or (float(manifest_radius) > 0 and effective_radius == 0):
            raise ValueError("Physical calibration radius must be finite")
        if radius is not None and abs(radius - effective_radius) > 1e-12:
            raise ValueError("wasserstein_radius conflicts with the physical calibration radius")
        for variant in (primary, *reporting_variants):
            if (variant.minimum_index is not None or variant.maximum_index is not None
                    or len(variant.quantiles) != 2
                    or [decimal_probability(q.as_dict()["probability"]) for q in variant.quantiles]
                       != [decimal_probability("0.5"), decimal_probability("0.9")]
                    or any(q.rank != ceiling_rank(q.as_dict()["probability"], n) for q in variant.quantiles)):
                raise ValueError("summary policy differs from calibration: requires ceiling MIC50/MIC90 without range")
        radius = effective_radius

    return ParsedSpec(
        mode=mode,  # type: ignore[arg-type]
        n=n,
        panel=panel,
        quantiles=quantiles,
        minimum_index=minimum_index,
        maximum_index=maximum_index,
        thresholds=thresholds,
        reference_distribution=reference,
        wasserstein_radius=radius,
        population_options=dict(spec.get("population", {})),
        question_options=dict(spec.get("question_utility", {})),
        reporting_variants=tuple(reporting_variants),
        rejected_reporting_variants=tuple(rejected_variants),
        wasserstein_calibration_manifest=manifest,
        input_contract_version=input_contract_version,
        calibration_transport_scale=calibration_scale,
        representative_variant_id=primary.identifier,
        declared_reporting_summaries=tuple(declared),
    )
