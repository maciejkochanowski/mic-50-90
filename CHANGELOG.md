# Changelog

## 2.0.0 (unreleased)

- The local browser form (`mic-50-90 gui`, the `mic-50-90-gui` program) and the Windows application are removed. The Python interface and the command line remain, and the Galaxy tools in `galaxy/` give the same analyses in a web interface. Because a public command and program are removed, the major version changes.
- New command `mic-50-90 verify-report` checks a received reporting certificate from the declared summaries and the disclosed counts alone. It keeps exact decimal tokens, refuses contradictory disclosures and writes `verification.csv`, `verification.txt`, `results.json` and `report.html`; `--fail-on-insufficient` returns status 2 when a declared answer is not established. It replaces the verification step of the removed form.
- The HTML report resources (typography, print styles, report controls and fonts) move from `gui_assets` to `report_assets`. Reports separate list items with commas and semicolons instead of middle dots; their content is otherwise unchanged.
- The container image no longer includes Node.js, which only the removed form tests needed.
- Calculations, results and file formats are unchanged. Reporting certificates and distribution results produced by 1.0.0 to 1.0.3 are still accepted.

## 1.0.3 (2026-11-19)

- Each GitHub release also publishes a container image to the GitHub Container Registry (`ghcr.io/maciejkochanowski/mic-50-90`), tagged with the version and `latest`. The image is built from the release tag and checked before it is published.
- Two unused imports reported by the static checks are removed. Computations, results and file formats are unchanged from 1.0.2.
- The command reference lists the `distribution` options `--solver-execution` and `--solver-timeout`, which were missing from the 1.0.2 reference.
- Version checks accept reporting certificates and distribution results produced by 1.0.0, 1.0.1, 1.0.2 and 1.0.3. Unknown producer versions remain refused.

## 1.0.2 (2026-11-18)

- General integer-weighted objectives explicitly enforce a safe numerical domain, and returned objective values are recomputed exactly on integer witnesses. The large-weight audit reproducer is covered by regression tests; the domain restriction is a deliberate refusal of unsupported objectives.
- Histogram witnesses use explicit 64-bit integer storage so valid counts above the int32 range are preserved on platforms with narrower default NumPy integers. Numerical certification can still explicitly refuse difficult weighted objectives inside the supported input domain.
- The sdist build records SHA-256 digests of its actual regular members, including generated `PKG-INFO`, in `MANIFEST.sha256`. The source-tree manifest remains separate. The self-test rejects absent, empty, duplicate, incomplete or altered manifests.
- Package status no longer embeds stale archive hashes or a purported current commit. Final archive digests belong in an external delivery receipt. Release identity is recorded by the GitHub release, its checksums and the Zenodo record.
- Version checks retain compatibility with reporting certificates and distribution results produced by 1.0.0 and 1.0.1 while accepting 1.0.2. Unknown producer versions remain refused.
- Coverage-evaluation wording and summaries distinguish mathematical guarantees, empirical checks, Monte Carlo uncertainty and lack of detected undercoverage. Validation scopes and adverse calibration results remain explicit.
- Historical analyses, source-data records and previous-release evidence retain their original version labels. Fresh verification results must be taken from the matching external receipts.

## 1.0.1 (2026-11-02; not published separately, included in 1.0.2)

Corrections and input handling; the statistical methods and their defaults are unchanged.

- The optional likelihood analysis fits the maximum-likelihood distribution on the closed simplex, so categories may take zero probability, and refines it by pairwise transfers of probability mass. Profile-likelihood interval ends are located by bisection of the likelihood-ratio cutoff instead of being read from the evaluation grid; separate parts of a profile set are reported as components. For the ampicillin example the share above 0.25 mg/L is 28.21% with profile interval 6.448–56.400%.
- Sample-bound certificates take the dual bound and gap from the solver, rescale constraint rows before solving, check integrality before rounding and check every equality exactly at the returned count table.
- The request planners accept a count written as a cumulative range from the lowest or to the highest category, as the Windows form writes it, in the same way as the equivalent threshold count.
- The Windows form refuses input files that request analyses it cannot run, instead of running a reduced analysis. It accepts whole numbers written as 20.0 or 2e1 and opens files that write the unit as µg/mL.
- Reporting certificates written by 1.0.0 and by 1.0.1 are both accepted by the Windows form and by examples/received_report/verify.py.
- A CSV input with a header but no cohorts is refused.
- The checksum file of a report is included in downloads from the Windows application.
- Results of version 1.0.0 can be continued with Add a count; the earlier files are identified by their SHA-256 hashes in the new result.
- The evaluation folder holds the inputs, scripts and results of every comparison reported in the article, including the protocol (evaluation/PROTOCOL.md) and results of the confirmation on independent surveillance data, with job scripts that run them on a cluster node.
- New tests state the exact results of thirteen critical functions; evaluation/mutation.sbatch runs mutation testing of these functions. Continuous integration also runs Ruff, mypy and three browser checks of the application, among them the worked example.
- The test workflow no longer publishes; publication requires an explicit release run. The licence file is named LICENSE.txt.

## 1.0.0 (2026-10-11)

First public release.
