# Engineering verification of MIC-50-90 1.0.0

The current public verification is the completed GitHub Actions run for the selected software source commit. It tests installed packages on Windows and Linux with Python 3.11–3.13. The release workflow records its build checks, source identity and asset checksums. A release title or version string alone does not identify tested bytes.

| Check | What it establishes |
|---|---|
| Full Python suite | Input validation, calculations, reporting, saved updates, failure isolation and provenance behavior |
| JavaScript tests | Form normalization, source-scale interpretation, saved-input preservation and practical workflows |
| Independent numerical controls | Agreement in explicitly enumerated histogram, rounding and coverage cases |
| Real browser checks | Form behavior, saved analysis and report controls in a running local application |
| Wheel/source archive installation | A controlled analysis executes outside the checkout with the installed package |
| Windows build receipt | Runtime files and resources included in the executable match their measured source |
| Lean algebra | The stated algebraic consequences compile with their declared hypotheses; see ../formal/README.md |

Run the source suite and coverage measurement with:

```text
python -m pytest tests --cov=mic_50_90 --cov-branch --cov-report=json:coverage.json -q
node --test "tests/*.cjs"
```

Statement and branch coverage measure executed software, not statistical coverage. Numerical oracles cover stated finite domains. Lean checks the algebraic lemmas rather than the entire Python program. See PUBLIC_FUNCTIONS.md for links between tasks, code and checks, and REPRODUCING_RESULTS.md for installation and examples.

Time-limited optional searches can return different partial results. A comparison must keep conservative bounds and completion status and remove only specifically identified time/location fields. Reports distinguish sample identification, population confidence, calibrated new-unit bounds and numerical precision.
