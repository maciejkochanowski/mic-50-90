# Population row-lift theorem and measurement-interval projection

## Setting and result

Fix the sample size n, ordered panel of K categories and a doubled-binomial-score cutoff c. The cutoff is fixed before the report is observed. Let L(x), U(x) be the exact equal-tailed binomial confidence endpoints at that cutoff. Then L(x)=1-U(n-x), U(n)=1, and U is increasing. Suppose the finite sequence U(0),...,U(n) is discretely concave. This is a sufficient condition to be verified for the chosen n and c, not an assertion about all possible confidence rules.

For one reporting interpretation let D be its closed integer difference-bound matrix: S_b-S_a<=D_ab, S_0=0, S_K=n. Bounds must describe contiguous category counts; quantile ranks, cumulative counts, internal-range counts and bounds on such counts are included. Define the K+1 count histograms h^v by S^v_j=D_vj-D_v0.

**Population row-lift theorem.** Under these conditions, the union of the complete-data population regions for h^0,...,h^K has exactly the same lower and upper projection endpoints for every contiguous range as the union over all compatible histograms. For nonempty proper ranges, these endpoints also equal the report envelope obtained by applying L to minimum range counts and U to maximum range counts. The full range has probability one and the empty range probability zero. The assertion concerns projections, not equality of the full sets. Apply it separately to alternative interpretations and unite their projections.

## Proof

Discrete concavity and monotonicity give, for integers 0<=x<=x+d<=n,

    L(d) <= U(x+d)-U(x) <= U(d).

The lower inequality follows because the smallest increment of length d is U(n)-U(n-d)=L(d). The largest is U(d)-U(0)<=U(d), giving the upper inequality. Complementarity gives the same increment bounds for L. It also gives

    L(x+y) <= L(x)+U(y) <= U(x+y)  (x,y>=0, x+y<=n).

For an anchor 0<=v<K define population cumulative values relative to that anchor as T_j=-L(-D_vj) when j<v, T_v=0, and T_j=U(D_vj) when j>v. Subtract T_0 from all values. For 0<v<K, total-count equality gives D_vK=D_v0+n, hence T_K-T_0=1 by complementarity. For v=0 this follows from U(n)=1. Nonnegative count constraints and monotonicity give nonnegative successive population differences. Anchor K duplicates count anchor 0 because D_Kj=D_0j-n; use the same population vector for these two anchors.

For a range i<j not crossing v, the first increment inequality or its complementary L form gives L(S^v_j-S^v_i)<=T_j-T_i<=U(S^v_j-S^v_i). For i<v<j, the second inequality gives the same conclusion. For i=v or j=v one endpoint is attained by definition. Thus this population vector belongs to the complete-data region of h^v.

Every compatible histogram satisfies -D_ji<=S_j-S_i<=D_ij. Monotonicity therefore bounds every proper compatible population projection by [L(-D_ji),U(D_ij)]. The vector anchored at i attains the upper endpoint and the vector anchored at j attains the lower endpoint when j<K. If j=K, anchor 0 gives 1-U(D_0i)=L(n-D_0i)=L(-D_Ki), attaining the lower endpoint. These vectors lie in the regions of the count-row histograms, proving both equalities. The full range and empty range have fixed probabilities one and zero. Complementary ranges, including ranges ending at K, obey the same equal-tailed constraints. No enumeration or unproved claim about binomial endpoint curvature enters the argument. At most K distinct count-row histograms are needed because anchors 0 and K coincide.

## Recognizing the class and certifying numerical results

For fixed n and c, directed binomial-tail brackets provide lower and upper bounds on each exact U(x). The inequalities 2*U_lower(x)>=U_upper(x-1)+U_upper(x+1), x=1,...,n-1, certify the sufficient condition for every compatible report on this panel. A failed comparison is unresolved, not a counterexample to concavity. The finite check costs n+1 endpoint evaluations and can be reused for all reports with this n and cutoff. It does not establish a universal theorem about Clopper–Pearson curvature.

In the inference engine, numerical endpoint gaps are still certified from inward witness regions and an outward report envelope. This protects the returned endpoints when a shape check is unavailable or numerical brackets do not settle an equality. K+1 accepted probability-row potentials also suffice to certify all projections: each is checked against the report's integer constraints and the fixed binomial acceptance bands. Failure at one chosen point does not exclude its face. Residual count cells are split on an integer cumulative count; the two children are disjoint and cover the parent. Each unresolved cell retains its own outer envelope. A parent is replaced only after both child envelopes exist. Time or memory interruption therefore retains a conservative union.

## Measurement-interval projection

For an event A, let D(A) contain measured categories wholly in A, and P(A) categories that can intersect A. For every distribution of concentrations compatible with the measurement intervals,

    sum_{j in D(A)} p_j <= Pr(MIC in A) <= sum_{j in P(A)} p_j.

Projecting one simultaneous category confidence region onto the two sides preserves its original simultaneous coverage event; it does not require another multiplicity correction. For a strict tail these two category sets are contiguous tails. For sample counts the same inequalities yield sharp integer bounds by minimizing the definite count and maximizing the possible count. Concentrations within an ambiguous category may be placed on either side without adding a shape assumption. Empty fields supply no constraint. A fully known category histogram does not in general identify within-category allocation.

## Position relative to prior theory

Binomial confidence endpoints, simultaneous union bounds, integer difference constraints, shortest-path potentials and deterministic projection of confidence sets are established tools. The contribution specified here is their conditional row-lift result for incompletely reported ordered counts, with a finite, verifiable shape condition and an implementation retaining numerical certificates. Coverage comes from P4; this theorem concerns computation and endpoint attainment, not a new coverage level. No claim of universal novelty or global dominance follows from the theorem alone.

## General finite increment condition

The concavity-based statement above is a sufficient specialization of P6. More generally, it is enough that every admissible increment satisfies L(d) <= U(x+d)-U(x) <= U(d), with U nondecreasing, U(n)=1 and L(x)=1-U(n-x). The reflected increment gives the L bound; applying the same condition with length n-x-y gives the crossing-anchor bound. The remaining population construction and attainment proof are unchanged.

For n=4, U=(2/5,3/5,7/10,9/10,1) satisfies this condition and is not concave. This abstract example proves strict weakening; it is not a replacement statistical confidence rule. The linked Lean file proves the increment implication and its explicit nonconcave example. The production engine continues to use the verified concavity condition or direct endpoint certificates. The generalized algebra and example are machine-checked in formal/P6Core.lean.
