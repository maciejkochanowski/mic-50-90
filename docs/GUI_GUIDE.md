# Guided analysis on your computer



MIC-50-90 1.0.0 provides an English-language form for preparing one sample, importing tables for several samples, and checking a received report. These routes use the same validation, calculations and HTML reports as the command-line workflows. The software does not estimate a missing histogram or supply undocumented panel information.



## Read the answer and graph



After Calculate, the answer appears in the application. The top result identifies the sample, organism, drug, denominator and supplied source. A bar is a known count. An interval is the smallest to largest compatible count; it does not mark a most likely value. Separate uncertain groups must still satisfy the original data together. Sample ranges are not population confidence intervals.



**See a published example** loads 7133 S. pneumoniae isolates tested against penicillin (de Miguel et al., DOI 10.3390/antibiotics12020289). Use Calculate to see 5407, 1583 and 143 isolates in the three reported groups. **Show what each count adds** explains why the second source count determines the last two groups. The 5% question is an illustration, not a clinical criterion. No MIC50/MIC90 calculation rule is assumed.



**See a laboratory example** loads 276 canine E. coli isolates tested against amikacin (FDA NAHLN 2024). The report demonstrates that eight results above 4 mg/L suffice to establish four requested sample fractions below 5%. The summaries are calculated from real laboratory category counts. This concerns information disclosed to the reader, not fewer laboratory assays.



Use **Add a count** after a single distribution analysis to restore its inputs and append an existing count from the same original isolates. Keep previous counts. The application writes a separate result and offers a before/after graph on the same scale. Contradictory counts or changed sample conditions are refused. **Edit input** returns to the form. Starting a new sample requires **New analysis**.



**Save SVG** retains a scalable chart. **Save PNG** produces a raster image. **Print / save as PDF** opens the browser print dialog. The application enables these controls without changing the numerical results. The exported standalone HTML provides the same SVG, PNG and Print / save as PDF controls offline. Expand **Save inputs and full results** to download the complete analysis. For several samples, use the sample selector or pages of fifty; refused samples remain visible. Optional population and calibration results distinguish **Not requested** from **Unavailable**, with a reason for an unavailable result.



## Optional population calculations

For optional population inference, **Simultaneous bounds for all MIC ranges**

selects the `range-calibrated` method. Choose it before comparing results. It

uses every contiguous range of the recorded categories under the declared iid

sampling assumption. A numerical target such as 0.01 percentage point controls

how closely the program locates interval endpoints; it does not require a

population interval to be that narrow. Read the conclusion first. A safe bound

may already answer your question even when the endpoint target is unresolved.

[Calculation and assumptions](range-population-method.md).



**Joint refinement across MIC ranges** selects `range-hunter`, a separate

construction that accounts for dependencies between range comparisons. Set

**Largest acceptable population interval width** to the precision you need, for example

10 percentage points. When this width is confirmed, the program can stop

without reaching 0.01 percentage point endpoint precision. A result that is

still unresolved at the time limit retains valid outer bounds. It does not

prove that your sample is too small. Select the method before analysis; its

availability is not a claim that it always gives narrower intervals.

[Joint range inference and stopping rules](hunter-inference-kernel.md).



## Start the application



In the portable Windows package, open the MIC-50-90 application. It opens a local browser page. The runtime and scientific libraries are included; a separate Python installation is not required. Keep the application running while using the form. Select **Quit application** to stop it; closing only the browser tab does not stop the local service.



For an installed Python package, run `mic-50-90 gui`. This starts the same interface. The form and reports work offline, without external fonts, scripts or an internet connection. Input is sent only to the calculation process on your computer. Saved inputs and results contain the information you supplied; store them according to your laboratory's data-handling requirements.



## First analysis



Choose **I have results from a publication** for MIC50/MIC90, a range or partial counts. Choose **I have laboratory category counts** when you know the count in every MIC category. The two example buttons open separate filled-in examples; **New analysis** starts your own input without carrying those values over.



1. Copy the sample size and MIC unit. The sample name is just a label; organism and source notes are optional.

2. Copy the complete tested concentration list from the Methods or laboratory panel. Do not substitute the observed MIC range or the two MIC quantiles for this list. The form explains where to look if it is missing.

3. Copy your available results. The form shows a calculation-rule question only after a MIC50/MIC90 value is selected. A rule that the source does not establish is an assumption, not recovered metadata. Counts-only analyses leave the summaries blank. Laboratory counts include explicit zeros; a live total checks against the sample size.

4. For a first distribution report, proceed with the sample description. Optional concentration questions, grouping and population analysis expand when selected. Calibration is under a separate advanced section. For a laboratory reporting comparison, specify at least one concentration of interest.

5. Check the copied values, calculate and open the report. **Next** points out missing information at the relevant step. The calculation still performs the full scientific validation.



For example, a source reporting 59 of 67 isolates at or below 0.25 mg/L supplies sample size **67**, additional-count concentration **0.25**, relation **≤**, count **59**. The concentration panel must still come from that source. The software uses the count as a constraint; it does not invent the remaining individual MIC values.



## Choose your starting information



**I have results from a publication** accepts MIC summaries, an observed range, additional counts or a combination. The default distribution route can describe the whole recorded distribution and answer specified threshold questions using counts alone. MIC50/MIC90 are not needed when the counts supply the information. The separate additional-count planning route uses paired MIC50/MIC90 and requires both summaries with explicit ranks or a justified convention.



**I have laboratory category counts** evaluates reporting choices. Enter every category, including zero counts. The audit compares summaries, one additional count, all requested counts and the histogram. Choose the ceiling-rank convention explicitly for the summaries generated by this audit.



**Open a saved analysis** opens a saved form, a supported single-sample input JSON, a single-sample distribution `configuration.json`, or a saved table or verification session. The form retains advanced imported fields and preserves the meaning of earlier decision fractions. It does not silently convert unsupported analysis modes.



**Import CSV or paste a table** accepts text files or cells copied from a spreadsheet, including their header row. It supports distribution, paired-summary and complete-count reporting workflows for several samples. **Verify a received report** accepts the certificate document supplied with a sufficient report, without asking for its original histogram. Reference and calibration preparation remain available through the documented commands.



The supplied examples are controlled summaries for 20 isolates, a controlled reporting audit, published counts for 7,133 isolates and real laboratory counts for 276 isolates. Each example identifies its source or controlled origin. Loading an example is a demonstration, not evidence that its assumptions apply to your sample.



## Complete the five steps



1. **Sample.** Enter a unique identifier, the number of original isolates and the MIC unit. Organism, antimicrobial, source and panel identifier provide context. Their names do not automatically select susceptibility criteria, panels or sampling assumptions.

2. **MIC categories.** Enter the documented tested concentrations and confirm the two censoring choices. The concentration-series convention represents intervals between successive levels. Use explicit categories when the source supplies a different geometry, such as broad groups separated by published count thresholds. Blank category bounds mean unbounded ends; the recorded ordering value is not an imputed MIC within the category.

3. **Available results.** Select the reported MIC categories and declare each quantile's convention or original integer rank. An unknown convention is not replaced automatically with ceiling ranks. Alternative declared interpretations may be entered separately. Counts-only distribution inputs can leave the MIC summaries blank.

4. **Questions.** Request a whole-distribution report, optionally with a maximum width for grouped sample percentages, and add any concentration questions and criteria. Enter decision criteria as percentages from 0 to 100: `5` means 5%. Exact decimal input is retained; a strict comparison at 5% is not changed by displayed rounding. Saved and exported scientific inputs use the fraction scale (`0.05` for 5%). Population analysis requires an explicit independent, identically distributed sampling declaration. Calibration requires an independently prepared compatible reference and manifest.

5. **Check and calculate.** Review the denominator, categories and assumptions, then check the input. All detected structural issues appear together. Feasibility and optional scientific calculations are evaluated by the calculation process. A structurally valid input is not a promise that every analysis will be available.



## Enter additional counts accurately



Every additional row has its own original denominator, threshold and source. Choose **Source count relation** exactly as reported: strictly above (`>`), at or above (`>=`), strictly below (`<`), or at or below (`<=`). Supported forms are an exact number, an integer range, and a rounded percentage with explicit decimal places and rounding rule. The editable input retains the original relation; the calculation normalizes it to a compatible recorded-tail constraint and retains the source information.



For example, with 67 original isolates and 59 at or below 0.25 mg/L, select `<=` and enter 59. The preview explains the equivalent 8 strictly above 0.25 mg/L. For rounded percentages and ranges, compatible integer counts are determined before complementing. Relations `>=` and `<` require a source- and category-consistent boundary. **Check input** refuses an ambiguous category; these relations are never replaced blindly by `>` at the same threshold. Keep the source relation visible when correcting an input.



All rows must describe the same sample and unit. Changing the sample size does not silently change a previously entered count's denominator. Do not combine results from different subsets or insert rounded percentages as exact counts. Count fields and decision fractions retain their decimal input; invalid fractional counts are not truncated.



## Read and save the results



Start with **What we know**, **What remains unknown** and **What to do next**.

The graph immediately below describes the original isolates. A bar gives a known

count; a range shows every attainable endpoint, without a guessed middle value.

Use the population section only when its sampling assumptions apply.



For a first publication example, select **See a published example**. The two

published counts give 5407, 1583 and 143 of 7133 isolates in three broad MIC

groups. **Show what each count adds** explains why the second count is needed.

For a laboratory example, select **See a laboratory example**. Eight of 276

isolates above 4 mg/L suffice for four stated questions. This is a smaller report,

not fewer susceptibility tests. Retain the original complete histogram.



Select **Calculate and create report**. The local application runs the analysis in a separate process and displays its status. A cancelled or failed calculation is not labelled completed. Outputs provide links to the HTML report and individual result files, plus a combined download. A mixed table result is labelled **Report ready · review refused results**: open the report to inspect both successful samples and the reasons for refusal. Its successful results and downloads remain available. Each calculation receives a new output directory.



The three interpretation layers remain separate:



- The sample result describes what is compatible with the supplied information for the original isolates.

- The population result requires the stated sampling model and reports its confidence guarantee.

- Calibration describes the event covered for a new compatible study unit and reports its own level, units and assumptions.



The absence of population or calibration support does not invalidate a correctly calculated sample result. If a numerical search ends before its precision target, read its status and retained outer bounds; do not treat it as a completed optimum.



Select **Save editable input** to download a form that can be reopened, including imported advanced settings and an attached previous result where applicable. The scientific input and ordinary result exports remain available in the output directory. The form does not require editing JSON for its guided fields; the advanced editor is optional.



## Add information to a previous distribution result



In **Check and calculate**, open the matching `configuration.json` and `results.json` from the previous distribution analysis together. The form restores the original input. Append the newly obtained truthful counts and keep the earlier rows in their original order.



The denominator, sample identity, categories, quantile interpretations, sampling declaration, confidence level and population method must remain fixed. The engine checks this contract. A valid update can retain the earlier population outer bounds as well as the original sample information. Different samples or methods require a separate analysis. Keep earlier output files unchanged.



## Understand a wide result



For a question about one MIC category or a group inside the panel, choose

**One or more adjacent MIC categories** in the distribution view. Select the

first and last included categories; selecting the same label twice means that

category alone. Enter the criterion as a percentage. The opening result names

the selected categories and gives the compatible count out of the original

sample. It does not divide censored categories or assign clinical resistance.



The opening report includes **What limits this answer?** Missing counts mean that the original sample was incompletely reported. Sampling uncertainty concerns a population beyond those isolates and requires the stated sampling assumptions. Numerical refinement means that the program has retained safe bounds but has not proved the requested accuracy of their endpoints. These can occur together.



For missing counts, the next step names a cumulative total for the same original isolates and shows its current range. When a declared question is still open (an unresolved criterion, or a question whose count is not yet fixed), it is the single cumulative count that narrows the answers most in the worst case; otherwise, or when no count narrows them, it is the cumulative total with the widest remaining range. This fixes that cumulative share; it does not necessarily determine every group. It is one suggested count, not the minimum-cost plan that the planning options compute. **Where the input information came from** shows the source descriptions supplied with counts and metadata; the program does not authenticate them.



Population results report the time for the safe baseline separately from the optional joint refinement. The selected time limit applies to refinement, with cooperative interruption. It is not a guarantee of total application response time. Save the current result even when refinement has not reached its requested numerical precision.



## Prepared calibration and advanced inputs



The calibration import accepts an analysis configuration containing `reference_distribution`, `wasserstein_calibration_manifest` and `calibration_context`. The presence of these fields is not itself a guarantee: compatibility, scope and binding to the current cohort and panel are checked. Reference preparation and calibration-data assembly use the documented calibration workflows.



The advanced input section shows every retained setting. Unknown or unsupported fields are not silently interpreted as a new scientific method. Relevant unsupported conversions are refused; unused options are reported. For public Python functionality or workflows outside the guided form, use [the Python interface](PYTHON_INTERFACE.md), [CSV workflows](CSV_WORKFLOWS.md) and [distribution guide](distribution-user-guide.md).



## Import CSV files or copied spreadsheet cells



Choose the analysis type, then supply sample information (or complete category counts) and the panel table. Choose each file or paste its header and cells. Select **Comma**, **Semicolon**, or **Tab** explicitly for each table; copied Excel cells normally use tabs. Different tables may use different separators. Workbook files such as `.xlsx` are not accepted; export CSV or copy the cells instead.



The preview shows headers, row counts, sample identifiers and the first five data rows. A wrong separator, mismatched row width or duplicate header produces a preview error. **Check input** also checks required columns and joins. It lists unknown sample identifiers as errors and missing per-sample panels as warnings; the latter sample is refused during calculation while independent valid samples can continue. This structural preview does not prove numerical compatibility.



Use the [CSV schemas](CSV_WORKFLOWS.md). Distribution rows require `cohort_id,panel_id,variant_id,n`; use `primary` for the main variant. Counts-only distribution inputs may leave the MIC summaries blank. Questions are optional for distributions and required for the other two table workflows. In an imported question table, the `decision_fraction` column uses the 0–1 scale (`0.05` for 5%); this is not reinterpreted as the form's percentage field. All counts must concern their stated original sample. A table import runs locally and never evaluates spreadsheet formulas.



Save the editable input to retain all table text, chosen separators and analysis settings. The reporting-audit route can optionally find sufficient count fields when the questions contain explicit criteria.



## Verify a received sufficient report



Choose **Verify a received report**, then open `reporting_certificates.json` or paste its complete JSON document. A valid envelope contains `version: "1.0.0"` and a nonempty `certificates` list. A bare single certificate or `results.json` is not that envelope. The original JSON text is retained so exact decimal criteria survive the browser.



Select **Verify and create report**. The checker recomputes logical sufficiency from the supplied specification, questions and disclosures; previous success labels are not trusted. The report shows the questions, disclosed counts and resulting sample decisions. Insufficient or inconsistent disclosures produce a refusal with its reason. The check requires no original histogram and does not authenticate source records or provide population guarantees. Save the report and its JSON results with the received certificate.



The [276-isolate received-report example](../examples/received_report/README.md) supplies a certificate that can be selected through this route.

## Why the ampicillin result is 2 to 7



Open the prepared `ampicillin-67-with-count.json` Windows input. It describes 67 canine staphylococci and asks about the recorded 0.5 mg/L category. The declared ceiling ranks are assumptions of this analysis.



The source gives 59 results at or below 0.25 mg/L, so 8 remain above it. MIC90 occupies position 61, requiring at least two in category 0.5. At least one is above 1 mg/L, leaving at most seven in category 0.5. The sample answer is therefore 2–7 (2.99–10.45%). With MIC90 rank 60 instead, it is 1–7.



Two compatible category-count tables, in the order ≤0.12, 0.25, 0.5, 1 and >1 mg/L, are `(34,25,2,0,6)` and `(34,25,7,0,1)`. They demonstrate both possible limits; they are not recovered observations. The source is Brookshire et al., Table 1, DOI 10.3389/fvets.2024.1512582; both species remain in the denominator.



Population bounds are a separate result requiring an explicit sampling model. The selected-table theorem speeds calculation of those bounds under a verified condition; it does not reduce the number of isolates or infer a resistance mechanism. A threshold inside a censored category may still need finer measurements, as the chloramphenicol example shows.


## Choose the document for your task

GUI_GUIDE.md explains Windows entry, execution and saving. distribution-user-guide.md gives CLI analyses. REPORT_CONTENTS.md explains the generated reports, and PUBLIC_FUNCTIONS.md maps functions to their checks. The examples directory supplies input files and attributed source facts.


## Keep a population result while adding a count

Use Add a count from a completed distribution result. The application restores
configuration.json and results.json and appends the new statement to the same
sample. Save this updated form to retain the previous analysis when reopening.
Download all results to keep the original pair. Opening an ordinary input alone
starts a fresh calculation. The corresponding CLI command uses --previous-output;
see distribution-user-guide.md. Preserve the denominator, panel,
ranks, questions, confidence, method and earlier counts.

The application and standalone HTML use the same local SVG/PNG and print controls.
PUBLIC_FUNCTIONS.md maps tasks, interfaces and outputs; this guide describes saving and reopening. Advanced analyse and
calibration preparation/planning/audit remain CLI tasks; no additional Windows
forms are implied. CLI_REFERENCE.md lists every public command-line option.
