# MIC-50-90 2.0.0

Changes between versions are listed in `CHANGELOG.md`. The release files and their checksums are attached to the [GitHub release](https://github.com/maciejkochanowski/mic-50-90/releases/tag/v2.0.0) and archived at Zenodo.

MIC-50-90 is a Python package for bounding MIC distributions from incomplete susceptibility reports. Published antimicrobial susceptibility results often give only MIC50, MIC90, a range and a few percentages. From these, and from exact or rounded counts, MIC-50-90 computes the smallest and largest count the report allows in every MIC category and range, names the count that would narrow an open question most, selects counts a laboratory can publish so that readers can check its conclusions, and gives optional population bounds under stated sampling assumptions. The Python interface, the command line and the Galaxy tools use the same calculation engine.

Use it to interpret an unreported concentration range, distinguish missing counts from measurement censoring, determine which additional counts would resolve a question, or prepare a short laboratory report whose conclusions a recipient can verify. Inputs refer to the same original isolates and retain their denominator, panel, units and reporting convention.

## Install and start

Use Python 3.11–3.13 in a separate environment. The release checksums identify the published files; the release workflow records the operating systems and Python versions on which they were tested.

Install from PyPI with the Python interpreter of that environment:

```text
python -m pip install mic-50-90==2.0.0
mic-50-90 --help
```

To install from a source checkout, run `python -m pip install .` from its root directory.

For work in a web browser without installing anything, the MIC-50-90 Galaxy tools describe a distribution, audit a laboratory report and check a received certificate. Their wrappers and tests are in `galaxy/`.

Each release is also published as a container image that already contains Python and all dependencies, so only Docker or another container runtime is needed. On Linux or macOS, this runs the program on files in the current folder:

```text
docker run --rm -u "$(id -u):$(id -g)" -v "$PWD:/data" -w /data ghcr.io/maciejkochanowski/mic-50-90:2.0.0 mic-50-90 --help
```

Started without a command, the container runs the software checks.

To inspect the command-line interface:

```text
mic-50-90 --help
mic-50-90 distribution --help
```

Download the source archive for the example inputs, schemas and documentation. From its extracted directory, run:

```text
mic-50-90 distribution examples/distribution/summaries.json --precision-pp 10 --output-dir output/distribution
```

Open the generated `report.html`. Reports also provide CSV/JSON results and reusable input settings. The wheel installs the command line and the library; the software source release supplies the tests, formal checks, examples and user documentation.

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
- Select sufficient counts from complete category counts so a recipient can verify the stated sample conclusions.
- Prepare and assess study-unit calibration with its own reference and sampling requirements.

The main mathematical result gives a checkable P6 endpoint-attainment condition: when it holds, a selected family of compatible count tables attains the same population-range endpoints as considering every compatible table for the fixed confidence construction. The result has a written proof and independent numerical checks, and the algebraic core of the proof is checked in the Lean proof assistant (29 declarations).

## Documentation and checks

### What the repository contains

| Folder | Purpose |
|---|---|
| `src` | Calculation engine, command line and report resources |
| `tests` | Automated checks of calculations, input handling and interfaces |
| `galaxy` | Galaxy tool wrappers with their test data |
| `tools` and `.github/workflows` | Build, test and publish the software packages |
| `docs` and `schemas` | Installation, usage, input formats and output definitions |
| `examples` and `data` | Small example inputs, source attribution and data terms |
| `formal` and `reproducibility` | Formal algebra and independent checks of the implemented calculations |
| `evaluation` | Inputs, scripts and result tables of the comparisons reported in the article |
| `scripts` | Source manifest, source bundle, archive installation check, command reference and document claim check |

The command line, the Python interface and the Galaxy tools use the same calculation engine. Article-production files are maintained outside this repository.

- [Distribution guide](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/distribution-user-guide.md): an end-to-end CLI analysis and interpretation.
- [CLI reference](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/CLI_REFERENCE.md): every command and option.
- [Python interface](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/PYTHON_INTERFACE.md): callable analysis functions and update contracts.
- [Report contents](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/REPORT_CONTENTS.md): results, numerical checks and exports.
- [Public functions](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/PUBLIC_FUNCTIONS.md): tasks, implementation and independent checks.
- [Reproducing software checks](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/REPRODUCING_RESULTS.md) and [formal algebra](https://github.com/maciejkochanowski/mic-50-90/blob/main/formal/README.md).

The GitHub Actions workflow tests installed packages on Windows and Linux with Python 3.11–3.13. The release workflow builds the Python packages and the container image, checks their contents and attaches only software assets. Consult the completed Actions run and the release checksums for the exact distributed files.

Manuscripts, supplementary appendices and editorial figures are maintained separately. They are not included in this repository, its software release assets, or a software deposit generated from this repository. [Distribution policy](https://github.com/maciejkochanowski/mic-50-90/blob/main/docs/DISTRIBUTION_POLICY.md).

## Scientific scope and license

MIC-50-90 is a tool for research, surveillance and reporting audits. Its results describe a collection of isolates or the population from which the collection was sampled, and every result states the reporting convention and the sampling assumption on which it rests.

The software is distributed under **MIT**. Example data, source publications and bundled fonts retain their own attributed terms; some publication examples have noncommercial source terms. Source URLs, hashes and exclusions are documented in `docs/DATA_TERMS.md` and `data/LICENSES.md`. The software license does not relicense third-party material.

Author: **Maciej Kochanowski**, Department of Bacteriology and Bacterial Diseases, National Veterinary Research Institute, Puławy, Poland. [ORCID 0000-0002-9982-3028](https://orcid.org/0000-0002-9982-3028). Use `CITATION.cff` for citation metadata. Archived releases: [doi:10.5281/zenodo.23297915](https://doi.org/10.5281/zenodo.23297915). Report issues through the [GitHub issue tracker](https://github.com/maciejkochanowski/mic-50-90/issues).
