"""Rewrite PACKAGE_MANIFEST.sha256 over exactly the files a bundle would ship.

The manifest and the bundle read one list, `build_release_bundle.selected_files()`, so the
two cannot drift apart. That is the point: a manifest maintained separately from the thing
it describes records the state of a third thing nobody looks at.

    PYTHONPATH=src .venv/bin/python scripts/refresh_package_manifest.py
    PYTHONPATH=src .venv/bin/python scripts/refresh_package_manifest.py --check

`--check` writes nothing and exits non-zero on drift. Use it in review; use the bare form
only after a deliberate change, because a manifest that silently follows whatever is on
disk is not evidence of anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_files import source_files  # noqa: E402
from manifest_tools import check_manifest, read_manifest, sha  # noqa: E402

MANIFEST = ROOT / "PACKAGE_MANIFEST.sha256"


def current(root: Path = ROOT) -> list[str]:
    return [
        f"{sha(path)}  {path.relative_to(root).as_posix()}"
        for path in source_files(root)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="report drift without rewriting the manifest")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=Path("PACKAGE_MANIFEST.sha256"))
    parser.add_argument("--scope", choices=("source", "listed"), default="source",
                        help="source checks the shared delivery selection; listed checks an explicit archive manifest")
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / args.manifest
    if args.check:
        selected = source_files(root) if args.scope == "source" else None
        inputs = {manifest, *(selected or [])}
        try:
            inputs.update(root / name for name in read_manifest(manifest, root))
        except (OSError, UnicodeError, ValueError):
            pass  # The manifest check below reports malformed or missing inputs.
        if args.json_report and any(
            args.json_report.resolve() == path.resolve()
            or (args.json_report.exists() and path.exists() and args.json_report.samefile(path))
            for path in inputs
        ):
            parser.error("--json-report must not overwrite the manifest or checked source files")
        report = check_manifest(manifest, root, selected)
        print(f"manifest: {report['path']} SHA256={report['sha256']}")
        for problem in report["problems"]:
            print(f"  {problem}")
        print(f"{report['status'].upper()}: {report['entries']} manifest entries; scope={args.scope}")
        if args.json_report:
            args.json_report.parent.mkdir(parents=True, exist_ok=True)
            args.json_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return 0 if report["status"] == "passed" else 1
    if args.scope != "source":
        parser.error("--scope listed is read-only and requires --check")
    lines = current(root)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {manifest}: {len(lines)} files; SHA256={sha(manifest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
