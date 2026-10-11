# Calculations visible in a report

The HTML report is the primary interpretation interface. CSV contains compact tabular results. JSON retains unrounded values, full arrays and normalized numerical diagnostics; configuration.json records the exact inputs and their hashes.

The guided application opens these same reports and provides their complete
download archive. Its five steps collect inputs; they do not replace the report's
scientific assumptions. `gui-input.json` preserves the completed form. Reopening
that file restores an analysis; a supported saved-output update also retains the
original numerical bounds. A refused input or cancelled calculation is clearly
distinguished from a completed analysis. See [GUI_GUIDE.md](GUI_GUIDE.md).

| Calculation | HTML location | Main implementation | Verification |
|---|---|---|---|
| Criterion evaluated on unrounded sets across all declared variants | Your questions; separate sample, population and calibration answers | decisions, workflows | exact boundary, variant union and distinct population tests |
| Least worst-case cost to settle explicit recorded-sample criteria, next count and stopping rule | Counts to resolve your criteria | decision_planning, decision_report, workflows | D1–D4 proofs, independent finite-tree oracles, 300 retained-cohort tasks and optional-failure tests |
| Accessible interval chart; disconnected confidence components retained | Opening interval chart | report | component rendering and browser inspection |
| Source metadata versus analyst-declared assumptions | Cohort provenance | workflows, report | CSV provenance persistence and escaping test |
| All identifiable missing required fields | Refused cohort explanation | workflows | simultaneous panel/rank and panel-field omissions |
| Input panel, ranks, extrema and reporting variants | Declared reporting assumptions and panel geometry | model, workflows | contract, CSV and rejection tests |
| Sharp recorded and latent fractions with counts | Observed sample | empirical, censoring, analysis | integer enumeration, analytic extrema, solver comparisons |
| Envelope and bounds for each reporting variant | Observed sample and expandable per-variant diagnostics | analysis | reporting union tests |
| Endpoint witness histograms and solver certificates | Expandable numerical checks | empirical, report | independent extrema and report completeness tests |
| Exact marginal and Bonferroni family confidence sets | Exact iid population | exact_population | exhaustive coverage enumeration; disconnected-union regression |
| MLE, profile grid, likelihood ratios and cutoff | Optional population analyses | likelihood, population | order-event enumeration, fit and failure tests |
| Profile fallback and boundary warnings | Optional population analyses | population, report | successful fallback and returned-failure checks |
| Dirichlet prior, posterior intervals, ESS and Monte Carlo error | Optional population analyses | bayes | posterior tests and serialized-output rendering |
| Calibrated tail intervals and full manifest contract | New cohort calibration | conformal, dro, comparability | contract/unit checks and public-API replay |
| Maximum-entropy and KL scenarios, probabilities, tails and status | Assumption-dependent scenarios | scenarios | optimizer and failure-isolation checks |
| Uncalibrated transport-radius scenario | Assumption-dependent scenarios | dro | transport oracle and failure checks |
| Additional counts, costs, feasible answers and guaranteed benefit | Additional information | utility | exhaustive small histograms and retained LP oracle |
| Summary, one-count, all-target and histogram comparison | Laboratory reporting audit | workflows | per-threshold containment and 60-cohort pilot |
| Refusals, unavailable layers, timeout and zero benefit | Beside the affected result | analysis, workflows, report | controlled failures and frozen researcher pilot |
| Intended/available units, containment and paired widths | Separate calibration-audit HTML | calibration_audit | Frozen-roster omissions, whole-unit failures and independent binomial inversion |
| Calibration/test requirements for three probability statements | Separate calibration-plan HTML | calibration_audit | Marginal rank, PAC rank and zero-failure boundaries |

The reported family confidence set preserves disconnected components using the union sign ∪. It does not fill excluded gaps with a convex hull. A reporting-envelope minimum and maximum have a different purpose: they summarize all declared sample variants, whose individual bounds remain visible.

The interval-width question list displays up to ten highest-ranked evaluated questions. A completed width search determines the recommendation over the full allowed set; an incomplete search cannot claim an optimum. Zero-width-gain comparisons remain visible without a recommendation under that objective. The observed benefit uses either the audit histogram or explicitly entered additional counts from the original sample.

The separate decision-planning section identifies each recorded-sample criterion, its initial status and the next count to request. Costs mean the declared acquisition units; unit costs count requests, not measured laboratory effort. An optimal result certifies the minimum worst-case cost. An incomplete result labels any verified upper bound and fixed fallback. The fixed-plan comparison is a feasible baseline unless `fixed_plan_optimality_verified` is true. An impossible result displays two compatible histograms that agree at every allowed cut but disagree on a criterion. Unavailable explains an optional input failure while preserving valid base results.

Stop only when every declared sample criterion is supported or contradicted. Enter truthful responses through `--additional-counts`, retaining the original denominator and earlier answers. The planner cannot certify stopping for latent, population or calibrated decisions. HTML shows the initial response branches; JSON retains the complete adaptive tree with inclusive integer tail-count ranges, or the verified fixed-order fallback. CSV retains basic status, cost, optimality and next-question fields. See [decision planning](DECISION_PLANNING.md).

Optional fitting failures leave successfully computed exact results available. A failed reference projection or transport optimization makes the affected optional variant unavailable; the tool does not form a misleading complete envelope from the remaining variants. Profile calculations use a Powell fallback if L-BFGS-B fails and expose its use; failure of both methods refuses that optional result.

No finite test suite proves every possible use correct. Static analysis and execution coverage complement numerical oracles. The [current engineering verification](ENGINEERING_VERIFICATION.md) gives measured coverage, test scope and source-bound records. The reproduction package's dated CODE_AUDIT.md is a retained audit, not the current coverage measurement.

Returned counts now have their own visible section: original denominator, source, before/after bounds and observed gain. The next recommendation uses the refined information. Calibration conflicts are explicit, preserving valid sample results. Large reports retain every section on linked detail pages; the index lists all successes and refusals. Preparation has a separate HTML report with the intended calibration denominator, every score/refusal and the provenance contract.

Trained calibration preparation shows the number of separate training units, learned panel scales and the applied physical radii. Target analysis shows the normalized radius and panel scale alongside the physical radius. Missing training information is reported as a failed trained preparation, without relabelling it as a uniform method.

The first per-cohort sections are Source and sample, then Your questions. Organism and antimicrobial annotations are preserved when supplied. Each unresolved sample criterion has two compatible hypothetical samples giving opposite answers. Returned ranges and explicit rounding rules are shown without midpoint substitution. Conflicts identify answers to verify; acquired information never changes the original denominator. Acquisition cost bounds are displayed alongside search status. See examples/laboratory_use/README.md.


## Sufficient reports and whole distributions

`reporting-audit --reporting-plan` adds **Counts to include in your report**: actual disclosed counts, before/after sample decisions, recipient sufficiency, cost and optimality status. `reporting_counts.csv` is reusable in the reader workflow; `reporting_certificates.json` permits logical checking without the full source histogram. An unfinished search does not claim the cheapest report. See [sufficient reporting](SUFFICIENT_REPORTING.md).

The separate `distribution` report shows category and cumulative count/proportion ranges, their disconnected sample components, and any selected contiguous grouping. Population bounds state the iid assumption, confidence level, baseline, numerical method and whether the requested endpoint precision was reached. A time-limited or unresolved calculation retains conservative outer bounds. `--precision-pp` describes sample grouping, not population confidence or numerical endpoint precision. Saved updates state their retained earlier information and bounds. See [distribution use](distribution-user-guide.md).

Distribution calibration identifies its own achieved marginal level, requested level, number and definition of calibration units, event scope, reference and radius. These are not the population confidence level. An incompatible cohort/panel binding makes calibration unavailable while valid sample/population results remain visible. Full contracts and assumptions remain in JSON. Displayed calibration category ranges are projections implied by the calibrated all-tail event, not a guarantee that the complete distribution lies in a transport ball.


## Checking a received report

The guided verification operation accepts the existing versioned certificate
export. It recomputes logical sufficiency without a hidden histogram and shows
sample size, each question, compatible counts, decisions and disclosed source
comparisons. Full calculation records remain available in a collapsed section
and JSON. A missing or contradictory disclosure cannot receive a successful
verification. This check assumes truthful counts; it does not authenticate data
or establish a population or calibration guarantee.

The distribution report also shows optional criteria for counts-only inputs.
Exact sample count components and separate population/calibration statuses are
exported to decisions.csv. User-entered comparisons retain strict endpoints.


## Portable controls and endpoint evidence

Windows and standalone HTML share local SVG/PNG export and Print / save as PDF.
The HTML embeds the control code and fonts. The application binds the same controls
from its host, retaining the script-disabled report sandbox. Reading tables and
links does not require JavaScript. Printing opens all details and includes every
cohort in the current file; a paginated index retains links to other detail files.

Analysis request flags distinguish Not requested from Unavailable. Incomplete
identifies unresolved numerical endpoint work; the returned conservative bounds
remain visible. The overview and detailed layer use the same status rule.

| Calculation or record | HTML explanation | Complete output |
|---|---|---|
| Sample category and cumulative bounds | Counts, percentages and separate allowed components | distribution.csv / results.json |
| Population construction and confidence | Population distribution; How this result was checked | population object in results.json |
| P6 sufficient condition | Recorded certified/not-certified condition; K is category count | population_row_lift_certificate |
| Endpoint confirmation | Requested precision, remaining certified gap and evaluated-table count | numerical_certificate and recorded witness/search fields |
| Previous same-sample bounds | Retention note in Population distribution | previous_outer_bounds_preserved and saved configuration |
| New-study calibration | Unit, reference, level and scope | Calibration contract and results.json |
| Count choice or sufficient report | Next question, cost, stopping status or recipient answers | Complete trees/certificates in results.json and reporting_certificates.json |
| Model sensitivity | analyse report when --html is supplied | Model-specific JSON fields |

P6 is reported only when its certificate exists. An unconfirmed sufficient condition
does not establish its failure. The statistical confidence level and numerical
endpoint tolerance describe different uncertainties. Timing is measured separately.

When a requested confidence level is so close to one that its multiplicity-adjusted
value rounds to 1 in floating-point output, the calculation keeps the nonzero tail
probability. The report flags the rounded display; `confidence_level_exact` gives
the rational adjusted level in JSON. This is not a claim of 100% confidence.
