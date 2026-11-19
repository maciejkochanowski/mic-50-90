# Engineering verification of MIC-50-90

Verification belongs to specific source and artifact hashes. For a supplied candidate,
the accompanying delivery receipt and acceptance report identify completed checks and
their environments. A historical public GitHub Actions run is not automatically evidence
for changed code or rebuilt artifacts. Windows/Linux and Python 3.11–3.13 are the intended
matrix; only actually completed cells can be claimed for a given delivery. A release title
or version string alone does not identify tested bytes.

| Check | What it establishes |
|---|---|
| Full Python suite | Input validation, calculations, reporting, saved updates, failure isolation and provenance behavior |
| Independent numerical controls | Agreement in explicitly enumerated histogram, rounding and coverage cases |
| Wheel/source archive installation | A controlled analysis executes outside the checkout with the installed package |
| Lean algebra | The stated algebraic consequences compile with their declared hypotheses; see ../formal/README.md |

Install the Python test dependencies first.

Run the source suite and coverage measurement with:

```text
python -m pytest tests --cov=mic_50_90 --cov-branch --cov-report=json:coverage.json -q
```

Statement and branch coverage measure executed software, not statistical coverage. Numerical oracles cover stated finite domains. Lean checks the algebraic lemmas rather than the entire Python program. An attempted run, an environment failure or an unavailable toolchain cannot be labelled a completed check. See PUBLIC_FUNCTIONS.md for links between tasks, code and checks, VALIDATION_SCOPE.md for scientific assumptions, and REPRODUCING_RESULTS.md for installation and examples.

Time-limited optional searches can return different partial results. A comparison must keep conservative bounds and completion status and remove only specifically identified time/location fields. Reports distinguish sample identification, population confidence, calibrated new-unit bounds and numerical precision.
