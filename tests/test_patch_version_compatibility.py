"""A repaired patch version preserves the explicitly supported prior contracts."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("version", ["1.0.0", "1.0.1", "1.0.2", "1.0.3"])
def test_patch_102_accepts_known_distribution_producers(monkeypatch, version):
    from mic_50_90 import _version
    from mic_50_90.result_schema import validate_distribution_schema
    monkeypatch.setattr(_version, "__version__", "1.0.3")
    document = {"software": "MIC-50-90", "software_version": version,
                "result_schema": "mic-50-90.distribution/1"}
    before = deepcopy(document)
    validate_distribution_schema(document)
    assert document == before


@pytest.mark.parametrize("version", ["1.0.0", "1.0.1", "1.0.2", "1.0.3"])
def test_patch_102_recipient_example_accepts_known_certificate_versions(tmp_path, version):
    document = json.loads((ROOT / "examples/received_report/certificate.json").read_text())
    document["version"] = version
    path = tmp_path / "certificate.json"
    path.write_text(json.dumps(document))
    result = subprocess.run([sys.executable, str(ROOT / "examples/received_report/verify.py"), str(path)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Sufficient" in result.stdout


@pytest.mark.parametrize("version", ["1.0.0", "1.0.1", "1.0.2", "1.0.3"])
def test_patch_102_gui_accepts_known_certificate_versions(version):
    from mic_50_90.gui_documents import validate_document
    document = json.loads((ROOT / "examples/received_report/certificate.json").read_text())
    document["version"] = version
    result = validate_document({"mode": "verify-report", "certificate": document})
    assert result["valid"], result["issues"]
