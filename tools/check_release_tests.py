"""Require complete, internally consistent, passing Python test evidence before upload."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import xml.etree.ElementTree as ET

EXPECTED = {f"verification-{platform}-{version}"
            for platform in ("ubuntu-latest", "windows-latest")
            for version in ("3.11", "3.12", "3.13")}


def verify_matrix(directory: Path) -> dict:
    files = sorted(directory.rglob("test-results.xml"))
    if len(files) != len(EXPECTED) or {path.parent.name for path in files} != EXPECTED:
        raise ValueError("Exactly one JUnit report is required for every Windows/Linux Python 3.11–3.13 job")
    rows = []
    identities = None
    for path in files:
        data = path.read_bytes()
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("Unexpectedly large JUnit report: " + str(path))
        suites = list(ET.fromstring(data).iter("testsuite"))
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
        if identities is None:
            identities = set(current)
        elif identities != set(current):
            raise ValueError("The platform reports contain different testcase identities: " + str(path))
        observed = {"tests": len(cases), "errors": sum(case.find("error") is not None for case in cases),
                    "failures": sum(case.find("failure") is not None for case in cases),
                    "skipped": sum(case.find("skipped") is not None for case in cases)}
        if observed != totals:
            raise ValueError("JUnit totals disagree with individual test cases: " + str(path))
        if totals["errors"] or totals["failures"] or totals["tests"] <= totals["skipped"]:
            raise ValueError("Release requires a passing, non-empty test suite: " + str(path))
        rows.append({"platform": path.parent.name, **totals, "seconds": float(suite.attrib["time"]),
                     "junit_sha256": sha256(data).hexdigest()})
    return {"status": "passed", "platforms_checked": len(rows), "checks": rows,
            "rule": "all six platform jobs; consistent JUnit counts; zero failures/errors; at least one executed test per job"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists():
        parser.error("Use a new receipt path")
    result = verify_matrix(args.directory)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
