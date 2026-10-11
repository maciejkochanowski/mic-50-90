from time import monotonic
import numpy as np
from .pairwise import (CalibrationResult, ONE, ProbabilityBounds, ZERO, _binomial_masses, _check_deadline, _integer, _membership, _moment_lp, _probabilities, _sum_out, _threshold, _tree, exact_binomial_scores, range_family)
from .fast_pairs import exact as pair_count_distribution_exact, bounds as pair_count_distribution_bounds

def pair_event_probability(n,p,e,f,t,*,exact=False,deadline=None):
    """Bounds on P(b_e(X_e)<=t, b_f(X_f)<=t) under iid categories."""
    n, p, t = _integer(n,"n",1),_probabilities(p),_threshold(t)
    for a,b in (e,f):
        if not 0 <= a < b <= len(p):
            raise ValueError("invalid event range")
    allow_e = [c for c,x in enumerate(exact_binomial_scores(n,sum(p[e[0]:e[1]]))) if x <= t]
    allow_f = [c for c,x in enumerate(exact_binomial_scores(n,sum(p[f[0]:f[1]]))) if x <= t]
    if not allow_e or not allow_f:
        return ProbabilityBounds(ZERO,ZERO)
    q = _membership(p,e,f)
    _check_deadline(deadline)
    if exact:
        cells = pair_count_distribution_exact(n,q)
        value = sum((cells[a][b] for a in allow_e for b in allow_f),ZERO)
        return ProbabilityBounds(value,value)
    low,high = pair_count_distribution_bounds(n,q,deadline=deadline)
    selected = np.ix_(allow_e,allow_f)
    return ProbabilityBounds(_sum_out(low[selected],False),_sum_out(high[selected],True))


def calibrate(n,p,t,*,use_lp=True,exact=False,deadline=None):
    """Certified upper bound for G_p(t)=P(min_e b_e(X_e)<=t).

    Marginals and score-event classification are rational-exact. Pair cells
    use outward binary64 or the optional exact integer kernel. An exhausted
    pair budget uses zero lower intersections, preserving a valid tree bound.
    """
    n,p,t = _integer(n,"n",1),_probabilities(p),_threshold(t)
    ranges = range_family(len(p))
    if t == 1:
        certain = ProbabilityBounds(ONE,ONE)
        pairs = {(i,j):certain for i in range(len(ranges)) for j in range(i+1,len(ranges))}
        edges = tuple((0,j) for j in range(1,len(ranges)))
        return CalibrationResult(t,ONE,ONE,ONE,(certain,)*len(ranges),pairs,edges,
                                 None,"analytic union probability one; LP unnecessary",len(pairs),len(pairs))
    marginals = []
    for a,b in ranges:
        # One exact rational table is a noninterruptible work unit.
        # Expiry prevents starting a subsequent unit; see MATHEMATICS.md.
        if deadline is not None and monotonic() >= deadline:
            missing = len(ranges)-len(marginals)
            marginals.extend(ProbabilityBounds(ZERO,ONE) for _ in range(missing))
            break
        q = sum(p[a:b])
        value = sum((mass for mass,score in zip(_binomial_masses(n,q),exact_binomial_scores(n,q)) if score <= t),ZERO)
        marginals.append(ProbabilityBounds(value,value))
    pairs,completed = {},0
    for i,e in enumerate(ranges):
        for j in range(i+1,len(ranges)):
            try:
                if marginals[i].upper == 0 or marginals[j].upper == 0:
                    pairs[i,j] = ProbabilityBounds(ZERO,ZERO)
                    completed += 1
                    continue
                _check_deadline(deadline)
                intersection = pair_event_probability(n,p,e,ranges[j],t,exact=exact,deadline=deadline)
                # Intersect independent certified bounds with the marginal cap.
                cap = min(marginals[i].upper,marginals[j].upper)
                pairs[i,j] = ProbabilityBounds(intersection.lower,min(cap,intersection.upper))
                completed += 1
            except TimeoutError:
                pairs[i,j] = ProbabilityBounds(ZERO,min(marginals[i].upper,marginals[j].upper))
    total_marginal = sum((x.upper for x in marginals),ZERO)
    bonferroni = min(ONE,total_marginal)
    edges,weight = _tree(len(ranges),pairs)
    hunter = min(bonferroni,max(ZERO,total_marginal-weight))
    moments = (*marginals,*(pairs[key] for key in sorted(pairs)))
    certificate,lp_status = _moment_lp(len(ranges),moments,deadline) if use_lp else (None,"disabled")
    bound = min(hunter,certificate.upper_bound) if certificate is not None else hunter
    return CalibrationResult(t,bonferroni,hunter,bound,tuple(marginals),pairs,edges,
                             certificate,lp_status,completed,len(pairs))

