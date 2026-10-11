"""UTF-8 SHA-256 manifests with explicit roots, safe paths and diagnostic identities."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_manifest(path: Path, root: Path) -> dict[str, str]:
    entries = {}
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if not match:
            raise ValueError(f"invalid manifest line {index}")
        digest, name = match.groups()
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or not (root / relative).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"unsafe manifest path: {name}")
        if name in entries:
            raise ValueError(f"duplicate manifest path: {name}")
        entries[name] = digest.lower()
    if not entries:
        raise ValueError("empty manifest")
    return entries


def check_manifest(path: Path, root: Path, expected_files=None) -> dict:
    report = {"path": str(path.resolve()), "sha256": sha(path) if path.is_file() else None,
              "root": str(root.resolve()), "problems": [], "entries": 0}
    try:
        entries = read_manifest(path, root)
    except (OSError, UnicodeError, ValueError) as exc:
        report["problems"].append(str(exc))
        report["status"] = "failed"
        return report
    report["entries"] = len(entries)
    for name, recorded in entries.items():
        member = root / name
        if not member.is_file():
            report["problems"].append(f"missing: {name}")
        elif sha(member) != recorded:
            report["problems"].append(f"changed: {name}")
    if expected_files is not None:
        expected = {p.relative_to(root).as_posix() for p in expected_files}
        report["selected_files"] = len(expected)
        report["problems"].extend(f"not in manifest: {name}" for name in sorted(expected - entries.keys()))
        report["problems"].extend(f"in manifest but not selected: {name}" for name in sorted(entries.keys() - expected))
    report["status"] = "passed" if not report["problems"] else "failed"
    return report
