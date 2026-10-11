# Synthetic calibration preparation example

This small teaching example has three calibration studies, two explicit panels per study and one future target study. It is not empirical validation. Three units support a maximum marginal level of 3/4; the example therefore requests 0.75. Real 90%, 95% or 99% requests need at least 9, 19 or 99 appropriate calibration units, respectively.

From the repository root:

```console
mic-50-90 calibration-prepare examples/calibration_preparation/counts.csv --panels examples/calibration_preparation/panels.csv --roster examples/calibration_preparation/roster.csv --metadata examples/calibration_preparation/metadata.json --level 0.75 --output-dir output/calibration-preparation
mic-50-90 batch examples/calibration_preparation/future-summaries.csv --panels examples/calibration_preparation/panels.csv --targets output/calibration-preparation/targets.csv --calibrations output/calibration-preparation/calibrations.json --output-dir output/calibration-application
```

Preparation reads only calibration counts, panel definitions, metadata and the independent roster. `future-summaries.csv` is used only by the later batch command. No target histogram is included.

The unit scores are approximately 0.3, 0.2 and 0. The fixed third rank yields a radius of approximately 0.3 log2 dilution steps. The tiny positive bisection resolution near zero is retained alongside the exact transport calculation.

Open each output directory's `report.html`. The preparation report records all six expected calibration cohorts, all three calibration units, two target cohorts and the explicit refusal state if any required input is damaged. See `docs/CALIBRATION_PREPARATION.md` for input requirements and limits.
