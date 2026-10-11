# Prepare calibration from complete category counts

`calibration-prepare` turns complete category histograms and an independently specified roster into a calibration manifest and a `calibrations.json` file for `batch --calibrations`. It saves an HTML report, cohort and unit scores, every scored cut, input and output hashes, and explicit refusals. The software version remains 1.0.0.

The default uses a uniform reference on each explicit panel and emits manifest 1.2. Both default and trained modes project using ceiling MIC50/MIC90 without extrema, cover all internal recorded panel tails, and take a maximum over every planned cohort and cut within a unit. Target outcomes are never preparation inputs.

## Learn a reference and panel scales

Add `--reference-method training --transport-scaling training` and include separate `training` units in the roster. Each training unit must provide complete histograms on the same panels as the calibration units. At least two training units are required. Their pooled counts give one reference per panel. Leave-one-training-unit-out scores determine positive panel scales, with a floor of the smallest log2 panel step divided by the smallest training sample size. Calibration scores are divided by these scales before taking the unit maximum.

The resulting manifest 1.3 records the normalized radius, panel scales, geometry hashes and training labels. The report gives the physical radius used on each panel: normalized radius multiplied by its scale. The training data, calibration data and target data have separate roles. No target histogram is needed to generate or apply the mapping. With `--reference-method training` alone, the pooled reference uses the existing unscaled manifest 1.2 contract.

[Run the complete synthetic example](../examples/trained_calibration/README.md). Its three calibration units support 75%, which is used only to keep the example small. Nineteen exchangeable calibration units are needed for a finite nominal 95% rank. Neither number establishes useful precision or biological independence. Fix the method before evaluating it on fresh units; choosing a method from test outcomes requires a separate evaluation.

Training diagnostics, learned scales and all calibration scores are saved in `preparation.json`; references and settings also have separate exports. An incomplete training unit, overlapping role, mismatched panel or nonfinite score prevents a usable manifest and produces a refusal explaining the requested method.

## Inputs

Prepare four files before inspecting calibration scores. Keep the roster and the selection rule independent of outcome availability and observed scores.

| File | Required content |
| --- | --- |
| `counts.csv` | `cohort_id,panel_id,category,count,rank_convention`; calibration cohorts only; one row for every panel category, including zeros; `rank_convention=ceiling` |
| `panels.csv` | Existing explicit panel format: `panel_id,unit,category,lower,upper,lower_closed,upper_closed,panel_value` |
| `roster.csv` | Exactly `unit_id,cohort_id,panel_id,role`; each cohort appears once; `role` is `calibration` or `target` |
| `metadata.json` | Explicit protocol, source and selection declarations described below |

Every unit must contain exactly one cohort on each prespecified panel, with the same panel set in calibration and target units. Cohort IDs are globally unique. A unit cannot appear in both roles. This bounded interface does not accept multiple cohorts on the same panel within one unit. It cannot infer that differently named units are independent or that their cohort definitions are comparable; resolve dependence and define the eligible units before preparing the files.

The denominator is the sum of the complete category counts for each cohort. An optional `original_n` column is strongly useful for checking extraction: when present it must be supplied on every category row, agree throughout the cohort and equal that sum. Counts must be finite, exact nonnegative integers, and each cohort needs at least two observations. This is a technical minimum. Missing categories, even zero categories, are refused. The procedure never drops censored categories, changes their bounds, infers a panel from observed extrema or pools different panels.

Metadata is a JSON object containing exactly these keys:

```json
{
  "protocol_label": "MY-PROSPECTIVE-PROTOCOL-v1",
  "unit_definition": "One independently sampled study, including every eligible cohort",
  "cohort_selection_rule": "One prespecified cohort on each of P1 and P2 per study",
  "roster_provenance": "Location and date of the independent study/cohort register",
  "counts_provenance": "Source, extraction method and completeness checks for calibration counts",
  "grouping": {"population": "Explicit intended study population"},
  "panel_provenance": {
    "P1": "Independent source of P1 categories, censoring bounds and recorded values",
    "P2": "Independent source of P2 categories, censoring bounds and recorded values"
  }
}
```

Replace the example descriptions with real provenance. `grouping` must be a nonempty object of nonempty string labels. Every used panel needs provenance. Duplicate JSON keys, nonfinite JSON constants, unknown metadata fields, blank identifiers and surrounding identifier whitespace are refused. These declarations remain user-supplied evidence; a hash or a filled field does not establish their truth.

## Run preparation, then apply to future summaries

```console
mic-50-90 calibration-prepare counts.csv --panels panels.csv --roster roster.csv --metadata metadata.json --level 0.95 --output-dir prepared-calibration
mic-50-90 batch future-summaries.csv --panels panels.csv --targets prepared-calibration/targets.csv --calibrations prepared-calibration/calibrations.json --output-dir future-report
```

The preparation command accepts `--delimiter comma`, `semicolon` or `tab` for all CSV inputs. Outputs use comma-separated CSV. Preparation returns status 0 when ready and 2 when unavailable. It does not silently reduce the requested level or choose a fallback.

The later batch command receives only target summaries, explicit panels, the generated recorded-tail targets and the calibration mapping. Its summaries must use ceiling MIC50/MIC90 without a minimum or maximum. The prepared target mapping contains only cohorts in the target roster; new panels or additional target cohorts require a new prespecified roster and compatible preparation. The generated targets cover all internal cut vectors. A numerical threshold is the same recorded-tail functional when it induces the same panel-category indicator vector.

For a runnable three-unit teaching example, use `examples/calibration_preparation/README.md`. Its 0.75 level is chosen for a small, hand-checkable demonstration and is not an empirical performance claim.

## What is scored

For each calibration cohort, the existing count parser preserves the category histogram and generates ceiling MIC50/MIC90. The uniform distribution is projected into that summary's sharp set. At each of the panel's `k-1` internal cuts, an independent transport linear program finds the minimum radius needed to include the true recorded tail in the reported interval. The existing critical-radius routine separately checks the simultaneous score. Both values are retained and must agree within `2e-6` log2 dilution steps; the larger numerical solution is used. The core bisection has 24 steps, so a mathematical zero can appear as a tiny positive score.

The cohort score is the maximum over cuts. The unit score is the maximum over every rostered cohort in that unit. The conformal rank counts units, with rank `ceil((m+1)*level)`. The manifest records the fixed-rank marginal level `rank/(m+1)` and the requested level separately. At least 9, 19 or 99 calibration units are needed for finite 90%, 95% or 99% ranks. Those counts alone do not establish exchangeability, independence, coverage on new data or a PAC guarantee.

The event is simultaneous coverage of the declared recorded-tail intervals for every eligible cohort in a new exchangeable unit, under the same fixed reference, summary and selection procedure. It is not a statement that a whole distribution is inside a Wasserstein ball, a latent-MIC guarantee, or conditional coverage for each individual study. An independent later audit is required to measure held-out performance.

## Refusals preserve the planned denominator

If any expected calibration cohort is missing, incomplete, invalid or fails numerical scoring, the whole preparation becomes unavailable. The expected number of units and cohorts stays visible. Successful diagnostic scores already computed are retained, but the procedure writes `manifest.json` as `null` and `calibrations.json` as `{}`. No zero, infinity, deleted unit or data-dependent replacement is inserted into a conformal rank.

Other refusals include duplicate roster or category rows, overlapping roles, incompatible unit compositions, absent panel definitions or provenance, target outcomes in the counts input, unplanned count cohorts, unsupported levels and input files changing during scoring. Correct an extraction or metadata error against the independently fixed source; do not edit the roster after seeing scores to manufacture a more favourable result.

## Retained artifacts and bindings

`preparation.json` retains full calibration histograms, generated summaries, projected references, per-cut scores, unit accounting, the roster, configuration and refusals. The CSV score files make those quantities easy to inspect. `targets.csv` is machine input and preserves exact IDs; diagnostic CSV exports neutralise spreadsheet formulas. Exact IDs remain available in JSON.

`configuration.json` records explicit panel geometry including censoring, unit composition, metadata, requested level, numerical settings and SHA-256 hashes of all input files. `artifact-hashes.json` records the saved output hashes. `manifest.json` additionally binds the normalized full roster, panel composition, configuration, uniform references, scores and individual target bindings. Frozen experimental protocols, prior result directories and release archives are not modified by this workflow.

Each target mapping includes a `preparation_binding` with its cohort, unit and panel IDs, panel geometry hash, reference hash, protocol, roster hash, composition hash and permitted recorded-tail vectors. The batch integration checks these against the actual target input and manifest. The binding is a consistency check on the declared inputs and calibration scope; it is not authentication or independent verification of the sources. The canonical hash uses UTF-8 JSON with sorted keys, no insignificant whitespace, unescaped Unicode and finite values only.

Python callers can use `prepare_calibration(counts_path, panels_path=..., roster_path=..., metadata_path=..., level=0.95)`. The returned dictionary has `status`, `manifest`, `calibrations`, `configuration`, `summary`, `roster`, `references`, `targets`, `cohort_scores`, `unit_scores` and `refusals`. An unavailable result must not be treated as a successful calibration.
