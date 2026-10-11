"""Clean-room check that a shipped MIC-50-90 package is intact and runnable.

No network, no downloads, no fixtures beyond what the package carries. This is the first
thing a reviewer runs and the first thing that fails when a bundle was assembled wrongly,
so every step reports what it looked at rather than only whether it passed.

    PYTHONPATH=src python3 reproducibility/self_test.py

Five steps. The manifest step tolerates its own absence, because the source tree and a
built bundle carry different manifests, and reports which one it used.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FAILURES: list[str] = []


def step(number: int, title: str) -> None:
    print(f"\n[{number}/5] {title}")


def ok(message: str) -> None:
    print(f"      {message}")


def bad(message: str) -> None:
    print(f"      FAILED: {message}")
    FAILURES.append(message)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_import() -> None:
    step(1, "package imports and declares one version")
    try:
        import mic_50_90
        from mic_50_90.empirical import EmpiricalProblem  # noqa: F401
        from mic_50_90.model import MICPanel, QuantileSummary  # noqa: F401
    except Exception as exc:
        bad(f"import failed: {exc}")
        return
    declared = None
    for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            declared = line.split("=", 1)[1].strip().strip('"')
            break
    ok(f"mic_50_90 imported from {Path(mic_50_90.__file__).parent}")
    if declared is None:
        bad("pyproject.toml declares no version")
    else:
        ok(f"pyproject version {declared}")
        installed = getattr(mic_50_90, "__version__", None)
        if installed is not None and installed != declared:
            bad(f"mic_50_90.__version__ is {installed}, pyproject says {declared}")


def check_schemas() -> None:
    step(2, "schemas parse and the shipped examples validate against them")
    try:
        import jsonschema
    except ImportError:
        ok("jsonschema is not installed; parsing schemas without validating")
        jsonschema = None
    for name in ("input.schema.json", "output.schema.json"):
        path = ROOT / "schemas" / name
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            bad(f"{name} does not parse: {exc}")
            continue
        ok(f"{name} parses, {len(schema.get('properties', {}))} top-level properties")
    if jsonschema is None:
        return
    schema = json.loads((ROOT / "schemas" / "input.schema.json").read_text(encoding="utf-8"))
    for example in sorted((ROOT / "examples").glob("*.json")):
        document = json.loads(example.read_text(encoding="utf-8"))
        # examples/ also carries helper inputs for single modules, which are not analysis
        # documents and are not governed by the input contract. The contract marker is
        # what separates them, so absence of the marker is a skip and never a pass.
        if "contract_version" not in document:
            ok(f"{example.name} carries no contract marker; not an analysis document, skipped")
            continue
        try:
            jsonschema.validate(document, schema)
            ok(f"{example.name} validates")
        except jsonschema.ValidationError as exc:
            bad(f"{example.name} does not validate: {exc.message}")


def check_solver() -> None:
    step(3, "the solver reproduces a bound whose answer is known by hand")
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICBin, MICPanel, QuantileSummary

    # Twenty isolates on a four-category panel, MIC50 in category 1 and MIC90 in category 2.
    # The rank argument alone fixes the identified set for a threshold above category 2:
    # at most n - ceil(0.9 n) = 2 isolates can exceed it, and none is forced to.
    panel = MICPanel(
        tuple(
            MICBin(
                label=f"c{i}",
                lower=float(2**i),
                upper=float(2**i),
                lower_closed=True,
                upper_closed=True,
                panel_value=float(2**i),
            )
            for i in range(4)
        )
    )
    problem = EmpiricalProblem(
        n=20,
        panel=panel,
        quantiles=(
            QuantileSummary(0.5, 10, 1, panel.labels[1]),
            QuantileSummary(0.9, 18, 2, panel.labels[2]),
        ),
    )
    objective = [0.0, 0.0, 0.0, 1.0]
    low, high = problem.bounds(objective)
    if (low.count, high.count) != (0, 2):
        bad(f"expected counts (0, 2) above the top category, got ({low.count}, {high.count})")
    else:
        ok(f"sharp counts above the top category are {low.count} and {high.count}, as derived")


def check_bound_numbers() -> None:
    step(4, "a generated report reproduces independently known category counts")
    import tempfile
    from mic_50_90.distribution_workflow import analyse_distribution
    from mic_50_90.distribution_report import render_distribution_html
    raw = dict(n=20, unit="mg/L", panel=dict(levels=[1, 2, 4]),
               additional_counts=[dict(threshold=1, count=8, n=20, unit="mg/L"),
                                  dict(threshold=2, count=2, n=20, unit="mg/L")],
               targets=[dict(start_category="2", end_category="2", unit="mg/L",
                             decision_operator="<=", decision_fraction=".3")])
    result = analyse_distribution(raw)
    target = result["decisions"][0]["sample"]
    if target["count_components"] != [[6, 6]] or target["status"] != "supported":
        bad(f"expected exactly six middle-category isolates, got {target}")
        return
    with tempfile.TemporaryDirectory(prefix="mic-software-self-test-") as directory:
        destination = Path(directory) / "report.html"
        render_distribution_html({"software_version": "1.0.0", "cohorts": [result]}, destination)
        text = destination.read_text(encoding="utf-8")
        if "recorded MIC category 2 mg/L" not in text:
            bad("known category question missing from the generated report")
            return
    ok("8 above 1 minus 2 above 2 gives six middle-category isolates; report created")


def check_manifest() -> None:
    step(5, "shipped artefacts match their recorded digests")
    candidates = [
        ROOT / "MANIFEST.sha256",              # written into a built bundle
        ROOT / "PACKAGE_MANIFEST.sha256",      # the source tree

    ]
    used = [path for path in candidates if path.is_file()]
    if not used:
        bad("no manifest of any kind is present")
        return
    for manifest in used:
        checked = missing = changed = 0
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, relative = line.split("  ", 1)
            target = ROOT / relative
            checked += 1
            if not target.is_file():
                missing += 1
            elif sha(target) != digest:
                changed += 1
        if missing or changed:
            bad(f"{manifest.name}: {checked} entries, {missing} missing, {changed} changed")
        else:
            ok(f"{manifest.name}: {checked} entries, all match")


def main() -> int:
    print(f"MIC-50-90 self test, root {ROOT}")
    check_import()
    check_schemas()
    check_solver()
    check_bound_numbers()
    check_manifest()
    print()
    if FAILURES:
        print(f"FAILED - {len(FAILURES)} step(s) reported a problem:")
        for line in FAILURES:
            print(f"  - {line}")
        return 1
    print("PASS - the package is intact and its controlled numerical example and reports agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
