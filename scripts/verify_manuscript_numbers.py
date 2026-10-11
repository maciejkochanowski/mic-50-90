"""Check explicitly selected report claims against named JSON fields.

The command name and --manuscript argument remain compatible with existing callers.
This software package contains no article or editorial claim map. Supply your own
document and claim specification explicitly. Each contextual pattern captures one
value and names its JSON source field. Synthetic tests verify provenance and file
safety; this helper does not certify every number or sentence in a document.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manifest_tools import check_manifest, read_manifest, sha  # noqa: E402


def dig(blob, path):
    for part in path.strip("/").split("/"):
        if part:
            blob = blob[int(part)] if isinstance(blob, list) else blob[part]
    return blob


def verify(root: Path, manuscript: Path, manifest: Path, claims_path: Path, registry: dict,
           _inputs: set[Path] | None = None) -> dict:
    if _inputs is not None:
        _inputs.update((manuscript, manifest, claims_path))
    integrity = check_manifest(manifest, root)
    report = {"scope": "named contextual claims in the explicitly selected current manuscript",
              "manuscript": {"path": str(manuscript.resolve()), "sha256": sha(manuscript) if manuscript.is_file() else None},
              "manifest": integrity, "claim_definition": {"path": str(claims_path.resolve()), "sha256": sha(claims_path) if claims_path.is_file() else None},
              "claims": [], "problems": list(integrity["problems"])}
    try:
        text = manuscript.read_text(encoding="utf-8")
        specification = json.loads(claims_path.read_text(encoding="utf-8"))
        definitions = specification["claims"]
        if not definitions:
            raise ValueError("claim list is empty")
        entries = read_manifest(manifest, root)
        if _inputs is not None:
            _inputs.update(root / name for name in entries)
        manuscript_name = manuscript.resolve().relative_to(root.resolve()).as_posix()
        if entries.get(manuscript_name) != sha(manuscript):
            report["problems"].append(f"selected manuscript is not bound by this manifest: {manuscript_name}")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        report["problems"].append(str(exc))
        report["status"] = "failed"
        return report
    seen = set()
    for definition in definitions:
        row = {"id": definition["id"], "status": "failed"}
        report["claims"].append(row)
        try:
            if row["id"] in seen:
                raise ValueError("duplicate claim identifier")
            seen.add(row["id"])
            source_name = definition["source"]
            if source_name == "$engineering":
                source_name = registry["engineering_record"]
            source = root / source_name
            if _inputs is not None:
                _inputs.add(source)
            source_relative = source.resolve().relative_to(root.resolve()).as_posix()
            row.update(source=source_relative, source_path=str(source.resolve()), field=definition["field"],
                       source_sha256=sha(source), source_scope=definition.get("scope", "retained result; not a new computation"))
            if entries.get(source_relative) != row["source_sha256"]:
                raise ValueError(f"claim source is not bound by this manifest: {source_relative}")
            source_result = json.loads(source.read_text(encoding="utf-8"))
            if "source_hashes_field" in definition:
                recorded_sources = dig(source_result, definition["source_hashes_field"])
                if not isinstance(recorded_sources, dict) or not recorded_sources:
                    raise ValueError("source identity mapping is absent or empty")
                differences = []
                for relative, digest in recorded_sources.items():
                    member = (root / relative).resolve()
                    if _inputs is not None:
                        _inputs.add(member)
                    if (not member.is_relative_to(root.resolve()) or not member.is_file()
                            or sha(member) != digest):
                        differences.append(relative)
                row["source_current_match"] = {
                    "status": "differs" if differences else "passed",
                    "recorded_files": len(recorded_sources), "differences": differences,
                }
                if differences:
                    raise ValueError("recorded engineering sources differ from current sources: " + ", ".join(differences))
            value = dig(source_result, definition["field"])
            if "scale" in definition:
                value *= definition["scale"]
            expected = format(value, definition.get("format", ".0f"))
            matches = list(re.finditer(definition["pattern"], text, re.MULTILINE))
            if len(matches) != 1:
                raise ValueError(f"context must match exactly once, found {len(matches)}")
            row.update(expected=expected, observed=matches[0].group("value"), context=matches[0].group(0))
            row["status"] = "passed" if row["observed"] == expected else "mismatch"
            if row["status"] != "passed":
                row["problem"] = f"prints {row['observed']}, source renders {expected}"
        except (OSError, UnicodeError, ValueError, KeyError, IndexError, TypeError, re.error) as exc:
            row["problem"] = str(exc)
        if row["status"] != "passed":
            report["problems"].append(f"{row['id']}: {row['problem']}")
    report["status"] = "passed" if not report["problems"] else "failed"
    report["claims_checked"] = len(report["claims"])
    return report


def verify_documents(root: Path, manifest: Path, registry: dict,
                     _inputs: set[Path] | None = None) -> dict:
    """Check the four registered current documents, with a separate claim scope each."""
    report = {"scope": "named central quantitative claims in current main and Appendices A-C; not every number",
              "documents": [], "problems": [], "claims_checked": 0}
    for key in ("main", "appendix_a", "appendix_b", "appendix_c"):
        try:
            manuscript = root / registry["documents"][key]
            claims = root / registry["document_claims"][key]
        except (KeyError, TypeError) as exc:
            report["problems"].append(f"{key}: missing registry document/claim selection: {exc}")
            continue
        checked = verify(root, manuscript, manifest, claims, registry, _inputs)
        checked["document_key"] = key
        report["documents"].append(checked)
        report["claims_checked"] += len(checked["claims"])
        report["problems"].extend(f"{key}: {problem}" for problem in checked["problems"])
    report["status"] = "passed" if len(report["documents"]) == 4 and not report["problems"] else "failed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, default=Path("PACKAGE_STATUS.json"))
    parser.add_argument("--manuscript", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--claims", type=Path)
    parser.add_argument("--all-documents", action="store_true", help="check registered main and Appendices A-C")
    parser.add_argument("--json-report", type=Path)
    parser.add_argument("--report", type=Path, help="write a Markdown claim report")
    parser.add_argument("--legacy", action="store_true", help="explicit historical manuscript scope only")
    args = parser.parse_args()
    if args.legacy:
        if any((args.manuscript, args.manifest, args.claims, args.json_report, args.all_documents)):
            parser.error("--legacy cannot be combined with current-document options")
        command = [sys.executable, str(Path(__file__).with_name("verify_legacy_manuscript_numbers.py"))]
        if args.report:
            command += ["--report", str(args.report)]
        if not Path(command[1]).is_file():
            parser.error("legacy editorial verifier is not distributed with the software package")
        return subprocess.run(command).returncode
    root = args.root.resolve()
    registry_path = root / args.registry
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.is_file() else {}
    if not args.all_documents and not (
        (args.manuscript or registry.get("documents", {}).get("main"))
        and (args.claims or registry.get("manuscript_claims"))
    ):
        parser.error("Supply --manuscript and --claims; editorial documents are not part of the software package")
    manuscript = root / (args.manuscript or registry.get("documents", {}).get("main", "manuscript/softwarex_1.0.0/main.md"))
    manifest = root / (args.manifest or registry.get("source_manifest", "PACKAGE_MANIFEST.sha256"))
    claims = root / (args.claims or registry.get("manuscript_claims", "scripts/manuscript_claims_1_0_0.json"))
    if args.all_documents and (args.manuscript or args.claims):
        parser.error("--all-documents uses the registry and cannot be combined with --manuscript or --claims")
    inputs = {registry_path, manifest}
    try:
        inputs.update(root / name for name in read_manifest(manifest, root))
    except (OSError, UnicodeError, ValueError):
        pass  # Verification reports malformed or missing inputs below.
    report = (verify_documents(root, manifest, registry, inputs) if args.all_documents
              else verify(root, manuscript, manifest, claims, registry, inputs))
    for output in (args.json_report, args.report):
        if output and any(
            output.resolve() == path.resolve()
            or (output.exists() and path.exists() and output.samefile(path))
            for path in inputs
        ):
            parser.error("report destinations must not overwrite checked inputs")
    reports = report["documents"] if args.all_documents else [report]
    for checked in reports:
        for key in ("manuscript", "manifest", "claim_definition"):
            print(f"{key}: {checked[key]['path']} SHA256={checked[key]['sha256']}")
        for row in checked["claims"]:
            print(f"{row['status'].upper()} {row['id']}: {row.get('observed', '?')} -> {row.get('source', '?')}:{row.get('field', '?')} SHA256={row.get('source_sha256', '?')}")
    for problem in report["problems"]:
        print(f"  {problem}")
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.report:
        lines = ["# Current manuscript claim check", "", report["scope"], ""]
        for checked in reports:
            lines += [f"## {checked.get('document_key', 'Selected document')}", "",
                      f"Document: `{checked['manuscript']['path']}`; SHA-256 `{checked['manuscript']['sha256']}`.",
                      f"Manifest: `{manifest}`; SHA-256 `{checked['manifest']['sha256']}`.", "",
                      "| Named claim | Printed | Expected | Source field | Status |", "|---|---|---|---|---|"]
            for row in checked["claims"]:
                lines.append(f"| {row['id']} | {row.get('observed', '')} | {row.get('expected', '')} | {row.get('source', '')}:{row.get('field', '')} | {row['status']} |")
        lines += ["", *report["problems"], "", f"Overall: {report['status']}"]
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    total = sum(len(checked["claims"]) for checked in reports)
    print(f"{report['status'].upper()} - {total} named claims in {len(reports)} document(s); this is not an audit of every manuscript number")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
