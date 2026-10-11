# MIC-50-90 1.0.0 release contents

The local release provides the following supported workflows:

- Input from MIC summaries, panel definitions, exact or bounded counts, and explicitly rounded percentages.
- Sharp compatible sample-count ranges, including reporting variants and interval-recorded MIC measurements.
- Separate iid population inference and calibrated study-unit inference, with stated assumptions and numerical status.
- Certified selected-table calculations for eligible population endpoints, backed by the stated proofs and Lean 4 algebraic formalization.
- Cost-aware additional-count planning, sufficient laboratory reporting, and recipient verification.
- Saved same-sample updates that preserve previously confirmed information.
- An English local Windows application and installed CLI, with explanatory HTML, CSV/JSON records and SVG/PNG/PDF exports.
- Software usage guides, example inputs, test suites, formal proof sources and build instructions.

The supplied manifest identifies this exact 1.0.0 software package. Consult
`PACKAGE_STATUS.json` for the release location and the Actions verification assets
for execution evidence. Statistical guarantees, numerical precision, formalized
algebra and engineering checks have separate scopes.

## Final 1.0.0 build (11 October 2026)

- The maximum-entropy and KL-projection scenarios are computed by a log-barrier Newton method started from a strictly
  feasible point, and a result is returned only when its Frank-Wolfe optimality gap is below 1e-9. The previous local method
  could stop at a vertex of the compatible shares or report an unavailable scenario.
- Every command option has help text, malformed panel definitions and non-finite planning limits are reported as
  input messages, and an incompatible report is refused without solver status text.
