# MIC-50-90 1.0.0: command and option reference

Generated from the installed command parser. GUI_GUIDE.md and PUBLIC_FUNCTIONS.md map tasks to Windows and CLI.
Values shown as None mean the option is omitted, not a numerical zero.

## mic-50-90

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `--version` | show program's version number and exit | — |

## mic-50-90 gui

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `--no-browser` | start without opening a browser | False |
| `--port` | local port; zero selects an available port | 0 |
| `--output-root` | directory for separately saved analysis runs | None |

## mic-50-90 analyse

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | path to a MIC-50-90 JSON input | required |
| `--output` | write strict JSON to this path | None |
| `--html` | write a self-contained HTML report to this path | None |

## mic-50-90 distribution

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | distribution JSON or summary CSV | required |
| `--targets` | optional recorded-scale decision targets CSV | None |
| `--panels` | explicit categories CSV, required for CSV input | None |
| `--additional-counts` | same-sample recorded-tail counts CSV for CSV input | None |
| `--population-method` | ; choices: bonferroni, joint-exact, range-calibrated, range-hunter | bonferroni |
| `--population-time-limit` | seconds per cohort for optional joint refinement (default: 30) | 30.0 |
| `--population-tolerance-pp` | requested outer-bound precision in percentage points (default: 0.01) | 0.01 |
| `--precision-pp` | maximum width in percentage points for a contiguous sample description; exact decimal, no default | None |
| `--population-precision-pp` | maximum population interval width in percentage points; requires declared iid sampling; separate from numerical tolerance | None |
| `--population-count-plan` | search for same-sample counts meeting population precision for the requested number of groups | False |
| `--population-minimum-bins` | minimum number of population groups required; default is every original category | None |
| `--population-planning-time-limit` | cooperative acquisition search budget in seconds | 10.0 |
| `--previous-output` | previous distribution output directory; retain its same-sample constraints and population outer bounds | None |
| `--delimiter` | ; choices: comma, semicolon, tab | comma |
| `--output-dir` |  | required |
| `--fail-on-refusal` |  | False |

## mic-50-90 calibrate-wasserstein

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | path to calibration-score JSON | required |
| `--output` | write the manifest to this path | None |

## mic-50-90 calibration-prepare

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | calibration category counts CSV; no target outcomes | required |
| `--panels` |  | required |
| `--roster` |  | required |
| `--metadata` | provenance and prespecified unit definition JSON | required |
| `--level` |  | 0.95 |
| `--reference-method` | use a uniform reference or learn it from separate training units in the roster; choices: uniform, training | uniform |
| `--transport-scaling` | optionally learn panel-specific transport scales from training units only; choices: none, training | none |
| `--delimiter` | ; choices: comma, semicolon, tab | comma |
| `--output-dir` |  | required |

## mic-50-90 calibration-plan

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `--level` |  | 0.95 |
| `--assurance` |  | 0.95 |
| `--calibration-units` |  | 0 |
| `--test-units` |  | 0 |
| `--output-dir` |  | required |

## mic-50-90 calibration-audit

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | observed per-target intervals and truths CSV | required |
| `--roster` | independently frozen intended unit/cohort/target CSV | required |
| `--output-dir` |  | required |
| `--manifest` | optional manifest 1.2 or 1.3 for tail intervals | None |
| `--training-units` | optional JSON list of training unit identifiers | None |
| `--level` | target level; defaults to manifest level or 0.95 | None |
| `--assurance` |  | 0.95 |
| `--tolerance` | prespecified numerical tolerance, at most 1e-6 | 0.0 |
| `--iid-units` | declare iid test units for binomial precision | False |
| `--procedure-frozen` | declare procedure and test size fixed before outcomes | False |
| `--delimiter` | ; choices: comma, semicolon, tab | comma |

## mic-50-90 batch

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | summary or count CSV | required |
| `--panels` | explicit panel categories CSV | required |
| `--targets` | cohort threshold CSV | required |
| `--output-dir` | directory for CSV, HTML and configuration | required |
| `--calibrations` | optional cohort-to-calibration JSON mapping | None |
| `--additional-counts` | truthful recorded-tail counts CSV from the original cohorts | None |
| `--question-time-limit` |  | 10.0 |
| `--report-page-size` | cohorts per HTML detail page; 0 writes one file (default: 50) | 50 |
| `--exclude-direct-targets` |  | False |
| `--decision-plan` | plan counts needed to resolve the declared recorded-sample criteria; cannot be combined with `--acquisition-plan` | False |
| `--acquisition-plan` | choose which existing counts to request together or in successive rounds; cannot be combined with `--decision-plan` | False |
| `--round-cost` | cost of each request/export round in acquisition mode (default: 0) | 0 |
| `--decision-queries` | optional query whitelist CSV: cohort_id,threshold,unit,cost | None |
| `--decision-plan-time-limit` | decision-plan search time limit (default: 5 seconds) | 5.0 |
| `--decision-plan-max-states` | decision-plan search state limit (default: 5000) | 5000 |
| `--delimiter` | separator used by all three input tables (default: comma); choices: comma, semicolon, tab | comma |
| `--fail-on-refusal` | return status 2 after writing reports if any cohort is refused | False |

## mic-50-90 reporting-audit

| Argument | Meaning | Default or requirement |
|---|---|---|
| `-h, --help` | show this help message and exit | — |
| `input` | summary or count CSV | required |
| `--panels` | explicit panel categories CSV | required |
| `--targets` | cohort threshold CSV | required |
| `--output-dir` | directory for CSV, HTML and configuration | required |
| `--calibrations` | optional cohort-to-calibration JSON mapping | None |
| `--question-time-limit` |  | 10.0 |
| `--report-page-size` | cohorts per HTML detail page; 0 writes one file (default: 50) | 50 |
| `--exclude-direct-targets` |  | False |
| `--decision-plan` | plan counts needed to resolve the declared recorded-sample criteria; cannot be combined with `--acquisition-plan`, `--reporting-plan` | False |
| `--acquisition-plan` | choose which existing counts to request together or in successive rounds; cannot be combined with `--decision-plan`, `--reporting-plan` | False |
| `--reporting-plan` | select a cheapest sufficient report from the known histogram; cannot be combined with `--decision-plan`, `--acquisition-plan` | False |
| `--round-cost` | cost of each request/export round in acquisition mode (default: 0) | 0 |
| `--decision-queries` | optional query whitelist CSV: cohort_id,threshold,unit,cost | None |
| `--decision-plan-time-limit` | decision-plan search time limit (default: 5 seconds) | 5.0 |
| `--decision-plan-max-states` | decision-plan search state limit (default: 5000) | 5000 |
| `--delimiter` | separator used by all three input tables (default: comma); choices: comma, semicolon, tab | comma |
| `--fail-on-refusal` | return status 2 after writing reports if any cohort is refused | False |
