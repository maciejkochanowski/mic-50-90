"""A green wrapper process cannot replace examination of individual test results."""
import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).resolve().parents[1] / "tools/check_release_tests.py"
_spec = importlib.util.spec_from_file_location("release_test_evidence", _path)
evidence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evidence)


def matrix(root):
    for name in evidence.EXPECTED:
        directory = root / name
        directory.mkdir()
        (directory / "test-results.xml").write_text(
            '<testsuites><testsuite tests="1" errors="0" failures="0" skipped="0" time="1.5">'
            '<testcase name="reference"/></testsuite></testsuites>', encoding="utf-8")
    return next(root.rglob("test-results.xml"))


def test_complete_passing_matrix(tmp_path):
    matrix(tmp_path)
    assert evidence.verify_matrix(tmp_path)["platforms_checked"] == 6


def test_missing_platform_is_rejected(tmp_path):
    matrix(tmp_path).unlink()
    with pytest.raises(ValueError, match="Exactly one"):
        evidence.verify_matrix(tmp_path)


@pytest.mark.parametrize("failure", ["failure", "error"])
def test_actual_failed_case_is_rejected_even_with_green_wrapper(tmp_path, failure):
    path = matrix(tmp_path)
    field = "failures" if failure == "failure" else "errors"
    text = path.read_text(encoding="utf-8").replace(f'{field}="0"', f'{field}="1"')
    text = text.replace('<testcase name="reference"/>', f'<testcase name="reference"><{failure}/></testcase>')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="passing"):
        evidence.verify_matrix(tmp_path)


def test_contradictory_totals_are_rejected(tmp_path):
    path = matrix(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('tests="1"', 'tests="2"'), encoding="utf-8")
    with pytest.raises(ValueError, match="disagree"):
        evidence.verify_matrix(tmp_path)


def test_all_skipped_is_rejected(tmp_path):
    path = matrix(tmp_path)
    text = path.read_text(encoding="utf-8").replace('skipped="0"', 'skipped="1"')
    text = text.replace('<testcase name="reference"/>', '<testcase name="reference"><skipped/></testcase>')
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty"):
        evidence.verify_matrix(tmp_path)


def test_changed_testcase_identity_is_rejected(tmp_path):
    path = matrix(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace('name="reference"', 'name="different"'), encoding="utf-8")
    with pytest.raises(ValueError, match="different testcase"):
        evidence.verify_matrix(tmp_path)
