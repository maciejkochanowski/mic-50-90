"""Require complete, revision-bound passing Python evidence before publication."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
import xml.etree.ElementTree as ET

EXPECTED = {f"verification-{platform}-{version}"
            for platform in ("ubuntu-latest", "windows-latest")
            for version in ("3.11", "3.12", "3.13")}
MANIFEST_SCHEMA = "mic-50-90.test-manifest/1"
IDENTITY_FIELDS = ("source_commit", "source_tree_sha256", "wheel_sha256")


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key: " + key)
        value[key] = item
    return value


def read_json(path: Path) -> dict:
    if path.is_symlink() or path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Invalid or oversized evidence file: " + str(path))
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("Evidence must be a JSON object: " + str(path))
    return value


def load_manifest(path: Path, expected_commit: str) -> dict:
    data = read_json(path)
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("Expected a full source commit, not a branch or tag")
    if data.get("schema") != MANIFEST_SCHEMA or data.get("source_commit") != expected_commit:
        raise ValueError("Test manifest schema or source commit/revision does not match")
    for name in ("source_tree_sha256", "wheel_sha256"):
        if not isinstance(data.get(name), str) or not re.fullmatch(r"[0-9a-f]{64}", data[name]):
            raise ValueError("Invalid identity field: " + name)
    ids = data.get("test_ids")
    protected = data.get("non_skippable_test_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids):
        raise ValueError("Test manifest requires a non-empty expected test list")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate expected testcase identities")
    if (not isinstance(protected, list) or any(not isinstance(x, str) for x in protected)
            or len(protected) != len(set(protected)) or not set(protected) <= set(ids)):
        raise ValueError("Invalid non-skippable test identities")
    return data


def _properties(parent: ET.Element) -> dict[str, str]:
    result = {}
    for entry in parent.findall("./properties/property"):
        key, value = entry.get("name"), entry.get("value")
        if key is None or value is None or key in result:
            raise ValueError("Missing or duplicate JUnit provenance property")
        result[key] = value
    return result


def _allowed_skips(path: Path | None, manifest: dict) -> dict:
    if path is None:
        return {}
    policy = read_json(path)
    if policy.get("schema") != "mic-50-90.test-skips/1" or policy.get("source_commit") != manifest["source_commit"]:
        raise ValueError("Skip policy schema or source commit does not match")
    if not isinstance(policy.get("allow"), list):
        raise ValueError("Skip policy requires an explicit allow list")
    result = {}
    for row in policy["allow"]:
        if not isinstance(row, dict) or set(row) != {"job", "test_id", "reason"}:
            raise ValueError("Each skip exception must name a job, test_id and reason")
        if row["job"] not in EXPECTED or row["test_id"] not in manifest["test_ids"]:
            raise ValueError("Skip policy refers to an unknown job or test")
        if row["test_id"] in manifest["non_skippable_test_ids"]:
            raise ValueError("Required/non-skippable test cannot be whitelisted")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise ValueError("Skip exceptions require a non-empty reason")
        key = (row["job"], row["test_id"])
        if key in result:
            raise ValueError("Duplicate skip exception")
        result[key] = row["reason"]
    return result


def verify_matrix(directory: Path, *, manifest: Path, expected_commit: str,
                  skip_policy: Path | None = None) -> dict:
    files = sorted(directory.rglob("test-results.xml"))
    if len(files) != len(EXPECTED) or {path.parent.name for path in files} != EXPECTED:
        raise ValueError("Exactly one JUnit report is required for every Windows/Linux Python 3.11–3.13 job")
    expected = load_manifest(manifest, expected_commit)
    manifest_sha = sha256(manifest.read_bytes()).hexdigest()
    allowed = _allowed_skips(skip_policy, expected)
    expected_ids = set(expected["test_ids"])
    rows = []
    identities = None
    for path in files:
        if path.is_symlink() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Invalid or oversized JUnit report: " + str(path))
        data = path.read_bytes()
        if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
            raise ValueError("DTD/entity declarations are not allowed in JUnit evidence")
        root = ET.fromstring(data)
        suites = list(root.iter("testsuite"))
        if len(suites) != 1:
            raise ValueError("Expected one pytest test suite in " + str(path))
        suite = suites[0]
        totals = {key: int(suite.attrib[key]) for key in ("tests", "errors", "failures", "skipped")}
        if any(value < 0 for value in totals.values()):
            raise ValueError("Negative JUnit totals: " + str(path))
        cases = suite.findall("testcase")
        current = [(case.attrib.get("classname", ""), case.attrib["name"]) for case in cases]
        if len(current) != len(set(current)):
            raise ValueError("Duplicate testcase identities: " + str(path))
        observed = {"tests": len(cases), "errors": sum(case.find("error") is not None for case in cases),
                    "failures": sum(case.find("failure") is not None for case in cases),
                    "skipped": sum(case.find("skipped") is not None for case in cases)}
        if observed != totals or any(sum(case.find(tag) is not None for tag in ("error", "failure", "skipped")) > 1 for case in cases):
            raise ValueError("JUnit totals disagree with individual test cases: " + str(path))
        if totals["errors"] or totals["failures"] or totals["tests"] <= totals["skipped"]:
            raise ValueError("Release requires a passing, non-empty test suite: " + str(path))
        properties = _properties(suite)
        needed = {key: expected[key] for key in IDENTITY_FIELDS}
        needed.update(test_manifest_sha256=manifest_sha, runner_exit_code="0",
                      platform="Windows" if "windows" in path.parent.name else "Linux",
                      python_version=path.parent.name.rsplit("-", 1)[1])
        if any(properties.get(key) != value for key, value in needed.items()):
            raise ValueError("JUnit provenance/identity or runner outcome does not match: " + str(path))
        ids = [_properties(case).get("mic_50_90_nodeid") for case in cases]
        if any(not ident for ident in ids) or len(ids) != len(set(ids)):
            raise ValueError("Missing or Duplicate JUnit test IDs: " + str(path))
        if set(ids) != expected_ids:
            raise ValueError("JUnit cases differ from expected manifest: " + str(path))
        for case, ident in zip(cases, ids, strict=True):
            prefix, bracket, parameters = ident.partition("[")
            expected_name = prefix.split("::")[-1] + bracket + parameters
            if case.attrib["name"] != expected_name:
                raise ValueError("JUnit contains different testcase identity/name: " + str(path))
        if identities is None:
            identities = set(current)
        elif identities != set(current):
            raise ValueError("The platform reports contain different testcase identities: " + str(path))
        accepted = []
        for case, ident in zip(cases, ids, strict=True):
            skipped = case.find("skipped")
            if skipped is not None:
                key = (path.parent.name, ident)
                if key not in allowed:
                    raise ValueError("Unapproved skipped test: " + ident + " in " + path.parent.name)
                accepted.append({"test_id": ident, "reason": allowed[key], "observed_reason": skipped.get("message", "")})
        seconds = float(suite.attrib["time"])
        if not isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid JUnit duration")
        rows.append({"platform": path.parent.name, **totals, "executed": totals["tests"] - totals["skipped"],
                     "allowed_skips": accepted, "seconds": seconds, "junit_sha256": sha256(data).hexdigest()})
    return {"status": "passed", **{key: expected[key] for key in IDENTITY_FIELDS},
            "test_manifest_sha256": manifest_sha, "expected_testcases": len(expected_ids),
            "skip_policy_sha256": None if skip_policy is None else sha256(skip_policy.read_bytes()).hexdigest(),
            "platforms_checked": len(rows), "checks": rows,
            "rule": "all six platform jobs; every expected ID; bound source/wheel; zero failures/errors; no unapproved skips"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--skip-policy", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("Use a new receipt path")
    try:
        result = verify_matrix(args.directory, manifest=args.manifest, expected_commit=args.commit, skip_policy=args.skip_policy)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        parser.error(str(error))
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
