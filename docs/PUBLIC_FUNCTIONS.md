# Public tasks, calculations and checks

For invocation examples and interface defaults, see [Python interface](PYTHON_INTERFACE.md); [missing information](MISSING_INFORMATION.md) explains refusal and unavailable-layer outcomes.

This map covers every name exported by `mic_50_90.__all__`, the command-line tasks, and the reporting/workflow entry points. Classes represent data contracts; they are not competing analysis methods. The [current engineering record](ENGINEERING_VERIFICATION.md) links module coverage and a lexical function execution inventory. Lack of execution or use in a tutorial does not justify deleting a public function.

## Guided local application

The distribution workflow exposes four population constructions: `bonferroni`,
`joint-exact`, `range-calibrated` and `range-hunter`. The common input/output
contract is documented in [the Python interface](PYTHON_INTERFACE.md).
`distribution_targets` translates threshold and inclusive category-range
questions into a shared event for validation, calculations and display. Recorded
categories remain the default. For `target_scale=interval`, definite and possible
membership preserve uncertainty within the declared measurement intervals.
`distribution_decisions` projects sample, population and calibrated results onto
that event, using the same simultaneous region for both membership bounds.
Independent finite-histogram checks and JSON/CSV/GUI round trips are in
`test_distribution_range_questions.py` and `test_interval_scale_targets.py`.

`range_certificates` checks the P6 sufficient condition documented in population-row-lift.md for
population projection endpoints to be attained by at most K distinct count-row
histograms on a K-category panel. This condition concerns the finite sequence of
binomial confidence endpoints, not the shape of the MIC distribution. If it is
not certified, `range_population` retains conservative bounds and can check
compatible probability witnesses and disjoint parts of the remaining count
space. Projection equality does not imply equality of the full confidence sets.
See [the proof and numerical contract](population-row-lift.md).

`maximum_population_partition` certifies achievable and possible numbers of
contiguous population groups from all interval projections. `plan_population_precision`
searches same-sample interval counts with declared costs and availability.
The independent partition and question-tree checks are in
`test_population_resolution.py` and `test_population_acquisition.py`.
`observation_coefficients` translates tail or whole-category range observations
into the common constraint representation; `test_interval_observations.py`
checks exact counts, rounding, contradictions and the guided report.

The portable Windows launcher, `mic-50-90-gui` and `mic-50-90 gui` open the same
English form. `gui_forms.validate_payload` checks the input structure and explicit
metadata; scientific feasibility is checked by the calculation engine. `gui_worker`
runs distribution, summary-threshold or histogram-reporting workflows in a separate
process. `gui.DesktopServer` manages local sessions, cancellation, protected output
downloads and shutdown. These interfaces add no statistical estimator. Saved input
and same-sample updates preserve exact decimal counts and decision criteria.

Backend tests check malformed inputs, local access restrictions, optional failures,
saved updates and real engine results. Browser checks exercise all five steps,
prepared examples, validation, saved-input reuse and responsive layouts. Installed
archive and portable checks run in the software release workflow.
The form is described in [the guided application manual](GUI_GUIDE.md).

| Public entry | User task and calculation | Result or export | Independent check |
|---|---|---|---|
| `__version__` | Identify the installed software | CLI, report and package metadata | Installed-wheel and metadata consistency |
| `MICBin` | Declare a point, interval or censored category | Panel geometry | Endpoint/open-boundary examples |
| `MICPanel` | Declare ordered categories and units | Configuration and report | Category order and twofold-panel tests |
| `QuantileSummary` | Bind a percentile to an order-statistic rank | Declared ranks | Integer/rank validation and independent order inequalities |
| `ReportingVariant` | Declare a complete alternative reporting convention | Per-variant bounds and union | Distinct-rank union tests |
| `parse_spec` | Validate JSON and compatible legacy inputs | Normalized specification or refusal | Schema and malformed-input checks |
| `EmpiricalIdentification` | Store a sharp interval and its witnesses | Counts, fractions and certificates | Integer enumeration and objective checks |
| `empirical_bounds` | Find sharp sample extrema | Sample layer | Independent compositions and analytic extrema |
| `analyse_spec` | Run requested JSON analyses | Full result and optional HTML | End-to-end examples, solver and failure oracles |
| `plan_decisions` | Minimize the worst-case cost of resolving every explicit recorded-sample criterion using permitted exact counts | Status, initial decisions, exact costs, next count, branching policy or indistinguishable histogram pair | Independent tree and histogram oracles, with every compatible path checked |
| `clopper_pearson` | Compute a binomial interval for one known count | Population components | Known boundary cases and coverage enumeration |
| `exact_count_confidence` | Unite intervals over canonical compatible recorded-tail counts; refuse unsupported support | Marginal/family confidence components and hull | Independent binomial inversion, coverage enumeration and disconnected components |
| `order_event_probability` | Compute the probability of the reported order event | Optional likelihood analysis | Direct small multinomial summation |
| `log_order_event_probability` | Evaluate that event on the log scale, with positive-sum fallback when needed | Optional fit and diagnostics; finite rare-event log values | Independent Decimal multinomial and exact ordered-draw enumeration |
| `WassersteinCalibrationManifest` | Store the versioned reference, score, scope and unit record; validate through builders/application | Calibration provenance | Invalid/migrated manifest and unit tests; bare construction is not validation |
| `split_conformal_radius` | Select the finite-sample conformal order statistic | Radius and attainable level | Rank arithmetic, ties and unattainable-level cases |
| `calibrate_wasserstein_manifest` | Aggregate unit scores and bind a contract | Manifest JSON | Duplicate/invalid-unit, nonfinite-score and scope tests |
| CLI `analyse` / `batch` | Analyse one JSON or joined summary CSVs | HTML, CSV, JSON, configuration | Installed-archive examples, published-summary arithmetic |
| CLI `reporting-audit` | Compare summaries, one count, all targets and histogram | Audit widths and observed/guaranteed gain | Controlled histogram and per-cut independent checks |
| CLI `batch --decision-plan` / `reporting-audit --decision-plan` | Request an adaptive plan, optionally restricting cuts/costs through `--decision-queries` | Separate decision-plan HTML, compact CSV status/cost/next count, full JSON policy | Exact-decimal input, optional-failure isolation, whitelist and returned-count integration checks |
| CLI `calibrate-wasserstein` | Convert explicit scores and contract into a manifest | Validated manifest | CLI and calibration contract tests |
| `plan_calibration`, CLI `calibration-plan` | Distinguish marginal-rank feasibility, PAC assurance and held-out precision | Planning JSON and HTML with separate unit requirements | Rank boundaries and exact zero-failure minima |
| `audit_calibration`, CLI `calibration-audit` | Compare every intended held-out target with its known truth | Unit/cohort/target tables, success, optional iid bound, widths and hashes | Missing/foreign/duplicate rows, overlap, baseline nesting and independent binomial inversion |
| Workflow entry points `run_csv_workflow`, `read_csv`, `load_panels`, `analyse_layers`, `summary_spec`, `counts_spec`, `audit_histogram` | Join, validate and execute the two workflows | Per-cohort results; layer-specific refusal | CSV joins, missing inputs, incompatibility and optional failures |
| `report.render_html`, `render_batch_html`, `result_sections`, `audit_section` | Present every requested calculation with its scope | Self-contained HTML | Content tests, HTML escaping, visible page inspection |
| `decision_report.render_decision_plan` | Explain the next count, acquisition cost, stopping rule and sample-only scope | Decision-plan section, incomplete-search qualification and impossibility pair | Optimal, resolved, impossible, incomplete and unavailable rendering checks |
| `decisions.parse_criterion`, `classify_intervals`, `decision_results` | Interpret a one-sided fractional criterion | Four statuses per inference layer | Strict endpoints, rational boundary, all-variant union and calibrated-event tests |

Internal families have specific roles: `utility` ranks additional counts; `scenarios` computes entropy and KL sensitivity; `population` and `bayes` fit optional likelihood/prior models; `dro` computes transport ambiguity bounds; `comparability` checks reference compatibility; `censoring` constructs recorded and latent objectives. Their results and failures appear in HTML or the full JSON. They remain useful optional capabilities, without an empirical superiority claim.

Decision planning and width reduction answer different questions. The former stops once all requested sample criteria are definite; the latter ranks one count by guaranteed interval narrowing. The planner's fixed-plan comparison is a sufficient baseline unless `fixed_plan_optimality_verified` is true. Its exact common-boundary reduction applies to one coherent prefix box, not arbitrary variant unions. See [decision planning](DECISION_PLANNING.md) for permitted queries, resource limits and same-cohort returned counts.

The legacy `conformal.assign_partition` helper is retained for API compatibility and tested. It is not the current study-unit calibration design. A static unused-code heuristic and observed execution coverage are complementary checks, not proofs that all branches or assumptions are correct.

The CLI also exposes --version, python -m mic_50_90, explicit comma/semicolon/tab input selection, and optional --fail-on-refusal after saving reports. PYTHON_INTERFACE.md documents optional numerical methods and REPORT_CONTENTS.md maps calculations to report/export fields. HTML, JSON and CSV retain disconnected confidence components. Existing CSV endpoint columns describe the outer hull; explicit component columns preserve the gaps.

| Workflow entry | User task | Output | Check |
|---|---|---|---|
| prepare_calibration; CLI calibration-prepare | Complete histograms to uniform or separately trained reference/scaled calibration | Training references/scales, expected scores, refusals, manifest and target mapping | Direct transport LP, complete-roster failures and trained-reference controls |
| analyse_with_counts; batch --additional-counts | Incorporate truthful same-sample counts | Updated sample, iid and calibrated bands, comparisons and further questions | Independent enumeration, witness-loss counterexample, conflict and numerical-failure tests |
| report_pages; --report-page-size | Navigate all large-batch results | Local index, complete pages, hashes and counts | Exact membership/content/raw-gzip equivalence and interrupted-render checks |

The lower-level modules also expose optional fitting functions: population.fit_population_mle and profile_likelihood have an analytic two-category control; bayes.dirichlet_posterior_tail has exact conjugate-mixture and Monte Carlo error checks. The tests directory contains the corresponding estimator and numerical-oracle checks. This distinguishes a documented callable API from the scientific description; individual internal helpers do not require separate main-text claims.

Discrete numerical inputs are validated rather than silently truncated. Malformed or duplicate variants stop input validation; only mathematically infeasible variants may be excluded. The exact-count support claim is restricted to canonical integral interval constraints and monotone binary tails. Source-test coverage, finite numerical agreement and empirical calibration outcomes are separate evidence.

## Counts requested together

| Public entry | User task | Output | Independent check |
|---|---|---|---|
| `acquisition.plan_acquisition` (also exported at package level) | Choose which existing counts to request together, allowing a cost per request | Exact or sufficient policy, next batch, remaining cost and separate bounds on rounds/counts | Independent enumeration and Bellman search in `tests/test_acquisition_oracle.py`; controlled replay and ordered-search comparisons |

The workflow exposes this calculation through `--acquisition-plan`. `decision_report.render_acquisition_plan` explains its result in HTML. `requested_counts.csv` can be completed and returned through `--additional-counts`; input delimiter, previous answers and original denominator are preserved. Optional planning or comparator failure does not discard the basic result.

## Bounded information and explanations

| Public entry | User task | Result | Check |
|---|---|---|---|
| `counts_from_percentage` | Convert an explicitly rounded percentage to possible integer counts | Inclusive endpoints or an empty-preimage refusal | Independent Decimal preimages, four rules, ties and endpoints |
| `analyse_with_counts` with `count_min/count_max` | Retain uncertainty in an acquired answer | Updated sample, population and original calibrated bands | Independent range/variant enumeration; all-layer and CSV tests |
| `decision_results` | Explain an unresolved sample criterion | Opposite feasible hypothetical histograms | Direct feasibility and criterion checks |
| `CountInformationConflict` | Identify conflicting acquired answers | Conditional irreducible subset after a completed deletion pass | Independent prefix feasibility and conflict controls |
| `plan_acquisition` cost bounds | Assess an interrupted search | Certified lower bound, sufficient upper bound and exact gap | Feasible-pair certificates and independent finite-histogram oracle |

The NARMS minor-species example contains several drug results per isolate. Its input rows are not independent studies. See examples/laboratory_use/README.md for source attribution and runnable commands.

## Sufficient reporting from a known histogram

| Public entry | User task | Result | Independent check |
|---|---|---|---|
| `plan_reporting` | Choose which known category-tail counts should accompany empirical MIC50/MIC90 | Minimum-cost sufficient disclosures under a completed search, or a verified sufficient fallback and cost bounds | Independent sufficient-reporting checks; independent exhaustive histogram/subset oracle |
| `verify_reporting` | Check a report without receiving its complete source histogram | Sharp remaining count ranges, criterion decisions and logical sufficiency | Independent histogram filtering; certificate and count-CSV round-trip tests |
| CLI `reporting-audit --reporting-plan` and `reporting_report.render_reporting_plan` | Produce and explain a shorter laboratory report | HTML before/after decisions, reusable count CSV, certificate JSON and compact status exports | End-to-end input, rational fraction, failure-isolation and installed-example checks |

The reporting laboratory supplies the complete histogram. The recipient supplies only summaries, questions and disclosed counts. Verification does not authenticate those inputs or confer a population or calibration guarantee. See [sufficient reporting](SUFFICIENT_REPORTING.md) for exact signatures, costs, optional limits and a complete example.


## Whole-distribution analysis and sample resolution

| Public entry | User task and calculation | Result or export | Check |
|---|---|---|---|
| CLI `distribution`; `distribution_workflow.analyse_distribution` | Describe all recorded categories and cumulative boundaries from summaries and/or counts | Sample, optional population and calibration layers; `distribution.csv`, JSON, configuration and HTML | Independent histograms; counts-only and variant controls; installed CLI examples |
| `distribution_workflow.distribution_problems` | Validate one distribution input and retain feasible interpretations | Problem mapping, normalized observations and rejected interpretations | Invalid input, rank, extrema and truthful-count controls |
| `distribution_resolution.maximum_resolvable_partition`; `--precision-pp` | Find the most detailed contiguous sample grouping satisfying both group and cumulative width requirements | Exact precision target, selected boundaries, count ranges and `sample_resolution` CSV rows | Exhaustive partitions, interval constraints, exact decimal boundary and tie tests |
| `joint_population.population_distribution`; `--population-method` | Bonferroni, directed conservative joint minP, or fixed all-range inference under iid sampling | CDF/category outer bounds, baseline, endpoint gap, precision and computation status | Rational enumeration, directed probability controls, range witness certificates and interrupted-search tests |
| `joint_population.update_population_distribution`; `--previous-output` | Add original-sample constraints while preserving saved population bounds | Validated update and intersection with previous outer bounds | Same-input/method validation; truthful-update and nesting controls |
| `distribution_report.render_distribution_html` | Explain ranges and assumptions without reconstructing a histogram | Distinct sample, population, calibration and resolution sections; all-cohort paging | Content/escaping tests and desktop/mobile report checks |

These functions are module interfaces rather than package-root exports. [Python examples](PYTHON_INTERFACE.md#describe-the-recorded-distribution-in-python) give imports and saved-update contracts; [the user guide](distribution-user-guide.md) gives CLI examples. The sample precision target is separate from confidence level and numerical population tolerance.

## Diagnostic, helper and compatibility interfaces

A callable used by a validation script, external Python caller or structural typing contract need not be invoked by the main command. These interfaces have explicit supporting roles:

| Interface | Role and scope |
|---|---|
| `joint_population.joint_report_pvalue`, `joint_minp_probability`, `max_compatible_statistic` | Floating point evaluation of the finite model for diagnostics and independent comparisons; not certified exclusion bounds. |
| `joint_population.rectangle_probability_bounds`, `box_pvalue_upper` | Directed probability enclosures supporting parameter-box exclusion. A surviving box need not contain an accepted point; endpoint precision also requires accepted witnesses. |
| `dro.wasserstein_1d` | Direct one-dimensional transport distance used by comparisons and numerical checks; does not supply calibration validity by itself. |
| `comparability.comparability_graph`, `matched_reference` | Helpers for historical external-data eligibility/reference scripts. They inspect retained histogram/range information; their output is not evidence that target-independent eligibility or exchangeability has been established. Current strict workflows require independently documented panels. |
| `comparability.TestedRange.fully_known` | Reports whether both bounds were marked as arising from censoring operators. This tested convenience property does not authenticate the original tested panel. |
| `conformal.split_unit`, `balanced_partition`, `straddling_studies` | Study-label normalization, deterministic allocation and overlap diagnostics in evaluation scripts. They cannot detect biological dependence hidden behind different labels or establish exchangeability. |
| `conformal.assign_partition` | Tested legacy deterministic partition interface; not the current connected-study allocation. |
| `utility.rank_tail_count_questions` | Single-interpretation count-width planning and validation helper; the robust variant combines declared interpretations. |
| `report_pages.DetailRenderer.__call__` | Structural callback signature for paginated report renderers. The protocol declaration is not an unexecuted analysis algorithm. |

The retained calibration adapter, its unit-allocation helper and `verify_width_identity.py` contain relevant helper calls. A production-only reference scan is therefore insufficient to declare these functions dead. None of these supporting roles creates a new statistical guarantee.
