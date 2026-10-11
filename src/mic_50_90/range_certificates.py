"""Population endpoint certificates and disjoint integer report partitions.

All witnesses are sufficient certificates. Failure to certify a chosen point
is not an exclusion of its face or of other population distributions.
"""
from fractions import Fraction as F
from time import monotonic


def binomial_shape_certificate(n, cutoff, deadline):
    """Sufficient precondition for the population row-lift theorem.

    Certify discrete concavity of the exact upper endpoint sequence by inward
    and outward brackets. An unresolved comparison makes no shape assertion.
    """
    from .joint_population import _cp_inner, _cp_outer
    lower, upper = [], []
    for x in range(n+1):
        if monotonic() >= deadline:
            return dict(status='unresolved', reason='Shape certificate time limit')
        inside = _cp_inner(x,n,cutoff)
        if inside is None:
            return dict(status='unresolved', reason='An inward endpoint was not certified')
        lower.append(F(inside[1]))
        upper.append(F(_cp_outer(x,n,cutoff)[1]))
    margins = [2*lower[x]-upper[x-1]-upper[x+1] for x in range(1,n)]
    if any(m < 0 for m in margins):
        return dict(status='unresolved', reason='Discrete concavity was not certified')
    return dict(status='certified', n=n, critical_score_fraction=str(cutoff),
        minimum_concavity_margin=str(min(margins)) if margins else None,
        claim='At most K distinct histograms from K+1 indexed count rows attain all contiguous population projection endpoints in each reporting variant; no equality of full regions is claimed')


def close_counts(d):
    """Close finite integer difference bounds without floating arithmetic."""
    d = [[int(v) for v in row] for row in d]
    for via in range(len(d)):
        for a in range(len(d)):
            for b in range(len(d)):
                d[a][b] = min(d[a][b], d[a][via]+d[via][b])
    return None if any(d[a][a] < 0 for a in range(len(d))) else d


def split_count_cell(d):
    """Split one cumulative integer coordinate into exhaustive disjoint parts."""
    k = len(d)-1
    width, j = max((d[0][i]+d[i][0], i) for i in range(1,k))
    if width == 0:
        return []
    midpoint = (d[0][j]-d[j][0])//2
    left, right = [r[:] for r in d], [r[:] for r in d]
    left[0][j] = min(left[0][j], midpoint)
    right[j][0] = min(right[j][0], -midpoint-1)
    return [c for c in (close_counts(left), close_counts(right)) if c is not None]


def compatible_probability_witness(d, probabilities, cutoff, deadline):
    """Return a certified compatible accepted histogram, or no certificate.

    Directed binomial tails bracket rational range probabilities. Their lower
    bounds authorize integer acceptance bands. Closing their intersection with
    the report is exact. A numerical equality may remain uncertified.
    """
    from .joint_population import _binomial_tails
    from .range_population import _rounded
    p = tuple(F(x) for x in probabilities)
    if any(x < 0 for x in p) or sum(p) != 1:
        raise ValueError('Probability certificate must lie in the simplex')
    k, n = len(p), int(d[0][-1])
    accepted = [list(map(int,row)) for row in d]
    half = F(cutoff)/2
    for a in range(k):
        for b in range(a+1,k):
            if monotonic() >= deadline:
                raise TimeoutError('Probability certificate time limit; no exclusion follows')
            q = sum(p[a:b])
            cdf, _, _, _ = _binomial_tails(n, _rounded(q, True))
            _, _, sf, _ = _binomial_tails(n, _rounded(q, False))
            allowed = [x for x in range(n+1) if F(cdf[x]) >= half and F(sf[x]) >= half]
            if not allowed:
                return None
            if allowed != list(range(allowed[0],allowed[-1]+1)):
                return None
            accepted[a][b] = min(accepted[a][b], allowed[-1])
            accepted[b][a] = min(accepted[b][a], -allowed[0])
    accepted = close_counts(accepted)
    if accepted is None:
        return None
    return tuple(accepted[0][j+1]-accepted[0][j] for j in range(k))
