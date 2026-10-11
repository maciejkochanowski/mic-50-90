# Mathematical components and software checks

MIC-50-90 connects incomplete reports to compatible sample counts, simultaneous population bounds and requests for further counts. The following map identifies the mathematical work implemented in the public software. The journal manuscript and supplementary appendices are maintained separately.

| Question | Implemented construction | Explanation and checks |
|---|---|---|
| Which population shares are compatible with incomplete category counts? | Fixed simultaneous all-range inference | range-population-method.md; tests/test_range_population.py; independent finite-domain checks |
| Can a small selected family attain the same population endpoints? | Count-row extrema and the conditional population row-lift theorem | population-row-lift.md; formal/P6Core.lean; tests/test_range_witnesses.py and test_probability_certificates.py |
| Which counts should be requested or transmitted? | Costed question plans and sufficient disclosure | DECISION_PLANNING.md, ACQUIRING_COUNTS.md, SUFFICIENT_REPORTING.md; independent question-tree and subset oracles |
| How can another truthful count update the same analysis? | Retention of the original calibrated event and previous population bounds | RETURNED_COUNTS.md, distribution-user-guide.md; tests/test_count_updates.py and test_joint_population.py |

K in the row-lift theorem denotes recorded MIC categories, not isolates. The theorem uses a nonempty closed integer difference system and a stated endpoint-increment condition. The runtime concavity test is a sufficient check. Formal algebra, numerical certificates, statistical assumptions and tests have distinct roles; none substitutes for the others.

Exact binomial inversion, simultaneous inference, difference constraints, ordered search and set intersection are established foundations. The linked documentation states the implemented construction and its conditions. The ordinary software guides explain the inputs, outputs and practical tasks without requiring the separately maintained article documents.
