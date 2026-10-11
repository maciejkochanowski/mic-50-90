# Original published MIC summaries

These inputs transcribe reported MIC50/MIC90 values and sample sizes. No full histogram is supplied to the analysis. Panels come from the source methods; declared interval geometry is a reporting model, not measured individual MIC. `provenance.json` identifies each source, location and assumption.

Run from the extracted examples directory or replace paths with its location:

```text
mic-50-90 batch examples/published_summaries/summaries.csv --panels examples/published_summaries/panels.csv --targets examples/published_summaries/targets.csv --output-dir output/published-summaries
```

Open `output/published-summaries/report.html`. `results.csv` and `results.json` retain unrounded endpoints. `configuration.json` preserves all reporting variants and input hashes.

| Cohort | Source input | Result for recorded values | Interpretation |
|---|---|---|---|
| extension-06, human | 507 clinical C. parapsilosis sensu stricto isolates; fluconazole MIC50=1, MIC90=4 mg/L | Above 2 mg/L: 51–254/507 (10.06–50.10%). Above 4 mg/L: 0–51/507 (0–10.06%). | Under every declared rank variant at least 51 recorded values exceed 2 mg/L. The summaries do not establish a tail of at most 10% above 4 mg/L. |
| extension-11, veterinary | 16 canine S. pseudintermedius isolates; chlorhexidine MIC50=0.781, MIC90=1.562 mg/L | Above 1.562 mg/L: 0–2/16 (0–12.5%). | At most two recorded values exceed the threshold; a 10% criterion remains unresolved across the declared variants. |
| extension-13, veterinary, source-defined ranks | 30 multidrug-resistant S. pseudintermedius isolates; shampoo formulation, chlorhexidine-equivalent MIC50=MIC90=0.625 mg/L | Above 0.625 mg/L: 0–3/30 (0–10%). | The sample criterion <=10% is supported under the source's minimum-inhibiting-fraction definition. This is a formulation result, not efficacy of chlorhexidine alone. |

The first two cases use analyst-declared ceiling and adjacent ranks because the finite-sample convention was not established in the paper. Their union is a limited sensitivity analysis; it does not cover every possible quantile definition. The third source explicitly defines the lowest concentration inhibiting the specified fraction of isolates, implying ceiling ranks. None of these convenience collections is automatically an iid population sample. No clinical susceptibility conclusion is inferred from the descriptive thresholds.

Sources: https://doi.org/10.1186/s12879-026-12598-y (Table 4); https://doi.org/10.1002/vms3.71162 (Table 4, Total n=16); https://doi.org/10.3390/microorganisms14081660 (Table 1 and statistical definition).

These are three of the five numerical outcomes in the frozen twenty-paper extension. The complete register retains all 15 refusals and does not replace the original pilot's ten refusals. Search metadata and the frozen protocol accompany the scientific reproduction package.
