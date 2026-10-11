#!/usr/bin/env python3
"""Create the current MIC-50-90 software source bundle.

The shared source selection is checked against PACKAGE_MANIFEST.sha256 first.
Installers and the portable application have separate builders and receipts.
An existing destination is never replaced.
"""

from __future__ import annotations

import argparse
import datetime
import json
import hashlib
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from package_files import source_files  # noqa: E402
from manifest_tools import check_manifest as inspect_manifest  # noqa: E402


def selected_files() -> list[Path]:
    """The current source bundle and root manifest share this exact selection."""
    return source_files(ROOT)


def check_manifest(files: list[Path]) -> list[str]:
    """Inspect, never rewrite, the shared source manifest before packaging."""
    return inspect_manifest(ROOT / "PACKAGE_MANIFEST.sha256", ROOT, files)["problems"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="explicit source-bundle destination")
    args = parser.parse_args()
    registry = json.loads((ROOT / "PACKAGE_STATUS.json").read_text(encoding="utf-8"))
    destination = args.output or ROOT / registry["current_delivery"] / "MIC-50-90-1.0.0-source-bundle.zip"
    if destination.exists():
        raise SystemExit("Destination already exists; choose a new path to preserve dated evidence")
    files = selected_files()
    stale = check_manifest(files)
    if stale:
        print("REFUSING TO BUILD: PACKAGE_MANIFEST.sha256 does not describe this source selection.")
        for line in stale:
            print(f"  {line}")
        raise SystemExit(3)
    # The software-only source selection excludes editorial materials.
    # Python installers and the portable application have separate build receipts.
    destination.parent.mkdir(parents=True, exist_ok=True)
    payloads = []
    manifest_lines = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        payload = path.read_bytes()
        payloads.append((relative, payload))
        manifest_lines.append(f"{hashlib.sha256(payload).hexdigest()}  {relative}")
    manifest = "\n".join(manifest_lines) + "\n"

    # A deterministic timestamp derived from content, not a claimed execution date.
    stamp = int(hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:8], 16)
    when = (datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=1 + stamp % 86400)).timetuple()[:6]

    def entry(name: str) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(name, date_time=when)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        return info

    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, payload in payloads:
            archive.writestr(entry(relative), payload)
        archive.writestr(entry("MANIFEST.sha256"), manifest)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(f"Built {destination} with {len(files)} files")
    print(f"SHA-256 {digest}")


if __name__ == "__main__":
    main()
