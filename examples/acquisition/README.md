# Obtain only the additional counts your question needs

Version **1.0.0**. The first example is a constructed teaching example, not patient data or measured laboratory work. It uses the retained inputs in `examples/decision_planning`.

Ten isolates have MIC50=1 and MIC90=2 mg/L under ceiling ranks. We want to know whether fewer than 5% exceeded each of 2, 4 and 8 mg/L. With ten isolates, each question asks whether the corresponding count is zero.

If another request has no separate cost:

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/targets.csv --acquisition-plan --round-cost 0 --output-dir output/acquisition-one-at-a-time
```

The first request is the count above 4 mg/L. At most two counts are needed; the second depends on the first answer. The guaranteed declared cost is two units.

If preparing each request/export costs two units in addition to one per count:

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/targets.csv --acquisition-plan --round-cost 2 --output-dir output/acquisition-together
```

Request all three counts together. This costs five units, versus six for the best strategy restricted to one count per round. Fill the blank cells in `output/acquisition-together/requested_counts.csv` using the original records. For the tutorial only, the supplied answers are 1 above 2 mg/L and 0 above both 4 and 8 mg/L:

```text
mic-50-90 batch examples/decision_planning/summaries.csv --panels examples/decision_planning/panels.csv --targets examples/decision_planning/targets.csv --acquisition-plan --round-cost 2 --additional-counts examples/acquisition/completed.csv --output-dir output/acquisition-complete
```

The first question is answered no (1/10=10%); the other two are answered yes (0/10). The report requests no further counts. Open `report.html` in each output directory to compare the stages.

## A researcher reading actual published summaries

```text
mic-50-90 batch examples/published_summaries/summaries.csv --panels examples/published_summaries/panels.csv --targets examples/published_summaries/targets.csv --acquisition-plan --round-cost 1 --output-dir output/publication-requests
```

This uses the original-publication inputs and their existing source declarations. It does not invent answers to missing counts. The thirty-isolate veterinary example already answers its sample question; other questions may require a count from the publication authors' records. See the adjacent original-example README for source and rank conventions.

## A laboratory deciding what to include in its report

```text
mic-50-90 reporting-audit examples/acquisition/laboratory-counts.csv --panels examples/acquisition/laboratory-panels.csv --targets examples/acquisition/laboratory-targets.csv --acquisition-plan --round-cost 1 --output-dir output/laboratory-requests
```

These files contain the first cohort in the retained CDC/NARMS selection, without selecting it for a favourable outcome. Its source identifier and the copied panel are preserved. The planner receives only the derived summaries; the audit separately uses the complete counts to show what those summaries omit. The threshold questions are descriptive examples, not susceptibility classifications.
