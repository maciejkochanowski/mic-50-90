"""Prespecified multi-source external validation for MIC-50-90 v1."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import ceil, sqrt
from pathlib import Path
import re
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd

from mic_50_90.censoring import censoring_record, parse_numeric_mic
from mic_50_90.conformal import (
    balanced_partition,
    calibrate_wasserstein_manifest,
    canonical_split_units,
    split_unit,
    straddling_studies,
)
from mic_50_90.comparability import (
    matched_reference, tested_range,
)
from mic_50_90.dro import critical_radius, project_onto_sharp_set, wasserstein_1d
from mic_50_90.empirical import EmpiricalProblem, closed_form_tail_counts
from mic_50_90.model import MICPanel, QuantileSummary, format_mic


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MIN_N = 20
MIN_CATEGORIES = 3
BOOTSTRAP_REPETITIONS = 500
RANDOM_SEED = 20260809


@dataclass(frozen=True)
class Cohort:
    source: str
    study: str
    country: str
    year: int
    species: str
    drug: str
    method: str
    standard: str
    counts: dict[float, int]
    censored_count: int = 0
    censored_counts: dict[str, int] = field(default_factory=dict)
    source_observation_count: int | None = None

    @property
    def n(self) -> int:
        return int(sum(self.counts.values()))

    @property
    def identifier(self) -> str:
        value = "|".join(
            map(
                str,
                (
                    self.source,
                    self.study,
                    self.country,
                    self.year,
                    self.species,
                    self.drug,
                    self.method,
                    self.standard,
                ),
            )
        )
        return sha256(value.encode("utf-8")).hexdigest()[:20]

    @property
    def block_id(self) -> str:
        return f"{self.source}|{self.study}|{self.country}|{self.year}"

    @property
    def split_unit(self) -> str:
        """Project/study unit kept wholly within one conformal partition."""
        return split_unit(self.source, self.study)

    @property
    def source_n(self) -> int:
        return int(
            self.source_observation_count
            if self.source_observation_count is not None
            else self.n + self.censored_count
        )




def load_cdc() -> tuple[list[Cohort], dict[str, Any]]:
    cohorts: list[Cohort] = []
    audit: dict[str, Any] = {"workbooks": {}, "parse_failures": []}
    for path in sorted((ROOT / "data" / "raw" / "cdc").glob("Lab-*-MIC.xlsx")):
        if "Description" in path.name:
            continue
        species = path.stem.removeprefix("Lab-").removesuffix("-MIC").replace("-", " ")
        book = pd.ExcelFile(path)
        accepted = 0
        for sheet in book.sheet_names:
            if any(token in sheet.lower() for token in ("main", "query", "work", "count")):
                continue
            raw = pd.read_excel(path, sheet_name=sheet, header=None)
            header = None
            for index in range(min(15, len(raw))):
                first = str(raw.iloc[index, 0]).lower()
                second = str(raw.iloc[index, 1]).lower() if raw.shape[1] > 1 else ""
                if "mic" in first and ("count" in second or "number" in second):
                    header = index
                    break
            if header is None:
                audit["parse_failures"].append(
                    {"file": path.name, "sheet": sheet, "reason": "MIC count header absent"}
                )
                continue
            counts: Counter[float] = Counter()
            censored_counts: Counter[str] = Counter()
            for _, row in raw.iloc[header + 1 :].iterrows():
                parsed = parse_numeric_mic(row.iloc[0])
                count = pd.to_numeric(row.iloc[1], errors="coerce")
                if parsed is None or pd.isna(count) or int(count) <= 0:
                    continue
                numeric, operator = parsed
                if operator is None:
                    counts[numeric] += int(count)
                else:
                    censored_counts[f"{operator}{format_mic(numeric)}"] += int(count)
            if sum(counts.values()) < MIN_N or len(counts) < MIN_CATEGORIES:
                continue
            drug = re.split(r"_(?:a|e|p|ec|cns|mrsa)$", sheet, flags=re.IGNORECASE)[0]
            cohorts.append(
                Cohort(
                    source="CDC Reference AST",
                    study=path.stem,
                    country="USA/mixed surveillance",
                    year=2024,
                    species=species,
                    drug=drug.replace("_", " "),
                    method=(
                        "E-test"
                        if species.lower() == "candida" and "amphotericin" in drug.lower()
                        else "reference broth microdilution"
                    ),
                    standard="CLSI",
                    counts=dict(counts),
                    censored_count=sum(censored_counts.values()),
                    censored_counts=dict(censored_counts),
                    source_observation_count=sum(counts.values()) + sum(censored_counts.values()),
                )
            )
            accepted += 1
        audit["workbooks"][path.name] = {
            "sheets": len(book.sheet_names),
            "eligible_distribution_sheets": accepted,
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
    audit["eligible_cohorts"] = len(cohorts)
    audit["eligible_observations"] = sum(item.n for item in cohorts)
    audit["censored_observations_excluded_from_exact_value_analysis"] = sum(
        item.censored_count for item in cohorts
    )
    return cohorts, audit


EBI_PATH = ROOT / "data" / "raw" / "ebi" / "phenotype-2026-07.parquet"

#: Common eligibility filter for the external cohort loader. Independently supplied
#: study-accession maps must describe these eligible source rows.
_EBI_ROW_FILTER = """
      measurement_units='mg/L'
      AND laboratory_typing_method IN ('broth dilution','agar dilution','E-test')
      AND ast_standard IS NOT NULL
      AND measurement_sign IN ('=','==','<=','<','>','>=')
      AND regexp_full_match(measurement, '[0-9]+([.][0-9]+)?')
      AND BioSample_ID IS NOT NULL AND species IS NOT NULL
      AND antibiotic_name IS NOT NULL
"""


def eligible_ebi_rows() -> tuple[pd.DataFrame, dict[str, int]]:
    """One row per isolate, antibiotic, method and standard, before any cohort grouping.

    Returned alongside the two counts the audit trail records: the size of the release and
    the size after the value filters but before the explicit BioSample deduplication.
    """
    escaped = str(EBI_PATH).replace("'", "''")
    connection = duckdb.connect()
    total = connection.execute(
        f"SELECT count(*) FROM read_parquet('{escaped}')"
    ).fetchone()[0]
    base_count = connection.execute(
        f"SELECT count(*) FROM read_parquet('{escaped}') WHERE {_EBI_ROW_FILTER}"
    ).fetchone()[0]
    frame = connection.execute(
        f"""
        WITH eligible AS (
          SELECT
            BioSample_ID,
            coalesce(nullif(AMR_associated_publications, ''), database, 'unknown') AS study,
            coalesce(ISO_country_code, 'UNK') AS country,
            coalesce(collection_year, -1) AS year,
            species,
            antibiotic_name AS drug,
            laboratory_typing_method AS method,
            ast_standard AS standard,
            cast(measurement AS DOUBLE) AS mic,
            measurement_sign AS sign,
            row_number() OVER (
              PARTITION BY BioSample_ID, antibiotic_name, laboratory_typing_method, ast_standard
              ORDER BY CASE WHEN measurement_sign IN ('=','==') THEN 0 ELSE 1 END,
                       coalesce(AMR_associated_publications, ''), coalesce(database, '')
            ) AS duplicate_rank
          FROM read_parquet('{escaped}')
          WHERE {_EBI_ROW_FILTER}
        )
        SELECT * EXCLUDE duplicate_rank FROM eligible WHERE duplicate_rank=1
        """
    ).fetchdf()
    return frame, {"raw_rows": int(total),
                   "rows_before_deduplication": int(base_count)}


NCBI_ACCESSIONS = ROOT / "data" / "raw" / "ncbi"


def repaired_study_column(frame: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    """Replace a repository name in `study` with the accessions that name the study.

    A row whose portal record already carries a publication accession is left alone. A row
    that carries none takes the BioProject its isolate was deposited under, joined with
    every publication NCBI records for that project. Both tokens go in, not just the
    project: a study that reached the corpus twice -- once with its paper, once only as a
    deposit -- must be merged by the closure rather than counted as two units, and the
    closure can only merge what it can see in one field.

    A row whose BioSample has no project on record keeps the repository name and therefore
    keeps no unit. That is the honest outcome: the study is still unidentified.
    """
    samples = json.loads((NCBI_ACCESSIONS / "biosample_to_bioproject.json").read_text())
    publications = json.loads(
        (NCBI_ACCESSIONS / "bioproject_to_publication.json").read_text())

    def repair(row: pd.Series) -> str:
        recorded = str(row["study"] or "").strip()
        if any(part.strip().isdigit() for part in recorded.split(";")):
            return recorded
        projects = samples.get(row["BioSample_ID"]) or []
        if not projects:
            return recorded
        tokens = set(projects)
        for project in projects:
            tokens.update(publications.get(project, []))
        return ";".join(sorted(tokens))

    repaired = frame.apply(repair, axis=1)
    audit = {
        "rows_repaired": int((repaired != frame["study"]).sum()),
        "rows_total": int(len(frame)),
        "biosamples_in_map": len(samples),
        "biosamples_with_project": sum(1 for value in samples.values() if value),
        "bioprojects_with_publication": sum(1 for v in publications.values() if v),
        "rule": "publication accession where the portal has one; otherwise the BioProject "
                "accession joined with that project's publications; otherwise unchanged",
    }
    return repaired, audit


def load_ebi(*, repair_study: bool = True) -> tuple[list[Cohort], dict[str, Any]]:
    """Load EMBL-EBI cohorts and optionally resolve missing study labels.

    With repair_study=True, the loader uses the separately provided BioSample-to-
    BioProject maps to distinguish study units. With False, it retains the source
    labels. The unit-allocation helper can inspect both interpretations.
    """
    path = EBI_PATH
    frame, counts = eligible_ebi_rows()
    repair_audit: dict[str, Any] | None = None
    if repair_study:
        frame = frame.copy()
        frame["study"], repair_audit = repaired_study_column(frame)
    total = counts["raw_rows"]
    base_count = counts["rows_before_deduplication"]
    keys = ["study", "country", "year", "species", "drug", "method", "standard"]
    cohorts: list[Cohort] = []
    all_groups = 0
    for values, group in frame.groupby(keys, dropna=False, sort=False):
        all_groups += 1
        exact = group[group["sign"].isin(["=", "=="])]
        counts = exact.groupby("mic").size().to_dict()
        censored = group[~group["sign"].isin(["=", "=="])]
        censored_counts = {
            f"{sign}{format_mic(float(mic))}": int(count)
            for (sign, mic), count in censored.groupby(["sign", "mic"]).size().items()
        }
        if len(exact) < MIN_N or len(counts) < MIN_CATEGORIES:
            continue
        cohorts.append(
            Cohort(
                source="EMBL-EBI AMR Portal 2026-07",
                study=str(values[0]),
                country=str(values[1]),
                year=int(values[2]),
                species=str(values[3]),
                drug=str(values[4]),
                method=str(values[5]),
                standard=str(values[6]),
                counts={float(key): int(value) for key, value in counts.items()},
                censored_count=int(len(censored)),
                censored_counts=censored_counts,
                source_observation_count=int(len(group)),
            )
        )
    # DuckDB returns scan results in a non-deterministic order, and `groupby(sort=False)`
    # carries that order through, so two calls in one process yielded the same 878 cohorts
    # in different order. Every statistic here is order-invariant, but the manifest field
    # `calibration_scores_sha256` is not: it hashed a list whose order changed run to run,
    # so it bound nothing. Ordering the cohorts fixes the cause and leaves the hash sharp
    # enough to still detect a genuine change of content.
    cohorts.sort(key=lambda item: item.identifier)
    audit = {
        "release": "2026-07",
        "raw_rows": int(total),
        "rows_after_unit_method_standard_and_value_filters_before_deduplication": int(
            base_count
        ),
        "rows_after_explicit_biosample_deduplication": int(len(frame)),
        "duplicates_removed": int(base_count - len(frame)),
        "deduplication_key": [
            "BioSample_ID",
            "antibiotic_name",
            "laboratory_typing_method",
            "ast_standard",
        ],
        "deduplication_tie_break": "prefer exact signs, then stable source labels",
        "homogeneous_cohort_key": keys,
        "cohorts_before_minimum_size_filter": all_groups,
        "eligible_cohorts": len(cohorts),
        "eligible_observations": sum(item.n for item in cohorts),
        "eligible_observations_definition": "exact MIC observations used in analysis",
        "censored_observations_excluded_from_exact_value_analysis": sum(
            item.censored_count for item in cohorts
        ),
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "study_accession_repair": repair_audit,
        "sign_counts_after_deduplication": {
            str(key): int(value) for key, value in frame["sign"].value_counts().items()
        },
    }
    return cohorts, audit


def load_eucast() -> tuple[list[Cohort], dict[str, Any]]:
    cohorts: list[Cohort] = []
    audit: dict[str, Any] = {
        "role": "information_loss_benchmark_only",
        "prohibited_interpretation": "resistance frequencies or comparisons",
        "files": {},
    }
    for path in sorted((ROOT / "data" / "raw" / "eucast").glob("*.html")):
        frame = pd.read_html(path, attrs={"id": "search-results-table"})[0]
        numeric_columns: list[tuple[str, float]] = []
        for column in frame.columns:
            try:
                numeric_columns.append((str(column), float(column)))
            except (TypeError, ValueError):
                continue
        accepted = 0
        for _, row in frame.iterrows():
            counts = {
                numeric: int(pd.to_numeric(row[label], errors="coerce"))
                for label, numeric in numeric_columns
                if pd.notna(pd.to_numeric(row[label], errors="coerce"))
                and int(pd.to_numeric(row[label], errors="coerce")) > 0
            }
            if sum(counts.values()) < MIN_N or len(counts) < MIN_CATEGORIES:
                continue
            cohorts.append(
                Cohort(
                    source="EUCAST aggregated MIC website",
                    study="curated aggregated distributions",
                    country="multiple",
                    year=2026,
                    species=str(row.iloc[0]),
                    drug=path.stem.replace("_", " ").title(),
                    method="reference or reference-calibrated MIC",
                    standard="EUCAST/CLSI/ISO-calibrated heterogeneous",
                    counts=counts,
                )
            )
            accepted += 1
        audit["files"][path.name] = {
            "table_rows": int(len(frame)),
            "eligible_rows": accepted,
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()).hexdigest(),
        }
    audit["eligible_cohorts"] = len(cohorts)
    audit["eligible_observations"] = sum(item.n for item in cohorts)
    return cohorts, audit


def _quantile_index(counts: np.ndarray, probability: float) -> tuple[int, int]:
    rank = int(ceil(probability * int(counts.sum())))
    index = int(np.searchsorted(np.cumsum(counts), rank, side="left"))
    return rank, index


def _thresholds(levels: np.ndarray, q50_index: int, q90_index: int) -> list[tuple[str, float]]:
    candidates = [("at_MIC50", float(levels[q50_index]))]
    if q50_index < q90_index:
        candidates.append(
            (
                "between_MIC50_MIC90",
                float(sqrt(levels[q50_index] * levels[q90_index])),
            )
        )
    else:
        candidates.append(("MIC50_equals_MIC90", float(levels[q50_index])))
    candidates.append(("at_MIC90", float(levels[q90_index])))
    unique: dict[float, str] = {}
    for relation, value in candidates:
        unique.setdefault(value, relation)
    return [(relation, value) for value, relation in unique.items()]


def evaluate_cohorts(
    cohorts: Iterable[Cohort],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    certificates: list[dict[str, Any]] = []
    for cohort in cohorts:
        levels = np.asarray(sorted(cohort.counts), dtype=float)
        counts = np.asarray([cohort.counts[value] for value in levels], dtype=int)
        panel = MICPanel.from_twofold_levels(
            levels, left_censored=False, right_censored=False
        )
        rank50, q50 = _quantile_index(counts, 0.5)
        rank90, q90 = _quantile_index(counts, 0.9)
        summaries = (
            QuantileSummary(0.5, rank50, q50, panel.labels[q50], "ceiling"),
            QuantileSummary(0.9, rank90, q90, panel.labels[q90], "ceiling"),
        )
        base = {
            "cohort_id": cohort.identifier,
            "source": cohort.source,
            "study": cohort.study,
            "country": cohort.country,
            "year": cohort.year,
            "block_id": cohort.block_id,
            "species": cohort.species,
            "drug": cohort.drug,
            "method": cohort.method,
            "standard": cohort.standard,
            "n": cohort.n,
            "source_observation_count": cohort.source_n,
            "exact_observations_analysed": cohort.n,
            "categories": len(levels),
            "censored_fraction": cohort.censored_count / cohort.source_n,
            "censored_observations_excluded": cohort.censored_count,
            "censoring_intervals": [
                censoring_record(label, count)
                for label, count in sorted(cohort.censored_counts.items())
            ],
            "censoring_policy": (
                "operator-bearing observations are preserved as intervals in the audit "
                "and excluded from exact-value likelihood and conformal calculations"
            ),
            "mic50": float(levels[q50]),
            "mic90": float(levels[q90]),
            "quantile_categories_equal": q50 == q90,
        }
        try:
            problem = EmpiricalProblem(n=cohort.n, panel=panel, quantiles=summaries)
        except (RuntimeError, ValueError) as exc:
            records.append(
                {
                    **base,
                    "threshold_relation": "problem_initialisation",
                    "threshold": np.nan,
                    "available": False,
                    "error": str(exc),
                    "covered": False,
                }
            )
            continue
        for relation, threshold in _thresholds(levels, q50, q90):
            objective = panel.panel_tail(threshold)
            truth_count = int(objective @ counts)
            try:
                lower, upper = problem.bounds(objective)
                closed = closed_form_tail_counts(
                    n=cohort.n,
                    tail=objective,
                    quantiles=summaries,
                    minimum_index=None,
                    maximum_index=None,
                )
                certificate_ok = bool(
                    lower.certificate.optimality_verified
                    and upper.certificate.optimality_verified
                    and (lower.count, upper.count) == closed
                )
                records.append(
                    {
                        **base,
                        "threshold_relation": relation,
                        "threshold": threshold,
                        "available": True,
                        "error": None,
                        "true_tail_fraction": truth_count / cohort.n,
                        "lower": lower.fraction,
                        "upper": upper.fraction,
                        "width": upper.fraction - lower.fraction,
                        "midpoint_absolute_error": abs(
                            (lower.fraction + upper.fraction) / 2 - truth_count / cohort.n
                        ),
                        "covered": lower.count <= truth_count <= upper.count,
                        "certificate_ok": certificate_ok,
                        "max_duality_gap": max(
                            lower.certificate.duality_gap,
                            upper.certificate.duality_gap,
                        ),
                    }
                )
                certificates.append(
                    {
                        "cohort_id": cohort.identifier,
                        "threshold": threshold,
                        "lower": lower.as_dict(panel.labels),
                        "upper": upper.as_dict(panel.labels),
                        "closed_form_counts": list(closed),
                    }
                )
            except (RuntimeError, ValueError) as exc:
                records.append(
                    {
                        **base,
                        "threshold_relation": relation,
                        "threshold": threshold,
                        "available": False,
                        "error": str(exc),
                        "covered": False,
                    }
                )
    return pd.DataFrame(records), certificates


def _distribution(counter: Counter[float], levels: np.ndarray) -> np.ndarray:
    values = np.asarray([counter.get(float(level), 0) for level in levels], dtype=float)
    return values / values.sum()


#: A printed dilution label deviates from the exact concentration by at most this much in
#: log2. EUCAST prints 0.03 for 0.03125 and 0.06 for 0.0625, which are 0.058 and 0.059
#: away; a gradient-strip panel steps by about 0.5. Nothing real sits between.
_PRINTING_TOLERANCE_LOG2 = 0.15


def transport_positions(levels: np.ndarray) -> np.ndarray:
    """Positions for the transport cost, in log2 mg/L, with printing undone where it applies.

    Two scales reach this function and they must not be treated alike. On a twofold panel
    the categories are one dilution apart by construction, but the labels are printed
    rounded, so ``log2(0.030) - log2(0.016)`` returns 0.907 and ``log2(0.125) - log2(0.060)``
    returns 1.059 for two pairs that are both exactly one dilution apart. Taking the printed
    label at face value makes the transport cost uneven exactly where the printing convention
    bites, and the calibrated radius inherits it. Snapping to the lattice removes that.

    A gradient-strip panel is different: 0.023, 0.032, 0.047 are the concentrations the strip
    actually carries, about half a dilution apart, and snapping them to a doubling lattice
    would collapse distinct categories into one. Measured on the external corpus of 1282
    cohorts: 779 panels are exact twofold, 377 are twofold with printed labels (median step
    error 0.059 in log2, worst 0.476) and 126 are gradient scales. So the scale is decided
    per panel and only the printed twofold ones are snapped.
    """
    logs = np.log2(np.asarray(levels, dtype=float))
    steps = np.diff(logs)
    if steps.size and np.all(np.abs(steps - np.round(steps)) <= _PRINTING_TOLERANCE_LOG2):
        snapped = np.round(logs)
        if np.all(np.diff(snapped) > 0):        # never collapse two categories into one
            return snapped
    return logs


def _w1_between(left: Counter[float], right: Counter[float]) -> float:
    levels = np.asarray(sorted(set(left) | set(right)), dtype=float)
    return wasserstein_1d(
        _distribution(left, levels),
        _distribution(right, levels),
        transport_positions(levels),
    )



def _comparable_score(cohort: Cohort, training: list[Cohort], *,
                      score: str, centre: str = "reference") -> float | None:
    """One nonconformity score, or None when the pair carries no admissible comparison.

    `score="distance"` is the released surrogate: the transport distance between the two
    histograms. `score="interval"` is the quantity the guarantee is actually about: the
    smallest radius at which the interval this work reports still covers the true tail
    fraction, worst case over every threshold on the common panel.

    `centre="projected"` moves the ball onto the point of the sharp identified set nearest
    the reference before scoring. The pooled reference is another study's histogram and
    need not satisfy the target's own reported MIC50 and MIC90, so the ball is otherwise
    centred outside the set it is intersected with and every radius carries that distance
    as an additive floor. See `dro.project_onto_sharp_set`.
    """
    built = matched_reference(
        cohort.counts, tested_range(cohort.counts, cohort.censored_counts),
        [(item.counts, tested_range(item.counts, item.censored_counts))
         for item in training],
        minimum_count=MIN_N, minimum_categories=MIN_CATEGORIES)
    if built is None:
        return None
    observed, matched, _window, _used = built
    if score == "distance":
        return _w1_between(observed, matched)
    levels = np.asarray(sorted(observed), dtype=float)
    counts = np.asarray([observed[value] for value in levels], dtype=int)
    panel = MICPanel.from_twofold_levels(levels, left_censored=False, right_censored=False)
    rank50, q50 = _quantile_index(counts, 0.5)
    rank90, q90 = _quantile_index(counts, 0.9)
    try:
        problem = EmpiricalProblem(n=int(counts.sum()), panel=panel, quantiles=(
            QuantileSummary(0.5, rank50, q50, panel.labels[q50], "ceiling"),
            QuantileSummary(0.9, rank90, q90, panel.labels[q90], "ceiling")))
    except ValueError:
        return None
    weights = np.array([matched.get(value, 0.0) for value in levels], dtype=float)
    if weights.sum() <= 0:
        return None
    reference = weights / weights.sum()
    if centre == "projected":
        try:
            _distance, reference = project_onto_sharp_set(
                problem=problem, reference=reference, positions=None)
        except ValueError:
            return None
    elif centre != "reference":
        raise ValueError(f"unknown ambiguity-set centre: {centre!r}")
    objectives = [panel.panel_tail(float(value)) for value in levels[:-1]]
    truths = [float(objective @ counts) / counts.sum() for objective in objectives]
    return critical_radius(problem=problem, reference=reference,
                           positions=None, objectives=objectives, truths=truths)


def conformal_external_validation(
    cohorts: list[Cohort], ebi_hash: str, *,
    assignment: dict[str, str] | None = None,
    calibrate_on: str = "units",
    score: str = "interval",
    centre: str = "projected",
    require_comparable: bool = True,
    alpha: float = 0.10,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    """Evaluate interval calibration with an explicit exchangeable-unit contract.

    assignment supplies a partition of whole units. New manifests require
    unit-level interval scores and comparable panels; unsupported cohort-ranked
    or unqualified distance settings are refused before scoring.

    require_comparable restricts comparisons to the available common measurement
    range. The score is the smallest radius for which the reported interval
    covers the observed cohort quantity. A supplied assignment does not bypass
    overlap, eligibility or unit-contract checks.
    """
    if calibrate_on != 'units' or score != 'interval' or not require_comparable:
        raise ValueError('New calibration requires an explicit contract: use '
                         'calibrate_on="units", score="interval", require_comparable=True. '
                         'Inspect retained historical artifacts for other settings; '
                         'do not interpret them as current calibrated guarantees.')
    if centre not in {'projected', 'reference'}:
        raise ValueError('centre must be projected or reference')
    ebi = [item for item in cohorts if item.source.startswith("EMBL-EBI")]
    group_key = lambda item: (item.species, item.drug, item.method, item.standard)
    # Three changes from the released design, each forced by a defect the previous one hid.
    #
    # The assignment is made on the canonical unit rather than the raw label: a cohort
    # citing "A;B" and a cohort citing "B" are one study for exchangeability and two
    # different strings for a hash, so hashing the label put study B in two partitions.
    #
    # A cohort whose study field carries no publication accession has no identifiable study.
    # It contributes to the training pool, where only distributions are added up, and never
    # to calibration or test, where the guarantee rests on units being exchangeable. The
    # alternative -- treating the repository name as the study -- merged CDC, NCBI, NDARO
    # and PATRIC into a single 221-cohort unit, which is not a study either.
    #
    # The partition is balanced by cohort count instead of hashed, because the units are
    # too unequal for a hash to divide them usefully; see balanced_partition.
    canonical = canonical_split_units({item.split_unit for item in ebi})
    unit_of = {item.identifier: canonical[item.split_unit] for item in ebi}
    unit_sizes: Counter[str] = Counter(
        unit for unit in (unit_of[item.identifier] for item in ebi) if unit is not None)
    if assignment is None:
        split_by_unit = balanced_partition(
            dict(unit_sizes), {"training": 0.30, "calibration": 0.30, "test": 0.40})
        split_rule = ("whole units assigned largest first to whichever partition is "
                      "furthest below its cohort quota, targets 30/30/40")
    else:
        # A unit the allocation does not name is one that could never produce a score --
        # under the comparability rule, a unit with no potential reference anywhere. It
        # goes to training, where its distributions still add to a pool, and never to
        # calibration or test, where it would be counted as an exchangeable unit it is
        # not. The count is reported rather than absorbed silently.
        unplaced = sorted(set(unit_sizes) - set(assignment))
        split_by_unit = {unit: assignment.get(unit, "training") for unit in unit_sizes}
        split_rule = ("prespecified allocation supplied by the caller; "
                      f"{len(unplaced)} units with no admissible reference sent to training")
    splits = {item.identifier: (split_by_unit[unit_of[item.identifier]]
                                if unit_of[item.identifier] is not None else "training")
              for item in ebi}
    straddling = straddling_studies(split_by_unit)
    unidentified = sum(1 for item in ebi if unit_of[item.identifier] is None)
    training_pools: dict[tuple[str, str, str, str], Counter[float]] = defaultdict(Counter)
    training_sizes: Counter[tuple[str, str, str, str]] = Counter()
    training_members: dict[tuple[str, str, str, str], list[Cohort]] = defaultdict(list)
    for cohort in ebi:
        if splits[cohort.identifier] == "training":
            training_pools[group_key(cohort)].update(cohort.counts)
            training_sizes[group_key(cohort)] += cohort.n
            training_members[group_key(cohort)].append(cohort)


    def score_against(cohort: Cohort, key: tuple[str, str, str, str]) -> float | None:
        """The nonconformity score of this cohort against a named group's training pool.

        Taking the group as an argument rather than reading it off the cohort is what lets
        the negative control be scored by the same function as the matched reference. It
        used to be a raw transport distance while the matched side was the calibrated
        score, so once the score became the critical radius of the reported interval the
        two sides stopped being the same quantity and the control compared nothing.
        """
        if key not in training_pools:
            return None
        if not require_comparable:
            return _w1_between(Counter(cohort.counts), training_pools[key])
        return _comparable_score(cohort, training_members[key], score=score,
                                 centre=centre)

    def nonconformity(cohort: Cohort) -> float | None:
        return score_against(cohort, group_key(cohort))

    incomparable = 0
    calibration_rows: list[dict[str, Any]] = []
    calibration_scores: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    # The exchangeable unit of this design is the split unit, not the cohort: `_split`
    # keeps every cohort of a study in one partition precisely because they are dependent.
    # Carrying the unit alongside each score lets the manifest report the level those
    # units support instead of the level the cohort count suggests.
    calibration_units: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for cohort in ebi:
        key = group_key(cohort)
        if splits[cohort.identifier] == "calibration" and key in training_pools:
            value = nonconformity(cohort)
            if value is None or not np.isfinite(value):
                incomparable += 1
                continue
            calibration_scores[key].append(value)
            calibration_units[key].append(unit_of[cohort.identifier])
            # Kept here rather than recomputed: every score costs a bisection over linear
            # programmes, so a supplementary analysis that regroups them must read them.
            calibration_rows.append(
                {"species": cohort.species, "drug": cohort.drug, "method": cohort.method,
                 "standard": cohort.standard, "country": cohort.country,
                 "year": cohort.year, "n": cohort.n,
                 "split_unit": unit_of[cohort.identifier],
                 "cohort_id": cohort.identifier, "score": value})
    global_scores = [value for values in calibration_scores.values() for value in values]
    # The calibration scores, with the labels a regrouping would need. Written here rather
    # than recomputed downstream: every score costs a bisection over linear programmes, so
    # a supplementary analysis that regroups them must read them, not repeat them.

    global_units = [unit for key in calibration_scores for unit in calibration_units[key]]
    if len(global_scores) < 19:
        raise RuntimeError("External conformal calibration has fewer than 19 global scores")
    manifests: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    manifest_rows: list[dict[str, Any]] = []
    for key in training_pools:
        manifest = calibrate_wasserstein_manifest(
            group_scores=calibration_scores.get(key, []),
            global_scores=global_scores,
            group_units=calibration_units.get(key, []),
            global_units=global_units,
            alpha=alpha,
            grouping={
                "species": key[0],
                "drug": key[1],
                "method": key[2],
                "standard": key[3],
            },
            source="EMBL-EBI AMR Portal 2026-07 prespecified split",
            data_hashes={"phenotype.parquet": ebi_hash},
            calibrate_on=calibrate_on,
            calibration_contract=({
                "score_kind": "simultaneous_tail_intervals",
                "reference_rule": "projected" if centre == "projected" else "raw",
                "functional_scope": "all_panel_tails",
                "transport_unit": "log2_mg_L",
                "summary_policy": "ceiling_50_90_no_range",
                "reference_protocol": "ebi-comparable-training-pool-v1",
                "unit_definition": "connected publication/BioProject study; max over eligible cohorts",
            } if calibrate_on == "units" and score == "interval" and require_comparable else None),
        ).as_dict()
        manifests[key] = manifest
        manifest_rows.append({"group": list(key), **manifest})

    by_drug = defaultdict(list)
    for key in training_pools:
        by_drug[key[1]].append((training_sizes[key], key))
    records: list[dict[str, Any]] = []
    for cohort in ebi:
        if splits[cohort.identifier] != "test":
            continue
        key = group_key(cohort)
        base = {
            "cohort_id": cohort.identifier,
            "block_id": cohort.block_id,
            "split_unit": unit_of[cohort.identifier],
            "species": cohort.species,
            "drug": cohort.drug,
            "method": cohort.method,
            "standard": cohort.standard,
            "n": cohort.n,
        }
        matched_distance = (nonconformity(cohort)
                            if key in training_pools and key in manifests else None)
        if matched_distance is None or not np.isfinite(matched_distance):
            records.append(
                {
                    **base,
                    "available": False,
                    # Two different refusals, kept apart on purpose: no reference at all,
                    # or a reference measured over concentrations this cohort was not
                    # tested at. Reporting them as one hides which of the two a wider
                    # corpus would fix.
                    "no_reference": key not in training_pools or key not in manifests,
                    "no_comparable_reference": (key in training_pools
                                                and key in manifests),
                    "covered": False,
                }
            )
            continue
        manifest = manifests[key]
        candidates = [
            item
            for item in by_drug.get(cohort.drug, [])
            if item[1] != key
            and (item[1][0] != key[0] or item[1][2] != key[2] or item[1][3] != key[3])
        ]
        negative_distance = np.nan
        negative_key = None
        matched_transport = negative_transport = None
        if candidates:
            _, negative_key = max(candidates, key=lambda item: item[0])
            against = score_against(cohort, negative_key)
            # The same control on the released quantity, so the two questions stay apart:
            # whether the group key carries signal at all (transport distance between the
            # cohort and each reference, both restricted to the range they share), and
            # whether swapping the reference moves the interval the work reports.
            matched_transport = _comparable_score(
                cohort, training_members[key], score="distance", centre=centre)
            negative_transport = _comparable_score(
                cohort, training_members[negative_key], score="distance", centre=centre)
            # None means the deliberately mismatched pair carries no admissible comparison
            # under the same rule the matched side obeys. That is an absent control, not a
            # control that passed, and it drops out of the denominator rather than scoring.
            negative_distance = (float(against) if against is not None
                                 and np.isfinite(against) else np.nan)
        records.append(
            {
                **base,
                "available": True,
                "no_reference": False,
                "calibration_size": manifest["calibration_size"],
                "rank": manifest["rank"],
                "radius": manifest["radius"],
                "fallback_used": manifest["fallback_used"],
                "guarantee_scope": manifest["guarantee_scope"],
                "matched_distance": matched_distance,
                "covered": matched_distance <= float(manifest["radius"]),
                "negative_group": None if negative_key is None else "|".join(negative_key),
                "negative_distance": negative_distance,
                "negative_distance_increased": bool(
                    np.isfinite(negative_distance) and negative_distance > matched_distance
                ),
                "matched_transport": matched_transport,
                "negative_transport": negative_transport,
                "negative_transport_increased": (
                    bool(negative_transport > matched_transport)
                    if matched_transport is not None and negative_transport is not None
                    else None
                ),
            }
        )
    frame = pd.DataFrame(records)
    available = frame[frame["available"]] if len(frame) else frame
    negative = available[available["negative_distance"].notna()] if len(available) else available
    transport_control = (available[available["negative_transport"].notna()]
                         if len(available) and "negative_transport" in available
                         else available.iloc[0:0])
    summary = {
        "guarantee_class": "conformal_new_cohort",
        # The released summary described a hash of the label modulo ten, which is the
        # rule this design stopped using when `balanced_partition` replaced it on
        # 2026-08-23. An artefact that names a rule it does not run cannot be audited
        # against its own code, so the field now reports the rule actually applied.
        "split_rule": split_rule,
        "all_cohorts_of_one_unit_stay_together": True,
        "conformal_rank_counts": calibrate_on,
        "units_without_any_admissible_reference": (0 if assignment is None
                                                   else len(unplaced)),
        "alpha": alpha,
        "nonconformity_score": score if require_comparable else "distance",
        "reference_restricted_to_common_tested_range": bool(require_comparable),
        "ambiguity_set_centre": centre,
        "calibration_score_rows": calibration_rows,
        "calibration_cohorts_without_comparable_reference": int(incomparable),
        "split_unit": "connected component of studies sharing a publication",
        "split_units_total": len(split_by_unit),
        "split_unit_overlap_count": len(straddling),
        "split_unit_overlap_studies": straddling,
        "cohorts_without_publication_accession": unidentified,
        "training_cohorts": sum(value == "training" for value in splits.values()),
        "calibration_cohorts": sum(value == "calibration" for value in splits.values()),
        "test_cohorts_total_denominator": int(len(frame)),
        "test_cohorts_with_reference": int(len(available)),
        "missing_reference_count": int((~frame["available"]).sum()) if len(frame) else 0,
        # Gate 2 of the comparability amendment: two refusals, never summed. A test cohort
        # whose group holds no training pool is one a wider corpus would fix; one whose
        # reference was measured over different concentrations is not, and reporting them
        # as a single number hides which of the two the corpus is short of.
        "refused_no_reference_at_all": (
            int(frame.get("no_reference", pd.Series(dtype=bool)).fillna(False).sum())
            if len(frame) else 0),
        "refused_reference_not_comparable": (
            int(frame.get("no_comparable_reference", pd.Series(dtype=bool)).fillna(False).sum())
            if len(frame) else 0),
        "coverage_all_test_denominator": float(frame["covered"].mean()) if len(frame) else None,
        "coverage_with_reference": float(available["covered"].mean()) if len(available) else None,
        "global_calibration_scores": len(global_scores),
        "group_specific_radius_count": int(
            sum(not bool(item["fallback_used"]) for item in manifests.values())
        ),
        "global_fallback_radius_count": int(
            sum(bool(item["fallback_used"]) for item in manifests.values())
        ),
        "negative_control_pairs": int(len(negative)),
        # Both sides of the control are this score, not a raw transport distance.
        "negative_control_score": score if require_comparable else "distance",
        "negative_control_transport_pairs": int(transport_control["negative_transport"].notna().sum())
        if len(transport_control) else 0,
        "negative_control_transport_increase_rate": (
            float(transport_control["negative_transport_increased"].mean())
            if len(transport_control) else None
        ),
        "median_matched_transport": (
            float(transport_control["matched_transport"].median())
            if len(transport_control) else None
        ),
        "median_negative_transport": (
            float(transport_control["negative_transport"].median())
            if len(transport_control) else None
        ),
        "negative_control_distance_increase_rate": (
            float(negative["negative_distance_increased"].mean()) if len(negative) else None
        ),
        "median_matched_distance": (
            float(available["matched_distance"].median()) if len(available) else None
        ),
        "median_negative_distance": (
            float(negative["negative_distance"].median()) if len(negative) else None
        ),
        "transport_warning_rule": (
            "Warn when the prespecified mismatched distance exceeds the matched distance; "
            "never expand a radius after inspecting the test cohort."
        ),
    }
    return frame, summary, manifest_rows


def summarise(records: pd.DataFrame) -> dict[str, Any]:
    summaries = {}
    for source, group in records.groupby("source"):
        available = group[group["available"]]
        source_summary = {
            "records_total_denominator": int(len(group)),
            "records_available": int(len(available)),
            "optimisation_or_reference_failures": int((~group["available"]).sum()),
            "sharp_coverage_all_denominator": float(group["covered"].mean()),
            "sharp_coverage_available": (
                float(available["covered"].mean()) if len(available) else None
            ),
            "certificate_success_available": (
                float(available["certificate_ok"].mean()) if len(available) else None
            ),
            "mean_width_available": (
                float(available["width"].mean()) if len(available) else None
            ),
            "median_width_available": (
                float(available["width"].median()) if len(available) else None
            ),
            "median_midpoint_absolute_error_available": (
                float(available["midpoint_absolute_error"].median())
                if len(available)
                else None
            ),
        }
        by_method = []
        for (method, standard), method_group in group.groupby(["method", "standard"]):
            method_available = method_group[method_group["available"]]
            by_method.append(
                {
                    "method": method,
                    "standard": standard,
                    "records_total": int(len(method_group)),
                    "failures": int((~method_group["available"]).sum()),
                    "coverage_all_denominator": float(method_group["covered"].mean()),
                    "mean_width_available": (
                        float(method_available["width"].mean())
                        if len(method_available)
                        else None
                    ),
                }
            )
        worst = (
            available.groupby(["species", "drug", "method"], as_index=False)
            .agg(mean_width=("width", "mean"), records=("width", "size"))
            .sort_values(["mean_width", "records"], ascending=[False, False])
            .head(10)
            .to_dict(orient="records")
        )
        source_summary["by_method_and_standard"] = by_method
        source_summary["worst_width_groups"] = worst
        summaries[source] = source_summary
    return summaries


def block_bootstrap(records: pd.DataFrame) -> dict[str, Any]:
    rng = np.random.default_rng(RANDOM_SEED)
    output = {}
    for source, group in records[records["available"]].groupby("source"):
        blocks = (
            group.groupby("block_id")
            .agg(sum_width=("width", "sum"), count=("width", "size"))
            .reset_index()
        )
        values = []
        if len(blocks):
            for _ in range(BOOTSTRAP_REPETITIONS):
                indices = rng.integers(0, len(blocks), len(blocks))
                sampled = blocks.iloc[indices]
                values.append(float(sampled["sum_width"].sum() / sampled["count"].sum()))
        output[source] = {
            "block_definition": "study-country-year; all species and drugs retained within a block",
            "blocks": int(len(blocks)),
            "repetitions": BOOTSTRAP_REPETITIONS,
            "mean_width": float(group["width"].mean()),
            "percentile_95_interval": (
                [float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975))]
                if values
                else None
            ),
        }
    return output


def influence_analysis(records: pd.DataFrame) -> dict[str, Any]:
    output = {}
    available = records[records["available"]]
    for source, group in available.groupby("source"):
        global_mean = float(group["width"].mean())
        source_result = {"global_mean_width": global_mean}
        for dimension in ("species", "drug"):
            rows = []
            for value in group[dimension].unique():
                retained = group[group[dimension] != value]
                if len(retained) == 0:
                    continue
                mean = float(retained["width"].mean())
                rows.append(
                    {
                        "left_out": str(value),
                        "records_removed": int((group[dimension] == value).sum()),
                        "mean_width_after_exclusion": mean,
                        "change_from_global": mean - global_mean,
                    }
                )
            source_result[f"leave_one_{dimension}_out"] = sorted(
                rows, key=lambda item: abs(item["change_from_global"]), reverse=True
            )[:25]
        output[source] = source_result
    return output


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    cdc, cdc_audit = load_cdc()
    ebi, ebi_audit = load_ebi()
    eucast, eucast_audit = load_eucast()
    cohorts = [*cdc, *ebi, *eucast]
    records, certificates = evaluate_cohorts(cohorts)
    records.to_csv(RESULTS / "external_validation_records.csv", index=False)
    with (RESULTS / "external_validation_certificates.jsonl").open(
        "w", encoding="utf-8"
    ) as handle:
        for item in certificates:
            handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")

    # The allocation is solved, not hashed: whole exchangeable units are assigned to
    # maximise the number of units behind the radius under floors no released quantity may
    # fall below. Imported here rather than at module scope because the audit module
    # imports this one. The gates and the ladder live there so that one file decides them.
    import run_stage0_unit_audit as unit_audit

    shape = unit_audit.structure(cohorts, require_comparable=True)
    assignment = None
    for floor in unit_audit.CALIBRATION_FLOORS:
        assignment, solver_report = unit_audit.solve(
            shape, floor, unit_audit.TEST_FLOOR, unit_audit.TEST_UNIT_FLOOR,
            unit_audit.TEST_TOTAL_FLOOR)
        if assignment is not None:
            break
    if assignment is None:
        raise RuntimeError(f"no allocation clears the Stage 0 gates: {solver_report}")

    conformal_records, conformal_summary, manifests = conformal_external_validation(
        cohorts, ebi_audit["sha256"], assignment=assignment
    )
    conformal_records.to_csv(RESULTS / "external_conformal_records.csv", index=False)
    pd.DataFrame(conformal_summary.pop("calibration_score_rows")).to_csv(
        RESULTS / "external_calibration_scores.csv", index=False)
    write_json(RESULTS / "wasserstein_calibration_manifests.json", manifests)
    quality = {
        "prespecified_filters": {
            "minimum_cohort_n": MIN_N,
            "minimum_numeric_mic_categories": MIN_CATEGORIES,
            "ebi_units": "mg/L only",
            "ebi_methods": ["broth dilution", "agar dilution", "E-test"],
            "ebi_standard": "required and used in homogeneous cohort key",
            "eucast_role": "information-loss benchmark only",
        },
        "CDC Reference AST": cdc_audit,
        "EMBL-EBI AMR Portal 2026-07": ebi_audit,
        "EUCAST aggregated MIC website": eucast_audit,
    }
    summary = {
        "analysis_version": "1.0",
        "source_results_not_pooled": True,
        "method_selected_before_external_test": True,
        "no_favourable_mae_release_threshold": True,
        "cohorts": {
            source: int(sum(item.source == source for item in cohorts))
            for source in sorted({item.source for item in cohorts})
        },
        "sharp_identification": summarise(records),
        "block_bootstrap": block_bootstrap(records),
        "influence_analysis": influence_analysis(records),
        "conformal_new_cohort": conformal_summary,
        "certificates_written": len(certificates),
    }
    write_json(RESULTS / "external_data_quality.json", quality)
    write_json(RESULTS / "external_validation_summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
