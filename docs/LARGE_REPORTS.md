# Large batch reports

MIC-50-90 1.0.0 creates a static index and detail pages when a CSV batch contains
more than 50 cohorts. Open `report.html` to see the complete cohort list, each
status and refusal reason, and a link to the corresponding result. The detail
pages contain the same scientific sections, diagnostics and available audit
results. They provide links to the index and adjacent pages.

The same option applies to `batch` and `reporting-audit` (replace the file names with your own tables):

```console
mic-50-90 batch summaries.csv --panels panels.csv --targets targets.csv --output-dir results --report-page-size 50
mic-50-90 reporting-audit counts.csv --panels panels.csv --targets targets.csv --output-dir audit --report-page-size 50
```

Use a positive integer to select the maximum number of cohorts per detail page.
Use `--report-page-size 0` to request one HTML file, including for a large batch.
A batch that fits within the selected page size keeps the single-file
format. Pagination does not change the calculations or the numerical exports.

The index states accepted analyses and refusals against the entire batch. Each
detail page states both the entire-batch denominator and its own page denominator.
These denominators count cohorts. The isolate denominator is displayed within
each cohort's scientific results. Refusals remain in both appropriate cohort
denominators. Ordering follows the input record order, including refused records.

## Sharing and offline use

Copy `report.html` together with the `report-pages-*` directory referenced by its
links. Include `configuration.json`, `results.csv` and `results.json` when sharing
the reproducible analysis package. The index and detail pages work from local
files without JavaScript, a server or a network connection. The index includes
an inert JSON data element; it does not execute code. Browser Find can locate a
cohort in the complete index even if its detail is on another page.

Detail filenames use page ordinals, and in-page anchors use global record
ordinals. Cohort labels are escaped as text and never used as file paths or
anchors. Unicode, repeated labels and labels containing HTML or path separators
therefore preserve their record membership.

## Integrity and repeated rendering

The index links to `manifest.json` and `checksums.sha256` inside its detail folder.
The manifest gives every cohort's original identifier and status, its ordinal and
link, page ranges, global and page counts, and the byte length and SHA-256 of each
detail page. Manifest links resolve relative to the index directory. The same manifest is embedded in the index as
`script[type="application/json"]#report-pagination-manifest` for offline readers.
The checksum file covers the detail pages, manifest and index. Its paths are
relative to the directory containing the checksum file.

Every paginated render uses a newly created detail folder. The index is replaced
only after all new pages and integrity files have been written. If rendering a
detail page fails, an existing index continues to link to its previous pages.
Previous detail folders and unrelated files are not removed; an interrupted
render may leave an unlinked partial folder. Retain the currently linked folder
when managing old report copies.

Fresh folder names mean the index and manifest hashes can differ between two
otherwise identical runs. Detail-page hashes are reproducible for the same
records, order, renderer environment, page size and index filename; the manifest records the
exact bytes for each run. Pagination is an output transformation, not a new
scientific validation or a claim of improved human task performance.

## Python integration

The three-argument call is also accepted:

```python
from mic_50_90.report import render_batch_html

render_batch_html(records, configuration, "report.html")
render_batch_html(records, configuration, "report.html", page_size=100)
render_batch_html(records, configuration, "report.html", page_size=0)
```

`page_size` must be a nonnegative Python integer. Booleans, floating-point values,
negative numbers and strings are rejected before output is written.

The reusable `render_paginated_batch_html` helper in `mic_50_90.report_pages`
accepts a `render_page(records, configuration, destination, context)` callback.
For a single-file report, `context` is `None`. For a detail page,
`BatchPageContext.summary_html()` supplies explicit global and local denominators,
`navigation_html()` supplies local navigation, and `cohort_anchor(local_index)`
supplies the article's globally unique ordinal anchor. The callback remains
responsible for rendering the full cohort contents.
