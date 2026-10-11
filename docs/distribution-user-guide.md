# Describe a MIC distribution from summaries and counts



MIC-50-90 1.0.0 describes the MIC categories supported by the information you supply. It does not fill in a plausible histogram or create isolate records.



The `distribution` command answers: **What fractions of the original isolates can occupy each recorded MIC category, and how uncertain are the corresponding population proportions?**



## Start with a prepared example



Install MIC-50-90, then run these commands from the directory containing the supplied examples:



```console

mic-50-90 distribution examples/distribution/summaries.json --output-dir results/summaries

mic-50-90 distribution examples/distribution/supplemented.json --output-dir results/supplemented

```



Open `report.html` in either output directory. The second input adds two counts from the same controlled sample of 20 isolates. It identifies the category counts as 12, 6 and 2. The first report contains only MIC50 and MIC90, so several category histograms remain possible. The example assumes ceiling ranks explicitly; it does not establish that convention for any publication.



Each output directory contains:



- `report.html`: the question, denominator, supplied summaries, distribution ranges, assumptions and unavailable results.

- `distribution.csv`: the numerical ranges for each category and each cumulative boundary. Fractions use the 0–1 scale; the HTML shows percentages.

- `results.json`: all layers, numerical status, retained and incompatible reporting variants, and the additional information used.

- `configuration.json`: the input records and analysis settings needed to repeat the calculation.



When alternative reporting conventions permit separated sets of counts, the HTML and chart preserve the gaps. In CSV, `count_components` contains those separate integer intervals; the lower and upper columns give their outer endpoints.



All input and output remain on your computer. The HTML is self-contained, works without a network connection and displays at most 50 cohorts per page. Without JavaScript it displays every cohort; printing includes all cohorts.



## Supply information from one original sample



A JSON input requires `n`, `unit` and an explicit `panel`, plus at least one summary, observed range or count. MIC units must be `mg/L` or equivalent `ug/mL`. Do not combine counts from different samples or denominators.



For a measured panel, use its actual categories, including censored categories. The `panel.levels` shorthand creates a left-censored first category, interval categories between levels, and a right-censored final category by default. The report describes these categories, not the unknown concentrations within them. Use explicit `panel.categories` when the source geometry differs.



MIC summaries are optional when counts already provide the relevant information. Every supplied quantile requires either an explicit `convention: "ceiling"` or its original integer `rank`. An unknown publication convention must not be entered as if the paper had verified it. Alternative declared interpretations can use the `reporting_envelope.variants` format.



`additional_counts` defaults to **recorded MIC strictly greater than `threshold`**. An explicit `relation` may be `>`, `<=`, `>=` or `<`; normalization preserves the original statement and denominator. Each item requires the original `n` and explicit `unit`, plus one of:



- `count`: an exact count.

- `count_min` and `count_max`: integer bounds on the count.

- `percentage`, `decimal_places` and `rounding_rule`: a rounded percentage. Rules are `half_up`, `half_even`, `floor` or `ceiling`; the percentage scale is 0–100.



Record the source in `source`. For 20 isolates with 12 results at or below 1 mg/L, supply `relation: "<="`, `count: 12`, and `n: 20`; the engine obtains eight strictly above. Rounded percentages are first converted to all compatible integers, then complemented. The operators `>=` and `<` are accepted only when the declared category geometry identifies the corresponding whole-category split. A threshold cutting an interval is refused rather than assigned from an arbitrary representative. Normalized output retains `source_relation`, `source_threshold` and `source_information`.



To update a report, retain earlier truthful counts and add the newly obtained count to the same input. The sample size, panel and target family must stay fixed. Conflicting counts are refused; the software does not discard them to produce a narrower answer.



To preserve the numerical population bounds from an earlier run as well, supply its output directory:



```console

mic-50-90 distribution examples/distribution/summaries.json --population-method joint-exact --output-dir results/before-counts

mic-50-90 distribution examples/distribution/supplemented.json --population-method joint-exact --previous-output results/before-counts --output-dir results/after-counts

```



The two supplied inputs identify the same controlled 20-isolate cohort. The updated input appends the recovered counts. `--previous-output` reads the previous JSON configuration and results, checks the original constraints, and intersects the new population outer bounds with the saved bounds. Even a shorter subsequent computation cannot widen the saved population result. Keep the previous output unchanged and write the update to a different directory.



Only the additional counts may change in a saved update. Retain earlier count rows in their original order, the denominator, panel, cohort identifier, quantile interpretations, iid declaration, confidence level and population method. A changed method or source cohort requires a separate analysis, not an update. Search time, numerical tolerance and the optional sample precision target may change. Invalid saved updates are refused; they are not silently treated as fresh analyses.



## Ask about an internal MIC group



In the Windows form, add a question and select **One or more adjacent MIC

categories**. Choose the first and last included categories. Select the same

category twice to ask about that category alone. The percentage criterion is

optional; for example, enter `10` for a 10% criterion. A censored endpoint remains

a whole category, not an assumed exact MIC value.



The JSON equivalent is:



```json

"targets": [{"start_category": "0.5", "end_category": "0.5", "unit": "mg/L",

             "decision_operator": "<", "decision_fraction": "0.15"}]

```



In the distribution question CSV, use `cohort_id,start_category,end_category,unit`

and the optional paired criterion columns. Leave `threshold` blank for these

rows. The first and last labels must occur in the panel. The CSV fraction remains

on the 0–1 scale. The result gives the number of original isolates, its percentage

and whether all compatible counts satisfy the criterion. Population conclusions

remain separate and require their stated sampling assumptions.



The `batch` and `reporting-audit` question planners retain their strict-tail

contract. Category-range questions belong to `distribution`; the theorem giving

at most two sufficient disclosures does not apply to arbitrary range questions.



## A published example without guessing the quantile convention



```console

mic-50-90 distribution examples/distribution/published-7133-counts.json --output-dir results/published-7133

```



Two verified counts in the [source publication](https://doi.org/10.3390/antibiotics12020289) give 1726/7133 above 0.06 mg/L and 143/7133 above 2 mg/L. The resulting three broad category counts are **5407, 1583 and 143**. These categories use the published count thresholds; they are not a reconstruction of the original complete laboratory panel. The final category's `panel_value` is an ordering representative, not an imputed MIC value.



This example leaves `iid` false. An observational publication does not, by itself, establish independent random sampling from the population of interest. The sample distribution remains available. Enabling population analysis requires a defensible sampling assumption, not simply changing an option to obtain another figure.



Four further [published-count examples](../examples/publication_review/README.md) show how to use exact counts from human and veterinary studies, including a 21-isolate sample with repeated observations from the same cows. Their default inputs use counts without guessing a quantile convention. Separate, explicitly conditional before/after inputs show what the additional counts contribute. A contradictory source example demonstrates when clarification is needed.



## Read the three layers separately



**Sample distribution.** Each displayed count range is sharp conditional on the declared information. A percentage refers to the original denominator. The ranges are projections of one constrained set: arbitrary combinations of displayed endpoints need not form a compatible histogram. For example, category maxima generally cannot all occur together.



**Population distribution.** Set `iid: true` only when independent and identically distributed sampling is appropriate for the intended population. `confidence_level` defaults to 0.95. All internal boundaries of the supplied panel form one simultaneous family, which must be fixed independently of the observed counts. Category bounds are obtained from the same joint region. Observed sample minima and maxima do not imply population zeros outside those observations.



**Calibration for a new study unit.** This layer requires an independently prepared, compatible reference and calibration manifest. The JSON input uses the `reference_distribution`, `wasserstein_calibration_manifest` and `calibration_context` fields. Whole-distribution reporting requires a manifest covering all panel tails. Counts-only inputs cannot bypass a manifest's MIC50/MIC90 summary policy. Missing or incompatible calibration is displayed as unavailable; it does not change the sample or population result. Prepared calibration must match the actual cohort identifier and, when supplied, panel identifier. The report and exports retain the achieved marginal calibration level, requested level, calibration-unit count and definition, event scope, reference, radius and assumptions. These describe the calibrated new-unit event, independently of the population confidence level. Saved updates retain the same calibration contract.



There is no general sample size at which the answer becomes scientifically useful. Counts-only inputs accept `n=1`; MIC50/MIC90 with distinct ranks need at least two observations and compatible ranks. Small samples usually give wide population ranges. Whether a range is useful depends on your question and required precision.



### Does this question need more computation?



For a declared population question, such as whether the proportion above a MIC

threshold is below 5%, the report distinguishes three situations:



- **Resolved:** the retained bounds support or contradict the criterion at the

  stated confidence level. Computing more decimal places is unnecessary for

  that answer, even when the global numerical precision target was not reached.

- **The confidence region crosses the target:** certified bounds show that

  both answers remain possible. Further computation for the same method and

  information cannot settle the question. Extra counts might help, but the

  program does not promise that they will.

- **Numerically unresolved:** the calculation has not established either of

  the above. A longer calculation may help; it may also confirm that the

  available information is insufficient under the selected method.



These explanations appear in the application, HTML report, `results.json` and

`decisions.csv`. They describe population inference under the displayed sampling

assumptions. They do not replace the separate answer about the observed isolates.

Numerical endpoint precision, statistical interval width and confidence level

are different quantities. A numerical tolerance of 0.01 percentage points is

not a biological accuracy requirement. Saved updates recompute the assessment

from the current information; an old inconclusive answer need not remain so

after a truthful additional count.



With `--population-method joint-exact`, declared questions also receive a

direct check of the opposite answer within the same confidence region. For

example, to establish that the population share is below 5%, the calculation

must exclude every compatible population distribution with a share of 5% or

more. Equality is included in that check. A completed check can settle the

question even if some displayed interval endpoints remain conservative.



This check uses at most half of the optional refinement budget; the remaining

time is available for the whole-distribution calculation. It does not change

the confidence level or replace the distribution plot. Its status, numerical

exclusion trace and data signature are retained in `results.json`. An

interrupted check remains unresolved. After additional counts, the check is

performed again using the updated constraints.



## Choose how detailed the sample description should be



If the individual categories are poorly known, ask for the most detailed contiguous grouping that the evidence supports at your required width:



```console

mic-50-90 distribution examples/distribution/summaries.json --precision-pp 10 --output-dir results/resolution

```



This controlled example supports two groups at a maximum width of 10 percentage points: 18–20 of the 20 isolates through the 2 mg/L category and 0–2 above it. The report retains the original, more uncertain category ranges as well.



`--precision-pp` is an absolute width requirement for **both** every grouped category share and every retained cumulative share. It is not a significance level, relative percentage improvement or population numerical tolerance. There is no default scientific precision target. Values range from 0 to 100; zero requires exact sample counts.



The algorithm evaluates all contiguous category intervals under every supplied reporting variant. It then selects the maximum number of acceptable groups. Equally detailed solutions use the earliest sequence of category boundaries. Interior interval-count constraints are retained in the Python API. A single group containing the entire sample always meets the criterion; if that is all the data support, the report shows one group rather than inventing finer detail.



This grouping answers what the observed sample supports. It does not turn a wide population confidence region into a precise population claim. The CSV exports the selected groups as `sample_resolution` rows, separately from the original categories.



## Choose the population construction

The population layer offers four constructions. Choose one before looking at the results, according to the question:

- `bonferroni` (the default) divides the error rate among the cumulative cut points between recorded categories. It gives the narrowest intervals for cumulative questions, such as the share above a clinical breakpoint or at or below an epidemiological cut-off value.
- `range-calibrated` protects every contiguous range of categories at once. It gives narrower intervals for single categories and internal ranges; its endpoints come from at most K selected count tables when the certificate recorded in the result holds.
- `joint-exact` and `range-hunter` refine these two by searching the compatible count tables within a time budget.

Bonferroni spends the error rate on the K−1 cumulative cut points only, which favours cumulative questions; range-calibrated covers all contiguous ranges with one cutoff, which favours categories and internal ranges. Results of different constructions must not be combined, and running several constructions to keep the narrowest result does not keep the stated confidence level.

## Request joint population refinement



To use dependencies between contiguous MIC range comparisons, select

`--population-method range-hunter`. For example:



```text

mic-50-90 distribution examples/distribution/supplemented.json --population-method range-hunter --population-precision-pp 10 --population-time-limit 120 --output-dir results/ranges

```



The width target is ten percentage points at the input confidence level.

The calculation may confirm this target without reaching the default 0.01

percentage point numerical endpoint tolerance. The result distinguishes a

confirmed width, a width proved too large for the current report and method,

and an unresolved calculation. Additional counts may still improve a result

that is too wide; that status does not prove that more isolates are required.

See [the construction and stopping rule](hunter-inference-kernel.md).



To refine the default construction using dependencies between cumulative-boundary comparisons, select `joint-exact`:



```console

mic-50-90 distribution examples/distribution/supplemented.json --population-method joint-exact --population-time-limit 30 --population-tolerance-pp 0.01 --output-dir results/joint

```



The method accounts for dependence between cumulative counts. It calculates conservative outer bounds for the whole recorded distribution. **The word exact describes the finite sampling model, not unlimited numerical precision or guaranteed completion.** The report states whether the requested endpoint precision was reached. `0.01` means 0.01 percentage point, not 1% relative improvement.



The default search budget is 30 seconds per cohort. If it is exhausted, all unresolved parameter regions are retained. The result may therefore equal the basic result. A failed optional calculation preserves valid sample and basic population results. Numerical refinement does not establish a better clinical decision or universal superiority; compare the reported widths and the question you need to answer.



See [the mathematical specification](joint-distribution-method.md) for the test construction, coverage argument, computational domain and validation.



## Use CSV tables



Replace the three file names with your own tables:

```console

mic-50-90 distribution summaries.csv --panels panels.csv --additional-counts additional-counts.csv --output-dir results/distribution

```



The panel table is the explicit categories table. No target table is required because the full fixed panel supplies the cumulative boundaries.



The summary table uses `cohort_id,panel_id,variant_id,n,mic50,mic90,rank_convention,rank50,rank90,minimum,maximum,iid,confidence_level`. Use `variant_id=primary` for the main row. Both MIC fields may be blank for a counts-only record; if either is supplied, the pair and its convention must be completed. The panel table supplies the MIC unit. Alternative rows must preserve panel, denominator and inference settings.



The optional counts table uses `cohort_id,threshold,unit,n,source` and the applicable count fields described above. Cohort identifiers must match exactly. Rows belonging to an unknown cohort are rejected. Missing or inconsistent records appear as refusals alongside successful records; `--fail-on-refusal` also returns exit status 2 after writing the report.



The delimiter defaults to comma; `--delimiter semicolon` and `--delimiter tab` are supported. For JSON inputs, include the panel and counts in the JSON rather than supplying CSV options.





## Ask a question without MIC50/MIC90



Counts-only inputs can include `targets` in JSON, using the same threshold table

fields as the summary workflow. For CSV add `--targets questions.csv` to the

`distribution` command. A question such as "is the recorded fraction above

2 mg/L below 5%?" uses `threshold: 2`, `unit: "mg/L"`,

`decision_operator: "<"`, and `decision_fraction: "0.05"`.



The HTML displays the criterion and each layer's answer. `decisions.csv` exports

statuses and retained sample components; `results.json` preserves the complete

record. Sample decisions compare exact integer fractions across every declared

variant. Population decisions project the simultaneous all-panel family;

calibration decisions require a matching all-panel contract. Optional layers are

unavailable when their assumptions fail. Adding a criterion does not add evidence.

Saved updates retain the original questions as well as the denominator and panel.



The guided form displays **5%**, while saved files retain **0.05**. No conversion

is applied retrospectively to existing saved fractions.

## Understanding an unreported category



In the supplied 67-isolate ampicillin example, MIC50/MIC90 and observed extremes permit 1–32 results in the recorded 0.5 mg/L category. Adding the published count of 59 at or below 0.25 gives 2–7 under the declared ceiling ranks: eight remain above 0.25; at least two reach MIC90 position 61 at 0.5; at least one must lie above 1. Using MIC90 rank 60 instead permits 1–7.



The compatible tables `(34,25,2,0,6)` and `(34,25,7,0,1)` attain both limits on the panel ≤0.12, 0.25, 0.5, 1 and >1 mg/L. They are illustrative possibilities, not reconstructed measurements. The sample bounds have no population confidence level.



For population inference, a fixed confidence construction and iid sampling assumptions are required. Under the certified P6 condition, at most K selected compatible tables yield the same lower and upper bounds for each contiguous range as all compatible tables. K is the category count. Apply the condition to each reporting interpretation separately; the equality does not identify a complete population distribution. Additional counts narrow the information; the theorem reduces the work needed to calculate the bounds.


## Choose the document for your task

GUI_GUIDE.md explains Windows entry, execution and saving. distribution-user-guide.md gives CLI analyses. REPORT_CONTENTS.md explains the generated reports, and PUBLIC_FUNCTIONS.md maps functions to their checks. The examples directory supplies input files and attributed source facts.


## Preserve a completed population calculation

Append a true count to the original input, retain every other input field, and run (with your own file and directory names):

```text
mic-50-90 distribution updated.json --population-method range-calibrated --previous-output output/original --output-dir output/updated
```

Use the same population method as the original run. The previous directory must
contain configuration.json and results.json. In Windows, Add a count passes this
pair automatically. A saved form created through that action also retains the
previous analysis. Ordinary input files describe a fresh calculation.

The report states when previous population outer bounds were retained. A shorter
refinement cannot widen that saved result. Inspect How this result was checked for
the current endpoint evidence. Sample precision, population interval width and
numerical endpoint tolerance remain separate quantities, all expressed in
percentage points. CLI_REFERENCE.md documents their options and defaults.
