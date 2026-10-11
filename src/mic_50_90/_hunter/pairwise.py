"""Exact pair-count primitives and probability certificates.

All candidates and thresholds denote exact rationals. Float inputs denote their
shortest decimal strings, never an implicitly renormalized simplex point.
See MATHEMATICS.md for definitions, certificates, assumptions and limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from math import comb, isfinite, lcm
from numbers import Integral
from time import monotonic
from typing import Mapping

import numpy as np
from .budget import effective_deadline

ZERO, ONE = Fraction(0), Fraction(1)


def _integer(x, name, minimum=0):
    if isinstance(x, (bool, np.bool_)) or not isinstance(x, Integral) or int(x) < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(x)


def _fraction(x):
    if isinstance(x, Fraction):
        return x
    if isinstance(x, (float, np.floating)):
        if not isfinite(x):
            raise ValueError("rational values must be finite")
        return Fraction(str(x))
    if isinstance(x, (bool, np.bool_)):
        raise ValueError("booleans are not probabilities")
    try:
        return Fraction(x)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("expected an exact rational or finite decimal value") from exc


def _probabilities(p, minimum_length=2):
    p = tuple(_fraction(x) for x in p)
    if len(p) < minimum_length or any(x < 0 or x > 1 for x in p) or sum(p) != 1:
        raise ValueError("probabilities must be nonnegative and sum exactly to one")
    return p


def _threshold(t):
    t = _fraction(t)
    if not 0 <= t <= 1:
        raise ValueError("threshold must be in [0,1]")
    return t


def _check_deadline(deadline):
    deadline = effective_deadline(deadline)
    if deadline is not None and monotonic() >= deadline:
        raise TimeoutError("Joint MIC range calculation reached its time limit")


@dataclass(frozen=True)
class HistRegion:
    """Union of integer count regions; constraints are (start, stop, low, high).

    Category slices are zero-based and half-open. A variant is a tuple of
    contiguous count constraints. An empty variant means all histograms with
    the fixed total; an empty union is rejected.
    """
    n: int
    k: int
    variants: tuple

    def __post_init__(self):
        n, k = _integer(self.n, "n", 1), _integer(self.k, "k", 2)
        variants = tuple(tuple(tuple(c) for c in v) for v in self.variants)
        if not variants:
            raise ValueError("empty union of reporting variants")
        for v in variants:
            for c in v:
                if len(c) != 4:
                    raise ValueError("a count constraint has four entries")
                a, b, lo, hi = (_integer(x, "count constraint") for x in c)
                if not (0 <= a <= b <= k and 0 <= lo <= hi <= n):
                    raise ValueError("invalid contiguous count interval")
        object.__setattr__(self, "n", n)
        object.__setattr__(self, "k", k)
        object.__setattr__(self, "variants", variants)


def as_region(problem):
    """Adapt one EmpiricalProblem, mapping/list of variants, or HistRegion.

    Independently inspect every matrix row and RHS: production's TU metadata
    and floating tolerance flags are not used to authorize integer geometry.
    """
    if isinstance(problem, HistRegion):
        return problem
    problems = tuple(problem.values()) if isinstance(problem, Mapping) else (
        tuple(problem) if isinstance(problem, (list, tuple)) else (problem,))
    if not problems:
        raise ValueError("empty union of reporting variants")
    first = problems[0]
    n, k = _integer(first.n, "n", 1), _integer(first.k, "k", 2)
    variants = []
    for item in problems:
        if item.n != n or item.k != k or item.panel != first.panel:
            raise ValueError("reporting variants must share n and panel")
        matrix, lower, upper = item.linear_constraints
        constraints = []
        for row, lo, hi in zip(matrix, lower, upper):
            row = np.asarray(row)
            if row.shape != (k,) or not np.all(np.isin(row, (0, 1))):
                raise ValueError("only contiguous indicator constraints are supported")
            support = np.flatnonzero(row)
            if len(support) and support[-1] - support[0] + 1 != len(support):
                raise ValueError("only contiguous indicator constraints are supported")
            if np.isnan(lo) or np.isnan(hi) or lo == np.inf or hi == -np.inf:
                raise ValueError("invalid report right hand side")
            if (np.isfinite(lo) and lo != int(lo)) or (np.isfinite(hi) and hi != int(hi)):
                raise ValueError("report counts must be exactly integral")
            lo = max(0, int(lo)) if np.isfinite(lo) else 0
            hi = min(n, int(hi)) if np.isfinite(hi) else n
            if lo > hi:
                # Preserve an infeasible variant; max-statistic rejects it.
                constraints.append((0, 0, 1, 1))
            else:
                a, b = (int(support[0]), int(support[-1]) + 1) if len(support) else (0, 0)
                constraints.append((a, b, lo, hi))
        variants.append(tuple(constraints))
    return HistRegion(n, k, tuple(variants))


def range_family(k):
    """One member per distinct contiguous nonfull range/complement event."""
    k = _integer(k, "k", 2)
    return tuple((a, b) for a in range(k) for b in range(a + 1, k))


@lru_cache(maxsize=64)
def _integer_binomial(n, q):
    """Common-denominator masses, with interruption between integer steps."""
    a, d = q.numerator, q.denominator
    denominator = d ** n
    _check_deadline(None)
    if a==d:return tuple([0]*n+[denominator]),denominator
    mass=(d-a)**n
    weights=[]
    for c in range(n+1):
        _check_deadline(None)
        weights.append(mass)
        if c<n:
            mass,remainder=divmod(mass*(n-c)*a,(c+1)*(d-a))
            if remainder:raise ArithmeticError('Nonintegral binomial recurrence')
    return tuple(weights),denominator


@lru_cache(maxsize=256)
def _binomial_masses(n, q):
    weights,denominator=_integer_binomial(n,q)
    masses=[]
    for mass in weights:
        _check_deadline(None)
        masses.append(Fraction(mass,denominator))
    return tuple(masses)


def exact_binomial_scores(n, q):
    """b(c,q)=min(1, 2 min(P[X<=c],P[X>=c])), inclusive exact tails."""
    n = _integer(n, "n", 1)
    q = _threshold(q)
    return _exact_scores(n, q)


@lru_cache(maxsize=256)
def _exact_scores(n, q):
    weights,denominator = _integer_binomial(n,q)
    cumulative, scores = 0, []
    for mass in weights:
        _check_deadline(None)
        previous = cumulative
        cumulative += mass
        scores.append(Fraction(min(denominator, 2*min(cumulative, denominator-previous)),denominator))
    return tuple(scores)


@dataclass(frozen=True)
class MaxStatistic:
    threshold: Fraction
    witness: tuple[int, ...]
    feasibility_checks: int


def _feasible_histogram(n, k, constraints):
    """Bellman-Ford with an implicit super-source; exact integer arithmetic."""
    edges = [(j+1, j, 0) for j in range(k)]
    edges.extend(((0, k, n), (k, 0, -n)))
    for a, b, lo, hi in constraints:
        edges.extend(((a, b, hi), (b, a, -lo)))
    distances = [0]*(k+1)
    for _ in range(k+1):
        changed = False
        for a, b, weight in edges:
            if distances[b] > distances[a] + weight:
                distances[b] = distances[a] + weight
                changed = True
        if not changed:
            h = tuple(distances[j+1]-distances[j] for j in range(k))
            if sum(h) != n or min(h) < 0 or not all(
                    lo <= sum(h[a:b]) <= hi for a,b,lo,hi in constraints):
                raise ArithmeticError("integer witness verification failed")
            return h
    return None


def max_compatible_statistic(problem, p, *, deadline=None):
    """Exact max-min statistic via score bisection and difference constraints.

    Histograms are never enumerated by this routine. Empty reports raise;
    infeasible alternatives in a nonempty union do not exclude valid ones.
    """
    region = as_region(problem)
    p = _probabilities(p)
    if len(p) != region.k:
        raise ValueError("candidate dimension differs from report panel")
    ranges = range_family(region.k)
    scores = []
    for a,b in ranges:
        _check_deadline(deadline)
        scores.append(exact_binomial_scores(region.n,sum(p[a:b])))
    _check_deadline(deadline)
    return _max_from_scores(region,ranges,scores,deadline)


def _max_from_scores(region,ranges,scores,deadline):
    levels = sorted({x for row in scores for x in row})
    checks = 0

    def feasible(t):
        nonlocal checks
        _check_deadline(deadline)
        checks += 1
        constraints = []
        for (a,b), row in zip(ranges, scores):
            allowed = [c for c,value in enumerate(row) if value >= t]
            if not allowed:
                return None
            # Two inclusive monotone tails imply a contiguous superlevel set.
            constraints.append((a,b,allowed[0],allowed[-1]))
        for variant in region.variants:
            _check_deadline(deadline)
            witness = _feasible_histogram(region.n, region.k, (*variant,*constraints))
            if witness is not None:
                return witness
        return None

    left, right, winner, value = 0, len(levels), None, None
    while left < right:
        middle = (left+right)//2
        witness = feasible(levels[middle])
        if witness is not None:
            winner, value, left = witness, levels[middle], middle+1
        else:
            right = middle
    if winner is None:
        raise ValueError("empty or infeasible report histogram region")
    return MaxStatistic(value, winner, checks)


def _membership(p, e, f):
    result = [ZERO]*4
    for j, probability in enumerate(p):
        state = int(e[0] <= j < e[1]) + 2*int(f[0] <= j < f[1])
        result[state] += probability
    return tuple(result)


def pair_count_distribution_exact(n, q):
    """Exact integer DP, q ordered 00,10,01,11; returns rational cells."""
    n = _integer(n, "n", 1)
    q = _probabilities(q, 4)
    if len(q) != 4:
        raise ValueError("four isolate membership probabilities required")
    return _pair_exact_cached(n,q) if n <= 30 else _pair_exact(n,q)


@lru_cache(maxsize=128)
def _pair_exact_cached(n,q):
    return _pair_exact(n,q)


def _pair_exact(n,q):
    denominator = lcm(*(x.denominator for x in q))
    weights = tuple(int(x*denominator) for x in q)
    cells = [[1]]
    for r in range(n):
        _check_deadline(None)
        new = [[0]*(r+2) for _ in range(r+2)]
        for a in range(r+1):
            for b in range(r+1):
                value = cells[a][b]
                if value:
                    for da,db,state in ((0,0,0),(1,0,1),(0,1,2),(1,1,3)):
                        new[a+da][b+db] += value*weights[state]
        cells = new
    denominator **= n
    result=[]
    for row in cells:
        _check_deadline(None)
        result.append(tuple(Fraction(value,denominator) for value in row))
    return tuple(result)


def _float_interval(q):
    rounded = float(q)
    actual = Fraction.from_float(rounded)
    low = np.nextafter(rounded,-np.inf) if actual > q else rounded
    high = np.nextafter(rounded,np.inf) if actual < q else rounded
    return max(0.,float(low)), min(1.,float(high))


def _out_product(array, scalar, upward):
    # Exact structural zeros remain zero, including subnormal underflow cases.
    product_value = array * scalar
    direction = np.inf if upward else -np.inf
    rounded = np.nextafter(product_value,direction)
    return np.where((array == 0) | (scalar == 0), 0., np.maximum(0.,rounded))


def _out_add(a,b,upward):
    rounded = np.maximum(0.,np.nextafter(a+b,np.inf if upward else -np.inf))
    return np.where(b == 0,a,np.where(a == 0,b,rounded))


def pair_count_distribution_bounds(n, q, *, deadline=None):
    """Outward binary64 DP, O(n^3) time / O(n^2) memory for one pair.

    Uses separate rounded multiply/add operations, including subnormals and
    rational-to-float endpoint conversion. No range independence assumption.
    """
    n = _integer(n, "n", 1)
    q = _probabilities(q, 4)
    if len(q) != 4:
        raise ValueError("four isolate membership probabilities required")
    _check_deadline(deadline)
    if deadline is None and n <= 150:
        return _pair_bounds_cached(n,q)
    return _pair_bounds(n,q,deadline)


@lru_cache(maxsize=128)
def _pair_bounds_cached(n,q):
    return _pair_bounds(n,q,None)


def _pair_bounds(n,q,deadline):
    intervals = tuple(_float_interval(x) for x in q)
    return _pair_interval_dp(n,intervals,deadline)


def _pair_interval_dp(n,intervals,deadline):
    low, high = np.ones((1,1)), np.ones((1,1))
    for r in range(n):
        _check_deadline(deadline)
        new_low, new_high = np.zeros((r+2,r+2)), np.zeros((r+2,r+2))
        for da,db,state in ((0,0,0),(1,0,1),(0,1,2),(1,1,3)):
            if intervals[state][1] == 0:
                continue
            qlo,qhi = intervals[state]
            target = (slice(da,da+r+1),slice(db,db+r+1))
            new_low[target] = _out_add(new_low[target],_out_product(low,qlo,False),False)
            new_high[target] = _out_add(new_high[target],_out_product(high,qhi,True),True)
        low,high = new_low,np.minimum(1.,new_high)
    low.setflags(write=False)
    high.setflags(write=False)
    return low,high


def _sum_out(array,upward):
    values = np.asarray(array,dtype=float).ravel()
    if not values.size:
        return ZERO
    while values.size > 1:
        half = values.size//2
        new = _out_add(values[:2*half:2],values[1:2*half:2],upward)
        values = np.concatenate((new,values[-1:])) if values.size%2 else new
    return min(ONE,Fraction.from_float(float(values[0])))


@dataclass(frozen=True)
class ProbabilityBounds:
    lower: Fraction
    upper: Fraction

    def __post_init__(self):
        lo,hi = _threshold(self.lower),_threshold(self.upper)
        if lo > hi:
            raise ValueError("probability lower bound exceeds upper bound")
        object.__setattr__(self,"lower",lo)
        object.__setattr__(self,"upper",hi)




def _tree(m,pairs):
    parent = list(range(m))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    chosen,weight = [],ZERO
    for (i,j),bounds in sorted(pairs.items(),key=lambda item:(-item[1].lower,item[0])):
        a,b = root(i),root(j)
        if a != b:
            parent[a] = b
            chosen.append((i,j))
            weight += bounds.lower
            if len(chosen) == m-1:
                break
    return tuple(chosen),weight


@dataclass(frozen=True)
class DualCertificate:
    coefficients: tuple[Fraction,...]
    normalization_repair: Fraction
    minimum_slack: Fraction
    patterns_checked: int
    upper_bound: Fraction
    verified: bool


def certify_moment_dual(m,moments,coefficients):
    """Rationalize any candidate dual and repair all pattern inequalities.

    Moments ordered as singletons then lexicographic i<j pairs. Each converted
    coefficient is an exact rational; the normalization coefficient is raised
    by the greatest exact violation. Objective signs select outward endpoints.
    """
    m = _integer(m,"number of events",1)
    if m > 12:
        raise ValueError("moment-pattern certificate limited to m<=12")
    pairs = tuple((i,j) for i in range(m) for j in range(i+1,m))
    expected = m+len(pairs)
    if len(moments) != expected or len(coefficients) != expected+1:
        raise ValueError("wrong moment or dual dimension")
    y = tuple(_fraction(x).limit_denominator(10**9) for x in coefficients)
    common = lcm(*(x.denominator for x in y))
    integers = tuple(int(x*common) for x in y)
    pair_index = {pair:1+m+j for j,pair in enumerate(pairs)}
    lhs = [integers[0]]*(1<<m)
    for mask in range(1,1<<m):
        bit = mask & -mask
        i = bit.bit_length()-1
        rest = mask ^ bit
        value = lhs[rest]+integers[1+i]
        for j in range(i+1,m):
            if rest & (1<<j):
                value += integers[pair_index[(i,j)]]
        lhs[mask] = value
    required = [0]+[common]*((1<<m)-1)
    repair_int = max(0,max(want-got for want,got in zip(required,lhs)))
    repair = Fraction(repair_int,common)
    repaired = (y[0]+repair,*y[1:])
    slack = Fraction(min(got+repair_int-want for want,got in zip(required,lhs)),common)
    objective = repaired[0]+sum((coefficient*(moment.upper if coefficient>=0 else moment.lower)
                                for coefficient,moment in zip(repaired[1:],moments)),ZERO)
    return DualCertificate(repaired,repair,slack,1<<m,min(ONE,max(ZERO,objective)),slack>=0)


def _moment_lp(m,moments,deadline):
    if m > 12:
        return None,"not attempted: more than 12 events"
    try:
        _check_deadline(deadline)
        from scipy.optimize import linprog
        pairs = tuple((i,j) for i in range(m) for j in range(i+1,m))
        masks = np.arange(1<<m,dtype=np.int64)
        indicators = ((masks[:,None] >> np.arange(m)) & 1).astype(float)
        features = np.column_stack((indicators,*[indicators[:,i]*indicators[:,j] for i,j in pairs])) if pairs else indicators
        objective = np.asarray([1.,*[float(x.upper) for x in moments],*[-float(x.lower) for x in moments]])
        inequalities = np.column_stack((-np.ones(1<<m),-features,features))
        rhs = -(masks != 0).astype(float)
        options = {}
        if deadline is not None:
            options["time_limit"] = max(0.001,deadline-monotonic())
        result = linprog(objective,A_ub=inequalities,b_ub=rhs,
                         bounds=[(None,None)]+[(0,None)]*(2*len(moments)),
                         method="highs",options=options)
        if result.x is None or not np.all(np.isfinite(result.x)):
            return None,f"no finite dual candidate: {result.message}"
        size = len(moments)
        coefficients = (result.x[0],*(result.x[1:1+size]-result.x[1+size:]))
        certificate = certify_moment_dual(m,moments,coefficients)
        return certificate,f"rational dual verified; solver status {result.status}"
    except (ImportError,TimeoutError,ValueError,RuntimeError,ArithmeticError) as exc:
        return None,f"safe Hunter fallback: {type(exc).__name__}: {exc}"


@dataclass(frozen=True)
class CalibrationResult:
    threshold: Fraction
    bonferroni: Fraction
    hunter: Fraction
    bound: Fraction
    marginal_bounds: tuple[ProbabilityBounds,...]
    pair_bounds: dict
    tree_edges: tuple
    lp_certificate: DualCertificate | None
    lp_status: str
    pairs_completed: int
    pairs_total: int
    monotonicity: str = "valid pointwise upper bound; not monotonized"










def _simplex_box(lower,upper,minimum_length=2):
    lower,upper = tuple(_threshold(x) for x in lower),tuple(_threshold(x) for x in upper)
    if len(lower) < minimum_length or len(lower) != len(upper):
        raise ValueError("box dimensions must agree")
    if any(a>b for a,b in zip(lower,upper)) or sum(lower)>1 or sum(upper)<1:
        raise ValueError("empty probability box on the simplex")
    # Individual tightening is exact for a box intersected with sum p=1.
    sumlo,sumhi = sum(lower),sum(upper)
    lo = tuple(max(a,ONE-(sumhi-b)) for a,b in zip(lower,upper))
    hi = tuple(min(b,ONE-(sumlo-a)) for a,b in zip(lower,upper))
    return lo,hi




def pair_count_distribution_box_bounds(n,lower,upper,*,deadline=None):
    """Directed DP for any four-cell law in a simplex probability box.

    Intermediate interval endpoints need not sum to one; the recurrence uses
    nonnegative-polynomial inclusion, not a fabricated normalized distribution.
    """
    n = _integer(n,"n",1)
    lower,upper = _simplex_box(lower,upper,4)
    if len(lower) != 4:
        raise ValueError("four membership cells required")
    intervals = tuple((_float_interval(a)[0],_float_interval(b)[1]) for a,b in zip(lower,upper))
    return _pair_interval_dp(n,intervals,deadline)


def _score_envelopes(n,lo,hi):
    masses_lo,masses_hi = _binomial_masses(n,lo),_binomial_masses(n,hi)
    scores_lo,scores_hi = _exact_scores(n,lo),_exact_scores(n,hi)
    lower = tuple(min(a,b) for a,b in zip(scores_lo,scores_hi))
    cdf_lo,sf_hi,upper = ZERO,ONE,[]
    for a,b in zip(masses_lo,masses_hi):
        cdf_lo += a
        upper.append(min(ONE,2*min(cdf_lo,sf_hi)))
        sf_hi -= b
    return lower,tuple(upper)


def _binomial_event_box(n,lo,hi,allowed):
    # Every binomial PMF cell is unimodal in q, peaking at c/n (endpoints for
    # c=0,n). Exact cellwise extrema yield an outward bound for any event set.
    masses_lo,masses_hi = _binomial_masses(n,lo),_binomial_masses(n,hi)
    total_lo,total_hi = ZERO,ZERO
    for c in allowed:
        total_lo += min(masses_lo[c],masses_hi[c])
        mode = Fraction(c,n)
        maximum = max(masses_lo[c],masses_hi[c])
        if lo < mode < hi:
            maximum = max(maximum,Fraction(comb(n,c))*mode**c*(1-mode)**(n-c))
        total_hi += maximum
    return ProbabilityBounds(total_lo,min(ONE,total_hi))




