# Reviewing MIC-50-90 1.0.0 software

Start with README.md, docs/GUI_GUIDE.md and docs/distribution-user-guide.md. The source tree contains the engine, application, tests, examples and formal algebra. The manuscript and supplementary appendices are supplied separately by the author and are not part of the public software distribution.

## Run the examples

Install the release wheel in a separate Python 3.11–3.13 environment. From an extracted source directory:

```text
python -m pip check
mic-50-90 distribution examples/distribution/summaries.json --output-dir output/summaries
mic-50-90 distribution examples/biological_cases/ampicillin-67-summaries.json --output-dir output/before
mic-50-90 distribution examples/biological_cases/ampicillin-67-with-count.json --output-dir output/after
python examples/received_report/verify.py examples/received_report/certificate.json
```

Read report.html, configuration.json and results.json together. The ampicillin sample bounds for recorded category 0.5 mg/L change from 1–32 to 2–7 under the declared ceiling-rank interpretation. The received-report example checks four sample answers without the source histogram. Source provenance and assumptions are retained beside each input.

## Inspect the checks

```text
python -m pip install ".[test]"
python -m pytest -q
node --test "tests/*.cjs"
```

docs/PUBLIC_FUNCTIONS.md maps scientific and practical tasks to functions, outputs and independent tests. docs/population-row-lift.md and formal/README.md describe the endpoint construction and scoped algebraic checks. Test execution coverage and statistical confidence are different quantities.

The tests workflow runs on Windows and Linux with Python 3.11–3.13. The release workflow builds software packages and records their identities. Use the completed run and checksums as evidence for the downloaded assets. Numerical campaigns and article documents are maintained separately; this software package does not claim to contain that full editorial archive.
