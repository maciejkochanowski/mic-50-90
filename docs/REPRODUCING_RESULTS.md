# Reproduce software examples and verification

This source package contains the engine, tests, examples, formal algebra and build tools. Manuscripts, supplementary appendices and the author's combined editorial archive are maintained separately. Work in an extracted source copy and use a fresh output directory for each analysis.

## Installed software

```text
python -m venv check-env
check-env/Scripts/python -m pip install path/to/mic_50_90-1.0.0-py3-none-any.whl
```

On Linux use check-env/bin/python. Activate that environment before running the following commands from the source copy:

```text
mic-50-90 distribution examples/distribution/summaries.json --output-dir output/summaries
mic-50-90 distribution examples/biological_cases/ampicillin-67-summaries.json --output-dir output/before
mic-50-90 distribution examples/biological_cases/ampicillin-67-with-count.json --output-dir output/after
python examples/received_report/verify.py examples/received_report/certificate.json
```

Open each report.html and retain configuration.json and results.json. The ampicillin category 0.5 mg/L has sample limits 1–32 before the additional count and 2–7 afterward, under the ranks declared in its input. The examples retain their source references and assumptions. See distribution-user-guide.md, GUI_GUIDE.md and REPORT_CONTENTS.md for interpretation and saved updates.

## Tests and independent controls

```text
python -m pip install ".[test]"
python -m pytest tests -q
node --test "tests/*.cjs"
```

The tests include independent finite-histogram enumeration, exact binomial coverage controls, decimal rounding checks, interrupted-search bounds and Windows-form/CLI behavior. See PUBLIC_FUNCTIONS.md for the task-to-test map. Test execution and empirical statistical coverage have different meanings.

The standalone oracle for joint inference is reproducibility/v1.0.0/joint-distribution-20260930/oracle.py. formal/README.md describes the pinned Lean environment and the scope of its algebraic proof. The retained calibration adapter and unit-allocation helper are exercised by the panel-convention tests. Their external-data entry point requires separately provided source data. Historical research campaigns and HPC launchers are outside this software package.

## Build and install checks

```text
python -m pip install build
python -m build
python scripts/check_release_archives.py dist --receipt archive-check.json
```

The archive checker installs the wheel and source archive in independent temporary environments and runs a controlled analysis outside the checkout. BUILD_WINDOWS.md covers the native application. The GitHub Actions tests workflow runs Windows/Linux with Python 3.11–3.13. The release workflow builds, checks and uploads software assets only.

For a source integrity snapshot and an offline software self-test:

```text
python scripts/refresh_package_manifest.py --manifest PACKAGE_MANIFEST.sha256
python scripts/refresh_package_manifest.py --manifest PACKAGE_MANIFEST.sha256 --check
python reproducibility/self_test.py
```

Creating a hash manifest records identity; it is not itself evidence of mathematical correctness. The self-test checks a hand-derived bound, a real report with known counts, schemas and the recorded files. Keep its receipt and the completed Actions run with the release checksums.
