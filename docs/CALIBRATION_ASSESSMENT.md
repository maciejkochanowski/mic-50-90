# Plan and assess a calibration

A nominal coverage level and a successful evaluation answer different questions. `calibration-plan` calculates how many independent units a design needs. `calibration-audit` checks a fixed procedure against a separate intended roster. Both commands write HTML reports and retain unrounded values in JSON.

## Plan the units before collecting outcomes

```text
mic-50-90 calibration-plan --level 0.95 --assurance 0.95 --calibration-units 9 --test-units 6 --output-dir output/planning
```

For 95% coverage, nineteen exchangeable calibration units are the minimum for a finite ordinary split-conformal rank. This is a marginal statement averaged over calibration and a future unit. It does not mean that every fitted calibration achieves 95%.

The separate PAC calculation asks whether the fitted rule reaches the target with a specified probability over iid calibration samples. At 95% coverage and 95% assurance, at least 59 calibration units are required when using their maximum score. The planner reports the smallest qualifying rank for a supplied larger sample; it does not upgrade an existing manifest. This order-statistic result is established theory [Vovk, 2012](https://proceedings.mlr.press/v25/vovk12.html).

The best-case test requirement is different. If every test unit succeeds, 59 iid held-out units are needed for a one-sided 95% Clopper–Pearson lower bound to reach 95%. This is an optimistic minimum, not a power calculation or a rule for stopping after favourable results. At coverage targets of 90% and 99%, the corresponding marginal minima are 9 and 99; the PAC and zero-failure test minima at 95% assurance are 29 and 299.

## Prepare a separate intended roster

Create `expected.csv` before inspecting evaluation outcomes, with one row for each intended `unit_id,cohort_id,target_id`. A cohort belongs to exactly one unit. For a manifest covering every drug and panel cut, include every such target. An observed-results table alone cannot establish completeness.

Create `observed.csv` with the same identifiers and these fields:

| Field | Meaning |
|---|---|
| `status` | `ok` or `unavailable` |
| `truth` | Known recorded-category tail fraction, on the 0–1 scale |
| `lower`, `upper` | Unrounded interval endpoints, on the 0–1 scale |
| `reason` | Required explanation for an unavailable result |
| `baseline_lower`, `baseline_upper` | Optional paired sharp-sample endpoints for the same truth |
| `truth_count`, `original_n` | Optional paired integers; their ratio must match `truth` |

A missing planned row remains unavailable. A duplicate, foreign identifier, invalid interval or inconsistent count stops the audit. An unavailable row may leave numerical cells blank. Supplied baselines must contain the truth, and calibrated intervals must be nested within them. Preserve the original denominator.

```text
mic-50-90 calibration-audit examples/calibration_audit/observed.csv --roster examples/calibration_audit/expected.csv --output-dir output/assessment
```

This example is synthetic. It includes a missed truth and an unavailable reference: only one of three intended units succeeds. The exported `units.csv`, `cohorts.csv` and `targets.csv` distinguish the denominators. `audit.json` retains exact identifiers; CSV neutralizes spreadsheet formula-like labels. `configuration.json` records input hashes; `intended-roster.csv` preserves the requested task.

## Interpret the result

Operational success requires availability **and** containment of every planned target in a unit. The report separately gives complete units and containment among them. Many successful cuts cannot compensate for a missed target in a whole-unit claim. Widths include zero gains and are averaged within complete units before averaging across units. The paired-width denominator is explicit.

By default the audit is descriptive. Add `--iid-units --procedure-frozen` only when the design justifies iid test units and the procedure and test size were fixed before outcomes. These flags record declarations, not verified facts. They enable a one-sided binomial lower bound for operational success over **all** intended units. Exchangeability alone is not an iid declaration.

`--manifest path.json` checks manifest 1.2 or 1.3, its tail-event scope, exact calibration/test label overlap and stated level. Tail rows cannot verify whole-distribution containment. `--training-units path.json` accepts a JSON list and checks known training overlap. Neither check detects biological overlap hidden behind different identifiers. Manifest 1.3 also supplies training labels for the exact-overlap check. Without these labels or a separate training roster, the report states that training separation was not checked.

Comparison tolerance defaults to zero. If needed, specify a numerical tolerance prospectively through `--tolerance` (at most 0.000001). It is saved and displayed. It cannot be used to convert substantive misses into successes. `--delimiter comma|semicolon|tab` declares the input separator.

Endpoint arithmetic is handled separately. A public solver can serialize an upper bound as 1.0000000000000002, or reverse a point interval by a few floating-point units. Domain excursions of at most 1e-12 are clipped to [0,1]; reversed endpoints at most 1e-12 apart are sorted to their conservative hull, without using the truth. Larger errors are rejected. Truth values are never normalized. Every correction, its raw value and its target identifier are saved in `audit.json` and `numeric-corrections.csv`; input hashes retain the source file identity. The report displays the correction count and both numerical limits. Valid in-domain intervals are unchanged. Width reductions are expressed in percentage points, not relative percentages.

Ranks within eight floating-point units of an integer use that integer. This handles literal levels and complements such as `1-level` consistently; it is an arithmetic boundary rule, not a change in requested statistical coverage. The 27 September empirical ranks are unchanged by this repair.

The audit checks supplied intervals against supplied truths; it does not create calibration scores or establish source-panel validity. Reference and score construction still require a documented independent procedure. Source-specific reproduction scripts illustrate that work.
