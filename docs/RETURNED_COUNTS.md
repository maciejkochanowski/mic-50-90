# Using a count obtained after the first analysis

MIC-50-90 1.0.0 accepts truthful aggregate counts from the same original collection. Use this when a source table, laboratory or author supplies the count recommended in your first report. This does not require a complete histogram.

```text
mic-50-90 batch examples/returned_counts/summaries.csv --panels examples/returned_counts/panels.csv --targets examples/returned_counts/targets.csv --additional-counts examples/returned_counts/additional-counts.csv --output-dir output/returned-counts
```

The example uses an existing published histogram compressed to MIC50/MIC90. Its 2902 observations originally permit 0–290 recorded MIC values above 0.5 mg/L. The separately entered count of 85 gives exactly 85/2902 (2.93%), supporting the sample criterion <5%. It demonstrates recovering information after compression, not an independent application to original published summaries.

## Input

| Field | Meaning |
|---|---|
| cohort_id | Exact identifier in the summary file |
| threshold | Positive concentration; the count uses recorded panel values strictly greater than this value |
| unit | mg/L or the equivalent ug/mL |
| count | Exact integer from zero through n; leave blank when entering an interval or percentage |
| count_min, count_max | Inclusive integer range, with both endpoints supplied |
| percentage, decimal_places, rounding_rule | Printed percentage on the 0–100 scale, number of decimal places (0–6), and explicit rounding rule |
| n | Original denominator; must match the summary |
| source | Optional description of where this count was obtained |

Supply exactly one of the three forms in each row: `count`; both `count_min` and `count_max`; or all three percentage fields. Blank unused columns are allowed. Rounding rules are `half_up` (ties upward), `half_even` (ties to an even last digit), `floor` (downward) and `ceiling` (upward). Do not guess a paper's rounding rule. If it is unavailable, obtain an exact count or a defensible integer range. A range is retained in full; its midpoint is never substituted.

For example, 12% of 200 isolates rounded to an integer by `half_up` permits 23 or 24 isolates. Under `half_even` it also permits 25. The rule can therefore change a conclusion near 12.5%. The executable [laboratory examples](../examples/laboratory_use/README.md) show the first rule and an explicit count range.

Every row is an additional constraint. To add a second answer, retain the first row and rerun from the original summaries with both rows. An earlier range may accompany a later exact answer at the same threshold; both must hold. Duplicate equivalent exact counts are rejected. Counts can be chosen after seeing previous answers. Keep the original panel, denominator, cohort definition, target family and reporting variants. A count on a new sample or a latent-MIC interpretation does not meet this contract. Cohorts without a count retain their original analysis; unmatched cohort identifiers are reported as refusals. Missing join identifiers stop preflight. Surrounding spaces are rejected; a count for ` example ` cannot be assigned to `example`.

When answers contradict the summaries, the report identifies a conflicting subset and asks the user to check the original sample, denominator and strict `>` definition. A completed deletion check gives an irreducible subset conditional on the summaries, not necessarily the smallest subset. No input is changed. An unresolved sample decision instead shows two compatible hypothetical histograms giving opposite answers; these are explanations, not reconstructed observations.

The report shows entered counts and sources, before/after sample intervals and the observed gain. Its recommendation concerns the next count. The JSON contains every witness and rejected reporting variant; the CSV contains status and observed gain. No independence between sequential queries is required for deterministic sample identification.

## Calibration and population guarantees

The calibrated update preserves the original bands, reference and radius. It intersects the integer histogram set with those bands and all returned counts. This retains the original simultaneous coverage event when the counts are truthful. It does not claim coverage conditional on a particular answer. If the sample constraints remain feasible but conflict with calibration, the sample result is displayed and calibration is unavailable. That conflict is not a successful calibration outcome.

For fixed population targets, the optional iid layer recomputes the union of exact binomial intervals and its original Bonferroni adjustment. Adaptive acquisition of truthful counts does not justify changing the target family after seeing results. Assumption-only transport scenarios remain uncalibrated.

The update keeps the original calibrated event; tests/test_count_updates.py contains controls for incompatible restrictions of a tail-calibrated transport ball. The numerical count allowance is max(1e-7, 8*n*machine_epsilon); it is stored with the original bands. It is an engineering tolerance, not a certified bound on solver error.

The Python entry point is `analyse_with_counts(raw_spec, additional_counts, *, iid=False, confidence=0.95, calibration=None)`. It takes an empirical JSON specification and count dictionaries without cohort_id. Input objects remain unchanged. A numerical failure in optional count refinement leaves the original results visible with an explicit unavailable status.

`counts_from_percentage(percentage, n=..., decimal_places=..., rounding_rule=...)` returns the exact integer endpoints independently of an analysis. Explicit rounding creates an information constraint; it does not create a confidence interval or remove sampling uncertainty.
