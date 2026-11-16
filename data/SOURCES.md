# Sources of the supplied software examples

This directory records provenance and rights. The runnable inputs are in `examples/`; the inputs, scripts and result tables of the article's evaluation are in `evaluation/`, with their sources in `evaluation/data/README.md`.

| Example | Source record supplied with the input |
|---|---|
| Published summary inputs | `examples/published_summaries/provenance.json` and its README identify each DOI, table, panel and analyst-declared rank convention. |
| Laboratory published-summary inputs | `examples/laboratory_use/published/provenance.json` identifies source tables and panel evidence. |
| Canine staphylococci, ampicillin and chloramphenicol | `examples/biological_cases/` JSON files cite Table 1 of DOI 10.3389/fvets.2024.1512582 and distinguish source values from panel/rank assumptions. |
| Pneumococcal penicillin groups | The `examples/biological_cases/penicillin-*` inputs contain their source DOI, table and population assumptions. |
| Counts extracted from other publications | `examples/publication_review/README.md` and the JSON inputs retain DOI links and the exact count statements used. |
| Delma et al. histogram and returned counts | `examples/published_table/SOURCE.json` and `examples/returned_counts/SOURCE.json` identify the factual row, source hash and CC BY-NC 4.0 terms, DOI 10.1093/jacamr/dlae153. |
| NARMS laboratory reporting | `examples/laboratory_use/README.md` attributes the selected aggregate counts to FDA NARMS and identifies the methods and panel source. |
| Evaluation count tables (FDA animal-pathogen, NORM 2024, NARMS, FSIS) | `evaluation/data/README.md` identifies each source, the derived count tables and their terms. |
| Controlled calibration, decision and reporting examples | The corresponding example README or JSON metadata identifies constructed inputs and the purpose of the check. |

Source observations and analyst choices are separate. A panel representative is a coding convention, not an observed concentration; a stated rank sensitivity is not attributed to a paper unless its definition supports it. Clinical interpretations are not inferred from descriptive thresholds.

Full journal articles, publisher graphics, complete downloaded workbooks and ATLAS derivatives are not supplied.

See [LICENSES.md](LICENSES.md) and [source-data terms](../docs/DATA_TERMS.md) before redistributing an example.
