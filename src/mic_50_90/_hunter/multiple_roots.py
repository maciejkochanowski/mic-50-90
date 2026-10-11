"""Certified membership at several simultaneous inclusive-score ties.

Coordinates are affine functions of shared algebraic roots. The certificate
describes one normalized law, not an arbitrary point in an enclosing box.
Selected-event integer dynamic programming supplies a null-probability lower
bound. Small enumerations can supply a stronger lower bound when necessary.
"""
from fractions import Fraction as F
from functools import lru_cache
from math import comb, factorial, lcm, prod

from .pairwise import _check_deadline, _integer_binomial, range_family


@lru_cache(maxsize=64)
def cumulative(n, q):
    weights, denominator = _integer_binomial(n, F(q))
    total, rows = 0, []
    for weight in weights:
        _check_deadline(None)
        total += weight
        rows.append(total)
    return tuple(rows), denominator


def cdf(n, c, q):
    rows, denominator = cumulative(n, q)
    return F(rows[c], denominator)


def sf(n, c, q):
    rows, denominator = cumulative(n, q)
    return F(denominator-(rows[c-1] if c else 0), denominator)


@lru_cache(maxsize=512)
def root(n, c, tau):
    lo, hi = F(0), F(1)
    for _ in range(44):
        _check_deadline(None)
        mid = (lo+hi)/2
        if sf(n,c,mid) < tau:
            lo = mid
        else:
            hi = mid
    return lo, hi


def affine_bounds(intercept, coefficients, roots):
    lo = hi = F(intercept)
    for weight, (a,b) in zip(coefficients, roots):
        lo += weight*(a if weight>=0 else b)
        hi += weight*(b if weight>=0 else a)
    return lo, hi


def projection(record, a, b):
    roots = tuple(tuple(map(F,row)) for row in record['roots'])
    intercept = sum(map(F,record['intercept'][a:b]))
    coefficients = tuple(sum(row[i] for row in record['coefficients'][a:b])
                         for i in range(len(roots)))
    return affine_bounds(intercept,coefficients,roots)


def _group_masses(n, weights, limits):
    dp = [0]*(n+1)
    dp[0] = 1
    for weight, limit in zip(weights,limits):
        _check_deadline(None)
        powers = []
        for j in range(min(n,limit)+1):
            _check_deadline(None)
            powers.append(weight**j)
        out = [0]*(n+1)
        for m in range(n+1):
            _check_deadline(None)
            out[m] = sum(comb(m,c)*powers[c]*dp[m-c]
                         for c in range(min(m,limit)+1) if dp[m-c])
        dp = out
    return dp


def lower_union(n, probability_lower, assignments, group, count_limit):
    """Exact lower-weight mass of group-low OR assigned-category-high events."""
    _check_deadline(None)
    p = tuple(map(F,probability_lower))
    group = set(group)
    if n<1 or min(p)<0 or sum(p)>1 or not 0<=count_limit<=n:
        raise ValueError('Invalid lower-weight model')
    denominator = lcm(*(v.denominator for v in p))
    weights = tuple(int(v*denominator) for v in p)
    caps = [assignments.get(j,0)-1 if assignments.get(j,0)>0 else n
            for j in range(len(p))]
    inside = [j for j in range(len(p)) if j in group]
    outside = [j for j in range(len(p)) if j not in group]
    a = _group_masses(n,[weights[j] for j in inside],[caps[j] for j in inside])
    b = _group_masses(n,[weights[j] for j in outside],[caps[j] for j in outside])
    complement = 0
    for c in range(count_limit+1,n+1):
        _check_deadline(None)
        complement += comb(n,c)*a[c]*b[n-c]
    numerator = sum(weights)**n-complement
    if numerator<0:
        raise ArithmeticError('Invalid event-union recurrence')
    return F(numerator,denominator**n)


def _histograms(n,k):
    _check_deadline(None)
    if k==1:
        yield (n,)
    else:
        for x in range(n+1):
            for tail in _histograms(n-x,k-1):
                yield (x,)+tail


def certify(h, dominant, u, residual, assignments, alpha=F(1,20), *, group=None):
    """Return a verified inner law, or no certificate; never reject a law."""
    _check_deadline(None)
    h = tuple(h)
    if not h or any(isinstance(c,bool) or int(c)!=c or c<0 for c in h):
        raise ValueError('Invalid histogram')
    h = tuple(map(int,h))
    n, k = sum(h), len(h)
    u, alpha = F(u), F(alpha)
    if n<1 or not 0<alpha<1:
        raise ValueError('Invalid histogram or confidence level')
    group = {dominant} if group is None else set(group)
    if dominant not in group or residual in group or not group<=set(range(k)) or residual not in range(k):
        raise ValueError('Invalid fixed-mass group')
    ce = sum(h[j] for j in group)
    if not 0<u<1 or ce==n:
        return None
    assignments = dict(assignments)
    if set(assignments) != set(range(k))-{dominant,residual}:
        raise ValueError('Missing assigned category')
    if any(isinstance(c,bool) or int(c)!=c or not 0<=c<=n for c in assignments.values()):
        raise ValueError('Invalid tail count')
    assignments = {j:int(c) for j,c in assignments.items()}
    complement = set(range(k))-group
    if (sorted(group)!=list(range(min(group),max(group)+1)) and
        sorted(complement)!=list(range(min(complement),max(complement)+1))):
        return None
    tau = cdf(n,ce,u)
    if not 0<tau<F(1,2):
        return None
    labels = tuple(sorted({c for c in assignments.values() if c}))
    roots = tuple(root(n,c,tau) for c in labels)
    A, B = [F(0)]*k, [[0]*len(labels) for _ in range(k)]
    A[dominant], A[residual] = u, 1-u
    for j,c in assignments.items():
        if c:
            index = labels.index(c)
            B[j][index] = 1
            B[dominant if j in group else residual][index] -= 1
    bounds = [affine_bounds(a,b,roots) for a,b in zip(A,B)]
    if any(lo<0 or hi>1 for lo,hi in bounds):
        return None
    family, events, score_checks = range_family(k), [], []
    for a,b in family:
        _check_deadline(None)
        intercept = sum(A[a:b])
        coefficients = tuple(sum(row[i] for row in B[a:b]) for i in range(len(labels)))
        qlo,qhi = affine_bounds(intercept,coefficients,roots)
        observed, tags, exact_observed = sum(h[a:b]), set(), False
        for i,c in enumerate(labels):
            unit = tuple(int(j==i) for j in range(len(labels)))
            if intercept==0 and coefficients==unit:
                tags.update(range(c,n+1))
                exact_observed |= observed==c
            if intercept==1 and coefficients==tuple(-x for x in unit):
                tags.update(range(n-c+1))
                exact_observed |= observed==n-c
        if not exact_observed and min(cdf(n,observed,qhi),sf(n,observed,qlo))<tau:
            return None
        score_checks.append(dict(range=[a,b],exact_tag=exact_observed))
        allowed = []
        for c in range(n+1):
            _check_deadline(None)
            if c in tags or min(cdf(n,c,qlo),sf(n,c,qhi))<=tau:
                allowed.append(c)
        events.append(tuple(allowed))
    lower = lower_union(n,[v[0] for v in bounds],assignments,group,ce)
    union_method = 'selected_root_events_dp'
    # Enumeration is only a stronger inner certificate for affordable cases.
    # Exceeding this cap never changes the outer confidence region.
    if lower<alpha and comb(n+k-1,k-1)<=3000:
        lower = F(0)
        for null_h in _histograms(n,k):
            if any(sum(null_h[a:b]) in allowed for (a,b),allowed in zip(family,events)):
                coefficient = factorial(n)//prod(factorial(x) for x in null_h)
                lower += coefficient*prod(lo**x for (lo,hi),x in zip(bounds,null_h))
        union_method = 'all_score_events_enumerated'
    if lower<alpha:
        return None
    return dict(union_method=union_method,histogram=list(h),group=sorted(group),
        dominant=dominant,u=str(u),residual=residual,
        assignments={str(j):c for j,c in assignments.items()},root_counts=list(labels),
        roots=[list(map(str,x)) for x in roots],tau=str(tau),
        intercept=list(map(str,A)),coefficients=B,
        probability_bounds=[list(map(str,x)) for x in bounds],union_lower=str(lower),
        events=[list(x) for x in events],observed_score_checks=score_checks,
        semantics='One normalized algebraic law sharing root variables, not every point in its coordinate box')


def proposals(histograms, initial, alpha):
    """Search shared-score laws; every yielded proposal has its own proof.

    Rare contiguous groups are visited first because their upper endpoints
    often occur at several simultaneous score ties. This order is a numerical
    search heuristic, not a population shape assumption or a rejection rule.
    """
    tasks = []
    for values in sorted(histograms):
        h = tuple(map(int,values))
        n,k = sum(h),len(h)
        seen = set()
        for a,b in range_family(k):
            for complement in (False,True):
                group = set(range(a,b))
                if complement:
                    group = set(range(k))-group
                key = tuple(sorted(group))
                if key in seen:
                    continue
                seen.add(key)
                count = sum(h[j] for j in group)
                if count==n:
                    continue
                high = 1+initial[b][a] if complement else initial[a][b]
                tasks.append((F(count,n),-len(group),h,key,F(high)))
    for low,_,h,key,high in sorted(tasks):
        _check_deadline(None)
        group,k,n = set(key),len(h),sum(h)
        inside = sorted(group)
        outside = sorted(set(range(k))-group)
        # Cover alternative allocations of the fixed group mass, including
        # an unobserved residual category. The data still enter every proof.
        dominant_order = list(dict.fromkeys([inside[len(inside)//2],inside[0],inside[-1]]))
        residual_order = list(dict.fromkeys([max(outside,key=lambda j:h[j]),min(outside,key=lambda j:h[j]),*outside]))
        specifications = []
        for dominant in dominant_order:
            for residual in residual_order:
                base = {j:max(1,h[j]) for j in range(k) if j not in (dominant,residual)}
                assignments = [base]
                for j,c in base.items():
                    if c<n:
                        assignments.append({**base,j:c+1})
                specifications.extend((dominant,residual,assignment) for assignment in assignments)
        # Visit all allocations at a coarse mass before polishing one.
        accepted = set()
        for step in range(16,0,-1):
            u = low+(high-low)*F(step,16)
            for index,(dominant,residual,assignment) in enumerate(specifications):
                _check_deadline(None)
                if index in accepted:
                    continue
                record = certify(h,dominant,u,residual,assignment,alpha,group=group)
                if record is None:
                    continue
                accepted.add(index)
                yield record
                left,right = u,low+(high-low)*F(step+1,16) if step<16 else high
                for _ in range(6):
                    _check_deadline(None)
                    mid = (left+right)/2
                    if mid==left:
                        break
                    refined = certify(h,dominant,mid,residual,assignment,alpha,group=group)
                    if refined is None:
                        right = mid
                    else:
                        left = mid
                        yield refined
