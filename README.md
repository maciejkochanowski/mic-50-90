# MIC-50-90

[![PyPI](https://img.shields.io/pypi/v/mic-50-90)](https://pypi.org/project/mic-50-90/)
[![Bioconda](https://img.shields.io/conda/vn/bioconda/mic-50-90)](https://bioconda.github.io/recipes/mic-50-90/README.html)
[![Tests](https://github.com/maciejkochanowski/mic-50-90/actions/workflows/tests.yml/badge.svg)](https://github.com/maciejkochanowski/mic-50-90/actions/workflows/tests.yml)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23297915.svg)](https://doi.org/10.5281/zenodo.23297915)
[![License](https://img.shields.io/pypi/l/mic-50-90)](https://github.com/maciejkochanowski/mic-50-90/blob/main/LICENSE.txt)

**Exact bounds on MIC distributions from incomplete susceptibility reports.**

Many antimicrobial susceptibility studies report minimum inhibitory concentrations (MICs) only as MIC50 and MIC90. Such a report does not say how many isolates exceed a breakpoint: when the breakpoint lies between the two values, the answer is anywhere from 10% to 50%. MIC-50-90 computes exactly what a report does establish. It

- gives the smallest and largest number of isolates the report allows in every MIC category and range,
- names the one further count that would narrow an open question most,
- tells a laboratory which few counts to publish so that readers can check its conclusions,
- adds confidence bounds for the source population when the isolates were sampled independently.

The bounds assume no distributional model. They hold for every complete table that agrees with the report. A Python interface, a command line and three Galaxy tools share one calculation engine.

## Example

[Brookshire et al.](https://doi.org/10.3389/fvets.2024.1512582) tested 67 canine staphylococci against ampicillin and report MIC50 ≤0.12 mg/L, MIC90 0.5 mg/L and a highest value above 1 mg/L. How many isolates had each MIC?

| MIC (mg/L) | ≤0.12 | 0.25 | 0.5 | 1 | >1 |
|---|---|---|---|---|---|
| Isolates, from the summaries alone | 34–60 | 0–26 | 1–32 | 0–5 | 1–6 |
| Isolates, with one further count | 34–59 | 0–25 | 2–7 | 0–5 | 1–6 |

Asked about the 0.5 mg/L category, the program names the count to request: the number of isolates at or below 0.25 mg/L. The paper prints it (59), and the category narrows from 1–32 to 2–7 isolates.

Both rows come from the inputs in `examples/`. Each run writes `report.html` with the results as CSV and JSON beside it:

```console
mic-50-90 distribution examples/biological_cases/ampicillin-67-summaries.json --output-dir out/summaries
mic-50-90 distribution examples/biological_cases/ampicillin-67-with-count.json --output-dir out/with-count
```

The same calculation in Python:

```python
from mic_50_90.distribution_workflow import analyse_distribution

report = {
    "n": 67, "unit": "mg/L",
    "panel": {"levels": [0.12, 0.25, 0.5, 1]},
    "summaries": {
        "minimum": "<=0.12", "maximum": ">1",
        # "ceiling": MIC50 is result number ceil(n/2) in increasing order
        "quantiles": [
            {"probability": 0.5, "category": "<=0.12", "convention": "ceiling"},
            {"probability": 0.9, "category": "0.5", "convention": "ceiling"},
        ],
    },
}
for c in analyse_distribution(report)["sample"]["categories"]:
    print(c["label"], c["count_lower"], c["count_upper"])
# <=0.12 34 60
# 0.25 0 26
# 0.5 1 32
# 1 0 5
# >1 1 6
```

## Installation

MIC-50-90 runs on Python 3.11 to 3.13 and needs only NumPy and SciPy.

| Source | Command |
|---|---|
| PyPI | `python -m pip install mic-50-90` |
| Bioconda | `conda install -c conda-forge -c bioconda mic-50-90` |
| Container | `docker run --rm ghcr.io/maciejkochanowski/mic-50-90:2.0.0 mic-50-90 --help` |

To use the container on files in the current folder, add `-v "$PWD:/data" -w /data`.

**Galaxy, with nothing to install.** The tools *MIC-50-90 distribution bounds*, *laboratory report* and *check a received report* run in a web browser on [usegalaxy.eu](https://usegalaxy.eu/?tool_id=mic_50_90_distribution), [usegalaxy.org](https://usegalaxy.org/?tool_id=mic_50_90_distribution) and [usegalaxy.org.au](https://usegalaxy.org.au/?tool_id=mic_50_90_distribution). They are published in the Galaxy Tool Shed by the Intergalactic Utilities Commission as [suite_mic_50_90](https://toolshed.g2.bx.psu.edu/view/iuc/suite_mic_50_90); the wrappers are maintained in [galaxyproject/tools-iuc](https://github.com/galaxyproject/tools-iuc/tree/main/tools/mic_50_90).

## Choosing the analysis

| You want to | You provide | Use |
|---|---|---|
| know how many isolates lie above a breakpoint or in any MIC category | sample size, MIC categories, MIC50, MIC90, range and any printed counts | [`distribution`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/distribution-user-guide.md) for one report, [`batch`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/CSV_WORKFLOWS.md) for a CSV of many |
| decide what to ask the authors for | the same report and your question | the count named in the report, or [`batch --acquisition-plan`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/ACQUIRING_COUNTS.md) for several questions |
| publish a short table that readers can verify | the complete counts and the questions readers will ask | [`reporting-audit --reporting-plan`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/SUFFICIENT_REPORTING.md) |
| check a report you received | its certificate | [`verify-report`](https://github.com/maciejkochanowski/mic-50-90/blob/main/examples/received_report/README.md) |
| describe the population the isolates came from | isolates sampled independently, a confidence level | `"iid": true` in the input of [`distribution`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/distribution-user-guide.md) |
| describe a new farm, plant, state or year | complete data from comparable units | [`calibration-prepare`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/CALIBRATION_PREPARATION.md), then `batch --calibrations` |

A count can be exact, a range or a rounded percentage. If a source does not say how it computed MIC50 and MIC90, several rules can be entered side by side and the bounds cover all of them.

## Guarantees and evaluation

The bounds for the tested isolates are exact: each one is reached by a complete table that agrees with the report. The population bounds hold for all such tables together, so under independent sampling their coverage is at least the stated level.

An endpoint theorem makes the population bounds for single categories and ranges fast to compute. Under a condition that the program verifies for the sample size at hand, at most one table per MIC category gives exactly the bounds of all compatible tables together. In the example above, five tables replace 7938. The theorem has a written proof and independent numerical checks, and the algebraic core of the proof is checked in the Lean proof assistant.

Every function of version 2.0.0 was evaluated separately. Three of the results:

- All 17,658 intervals for tested isolates agreed with an independent probability-bounds implementation.
- In 601 public surveillance collections reduced to MIC50, MIC90 and range, one named count narrowed an open category by a median of 84%.
- In 180 reporting tasks from 60 surveillance collections, 115 published counts instead of 405 kept all 1809 answers checkable.

Protocols, inputs, scripts and results are in [`evaluation/`](https://github.com/maciejkochanowski/mic-50-90/tree/main/evaluation). [`README_REVIEWER.md`](https://github.com/maciejkochanowski/mic-50-90/blob/main/README_REVIEWER.md) and the [reproduction package](https://doi.org/10.5281/zenodo.24455780) recreate every figure and example number of the article and its supplements.

## Documentation

- [Distribution guide](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/distribution-user-guide.md): one analysis from input to interpretation.
- [CLI reference](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/CLI_REFERENCE.md) and [Python interface](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/PYTHON_INTERFACE.md): every command, option and function.
- [CSV workflows](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/CSV_WORKFLOWS.md): many collections at once from summary and count tables.
- [Public functions](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/PUBLIC_FUNCTIONS.md): each task, the function that performs it and the tests that check it.
- [Report contents](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/REPORT_CONTENTS.md): what the HTML, CSV and JSON outputs hold.
- [Reproducing the results](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/REPRODUCING_RESULTS.md) and the [formal proof files](https://github.com/maciejkochanowski/mic-50-90/blob/main/formal/README.md).

Changes between versions are listed in [`CHANGELOG.md`](https://github.com/maciejkochanowski/mic-50-90/blob/main/CHANGELOG.md).

## Citation

> Kochanowski M. MIC-50-90: A Python package for bounding MIC distributions from incomplete susceptibility reports. Version 2.0.0 [software]. Zenodo; 2026. https://doi.org/10.5281/zenodo.24442629

[`CITATION.cff`](https://github.com/maciejkochanowski/mic-50-90/blob/main/CITATION.cff) holds the same record for reference managers. All archived versions share [doi:10.5281/zenodo.23297915](https://doi.org/10.5281/zenodo.23297915).

## License and contact

MIC-50-90 is a tool for research, surveillance and reporting audits. It is distributed under the MIT license. Example data and bundled fonts keep the terms of their sources, listed in [`docs/DATA_TERMS.md`](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/DATA_TERMS.md) and [`data/LICENSES.md`](https://github.com/maciejkochanowski/mic-50-90/blob/main/data/LICENSES.md).

Maciej Kochanowski ([ORCID 0000-0002-9982-3028](https://orcid.org/0000-0002-9982-3028)), Department of Bacteriology and Bacterial Animal Diseases, National Veterinary Research Institute, Puławy, Poland. Questions and problems are welcome in the [issue tracker](https://github.com/maciejkochanowski/mic-50-90/issues).
