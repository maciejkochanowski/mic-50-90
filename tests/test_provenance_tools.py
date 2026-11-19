"""Provenance tools: source manifest, source bundle and archive check."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(script, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def test_shared_manifest_includes_runtime_assets_and_user_docs_but_excludes_article(tmp_path):
    names = ["src/mic_50_90/report_assets/fonts/body.woff2", "src/mic_50_90/report_assets/typography.css",
             "docs/new-guide.md", "tests/test_new.py",
             "reproducibility/independent-check/oracle.py"]
    for name in names:
        write(tmp_path, name, "measured fixture\n")
    editorial = ["manuscript/softwarex_1.0.0/main.md",
                 "docs/MIC-50-90-main-1.0.0.pdf",
                 "examples/MIC-50-90-1.0.0-Appendix-A-Methods.pdf",
                 "scripts/appendix_a_claims_1_0_0.json"]
    for name in editorial:
        write(tmp_path, name, "must remain outside software package")
    write(tmp_path, "src/mic_50_90/__pycache__/ignored.pyc", "cache")
    manifest = tmp_path / "PACKAGE_MANIFEST.sha256"
    result = run("refresh_package_manifest.py", "--root", tmp_path, "--manifest", manifest)
    assert result.returncode == 0, result.stdout + result.stderr
    recorded = manifest.read_text(encoding="utf-8")
    assert all(name in recorded for name in names)
    assert "ignored.pyc" not in recorded
    assert all(name not in recorded for name in editorial)
    write(tmp_path, names[0], "changed font\n")
    bad = run("refresh_package_manifest.py", "--root", tmp_path, "--manifest", manifest, "--check")
    assert bad.returncode == 1
    assert names[0] in bad.stdout
    assert sha(manifest) in bad.stdout


def test_source_bundle_uses_the_manifest_selection_and_refuses_replacement(tmp_path, monkeypatch):
    write(tmp_path, "PACKAGE_STATUS.json", '{"current_delivery": "dist/current"}\n')
    write(tmp_path, "src/mic_50_90/report_assets/fonts/body.woff2", "font bytes")
    write(tmp_path, "docs/current.md", "current document\n")
    result = run("refresh_package_manifest.py", "--root", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    spec = importlib.util.spec_from_file_location("bundle_under_test", ROOT / "scripts/build_release_bundle.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    target = tmp_path / "delivery.zip"
    monkeypatch.setattr(sys, "argv", ["build_release_bundle.py", "--output", str(target)])
    module.main()
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {
            "PACKAGE_STATUS.json", "src/mic_50_90/report_assets/fonts/body.woff2",
            "docs/current.md", "MANIFEST.sha256",
        }
        assert archive.read("src/mic_50_90/report_assets/fonts/body.woff2") == b"font bytes"
    before = target.read_bytes()
    with pytest.raises(SystemExit, match="already exists"):
        module.main()
    assert target.read_bytes() == before


@pytest.mark.parametrize("target", ["manifest", "member", "hardlink"])
def test_manifest_check_report_cannot_replace_checked_evidence(tmp_path, target):
    source = write(tmp_path, "src/mic_50_90/model.py", "# evidence to retain\n")
    manifest = write(tmp_path, "MANIFEST.sha256", f"{sha(source)}  src/mic_50_90/model.py\n")
    output = manifest if target == "manifest" else source
    if target == "hardlink":
        output = tmp_path / "report.json"
        output.hardlink_to(source)
    before = {path: path.read_bytes() for path in (manifest, source)}
    result = run("refresh_package_manifest.py", "--root", tmp_path, "--manifest", manifest,
                 "--check", "--scope", "listed", "--json-report", output)
    assert result.returncode == 2, result.stdout + result.stderr
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize("names", [[], ["a.whl"], ["a.whl", "b.whl"],
                                   ["a.tar.gz", "b.tar.gz"], ["a.whl", "a.tar.gz", "b.whl"]])
def test_archive_verification_requires_one_of_each_distribution_before_install(tmp_path, monkeypatch, names):
    for name in names:
        write(tmp_path, name, "fixture archive bytes\n")
    spec = importlib.util.spec_from_file_location("archive_check_under_test", ROOT / "scripts/check_release_archives.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Environment creation is the external side effect. Invalid selection must stop first.
    def unexpected_environment(*args, **kwargs):
        pytest.fail("Invalid archive selection reached environment creation")
    monkeypatch.setattr(module.tempfile, "mkdtemp", unexpected_environment)
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(sys, "argv", ["check_release_archives.py", str(tmp_path), "--receipt", str(receipt)])
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert not receipt.exists()
    assert {path: path.read_bytes() for path in before} == before
