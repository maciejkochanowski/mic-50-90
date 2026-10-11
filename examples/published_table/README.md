# Published table example

This example asks: **Do fewer than 5% of the 2902 observations have recorded MIC strictly above 0.5 mg/L?**

With explicitly re-summarized MIC50 = 0.125 and MIC90 = 0.25 mg/L, the answer is unresolved: compatible counts are 0–290, or 0–9.99%. The additional published count is 85, giving 2.93% and resolving this sample-level question.

## Run

Install the version 1.0.0 wheel, then run these single-line commands from the extracted source/reproduction package:

```text
mic-50-90 batch examples/published_table/summaries.csv --panels examples/published_table/panels.csv --targets examples/published_table/targets.csv --output-dir output/published-summary
mic-50-90 reporting-audit examples/published_table/counts.csv --panels examples/published_table/panels.csv --targets examples/published_table/targets.csv --output-dir output/published-counts
```

Open `report.html` in each output directory. The first report shows the summary-only range and recommends obtaining the direct count above 0.5. In the second report, **Laboratory reporting audit** shows the actual answer 85, the known fraction 2.93%, and zero residual width after that answer. Both commands also save results.csv, results.json and configuration.json. No iid assertion is made, so population inference is explicitly unavailable. There is no calibration reference for this example.

## What was supplied

The factual counts come from the local Candida albicans row in [Table 1 of Delma et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11450473/#dlae153-T1), DOI [10.1093/jacamr/dlae153](https://doi.org/10.1093/jacamr/dlae153). This is the local collection, not the pooled EUCAST table. SOURCE.json records the transcription and provenance. The source article is CC BY-NC 4.0; its terms remain applicable to reproduced example material, separate from the software's MIT licence.

We choose ceiling ranks explicitly: 1451 and 2612. This is a new summary of the full published counts, **not proof of the original authors' finite-sample quantile convention**. Interior categories represent the reported-value scale; the two censored end categories are retained. The representative 128 encodes >64 and is not a measured value. This choice cannot affect the selected threshold of 0.5.

The independent check is `2902 − 2612 = 290` for the upper compatible count and `38 + 9 + 18 + 9 + 1 + 1 + 4 + 5 = 85` for the observed count. The reproduction package's `run_published_example.py` asserts agreement with the program and saves CHECK.json and RECEIPT.json.

This exploratory follow-up was added after the frozen researcher pilot. It does not replace the ten original refused tasks, estimate population prevalence or assign clinical susceptibility categories.
