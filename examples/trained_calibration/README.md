# Trained calibration, MIC-50-90 1.0.0

This small synthetic example demonstrates separate training, calibration and target roles. It is not an empirical validation. Two complete training units determine references and scales. Three calibration units support the requested 75% marginal level; they cannot support 95%.

Run these commands from the extracted package directory:

```text
mic-50-90 calibration-prepare examples/trained_calibration/counts.csv --panels examples/trained_calibration/panels.csv --roster examples/trained_calibration/roster.csv --metadata examples/trained_calibration/metadata.json --reference-method training --transport-scaling training --level .75 --output-dir output/trained-preparation
mic-50-90 batch examples/trained_calibration/summaries.csv --panels examples/trained_calibration/panels.csv --targets output/trained-preparation/targets.csv --calibrations output/trained-preparation/calibrations.json --output-dir output/trained-analysis
```

Open both output report.html files. Each reference is [0.7, 0.15, 0.15], and each learned scale is approximately 0.2 log2 dilution steps. The preparation report shows the dimensionless calibration radius and the applied radius for each panel. The analysis report keeps sample, population and calibrated conclusions separate. The example has no iid population declaration.

For real data, declare collection units before assigning roles, record all categories including zeros, and replace the synthetic provenance with documented sources. At least two complete training units are needed. Calibration and target units must be suitable for the stated exchangeability assumption. Do not split a dependent collection into invented independent units. Target counts do not belong in the preparation input.

Manifest 1.3 is a data-contract version. The software version remains 1.0.0. Without these two options, calibration-prepare retains its uniform, unscaled default and emits manifest 1.2.
