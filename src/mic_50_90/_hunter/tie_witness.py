"""Algebraic membership witnesses at inclusive-score ties.

The law is specified by a monotone polynomial root, not by a rounded point.
All stored endpoint bounds enclose that same exact law.
"""
from fractions import Fraction as F

from .pairwise import _binomial_masses,exact_binomial_scores,range_family,_check_deadline


def _tail(n,c,q,right):
    masses=_binomial_masses(n,q)
    return sum(masses[c:] if right else masses[:c+1],F(0))


def tied_witness(histogram,group_e,group_f,u,alpha=F(1,20),*,root_bits=48,deadline=None):
    """Certify a left-tail/right-tail tie on two disjoint MIC ranges.

    E has probability u. F has the unique probability v satisfying
    P[Bin(n,v)>=h_F]=P[Bin(n,u)<=h_E]. Within each group the probability
    is allocated in the empirical proportions, or equally for a zero count.
    E/F must each be a contiguous range or its complement, as used by the
    fixed score family. No external distributional assumption is introduced.
    """
    h=tuple(histogram);n=sum(h);k=len(h);e=set(group_e);f=set(group_f)
    if n<1 or any(not isinstance(c,int) or c<0 for c in h):raise ValueError('invalid histogram')
    if not e or not f or e&f or not e|f<=set(range(k)):raise ValueError('groups must be nonempty and disjoint')
    rest=set(range(k))-e-f
    if not rest:raise ValueError('a remaining probability group is required')
    for group in (e,f):
        complement=set(range(k))-group
        if sorted(group)!=list(range(min(group),max(group)+1)) and sorted(complement)!=list(range(min(complement),max(complement)+1)):
            raise ValueError('selected event must belong to the fixed range/complement family')
    u=F(u);alpha=F(alpha)
    if not 0<u<1 or not 0<alpha<1:return None
    ce=sum(h[j] for j in e);cf=sum(h[j] for j in f)
    if ce==n or cf==0:return None
    _check_deadline(deadline)
    tau=_tail(n,ce,u,False)
    if not 0<tau<=F(1,2):return None
    l,v=F(0),1-u
    if _tail(n,cf,v,True)<tau:return None
    for _ in range(root_bits):
        _check_deadline(deadline)
        mid=(l+v)/2
        if _tail(n,cf,mid,True)<tau:l=mid
        else:v=mid
    intercept=[F(0)]*k;coefficient=[F(0)]*k
    for group,base,slope in ((e,u,F(0)),(f,F(0),F(1)),(rest,1-u,F(-1))):
        total=sum(h[j] for j in group)
        for j in group:
            weight=F(h[j],total) if total else F(1,len(group))
            intercept[j]=base*weight;coefficient[j]=slope*weight
    t=2*tau
    checked=[]
    for a,b in range_family(k):
        _check_deadline(deadline)
        A=sum(intercept[a:b]);B=sum(coefficient[a:b]);c=sum(h[a:b])
        # Exact equality tags, including duplicate/complement events created
        # by zero-probability categories, survive arbitrarily narrow roots.
        tags=((u,F(0),ce),(1-u,F(0),n-ce),(F(0),F(1),cf),(F(1),F(-1),n-cf))
        if (A,B,c) in tags:
            checked.append((a,b,'exact active score'));continue
        qlo=min(A+B*l,A+B*v);qhi=max(A+B*l,A+B*v)
        if min(exact_binomial_scores(n,qlo)[c],exact_binomial_scores(n,qhi)[c])<t:
            return None
        checked.append((a,b,'interval lower score'))
    # Conditional on X_E=i, X_F is Bin(n-i,v/(1-u)). This joint event
    # probability increases with v, so evaluating at the root upper bound
    # gives an exact rational upper bound on its true value.
    masses=_binomial_masses(n,u)
    intersection=F(0)
    for i in range(ce+1):
        _check_deadline(deadline)
        if cf<=n-i:intersection+=masses[i]*_tail(n-i,cf,v/(1-u),True)
    union_lower=2*tau-intersection
    if union_lower<alpha:return None
    lower=tuple(min(A+B*l,A+B*v) for A,B in zip(intercept,coefficient))
    upper=tuple(max(A+B*l,A+B*v) for A,B in zip(intercept,coefficient))
    assert min(lower)>=0 and sum(lower)<=1<=sum(upper)
    return dict(histogram=h,group_e=tuple(sorted(e)),group_f=tuple(sorted(f)),u=u,
        root_lower=l,root_upper=v,tail_probability=tau,union_lower=union_lower,
        lower=lower,upper=upper,intercept=tuple(intercept),coefficient=tuple(coefficient),
        range_score_checks=checked,
        semantics='One exact algebraic population law, enclosed coordinatewise; not all points in the box')


def witness_range(record,a,b):
    if 'coefficients' in record:
        from .multiple_roots import projection
        return projection(record,a,b)
    A=sum(record['intercept'][a:b]);B=sum(record['coefficient'][a:b])
    values=(A+B*record['root_lower'],A+B*record['root_upper'])
    return min(values),max(values)
