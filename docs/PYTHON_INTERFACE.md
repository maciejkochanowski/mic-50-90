# Python interface: MIC-50-90 1.0.0

Use the same versioned input dictionary as the JSON command line. The example below runs from the extracted source archive; the wheel installs the library and command line, while examples are supplied separately.

    import json
    from pathlib import Path
    from mic_50_90 import analyse_spec
    from mic_50_90.report import render_html

    spec = json.loads(Path("examples/empirical.json").read_text(encoding="utf-8"))
    result = analyse_spec(spec)
    Path("result.json").write_text(
        json.dumps(result, indent=2, allow_nan=False), encoding="utf-8"
    )
    render_html(result, "report.html")

[Public functions](PUBLIC_FUNCTIONS.md) maps package exports and supported module interfaces to user tasks, outputs and validation. The method documents and PUBLIC_FUNCTIONS.md explain assumptions and map numerical families to checks. Invocation details belong here and in the module signatures.

## Input and failure contracts

JSON quantiles retain a ceiling-rank default when neither a rank nor a convention is supplied. For published summaries, state the actual or explicitly assumed rule. CSV instead requires rank_convention. A missing tested panel is never recovered from an observed minimum and maximum.

parse_spec checks the data used by the analysis before calculation; it does not automatically run the separately supplied JSON Schema. Invalid optional calibration can therefore stop that call, whereas the CSV workflow isolates that layer. Malformed or duplicate reporting variants are fatal input errors; only a valid variant proved infeasible can be excluded. A solver failure cannot justify removing a possible interpretation. Direct QuantileSummary construction validates exact integer ranks and category indices; analysis also checks them against the denominator and panel.

Sample sizes, counts and ranks must be exact integers, no larger than 9,007,199,254,740,991. Integral decimal and exponent forms such as `20.0` and `2e1` are accepted by the runtime parser. Automatic ranks use the exact declared decimal probability: n=50 and p=0.14 gives rank 7. The JSON command preserves numeric tokens for these fields. In Python, use a decimal string when the supplied digits matter; a float already rounded by the caller cannot recover its original digits. A quantile probability can also be a decimal string in JSON. Export retains such precision as a string when a float would lose it.

Panel and optional-analysis flags require actual booleans, not strings or numbers. Cohort, panel, variant and unit identifiers cannot have surrounding spaces. Reference dictionaries reject unknown category labels; omitted valid categories explicitly have weight zero. Finite nonnegative reference weights are normalized without first summing their original scale. File-writing commands reject input/output collisions before writing; direct callers writing their own files must choose separate paths themselves.

Population mode asserts an iid categorical sampling model; it cannot verify the sampling design. It enables profile likelihood by default and leaves Bayesian sensitivity off. CSV population analysis disables both optional fits. Invalid optional fit settings, including null numeric settings, and fit failures are returned as unavailable while completed exact-count results remain available. See [missing information](MISSING_INFORMATION.md) for the distinctions.

## Direct numerical use

empirical_bounds calculates sharp recorded and latent sample bounds. It requires an exact positive integer n and a finite threshold. EmpiricalProblem count optimization accepts finite integral objective coefficients; an equality count must be an exact integer, never a boolean, fractional or nonfinite value. It does not silently truncate fractional linear objectives into counts. Separate transport and scenario calculations can use real-valued linear objectives. exact_count_confidence accepts variants with the same n and panel, canonical integral interval-row constraints and a monotone binary tail objective. Unsupported coupled constraints or other objectives raise ValueError; deterministic integer bounds remain available separately. probability_components contains the confidence set; its hull contains only the overall endpoints.

order_event_probability and log_order_event_probability accept one or two valid order-statistic records and finite nonnegative category weights. Two records require increasing ranks and probabilities and nondecreasing categories. Optional extrema refer to observed categories. A positive probability can underflow to zero while the log interface remains finite. Numerically difficult events can invoke a slower positive recurrence; these floating-point results are not certified interval arithmetic.

Profile and Bayesian outputs are sensitivity analyses, not replacements for exact iid confidence sets. The direct profile target must be a finite binary one-dimensional objective matching a successful finite normalized MLE. Sample size and grid_size must be exact integers, with grid_size at least 11; fractional settings are not silently truncated. Bayesian Monte Carlo error of the mean uses sqrt(sum(w_i² (theta_i−mu)²)) with normalized importance weights and weighted mean mu. Its posterior interval and Monte Carlo error answer different questions; low effective sample size requires attention.

## Calibration and returned counts

For a new manifest, pass an explicit calibration_contract, unit labels and calibrate_on="units", unit_aggregation="max" to calibrate_wasserstein_manifest. The Python compatibility default is cohorts; the CLI builder defaults to units. The builder rejects a missing contract. Existing 1.0/1.1 manifests remain readable for diagnostics, but do not establish a new guarantee. To migrate, return to the original calibration scores and explicitly declare the reference, score, target functional and study-unit semantics; do not infer a missing contract from a stored radius. WassersteinCalibrationManifest stores the record; validated builders and application checks establish its contract. The contract's unit_definition is authoritative; the separate compatibility keyword cannot override it. The certified marginal level is `rank / (m + 1)`, where `m` is the calibration-unit count; tied scores do not increase that level. Median aggregation does not establish the unit-maximum guarantee.

split_conformal_radius(scores, alpha) takes error probability alpha and returns (radius, rank). Planning and preparation instead take coverage level=1−alpha. plan_calibration returns requirements, not achieved coverage. prepare_calibration uses complete histograms and an independent intended roster; audit_calibration retains missing held-out results in the denominator. A valid hash or constructor does not establish exchangeability.

analyse_with_counts(raw_spec, additional_counts, *, iid=False, confidence=0.95, calibration=None) accepts an empirical original specification. Each record has threshold, unit and n, with optional source, and exactly one answer form: count; count_min/count_max; or percentage/decimal_places/rounding_rule; omit cohort_id in this Python call. Supply all accumulated truthful recorded-tail counts, keeping the same cohort, panel and denominator. An impossible same-sample answer raises an error. A calibration-only conflict preserves updated sample bounds; optional numerical refinement failure preserves the original results with additional_information.status="unavailable". See [returned counts](RETURNED_COUNTS.md) and [calibration preparation](CALIBRATION_PREPARATION.md).

## Plan counts that resolve sample criteria

```python
from mic_50_90 import plan_decisions

plan = plan_decisions(
    spec,
    [{"threshold": 4, "unit": "mg/L",
      "decision_operator": "<", "decision_fraction": "0.05"}],
    queries=None,
    additional_counts=None,
    time_limit_seconds=5.0,
    max_states=5000,
)
result["decision_plan"] = plan
render_html(result, "report-with-plan.html")
```

The signature is `plan_decisions(specification, criteria, *, queries=None, additional_counts=None, time_limit_seconds=5.0, max_states=5000)`. Use the empirical input specification and a nonempty list of explicit threshold/unit/operator/fraction dictionaries. Decimal strings preserve the exact criterion. Each query dictionary contains threshold, unit and a positive cost in one common acquisition unit. `queries=None` allows every internal recorded cut at unit cost; `queries=[]` allows none. Equivalent cuts cannot be listed twice. This API has no population, latent-concentration or calibrated-decision planning mode.

Pass all obtained counts in `additional_counts`, using the count records described above. They condition the original sample; they do not increase n. The result's scope is `recorded_sample_decisions`. Status is `already_resolved`, `optimal`, `impossible` or `incomplete`. A complete adaptive policy has a root, nodes, exact integer tail-count branch ranges and terminal decision vectors. An incomplete search can return a verified fixed-order plan and upper bound without claiming optimality. `worst_case_cost_exact` preserves rational cost; `fixed_plan_cost` is a baseline unless `fixed_plan_optimality_verified` is true. An impossibility witness contains two compatible histograms agreeing at all allowed cuts but disagreeing on a criterion.

Invalid criteria, costs, settings or inconsistent observations raise an input error in direct Python use. The optional CSV integration instead preserves valid base results and records an unavailable-plan reason. See [decision planning](DECISION_PLANNING.md) and its [worked examples](../examples/decision_planning/README.md).

## Counts in one or several requests

`plan_acquisition(specification, criteria, *, queries=None, additional_counts=None, round_cost=0, time_limit_seconds=5.0, max_states=5000, max_batch_size=None)` uses the same explicit recorded-sample criteria as `plan_decisions`. Query costs and the additional per-request cost are nonnegative and must remain representable in the numeric report. Zero marginal count cost models an export that can supply several counts for the same effort. `max_batch_size=1` restricts each request to one count.

`next_questions` lists the counts to request together. `policy` is the complete acquisition tree or a verified sufficient fixed-batch fallback. `optimality_verified` distinguishes an optimum from a sufficient bound after an incomplete search. No policy is claimed if the search ends before finding a sufficient request. `max_rounds` and `max_counts` are separate worst-case bounds. Planning concerns truthful counts from the original sample and does not add a population or calibration guarantee. See `examples/acquisition/README.md` for a complete CSV round trip.

`counts_from_percentage(percentage, *, n, decimal_places, rounding_rule)` returns inclusive integer endpoints using exact rational boundaries. See RETURNED_COUNTS.md for rounding rules. Both planners accept previous count ranges; requested future counts remain exact. Acquisition results also contain cost_lower_bound, cost_upper_bound, cost_gap, their `_exact` rational counterparts and a feasible-pair lower_bound_certificate. A zero gap establishes cost only, and does not mark an interrupted search complete.


## Describe the recorded distribution in Python

```python
import json
from copy import deepcopy
from pathlib import Path
from mic_50_90 import __version__
from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.distribution_report import render_distribution_html

raw = json.loads(Path("examples/distribution/summaries.json").read_text())
result = analyse_distribution(raw, precision_pp="10")
render_distribution_html({"software_version": __version__, "cohorts": [result]},
                         "distribution.html")
```

`analyse_distribution(raw, *, population_method="bonferroni", population_time_limit=30.0, population_tolerance_pp=0.01, precision_pp=None, previous_analysis=None, population_precision_pp=None, population_count_plan=False, population_minimum_bins=None, population_planning_time_limit=10.0)` accepts the distribution input described in [the user guide](distribution-user-guide.md). It does not use `analyse_spec`'s population-mode switch: the input declares `iid` and `confidence_level`. Without iid, sample bounds remain available and population inference is unavailable. Counts-only inputs need no quantile convention. Supplied quantiles require explicit ranks or conventions. `precision_pp` is an exact decimal sample-width target, distinct from numerical population tolerance. Use strings to preserve entered decimal digits.

`population_precision_pp` requests a statistical width in percentage points.
`population_count_plan=True` searches additional same-sample counts;
`population_minimum_bins` fixes the requested minimum number of groups, and
`population_planning_time_limit` limits that search. Confirmed and still possible
partitions are reported separately. An unfinished search does not establish a
minimum cost or that the requested precision is impossible.

The result contains `sample`, `population`, `calibration` and `resolution`, plus original metadata, retained/rejected variants and numerical status. Category and cumulative ranges are projections of joint constraints; arbitrary endpoint combinations need not be jointly feasible. Optional failure does not turn an unavailable layer into a sample refusal.

A saved Python update uses the previous input and result explicitly:

```python
previous = {"input": deepcopy(raw), "result": result,
            "population_method": "bonferroni"}
updated_raw = deepcopy(raw)
updated_raw.setdefault("additional_counts", []).append(
    {"threshold": 1, "unit": "mg/L", "n": 20, "count": 8,
     "source": "verified original-sample records"}
)
updated = analyse_distribution(updated_raw, precision_pp="10",
                               previous_analysis=previous)
```

The original input must be identical except for appended truthful counts; retain earlier count rows in order. The population method and confidence level cannot change. Numerical budget, numerical tolerance and requested sample precision may change. Saved population outer bounds are intersected with the new bounds. The CLI equivalent reads `configuration.json` and `results.json` through `--previous-output`; these files must come from the same original analysis.

For direct numerical use, `distribution_problems(raw)` returns the feasible `EmpiricalProblem` mapping, normalized observations and rejected interpretations. `distribution_resolution.maximum_resolvable_partition(problems, *, precision_pp)` finds the maximum number of contiguous sample groups meeting both grouped-share and cumulative-share widths. It supports integral contiguous-category constraints and unites all retained interpretations before assessing widths. Equal-size partitions use the earliest boundary sequence.

`joint_population.population_distribution(problems, *, method="bonferroni", confidence_level=0.95, time_limit_seconds=30.0, tolerance_pp=0.01, include_intervals=False, questions=(), width_target_pp=None)` returns conservative population CDF/category bounds. `include_intervals=True` adds every contiguous recorded-category projection. `questions` supplies supported direct tail certificates to joint-exact; it is not the user-facing target format. `width_target_pp` permits task-based stopping for range-hunter only. `update_population_distribution(previous_problems, problems, previous_result, **options)` additionally validates original constraint retention and preserves saved bounds. These direct calls do not check a study's iid design. The joint method's `precision_reached`, endpoint gap and status must be read together; timeout and `precision_unresolved` retain unresolved regions.

Choose `method="range-calibrated"` for the fixed simultaneous construction over all contiguous recorded MIC ranges. The workflow argument is `population_method="range-calibrated"`. Choose the method before inspecting comparative widths. Its `range_witnesses_checked` counts additional compatible histograms checked for inward population projections. `precision_reached` can be true while `compatible_histogram_search_complete` is false: verified endpoint brackets can make full enumeration unnecessary. A false precision flag does not invalidate the retained conservative bounds. The configurable tolerance concerns numerical endpoint error, not a required statistical interval width. [Method and proof](range-population-method.md).

`joint_report_pvalue`, `joint_minp_probability` and `max_compatible_statistic` are floating-point evaluation/validation interfaces, not certified interval bounds. `rectangle_probability_bounds` and `box_pvalue_upper` implement directed numerical enclosures used by the conservative projection. See [the mathematical specification](joint-distribution-method.md) for their domain and proof; do not substitute an ordinary floating p-value for a box-exclusion certificate.

The fourth available method is `range-hunter`. It uses event-dependence bounds
for a fixed simultaneous range family and retains unresolved regions. Its
`width_goal` and `precision_reached` answer different questions: a useful width
can be certified without resolving every endpoint to the numerical tolerance.
Choose the construction before inspecting comparative results.

Distribution `targets` accept either `threshold`, or `start_category` and
`end_category` naming whole recorded categories, plus `unit` and optional paired
`decision_operator`/`decision_fraction`. Both endpoint categories are included.
Sample decisions use exact integer bounds; population and calibrated decisions
project their respective simultaneous regions. These category-range questions
do not extend the sufficient-reporting theorem for strict-tail questions.
