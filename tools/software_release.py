"""Build and inspect software-only release archives; never include article files."""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tomllib
import zipfile

VERSION = "1.0.0"
FORBIDDEN_DIRS = {".git", "hpc", "manuscript", "manuscripts", "supplement", "supplements", "appendices"}
FORBIDDEN_SUFFIXES = {".pdf", ".doc", ".docx", ".tex", ".bib"}
FORBIDDEN_FILES = {"build_validation_notebook.py"}


def check_name(name: str) -> None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe archive path: {name}")
    if any(part.lower() in FORBIDDEN_DIRS for part in path.parts):
        raise ValueError(f"Excluded directory is forbidden in release archives: {name}")
    if path.name.lower() in FORBIDDEN_FILES:
        raise ValueError(f"Editorial audit generator is forbidden: {name}")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES or re.search(r"appendix[-_ ]?[abc](?:[._ -]|$)", path.name, re.I):
        raise ValueError(f"Publication document is forbidden: {name}")


def check_content(name: str, data: bytes) -> None:
    check_name(name)
    if data.startswith(b"%PDF-"):
        raise ValueError(f"PDF content is forbidden even under a different extension: {name}")
    if PurePosixPath(name).suffix.lower() in {".md", ".html", ".txt"}:
        text = data.decode("utf-8", errors="replace")
        headings = ("Motivation and significance", "Software description", "Illustrative examples")
        if all(heading in text for heading in headings) and re.search(r"(?im)^.{0,10}abstract\b", text):
            raise ValueError(f"Article text is forbidden: {name}")


def inspect_archive(path: Path) -> dict:
    checked = []

    def visit(name: str, data: bytes, depth: int = 0):
        check_content(name, data)
        checked.append(name)
        if depth > 4:
            raise ValueError("Nested archive depth exceeds the release inspection limit")
        if data.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    raise ValueError(f"Word document content is forbidden: {name}")
                for info in archive.infolist():
                    check_name(info.filename)
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError(f"Links are not allowed in release archives: {info.filename}")
                    if not info.is_dir():
                        if info.file_size > 256 * 1024 * 1024:
                            raise ValueError(f"Archive member exceeds inspection limit: {info.filename}")
                        visit(name + "!" + info.filename, archive.read(info), depth + 1)
        elif name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(fileobj=BytesIO(data), mode="r:gz") as archive:
                for info in archive:
                    check_name(info.name)
                    if info.issym() or info.islnk():
                        raise ValueError(f"Links are not allowed in release archives: {info.name}")
                    if info.isfile():
                        if info.size > 256 * 1024 * 1024:
                            raise ValueError(f"Archive member exceeds inspection limit: {info.name}")
                        visit(name + "!" + info.name, archive.extractfile(info).read(), depth + 1)

    visit(path.name, path.read_bytes())
    return {"file": path.name, "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()).hexdigest(), "checked_entries": len(checked), "status": "passed"}


def tracked_files(root: Path) -> list[Path]:
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0")
    paths = [root / name for name in names if name]
    for path in paths:
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Tracked release file is missing or a link: {relative}")
        check_content(relative, path.read_bytes())
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if version != VERSION:
        raise ValueError(f"Expected release version {VERSION}, found {version}")
    return paths


def source_archive(root: Path, output: Path) -> None:
    paths = tracked_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, f"MIC-50-90-{VERSION}/" + path.relative_to(root).as_posix())
    inspect_archive(output)


def windows_archive(application: Path, output: Path) -> None:
    if not (application / "MIC-50-90.exe").is_file():
        raise ValueError("A built MIC-50-90.exe is required")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(application.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Application symlink is forbidden: {path}")
            if path.is_file():
                name = f"MIC-50-90-{VERSION}-Windows/" + path.relative_to(application).as_posix()
                check_content(name, path.read_bytes())
                archive.write(path, name)
    inspect_archive(output)


def manifest(directory: Path, commit: str, run_url: str, publisher_commit=None, publisher_run_url=None) -> dict:
    files = sorted(path for path in directory.iterdir() if path.is_file())
    if any(path.name in {"SOFTWARE_MANIFEST.json", "SHA256SUMS.txt"} for path in files):
        raise ValueError("Use a fresh staging directory; manifests must not be overwritten")
    rows = [inspect_archive(path) for path in files]
    required = {f"mic_50_90-{VERSION}-py3-none-any.whl", f"mic_50_90-{VERSION}.tar.gz",
                f"MIC-50-90-{VERSION}-software-source.zip", f"MIC-50-90-{VERSION}-Windows-x64.zip"}
    if not required <= {row["file"] for row in rows}:
        raise ValueError("The release must contain a wheel, sdist, source ZIP and tested Windows ZIP")
    result = {"software": "MIC-50-90", "version": VERSION, "source_commit": commit,
              "actions_run": run_url, "scope": "software, usage documentation, examples and verification only",
              "publisher_commit": publisher_commit or commit, "publisher_actions_run": publisher_run_url or run_url,
              "article_documents_included": False, "files": rows}
    target = directory / "SOFTWARE_MANIFEST.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    files.append(target)
    (directory / "SHA256SUMS.txt").write_text("".join(
        f"{sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("source")
    source.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    source.add_argument("--output", type=Path, required=True)
    windows = commands.add_parser("windows")
    windows.add_argument("--application", type=Path, required=True)
    windows.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("paths", type=Path, nargs="+")
    final = commands.add_parser("manifest")
    final.add_argument("--directory", type=Path, required=True)
    final.add_argument("--commit", required=True)
    final.add_argument("--run-url", required=True)
    final.add_argument("--publisher-commit")
    final.add_argument("--publisher-run-url")
    args = parser.parse_args()
    if args.command == "source":
        source_archive(args.root.resolve(), args.output.resolve())
    elif args.command == "windows":
        windows_archive(args.application.resolve(), args.output.resolve())
    elif args.command == "check":
        print(json.dumps([inspect_archive(path) for path in args.paths], indent=2))
    else:
        print(json.dumps(manifest(args.directory, args.commit, args.run_url, args.publisher_commit, args.publisher_run_url), indent=2))


if __name__ == "__main__":
    main()
