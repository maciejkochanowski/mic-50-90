"""Inspect historical campaign receipts without rewriting their source identity.

`--check --mode integrity` tests recorded inputs/outputs. `--mode current` tests the
recorded code against current source bytes. `--mode both` (default) requires both.
Every mode reports both outcomes; source drift is not a scientific-error count.

Creating a snapshot requires --new-receipts-dir in a new location. Such snapshots
are always bound_only: hashing today's files never renews an old reproduction claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from library_closure import modules_reached  # noqa: E402

# Presets for the retained synthetic checks and calibration adapter.
CAMPAIGNS = {
    "stress_test": dict(
        code=["scripts/run_v1_stress_test.py"],
        inputs=[],
        outputs=["results/stress_test_summary.json", "results/stress_test_records.csv"],
    ),
    "coverage_simulations": dict(
        code=["scripts/run_v1_coverage_simulations.py"],
        inputs=[],
        outputs=[
            "results/v1_coverage_simulation_summary.json",
            "results/exact_population_coverage_records.csv",
        ],
    ),
    "external_validation": dict(
        code=["scripts/run_external_validation.py"],
        inputs=["data/manifests/external_sources_v1.json", "data/manifests/eucast_v1.json"],
        outputs=[
            "results/external_validation_summary.json",
            "results/external_validation_records.csv",
            "results/external_validation_certificates.jsonl",
            "results/external_conformal_records.csv",
            "results/external_calibration_scores.csv",
            "results/wasserstein_calibration_manifests.json",
        ],
    ),
}

VALID = {"reproduced", "reproduced_at_reporting_precision", "not_reproduced", "bound_only"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def digests(relatives: list[str]) -> tuple[dict, list[str]]:
    out, missing = {}, []
    for relative in relatives:
        path = ROOT / relative
        if path.is_file():
            out[relative] = sha(path)
        else:
            missing.append(relative)
    return out, missing


def receipt_path(name: str) -> Path:
    return ROOT / "results" / f"RECEIPT_{name}.json"


ALIASES = {
    "data/manifests/external_sources_v5.json": "data/manifests/external_sources_v1.json",
    "data/manifests/eucast_v5.json": "data/manifests/eucast_v1.json",
    "scripts/run_v5_coverage_simulations.py": "scripts/run_v1_coverage_simulations.py",
    "scripts/run_v5_stress_test.py": "scripts/run_v1_stress_test.py",
    "results/v5_coverage_simulation_summary.json": "results/v1_coverage_simulation_summary.json",
}


def inspect_block(root: Path, entries: dict) -> dict:
    rows = []
    for recorded, expected in entries.items():
        relative = Path(recorded)
        if relative.is_absolute() or ".." in relative.parts:
            rows.append({"recorded_path": recorded, "status": "unsafe_path"})
            continue
        resolved = recorded if (root / recorded).is_file() else ALIASES.get(recorded, recorded)
        path = root / resolved
        actual = sha(path) if path.is_file() else None
        rows.append({"recorded_path": recorded, "resolved_path": resolved,
                     "recorded_sha256": expected, "current_sha256": actual,
                     "alias_used": resolved != recorded,
                     "status": "matched" if actual == expected else "missing" if actual is None else "changed"})
    return {"status": "passed" if all(row["status"] == "matched" for row in rows) else "differs",
            "files": rows, "differences": sum(row["status"] != "matched" for row in rows)}


def inspect_receipt(root: Path, path: Path) -> dict:
    stored = json.loads(path.read_text(encoding="utf-8"))
    for name in ("code", "inputs", "outputs"):
        if not isinstance(stored.get(name), dict):
            raise ValueError(f"receipt has no {name} mapping")
    if not stored["outputs"] or not stored["code"]:
        raise ValueError("receipt must bind both source code and outputs")
    source_identity = hashlib.sha256(json.dumps(stored["code"], sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    artifacts = inspect_block(root, {**stored["inputs"], **stored["outputs"]})
    current = inspect_block(root, stored["code"])
    return {
        "campaign": stored.get("campaign", path.stem),
        "receipt": {"path": str(path.resolve()), "sha256": sha(path)},
        "recorded_reproduction": stored.get("reproduction"), "recorded_note": stored.get("note"),
        "recorded_source_identity": {"sha256_of_recorded_code_mapping": source_identity,
                                     "files": stored["code"]},
        "artifact_integrity": artifacts, "current_source_match": current,
        "interpretation": "Artifact differences require investigation of the retained files; source differences identify a different code snapshot. Neither count is a count of scientific errors. No campaign was rerun and no receipt was renewed.",
        "historical_source_availability": "The receipt records digests; a matching archived source snapshot is needed to inspect or rerun that historical version.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--receipt", type=Path, action="append", help="explicit receipt(s); default: three retained verification recipes")
    parser.add_argument("--mode", choices=("integrity", "current", "both"), default="both")
    parser.add_argument("--report", type=Path, help="new inspection report; never an existing campaign receipt")
    parser.add_argument("--new-receipts-dir", type=Path, help="create new bound_only snapshots; existing receipts are never replaced")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.check == bool(args.new_receipts_dir):
        parser.error("choose --check or --new-receipts-dir; historical receipts are never rewritten")
    if args.new_receipts_dir:
        if args.receipt:
            parser.error("--receipt applies only to --check")
        target = (root / args.new_receipts_dir).resolve()
        if target.exists():
            parser.error("new receipt directory must not exist")
        if root != ROOT.resolve():
            parser.error("snapshot creation uses this checkout; --root is for inspection")
        bodies = []
        for name, spec in CAMPAIGNS.items():
            listed = {"code": sorted(set(spec["code"]) | set(modules_reached(*spec["code"]))),
                      "inputs": spec["inputs"], "outputs": spec["outputs"]}
            body = {"campaign": name, "reproduction": "bound_only",
                    "note": "New byte snapshot only. This is not a reproduction run and does not renew any historical claim."}
            for field, paths in listed.items():
                body[field], missing = digests(paths)
                if missing:
                    parser.error(f"cannot bind missing {field}: {missing}")
            bodies.append((name, body))
        target.mkdir(parents=True)
        for name, body in bodies:
            (target / f"RECEIPT_{name}.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        print(f"Created {len(bodies)} bound_only snapshots in {target}; historical receipts unchanged")
        return 0
    paths = [root / p for p in args.receipt] if args.receipt else [root / "results" / f"RECEIPT_{name}.json" for name in CAMPAIGNS]
    if args.report and args.report.resolve() in {path.resolve() for path in paths}:
        parser.error("report must not overwrite a campaign receipt")
    report = {"mode": args.mode, "root": str(root), "campaigns": [], "errors": []}
    for path in paths:
        try:
            row = inspect_receipt(root, path)
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            report["errors"].append(f"{path}: {exc}")
            continue
        report["campaigns"].append(row)
        print(f"{row['campaign']}: receipt={row['receipt']['path']} SHA256={row['receipt']['sha256']}")
        print(f"  recorded source identity: {row['recorded_source_identity']['sha256_of_recorded_code_mapping']}")
        print(f"  artifact integrity: {row['artifact_integrity']['status']}; current-source match: {row['current_source_match']['status']}")
        for block in ("artifact_integrity", "current_source_match"):
            for item in row[block]["files"]:
                if item["status"] != "matched":
                    print(f"    {block}: {item['status']}: {item['recorded_path']}")
    fields = ("artifact_integrity", "current_source_match") if args.mode == "both" else ("artifact_integrity",) if args.mode == "integrity" else ("current_source_match",)
    failed = bool(report["errors"]) or any(row[field]["status"] != "passed" for row in report["campaigns"] for field in fields)
    report["status"] = "differences" if failed else "passed"
    report["meaning"] = "Separate file-integrity and current-source comparisons; no reproduction claim is created or updated."
    for error in report["errors"]:
        print(error)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{report['status'].upper()} for requested {args.mode} scope. Differences are file bindings, not scientific-error counts.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
