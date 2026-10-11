"""Executable provenance regressions; these tools belong to the source/reproduction tree."""
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
pytestmark = pytest.mark.skipif(
    not (ROOT / "scripts/verify_manuscript_numbers.py").is_file(),
    reason="this optional source verification requires the supplied provenance tools",
)


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


def fixture_claim(root):
    doc = write(root, "paper.md", "The collection contains 67 isolates. Unrelated value: 67.\n")
    result = write(root, "results/counts.json", '{"denominator": 67}\n')
    claims = write(root, "claims.json", json.dumps({"claims": [{
        "id": "collection-denominator", "pattern": r"The collection contains (?P<value>\d+) isolates",
        "source": "results/counts.json", "field": "denominator", "format": ".0f",
    }]}))
    manifest = write(root, "MANIFEST.sha256", f"{sha(doc)}  paper.md\n{sha(result)}  results/counts.json\n")
    return doc, result, claims, manifest


def test_current_manuscript_is_identified_and_a_changed_contextual_number_fails(tmp_path):
    doc, source, claims, manifest = fixture_claim(tmp_path)
    output = tmp_path / "report.json"
    args = ("--root", tmp_path, "--manuscript", doc, "--manifest", manifest,
            "--claims", claims, "--json-report", output)
    good = run("verify_manuscript_numbers.py", *args)
    assert good.returncode == 0, good.stdout + good.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["manuscript"]["sha256"] == sha(doc)
    assert report["manifest"]["sha256"] == sha(manifest)
    assert report["claims"][0]["source_sha256"] == sha(source)
    doc.write_text("The collection contains 68 isolates. Unrelated value: 67.\n", encoding="utf-8")
    # Bind the changed copy honestly: only the number-to-source check can catch this.
    manifest.write_text(f"{sha(doc)}  paper.md\n{sha(source)}  results/counts.json\n", encoding="utf-8")
    bad = run("verify_manuscript_numbers.py", *args)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["claims"][0]["id"] == "collection-denominator"
    assert report["claims"][0]["status"] == "mismatch"
    assert report["claims"][0]["observed"] == "68"
    assert report["claims"][0]["expected"] == "67"


def test_current_manuscript_requires_its_exact_source_in_manifest(tmp_path):
    doc, source, claims, manifest = fixture_claim(tmp_path)
    manifest.write_text(f"{sha(doc)}  paper.md\n", encoding="utf-8")
    result = run("verify_manuscript_numbers.py", "--root", tmp_path, "--manuscript", doc,
                 "--manifest", manifest, "--claims", claims)
    assert result.returncode == 1
    assert "results/counts.json" in result.stdout


def test_engineering_number_does_not_pass_with_a_different_recorded_runtime(tmp_path):
    doc, source, claims, manifest = fixture_claim(tmp_path)
    runtime = write(tmp_path, "src/mic_50_90/engine.py", "# current runtime\n")
    source.write_text(json.dumps({"denominator": 67, "runtime_sha256": {
        "src/mic_50_90/engine.py": "0" * 64}}), encoding="utf-8")
    definition = json.loads(claims.read_text(encoding="utf-8"))
    definition["claims"][0]["source_hashes_field"] = "runtime_sha256"
    claims.write_text(json.dumps(definition), encoding="utf-8")
    manifest.write_text(f"{sha(doc)}  paper.md\n{sha(source)}  results/counts.json\n"
                        f"{sha(runtime)}  src/mic_50_90/engine.py\n", encoding="utf-8")
    output = tmp_path / "report.json"
    bad = run("verify_manuscript_numbers.py", "--root", tmp_path, "--manuscript", doc,
              "--manifest", manifest, "--claims", claims, "--json-report", output)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    row = json.loads(output.read_text(encoding="utf-8"))["claims"][0]
    assert row["source_current_match"]["status"] == "differs"
    assert "src/mic_50_90/engine.py" in row["source_current_match"]["differences"]


def test_shared_manifest_includes_runtime_assets_and_user_docs_but_excludes_article(tmp_path):
    names = ["src/mic_50_90/gui_assets/fonts/body.woff2", "src/mic_50_90/gui_assets/typography.css",
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
    write(tmp_path, "src/mic_50_90/gui_assets/fonts/body.woff2", "font bytes")
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
            "PACKAGE_STATUS.json", "src/mic_50_90/gui_assets/fonts/body.woff2",
            "docs/current.md", "MANIFEST.sha256",
        }
        assert archive.read("src/mic_50_90/gui_assets/fonts/body.woff2") == b"font bytes"
    before = target.read_bytes()
    with pytest.raises(SystemExit, match="already exists"):
        module.main()
    assert target.read_bytes() == before


def fixture_receipt(root):
    code = write(root, "src/mic_50_90/model.py", "# source at run\n")
    output = write(root, "results/out.json", '{"count": 67}\n')
    receipt = write(root, "results/RECEIPT_fixture.json", json.dumps({
        "campaign": "fixture", "reproduction": "reproduced", "note": "Run on 2026-08-20.",
        "code": {"src/mic_50_90/model.py": sha(code)}, "inputs": {},
        "outputs": {"results/out.json": sha(output)},
    }))
    return code, output, receipt


def test_campaign_archive_integrity_and_current_source_drift_are_separate(tmp_path):
    code, output, receipt = fixture_receipt(tmp_path)
    old_receipt = receipt.read_bytes()
    code.write_text("# changed after the run\n", encoding="utf-8")
    report_path = tmp_path / "check.json"
    args = ("--root", tmp_path, "--receipt", receipt, "--check", "--report", report_path)
    result = run("write_campaign_receipts.py", *args, "--mode", "integrity")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))["campaigns"][0]
    assert report["artifact_integrity"]["status"] == "passed"
    assert report["current_source_match"]["status"] == "differs"
    assert report["recorded_reproduction"] == "reproduced"
    assert receipt.read_bytes() == old_receipt
    strict = run("write_campaign_receipts.py", *args, "--mode", "both")
    assert strict.returncode == 1
    output.write_text('{"count": 68}\n', encoding="utf-8")
    broken = run("write_campaign_receipts.py", *args, "--mode", "integrity")
    assert broken.returncode == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))["campaigns"][0]
    assert report["artifact_integrity"]["status"] == "differs"
    assert receipt.read_bytes() == old_receipt


def test_library_closure_reads_unicode_source_without_locale_override(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("closure_under_test", ROOT / "scripts/library_closure.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PACKAGE_DIR", tmp_path / "src/mic_50_90")
    write(tmp_path, "driver.py", "# source \u0143\nfrom mic_50_90 import model\n")
    write(tmp_path, "src/mic_50_90/__init__.py", "# \u0105\n")
    write(tmp_path, "src/mic_50_90/model.py", "# \u03b1\n")
    original_read = Path.read_text
    # Simulate the Polish Windows default without changing process-wide locale.
    def polish_default(path, encoding=None, errors=None):
        return original_read(path, encoding=encoding or "cp1250", errors=errors)
    monkeypatch.setattr(Path, "read_text", polish_default)
    assert module.modules_reached("driver.py") == ["src/mic_50_90/__init__.py", "src/mic_50_90/model.py"]


def test_library_closure_follows_subpackages_relative_and_literal_dynamic_imports(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('nested_closure', ROOT / 'scripts/library_closure.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'PACKAGE_DIR', tmp_path / 'src/mic_50_90')
    sources = {
        'driver.py':'from mic_50_90.engine import calculate\n',
        'src/mic_50_90/__init__.py':'',
        'src/mic_50_90/engine.py':'from ._nested.endpoint import calculate\n',
        'src/mic_50_90/_nested/__init__.py':'from . import registry\n',
        'src/mic_50_90/_nested/endpoint.py':'from ..model import Sample\nfrom .score import score\n',
        'src/mic_50_90/_nested/registry.py':'from importlib import import_module\nimport_module("mic_50_90._nested.dynamic")\n',
        'src/mic_50_90/_nested/dynamic.py':'',
        'src/mic_50_90/_nested/score.py':'',
        'src/mic_50_90/model.py':'',
    }
    for name, text in sources.items():write(tmp_path, name, text)
    assert module.modules_reached('driver.py') == sorted(name for name in sources if name.startswith('src/'))


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


@pytest.mark.parametrize("target", ["manuscript", "source", "claims", "manifest", "registry", "hardlink"])
@pytest.mark.parametrize("option", ["--json-report", "--report"])
def test_manuscript_report_cannot_replace_checked_inputs(tmp_path, target, option):
    doc, source, claims, manifest = fixture_claim(tmp_path)
    registry = write(tmp_path, "PACKAGE_STATUS.json", "{}\n")
    targets = dict(manuscript=doc, source=source, claims=claims, manifest=manifest, registry=registry)
    if target == "hardlink":
        targets[target] = tmp_path / "input-alias.json"
        targets[target].hardlink_to(source)
    before = {path: path.read_bytes() for path in targets.values()}
    output = tmp_path / "independent-report.json"
    extra = ("--json-report", output) if option == "--report" else ()
    result = run("verify_manuscript_numbers.py", "--root", tmp_path, "--manuscript", doc,
                 "--manifest", manifest, "--claims", claims, *extra, option, targets[target])
    assert result.returncode == 2, result.stdout + result.stderr
    assert {path: path.read_bytes() for path in before} == before
    assert not output.exists(), "Reject every conflicting destination before writing any report"


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
