# Answer a laboratory question with MIC-50-90 1.0.0

Start with a question about the isolates already tested, for example: **Were fewer than 5% above 8 mg/L?** This is a descriptive concentration threshold. It is not automatically a clinical resistance breakpoint.

## Read published summaries

```text
mic-50-90 batch examples/laboratory_use/published/summaries.csv --panels examples/laboratory_use/published/panels.csv --targets examples/laboratory_use/published/targets.csv --output-dir output/new-publications
```

The three source inputs give the following compatible counts above their reported MIC90:

| Source and tested isolates | Threshold | Compatible count | Interpretation |
|---|---|---|---|
| 121 clinical K. pneumoniae; cefiderocol | 8 mg/L | 0–12 (0–9.92%) | A tail below 5% is not established; obtain the count above 8 mg/L. The source names higher-value interpolation; the explicit ranks are 61 and 109. |
| 23 clinical C. tropicalis; fluconazole | 64 mg/L | 0–2 (0–8.70%) | A count of 0 or 1 would support <5%; a count of 2 would exclude it under the declared ranks. |
| 112 bovine S. uberis; ampicillin | 0.5 mg/L | 0–11 (0–9.82%) | The summaries do not establish <5%; obtain the number above 0.5 mg/L. |

The latter two use analyst-declared ceiling and nearest-integer ranks, which coincide for these sample sizes. Their papers do not establish a finite-sample rank convention. Panels are independently documented by the named manufacturers. `published/provenance.json` contains DOI, source location and assumptions. These inputs start from published summaries, not a re-summarised histogram. They are three numerical outcomes in a new twenty-paper screen; the full scientific package also retains seventeen refusals.

## Enter a count, a range, or a rounded percentage

```text
mic-50-90 batch examples/laboratory_use/returned/summaries.csv --panels examples/laboratory_use/returned/panels.csv --targets examples/laboratory_use/returned/targets.csv --additional-counts examples/laboratory_use/returned/additional-counts.csv --output-dir output/returned-ranges
```

This constructed example has 200 records, MIC50=1 and MIC90=4 mg/L on point categories 1, 2 and 4 mg/L. It asks whether fewer than 12.5% exceed 1 mg/L. The three truthful answer forms are an exact count of 24, a range of 23–24, and 12% rounded to zero decimal places by `half_up`. Each supports the sample criterion. The fourth row deliberately supplies a contradictory zero count, showing the refusal and correction advice. It is not a biological observation.

Use the original denominator. Fill exactly one answer form per row. A range means every integer between its endpoints remains possible. Do not select a rounding rule merely because it produces a preferred conclusion. [Returned information](../../docs/RETURNED_COUNTS.md) explains ties, later refinements, contradictions and separate statistical guarantees.

## Choose what to include in a laboratory report

```text
mic-50-90 reporting-audit examples/laboratory_use/laboratory/counts.csv --panels examples/laboratory_use/laboratory/panels.csv --targets examples/laboratory_use/laboratory/targets.csv --report-page-size 10 --question-time-limit 0 --output-dir output/minor-species
```

These sixty cohorts come from FDA NARMS minor-species data: 195 distinct isolates, with several drug results from the same isolate. They are not sixty independent studies. Open `report.html` and follow its page links. The zero question-search budget keeps the example quick and explicitly leaves the optional one-question search incomplete; basic intervals and reporting comparisons remain available. Increase the budget to rank a single additional count.

For costs of obtaining several counts together, add `--acquisition-plan --round-cost 1`. Costs are declared units chosen by the user. They are not measured staff time. The planner limits the worst possible remaining cost; it does not guarantee the cheapest result for every realised histogram. An incomplete search reports a verified cost interval when available, together with a sufficient request.

Source: [FDA data](https://www.fda.gov/animal-veterinary/national-antimicrobial-resistance-monitoring-system/integrated-reportssummaries); Dessai et al., *Sheep & Goat Research Journal* 39 (2024), 20–34, [methods and panel identification](https://www.sheepusa.org/wp-content/uploads/2025/05/2024-Combined.pdf). Full selection and overlap checks are retained in the reproduction package. No population or calibration claim is made for this example.
