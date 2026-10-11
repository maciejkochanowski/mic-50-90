"""Command-line interface for MIC-50-90."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence
from ._version import __version__

from .analysis import analyse_spec
from .conformal import calibrate_wasserstein_manifest, validate_calibration_manifest
from .report import render_html
from .file_safety import check_output_paths
from .validation import load_analysis_json


def _analyse(args: argparse.Namespace) -> int:
    check_output_paths([args.input], [args.output, args.html])
    source = Path(args.input)
    spec = load_analysis_json(source.read_text(encoding="utf-8"))
    result = analyse_spec(spec)
    serialized = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    if args.html:
        render_html(result, args.html)
    return 0


def _calibrate_wasserstein(args: argparse.Namespace) -> int:
    check_output_paths([args.input], [args.output])
    source = Path(args.input)
    raw = json.loads(source.read_text(encoding="utf-8"))
    manifest = calibrate_wasserstein_manifest(
        group_scores=raw["group_scores"],
        global_scores=raw.get("global_scores"),
        alpha=float(raw.get("alpha", 0.05)),
        grouping=dict(raw.get("grouping", {})),
        source=str(raw["source"]),
        data_hashes=dict(raw.get("data_hashes", {})),
        group_units=raw.get("group_units"), global_units=raw.get("global_units"),
        calibrate_on=raw.get("calibrate_on", "units"),
        unit_definition=raw.get("unit_definition", "explicit study identifier"),
        unit_aggregation=raw.get("unit_aggregation", "max"),
        calibration_contract=raw["calibration_contract"],
    ).as_dict()
    validate_calibration_manifest(manifest)
    serialized = json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)
    return 0


def _gui(args: argparse.Namespace) -> int:
    from .gui import start_gui
    return start_gui(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mic-50-90",
        description="Partial identification and finite-sample inference from incomplete MIC summaries",
    )
    parser.add_argument("--version", action="version", version=f"MIC-50-90 {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    gui = subparsers.add_parser("gui", help="open the local guided analysis form")
    gui.add_argument("--no-browser", action="store_true", help="start without opening a browser")
    gui.add_argument("--port", type=int, default=0, help="local port; zero selects an available port")
    gui.add_argument("--output-root", help="directory for separately saved analysis runs")
    gui.add_argument("--ready-file", help=argparse.SUPPRESS)
    gui.set_defaults(handler=_gui)
    analyse = subparsers.add_parser("analyse", help="analyse a JSON specification")
    analyse.add_argument("input", help="path to a MIC-50-90 JSON input")
    analyse.add_argument("--output", help="write strict JSON to this path")
    analyse.add_argument("--html", help="write a self-contained HTML report to this path")
    analyse.set_defaults(handler=_analyse)
    from .distribution_workflow import run_distribution
    distribution = subparsers.add_parser("distribution", help="describe the whole recorded MIC distribution from summaries and counts")
    distribution.add_argument("input", help="distribution JSON or summary CSV")
    distribution.add_argument("--targets", help="optional recorded-scale decision targets CSV")
    distribution.add_argument("--panels", help="explicit categories CSV, required for CSV input")
    distribution.add_argument("--additional-counts", help="same-sample recorded-tail counts CSV for CSV input")
    distribution.add_argument("--population-method", choices=("bonferroni", "joint-exact", "range-calibrated", "range-hunter"), default="bonferroni")
    distribution.add_argument("--population-time-limit", type=float, default=30., help="seconds per cohort for optional joint refinement (default: 30)")
    distribution.add_argument("--population-tolerance-pp", type=float, default=.01, help="requested outer-bound precision in percentage points (default: 0.01)")
    distribution.add_argument("--precision-pp", help="maximum width in percentage points for a contiguous sample description; exact decimal, no default")
    distribution.add_argument("--population-precision-pp", help="maximum population interval width in percentage points; requires declared iid sampling; separate from numerical tolerance")
    distribution.add_argument("--population-count-plan", action="store_true", help="search for same-sample counts meeting population precision for the requested number of groups")
    distribution.add_argument("--population-minimum-bins", type=int, help="minimum number of population groups required; default is every original category")
    distribution.add_argument("--population-planning-time-limit", type=float, default=10., help="cooperative acquisition search budget in seconds")
    distribution.add_argument("--previous-output", help="previous distribution output directory; retain its same-sample constraints and population outer bounds")
    distribution.add_argument("--delimiter", choices=("comma", "semicolon", "tab"), default="comma")
    distribution.add_argument("--output-dir", required=True)
    distribution.add_argument("--fail-on-refusal", action="store_true")
    distribution.set_defaults(handler=run_distribution)
    calibrate = subparsers.add_parser(
        "calibrate-wasserstein",
        help="create a versioned split-conformal Wasserstein calibration manifest",
    )
    calibrate.add_argument("input", help="path to calibration-score JSON")
    calibrate.add_argument("--output", help="write the manifest to this path")
    calibrate.set_defaults(handler=_calibrate_wasserstein)
    from .calibration_preparation import run_calibration_prepare
    preparation = subparsers.add_parser('calibration-prepare', help='prepare calibration from complete histograms and an independent unit roster')
    preparation.add_argument('input', help='calibration category counts CSV; no target outcomes')
    preparation.add_argument('--panels', required=True)
    preparation.add_argument('--roster', required=True)
    preparation.add_argument('--metadata', required=True, help='provenance and prespecified unit definition JSON')
    preparation.add_argument('--level', type=float, default=.95)
    preparation.add_argument('--reference-method', choices=('uniform', 'training'), default='uniform',
                             help='use a uniform reference or learn it from separate training units in the roster')
    preparation.add_argument('--transport-scaling', choices=('none', 'training'), default='none',
                             help='optionally learn panel-specific transport scales from training units only')
    preparation.add_argument('--delimiter', choices=('comma', 'semicolon', 'tab'), default='comma')
    preparation.add_argument('--output-dir', required=True)
    preparation.set_defaults(handler=run_calibration_prepare)
    from .calibration_audit import run_calibration_audit, run_calibration_plan
    planner = subparsers.add_parser('calibration-plan', help='plan calibration and held-out unit counts')
    planner.add_argument('--level', type=float, default=.95)
    planner.add_argument('--assurance', type=float, default=.95)
    planner.add_argument('--calibration-units', type=int, default=0)
    planner.add_argument('--test-units', type=int, default=0)
    planner.add_argument('--output-dir', required=True)
    planner.set_defaults(handler=run_calibration_plan)
    audit = subparsers.add_parser('calibration-audit', help='assess every planned target at the unit level')
    audit.add_argument('input', help='observed per-target intervals and truths CSV')
    audit.add_argument('--roster', required=True, help='independently frozen intended unit/cohort/target CSV')
    audit.add_argument('--output-dir', required=True)
    audit.add_argument('--manifest', help='optional manifest 1.2 or 1.3 for tail intervals')
    audit.add_argument('--training-units', help='optional JSON list of training unit identifiers')
    audit.add_argument('--level', type=float, help='target level; defaults to manifest level or 0.95')
    audit.add_argument('--assurance', type=float, default=.95)
    audit.add_argument('--tolerance', type=float, default=0., help='prespecified numerical tolerance, at most 1e-6')
    audit.add_argument('--iid-units', action='store_true', help='declare iid test units for binomial precision')
    audit.add_argument('--procedure-frozen', action='store_true', help='declare procedure and test size fixed before outcomes')
    audit.add_argument('--delimiter', choices=('comma', 'semicolon', 'tab'), default='comma')
    audit.set_defaults(handler=run_calibration_audit)
    from .workflows import run_csv_workflow
    for name, help_text in (("batch", "analyse summary CSVs"),
                            ("reporting-audit", "audit information loss from category-count CSVs")):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("input", help="summary or count CSV")
        command.add_argument("--panels", required=True, help="explicit panel categories CSV")
        command.add_argument("--targets", required=True, help="cohort threshold CSV")
        command.add_argument("--output-dir", required=True, help="directory for CSV, HTML and configuration")
        command.add_argument("--calibrations", help="optional cohort-to-calibration JSON mapping")
        if name == "batch":
            command.add_argument("--additional-counts", help="truthful recorded-tail counts CSV from the original cohorts")
        command.add_argument("--question-time-limit", type=float, default=10.0)
        command.add_argument("--report-page-size", type=int, default=50,
                             help="cohorts per HTML detail page; 0 writes one file (default: 50)")
        command.add_argument("--exclude-direct-targets", action="store_true")
        planning_modes = command.add_mutually_exclusive_group()
        planning_modes.add_argument("--decision-plan", action="store_true",
                             help="plan counts needed to resolve the declared recorded-sample criteria")
        planning_modes.add_argument("--acquisition-plan", action="store_true",
                             help="choose which existing counts to request together or in successive rounds")
        if name == "reporting-audit":
            planning_modes.add_argument("--reporting-plan", action="store_true",
                                 help="select a cheapest sufficient report from the known histogram")
        command.add_argument("--round-cost", default="0",
                             help="cost of each request/export round in acquisition mode (default: 0)")
        command.add_argument("--decision-queries",
                             help="optional query whitelist CSV: cohort_id,threshold,unit,cost")
        # Validate optional settings during planning, so malformed values do not
        # prevent otherwise valid sample results from being written.
        command.add_argument("--decision-plan-time-limit", default=5.0, metavar="SECONDS",
                             help="decision-plan search time limit (default: 5 seconds)")
        command.add_argument("--decision-plan-max-states", default=5000, metavar="COUNT",
                             help="decision-plan search state limit (default: 5000)")
        command.add_argument("--delimiter", choices=("comma", "semicolon", "tab"), default="comma",
                             help="separator used by all three input tables (default: comma)")
        command.add_argument("--fail-on-refusal", action="store_true",
                             help="return status 2 after writing reports if any cohort is refused")
        command.set_defaults(handler=run_csv_workflow)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"mic-50-90: error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
