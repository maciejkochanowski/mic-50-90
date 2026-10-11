# MIC-50-90 1.0.0

MIC-50-90 is research software for describing MIC distributions from incomplete laboratory reports. It combines MIC50/MIC90, observed extremes, exact or interval counts, and explicitly rounded percentages to show the smallest and largest category shares compatible with the reported information. A local Windows application, Python command line and Python interface support the same calculation workflows.

Use it to interpret an unreported concentration range, distinguish missing counts from measurement censoring, determine which additional counts would resolve a question, or prepare a short laboratory report whose conclusions a recipient can verify. Inputs refer to the same original isolates and retain their denominator, panel, units and reporting convention.

## Install and start

**Windows application:** download the portable Windows archive from the [version 1.0.0 software release](https://github.com/maciejkochanowski/mic-50-90/releases/tag/v1.0.0), extract it, and open `MIC-50-90.exe`. Keep the `_internal` folder beside the executable. Python is included. The application opens a guided form in your browser and performs calculations locally. Use **Quit application** to stop it.

**Python:** use Python 3.11–3.13 in a separate environment. Install version 1.0.0 from PyPI:

```text
python -m pip install mic-50-90==1.0.0
mic-50-90 gui
```

Alternatively, download the verified wheel from the software release and install it with `python -m pip install mic_50_90-1.0.0-py3-none-any.whl`.

To inspect the command-line interface:

```text
mic-50-90 --help
mic-50-90 distribution --help
```

Download the source archive for the example inputs, schemas and documentation. From its extracted directory, run:

```text
mic-50-90 distribution examples/distribution/summaries.json --precision-pp 10 --output-dir output/distribution
```

Open the generated `report.html`. Reports also provide CSV/JSON results and reusable input settings. The wheel installs the application and library; the software source release supplies the tests, formal checks, examples and user documentation.

## Choose the inference you need

| Question | Result | Requirements |
|---|---|---|
| What follows about these isolates? | Sharp finite-sample bounds over the distributions compatible with the report | Truthful summaries, ranks, panel geometry and category definitions |
| What follows about the source population? | Simultaneous confidence bounds accounting for incomplete reporting and sampling uncertainty | Independent observations from the same distribution, a declared population and confidence level |
| What is covered for a new study unit? | Calibrated bounds for the quantities in the declared protocol | Exchangeable study units and a matching reference, score, unit and calibration contract |

These layers answer different questions. Complete category counts can still leave concentrations uncertain inside measurement intervals. Optional likelihood, Bayesian, entropy and reference-based analyses report their additional assumptions. Incomplete numerical searches retain valid available bounds and their explicit completion status.

## Practical workflows

- Analyse published MIC summaries or counts, including several declared rank interpretations when necessary.
- Add a count from the original collection and update the analysis while preserving previous truthful information.
- Select contiguous concentration groups at a requested sample or population precision.
- Plan one request or successive requests for additional counts, with explicit permitted questions and costs.
- Select sufficient counts from a complete histogram so a recipient can verify the stated sample conclusions.
- Prepare and assess study-unit calibration with its own reference and sampling requirements.

The main mathematical result gives a checkable P6 endpoint-attainment condition: when it holds, a selected family of compatible count tables attains the same population-range endpoints as considering every compatible table for the fixed confidence construction. Written proofs, independent numerical checks and 29 Lean-checked algebraic declarations have distinct roles; the Lean development does not certify the entire program or all statistical assumptions.

## Documentation and checks

### What the repository contains

| Folder | Purpose |
|---|---|
| `src` | Calculation engine, CLI, Windows application and report resources |
| `tests` | Automated checks of calculations, input handling and interfaces |
| `tools` and `.github/workflows` | Build, test and publish the software packages |
| `docs` and `schemas` | Installation, usage, input formats and output definitions |
| `examples` and `data` | Small example inputs, source attribution and data terms |
| `formal` and `reproducibility` | Formal algebra and independent checks of the implemented calculations |
| `scripts` | Software integrity, reference calculations and validation utilities |

The Windows application and CLI use the same calculation engine. Cluster job submissions and article-production files are maintained outside this repository.

- [Windows user guide](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/GUI_GUIDE.md): installation, data entry, saved analyses and reports.
- [Distribution guide](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/distribution-user-guide.md): an end-to-end CLI analysis and interpretation.
- [CLI reference](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/CLI_REFERENCE.md): every command and option.
- [Python interface](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/PYTHON_INTERFACE.md): callable analysis functions and update contracts.
- [Report contents](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/REPORT_CONTENTS.md): results, numerical checks and exports.
- [Public functions](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/PUBLIC_FUNCTIONS.md): tasks, implementation and independent checks.
- [Reproducing software checks](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/REPRODUCING_RESULTS.md) and [formal algebra](https://github.com/maciejkochanowski/mic-50-90/blob/main/formal/README.md).

The GitHub Actions workflow tests installed packages on Windows and Linux with Python 3.11–3.13. The release workflow builds the Python and Windows packages, checks their contents and attaches only software assets. Consult the completed Actions run and the release checksums for the exact distributed files.

Manuscripts, supplementary appendices and editorial figures are maintained separately. They are not included in this repository, its software release assets, or a software deposit generated from this repository. [Distribution policy](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/DISTRIBUTION_POLICY.md).

## Scientific scope and licence

MIC-50-90 supports research and reporting audits. It does not infer clinical breakpoints, classify individual susceptibility or recommend treatment. Results depend on correct metadata and the assumptions attached to the chosen inference layer.

The software is distributed under **MIT**. Example data, source publications and bundled fonts retain their own attributed terms; some publication examples have noncommercial source terms. Source URLs, hashes and exclusions are documented in `docs/DATA_TERMS.md` and the evidence collection's `data/LICENSES.md`. The software licence does not relicense third-party material.

Author: **Maciej Kochanowski**, Department of Bacteriology and Bacterial Diseases, National Veterinary Research Institute, Puławy, Poland. [ORCID 0000-0002-9982-3028](https://orcid.org/0000-0002-9982-3028). Use `CITATION.cff` for citation metadata. Report issues through the [GitHub issue tracker](https://github.com/maciejkochanowski/mic-50-90/issues).
