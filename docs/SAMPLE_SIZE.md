# Sample size and useful precision

The CSV workflow for MIC50/MIC90 accepts two observations if the ranks and categories are compatible. It computes exact sample bounds under the declared information even at this size. That does not mean the bounds answer every scientific question.

Use the displayed interval and criterion to judge whether the available information is sufficient. There is no single minimum useful sample size:

- With ceiling ranks, MIC90 alone permits up to n-ceil(0.9n) recorded values above that concentration. At n=20 and n=100 this gives 0–10%. Increasing n does not recover an unreported count.
- If an exact additional count establishes zero exceedances, the two-sided 95% Clopper–Pearson interval has upper endpoint 1-0.025^(1/n). It is 16.84% at n=20 and 3.62% at n=100. Under iid sampling and for one threshold, the endpoint first falls below 5% at n=72. A nonzero count or another confidence level changes this calculation.
- Multiple threshold questions require the appropriate family adjustment. A sample conclusion and a source-population confidence statement have different meanings.
- Calibration counts independent exchangeable units, not isolates. A finite rank at 90% needs at least nine calibration units; at 95% it needs nineteen. Reference and evaluation units are additional. Enough units do not by themselves prove exchangeability or useful narrowing.

The stated zero-count calculation follows directly from the formula above; tests/test_exact_population.py checks the binomial construction. These examples are reporting and precision calculations, not clinical sampling recommendations. Counts-only distribution inputs can contain one isolate; paired MIC50/MIC90 summaries require compatible distinct ranks. Neither technical minimum establishes useful population precision.

For a new calibration study, use `calibration-plan` and the [assessment guide](CALIBRATION_ASSESSMENT.md). At 95% assurance, 29/59/299 iid calibration units are the minimum for maximum-score PAC targets of 90%/95%/99%. The same numbers are optimistic held-out test minima only when every test unit succeeds. These are separate samples and statements; neither follows from collecting more isolates within a unit.
