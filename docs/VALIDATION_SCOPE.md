# What a validated result means

MIC-50-90 answers several different questions. A result must be interpreted with its
own mathematical target, assumptions, numerical status and evidence. Test counts and
software execution coverage do not establish a universal statistical guarantee. Exact
artifact hashes and execution receipts identify which implementation was checked.

| Layer | Target and required assumptions | Meaning and limit of the evidence |
|---|---|---|
| Deterministic sample bounds | All nonnegative integer histograms consistent with the declared sample size, panel, ranks, extrema, counts and reporting variants | Extremes concern the observed sample. Truthful input and the documented numerical domain are required. Histogram enumeration, attained witnesses, boundary/rounding controls and monotonicity test implementation; they do not establish representativeness of the sample. |
| Default iid population regions | Simultaneous category probability region and its projections, with independent identically distributed observations and a fixed panel/method/confidence level | Clopper-Pearson and the stated family correction supply the sampling argument. A truthful incomplete report retains the actual histogram among the compatible ones. Projections inherit the same event, but unrelated drugs, cohorts or data-selected methods do not automatically share that family guarantee. |
| Range-calibrated population regions | The method's stated finite-sample region, under its sampling and calibration assumptions | Its calibration and certificates have their own checks. A finite grid of exact coverage calculations is an implementation check, not exhaustive validation of all parameter values. |
| Joint-exact and range-hunter refinements | Conservative outer regions and, when achieved, bounded endpoint error | Exact sampling laws do not imply that numerical inversion finishes. Validity of retained bounds, `precision_reached`, completion status and time limit must be reported separately. An incomplete refinement cannot be described as a completed sharp inversion. |
| Study-unit calibration | Simultaneous containment of every declared target in a new exchangeable unit, with fixed reference, score and selection procedure | The ordinary split-conformal statement is marginal over calibration and the new unit. It is not conditional coverage for every fitted calibration, state or later year. Training separation and exchangeability are scientific assumptions, not facts established by labels or flags. |
| LR, MLE, Bayesian and other model scenarios | Results conditional on the specified likelihood, prior, shape or reference model | Local optimizer success is not a global optimality certificate. Asymptotic LR cutoffs and Bayesian credible intervals have different interpretations from exact frequentist confidence regions. Posterior Monte Carlo error and effective sample size concern computation, not population coverage. |

## Inputs and simultaneous families

`iid=true` records an analyst's declaration. It does not establish independence of isolates
from the same animal, farm, outbreak or clone, nor a probability sampling design. Recorded
MIC categories can be identified while exact concentrations within a category remain
unknown. Additional true counts from the same sample retain its denominator and can narrow
the admissible set; arbitrary changes of sample, method or confidence level require their
own justification. The numerical domain for weighted objectives is specified in
[PYTHON_INTERFACE.md](PYTHON_INTERFACE.md).

## Histogram coverage simulations

The unit of replication is one independently generated sample in a fixed configuration.
A success is containment of **all** declared proper contiguous ranges for that sample.
New configuration summaries report covering, completed, failed and attempted counts.
`coverage` retains the completed-run denominator for compatibility;
`coverage_over_attempted_replicates` is the descriptive fraction with both an available
result and containment among all attempts. Errors cannot be removed from the account.

For configurations without errors, `monte_carlo_interval` is a pointwise two-sided 95%
Clopper-Pearson interval for the **simulation coverage probability**, not a MIC fraction.
The additional plug-in standard error may be zero at all successes or all failures, while
the interval remains nondegenerate. Configurations with execution errors receive no such
coverage interval. Pooled fractions across different configurations are descriptive;
there is no ordinary iid binomial interval for that heterogeneous pool.

A one-sided diagnostic p-value below 0.001 flags undercoverage relative to 95%, retaining
the existing criterion. Its nonrejection is reported as "no undercoverage detected in the
examined configurations". The field `empirical_check_confirms_guarantee` is always false:
the simulation diagnostic does not prove the mathematical guarantee. No multiplicity or
equivalence claim across configurations is implied. See the amended
[evaluation protocol](../evaluation/PROTOCOL.md) and its preserved original for provenance.

The separate synthetic study-unit experiment has a different replication structure:
each repetition refits a calibration and evaluates 100 units sharing that fitted rule.
Its pooled fraction is descriptive. The 100 outcomes within a repetition must not be
treated as independent repetitions for Monte Carlo uncertainty; uncertainty about the
marginal procedure must use independent calibration-and-test repetitions.

## Temporal calibration evidence

The recorded NARMS retail *E. coli* assessment trains on 2017, calibrates on 2018 and tests
on 2019. A unit is a state-year; the same 13 states occur in calibration and test. This is a
temporal assessment within NARMS. Distinct year labels prevent exact label reuse, but do
not establish independent geographic units, exchangeability across years or transfer to
another monitoring system.

The preserved trained result covers 8 of 13 whole test units (61.54%); the uniform result
covers 11 of 13 (84.62%), against the manifest level 13/14 (92.86%). This is the
discrete rank level for a requested 90% level and 13 calibration units. The counts 1099/1105
and 1101/1105 concern individual targets. They cannot replace the whole-unit denominator.
These values come from `evaluation/results/external_calibration/retail-ecoli-{trained,uniform}/`
and remain unchanged. They are not a new calibration or a fresh run of a rebuilt artifact.

Unfavourable assessment results do not identify a unique biological cause or disprove a
theorem under its assumptions. They limit the demonstrated applicability of the fitted
procedure. A rule modified after inspecting 2019 requires a new independent evaluation;
the same year cannot certify that modification as an untouched holdout. Use the intended
roster and the assessment rules in [CALIBRATION_ASSESSMENT.md](CALIBRATION_ASSESSMENT.md).

## Formal and engineering checks

Lean formalizes the stated algebraic consequences under explicit hypotheses. It does not
verify the whole Python implementation, every report translation, floating-point arithmetic,
GUI or statistical sampling argument. A fresh compilation must identify its toolchain and
source. A Linux wheel test is not a native Windows executable test. A dependency or build
change needs artifact-specific evidence; a version number alone is insufficient.

For the supplied delivery, use the accompanying acceptance report and artifact receipts to
distinguish completed, queued, unavailable and historical checks. Do not assign earlier
coverage percentages, CI matrices or formal compilation results to new bytes without the
corresponding evidence. See [ENGINEERING_VERIFICATION.md](ENGINEERING_VERIFICATION.md).
