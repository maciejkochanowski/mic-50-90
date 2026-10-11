"""Closed-side certificates for questions about the fixed population region.

The full-distribution calculation is independent of this optional search. A
failed search cannot remove a box from its cover or alter its sampling model.
"""
from fractions import Fraction
from math import inf, nextafter
from time import monotonic

import numpy as np

from .validation import exact_integer


def _outward(value, up):
    result=float(value)
    if (Fraction(result)<value if up else Fraction(result)>value):
        result=nextafter(result,inf if up else -inf)
    return result


def certify_questions(n, matrices, lower, upper, questions, *, alpha, deadline, bound):
    """Exclude a closed counter-side using a uniform joint-p-value bound.

    ``bound`` is the existing directed parameter-box bound. All retained boxes,
    including exact equality and interruption, prevent an exclusion claim.
    The nearer outer endpoint chooses the side attempted, not a new test.
    """
    lower,upper=np.asarray(lower,float),np.asarray(upper,float)
    if lower.shape!=upper.shape or lower.ndim!=1 or not len(lower) or not np.all(np.isfinite([lower,upper])):
        raise ValueError('Invalid CDF question bounds')
    if np.any(lower<0) or np.any(upper>1) or np.any(lower>upper):
        raise ValueError('Invalid CDF question bounds')
    prepared=[]
    for question in questions:
        cut=exact_integer(question['cut_index'],'question cut',0)
        if cut>=len(lower):raise ValueError('Question cut must be an interior CDF boundary')
        q=Fraction(question['fraction'])
        if not 0<=q<=1:raise ValueError('Question fraction must lie in [0,1]')
        prepared.append((cut,q))
    results=[]
    for index,(cut,q) in enumerate(prepared):
        low,high=1-Fraction(upper[cut]),1-Fraction(lower[cut])
        if q<low or q>high:
            continue  # the existing bounds already settle the strict question
        # Reserve a share of the remaining question budget for every request.
        now=monotonic();local_deadline=now+max(0.,deadline-now)/(len(prepared)-index)
        relation='<' if high-q <= q-low else '>'
        l,u=lower.copy(),upper.copy();cut_value=1-q
        if relation=='<':u[cut]=min(u[cut],_outward(cut_value,True))
        else:l[cut]=max(l[cut],_outward(cut_value,False))
        l=np.maximum.accumulate(l);u=np.minimum.accumulate(u[::-1])[::-1]
        initial=dict(cdf_lower=l.tolist(),cdf_upper=u.tolist())
        queue=[] if np.any(l>u) else [(0,l,u)];active=None;leaves=[];trace=[];splits=[];visited=0;reason=None;serial=0
        try:
            while queue:
                if monotonic()>=local_deadline:raise TimeoutError('Question calculation budget reached')
                active=queue.pop();node,a,b=active;visited+=1
                value=bound(n,matrices,a,b,deadline=local_deadline,reject_below=alpha)
                if Fraction(float(value))<alpha:
                    trace.append(dict(node=node,cdf_lower=a.tolist(),cdf_upper=b.tolist(),pvalue_upper=float(value)))
                    active=None;continue
                dimension=int(np.argmax(b-a));mid=float((a[dimension]+b[dimension])/2)
                if mid==a[dimension] or mid==b[dimension]:
                    leaves.append(active);active=None;continue
                children=[]
                for right in (False,True):
                    ll,uu=a.copy(),b.copy()
                    if right:ll[dimension]=mid
                    else:uu[dimension]=mid
                    ll=np.maximum.accumulate(ll);uu=np.minimum.accumulate(uu[::-1])[::-1]
                    serial+=1
                    children.append(dict(node=serial,empty=bool(np.any(ll>uu))))
                    if np.all(ll<=uu):queue.append((serial,ll,uu))
                splits.append(dict(node=node,dimension=dimension,cut=mid,children=children))
                active=None
        except (TimeoutError,ArithmeticError,MemoryError,RuntimeError) as exc:
            reason=f'{type(exc).__name__}: {exc}'
        if active is not None:leaves.append(active)
        remaining=len(queue)+len(leaves)
        results.append(dict(cut_index=cut,fraction=str(q),tail_relation=relation,
            status='unresolved' if remaining else 'excluded',visited_boxes=visited,remaining_boxes=remaining,
            excluded_boxes=trace,splits=splits,initial_box=initial,reason=reason,
            alpha_fraction=str(alpha),sample_size=n,
            interpretation='Exclusion of the closed opposite side for the same joint population region; no endpoint tolerance or new statistical test.'))
    return results
