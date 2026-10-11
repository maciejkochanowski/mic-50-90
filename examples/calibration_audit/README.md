# A calibration assessment with retained failures

These four rows are synthetic. They illustrate unit accounting, not measured software effectiveness.

```text
mic-50-90 calibration-audit examples/calibration_audit/observed.csv --roster examples/calibration_audit/expected.csv --output-dir output/calibration-audit
mic-50-90 calibration-plan --level 0.95 --assurance 0.95 --calibration-units 9 --test-units 6 --output-dir output/calibration-plan
```

Expected audit: three intended units, two complete, one successful. Two of four planned target truths are contained; the missing reference remains in the denominator. No iid declaration is made, so the report has no binomial confidence bound. Width reduction includes the zero-gain second target in site A. See `docs/CALIBRATION_ASSESSMENT.md` for the contract and interpretation.
