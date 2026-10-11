# Choosing counts for a laboratory report

Use this workflow when you have the complete category counts and want a shorter report that still answers specific questions about that collection. For example: do fewer than 5% of its isolates exceed each of three concentrations?

```text
mic-50-90 reporting-audit examples/sufficient_reporting/counts.csv --panels examples/sufficient_reporting/panels.csv --targets examples/sufficient_reporting/targets.csv --reporting-plan --output-dir output/sufficient-report
```

Open `report.html`. The section “Counts to include in your report” lists actual counts, the original denominator, the decisions they establish and whether minimum cost has been proved. Costs default to one per count. A query CSV supplied with `--decision-queries` can restrict the permitted concentrations and give nonnegative reporting costs. These costs describe the chosen reporting task; they are not measurements of work already performed.

The example contains ten observations, with MIC50=1 and MIC90=2 mg/L. Its three questions concern recorded values strictly above 2, 4 and 8 mg/L. Reporting one value above 2 and zero above 4 is sufficient: the first criterion is ruled out, and the other two are established. No additional count above 8 is necessary. The full histogram remains necessary for other questions not implied by this information.

The output includes:

- `reporting_counts.csv`: the selected counts in the format accepted by `batch --additional-counts`.
- `reporting_certificates.json`: original summary inputs, questions and selected counts. It does not contain the complete histogram.
- `results.csv`: reporting status, cost, number of count fields and whether optimality was established.
- `results.json`: complete calculations and the recipient's logical verification.

The recipient can check a certificate without obtaining the original histogram:

```python
import json
from pathlib import Path
from mic_50_90 import verify_reporting

document = json.loads(Path("output/sufficient-report/reporting_certificates.json").read_text())
for certificate in document["certificates"]:
    check = verify_reporting(certificate["specification"], certificate["criteria"], certificate["disclosures"])
    print(certificate["cohort_id"], check["sufficient"], check["decisions"])
```

Verification establishes what follows if the reported counts and metadata are correct. It cannot authenticate laboratory records. When no extra count is necessary, the certificate has an empty disclosure list; the count CSV has no rows for that cohort. Use the certificate check rather than passing an entirely empty count file to `batch`.

`plan_reporting(specification, histogram, criteria, queries=...)` provides the same calculation in Python. It requires an empirical summary specification and one nonnegative integer per panel category, summing to the declared n. A histogram inconsistent with every declared reporting interpretation is refused. `verify_reporting(specification, criteria, disclosures)` accepts the same exact counts or supported truthful count ranges as the returned-count interface.

For a single reporting interpretation and one integer decision boundary, the optimum follows from the boundary-count reduction implemented by sufficient_reporting. Other cases use a finite search. `--decision-plan-time-limit` and `--decision-plan-max-states` bound that search. An incomplete search retains a checked sufficient report, if one exists, but does not label it cheapest. If the permitted counts cannot establish the requested decisions, the result explains that restriction. Optional reporting failures preserve the basic analysis.

This workflow selects what to disclose **after the histogram is known**. `--acquisition-plan` selects what to request **before the answers are known**. Neither changes the collection or plans new susceptibility tests. A sufficient sample report does not imply population precision, whole-histogram recovery, new calibration coverage or preservation of unlisted questions.
