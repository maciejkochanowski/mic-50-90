# Joint range inference and numerical stopping

The internal module `mic_50_90._hunter` computes conservative projections of a
fixed confidence region for an incomplete MIC report. Select **Joint refinement
across MIC ranges** in the population settings of the form, or pass
`--population-method range-hunter` to `distribution`. The package version is 1.0.0.
This is an optional construction; selecting it does not establish that it will
give narrower intervals than another method.

## Statistical object

Let H have a multinomial distribution with sample size n and category
probabilities p on a fixed, ordered panel. This requires independent sampling
from the same population. A report defines a set of compatible integer
histograms. At least one declared reporting interpretation must contain the
actual histogram. Censored categories are retained as whole categories.

The fixed family consists of contiguous category ranges, with duplicate
prefix/complement comparisons removed. For a range with probability q and
count x, use the doubled inclusive binomial score

    b(x,q) = min(1, 2 P[Bin(n,q) <= x], 2 P[Bin(n,q) >= x]).

The complete-data statistic is the minimum score over this fixed family. The
report statistic is its maximum over compatible histograms. Counts and
alternative reporting conventions are linked within each histogram; separate
rangewise choices cannot replace that joint maximization.

For a candidate probability law, the null distribution of the minimum score
is bounded using event marginals, pairwise intersections and a maximum-weight
spanning tree. When the event family has at most 12 members, a certified moment
linear program supplies another upper bound. Taking the minimum over higher
attainable score levels makes this bound nondecreasing in the observed score.
Only certificates, rather than an unverified numerical optimizer result, are
used to exclude candidates or accept inner witnesses.

The spanning-tree inequality is established theory: Hunter, *An upper bound
for the probability of a union*, Journal of Applied Probability 13 (1976),
597–603, [doi:10.2307/3212481](https://doi.org/10.2307/3212481).

Write G for the exact null CDF of the minimum score and U for that monotone
upper bound. For every score t, G(t) <= U(t). The discrete probability integral
transform gives P[G(T) < alpha] <= alpha; therefore rejection when
U(T) < alpha has size at most alpha. Maximizing T over a report that contains
the actual histogram can only increase U. Inverting these tests consequently
gives simultaneous coverage at least 1-alpha for the full probability vector.
An outer approximation to that region preserves the guarantee.

These arguments use established probability inequalities, test inversion and
integer difference constraints. They do not establish a new general coverage
theorem, optimality, or superiority over other confidence constructions.

## Width goals and numerical endpoint precision

For a requested MIC range, let L and U be its outer probability bounds. Inner
witnesses certify an upper bound A on the true minimum and a lower bound B on
the true maximum within the same confidence region. Thus its exact projection
width lies between B-A and U-L. In particular:

* If U-L <= w, the requested width is attained.
* If B-A > w, the width cannot be attained by further endpoint refinement of
  this same report and confidence construction.
* Otherwise, the width assessment remains unresolved numerically.

Equality belongs to the attained case. The implementation compares exact
rational bounds before rounding for display. This assessment does not change
the confidence level, select a new method from its output, or treat numerical
uncertainty as sampling uncertainty. It remains valid when computation stops
as soon as the assessment is determined, since the outer-cover invariant and
inner-witness certificates hold at every stopping point.

`width_target_pp` applies to every contiguous range returned by the internal
projector. `tolerance_pp` instead controls the discrepancy between certified
inner and outer endpoint bounds. Meeting one target does not imply meeting
the other. A width failure for the current incomplete report does not prove
that additional counts, complete reporting or more isolates would be useless.

## Using the result

Population analysis requires an explicit acknowledgement of independent
sampling from the same population. Set the desired interval width using
`--population-precision-pp`, for example `10` for ten percentage points. The
separate `--population-tolerance-pp` controls numerical endpoint refinement.
It is not the requested biological precision and need not be reached to
confirm a width target.

```text
mic-50-90 distribution input.json --population-method range-hunter --population-precision-pp 10 --population-time-limit 120 --output-dir results
```

The report displays the confidence level, the intervals and the confirmed
grouping of MIC categories. When the width target is already confirmed, the
calculation may stop before the numerical endpoint tolerance is reached.
When an attained inner bound proves that a range is too wide, finer numerical
calculation alone cannot resolve that range for the current report. Additional
counts can still help. Combining categories changes reporting detail; it does
not improve the precision of the original category estimates.

At the time limit, valid outer bounds remain available. An unresolved width
assessment means that the calculation has not established whether the target
can be attained. It must not be read as a proof that more isolates are needed.
The time budget applies to optional refinement; mandatory input checks and the
initial valid envelope are also reported in execution time.

Use **Add a count** to update the same sample. The method, confidence level and
original constraints must be preserved. Saved outer bounds are retained, and
width assessments are recalculated for the updated result.

## Implementation

The runtime uses static package-relative imports. It does not load research
scripts, modify Python search paths, or execute source replacements. Integer
and rational operations certify count feasibility, score comparisons and
endpoint direction. Floating-point probability recurrences require ordinary
IEEE-754 arithmetic with gradual underflow and directed enclosure operations.

The internal API accepts the same contiguous-count constraints as the original
kernel. Its output includes conservative intervals, available inner witnesses,
the numerical endpoint gap, the confidence level and optional width statuses.
An interrupted search retains its unprocessed outer cells. It never substitutes
the midpoint of an unresolved interval for a certified endpoint.

Several simultaneous binomial-score ties can be represented using shared
algebraic roots. Exact tail inequalities enclose the roots, and affine
coordinates describe one normalized population law. Integer dynamic
programming gives a lower bound for selected null-event unions; small exact
enumerations may strengthen that bound. Only independently certifiable laws
can improve inner endpoint bounds. Searching these laws does not assume a
population distribution shape. Repeated certificates that add no endpoint
information are not retained.

When a compatible integer count remains uncertain, the search can split its
range into two disjoint integer intervals. Their union equals the original
range. The parent remains available until all replacements have been built,
so an interrupted split cannot remove admissible possibilities.

The CLI, form and HTML report use the shared distribution adapter. Optional
refinement failures retain the selected construction's own valid envelope;
they do not silently substitute a different method. Timing for
a membership check or width assessment is not the timing of full endpoint
inversion. Small control cases do not justify reducing biological sample size.
