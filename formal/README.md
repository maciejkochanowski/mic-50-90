# Machine-checked algebra for the population endpoint construction

This directory checks the algebraic core of P6 with Lean 4.29.1 and mathlib commit `5e932f97dd25535344f80f9dd8da3aab83df0fe6`. It is supporting evidence for MIC-50-90 1.0.0, not a new runtime dependency.

From this directory, with Lean installed, run:

```text
lake update
lake exe cache get Mathlib/Tactic.lean Mathlib/Data/Real/Basic.lean
lake env lean P6Core.lean
```

The file contains 29 theorem declarations and prints the axiom dependencies of every theorem. None may depend on `sorryAx`. There are no additional axioms or admitted proof steps in this file. Standard Lean foundations (`propext`, `Classical.choice`, `Quot.sound`) remain part of the trusted proof system. The audit also rejects native-evaluation or custom-axiom dependencies outside this allowlist. This follows Lean's [proof-validation guidance](https://lean-lang.org/doc/reference/latest/ValidatingProofs/).

For a laboratory reader, the checked step has a direct meaning: the selected table of isolate counts can be converted into a probability distribution that satisfies every analysed MIC-range bound at the same time. The proof also checks how the required lower or upper endpoint is attained, including a range ending at the last category.

## What is checked

| Mathematical step | Lean declarations | Python connection |
|---|---|---|
| Discrete concavity bounds increments | decreasing_slopes, decreasing_increments, increment_bounds, lower_increment_bounds, crossing_anchor_bounds | Precondition used by the P6 endpoint argument |
| Directed endpoint brackets certify concavity | bracket_certificate | range_certificates.binomial_shape_certificate |
| Rows of a closed difference matrix are feasible and attain count bounds | count_row_feasible, count_row_attains_upper, count_row_attains_lower | range_witnesses selected histograms |
| The terminal count row duplicates the initial row | terminal_row_duplicate | At most K distinct count rows for K categories |
| The anchored probability construction meets all range bands and is a probability vector | anchored_range_bounds, anchored_total, anchored_nonnegative | Written construction in ../docs/population-row-lift.md |
| The construction attains the anchor bounds | anchored_upper_attainment, anchored_lower_attainment | Population projection endpoint argument |
| K indexed choices give at most K distinct tables | selected_family_size | Cardinality step; this lemma alone is not the selection theorem |
| Bounds together with attaining witnesses certify a projection | projection_certificate | Conservative outer bounds and attainable endpoints |
| Concavity implies a weaker finite increment condition | concavity_implies_increment_admissible | The implemented concavity test is sufficient for the extended algebraic statement |
| The weaker condition gives complementary and crossing-range bounds | lower_increment_bounds_of_admissible, crossing_bounds_of_admissible, endpoint_order_of_admissible | Checks ranges on one side of an anchor and ranges crossing it |
| All range bands hold under the weaker condition | anchored_range_bounds_of_admissible | Generalized probability construction |
| Normalized anchored values belong to the complete-data population region | normalized_anchor_member, normalized_anchor_member_of_concavity | Assembles total probability, nonnegative category probabilities and all range bands |
| Initial anchor attains a proper range ending at K | normalized_terminal_lower_attainment | Boundary case in the population endpoint argument |
| The weaker condition is strictly weaker than concavity | nonconcave_example_admissible, nonconcave_example_endpoints, nonconcave_example_fails_concavity | Exact rational example; a statement about abstract endpoint sequences |

The file uses an abstract real-valued endpoint sequence U and explicit hypotheses. `Lower n U d` means 1-U(n-d). `IncrementAdmissible` states that each increment of length d lies between L(d) and U(d). Discrete concavity implies this condition, and an exact rational sequence proves that the converse fails. The Python implementation continues to use its existing concavity certificate.

`CompleteRegion` is stated in cumulative coordinates: its first value is zero, its final value is one, adjacent increments are nonnegative, and every contiguous range meets its band. `normalized_anchor_member` proves membership in this region, rather than assuming membership as a premise. The correspondence between U and the exact binomial confidence endpoints is stated in ../docs/population-row-lift.md and checked by independent numerical evidence. Count rows and probability constructions are connected in the written P6 proof; the complete translation from an arbitrary MIC report and Python objects into these formal objects is outside this formalization.

## What is not checked by Lean

Lean does not verify the Python program, the numerical enclosure implementation, the statistical coverage proof, source-data transcription, biological interpretation or user interface. Passing these algebraic proofs does not establish novelty. Property tests, direct enumeration, numerical certificates, example replay and the written statistical proofs address different parts of that evidence.

MathForm 8B is not used. Such a model could help translate a proposed statement into Lean, but its output would still require checking that the formal statement matches the intended theorem and that the Lean kernel accepts the proof. The direct formalization here avoids an unnecessary model dependency.

The portable commands above recompile the supplied formal source using its pinned dependencies. Inspect every printed axiom dependency: no theorem may depend on sorryAx or an added unproved axiom. A successful process alone is not sufficient evidence if such dependencies are present.
