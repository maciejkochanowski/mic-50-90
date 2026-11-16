"""The actual built source distribution carries a complete tamper-detecting manifest."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_sdist(tmp_path_factory):
    directory = tmp_path_factory.mktemp("sdist-build")
    command = [sys.executable, "-c", "from hatchling.build import build_sdist; import sys; build_sdist(sys.argv[1])", str(directory)]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    archives = list(directory.glob("*.tar.gz"))
    assert len(archives) == 1
    extracted = directory / "extracted"
    with tarfile.open(archives[0], "r:gz") as archive:
        # Build output is trusted test input; the production hook checks its names.
        archive.extractall(extracted, filter="data")
    roots = list(extracted.iterdir())
    assert len(roots) == 1
    return archives[0], roots[0]


def manifest_check(root):
    command = [sys.executable, "-c", (
        "import runpy,sys; m=runpy.run_path(sys.argv[1]); "
        "m['check_manifest'](); raise SystemExit(bool(m['FAILURES']))"
    ), str(root / "reproducibility/self_test.py")]
    return subprocess.run(command, cwd=root, text=True, capture_output=True)


def test_built_sdist_manifest_covers_every_regular_member(built_sdist):
    archive_path, root = built_sdist
    manifest = root / "MANIFEST.sha256"
    assert manifest.is_file(), "The built sdist must include its own manifest"
    entries = dict((name, digest) for digest, name in (
        line.split("  ", 1) for line in manifest.read_text().splitlines() if line.strip()
    ))
    with tarfile.open(archive_path, "r:gz") as archive:
        files = {"/".join(member.name.split("/")[1:]): archive.extractfile(member).read()
                 for member in archive.getmembers() if member.isfile()}
    assert set(entries) == set(files) - {"MANIFEST.sha256"}
    assert "PKG-INFO" in entries
    assert "PACKAGE_STATUS.json" in entries
    assert all(hashlib.sha256(files[name]).hexdigest() == digest for name, digest in entries.items())


def test_actual_sdist_self_test_completes(built_sdist):
    _, root = built_sdist
    result = subprocess.run([sys.executable, str(root / "reproducibility/self_test.py")],
                            cwd=root, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MANIFEST.sha256:" in result.stdout
    assert "all match" in result.stdout


@pytest.mark.parametrize("damage", ["changed", "missing", "generated_metadata", "empty_manifest",
                                    "duplicate_manifest", "omitted_manifest_entry"])
def test_sdist_integrity_refuses_damage(built_sdist, tmp_path, damage):
    _, original = built_sdist
    root = tmp_path / "damaged"
    shutil.copytree(original, root)
    manifest = root / "MANIFEST.sha256"
    if damage == "changed":
        with (root / "README.md").open("a") as stream:
            stream.write("\nChanged after packaging.\n")
    elif damage == "missing":
        (root / "README.md").unlink()
    elif damage == "empty_manifest":
        manifest.write_text("")
    elif damage == "duplicate_manifest":
        with manifest.open("a") as stream:
            stream.write(manifest.read_text().splitlines()[0] + "\n")
    elif damage == "generated_metadata":
        with (root / "PKG-INFO").open("a") as stream:
            stream.write("\nAltered metadata.\n")
    else:
        manifest.write_text("\n".join(line for line in manifest.read_text().splitlines()
                                      if not line.endswith("  README.md")) + "\n")
    result = manifest_check(root)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FAILED" in result.stdout


def test_sdist_does_not_claim_to_contain_its_own_final_archive_digest(built_sdist):
    _, root = built_sdist
    status = json.loads((root / "PACKAGE_STATUS.json").read_text())
    assert not any(key in status for key in ("validated_wheel_sha256", "validated_sdist_sha256"))
    if status["public_release"] is False:
        assert status["release_url"] is None
    assert status["archive_identity_policy"] == "external_delivery_receipt"


def test_wheel_builds_from_actual_unpacked_sdist(built_sdist, tmp_path):
    _, root = built_sdist
    command = [sys.executable, "-c", "from hatchling.build import build_wheel; import sys; build_wheel(sys.argv[1])",
               str(tmp_path)]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        assert wheel.read("mic_50_90/_version.py") == (root / "src/mic_50_90/_version.py").read_bytes()
        assert any(name.endswith(".dist-info/RECORD") for name in wheel.namelist())
