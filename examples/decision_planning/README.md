# Plan the counts needed to answer a question

This constructed example uses ten observations, ceiling-rank MIC50=1 and MIC90=2 mg/L. It asks separately whether fewer than 5% of the recorded values exceed 2, 4 and 8 mg/L. These are descriptive sample criteria, not clinical breakpoints or population conclusions. Version: **1.0.0**.

From the extracted example directory's parent, run:

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/targets.csv --decision-plan --output-dir output/decision-plan
```

Open `output/decision-plan/report.html`. Initially all three criteria are undetermined. The plan asks for the count **above 4 mg/L** first. At most **two counts** are needed to resolve all three criteria, compared with three counts requested together. With ten observations, a tail below 5% requires zero exceedances. The first count can be zero or one. Zero settles the criteria at 4 and 8 mg/L; one settles those at 2 and 4 mg/L. Only the remaining extreme requires a second count.

To enter the tutorial's first answer, run:

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/targets.csv --decision-plan --additional-counts examples/decision_planning/returned-count.csv --output-dir output/decision-after-count
```

The original denominator remains ten. A count of zero above 4 mg/L leaves one count to request, above 2 mg/L. Replace `returned-count.csv` with `complete-counts.csv` for the final tutorial result: the criterion at 2 mg/L is contradicted; those at 4 and 8 mg/L are supported; no further count is needed. In real work, enter only verified counts from the same original cohort, keeping all previous answers in the file. Do not collect a new sample to answer an old-sample count query.

Costs can differ. The following command has only two target criteria. The intermediate count costs one unit, whereas either target count costs ten:

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/weighted-targets.csv --decision-plan --decision-queries examples/decision_planning/weighted-queries.csv --output-dir output/decision-weighted
```

The optimal worst-case acquisition cost is **11 units**, compared with **20** for the minimum sufficient fixed set. These prices illustrate a mathematical possibility; they are not measured laboratory costs. Sequential requests can also incur delays that this fixed-cost model does not represent.

`results.json` retains the complete branching policy and exact rational costs. [Decision planning](../../docs/DECISION_PLANNING.md) describes restricted queries, incomplete searches and impossibility certificates.
