# Joint population inference from incomplete MIC reports

MIC-50-90 1.0.0. Mathematical specification and implementation requirements.

This method estimates the distribution of **recorded MIC categories in one
population**, using a sample whose report may omit category counts. It does not
estimate unobserved concentrations within censored categories. Its sampling
guarantee requires independent, identically distributed isolates. This is a
different guarantee from prediction for a new study unit using calibration.

## 1. Data and estimand

Fix ordered categories and all tested category boundaries before inspecting the
sample. Write `K` for the category count and `m = K - 1` for the internal
boundaries. The population cumulative probabilities are

\[
0=q_0\le q_1\le\cdots\le q_m\le q_K=1.
\]

Let `h` be a nonnegative integer histogram with total `n`, and let
`s_j(h) = h_1 + ... + h_j`. The report defines a finite, nonempty set `H` of
compatible histograms. This set retains quantile ranks, observed extrema,
interval counts, exact counts, rounded percentages and censoring conventions.
An unknown reporting convention gives a **union** of its compatible sets;
constraints known to hold simultaneously give their intersection. An observed
sample minimum or maximum is not a restriction on population support.

The coverage condition is that the realised histogram belongs to `H`. This
condition may hold for a sample-dependent reporting rule: the argument below
does not assume that omitted counts are missing at random. It does not,
however, establish coverage conditional on the report or repair biased sampling
of isolates or selective publication of studies.

## 2. Exact test and incomplete reports

For a binomial random variable `B` with parameters `(n, q_j)`, define the
equal-tailed value

\[
b_j(s;q_j)=\min\{1,2\min[P(B\le s),P(B\ge s)]\}.
\]

Use both inclusive tails, including when `q_j` is zero or one. Let

\[
T_q(h)=\min_j b_j(s_j(h);q_j),\qquad
G_q(t)=P_q\{T_q(X)\le t\},
\]

where `X` is a multinomial histogram generated under the candidate population
distribution. The complete-data value is `G_q(T_q(h))`. All ties belong to the
probability event; replacing `<=` by `<` can invalidate calibration.

For an incomplete report, compute

\[
t_H(q)=\max_{h\in H}T_q(h),\qquad
p_H(q)=G_q(t_H(q)).
\]

The confidence region at confidence level `1 - alpha` is

\[
C(H)=\{q:p_H(q)\ge\alpha\}.
\]

Closed acceptance is chosen deliberately. Rejection is `p_H(q) < alpha`.
Finite precision must never change this to a more aggressive decision.

### Proposition 1: finite-sample coverage

For any random variable `T` with cumulative distribution function `G`,
`P(G(T) <= a) <= a`. Thus `G_q(T_q(X))` is a valid, possibly conservative,
value under `q`. Because `X` belongs to `H`,
`t_H(q) >= T_q(X)` and `p_H(q) >= G_q(T_q(X))`. Consequently,

\[
P_q\{q\in C(H)\}\ge 1-\alpha.
\]

This is simultaneous coverage of the population vector at the fixed category
boundaries. Any category probability or contiguous-interval probability
projected from the same region inherits that event. It is not exact knowledge
of an individual isolate's MIC, and it does not assert that every collection
of values chosen from the projected intervals forms a compatible distribution.

### Proposition 2: comparison with Bonferroni

Every marginal binomial value is super-uniform, so the union bound gives
`G_q(t) <= min(1, m*t)`. Hence

\[
C(H)\subseteq B(H),\qquad
B(H)=\bigcup_{h\in H}\{q:b_j(s_j(h);q_j)\ge\alpha/m
\text{ for every }j\}.
\]

For each fixed histogram, the latter inequalities are the equal-tailed
Clopper--Pearson intervals with confidence `1 - alpha/m`, intersected with
monotonicity. The relation proves no larger **exact mathematical regions**
relative to this specified comparator, not uniform superiority over all
simultaneous methods. The union must use the same histogram at all boundaries.
A rectangle formed from separate count extrema can be larger than `B(H)`.

A numerical outer cover of `C(H)` need not itself lie in `B(H)` unless the
implementation enforces that intersection. Initialising the cover within the
coordinate hull of the Bonferroni baseline does ensure that displayed
coordinate intervals never exceed those baseline intervals.

### Proposition 3: truthful updates

If extra information from the same sample gives nonempty `H'` contained in
`H`, then `t_H'(q) <= t_H(q)` for every `q`; therefore `C(H')` is contained in
`C(H)`. If an adaptive sequence of such reports always contains the original
realised histogram, all regions contain the true population on the same
complete-data coverage event. No additional multiplicity penalty is required
for these refinements.

This statement requires fixed sample size, category boundaries, test statistic
and confidence level. It does not cover adding new isolates or selecting a new
family of boundaries after seeing results. An implementation that stops early
must intersect a new outer approximation with the previous saved outer cover
if it promises that successive **computed** outputs never widen. Independently
restarting a time-limited search need not yield nested numerical covers.

## 3. Computing the report value without enumerating histograms

For fixed `q` and a candidate value `t`, the condition `T_q(h) >= t` imposes
one integer interval on every cumulative count. Add these interval rows to the
original report constraints and check whether a compatible integer histogram
exists. Feasibility is monotone in `t`. Searching the sorted, finite set of
binomial values obtains `t_H(q)`.

For canonical interval-count constraints, this is an integer difference
constraint problem in the cumulative counts. Negative-cycle detection is an
exact feasibility test with integer input. Across reporting variants, check
each entire variant and take the largest feasible value. Do not replace their
union by a count box or discard interior interval constraints. Noncanonical
constraints require a correctly certified integer solver or a clearly marked
fallback.

To evaluate `G_q(t)`, each event `b_j(S_j;q_j) > t` is a central integer
interval. Its joint probability is computed by a recursion. Given
`S_(j-1) = r`, the next increment is binomial with parameters

\[
n-r,\quad (q_j-q_{j-1})/(1-q_{j-1}).
\]

Keep only states satisfying the central interval at each boundary. Subtract
the resulting probability from one. Zero-width population categories and
terminal probability one have deterministic transitions and must be handled
explicitly. The recursion is generally quadratic in `n` per boundary, although
central count ranges may reduce its actual work substantially. It must not be
described as uniformly linear time.

## 4. Safe rejection of a whole parameter box

The following construction permits global inversion without treating a dense
grid as proof. Let a box have ordered cumulative endpoints `l_j <= q_j <= u_j`.
For each potential cumulative count `s`, define

\[
\bar b_j(s)=\min\{1,2\min[P_{l_j}(B\le s),P_{u_j}(B\ge s)]\}.
\]

Binomial stochastic ordering gives `b_j(s;q_j) <= bar_b_j(s)` throughout the
box. Use the report feasibility problem to obtain

\[
\bar t=\max_{h\in H}\min_j\bar b_j(s_j(h)).
\]

It follows that `t_H(q) <= bar_t` everywhere in the box. A conservative upper
bound on `bar_t` is sufficient; an underestimated value is unsafe.

If `bar_t >= 1`, set the probability upper bound to one immediately. The
central event is empty because the clipped binomial value cannot exceed one.
The tail inequalities alone do not express this special case at a median atom.

Use independent uniform variables `U_1,...,U_n`, and put
`S(v) = number of U_i <= v`. For each boundary, let `a_j` be the smallest
integer with `P_(u_j)(B <= a_j) > bar_t/2`, and `b_j` the largest integer with
`P_(l_j)(B >= b_j) > bar_t/2`. If no such integer exists, the common acceptance
event below is empty. Define

\[
E=\bigcap_j\{S(l_j)\ge a_j,\ S(u_j)\le b_j\}.
\]

On `E`, for every population vector in the box, both inclusive binomial tails
at every tested boundary exceed `bar_t/2`. Therefore

\[
p_H(q)\le G_q(\bar t)\le 1-P(E)
\quad\text{throughout the box.}
\]

Compute `P(E)` with the same cumulative-count recursion, now at the sorted
unique endpoints among the `l_j` and `u_j`. Merge all constraints at duplicate
endpoints. Inconsistent bounds give probability zero. Endpoint zero has count
zero and endpoint one has count `n` deterministically.

If a verified lower probability bound is `L_E`, discard the entire box only
when `1 - L_E < alpha`. All other boxes remain possible until they are safely
rejected or subdivided. At a singleton box this construction equals the point
test, apart from the deliberate conservative numerical enclosures.

Retain unresolved boxes when a time or state limit is reached. Project all
retained boxes for cumulative or interval probabilities, then intersect with
the valid baseline. A surviving box is not evidence that every point in it is
accepted. Report numerical precision as established only when a proven outer
bound and an accepted witness bracket each reported extremum to the requested
tolerance. Small box sizes alone do not establish that bracket.

Discrete score comparisons can change at parameter values where two attainable
binomial scores are equal. The p-value includes the tied probability mass. A
box straddling such a boundary can remain unresolved even after its width is
smaller than the requested tolerance, while no binary64 point evaluated inside
it supplies an accepted witness. Such boxes are retained as unresolved leaves
instead of being subdivided indefinitely. Search then continues elsewhere,
allowing safe exclusions to improve other reported bounds. The output status
is `precision_unresolved` unless the witness-to-outer-bound test establishes
the requested precision. Retaining a tiny box does not establish that it
contains an accepted parameter vector.

## 5. Numerical certification

Floating-point agreement with enumeration is important validation but is not a
proof that an approximate probability bounds the true probability. A tolerance
added to an ordinary library result is not automatically a certificate.

One conservative implementation uses directed decimal arithmetic. Treat
binary64 grid endpoints as exact rational numbers. Each conditional transition
probability is a rational `a/b`. For `0 < a < b`, compute a downward-rounded
binomial probability using

\[
v_0=((b-a)/b)^N,\qquad
v_{k+1}=v_k\,(N-k)a/((k+1)(b-a)),
\]

with downward rounding for every nonnegative operation. Positive sums and
products of these lower bounds give a lower bound on the central-event
probability. An upper tail can be bounded above by one minus a lower bound for
its complementary tail. Bounds for the statistic and count cutoffs must use
the appropriate direction as well; certifying only the final recursion does
not certify the complete test.

Underflow to a proven lower bound zero is safe but may eliminate all numerical
gain. Overflow, invalid intervals, solver uncertainty and interruption must
preserve the valid baseline. If a probability kernel has only been checked
empirically against high precision, label it as validated numerical evaluation,
not directed-rounding certification.

## 6. Boundary of the scientific contribution

The minP principle, union bounds, Clopper--Pearson intervals, test inversion,
multinomial recursions and treatment of incomplete observations through
compatible completions are established methods. A defensible contribution
must concern their specified combination for MIC reporting, its computational
properties, and demonstrated usefulness. It is not evidence of novelty that
the software passes many tests or that a familiar principle has been proved
again in new notation.

Relevant primary literature:

- Westfall and Young (1989), *p Value Adjustments for Multiple Tests in
  Multivariate Binomial Models*, JASA.
  <https://doi.org/10.1080/01621459.1989.10478837>. Earlier minP work explicitly
  addresses dependence among binomial comparisons.
- *Addressing researcher degrees of freedom through minP adjustment* (2024),
  BMC Medical Research Methodology.
  <https://doi.org/10.1186/s12874-024-02279-2>. A medical application confirms
  that minP itself is not new to biomedical research.
- Zaffalon (2002), *Exact credal treatment of missing data*, Journal of
  Statistical Planning and Inference 105, 105--122.
  <https://doi.org/10.1016/S0378-3758(01)00206-3>. Compatible completions and
  bounds with incomplete categorical observations precede this application;
  its inferential framework differs from the test inversion above.
- Malloy, Tripathy and Nowak, *Optimal Confidence Regions for the Multinomial
  Parameter*, version 2 (2021). <https://arxiv.org/abs/2002.01044>. Their
  optimality criterion concerns categorical confidence regions and should not
  be equated with uniformly shortest MIC cumulative intervals.
- Weine, McPeek and Abney (2023), *Application of Equal Local Levels to Improve
  Q-Q Plot Testing Bands with R Package qqconf*, Journal of Statistical
  Software 106(10). <https://www.jstatsoft.org/article/view/v106i10>. Their
  simultaneous bands and binomial recursion on ordered boundaries are
  especially close computational foundations. Neither a recurrence of this
  form nor dependence-aware distribution bands should be claimed as new here.
- Gontscharuk, Landwehr and Finner (2016), *Goodness of fit tests in terms of
  local levels with special emphasis on higher criticism tests*, Bernoulli
  22(3), 1331--1363. <https://doi.org/10.3150/14-BEJ694>. The local-level and
  equal-local-level literature is a required comparison for the statistical
  construction, alongside standard distribution-function bands.

These references establish nearby foundations. They do not constitute a
systematic novelty search or establish that the present MIC-specific
construction has no prior equivalent.

## Timing and incomplete numerical refinement

The `time_limit_seconds` argument is a cooperative budget for optional joint
refinement after the conservative baseline has been computed. It is not a hard
limit on the entire analysis. Results expose `baseline_seconds`,
`refinement_seconds`, `elapsed_seconds` and
`time_limit_scope="optional_joint_refinement"`; HTML population details show the
two calculation times. A timeout or failed refinement retains available baseline
bounds and does not certify the requested endpoint precision. The result
separately explains missing counts, sampling uncertainty and numerical accuracy.

The executable finite-model oracle is in
`reproducibility/v1.0.0/joint-distribution-20260930`; its integration checks are in
`tests/test_joint_independent.py`. Lattice diagnostics must not be read as
continuous-region volumes or guarantees of shorter projected intervals.

## Direct certification of a population question

Let R denote the fixed joint confidence region and g(p) a requested panel-tail
share. To certify g(p) < q for every p in R, the search covers the closed set
B = {p in the baseline outer region: g(p) >= q}. Each parameter box is rejected
only when its directed upper bound on the existing joint p-value is strictly
below alpha. If every box is rejected, R intersect B is empty. The same argument
with the inequalities reversed certifies g(p) > q. This is a computational
consequence of the existing confidence region, not a different statistical test.

The initial boundary is rounded outward; equality is retained. A split covers
both closed children and monotonicity removes only infeasible CDF points. Thus
induction over the recorded splitting tree proves that a completed exclusion
covers the entire counter-side. Interrupted, unsplittable or failed cells prevent
certification. The search neither removes cells from the separate distribution
calculation nor intersects regions from different methods. Simultaneous coverage
is inherited from R, so these projections require no additional multiplicity
adjustment. They do not extend the stated sampling assumptions.

The JSON trace records the initial box, splits, excluded leaves, rejection
bounds, confidence level, method and constraint signature. A saved update
recomputes this search from the updated information. Certificates with a
different signature, method, confidence level or criterion are not used to
resolve a question. The checks in `tests/test_population_question_search.py`
replay the splitting tree and the box bounds, and exercise equality, interruption
and incompatible certificates.
