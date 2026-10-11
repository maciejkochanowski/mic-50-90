"""Joint population inference for a fixed ordered MIC panel.

The sampling law is finite multinomial, not a Wilks approximation. Exploratory
point evaluations use SciPy. Parameter-box exclusion uses separate, directed
Decimal calculations: an unresolved box is never rejected by a grid search.
See docs/joint-distribution-method.md for the coverage and containment proofs.
"""
from __future__ import annotations

from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR
from fractions import Fraction
from functools import lru_cache
from heapq import heappop, heappush
from hashlib import sha256
from itertools import chain
import json
from math import comb, isfinite
from time import monotonic

import numpy as np
from scipy.stats import binom

from .exact_population import clopper_pearson
from .utility import _prefix_distances
from .validation import exact_integer

_DOWN = Context(prec=40, rounding=ROUND_FLOOR)
_UP = Context(prec=40, rounding=ROUND_CEILING)
_ZERO, _ONE = Decimal(0), Decimal(1)


def _check_time(deadline):
    if deadline is not None and monotonic() >= deadline:
        raise TimeoutError("Joint population time budget exhausted")


def _validate(problems):
    if not problems:
        raise ValueError("at least one feasible reporting variant is required")
    first = next(iter(problems.values()))
    if any(p.n != first.n or p.panel != first.panel for p in problems.values()):
        raise ValueError("reporting variants must share sample size and panel")
    if any(not p.has_total_unimodular_canonical_matrix or not p._integral_rhs for p in problems.values()):
        raise ValueError("joint inference requires integral contiguous-category constraints")
    return first.n, first.k


def _constraint_signature(problems):
    content = []
    for name, p in sorted(problems.items()):
        matrix, lower, upper = p.linear_constraints
        content.append([name, p.n, p.panel.as_dict(), matrix.tolist(),
                        [str(x) for x in lower], [str(x) for x in upper]])
    return sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _cdf(cdf):
    f = np.asarray(cdf, dtype=float)
    if f.ndim != 1 or not len(f) or not np.all(np.isfinite(f)) or np.any(f < 0) or np.any(f > 1) or np.any(np.diff(f) < 0):
        raise ValueError("CDF cuts must be finite, ordered probabilities")
    return f


def _float_out(value, up):
    if value == 0:
        return 0.
    if value == 1:
        return 1.
    value = float(value)
    if up:
        return min(1., float(np.nextafter(value, np.inf)))
    return max(0., float(np.nextafter(value, -np.inf)))


def _binomial_window(n, theta, first, last, context, deadline=None):
    """Bounds on a PMF window; theta is an exact rational probability."""
    _check_time(deadline)
    if first > last:
        return []
    if theta == 0 or theta == 1:
        atom = n if theta == 1 else 0
        return [_ONE if s == atom else _ZERO for s in range(first, last+1)]
    a, b = theta.numerator, theta.denominator
    p = context.divide(Decimal(a), Decimal(b))
    q = context.divide(Decimal(b-a), Decimal(b))
    mass = context.multiply(Decimal(comb(n, first)),
                            context.multiply(context.power(p, first), context.power(q, n-first)))
    values = [mass]
    for s in range(first, last):
        if s % 64 == 0:
            _check_time(deadline)
        # The multiplier is an exact rational, rounded in the requested direction.
        mass = context.divide(context.multiply(mass, Decimal((n-s)*a)), Decimal((s+1)*(b-a)))
        values.append(mass)
    return values


@lru_cache(maxsize=128)
def _binomial_tails(n, probability, deadline=None):
    _check_time(deadline)
    theta = Fraction.from_float(float(probability))
    lower = _binomial_window(n, theta, 0, n, _DOWN, deadline)
    upper = _binomial_window(n, theta, 0, n, _UP, deadline)
    c_lo, c_hi, s_lo, s_hi = [], [], [_ZERO]*(n+1), [_ZERO]*(n+1)
    a, b = _ZERO, _ZERO
    for i, (x, y) in enumerate(zip(lower, upper)):
        if i % 64 == 0:
            _check_time(deadline)
        a, b = _DOWN.add(a, x), _UP.add(b, y)
        c_lo.append(min(a, _ONE)); c_hi.append(min(b, _ONE))
    a, b = _ZERO, _ZERO
    for s in range(n, -1, -1):
        if s % 64 == 0:
            _check_time(deadline)
        a, b = _DOWN.add(a, lower[s]), _UP.add(b, upper[s])
        s_lo[s], s_hi[s] = min(a, _ONE), min(b, _ONE)
    return c_lo, c_hi, s_lo, s_hi


@lru_cache(maxsize=64)
def _scores(n, probability, upper, deadline=None):
    _check_time(deadline)
    cl, cu, sl, su = _binomial_tails(n, float(probability), deadline)
    context = _UP if upper else _DOWN
    return tuple(min(_ONE, context.multiply(Decimal(2), min(a, b)))
                 for a, b in zip(cu if upper else cl, su if upper else sl))


@lru_cache(maxsize=64)
def _lower_score_floats(n, probability, deadline=None):
    return tuple(_float_out(x, False) for x in _scores(n, probability, False, deadline))


def rectangle_probability_bounds(n, cdf, lower, upper, *, deadline=None):
    """Outward bounds for an unconditional multinomial prefix rectangle.

    Binary64 cut coordinates are treated as exact rationals. Every PMF, product
    and sum is rounded outward at 40 decimal digits. No SciPy probability enters
    this certificate. Duplicate cuts are merged before the recurrence.
    """
    n = exact_integer(n, "n", 1)
    f = _cdf(cdf)
    if len(lower) != len(f) or len(upper) != len(f):
        raise ValueError("one integer count interval is required per cut")
    constraints = {}
    for q, lo, hi in zip(f, lower, upper):
        lo, hi = exact_integer(lo, "count lower", 0), exact_integer(hi, "count upper", 0)
        if lo > hi or lo > n:
            return 0., 0.
        previous = constraints.get(float(q), (0, n))
        constraints[float(q)] = (max(previous[0], lo), min(previous[1], hi, n))
    if any(lo > hi for lo, hi in constraints.values()):
        return 0., 0.
    prev_q = Fraction(0)
    prev_states = [0]
    weights_lo, weights_hi = [_ONE], [_ONE]
    for cut, (low, high) in sorted(constraints.items()):
        _check_time(deadline)
        q = Fraction.from_float(cut)
        theta = (q-prev_q)/(1-prev_q) if prev_q < 1 else Fraction(0)
        states = list(range(low, high+1))
        new_lo, new_hi = [_ZERO]*len(states), [_ZERO]*len(states)
        for s0, wlo, whi in zip(prev_states, weights_lo, weights_hi):
            if whi == 0:
                continue
            _check_time(deadline)
            begin, end = max(low, s0), min(high, n)
            if begin > end:
                continue
            plo = _binomial_window(n-s0, theta, begin-s0, end-s0, _DOWN, deadline)
            phi = _binomial_window(n-s0, theta, begin-s0, end-s0, _UP, deadline)
            for offset, (a, b) in enumerate(zip(plo, phi), begin-low):
                new_lo[offset] = _DOWN.add(new_lo[offset], _DOWN.multiply(wlo, a))
                new_hi[offset] = _UP.add(new_hi[offset], _UP.multiply(whi, b))
        prev_states, weights_lo, weights_hi, prev_q = states, new_lo, new_hi, q
    a, b = _ZERO, _ZERO
    for x, y in zip(weights_lo, weights_hi):
        a, b = _DOWN.add(a, x), _UP.add(b, y)
    return _float_out(a, False), _float_out(min(b, _ONE), True)


def _max_statistic(matrices, values, *, witness=False):
    """Maximize the minimum score using integer difference constraints."""
    candidates = np.unique(values)
    found = None
    def feasible(t):
        nonlocal found
        ranges = []
        for j in range(values.shape[1]):
            support = np.flatnonzero(values[:, j] >= t)
            if not len(support):
                return False
            ranges.append((int(support[0]), int(support[-1])))
        for matrix in matrices:
            d = matrix.copy()
            for j, (lo, hi) in enumerate(ranges, 1):
                d[0, j] = min(d[0, j], hi)
                d[j, 0] = min(d[j, 0], -lo)
            for k in range(len(d)):
                d = np.minimum(d, d[:, k, None]+d[None, k, :])
            if np.all(np.diag(d) >= 0):
                found = np.rint(d[0, 1:-1]).astype(int)
                return True
        return False
    left, right = 0, len(candidates)
    while left < right:
        mid = (left+right)//2
        if feasible(candidates[mid]):
            left = mid+1
        else:
            right = mid
    value = float(candidates[max(0, left-1)])
    if witness:
        feasible(value)
        return value, found
    return value


def max_compatible_statistic(problems, cdf):
    """Exploratory max-min binomial score; preserves all report constraints."""
    n, k = _validate(problems)
    f = _cdf(cdf)
    if len(f) != k-1:
        raise ValueError("one CDF probability is required for every panel cut")
    s = np.arange(n+1)[:, None]
    values = np.minimum(1., 2*np.minimum(binom.cdf(s, n, f), binom.sf(s-1, n, f)))
    return _max_statistic([_prefix_distances(p) for p in problems.values()], values)


def joint_minp_probability(n, cdf, t):
    """Finite sampling-law evaluation in binary64, for diagnostics/validation.

    This is not the parameter-box exclusion certificate.
    """
    n = exact_integer(n, "n", 1)
    f = _cdf(cdf)
    if not isfinite(t) or not 0 <= t <= 1:
        raise ValueError("score must lie in [0,1]")
    if t >= 1:
        return 1.
    old, states, weights = 0., np.array([0]), np.array([1.])
    for cut in f:
        counts = np.arange(n+1)
        scores = np.minimum(1., 2*np.minimum(binom.cdf(counts, n, cut), binom.sf(counts-1, n, cut)))
        allowed = counts[scores > t*(1+1e-12)+1e-300]
        if not len(allowed):
            return 1.
        theta = (cut-old)/(1-old) if old < 1 else 0.
        trans = binom.pmf(allowed[:, None]-states[None, :], n-states[None, :], np.clip(theta, 0, 1))
        weights, states, old = trans@weights, allowed, cut
    return float(np.clip(1-weights.sum(), 0, 1))


def joint_report_pvalue(problems, probabilities):
    n, k = _validate(problems)
    p = np.asarray(probabilities, dtype=float)
    if p.shape != (k,) or np.any(p < 0) or not np.all(np.isfinite(p)) or abs(p.sum()-1) > 1e-12:
        raise ValueError("one nonnegative probability per category, summing to one, is required")
    f = np.clip(np.cumsum(p)[:-1], 0, 1)
    return joint_minp_probability(n, f, max_compatible_statistic(problems, f))


def _box_upper(n, matrices, lower, upper, deadline=None, reject_below=None):
    _check_time(deadline)
    columns = []
    for l, u in zip(lower, upper):
        _check_time(deadline)
        _, c_hi, _, _ = _binomial_tails(n, float(l), deadline)
        _, _, _, s_hi = _binomial_tails(n, float(u), deadline)
        columns.append([_float_out(min(_ONE, _UP.multiply(Decimal(2), min(a, b))), True)
                        for a, b in zip(c_hi, s_hi)])
    t = _max_statistic(matrices, np.array(columns).T)
    if t >= 1:
        return 1.
    threshold = Decimal.from_float(t)
    union_bound = _float_out(min(_ONE, _UP.multiply(Decimal(len(lower)), threshold)), True)
    # The union bound alone can certify exclusion. Avoid the more expensive
    # rectangle recurrence when it cannot change this decision.
    if reject_below is not None and Fraction.from_float(union_bound) < reject_below:
        return union_bound
    constraints = {}
    for l, u in zip(lower, upper):
        lo_allowed = [i for i, v in enumerate(_scores(n, float(u), False, deadline)) if v > threshold]
        hi_allowed = [i for i, v in enumerate(_scores(n, float(l), False, deadline)) if v > threshold]
        if not lo_allowed or not hi_allowed:
            return union_bound
        for q, a, b in ((float(l), lo_allowed[0], n), (float(u), 0, hi_allowed[-1])):
            prev = constraints.get(q, (0, n))
            constraints[q] = max(a, prev[0]), min(b, prev[1])
    if any(a > b for a, b in constraints.values()):
        return union_bound
    cuts = sorted(constraints)
    inside_lo, _ = rectangle_probability_bounds(n, cuts, [constraints[q][0] for q in cuts],
                                                [constraints[q][1] for q in cuts], deadline=deadline)
    return min(union_bound, _float_out(_UP.subtract(_ONE, Decimal.from_float(inside_lo)), True))


def box_pvalue_upper(problems, lower, upper, *, deadline=None):
    """Uniform upper bound on the report p-value over an ordered CDF box."""
    n, k = _validate(problems)
    l, u = _cdf(lower), _cdf(upper)
    if len(l) != k-1 or len(u) != k-1 or np.any(l > u):
        raise ValueError("CDF box dimensions or endpoints are invalid")
    return _box_upper(n, [_prefix_distances(p) for p in problems.values()], l, u, deadline)


def _point_lower(n, matrices, f, deadline):
    _check_time(deadline)
    scores = np.array([_lower_score_floats(n, float(q), deadline) for q in f]).T
    t, counts = _max_statistic(matrices, scores, witness=True)
    if t >= 1:
        return 1.
    if t <= 0:
        return 0.
    # A lower threshold gives a subset of the exact rejection event. Upper
    # acceptance probabilities therefore give a valid lower p-value bound.
    lower_scores = [_scores(n, float(q), False, deadline)[int(s)] for q, s in zip(f, counts)]
    upper_scores = [_scores(n, float(q), True, deadline)[int(s)] for q, s in zip(f, counts)]
    threshold = min(lower_scores)
    critical = int(np.argmin(upper_scores))
    critical_proved = all(upper_scores[critical] <= lower_scores[j]
                          for j in range(len(f)) if j != critical)
    lows, highs = [], []
    for j, q in enumerate(f):
        allowed = [i for i, v in enumerate(_scores(n, float(q), True, deadline)) if v > threshold]
        # The observed cumulative count at a proved minimizing cut belongs to
        # the rejection event including equality. Resolve this identity exactly
        # instead of losing its (potentially large) atom to rounding intervals.
        if critical_proved and j == critical:
            allowed = [i for i in allowed if i != int(counts[j])]
        if not allowed:
            return 1.
        lows.append(allowed[0]); highs.append(allowed[-1])
    _, inside_hi = rectangle_probability_bounds(n, f, lows, highs, deadline=deadline)
    return _float_out(_DOWN.subtract(_ONE, Decimal.from_float(inside_hi)), False)


def _functional_bounds(lower, upper):
    l, u = np.r_[0., lower, 1.], np.r_[0., upper, 1.]
    cell_lo = np.maximum(0., np.nextafter(l[1:]-u[:-1], -np.inf))
    cell_hi = np.minimum(1., np.nextafter(u[1:]-l[:-1], np.inf))
    return np.r_[lower, cell_lo], np.r_[upper, cell_hi]


def _functional_values(f):
    return np.r_[f, np.diff(np.r_[0., f, 1.])]


def _interval_vectors(lower, upper, *, outward=True):
    """All contiguous projections of an ordered CDF box, rounded explicitly."""
    l, u = [Fraction(0), *map(Fraction, lower), Fraction(1)], [Fraction(0), *map(Fraction, upper), Fraction(1)]
    lows, highs = [], []
    def rounded(value, up):
        x = float(value)
        if (Fraction(x) < value if up else Fraction(x) > value):
            x = float(np.nextafter(x, np.inf if up else -np.inf))
        return x
    for a in range(len(l)-1):
        for b in range(a+1,len(l)):
            lows.append(rounded(max(Fraction(0),l[b]-u[a]), not outward))
            highs.append(rounded(min(Fraction(1),u[b]-l[a]), outward))
    return np.asarray(lows), np.asarray(highs)


def _attach_intervals(result, k, lo, hi, inner_lo=None, inner_hi=None):
    rows = []
    for index,(a,b) in enumerate((a,b) for a in range(k) for b in range(a+1,k+1)):
        valid = inner_lo is not None and np.isfinite(inner_lo[index]) and inner_lo[index] <= inner_hi[index]
        rows.append(dict(start_index=a,stop_index=b,lower=float(lo[index]),upper=float(hi[index]),
            inner_lower=float(inner_lo[index]) if valid else None, inner_upper=float(inner_hi[index]) if valid else None))
    result['interval_bounds'] = rows


def _cp_start(count, n, alpha_fraction):
    # A score cutoff of one is possible for n=1 at low confidence. Its
    # inclusive acceptance interval is well-defined even though a public
    # zero-confidence CP request is normally rejected by input validation.
    confidence = 1-float(alpha_fraction)
    if alpha_fraction == 1 or confidence == 1:
        # Subtracting a small score cutoff from one can round to one.
        # Invert the two tails directly; the directed checks below still
        # certify the final endpoints independently of this starting value.
        from scipy.special import betaincinv, betainccinv
        tail = float(alpha_fraction/2)
        return (0. if count == 0 else float(betaincinv(count, n-count+1, tail)),
                1. if count == n else float(betainccinv(count+1, n-count, tail)))
    return clopper_pearson(count, n, confidence)


def _cp_inner(count, n, alpha_fraction):
    """Certified locations inside CP endpoints for lower width bounds.

    Unlike outward brackets, these points pass the reversed, lower-tail
    probability comparison. They certify possible width, never coverage.
    """
    approximate = _cp_start(count, n, alpha_fraction)
    target = alpha_fraction/2
    endpoints = []
    for side in (0, 1):
        if (side == 0 and count == 0) or (side == 1 and count == n):
            endpoints.append(float(side)); continue
        x = approximate[side]
        delta = max(1e-12, 8*abs(np.spacing(x)))
        for _ in range(50):
            candidate = min(count/n, x+delta) if side == 0 else max(count/n, x-delta)
            cl, _, sl, _ = _binomial_tails(n, candidate)
            if Fraction(sl[count] if side == 0 else cl[count]) >= target:
                endpoints.append(candidate); break
            delta *= 2
        else:
            return None
    return tuple(endpoints)


def _cp_outer(count, n, alpha_fraction):
    """Bracket CP endpoints using directed binomial tails, not beta roundoff.

    SciPy supplies only a starting location. Each returned endpoint must pass a
    directed probability comparison with the exact binary64 confidence level.
    If it does not, expand toward the certain endpoints zero and one.
    """
    approximate = _cp_start(count, n, alpha_fraction)
    target = alpha_fraction/2
    endpoints = []
    for side in (0, 1):
        if (side == 0 and count == 0) or (side == 1 and count == n):
            endpoints.append(float(side)); continue
        x = approximate[side]
        delta = max(1e-12, 8*abs(np.spacing(x)))
        for _ in range(50):
            candidate = max(0., x-delta) if side == 0 else min(1., x+delta)
            if candidate in (0., 1.):
                endpoints.append(candidate); break
            _, cu, _, su = _binomial_tails(n, candidate)
            upper_tail = su[count] if side == 0 else cu[count]
            if Fraction(upper_tail) <= target:
                endpoints.append(candidate); break
            delta *= 2
        else:
            endpoints.append(float(side))
    return tuple(endpoints)


def _compatible_prefix_projections(matrices, n, k, alpha_fraction, pairs, *, witnesses):
    """Project the union of compatible, ordered CP boxes without enumerating h.

    A closed integer difference system has an extension with S[a]=s and
    S[b]=t exactly when its two-variable projection contains (s,t). For each
    s, monotonic CP endpoints make the smallest feasible t minimize the lower
    endpoint and the largest feasible t maximize the upper endpoint. See
    docs/compatible-population-projection.md for both extension arguments.

    Outer subtraction is directed. Inner endpoints are constructed only from
    the optimizing compatible pairs; they certify attained values in B(H),
    not accepted points of the smaller joint-minP region.
    """
    @lru_cache(maxsize=None)
    def outer(count):
        return _cp_outer(count, n, alpha_fraction)

    @lru_cache(maxsize=None)
    def inner(count):
        return _cp_inner(count, n, alpha_fraction)

    def endpoints(index, count, inward=False):
        if index in (0, k):
            value = float(index == k)
            return value, value
        return inner(count) if inward else outer(count)

    def difference(left, right, up):
        # One adjacent binary64 step encloses the exact subtraction of the
        # two binary64 endpoint certificates, including cancellation.
        return float(np.clip(np.nextafter(left-right, np.inf if up else -np.inf), 0., 1.))

    projected = {}
    for a, b in dict.fromkeys(pairs):
        low, high = 1., 0.
        low_pair = high_pair = None
        if (a, b) == (0, k):
            projected[a, b] = (1., 1., 1., 1.)
            continue
        for d in matrices:
            first_a, last_a = int(-d[a, 0]), int(d[0, a])
            first_b, last_b = int(-d[b, 0]), int(d[0, b])
            marginal_low = difference(endpoints(b, first_b)[0], endpoints(a, last_a)[1], False)
            marginal_high = difference(endpoints(b, last_b)[1], endpoints(a, first_a)[0], True)
            variant_low, variant_high = 1., 0.
            if a == 0:
                candidates = [(0, first_b, last_b)]
            elif b == k:
                # Here 1-U(s) decreases and 1-L(s) decreases with s.
                candidates = [(last_a, n, n), (first_a, n, n)]
            else:
                # Test boundary counts first. Prefix-only reports often attain
                # both marginal bounds here; this is an identical-projection
                # shortcut, not a switch to a different confidence method.
                counts = chain((first_a, last_a), range(first_a+1, last_a))
                candidates = ((s, max(first_b, s-int(d[b, a])),
                                min(last_b, s+int(d[a, b]))) for s in counts)
            for s, first, last in candidates:
                la, ua = endpoints(a, s)
                lb, _ = endpoints(b, first)
                _, ub = endpoints(b, last)
                candidate_low = difference(lb, ua, False)
                candidate_high = difference(ub, la, True)
                variant_low = min(variant_low, candidate_low)
                variant_high = max(variant_high, candidate_high)
                if low_pair is None or candidate_low < low:
                    low, low_pair = candidate_low, (s, first)
                if high_pair is None or candidate_high > high:
                    high, high_pair = candidate_high, (s, last)
                if variant_low <= marginal_low and variant_high >= marginal_high:
                    break
        inner_low, inner_high = np.inf, -np.inf
        if witnesses:
            sa, sb = low_pair
            ea, eb = endpoints(a, sa, True), endpoints(b, sb, True)
            if ea is not None and eb is not None:
                inner_low = difference(eb[0], ea[1], True)
            sa, sb = high_pair
            ea, eb = endpoints(a, sa, True), endpoints(b, sb, True)
            if ea is not None and eb is not None:
                inner_high = difference(eb[1], ea[0], False)
        projected[a, b] = low, high, inner_low, inner_high
    return np.asarray([projected[pair] for pair in pairs]).T


def population_distribution(problems, *, method='bonferroni', confidence_level=.95,
                            time_limit_seconds=30., tolerance_pp=.01, include_intervals=False, questions=(),
                            width_target_pp=None):
    """Simultaneous population CDF and category-mass outer bounds.

    ``complete`` for joint-exact requires an accepted witness within the stated
    tolerance of every outer endpoint. A time limit retains every unresolved
    box. The budget applies to optional refinement after the mandatory safe
    baseline; both times are reported. It is a cooperative, not hard real-time,
    deadline. This routine never substitutes grid minima for outer bounds.
    """
    n, k = _validate(problems)
    if method not in {'bonferroni', 'joint-exact', 'range-calibrated', 'range-hunter'}:
        raise ValueError("population method must be bonferroni, joint-exact, range-calibrated or range-hunter")
    if not isfinite(confidence_level) or not 0 < confidence_level < 1:
        raise ValueError("confidence_level must lie in (0,1)")
    if not isfinite(time_limit_seconds) or time_limit_seconds < 0:
        raise ValueError("time_limit_seconds must be finite and nonnegative")
    if not isfinite(tolerance_pp) or not 0 < tolerance_pp <= 100:
        raise ValueError("tolerance_pp must lie in (0,100]")
    if width_target_pp is not None:
        try:
            width_value = Fraction(str(width_target_pp))
        except (ValueError, ZeroDivisionError):
            raise ValueError('width_target_pp must lie in [0,100]') from None
        if isinstance(width_target_pp,bool) or not 0 <= width_value <= 100:
            raise ValueError('width_target_pp must lie in [0,100]')
    if width_target_pp is not None and method != 'range-hunter':
        raise ValueError('width_target_pp stopping is currently supported by range-hunter only')
    if method == 'range-hunter':
        from .hunter_population import hunter_population
        return hunter_population(problems, confidence_level=confidence_level,
            time_limit_seconds=time_limit_seconds, tolerance_pp=tolerance_pp,
            include_intervals=include_intervals, width_target_pp=width_target_pp)
    if method == 'range-calibrated':
        from .range_population import range_population
        return range_population(problems, confidence_level=confidence_level,
            time_limit_seconds=time_limit_seconds, tolerance_pp=tolerance_pp,
            include_intervals=include_intervals)
    start = monotonic()
    m = k-1
    alpha_exact = Fraction(1)-Fraction.from_float(float(confidence_level))
    matrices = [_prefix_distances(p) for p in problems.values()]
    pairs = [(0, b) for b in range(1, k)]+[(a, a+1) for a in range(k)]
    if include_intervals:
        pairs += [(a, b) for a in range(k) for b in range(a+1, k+1)]
    base_lo, base_hi, base_inner_lo, base_inner_hi = _compatible_prefix_projections(
        matrices, n, k, alpha_exact/m, pairs, witnesses=method == 'bonferroni')
    lower, upper = base_lo[:m], base_hi[:m]
    def bounds(l,u):
        lo,hi = _functional_bounds(l,u)
        if include_intervals:
            il,iu = _interval_vectors(l,u)
            return np.r_[lo,il], np.r_[hi,iu]
        return lo,hi
    def values(f):
        v = _functional_values(f)
        if include_intervals:
            il,iu = _interval_vectors(f,f,outward=False)
            return np.r_[v,il], np.r_[v,iu]
        return v,v
    baseline_seconds = monotonic()-start
    result = dict(requested_method=method, method=method, confidence_level=confidence_level,
                  constraint_signature=_constraint_signature(problems),
                  family_size=m, sample_size=n, numerical_tolerance_pp=tolerance_pp,
                  bounds_kind='conservative_outer', status='complete', precision_reached=False,
                  baseline_cdf_bounds=np.column_stack((lower, upper)).tolist(),
                  baseline_category_bounds=np.column_stack((base_lo[m:m+k], base_hi[m:m+k])).tolist(),
                  cdf_bounds=np.column_stack((lower, upper)).tolist(),
                  category_bounds=np.column_stack((base_lo[m:m+k], base_hi[m:m+k])).tolist(),
                  guarantee='Simultaneous finite-sample coverage under iid sampling on the fixed recorded panel; no within-category reconstruction.',
                  numerical_certificate='Compatible-prefix projections with CP endpoints bracketed by directed binomial tails; parameter-box exclusions use outward Decimal probabilities.',
                  box_count=0, excluded_boxes=0, elapsed_seconds=baseline_seconds,
                  baseline_seconds=baseline_seconds, refinement_seconds=0.,
                  time_limit_scope='optional_joint_refinement', question_certificates=[])
    if method == 'bonferroni':
        if include_intervals:
            _attach_intervals(result,k,base_lo[m+k:],base_hi[m+k:],
                              base_inner_lo[m+k:],base_inner_hi[m+k:])
        gap = max(float(np.max(np.nextafter(base_inner_lo-base_lo, np.inf))),
                  float(np.max(np.nextafter(base_hi-base_inner_hi, np.inf))), 0.)
        result['precision_reached'] = bool(isfinite(gap) and
            Fraction.from_float(gap) <= Fraction.from_float(float(tolerance_pp))/100)
        result['endpoint_gap_pp'] = float(np.nextafter(100*gap,np.inf)) if isfinite(gap) else None
        if not result['precision_reached']:
            result.update(status='precision_unresolved',
                          reason='Compatible-prefix outer bounds retained; endpoint precision is not certified.')
        return result
    if include_intervals:
        _attach_intervals(result,k,base_lo[m+k:],base_hi[m+k:])
    if n > 25000 or k > 13:
        result.update(status='unavailable', method='bonferroni', reason='Joint search currently supports at most 25000 observations and 13 categories; baseline retained.')
        return result
    refinement_start = monotonic()
    deadline = refinement_start+time_limit_seconds
    witness_lo, witness_hi = np.full(len(base_lo), np.inf), np.full(len(base_lo), -np.inf)
    tolerance_exact = Fraction.from_float(float(tolerance_pp))/100
    tolerance = float(np.nextafter(float(tolerance_exact), -np.inf))
    heap = [(-1., 0, lower, upper)]
    finished = []
    serial = 0
    active = None
    unresolved_small = 0
    def endpoint_gap(a, b):
        return max(float(np.max(np.nextafter(witness_lo-a, np.inf))),
                   float(np.max(np.nextafter(b-witness_hi, np.inf))), 0.)
    def remember(f):
        vl,vu = values(f)
        np.minimum(witness_lo, np.minimum(1., np.nextafter(vl, np.inf)), out=witness_lo)
        np.maximum(witness_hi, np.maximum(0., np.nextafter(vu, -np.inf)), out=witness_hi)
    try:
        _check_time(deadline)
        if questions:
            from .population_questions import certify_questions
            result['question_certificates'] = certify_questions(n,matrices,lower,upper,questions,
                alpha=alpha_exact,deadline=refinement_start+time_limit_seconds/2,bound=_box_upper)
            for certificate in result['question_certificates']:
                certificate.update(method='joint-exact',constraint_signature=result['constraint_signature'],
                    confidence_level=confidence_level)
            result['question_search_seconds'] = monotonic()-refinement_start
        for p in problems.values():
            _check_time(deadline)
            h = p.bounds(np.zeros(k))[0].histogram
            f = np.cumsum(h, dtype=float)[:-1]/n
            # Verify the actual binary64 witness, rather than assuming an
            # exactly representable rational empirical distribution.
            if Fraction.from_float(_point_lower(n, matrices, f, deadline)) >= alpha_exact:
                remember(f)
        while heap:
            _check_time(deadline)
            active = heappop(heap)
            _, _, l, u = active
            box_lo, box_hi = bounds(l, u)
            if endpoint_gap(box_lo, box_hi) <= tolerance:
                finished.append((l, u)); active = None
                continue
            result['box_count'] += 1
            if Fraction.from_float(_box_upper(n, matrices, l, u, deadline, reject_below=alpha_exact)) < alpha_exact:
                result['excluded_boxes'] += 1
                active = None
                continue
            middle = (l+u)/2
            if Fraction.from_float(_point_lower(n, matrices, middle, deadline)) >= alpha_exact:
                remember(middle)
            # Exact discrete tests can retain isolated parameter values at ties.
            # Do not starve other frontiers by bisecting such a box to machine
            # precision. It remains in the outer cover, never an accepted point.
            if np.max(np.nextafter(u-l, np.inf)) <= tolerance/4:
                unresolved_small += 1
                finished.append((l, u)); active = None
                continue
            dimension = int(np.argmax(u-l))
            cut = float(middle[dimension])
            if cut == l[dimension] or cut == u[dimension]:
                finished.append((l, u)); active = None
                continue
            for right in (False, True):
                ll, uu = l.copy(), u.copy()
                if right:
                    ll[dimension] = cut
                else:
                    uu[dimension] = cut
                ll = np.maximum.accumulate(ll)
                uu = np.minimum.accumulate(uu[::-1])[::-1]
                if np.any(ll > uu):
                    continue
                a, b = bounds(ll, uu)
                gap = endpoint_gap(a, b)
                serial += 1
                heappush(heap, (-gap, serial, ll, uu))
            active = None
    except TimeoutError:
        result['status'] = 'time_limit'
        result['reason'] = 'Time limit reached; all unresolved parameter boxes retained.'
    except (ArithmeticError, RuntimeError, MemoryError) as exc:
        # A probability calculation failure cannot turn an uncertain box into
        # a rejected box. Retain it with a readable diagnostic.
        result['status'] = 'unavailable'
        result['reason'] = f'Optional joint calculation stopped; conservative bounds retained: {exc}'
    leaves = finished+[(l, u) for _, _, l, u in heap]
    if active is not None:
        leaves.append((active[2], active[3]))
    if not leaves:
        # Empty output would contradict the empirical-distribution witness.
        # Treat a numerical inconsistency as a failed optional calculation.
        result.update(status='unavailable', reason='No retained parameter boxes; baseline retained.')
        out_lo, out_hi = base_lo, base_hi
    else:
        boxes = [bounds(l, u) for l, u in leaves]
        out_lo = np.maximum(base_lo, np.min([a for a, _ in boxes], axis=0))
        out_hi = np.minimum(base_hi, np.max([b for _, b in boxes], axis=0))
    result['cdf_bounds'] = np.column_stack((out_lo[:m], out_hi[:m])).tolist()
    result['category_bounds'] = np.column_stack((out_lo[m:m+k], out_hi[m:m+k])).tolist()
    if include_intervals:
        _attach_intervals(result,k,out_lo[m+k:],out_hi[m+k:],witness_lo[m+k:],witness_hi[m+k:])
    gap = endpoint_gap(out_lo, out_hi)
    result['precision_reached'] = bool(gap <= tolerance)
    if result['status'] == 'complete' and not result['precision_reached']:
        result.update(status='precision_unresolved', reason='Small unresolved parameter boxes remain; outer bounds are valid but endpoint precision is not certified.')
    result['unresolved_small_boxes'] = unresolved_small
    result['endpoint_gap_pp'] = None if not np.all(np.isfinite(witness_lo)) else float(np.nextafter(100*gap, np.inf))
    result['elapsed_seconds'] = monotonic()-start
    result['refinement_seconds'] = monotonic()-refinement_start
    return result


def _cohere_projections(result):
    """Propagate bounds for the same region through exact CDF differences.

    Every known bound constrains F[b]-F[a]. Shortest-path closure combines
    only these valid constraints, never confidence regions from other tests.
    Fractions avoid inward rounding when adding/subtracting saved endpoints.
    """
    k = len(result['category_bounds'])
    distance = [[Fraction(int(a < b)) for b in range(k+1)] for a in range(k+1)]
    distance[k][0] = Fraction(-1)
    def constrain(a, b, low, high):
        if not (isfinite(low) and isfinite(high) and 0 <= low <= high <= 1):
            raise ValueError('Invalid population projection bounds')
        distance[a][b] = min(distance[a][b], Fraction(high))
        distance[b][a] = min(distance[b][a], -Fraction(low))
    for b, (low, high) in enumerate(result['cdf_bounds'], 1):
        constrain(0, b, low, high)
    for a, (low, high) in enumerate(result['category_bounds']):
        constrain(a, a+1, low, high)
    for row in result.get('interval_bounds', []):
        constrain(row['start_index'], row['stop_index'], row['lower'], row['upper'])
    for middle in range(k+1):
        for a in range(k+1):
            for b in range(k+1):
                distance[a][b] = min(distance[a][b], distance[a][middle]+distance[middle][b])
    if any(distance[a][a] < 0 for a in range(k+1)):
        raise ValueError('Saved population projections conflict with the updated calculation')
    def outward(value, up):
        x = float(value)
        if (Fraction(x) < value if up else Fraction(x) > value):
            x = float(np.nextafter(x, np.inf if up else -np.inf))
        return x
    def bounds(a, b):
        return [outward(-distance[b][a], False), outward(distance[a][b], True)]
    result['cdf_bounds'] = [bounds(0, b) for b in range(1, k)]
    result['category_bounds'] = [bounds(a, a+1) for a in range(k)]
    for row in result.get('interval_bounds', []):
        row['lower'], row['upper'] = bounds(row['start_index'], row['stop_index'])
        if row['inner_lower'] is not None and not row['lower'] <= row['inner_lower'] <= row['inner_upper'] <= row['upper']:
            row.update(inner_lower=None, inner_upper=None)


def update_population_distribution(previous_problems, problems, previous_result, **options):
    """Refine the same sample while preserving its saved numerical outer bounds.

    The original constraints must literally remain present; a caller changing a
    panel, denominator, variant interpretation or confidence level must start a
    separate analysis. This explicit contract avoids combining unrelated 95%
    intervals after seeing their results.
    """
    _validate(previous_problems)
    _validate(problems)
    if previous_result.get('constraint_signature') != _constraint_signature(previous_problems):
        raise ValueError('Saved result does not match the previous reporting constraints')
    if not set(problems).issubset(previous_problems):
        raise ValueError('An update must retain the original reporting interpretations')
    for name, new in problems.items():
        old = previous_problems[name]
        if new.n != old.n or new.panel != old.panel:
            raise ValueError('An update must retain the original denominator and panel')
        def rows(p):
            matrix, lo, hi = p.linear_constraints
            return {(tuple(row), float(a), float(b)) for row, a, b in zip(matrix, lo, hi)}
        if not rows(old).issubset(rows(new)):
            raise ValueError('An update must retain every original constraint and add only truthful counts')
    confidence = previous_result['confidence_level']
    if 'confidence_level' in options and options['confidence_level'] != confidence:
        raise ValueError('An update must retain the original confidence level')
    options['confidence_level'] = confidence
    options.setdefault('method', previous_result['requested_method'])
    if options['method'] != previous_result['requested_method']:
        raise ValueError('An update must retain the original population method')
    current = population_distribution(problems, **options)
    for key in ('cdf_bounds', 'category_bounds'):
        old = np.asarray(previous_result[key], dtype=float)
        new = np.asarray(current[key], dtype=float)
        if old.shape != new.shape or not np.all(np.isfinite(old)) or np.any(old < 0) or np.any(old > 1) or np.any(old[:, 0] > old[:, 1]):
            raise ValueError('Saved population bounds are invalid')
        new[:, 0] = np.maximum(old[:, 0], new[:, 0])
        new[:, 1] = np.minimum(old[:, 1], new[:, 1])
        if np.any(new[:, 0] > new[:, 1]):
            raise ValueError('Saved population bounds conflict with the updated calculation')
        current[key] = new.tolist()
    if 'interval_bounds' in current and 'interval_bounds' in previous_result:
        saved = {(r['start_index'],r['stop_index']):r for r in previous_result['interval_bounds']}
        for row in current['interval_bounds']:
            old = saved.get((row['start_index'],row['stop_index']))
            if old is None or not all(isfinite(old[s]) for s in ('lower','upper')) or not 0 <= old['lower'] <= old['upper'] <= 1:
                raise ValueError('Saved population interval bounds are invalid')
            row['lower'] = max(row['lower'],old['lower'])
            row['upper'] = min(row['upper'],old['upper'])
            if row['lower'] > row['upper']:
                raise ValueError('Saved population interval bounds conflict with the updated calculation')
            # Only current accepted witnesses survive an information update.
            if row['inner_lower'] is not None and not row['lower'] <= row['inner_lower'] <= row['inner_upper'] <= row['upper']:
                row.update(inner_lower=None,inner_upper=None)
    _cohere_projections(current)
    if current['requested_method'] == 'range-hunter':
        from .hunter_population import refresh_projection_metadata
        refresh_projection_metadata(current)
    current['previous_outer_bounds_preserved'] = True
    return current
