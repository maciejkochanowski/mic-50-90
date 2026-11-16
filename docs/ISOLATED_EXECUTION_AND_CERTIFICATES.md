# Isolated distribution execution and arithmetic certificates

These changes are a checked development revision of MIC-50-90 1.0.1. The method
default remains `bonferroni`. A process-control option does not add a statistical
guarantee or make iid inference valid for dependent observations.

## Library and command line

```python
from mic_50_90.distribution_workflow import analyse_distribution
result = analyse_distribution(input_dict, solver_execution="isolated", solver_timeout=300)
```

```sh
mic-50-90 distribution input.json --output-dir output \
  --solver-execution isolated --solver-timeout 300
```

The new keyword arguments are optional. `solver_execution="in-process"` preserves
the original behavior and output fields. Isolated execution launches a fresh
interpreter for the complete analysis and its validation. It never reconfigures
or resets a native scheduler previously initialized by the calling application.
Both HiGHS and numerical libraries use one thread inside that worker. The same
control covers empirical LP/MILP, calibration and advanced population methods.

The hard wall limit includes interpreter startup, imports and the full cohort
analysis. It is separate from the existing optional-refinement budget. A timeout
raises `TimeoutError`; an invalid input preserves its validation exception; an
abnormal process exit raises `RuntimeError`. The CLI records a refused cohort and
supports `--fail-on-refusal`. No worker failure is a valid confidence interval.

Isolated inputs must be JSON-serializable analysis dictionaries. Successful
results retain the existing statistical fields and add `execution`: mode, worker
PID, requested solver threads, observed native threads where available, wall
limit, total elapsed time and captured warning counts. SciPy may warn that the
HiGHS `threads` option is passed through; this warning is retained. Isolated CLI
configuration records the two options. Existing saved-result loading is unchanged.

The parent reaps a timed-out or interrupted worker. On Linux a parent-death signal
also terminates a worker if the controller is killed abruptly. That additional
Linux protection is not a promise for other operating systems. Public execution
does not impose the research campaigns' CPU/address-space quotas; campaign
wrappers continue to enforce their separately frozen resource limits.

## Finite P6 shape certificate

The accelerated generator uses approximate beta inverses only as proposals.
Directed arithmetic bounds each binomial tail; the receiver independently checks
every endpoint inequality and exact rational second difference. The emitted
arithmetic certificate uses schema `mic5090-upper-shape-certificate/1` and contains
the exact n, cutoff, endpoint rows and numerical policy. This is a finite
arithmetic certificate, not a formal proof of Python or a theorem for every n.

The integrated shape check reserves45percent of the remaining caller budget for
generation and90percent for generation plus receiver verification. A failed
attempt retains its reason and allows the old method to use the remainder.
Unresolved comparisons never establish concavity. Large-n shape checks follow
the inexpensive pointwise witnesses, avoiding unnecessary endpoint tables.

Only a receiver-verified certificate can activate the accelerated row-lift
argument. Shape alone does not make unavailable inward endpoints available;
the refinement also checks their existence before claiming attainment. The
successful result includes `arithmetic_certificate` for a recipient to verify.

The standalone receiver is the standard-library-only `_shape_receiver.py` file.
Copy it alongside an extracted arithmetic certificate and run:

```sh
python -I -S _shape_receiver.py certificate.json --seconds 180 --output verification.json
```

Acceptance requires `status="certified"`; process exit alone is insufficient.
The original versioned research sources and all slower/unsuccessful measurements
remain in `strengthening/shape_certificate_acceleration`.
