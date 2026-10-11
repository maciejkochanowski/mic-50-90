# Simultaneous population bounds for MIC ranges

MIC-50-90 1.0.0 offers `range-calibrated` as an explicit choice for population
inference. It uses counts in all contiguous ranges of a fixed ordered panel.
The default remains `bonferroni`. The method must be chosen independently of
which result happens to be narrower. It is not an automatic selection among
several confidence regions.

## User task and interpretation

With independent, identically distributed isolates, this calculation gives
simultaneous bounds for the population shares in the recorded MIC categories
and their contiguous unions. A censored category remains one category. The
calculation does not locate concentrations within it. A report may contain
quantiles, exact or interval counts, and several explicitly declared reporting
conventions. It must contain at least one truthful interpretation.

In the Windows form, select **Simultaneous bounds for all MIC ranges** under
the optional population calculation. In the CLI:

```text
mic-50-90 distribution input.json --population-method range-calibrated --output-dir output
```

`iid: true` is required for this layer. It is an assumption about sampling,
not a correction for clustering or biased selection. Sample results remain
separate. `--population-precision-pp` sets a desired interval width;
`--population-tolerance-pp` sets a numerical endpoint target. A safe interval
can answer a question or meet a width target without meeting every numerical
endpoint target. Results must not be discarded solely because the latter
target was not reached.

Full recorded category counts give a particularly simple computation. The
accepted probabilities satisfy a system of differences between cumulative
probabilities. Its closure gives all the requested bounds. With incomplete
counts the program first returns an outer region containing every compatible
histogram's confidence region. An optional search can sharpen the projections.
If that search is interrupted, it keeps the full report envelope. The reported
endpoint gap separates safe outer endpoints from values certified inside the
same confidence construction; it is not statistical uncertainty.

## Fixed simultaneous construction

Let `n >= 1`, `K >= 2`, `alpha` be the error probability, and `p` a categorical
population law. For each range `(a,b)` with `0 <= a < b < K`, let `x` be its
count and `q` its population mass. These `m=K(K-1)/2` ranges represent every
nonconstant contiguous range up to complements: a suffix has the same test
as its complementary prefix. Define

`b(x,q) = min(1, 2 P_q[X <= x], 2 P_q[X >= x])`, `X ~ Binomial(n,q)`.

The score uses inclusive tails. For a complete histogram `h`, retain `p` when
every range score is at least a fixed cutoff `c`. Reject strictly below `c`.
For an incomplete report `R`, take the union of these regions over all
compatible histograms `H(R)` and all truthful candidate conventions. This is
a uniform-score confidence construction. It is distinct from an exactly
evaluated multinomial LR region or an inverted Hunter probability bound.

### Calibration bound

For `t<1`, each range rejection event has a lower and an upper count tail;
each has probability at most `t/2`. Both nonempty tails can occur only when

`a_t <= q <= 1-a_t`, where `a_t=1-(t/2)^(1/n)`.

View the `K` cumulative coordinates as ordered vertices; connect two vertices
when their difference is in this interval. If `a_t > 1/(r+1)`, an `(r+1)`
vertex clique is impossible: its `r` successive gaps have sum at least
`r*a_t`, but its extreme vertices must be at distance at most `1-a_t`.
By the classical extremal graph bound, there are at most `E_r(K)` such edges,
where `E_r(K)` is the edge count of the balanced complete `r`-partite graph.
Therefore the sum of rejection probabilities is at most

`(m+E_r(K))*t/2`, whenever `t < 2*(r/(r+1))^n`.

The ordinary union bound `m*t` also holds. Set

`c = min(1, max(alpha/m, max_r min(2*alpha/(m+E_r(K)), 2*(r/(r+1))^n)))`.

For every `t<c`, one of these bounds is no larger than `alpha`. Passing to
the limit from below proves `P_p[min_range b(X_range,p_range)<c] <= alpha`.
This also handles a cutoff exactly on a clique threshold and `c=1`; the
rejection rule remains strict. No large-sample approximation or assumption
about the shape of `p` enters this argument.

Consequently the complete-data region covers the entire population law with
probability at least `1-alpha`. A truthful report includes the observed
histogram, so its union region inherits that coverage. Adding truthful counts
from these same isolates reduces `H(R)` and nests the statistical region,
provided the panel, denominator, confidence level and cutoff remain fixed.
This argument is simultaneous over truthful refinements of the report; it
does not count new disclosures as new independent samples.

The binomial tail method, union bounds, extremal graph theorem, shortest-path
closure and union construction are established mathematical principles. The
specific calibration bound and its implementation are documented here; this
document does not establish priority over all previous literature.

## Projection and numerical certificates

For fixed `h`, each score constraint is a closed equal-tailed binomial interval
for `F[b]-F[a]`. Probability nonnegativity and `F[K]-F[0]=1` complete a system
of difference constraints. Exact rational shortest-path closure gives sharp
projections of that polytope. Directed outer binomial endpoints yield an outer
polytope; separately verified inward endpoints yield an inner polytope. A
projection endpoint of the inner polytope certifies attainable mass in the
statistical region; a collection of such endpoints need not be one law.

For each incomplete reporting variant, integer difference-constraint closure
gives exact minimum and maximum range counts. Binomial interval endpoints are
monotone in the count, so their extreme endpoints contain every compatible
complete-data region. Closing these constraints is safe, although it need not
give the sharp projection of the union. Variants are closed separately and
then unioned. They are never simultaneously imposed as if all conventions
were known to hold.

### Direct certificates from count bounds

Let D be the closed integer difference matrix for one reporting interpretation,
so S_b-S_a<=D[a,b], S_0=0 and S_K=n. For each anchor v in 0,...,K, define
S_j^(v)=D[v,j]-D[v,0]. The triangle inequality gives
S_b^(v)-S_a^(v)<=D[a,b]. The two total-count constraints give S_K^(v)=n,
and nonnegative-category constraints make successive differences nonnegative.
Thus these potentials define K+1 compatible integer histograms. Anchor a
attains the upper count bound D[a,b]; anchor b attains the lower bound
-D[b,a]. Every contiguous count extremum has a witness in this family.

The count result alone does not establish population endpoint attainment.
The program first checks whether the upper exact binomial endpoint sequence
has certified discrete concavity at this sample size and fixed cutoff. Under
this sufficient condition, Proposition P6 proves that the same count-row
family attains every contiguous population endpoint. Anchors 0 and K give
the same histogram, so at most K distinct histograms are needed. This is a
statement about projection endpoints, not equality of the complete regions.
The proof and directed finite certificate are in [population-row-lift.md](population-row-lift.md).

When that certificate is unavailable, the program separately checks inner
probability polytopes of compatible histograms and selected inner probability
vertices of the report envelope. A successful integer compatibility check
certifies an accepted histogram. A failed point check does not reject the
whole face. Remaining integer count space is partitioned into exhaustive,
disjoint cells. Every pending cell retains a valid outer envelope. A parent
is replaced only after both children are accounted for. Interruption keeps
the union of all unresolved outer possibilities and established inner
certificates. The confidence construction and cutoff remain unchanged.

Saved updates preserve verified bounds from the same method and invalidate
inner certificates that conflict with the updated information. Bounds from
different confidence constructions must not be intersected merely to obtain
a narrower answer.

## Validation scope

`tests/test_range_population.py` checks exact rational small-sample coverage,
complete histogram projections against independent linear programming,
incomplete-report containment and union projections, multiple conventions,
same-sample updates, contradictory counts, extreme confidence, CLI exports,
the desktop worker, and population precision planning. These are mathematical
and software checks. They do not establish empirical superiority in AMR data,
independent usability validation, or a general recommendation for fewer
isolates. The method can be evaluated as an explicit option without declaring
these broader claims established.
