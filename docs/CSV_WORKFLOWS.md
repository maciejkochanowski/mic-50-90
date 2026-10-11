# CSV workflows

Install the release with Python 3.11–3.13. Templates are in examples/csv. These commands run the researcher, laboratory and controlled calibration examples:

```text
mic-50-90 batch examples/csv/summaries.csv --panels examples/csv/panels.csv --targets examples/csv/targets.csv --output-dir output/researcher
mic-50-90 reporting-audit examples/csv/counts.csv --panels examples/csv/panels.csv --targets examples/csv/targets.csv --output-dir output/laboratory
mic-50-90 batch examples/csv/summaries-calibrated.csv --panels examples/csv/panels.csv --targets examples/csv/targets.csv --calibrations examples/csv/calibrations.json --output-dir output/calibrated
```

The calibration example is synthetic and explains the interface. Its radius is not validated for a real cohort.

Open report.html in the chosen output directory. results.csv is the flat result table; fractions range from zero to one, whereas HTML displays percentages. results.json retains all witnesses and configuration.json records normalized inputs and source hashes. A row with status refused contains no numerical result and explains what to correct. Batch exit code zero means the files were processed, not that every cohort produced a result; inspect status and the reported denominators.

## Inputs

All files use UTF-8 (an optional byte-order mark is accepted) and a header. Commas are the default separator. For spreadsheet exports, add --delimiter semicolon or --delimiter tab; use the selected separator throughout the input tables, including optional returned counts and decision queries. Numeric fields use a decimal point. Quoted fields can contain separators. Output results.csv always uses commas. IDs are exact, case-sensitive joins. Surrounding spaces in cohort, panel, variant or unit identifiers are rejected with a file and row reference. Do not reuse one cohort_id for different samples. Discrete fields must be exact integers no larger than 9,007,199,254,740,991; integral decimal and exponent forms such as 20.0 and 2e1 are accepted. Fractional tokens are rejected before conversion to floating point.

| File | Required contents |
|---|---|
| summaries.csv | One row per cohort and variant. cohort_id, panel_id, variant_id (exactly one primary), n, mic50, mic90, rank_convention. For explicit ranks also rank50 and rank90. Optional minimum/maximum. |
| counts.csv | One row per category and cohort: cohort_id, panel_id, category, count, rank_convention=ceiling. Include zero-count categories explicitly. |
| panels.csv | One row per ordered category: panel_id, unit, category, lower, upper, lower_closed, upper_closed, panel_value. Blank endpoint means unbounded. Closure fields must say true or false. |
| targets.csv | cohort_id, threshold, unit. Optional decision_operator and decision_fraction must occur together. These are strictly greater-than MIC questions, not inferred clinical breakpoints. |
| Optional decision-queries.csv | Exactly cohort_id, threshold, unit, cost. With --decision-plan, restrict permitted recorded-tail queries and give each a positive price in a common acquisition unit. |

mg/L and ug/mL are equivalent accepted units. No other conversion is guessed. Category labels in summaries and counts must exactly match their panel. The panel_value is the declared representative for the recorded-category estimand; interval endpoints define the latent estimand. An open upper category therefore still needs an explicit recorded representative.

rank_convention=ceiling means rank=ceil(probability*n); explicit requires both integer ranks. Unknown convention is not silently filled in. To examine documented alternative conventions, provide another complete summary row with the same cohort_id and a distinct variant_id. The result spans their union and does not assign them probabilities.

Set iid=true only when iid sampling is a defensible assumption for source-population inference. confidence_level defaults to 0.95; across multiple thresholds the displayed population intervals use Bonferroni adjustment. With iid=false or omitted, the population layer explains its unavailability. This does not prevent finite-sample analysis.

## Additional counts

The interval-width search permits direct target counts. --exclude-direct-targets explicitly restricts them. --question-time-limit defaults to 10 seconds per cohort; the search checks its budget between candidate answers. An individual solver call may finish after the budget. Incomplete search preserves basic bounds, but does not recommend a best question or claim an optimum. This width objective never recommends zero-width-gain questions. It uses the sum of widths over requested recorded-tail questions, per supplied acquisition cost in the JSON API.

The laboratory audit compares summaries, one recommended count, all target counts and the full category histogram. Guaranteed gain uses the worst feasible answer. Observed gain uses the actual histogram and is reported separately. A full histogram does not resolve latent MIC inside censored categories.

## Counts needed to settle explicit criteria

Add `--decision-plan` to `batch` or `reporting-audit` when targets.csv includes explicit criterion pairs. The planner minimizes the greatest total acquisition cost until every declared recorded-sample criterion is supported or contradicted. It has a separate report section from interval-width rankings.

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/targets.csv --decision-plan --output-dir output/decision-plan
```

Without a query file all internal cuts cost one. Add `--decision-queries decision-queries.csv` to restrict them and assign positive costs. A cohort missing from this supplied whitelist has no allowed counts. Equivalent cuts cannot have duplicate prices. `--exclude-direct-targets` also applies to this planner and can make resolution impossible. `--decision-plan-time-limit` defaults to 5 seconds and `--decision-plan-max-states` to 5000. A limit produces incomplete with a verified fixed-plan bound when available; it does not prove impossibility or optimality.

Use `--additional-counts` to enter each truthful answer from the original sample, retaining every previous answer and the original n. Stop when all declared sample criteria are definite. This stopping rule does not settle population or calibrated decisions. Malformed optional query files, invalid planner settings or absent explicit criteria leave valid base results available and explain why the planner is unavailable. Required-file preflight is unchanged.

The compact CSV includes planner status, scope, cost and next question. JSON retains the complete policy, exact rational costs and any pair of indistinguishable histograms. The fixed-plan cost is a sufficient baseline; it is minimal only when its optimality flag is true. [Decision planning](DECISION_PLANNING.md) explains statuses, and the [worked example](../examples/decision_planning/README.md) demonstrates two requests instead of three and an unequal-cost case.

## Calibration

calibrate-wasserstein accepts explicit score and unit arrays plus calibration_contract; the example calibration-scores.json documents the fields. New guarantees require manifest 1.2 or 1.3, matching reference_protocol and grouping in calibration_context, unit=mg/L and a matching summary policy. Legacy manifests must be regenerated from the original scores after confirming their semantics; editing only manifest_version is invalid. A user-specified radius without a valid manifest remains an assumption scenario.

Three guarantees answer different questions: the actual sample, an iid source population, and a new exchangeable study unit. They are not interchangeable and do not identify clinical susceptibility without additional justified information.

## A question with a numerical criterion

For example, `cohort_id=C, threshold=4, unit=mg/L, decision_operator=<, decision_fraction=0.05` asks whether the fraction of recorded MIC values strictly above 4 mg/L is less than 5%. The operators `<`, `<=`, `>` and `>=` are accepted. Enter 0.05, not 5. Both optional fields must be supplied together; leaving both blank keeps the ordinary interval report.

The opening section shows the denominator, threshold, criterion and three separate answers. **Supported** means every value in the applicable result set satisfies the criterion; **contradicted** means none does; **undetermined** means both answers remain compatible; **unavailable** means that layer did not provide a valid set. Population and calibration decisions retain their stated probabilistic guarantee and assumptions. They are not statements of certainty. Decisions use unrounded endpoints across all declared variants; sample comparisons use integer counts divided by n. A displayed percentage rounded to 10.0% can therefore still exceed a 10% criterion.

Optional summary columns `source_doi`, `source_location`, `metadata_basis`, `rank_basis` and `panel_basis` record where inputs came from. Their values must agree across a cohort's variants. The report and configuration preserve these fields. Distinguish a source-established reporting convention from an analyst-declared sensitivity analysis. The preflight lists all missing required fields that can be identified together; it does not guess an assay panel from observed values.

An absent join identifier in a required table prevents assigning a row to a cohort or panel. In that case preflight reports row-numbered missing fields and stops before analysis. Correct these file-level errors and rerun. Other invalid cohort inputs receive individual refusals in the report. A population numerical failure makes that layer unavailable while preserving completed sample bounds and any valid calibration result. Optional decision-query input failures affect only that planner.

## Published-summary examples

Run the three original-summary examples without any histogram input:

```text
mic-50-90 batch examples/published_summaries/summaries.csv --panels examples/published_summaries/panels.csv --targets examples/published_summaries/targets.csv --output-dir output/published-summaries
```

The accompanying README explains the human and veterinary examples and their source/assumption distinctions. The `published_table` example is a separate demonstration of compressing a complete histogram.

The paired MIC50/MIC90 workflow requires n >= 2 and valid ordered ranks. This technical minimum does not guarantee narrow bounds, adequate population precision or suitability for a scientific decision. There is no universal minimum useful n; the precision a given n supports depends on the report and the question.

## Installation and automated processing

Use mic-50-90 --version to identify the installed package. The equivalent module invocation is python -m mic_50_90; this is useful if the console command is not on the system path.

For automated runs, add --fail-on-refusal. The program writes the complete reports and returns status 2 if any cohort is refused. Successful cohorts remain available. Without this switch, status 0 indicates that the files were processed, including any recorded refusals. An unavailable population, calibration or decision-planning result alone does not count as a refused cohort. Required-file errors still stop the command with status 2. Choose a separate output directory for each analysis you want to retain; the command writes fixed filenames there.

The historical external calibration evaluation used common-range histograms. It does not establish performance for a user possessing only original summaries. The revision's stricter audit found no eligible cohorts among 871 retained EBI cohorts because independently documented tested panels were unavailable; 871 refusals are retained. Calibration remains a conditional capability requiring suitable reference and calibration data, not a generally validated shortcut.

## Further information and large reports

Use [returned counts](RETURNED_COUNTS.md) with batch --additional-counts to enter exact aggregate answers from the original sample. [Calibration preparation](CALIBRATION_PREPARATION.md) generates manifest and target mapping files from a complete independent calibration roster. [Large reports](LARGE_REPORTS.md) use fifty cohorts per page by default; --report-page-size 0 keeps one file.

## Request several counts together

The optional `--acquisition-plan` workflow compares one export with successive requests and provides a CSV to enter the answers. Counts come from existing records, not new susceptibility tests. See [the practical guide](ACQUIRING_COUNTS.md).


## Read component sets and guarantee columns

`results.csv` contains lower/upper endpoint columns and `sample_count_components`, `latent_count_components` and `population_confidence_components`. Optional-layer columns appear when that layer supplies results. Each component cell contains a JSON array of interval pairs. Sample and latent component endpoints are counts; population confidence components are fractions. Parse these arrays to preserve gaps between reporting interpretations. The extreme endpoint columns alone give the hull and must not be interpreted as making every intermediate count or probability feasible. HTML shows the unions and explains integer spacing for sample counts.

Calibration rows also include `conformal_guarantee_class`, `conformal_confidence_level` and `conformal_scope`. Their level refers to the calibrated event, separately from the iid population level. Exact decimal or rational criteria retain their precise meaning in the report; displayed rounding must not redefine a strict decision boundary. Returned-count before/after tables label extreme bounds explicitly.

Code reading CSV by column name should select the fields it needs. Spreadsheet text fields are escaped as text; JSON retains the original strings. The separate whole-distribution command writes `distribution.csv`, whose component and calibration fields are described in [the distribution guide](distribution-user-guide.md).


## Source comparison signs and counts-only questions

An additional-count table can include `relation` (`>`, `<=`, `>=`, `<`) and
the optional `source_scale`:

- `recorded` compares the declared recorded category values with the threshold.
- `interval` applies the comparison to whole measurement intervals. A count
  whose boundary cuts an interval requires a finer source statement.
- An omitted or empty scale preserves the saved input's interpretation.

An omitted relation means strictly greater than. Exact, ranged and rounded
counts retain their original denominator; percentage conversion precedes any
complement. The form defaults new counts to recorded categories and previews
the selected labels. A question's `target_scale` is independent of the meaning
of its input counts. For example, an exact count in category ≤4 can support a
question about MIC >2 while preserving uncertainty within that category.

The `distribution --targets questions.csv` option evaluates the same explicit
criteria without requiring MIC50/MIC90 when other supplied counts are sufficient.
The question table keeps `decision_fraction` on the 0–1 scale. The guided table
workspace reads these same CSV schemas, or tab-separated text pasted from Excel,
with an explicit delimiter for each table. It does not evaluate spreadsheet
formulas. Structural preview precedes analysis; invalid identifiable cohorts are
retained as refusals alongside valid results.


## Measurement intervals and incomplete counts

Distribution questions optionally accept `target_scale`: `recorded` (default) or `interval`. The latter asks about MIC within the measured intervals. For eight of fifty results recorded as >32 mg/L, the sample count above 32 is eight, whereas the count above 64 can be zero to eight. Whole-category counts cannot resolve that ambiguity. The threshold-only reporting planners retain recorded-category semantics and refuse an interval-scale request rather than change its meaning.

Use `count_min` and `count_max` for suppressed counts. Fewer than five isolates means 0–4; at least five of fifty means 5–50. The Windows form supplies a conversion control and retains the original statement in `source_information`. This is different from MIC measurement censoring. Blank fields are not zeros.

A percentage without its rounding rule or decimal precision is reported as unused in the distribution workflow. Other valid information remains available; malformed percentages, inconsistent denominators and contradictory usable counts are still rejected. Original statements remain in the saved configuration and input-information warnings.

Examples: `examples/biological_cases/chloramphenicol-67-censored.json` and `chloramphenicol-67-rounding-unknown.json`. The English user guide and biological case-study PDF show their interpretation. For population inference, definite and possible category contributions project the same simultaneous confidence region, without another test or an imputed concentration.
