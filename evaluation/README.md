# Evaluation

This folder contains the inputs and scripts of the evaluation reported in the article (Section 2.5
and Appendix D), including the confirmation on independent data and the finite controls described
in its Technical Archive. Each script runs one comparison with the
installed `mic_50_90` package and writes its results to `results/<comparison>/`. `summarize.py`
then collects every number reported there into `results/SUMMARY.json` and CSV tables, next to the
value given in the article and its supplements.

The settings of the program were chosen on the development data (`data/`) and then tested, unchanged,
on the confirmation data under the protocol in [PROTOCOL.md](PROTOCOL.md), whose SHA-256 value is
recorded with every confirmation result.

## Setup

Python 3.11 or later. From the repository root:

```text
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m pip install pba==0.90.4  # only for pba_comparison.py
python -m pip install -e ".[benchmark]"  # prepare_benchmark.py and the figure notebooks
```

`pba` is PBA-for-Python, an independent probability-bounds library published on PyPI. It needs
NumPy, SciPy and Matplotlib. It is used only by `pba_comparison.py` and is not part of the package.

## The comparisons

| Script | What it measures | Runtime, 2 cores | Runtime, 192 cores |
|---|---|---:|---:|
| `population_comparison.py` | Four constructions on 20 incomplete reports (10 FDA animal-pathogen, 10 NORM 2024 human cohorts): width and resolved questions by kind of range, cohorts meeting the endpoint target, seconds per cohort. 80 jobs, 120-second process budget each. | about 45 min | about 3 min |
| `coverage_simulation.py` | How often the Bonferroni and range-calibrated bounds contain every population share when the cohorts are resampled: 5000 replicates per cohort. | about 9 h | about 3 min |
| `complete_tables.py` | Width left by sampling alone (complete table known) against width from the incomplete report. | 15 s | 5 s |
| `controlled_reports.py` | On 144 controlled reports: width reduction from the range-calibrated cutoff alone, an independent linear-program check of the endpoints, and 15 scaling probes. | 2 min | 15 s |
| `sufficient_reporting.py` | Which counts a laboratory must send so that the recipient can verify every threshold answer: direct reporting, greedy deletion and minimal sufficient reports on 60 cohorts (180 tasks). | 2 s | 2 s |
| `calibration.py` | Held-out coverage and width of the calibrated intervals: NARMS 2021 collection blocks, and FSIS 2020–2021 plant groups (establishments under one owner) with a uniform or a trained reference. | 14 min | about 8 min |
| `pba_comparison.py` | Agreement with an exhaustive oracle, an independent cumulative-count calculation and PBA-for-Python on 8800 small inputs. | 1 min | 1 min |
| `reporting_controls.py` | Sufficient reporting against an independent histogram filter and exhaustive subset search: 4716 common-boundary and 300 seeded variant cases. | 7 s | about 7 s (one core) |
| `planning_controls.py` | Request planning against independent decision-tree enumeration: 2400 controlled tasks, a 128-case stress set and 31 input/contract controls. | 2 s | about 2 s (one core) |
| `count_extrema_controls.py` | Count extrema and P5 rows against explicit histograms for n = 1–6, K = 2–4, and 160 seeded reports with additional counts. | 12 s | about 12 s (one core) |
| `population_controls.py` | Population projections, zero-budget results and probability witnesses against complete-table regions for n = 1–5, K = 2–4: 2832 projection pairs, 1416 zero-budget pairs, 267 witness queries. | 36 s | about 36 s (one core) |
| `download_sources.py` | Fetches the six public isolate-level files of the confirmation data (FDA NARMS and FDA animal-pathogen data) and checks their SHA-256 values. | 1 min | 1 min |
| `prepare_benchmark.py` | Builds the 610 confirmation cohorts and the unit tables of the six calibration datasets from those files (PROTOCOL.md, sections 2 and 6). Deterministic. | 3 min | 3 min |
| `confirmation_population.py` | Bonferroni and range-calibrated on reports R1–R3, joint-exact and range-hunter on R1, for 610 cohorts: 4880 jobs. | about 1 day | about 15 min |
| `confirmation_coverage.py` | Coverage on the confirmation cohorts: 2000 replicates per cohort and report (3.66 million). | about 2.5 days | about 40 min |
| `synthetic_coverage.py` | Coverage on 1740 synthetic populations (generators G2–G4), 1000 replicates each. | about 2 days | about 35 min |
| `external_calibration.py` | Study-unit calibration on a later year in six datasets, uniform and trained reference, and synthetic units SU1–SU3. | about 1.5 days | about 25 min |
| `endpoint_selection.py` | The ampicillin example of Section 3.1: selected tables against every compatible table. | 1 min | 1 min |
| `examples_check.py` | Reruns the analyses of the article and Appendices B and C (`examples/appendix/COMMANDS.txt`) and compares every printed number with the program output. | 5 min | 5 min |
| `verify_subsets.py` | Recomputes seeded subsets of every simulation and requires exact agreement with the supplied results; the quick reproduction check. | about 1 h | 2 min |
| `summarize.py` | Collects the numbers of Section 2.5, the confirmation and the finite controls into `results/SUMMARY.json` and `results/tables/*.csv`. | 1 s | 1 s |

Each script explains its design in its docstring (`python evaluation/<script>.py --help`).

**Population comparison.** Each cohort is shortened to n, the panel, ceiling-rank MIC50 and MIC90
and one category count. Each construction bounds the share of every contiguous range of categories
at 95%. For every proper range three questions are asked: is the share below 5%, 10% and 20%? A
question is resolved when the whole interval lies on one side. A cumulative range starts at the
first or ends at the last category (160 ranges, 480 questions); there are 60 single internal
categories (180 questions) and 60 internal ranges of several categories (180 questions). Each job
runs in its own single-threaded process. It saves a quick conservative result first and then
refines it with the time left minus a 5-second reserve; if the process reaches the 120-second
budget, the quick result is kept. Bonferroni and range-calibrated finish in well under a second and
their results do not depend on the machine. Joint-exact and range-hunter use the whole budget, so
their last digits can differ between machines.

**Coverage simulation.** The complete table of each cohort is treated as the population. Each
replicate draws a sample of the cohort's size, shortens it as the cohort report was shortened, and
checks whether every interval contains its population share. The random seed of a replicate is
`[20261011, cohort position, replicate]`, so any replicate can be recomputed alone.

The historical protocol's criterion of no configuration with statistically detected
undercoverage is an empirical diagnostic. Non-rejection in finitely many simulated configurations
does not prove or confirm a universal coverage guarantee. The guarantee must follow from a
mathematical argument under its stated sampling assumptions; Monte Carlo uncertainty and the
range of simulated configurations limit the empirical check. The original protocol is
preserved unchanged in `protocols/PROTOCOL_1_0_1.md` with its SHA-256. The current `PROTOCOL.md`
makes this interpretation explicit and records the 2026-11-14 reporting amendment without
changing historical observations or design choices. New per-configuration summaries include
attempted/completed/failed denominators and a labelled pointwise 95% Monte Carlo interval when
there are no execution errors. Pooled heterogeneous configurations remain descriptive.

**Finite controls.** The four control scripts need no input files: every case is generated from
explicit integer histograms, and the seeded cases use fixed seeds. Each oracle enumerates the
compatible histograms itself (sorted observations, exact fractions) and does not call the package;
the package result is then compared with it case by case. `reporting_controls.py` compares the
minimum cost of a sufficient report from `plan_reporting` (checked by `verify_reporting`) with an
exhaustive search over every subset of the allowed counts, and requires an impossible report to be
recognized as such. `planning_controls.py` compares `plan_decisions` with the optimal worst-case
decision tree over the explicit histograms, follows every returned policy for every compatible
histogram and checks every impossibility witness. `count_extrema_controls.py` compares the integer
count extrema, the closed difference bounds, the closed-form tails and the P5 rows with
enumeration. `population_controls.py` builds, for every compatible complete table, its
Clopper-Pearson probability region (roots by exact rational bisection) and projects it onto every
contiguous range with a separately assembled linear program; `population_distribution` must
contain the union of these projections, also with zero search budget, and every probability
witness must match the report and be accepted exactly on every range. The scripts run on one core
and their counts do not depend on the machine; the maximum endpoint difference of the population
projections is a floating-point value and is compared with the stated bound.

**Interpreting the P6 certificate count.** In the historical controlled benchmark,
`endpoint_checks.shape_condition = 142` counts runtime results marked `certified`.
The other two results are `not_checked`: direct endpoint witnesses already met the target.
This field does not establish that the condition holds in only 142 of the 144 reports.
The separate 2026-11-03 research audit explicitly checked every actual returned sample-size/cutoff
pair and certified the sufficient condition for all 144 reports. Its case-level evidence is
`research/wp6/results/independent/actual_conditions.json` in the research bundle. The historical
summary remains unchanged so that its execution path is reproducible.

**Confirmation.** `PROTOCOL.md` fixes the data, the selection rules, the three report types, the
criteria and the outputs. Replicate r of configuration c of a simulation uses the seed
`[20261102, generator, c, r]`, so any part can be rerun alone: every confirmation script takes
`--shard i/n` and writes one file per shard, and a final run without `--shard` collects them.

**Calibration.** Calibration data never include test tables. The public `batch` command receives
only the summaries, panels, targets and the calibration. A unit (NARMS block or FSIS plant group)
is covered when every tail of all its 14 drug cohorts lies inside its interval.

## Commands

From the repository root (results go to `evaluation/results/` unless `--output` is given):

```text
python evaluation/population_comparison.py --workers 80
python evaluation/coverage_simulation.py --workers 192
python evaluation/complete_tables.py
python evaluation/controlled_reports.py
python evaluation/sufficient_reporting.py
python evaluation/calibration.py
python evaluation/pba_comparison.py
python evaluation/reporting_controls.py
python evaluation/planning_controls.py
python evaluation/count_extrema_controls.py
python evaluation/population_controls.py
python evaluation/download_sources.py
python evaluation/prepare_benchmark.py
python evaluation/confirmation_population.py
python evaluation/confirmation_coverage.py
python evaluation/synthetic_coverage.py
python evaluation/external_calibration.py
python evaluation/endpoint_selection.py
python evaluation/examples_check.py
python evaluation/summarize.py
```

Common options: `--output DIR` (results folder) and `--workers N` (parallel processes, default all
CPUs). The population comparison also takes `--budget` (seconds per job, default 120), `--cases`
and `--methods`; the coverage simulation `--replicates` (default 5000) and `--cases`. Quick checks
on a laptop:

```text
python evaluation/population_comparison.py --output /tmp/check --cases case-01,human-01 --budget 8
python evaluation/population_comparison.py --output /tmp/check2 --methods bonferroni,range-calibrated --budget 20
python evaluation/coverage_simulation.py --output /tmp/check --replicates 20 --block 10
python evaluation/pba_comparison.py --output /tmp/check --max-n 6
python evaluation/summarize.py --output /tmp/check
```

The second command reproduces the Bonferroni and range-calibrated rows of Table 3 exactly in
about 30 seconds. Results from reduced settings are marked `reduced run` by `summarize.py`.

**Resuming.** The population comparison saves one file per job and skips finished jobs. The
coverage simulation saves blocks of replicates and skips finished blocks. The calibration saves
its scores line by line and skips finished parts. Repeat the same command to continue. A run with
other settings is refused in an existing folder; use a new `--output`.

## Running on Helios (192-core node)

Submit from the repository root:

```text
sbatch evaluation/helios.sbatch
```

On the first run the job creates the Python environment `$HOME/venv-mic-50-90` on the compute
node (the Python module is built for the compute nodes) and installs the package and `pba` into it.

The job script runs all comparisons in turn on one node and then `summarize.py`:

```bash
#SBATCH --account=plgsoa27eupahw-cpu
#SBATCH --partition=plgrid
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=192
#SBATCH --mem=128G
#SBATCH --time=01:00:00
module load Python/3.11.5
python evaluation/population_comparison.py --workers 192 --budget 120
python evaluation/coverage_simulation.py --workers 192 --replicates 5000
...
python evaluation/summarize.py
```

Expected wall time is about 15 to 20 minutes: 3 for the population comparison (the 40 refined jobs
each use their 120-second budget in parallel), 3 for the coverage simulation (about 32,000
CPU-seconds), up to 8 for calibration (its preparation and batch steps run on one core) and a few
for the rest. The one-hour limit leaves a wide margin. Set `OUTPUT=evaluation/results-new` before
`sbatch` to write a completely new set of results; in an existing results folder finished
calibration parts are kept.

The confirmation runs as sharded jobs with `helios_confirmation.sbatch`; `PART` selects the step
(`prepare`, `population`, `coverage`, `synthetic`, `calibration-real`, `calibration-synthetic` or
`summary`) and `SHARD=i/n` the share of one job; a job of the same part without `SHARD` collects the
shards. The supplied results used 4, 8, 6 and 4 shards of 48 cores for the population, coverage,
synthetic and synthetic-unit parts, for example:

```text
sbatch -c 4 --export=ALL,PART=prepare evaluation/helios_confirmation.sbatch
for i in $(seq 0 7); do sbatch -c 48 --export=ALL,PART=coverage,SHARD=$i/8 evaluation/helios_confirmation.sbatch; done
sbatch -c 4 --export=ALL,PART=coverage evaluation/helios_confirmation.sbatch
sbatch -c 4 --export=ALL,PART=summary evaluation/helios_confirmation.sbatch
```

The `prepare` step rebuilds the confirmation tables and stops if they differ from those in
`data/benchmark/`.

## Outputs

| Path | Content |
|---|---|
| `results/SUMMARY.json` | Every number of Section 2.5: article value, reproduced value, status, package version and platform. |
| `results/tables/article_numbers.csv` | The same list as a table. |
| `results/tables/population_table3.csv`, `population_pairs.csv` | Table 3 and the paired cohort comparisons by kind of range. |
| `results/tables/coverage.csv`, `complete_tables.csv` | Per-cohort coverage and widths. |
| `results/<comparison>/summary.json` | All quantities of one comparison, its settings, the package version and the platform. |
| `results/population/runs/*.json` | The full result of every job, including all interval bounds. |
| `results/coverage/replicates.jsonl.gz` | One line per replicate, with every missed range. |
| `results/calibration/<part>/intervals.csv.gz` | Every held-out tail with its truth, calibrated interval and sample interval. |
| `results/controlled_reports/records.json`, `results/sufficient_reporting/tasks.csv`, `results/pba_comparison/*.csv.gz` | Per-report, per-task and per-input records. |
| `results/reporting_controls/cases.csv.gz` | Every finite reporting case: kind, histogram, oracle cost, package status and cost, agreement. |
| `results/planning_controls/controlled.csv.gz`, `stress.csv.gz`, `contract.json` | Every planning task with oracle and package status, cost, checked paths and witnesses; every contract control with its outcome. |
| `results/count_extrema/summary.json` | Counts of reports, P5 rows, range-endpoint pairs and feasibility decisions, and any failed check. |
| `results/population_controls/summary.json` | Counts of projection pairs, zero-budget pairs and probability witnesses, the maximum endpoint difference, and any failed check. |
| `data/benchmark/` | The confirmation cohorts, every eligible cohort and panel group with the reason for any exclusion, the unit tables of the calibration datasets and the SHA-256 values of the source files. |
| `results/confirmation_population/jobs.jsonl.gz` | Every cohort, report and construction: widths by kind of range, resolved questions, seconds and completion. |
| `results/confirmation_coverage/configurations.json.gz`, `results/synthetic_coverage/configurations.json.gz` | Every configuration with its covered replicates by block of 50 and every missed range. |
| `results/external_calibration/<dataset>-<reference>/` | Manifest, scores and test intervals of every calibration dataset and reference; `synthetic/` every repetition of the synthetic units. |
| `results/endpoint_selection/summary.json`, `results/examples/summary.json`, `results/examples/numbers.csv` | The Section 3.1 comparison and every printed number of the examples with the program output. |

Status values in `SUMMARY.json`: `match` (equal at the precision printed in the article, or not
above a stated upper bound),
`differs`, `timing` (seconds; these depend on the machine), `reduced run` and `not run`.

The results supplied in `results/` were computed with MIC-50-90 1.0.1 and Python 3.11 on 192-core
nodes of the Helios cluster (Cyfronet, Kraków), with the commands of `helios.sbatch` and
`helios_confirmation.sbatch`; the seconds are those of these nodes. Every number matches the article
and its supplements.

## Tests, coverage and mutations

The numbers of the software tests in Section 2.5 come from the repository test suites:

```text
python -m pip install -e ".[test]"
python -m pytest tests --cov --cov-report=json:coverage.json
ruff check src/mic_50_90 scripts tools && mypy
sbatch evaluation/mutation.sbatch
```

`results/software_checks/coverage.json` records the test counts and the statement and branch
coverage of the package. `mutation.sbatch` runs mutmut
3.8.0 on the thirteen critical functions it lists; `results/software_checks/mutation.json` records
every change, whether a test detected it and, for every change that no test detects, why it does
not alter a result on valid input. The mutation configuration is in `pyproject.toml`; the tests that
start a separate Python process need `mutants/src` on the interpreter path, which the job script
provides through a `.pth` file.

## Notes on reproduction

- Bonferroni and range-calibrated bounds, sample bounds, reporting plans and calibrated intervals
  are deterministic. Their numbers do not depend on the machine.
- Joint-exact and range-hunter search within a time budget. Their outer bounds are always
  conservative, but the last digits of their widths, and the number of cohorts in which they reach
  the endpoint target, can change with processor speed. Times in seconds always depend on the
  machine.

The inputs are described in [data/README.md](data/README.md), with their sources and terms.
