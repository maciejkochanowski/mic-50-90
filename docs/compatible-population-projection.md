# Compatible-prefix population projections

This implementation improvement in MIC-50-90 1.0.0 preserves dependence
between compatible empirical prefix counts when projecting the existing
Bonferroni Clopper–Pearson construction. It does not introduce a new general
Clopper–Pearson theory or establish superiority over direct intervals for all
contiguous ranges. The recorded MIC categories, denominator, confidence level
and reporting interpretations remain fixed.

## Region and projection

Let `K` be the number of ordered recorded categories, `n` the number of
independent identically distributed observations, and `H` the union of the
compatible integer histograms from the declared reporting interpretations.
For `h` in `H`, write `S_j(h) = sum(h_i, i < j)`, with `S_0=0`, `S_K=n`.
For every interior cut use the same two-sided Clopper–Pearson endpoints
`L(s), U(s)` at error probability `alpha/(K-1)`. Both are nondecreasing in `s`.
The population CDF has `F_0=0`, `F_K=1`. The region is

```
B(H) = union over h in H of
       {ordered F : L(S_j(h)) <= F_j <= U(S_j(h)), 0 < j < K}.
```

For a contiguous range `(a,b)`, its population share is `F_b-F_a`. At a
compatible pair of counts `(s,t)=(S_a,S_b)`, its exact extrema are

```
minimum = max(0, L_b(t)-U_a(s))
maximum = U_b(t)-L_a(s),
```

where the endpoints at cuts `0` and `K` are the fixed probabilities `0` and
`1`, rather than binomial intervals for counts `0` and `n`. Minimizing and
maximizing these expressions over compatible pairs gives the projections of
`B(H)`. Extrema from separate reporting interpretations are united; a count
from one interpretation cannot be paired with a count from another.

### Integer extension of a pair

For one reporting interpretation, all empirical constraints are integral
contiguous-category constraints. In prefix coordinates they are difference
inequalities. Let `D[u,v]` be their shortest-path closure, with the convention
`S_v-S_u <= D[u,v]`. Nonnegative category counts and total `n` are included.
The feasible pairs are exactly

```
-D[a,0] <= s <= D[0,a]
max(-D[b,0], s-D[b,a]) <= t <= min(D[0,b], s+D[a,b]).
```

Necessity follows by taking the corresponding inequalities in the closure.
For sufficiency, fix the values at cuts `R={0,a,b}` and suppose all their
pairwise difference inequalities hold. Define
`S_j = min(r in R) {S_r + D[r,j]}`. The triangle inequality for `D` ensures
every original difference inequality. At a fixed cut `r`, the self term
attains `S_r`, and the fixed-pair inequalities prevent any smaller value.
All values are integral. The total and order constraints imply `S_K=n` and
nonnegative integral differences, hence an extending compatible histogram.
Repeated fixed cuts are interpreted as one identical fixed value.

For each feasible `s`, monotonicity of `L` and `U` implies that the smallest
feasible `t` minimizes the lower expression, and the largest feasible `t`
maximizes the upper expression. Only `s` is scanned; histograms and all
two-dimensional pairs are not enumerated in production.

### Ordered population extension

For a fixed histogram, the sequences of CP lower and upper endpoints are
nondecreasing. For two ordered coordinate values inside their respective
intervals, every intermediate coordinate can be chosen inside its own
interval and between the two fixed values. One construction is the running
maximum of lower endpoints and the most recent fixed value, until the next
fixed value is reached. Monotonic endpoint sequences ensure no upper bound
or future fixed value is exceeded. The same argument applies before and
after the fixed coordinates.

Consequently the usual two-interval difference extrema written above are
attained by an ordered population CDF, rather than merely bounds for an
unconstrained two-coordinate relaxation. Combined with integer extension,
this proves the finite compatible-pair projection formulas.

## Coverage, containment and updates

For the actual histogram, the simultaneous CP event has probability at least
`1-alpha` by the union bound on the `K-1` interior cuts. If that histogram is
compatible with the truthful report, its CP box is included in `B(H)`.
Thus projection retains simultaneous coverage under the stated iid and
fixed-panel assumptions. This argument does not infer iid sampling from a
large sample size and does not turn repeated specimens into independent units.

The existing joint-minP region is contained in `B(H)`: writing `t` for the
maximum compatible minimum binomial score, the joint tail probability is at
most `(K-1)t`. A joint accepted point therefore has `t >= alpha/(K-1)`, so a
compatible histogram exists for which every binomial score meets this
threshold, placing the point inside that histogram's CP box. These
projections can therefore tighten the outer cover of the **same** joint-minP
region. This is not an intersection of confidence regions from different
tests. CP inner witnesses are never reused as joint-minP acceptance witnesses.

Adding truthful original-sample constraints, while retaining the original
constraints and reporting interpretations, shrinks `H` and hence `B(H)`.
The existing update contract still checks denominator, panel, method,
confidence level and retained constraints. Saved outer bounds may be retained
for the nested region; numerical inner witnesses are computed anew.

## Numerical and computational contract

SciPy supplies starting locations only. `_cp_outer` and `_cp_inner` verify
the CP locations with directed Decimal binomial tails against the exact
binary64 confidence level. Subtraction is directed outwards for coverage
bounds and inwards for attained-value certificates. An inner certificate is
computed from the same compatible count pair that gave the candidate outer
extremum. Overlapping inward intervals admit a common coordinate; otherwise
the inward endpoints themselves attain the difference. Both cases extend to
an ordered population CDF as proved above.

The reported `endpoint_gap_pp` measures the remaining outer-to-inner bracket.
If an inner certificate is missing or the gap exceeds the requested
tolerance, Bonferroni endpoint precision is marked unresolved while valid
outer bounds remain available. Joint refinement keeps its separate accepted
witnesses, time-limit status and conservative unfinished cover.

With `V` reporting variants the worst-case projection work is
`O(V K^3 + V K^2 n)`, plus certified CP endpoint computation. Endpoint
certificates are cached within the calculation. Boundary pairs are examined
first; a variant scan stops only when both independent marginal outer limits
are attained. Thus many prefix-only reports and complete histograms require
only a few certified endpoint evaluations. This shortcut gives the same
projection, without data-dependent switching between confidence methods.

## Independent verification

`tests/test_compatible_population_projection.py` uses an independent oracle:
enumerate integer histograms, filter them using the original constraint
matrix, and solve each ordered population box with general-purpose linear
programming. The oracle does not call the production closure, feasible-pair
formula or projection helper. SciPy beta quantiles are acceptable here as an
independent numerical comparison, not as production coverage certificates.
The directed CP certificates also retain the existing exact-rational tail
tests in `tests/test_joint_certificates.py`.

Controls include incompatible marginal extrema, a union of disconnected
reporting variants, zero category counts, `n=1` and `n=2`, censored recorded
categories, truthful count updates, and a zero optional-refinement budget.
For a development case with `n=50`, `K=5`, `S_1` in `[10,20]`,
`S_2-S_1=1`, `S_3` in `[35,40]`, `S_4` in `[45,49]`, the upper bound for
`F_2-F_1` changes from about `0.52361662256549` to `0.37180860249702`.
This illustrates an attainable improvement; it is not a frozen superiority
benchmark or a claim of strict improvement for every report.
