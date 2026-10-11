"""Split-conformal calibration of Wasserstein ambiguity-set radii."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import ceil, ulp
import re
from typing import Iterable

import numpy as np


_MANIFEST_KEYS = frozenset({
    "manifest_version", "guarantee_class", "confidence_level", "alpha",
    "rank", "calibration_size", "minimum_group_calibration_size", "radius",
    "grouping", "source", "data_hashes", "guarantee_scope",
    "fallback_used", "calibration_scores_sha256", "coverage_statement",
})

# Optional because manifests written before the exchangeable-unit accounting do not
# carry them. Present or absent, never partly present: the validator checks that.
_MANIFEST_UNIT_KEYS = frozenset({
    "exchangeable_units", "exchangeable_unit_definition", "exchangeable_unit_labels",
    "unit_score_aggregation", "maximum_supported_level", "attained_level",
    "conformal_rank_counts",
})

#: Diagnostic, not accounting. `unit_scores` lets a reader see how far the radius sits
#: from the next unit, which is the difference between "one more study would raise the
#: level" and "reaching it would mean admitting the mismatched reference". It is allowed
#: but never required, so a manifest written before it existed stays valid.
_MANIFEST_DIAGNOSTIC_KEYS = frozenset({
    "unit_scores", "unit_scores_median",
    "attained_level_all_cohorts", "attained_level_median_cohort",
})

#: Written from manifest version 1.1 onward. In 1.0 `confidence_level` carried the level
#: the caller asked for, so a manifest could declare 0.95 while its units certified 0.667
#: and nothing in the artefact contradicted it. From 1.1 `confidence_level` carries what
#: the exchangeable units certify, which means the requested level has to be recorded
#: separately or it would be lost. `requested_level_supported` answers the only question
#: a reader of the artefact needs answered: did the declared level meet the request.
_MANIFEST_LEVEL_KEYS = frozenset({"requested_level", "requested_level_supported"})

_MANIFEST_VERSIONS = ("1.0", "1.1", "1.2", "1.3")
_MANIFEST_CONTRACT_KEYS = frozenset({"calibration_contract"})


def split_unit(source: str, study: str) -> str:
    """The raw study label of one cohort, as the source records it.

    This is a label, not the exchangeable unit. The `study` field is a semicolon-joined
    list whenever a cohort cites more than one publication, so two cohorts that share a
    publication can carry different labels; hashing the label as if it were atomic sent
    the same study into two partitions. Use :func:`canonical_split_units` to obtain the
    unit an assignment may safely be made on.
    """
    return f"{source}|{study}"


#: What counts as naming a study: a publication accession, which is all digits, or a
#: BioProject accession. The Stage 0 preregistration of 2026-08-23 puts the two on equal
#: footing, and admitting only the first left every isolate deposited without a paper --
#: thirty percent of the eligible cohorts -- with no identifiable study at all.
_STUDY_ACCESSION = re.compile(r"^(?:[0-9]+|PRJ[A-Z]{2}[0-9]+)$")


def atomic_studies(study: str) -> tuple[str, ...]:
    """The study accessions inside one cohort's study field, if it has any.

    The field is a semicolon-joined list: publication accessions and BioProject accessions
    where the record has them, otherwise the name of the repository the record came from,
    otherwise `unknown`. Only an accession identifies a study. A repository name does not:
    two cohorts deposited in PATRIC are not one study, and treating the name as an
    identifier merges them; but they are not demonstrably two studies either, so a cohort
    with no accession has no exchangeable unit and :func:`canonical_split_units` returns
    none for it.

    A cohort repaired from its BioProject carries both the project accession and whatever
    publications NCBI records for that project, so a study that reached the corpus twice --
    once with its paper and once only as a deposit -- is merged by the closure below
    instead of being counted as two independent units.

    Returns an empty tuple when the field carries no accession.
    """
    parts = {part.strip() for part in study.split(";")}
    return tuple(sorted(part for part in parts if _STUDY_ACCESSION.match(part)))


def canonical_split_units(labels: Iterable[str]) -> dict[str, str | None]:
    """Map every raw `source|study` label to the exchangeable unit it belongs to.

    Two labels belong to one unit when they cite a publication in common, directly or
    through a chain of other labels: study A published with B, and B published with C,
    makes one unit of all three, because a partition boundary anywhere inside that chain
    puts dependent cohorts on both sides of it. This transitive closure is what the earlier
    label hash skipped: a cohort citing "A;B" and a cohort citing "B" hashed to two
    different strings and could land in two different partitions.

    A label with no publication accession maps to ``None``: it has no identifiable study,
    so it cannot carry a unit, and a design that rests on exchangeability between studies
    must not draw a calibration or test cohort from it.

    The unit label is the sorted list of accessions it contains, so it is stable under
    input order and readable in a manifest.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    label_studies: dict[str, tuple[str, ...]] = {}
    for label in labels:
        _, _, study = label.partition("|")
        studies = atomic_studies(study)
        label_studies[label] = studies
        for other in studies[1:]:
            union(studies[0], other)

    members: dict[str, set[str]] = {}
    for studies in label_studies.values():
        if studies:
            members.setdefault(find(studies[0]), set()).update(studies)
    names = {root: ";".join(sorted(group)) for root, group in members.items()}
    return {label: (names[find(studies[0])] if studies else None)
            for label, studies in label_studies.items()}


def balanced_partition(unit_sizes: dict[str, int],
                       targets: dict[str, float]) -> dict[str, str]:
    """Assign whole units to partitions, hitting the target cohort shares as closely as possible.

    Hashing each unit into a partition is deterministic and, with units this unequal, unusable:
    the twenty-four units here range from one cohort to one hundred and eighty-five, so a
    hash that is fair in units is arbitrary in cohorts. The measured consequence was a
    training side holding fifty-four cohorts, too few groups with a reference pool, and a
    calibration set below the minimum size at which any conformal statement exists.

    Largest unit first, each to whichever partition is furthest below its quota; ties broken
    by name. Deterministic, order-independent, and blind to every outcome -- it reads unit
    sizes and nothing else, so it cannot be tuned toward an answer.
    """
    total = sum(unit_sizes.values())
    filled = {key: 0 for key in targets}
    assignment: dict[str, str] = {}
    for unit, size in sorted(unit_sizes.items(), key=lambda kv: (-kv[1], kv[0])):
        choice = min(targets, key=lambda k: (filled[k] - targets[k] * total, k))
        assignment[unit] = choice
        filled[choice] += size
    return assignment


def straddling_studies(unit_partition: dict[str, str]) -> list[str]:
    """Studies that appear in more than one partition. Zero is a measurement, not a promise.

    The release used to record this count as the literal 0 and assert that literal in its
    own gate, so the check could not fail and the manuscript's claim of a leak-free split
    rested on nothing. Computing it from the assignment that was actually made turns the
    claim into evidence.
    """
    seen: dict[str, set[str]] = {}
    for unit, partition in unit_partition.items():
        for study in atomic_studies(unit):
            seen.setdefault(study, set()).add(partition)
    return sorted(study for study, parts in seen.items() if len(parts) > 1)


def assign_partition(unit: str) -> str:
    """Assign one split unit to training, calibration or test, 30/30/40.

    Deterministic in the unit and in nothing else: the same unit lands in the same partition
    on every machine and in every re-run, with no seed to record and no order dependence.
    """
    value = int(sha256(unit.encode("utf-8")).hexdigest()[:8], 16) % 10
    return "training" if value <= 2 else "calibration" if value <= 5 else "test"


def conformal_rank(calibration_size: int, alpha: float) -> int:
    """Return the split rank, resolving integer-boundary float roundoff.

    A product within eight float ULP of an integer is treated as that integer.
    This covers literal and computed ``1-level`` inputs without changing levels
    clearly outside arithmetic roundoff. It is not a statistical tolerance.
    """
    if calibration_size < 1:
        raise ValueError("calibration_size must be positive")
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0, 1)")
    product = (calibration_size + 1) * (1.0 - alpha)
    nearest = round(product)
    if abs(product-nearest) <= 8*ulp(product):
        product = nearest
    return int(ceil(product))


def minimum_calibration_size(alpha: float) -> int:
    """Smallest m for which the requested empirical conformal order statistic exists."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0, 1)")
    return int(ceil(1.0 / alpha - 1e-12) - 1)


def supported_level(exchangeable_units: int) -> float:
    """Highest level any distribution-free conformal radius can carry with m units.

    The inverse of `minimum_calibration_size`. The rank ceil((m+1)(1-alpha)) exists only
    when it is at most m, which holds exactly when 1-alpha <= m/(m+1). Counting cohorts
    where the exchangeable unit is a study inflates m and therefore inflates the level
    the manifest appears to support.
    """
    if exchangeable_units < 1:
        raise ValueError("exchangeable_units must be positive")
    return exchangeable_units / (exchangeable_units + 1)


def aggregate_unit_scores(
    scores: Iterable[float], units: Iterable[str], *, aggregate: str = "max"
) -> tuple[np.ndarray, list[str]]:
    """Collapse per-cohort scores to one score per exchangeable unit.

    Cohorts drawn from one study are not exchangeable with each other, so a conformal
    rank computed over them counts dependent observations as independent. `max` is the
    conservative collapse: it makes the unit score cover every cohort that unit supplied.
    """
    values = np.asarray(list(scores), dtype=float)
    labels = _validated_unit_labels(units)
    if len(values) != len(labels):
        raise ValueError("scores and units must have the same length")
    if len(values) == 0:
        raise ValueError("at least one score is required")
    if values.ndim != 1 or np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("calibration scores must be one-dimensional, finite and nonnegative before aggregation")
    if aggregate not in {"max", "median"}:
        raise ValueError("aggregate must be 'max' or 'median'")
    reducer = np.max if aggregate == "max" else np.median
    ordered = sorted(set(labels))
    collapsed = np.asarray(
        [reducer(values[[i for i, u in enumerate(labels) if u == unit]]) for unit in ordered],
        dtype=float,
    )
    return collapsed, ordered


def _validated_unit_labels(units):
    labels = list(units)
    if any(not isinstance(label, str) or not label or label != label.strip() for label in labels):
        raise ValueError("unit labels must be nonempty strings without surrounding whitespace")
    return labels


def _positive_integer(value, name):
    if (isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not np.isfinite(value) or value < 1 or value != int(value)):
        raise ValueError(f"{name} must be an exact positive integer")
    return int(value)


def radius_unit_rank(radius: float, unit_level_scores: Iterable[float]) -> int:
    """Order-statistic position of `radius` among unit-level scores."""
    values = np.asarray(list(unit_level_scores), dtype=float)
    return int(np.sum(values <= float(radius)))


def attained_level(radius: float, unit_level_scores: Iterable[float]) -> float:
    """Return the diagnostic fraction of scores at or below a radius, over m+1.

    This retrospective rank fraction is not a coverage guarantee: ties and a
    data-dependent choice of radius can inflate it. New manifests declare the
    prespecified conformal rank divided by m+1 instead.
    """
    values = np.asarray(list(unit_level_scores), dtype=float)
    if len(values) == 0:
        raise ValueError("at least one unit-level score is required")
    return radius_unit_rank(radius, values) / (len(values) + 1)


def split_conformal_radius(scores: Iterable[float], alpha: float) -> tuple[float, int]:
    values = np.asarray(list(scores), dtype=float)
    if len(values) < 1 or np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("calibration scores must be finite and nonnegative")
    rank = conformal_rank(len(values), alpha)
    if rank > len(values):
        raise ValueError(
            "the requested finite conformal rank exceeds the calibration sample; "
            "use a prespecified global fallback"
        )
    return float(np.partition(values, rank - 1)[rank - 1]), rank


def _scores_hash(values: np.ndarray) -> str:
    payload = json.dumps(
        [float(value) for value in values],
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


@dataclass(frozen=True)
class WassersteinCalibrationManifest:
    manifest_version: str
    confidence_level: float
    alpha: float
    rank: int
    calibration_size: int
    radius: float
    grouping: dict[str, str]
    source: str
    data_hashes: dict[str, str]
    guarantee_scope: str
    fallback_used: bool
    calibration_scores_sha256: str
    requested_level: float
    requested_level_supported: bool
    exchangeable_units: int | None = None
    exchangeable_unit_definition: str | None = None
    exchangeable_unit_labels: tuple[str, ...] | None = None
    unit_score_aggregation: str | None = None
    conformal_rank_counts: str | None = None
    attained_level_value: float | None = None
    unit_scores: tuple[float, ...] | None = None
    unit_scores_median: tuple[float, ...] | None = None
    attained_level_median: float | None = None
    calibration_contract: dict | None = None

    def as_dict(self) -> dict[str, object]:
        units: dict[str, object] = {}
        if self.exchangeable_units is not None:
            units = {
                "exchangeable_units": int(self.exchangeable_units),
                "exchangeable_unit_definition": str(self.exchangeable_unit_definition),
                "exchangeable_unit_labels": list(self.exchangeable_unit_labels or ()),
                "unit_score_aggregation": str(self.unit_score_aggregation),
                # What the rank counted. Without it `calibration_size` is ambiguous --
                # 161 cohorts and 20 units are two different numbers for one field, and a
                # reader cannot tell which guarantee the radius was built for.
                "conformal_rank_counts": str(self.conformal_rank_counts),
                # The collapsed score of every unit, in the order the labels are listed.
                # Without them the attained level is an assertion: a reader cannot see
                # whether the radius sits just under the next unit or far below it, which
                # is the difference between "one more study would help" and "widening the
                # radius would have to admit the mismatched reference".
                "unit_scores": [float(x) for x in (self.unit_scores or ())],
                "unit_scores_median": [float(x) for x in (self.unit_scores_median or ())],
                # New manifests use the fixed rank for the simultaneous unit event.
                # Median scores are diagnostic only; no median coverage is declared.
                "attained_level_all_cohorts": float(self.attained_level_value),
                "attained_level_median_cohort": (
                    None if self.attained_level_median is None
                    else float(self.attained_level_median)
                ),
                "maximum_supported_level": supported_level(int(self.exchangeable_units)),
                "attained_level": float(self.attained_level_value),
            }
        return {
            **({"calibration_contract": self.calibration_contract} if self.calibration_contract else {}),
            **units,
            "manifest_version": self.manifest_version,
            "guarantee_class": "conformal_new_cohort",
            "confidence_level": self.confidence_level,
            "requested_level": float(self.requested_level),
            "requested_level_supported": bool(self.requested_level_supported),
            "alpha": self.alpha,
            "rank": self.rank,
            "calibration_size": self.calibration_size,
            "minimum_group_calibration_size": minimum_calibration_size(self.alpha),
            "radius": self.radius,
            "grouping": self.grouping,
            "source": self.source,
            "data_hashes": self.data_hashes,
            "guarantee_scope": self.guarantee_scope,
            "fallback_used": self.fallback_used,
            "calibration_scores_sha256": self.calibration_scores_sha256,
            "coverage_statement": (coverage_statement(self.calibration_contract) if self.calibration_contract else (
                "LEGACY MANIFEST: migrate from original scores and declare calibration semantics before claiming coverage. "
                "Marginal finite-sample coverage for a new exchangeable cohort at the "
                "manifest scope; one accepted Wasserstein set yields simultaneous bounds "
                "for every threshold evaluated from that set."
            )),
        }


def calibrate_wasserstein_manifest(
    *,
    group_scores: Iterable[float],
    alpha: float,
    grouping: dict[str, str],
    source: str,
    data_hashes: dict[str, str],
    global_scores: Iterable[float] | None = None,
    group_units: Iterable[str] | None = None,
    global_units: Iterable[str] | None = None,
    unit_definition: str = "source|study",
    unit_aggregation: str = "max",
    calibrate_on: str = "cohorts",
    calibration_contract: dict | None = None,
) -> WassersteinCalibrationManifest:
    """Create a manifest under an explicit, fixed study-unit calibration contract.

    New manifests require declared score, reference, target and unit semantics,
    ``calibrate_on='units'`` and maximum aggregation within units. The declared
    level is the prespecified rank divided by the number of units plus one;
    observed ties do not raise it. A small group may use the declared global
    fallback. Historical manifests remain readable by
    :func:`validate_calibration_manifest`, but cannot be recreated as new
    coverage claims without recovering their original scores and semantics.
    ``unit_definition`` is retained for call compatibility; the explicit
    contract supplies the authoritative unit definition.
    """
    if calibration_contract is None:
        raise ValueError("Creating a calibration manifest requires an explicit calibration_contract; migrate original scores and declared semantics before claiming coverage")
    validate_calibration_contract(calibration_contract)
    if calibrate_on != "units" or unit_aggregation != "max":
        raise ValueError("manifest 1.2 requires a prespecified rank over units and max aggregation")
    group_values = np.asarray(list(group_scores), dtype=float)
    if group_values.ndim != 1 or np.any(~np.isfinite(group_values)) or np.any(group_values < 0):
        raise ValueError("calibration scores must be one-dimensional, finite and nonnegative")
    group_unit_labels = None if group_units is None else _validated_unit_labels(group_units)
    global_unit_labels = None if global_units is None else _validated_unit_labels(global_units)
    if group_unit_labels is not None and len(group_unit_labels) != len(group_values):
        raise ValueError("scores and unit labels must have the same length")
    if group_units is None and global_units is None:
        raise ValueError("calibrate_on='units' needs the exchangeable unit of every score")
    required = minimum_calibration_size(alpha)
    # Fallback selection and the quantile both count independent study units.
    available = 0 if group_unit_labels is None else len(set(group_unit_labels))
    use_global = available < required
    if use_global:
        if global_scores is None:
            raise ValueError(
                f"group calibration has m={available} units < {required}; global_scores are required"
            )
        values = np.asarray(list(global_scores), dtype=float)
        scope = "global_marginal"
        effective_grouping = {"scope": "global"}
        unit_labels = global_unit_labels
    else:
        values = group_values
        scope = "declared_group_marginal"
        effective_grouping = {str(key): str(value) for key, value in grouping.items()}
        unit_labels = group_unit_labels
    if unit_labels is None:
        raise ValueError("calibrate_on='units' needs the exchangeable unit of every score")
    collapsed, names = aggregate_unit_scores(values, unit_labels, aggregate="max")
    radius, rank = split_conformal_radius(collapsed, alpha)
    calibration_size = len(collapsed)
    collapsed_median, _ = aggregate_unit_scores(values, unit_labels, aggregate="median")
    requested = 1.0 - float(alpha)
    # Ties never increase the prespecified guarantee.
    declared = rank / (calibration_size + 1)
    request_met = bool(declared >= requested - 1e-12)
    scaling = calibration_contract.get("transport_scaling")
    final_hashes = {str(key): str(value) for key, value in data_hashes.items()}
    if scaling is not None:
        if set(scaling["training_unit_labels"]) & set(unit_labels or []):
            raise ValueError("Training units must be disjoint from calibration units")
        final_hashes["transport_scaling"] = _scaling_hash(scaling)
    return WassersteinCalibrationManifest(
        manifest_version="1.3" if scaling is not None else "1.2",
        calibration_contract=calibration_contract,
        confidence_level=declared,
        requested_level=requested,
        requested_level_supported=request_met,
        alpha=float(alpha),
        rank=rank,
        calibration_size=calibration_size,
        radius=radius,
        grouping=effective_grouping,
        source=str(source),
        data_hashes=final_hashes,
        guarantee_scope=scope,
        fallback_used=use_global,
        calibration_scores_sha256=_scores_hash(values),
        exchangeable_units=len(names),
        exchangeable_unit_definition=str(calibration_contract["unit_definition"]),
        exchangeable_unit_labels=tuple(names),
        unit_score_aggregation="max",
        conformal_rank_counts="units",
        attained_level_value=declared,
        unit_scores=tuple(float(x) for x in collapsed),
        unit_scores_median=tuple(float(x) for x in collapsed_median),
        attained_level_median=None,
    )


def validate_calibration_manifest(manifest: dict[str, object]) -> None:
    """Reject internally inconsistent or over-claimed calibration manifests."""
    if not isinstance(manifest, dict):
        raise ValueError("calibration manifest must be an object")
    keys = set(manifest)
    missing = sorted(_MANIFEST_KEYS - keys)
    unknown = sorted(keys - _MANIFEST_KEYS - _MANIFEST_UNIT_KEYS - _MANIFEST_LEVEL_KEYS
                     - _MANIFEST_DIAGNOSTIC_KEYS - _MANIFEST_CONTRACT_KEYS)
    if missing:
        raise ValueError(f"calibration manifest is missing required keys: {missing}")
    if unknown:
        raise ValueError(f"calibration manifest contains unknown keys: {unknown}")
    hashes = manifest["data_hashes"]
    if not isinstance(hashes, dict) or not hashes or not all(
            isinstance(key, str) and isinstance(value, str) and value
            for key, value in hashes.items()):
        raise ValueError("data_hashes must be a non-empty string mapping")
    for field in ("calibration_size", "rank", "minimum_group_calibration_size"):
        _positive_integer(manifest[field], field)
    unit_keys = keys & _MANIFEST_UNIT_KEYS
    if unit_keys and unit_keys != _MANIFEST_UNIT_KEYS:
        raise ValueError(
            "exchangeable-unit accounting must be complete or absent; missing: "
            f"{sorted(_MANIFEST_UNIT_KEYS - unit_keys)}"
        )
    if unit_keys:
        units = _positive_integer(manifest["exchangeable_units"], "exchangeable_units")
        labels = manifest["exchangeable_unit_labels"]
        if not isinstance(labels, list) or len(labels) != units:
            raise ValueError("exchangeable_unit_labels must list exactly exchangeable_units labels")
        _validated_unit_labels(labels)
        if len(set(labels)) != units:
            raise ValueError("exchangeable_unit_labels must contain one distinct label per unit")
        scores = manifest.get("unit_scores")
        if scores is not None and (not isinstance(scores, list) or len(scores) != units):
            raise ValueError("unit_scores, when present, must carry one score per unit")
        if not np.isclose(float(manifest["maximum_supported_level"]), supported_level(units)):
            raise ValueError("maximum_supported_level is inconsistent with exchangeable_units")
        gained = float(manifest["attained_level"])
        if not 0.0 <= gained <= supported_level(units) + 1e-12:
            raise ValueError("attained_level cannot exceed the level the units support")
        if units > int(manifest["calibration_size"]):
            raise ValueError("exchangeable_units cannot exceed calibration_size")
    version = str(manifest.get("manifest_version"))
    if version not in _MANIFEST_VERSIONS:
        raise ValueError("unsupported Wasserstein calibration manifest version")
    level_keys = keys & _MANIFEST_LEVEL_KEYS
    if version in {"1.1", "1.2", "1.3"} and level_keys != _MANIFEST_LEVEL_KEYS:
        raise ValueError(
            "a 1.1 manifest must record the requested level; missing: "
            f"{sorted(_MANIFEST_LEVEL_KEYS - level_keys)}"
        )
    if version == "1.0" and level_keys:
        raise ValueError("requested-level accounting requires manifest version 1.1")
    if version in {"1.2", "1.3"}:
        validate_calibration_contract(manifest.get("calibration_contract"))
        scaling = manifest["calibration_contract"].get("transport_scaling")
        if (version == "1.3") != (scaling is not None):
            raise ValueError("Normalized transport scaling requires manifest 1.3")
        if scaling is not None:
            if manifest.get("data_hashes", {}).get("transport_scaling") != _scaling_hash(scaling):
                raise ValueError("Transport scales differ from the manifest hash")
            if set(scaling["training_unit_labels"]) & set(manifest.get("exchangeable_unit_labels", [])):
                raise ValueError("Training units overlap calibration unit labels")
        if manifest.get("exchangeable_unit_definition") != manifest["calibration_contract"]["unit_definition"]:
            raise ValueError("exchangeable unit definition conflicts with calibration contract")
        if not unit_keys or manifest.get("conformal_rank_counts") != "units" or manifest.get("unit_score_aggregation") != "max":
            raise ValueError("manifest 1.2 requires complete unit calibration with max aggregation")
        if int(manifest["calibration_size"]) != int(manifest["exchangeable_units"]):
            raise ValueError("calibration_size must count exchangeable units")
        if not np.isclose(float(manifest["confidence_level"]), int(manifest["rank"]) / (int(manifest["calibration_size"]) + 1)):
            raise ValueError("manifest 1.2 coverage level must be the prespecified rank divided by m+1")
        values = manifest.get("unit_scores")
        if not isinstance(values, list) or len(values) != int(manifest["exchangeable_units"]):
            raise ValueError("manifest 1.2 requires every unit score")
        expected_radius, _ = split_conformal_radius(values, float(manifest["alpha"]))
        if not np.isclose(expected_radius, float(manifest["radius"]), rtol=1e-12, atol=1e-12):
            raise ValueError("radius is inconsistent with recorded unit scores")
        if manifest["coverage_statement"] != coverage_statement(manifest["calibration_contract"]):
            raise ValueError("coverage_statement does not match the calibration contract")
    elif "calibration_contract" in keys:
        raise ValueError("calibration_contract requires manifest version 1.2 or 1.3")
    if manifest.get("guarantee_class") != "conformal_new_cohort":
        raise ValueError("calibration manifest guarantee_class is invalid")
    alpha = float(manifest["alpha"])
    confidence = float(manifest["confidence_level"])
    size = int(manifest["calibration_size"])
    rank = int(manifest["rank"])
    radius = float(manifest["radius"])
    if not 0 < alpha < 1:
        raise ValueError("alpha must lie in (0, 1)")
    if version == "1.0":
        if not np.isclose(confidence, 1.0 - alpha):
            raise ValueError("confidence_level must equal 1 - alpha")
    else:
        requested = float(manifest["requested_level"])
        if not np.isclose(requested, 1.0 - alpha):
            raise ValueError("requested_level must equal 1 - alpha")
        if not isinstance(manifest["requested_level_supported"], bool):
            raise ValueError("requested_level_supported must be boolean")
        if unit_keys:
            ceiling = supported_level(int(manifest["exchangeable_units"]))
            if confidence > ceiling + 1e-12:
                raise ValueError(
                    "confidence_level cannot exceed the level the exchangeable units support"
                )
            if not np.isclose(confidence, float(manifest["attained_level"])):
                raise ValueError(
                    "confidence_level must be the level the units certify for this radius"
                )
            if confidence <= 0.0:
                raise ValueError(
                    "a conformal manifest cannot declare a level of zero; the radius "
                    "certifies nothing at the exchangeable unit"
                )
        if bool(manifest["requested_level_supported"]) != bool(confidence >= requested - 1e-12):
            raise ValueError(
                "requested_level_supported must say whether the declared level met the request"
            )
        if not unit_keys and not np.isclose(confidence, requested):
            raise ValueError(
                "without exchangeable-unit accounting the declared level is the requested one"
            )
    minimum = minimum_calibration_size(alpha)
    if int(manifest["minimum_group_calibration_size"]) != minimum:
        raise ValueError("minimum_group_calibration_size is inconsistent with alpha")
    if rank != conformal_rank(size, alpha):
        raise ValueError("calibration manifest rank is inconsistent with m and alpha")
    if rank > size:
        raise ValueError("calibration manifest has no finite empirical conformal quantile")
    if not np.isfinite(radius) or radius < 0:
        raise ValueError("calibration manifest radius must be finite and nonnegative")
    fallback_raw = manifest["fallback_used"]
    if not isinstance(fallback_raw, bool):
        raise ValueError("fallback_used must be boolean")
    fallback = fallback_raw
    scope = manifest["guarantee_scope"]
    grouping = manifest["grouping"]
    if not isinstance(grouping, dict) or not grouping or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in grouping.items()):
        raise ValueError("grouping must be a non-empty string-to-string object")
    if fallback:
        if scope != "global_marginal" or grouping != {"scope": "global"}:
            raise ValueError(
                "global fallback requires global_marginal scope and global grouping")
    elif scope != "declared_group_marginal" or grouping == {"scope": "global"}:
        raise ValueError(
            "group calibration requires declared_group_marginal scope and declared grouping")
    if size < minimum and not fallback:
        raise ValueError("small-group manifest must declare the global fallback")
    if not isinstance(manifest["source"], str) or not manifest["source"].strip():
        raise ValueError("calibration manifest source must be non-empty")
    score_hash = manifest["calibration_scores_sha256"]
    if (not isinstance(score_hash, str) or len(score_hash) != 64
            or any(char not in "0123456789abcdef" for char in score_hash.lower())):
        raise ValueError("calibration_scores_sha256 must be a SHA-256 hex digest")
    if not isinstance(manifest["coverage_statement"], str) or not manifest[
            "coverage_statement"].strip():
        raise ValueError("coverage_statement must be non-empty")


def validate_calibration_contract(contract):
    required = {"score_kind", "reference_rule", "functional_scope", "transport_unit",
                "summary_policy", "reference_protocol", "unit_definition"}
    scaled = isinstance(contract, dict) and contract.get("transport_unit") == "normalized_log2_mg_L"
    if scaled:
        required.add("transport_scaling")
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError("calibration_contract must declare score, reference, functionals, metric, summary policy and units")
    allowed = {"score_kind": {"simultaneous_tail_intervals", "distribution_distance"},
               "reference_rule": {"raw", "projected"},
               "functional_scope": {"all_panel_tails"}, "transport_unit": {"log2_mg_L", "normalized_log2_mg_L"},
               "summary_policy": {"ceiling_50_90_no_range"}}
    for key, choices in allowed.items():
        if contract[key] not in choices:
            raise ValueError(f"unsupported calibration {key}: {contract[key]}")
    for key in ("reference_protocol", "unit_definition"):
        if not isinstance(contract[key], str) or not contract[key].strip():
            raise ValueError(f"calibration {key} must be explicit")
    if scaled:
        if contract["score_kind"] != "simultaneous_tail_intervals" or contract["reference_rule"] != "projected":
            raise ValueError("Normalized calibration requires projected simultaneous-tail scores")
        scaling = contract["transport_scaling"]
        if not isinstance(scaling, dict) or set(scaling) != {"method", "panels", "training_unit_labels"}:
            raise ValueError("Transport scaling needs its method, complete panel map and training labels")
        if scaling["method"] != "training_loo_max":
            raise ValueError("Unsupported transport scaling method")
        if not isinstance(scaling["training_unit_labels"], list):
            raise ValueError("Training unit labels must be a list")
        labels = _validated_unit_labels(scaling["training_unit_labels"])
        if len(labels) < 2 or len(set(labels)) != len(labels):
            raise ValueError("Transport scaling needs at least two distinct training units")
        panels = scaling["panels"]
        if not isinstance(panels, dict) or not panels:
            raise ValueError("Transport scaling needs explicit panels")
        for pid, item in panels.items():
            if not isinstance(pid, str) or not pid or pid != pid.strip():
                raise ValueError("Transport scaling panel identifiers must be explicit")
            if not isinstance(item, dict) or set(item) != {"scale", "panel_sha256"}:
                raise ValueError("Every scaled panel needs a scale and panel hash")
            value = item["scale"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
                raise ValueError("Transport scales must be finite positive numbers")
            if not isinstance(item["panel_sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", item["panel_sha256"]) is None:
                raise ValueError("Invalid transport scaling panel hash")


def _scaling_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _calibration_transport_scale(contract, context, panel):
    """Bind a normalized calibration score to this panel's physical distance."""
    scaling = contract.get("transport_scaling")
    if scaling is None:
        return 1.0
    pid = context.get("panel_id")
    if not isinstance(pid, str) or pid not in scaling["panels"]:
        raise ValueError("calibration_context.panel_id must identify a scaled panel")
    item = scaling["panels"][pid]
    if item["panel_sha256"] != _scaling_hash(panel.as_dict()):
        raise ValueError("Transport scaling panel geometry does not match this input")
    binding = context.get("preparation_binding")
    if binding is not None:
        if not isinstance(binding, dict) or binding.get("panel_id") != pid:
            raise ValueError("Transport scaling panel differs from the preparation binding")
        if binding.get("unit_id") in scaling["training_unit_labels"]:
            raise ValueError("A training unit cannot be used as a target unit")
    return float(item["scale"])


def coverage_statement(contract):
    event = ("the recorded-category distribution" if contract["score_kind"] == "distribution_distance"
             else "the recorded tail intervals simultaneously over the declared panel cuts, not the whole distribution")
    scaling = (" Panel radii equal the normalized calibration radius times their fixed training scales."
               if contract.get("transport_scaling") is not None else "")
    return ("Marginal coverage of " + event + " for every eligible cohort of a new exchangeable unit, "
            "conditional on the fixed training/reference protocol. Requires exchangeable calibration and target units, "
            "the same summary/selection rule and max aggregation. No latent-MIC or conditional-on-covariates guarantee." + scaling)
