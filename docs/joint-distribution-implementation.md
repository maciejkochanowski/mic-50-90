# Joint distribution implementation, MIC-50-90 1.0.0

The workflow uses the exact multinomial sampling law for joint minimum-p-value
inference. “Exact” describes the sampling law; endpoint precision is separate.

- Directed probability bounds and conservative parameter boxes retain unresolved possibilities when the time limit is reached.
- Sample grouping and population grouping have separate precision criteria.
- Same-sample updates retain valid earlier bounds while adding truthful counts.
- HTML, CSV and JSON expose the same scientific results at different levels of detail.

Finite reference checks are in `tests/test_joint_independent.py`; stopping and
safe-bound checks are in `tests/test_population_budget.py` and
`tests/test_hunter_audit_safety.py`.
The [mathematical specification](joint-distribution-method.md) states the
guarantee and numerical requirements. Use
[REPRODUCING_RESULTS.md](REPRODUCING_RESULTS.md) for executable checks and environments.
