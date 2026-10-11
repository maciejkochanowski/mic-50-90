"""Certified endpoint search for the unchanged research confidence region.

Numerical proposal routines never authorize rejection or membership. Every
accepted point, excluded cell and displayed endpoint uses exact/outward bounds.
This internal kernel preserves the fixed monotone Hunter/moment target.
"""
from fractions import Fraction as F
from functools import lru_cache
from heapq import heappop,heappush
from math import isfinite,lcm
from time import monotonic
import numpy as np
from scipy.optimize import linprog
from scipy.linalg import qr
from .budget import bounded_calculation,deadline_scope

from .pairwise import (as_region,range_family,_feasible_histogram,_check_deadline,
    _binomial_masses,_score_envelopes,_max_from_scores,exact_binomial_scores,
    max_compatible_statistic,_tree,ProbabilityBounds,
    _sum_out,_moment_lp,_binomial_event_box)
from .calibration import calibrate
from .fast_pairs import box as pair_count_distribution_box_bounds
from .helpers import _union_lower,_float
from mic_50_90.joint_population import _cp_outer
from .tie_witness import tied_witness,witness_range
from .dense import direct_union,proposals as support_proposals
from .multiple_roots import proposals as multiple_root_proposals


@lru_cache(maxsize=16)
def _atom_matrix(m):
    masks=np.arange(1<<m,dtype=np.int64)
    bits=np.array([(masks>>i)&1 for i in range(m)],dtype=float)
    return np.vstack([np.ones(1<<m),bits,
        *[bits[i]*bits[j] for i in range(m) for j in range(i+1,m)]])


def _solve_exact(a,b):
    a=[list(map(F,row))+[F(value)] for row,value in zip(a,b)]
    n=len(b)
    for j in range(n):
        _check_deadline(None)
        pivot=next((i for i in range(j,n) if a[i][j]),None)
        if pivot is None:return None
        a[j],a[pivot]=a[pivot],a[j]
        q=a[j][j]
        a[j]=[v/q for v in a[j]]
        for i in range(n):
            if i!=j and a[i][j]:
                q=a[i][j]
                a[i]=[x-q*y for x,y in zip(a[i],a[j])]
    return tuple(row[-1] for row in a)


def moment_primal(m,moments,deadline=None):
    """Exact feasible atom weights lower-bound the true moment-LP optimum."""
    if m>12:return None
    _check_deadline(deadline)
    a=_atom_matrix(m)
    rhs=(F(1),*map(F,moments))
    if len(rhs)!=len(a):raise ValueError('wrong moment dimension')
    options={} if deadline is None else {'time_limit':max(.001,deadline-monotonic())}
    obj=np.ones(1<<m);obj[0]=0
    result=linprog(-obj,A_eq=a,b_eq=np.array(rhs,float),bounds=(0,None),
                   method='highs',options=options)
    if not result.success:return None
    columns=np.flatnonzero(result.x>0)
    if not len(columns) or len(columns)>len(rhs):return None
    _,_,pivots=qr(a[:,columns].T,pivoting=True,mode='economic')
    rows=pivots[:len(columns)]
    weights=_solve_exact(a[np.ix_(rows,columns)].astype(int).tolist(),[rhs[i] for i in rows])
    if weights is None or min(weights)<0:return None
    # All equations, including unused or rank-deficient rows, are mandatory.
    for row,value in zip(a,rhs):
        if sum((int(row[j])*w for j,w in zip(columns,weights)),F(0))!=value:return None
    return dict(patterns=tuple(map(int,columns)),weights=weights,
                objective=sum((w for j,w in zip(columns,weights) if j),F(0)))


def tail_upper(n,lo,hi,allowed):
    """Exact maximum for an outside-interval binomial event on [lo,hi]."""
    allowed=set(allowed)
    complement=[c for c in range(n+1) if c not in allowed]
    if complement and complement!=list(range(complement[0],complement[-1]+1)):
        raise ValueError('event must be the complement of a count interval')
    return max(sum((_binomial_masses(n,q)[c] for c in allowed),F(0)) for q in (lo,hi))


def certify_witness(region,p,alpha=F(1,20),deadline=None):
    """Certify membership in the fixed monotone Hunter/moment target.

    Check every attainable higher score until the true union lower bound
    exceeds alpha. Above that point monotonicity of the true CDF suffices.
    An unsuccessful certificate is unresolved, never a rejection certificate.
    """
    r=as_region(region);p=tuple(map(F,p));alpha=F(alpha)
    union=direct_union(r,p,alpha,deadline)
    if union is not None and union>=alpha:
        return dict(accepted=True,levels_checked=1,reason="exact enumerated true-union lower certificate")
    stat=max_compatible_statistic(r,p,deadline=deadline)
    levels=sorted({s for a,b in range_family(r.k)
        for s in exact_binomial_scores(r.n,sum(p[a:b])) if s>=stat.threshold})
    checked=0
    for t in levels:
        _check_deadline(deadline)
        result=calibrate(r.n,p,t,use_lp=False,exact=True,deadline=deadline)
        checked+=1
        if result.pairs_completed!=result.pairs_total:
            return dict(accepted=False,levels_checked=checked,reason='incomplete moments')
        if _union_lower(result)>=alpha:
            return dict(accepted=True,levels_checked=checked,reason='monotone true-union lower bound')
        if result.hunter<alpha:
            return dict(accepted=False,levels_checked=checked,reason='exact higher-score exclusion')
        if len(result.marginal_bounds)<=12:
            moments=tuple(x.lower for x in result.marginal_bounds)+tuple(
                result.pair_bounds[key].lower for key in sorted(result.pair_bounds))
            primal=moment_primal(len(result.marginal_bounds),moments,deadline)
            if primal is None or primal['objective']<alpha:
                return dict(accepted=False,levels_checked=checked,reason='primal acceptance not certified')
    return dict(accepted=True,levels_checked=checked,reason='all attainable higher scores certified')


def close(d):
    """Exact difference-bound closure for ordered cumulative probabilities."""
    d=[list(row) for row in d]
    for k in range(len(d)):
        for i in range(len(d)):
            for j in range(len(d)):
                d[i][j]=min(d[i][j],d[i][k]+d[k][j])
    if any(d[j][j]<0 for j in range(len(d))):raise ValueError('empty difference-bound cell')
    return tuple(map(tuple,d))


def cut_cell(d,a,b,lower,upper):
    out=[list(row) for row in d]
    out[a][b]=min(out[a][b],upper)
    out[b][a]=min(out[b][a],-lower)
    return close(out)


def count_cells(r):
    out=[]
    for variant in r.variants:
        d=[[r.n if i!=j else 0 for j in range(r.k+1)] for i in range(r.k+1)]
        for j in range(r.k):d[j+1][j]=0
        d[0][r.k]=r.n;d[r.k][0]=-r.n
        for a,b,l,u in variant:d[a][b]=min(d[a][b],u);d[b][a]=min(d[b][a],-l)
        try:out.append(close(d))
        except ValueError:pass
    if not out:raise ValueError('infeasible report')
    return out


def baseline_cell(r,alpha):
    cells=count_cells(r)
    k=r.k
    d=[[F(1) if i!=j else F(0) for j in range(k+1)] for i in range(k+1)]
    for j in range(k):d[j+1][j]=F(0)
    d[0][k]=F(1);d[k][0]=F(-1)
    local=alpha/len(range_family(k))
    # Below 2^(1-n), both extreme binomial tails cannot be nonempty at once.
    # Consequently U0(t)<=m*t/2 there, giving a sharper own-method outer.
    if 2*local<=F(1,2**(r.n-1)):local*=2
    for a in range(k):
        for b in range(a+1,k+1):
            low=min(-cell[b][a] for cell in cells)
            high=max(cell[a][b] for cell in cells)
            lo=_cp_outer(low,r.n,local)[0];hi=_cp_outer(high,r.n,local)[1]
            d[a][b]=min(d[a][b],F(float(hi)))
            d[b][a]=min(d[b][a],-F(float(lo)))
    return close(d)


def point(d):
    # Upper potentials and lower potentials each satisfy every difference
    # constraint. Their average is feasible by convexity.
    f=tuple(F(d[0][j]-d[j][0])/2 for j in range(len(d)))
    return tuple(f[j+1]-f[j] for j in range(len(d)-1))


def extreme(d,a,b,value):
    return point(cut_cell(d,a,b,value,value))


def rational_proposal(p,denominator=1<<20):
    """Small-denominator proposal only; exact membership is checked later."""
    # Keep affordable exact score ties. Quantising these again can move a law
    # across a discontinuity of the inclusive discrete test and lose a witness.
    p=tuple(map(F,p))
    if lcm(*(value.denominator for value in p))<=denominator:
        return p
    scaled=[value*denominator for value in p]
    counts=[value.numerator//value.denominator for value in scaled]
    missing=denominator-sum(counts)
    order=sorted(range(len(p)),key=lambda j:(scaled[j]-counts[j],-j),reverse=True)
    for j in order[:missing]:counts[j]+=1
    return tuple(F(value,denominator) for value in counts)


def dominance_forest(n,k,ranges,plus,minus,deadline=None):
    """Uniform event implications certified by null count feasibility.

    Crucially there are NO observed-report constraints in these checks.
    Implications must hold for all null histograms, not merely observed ones.
    """
    active=list(range(len(ranges)));edges=[]
    segments=[];complements=[]
    for hi,lo in zip(plus,minus):
        hi=set(hi);lo=set(lo)
        pieces=[]
        for c in sorted(hi):
            if pieces and c==pieces[-1][1]+1:pieces[-1]=(pieces[-1][0],c)
            else:pieces.append((c,c))
        segments.append(pieces)
        complement=[c for c in range(n+1) if c not in lo]
        if complement and complement!=list(range(complement[0],complement[-1]+1)):
            raise ValueError('inner score event must have an interval complement')
        complements.append(None if not complement else (complement[0],complement[-1]))
    changed=True
    while changed:
        changed=False
        for i in tuple(active):
            for j in active:
                if i==j:continue
                _check_deadline(deadline)
                c=complements[j]
                implies=c is None or all(_feasible_histogram(n,k,
                    ((*ranges[i],l,u),(*ranges[j],*c))) is None for l,u in segments[i])
                if implies:
                    edges.append((i,j));active.remove(i);changed=True;break
            if changed:break
    return tuple(active),tuple(edges)


def score_probability_cap(n,lo,hi,t):
    """Uniform inclusive-score probability bound, with exact tie handling."""
    if t<F(1,2**(n-1)) or (1-hi)**n>t/2 or lo**n>t/2:
        return t/2
    return t


def uniform_bound(r,d,deadline=None,alpha=None):
    """Bound the fixed monotone majorant using shared, lifted thresholds.

    Each evaluated level s is >= every report statistic in this cell.
    Therefore U*(T) <= U0(s). Lifting uncertain score ties restores the
    event implications lost by independent plus/minus envelopes; it does
    not alter the statistical target or assume continuity of its p-value.
    """
    ranges=range_family(r.k)
    envelopes=[]
    for a,b in ranges:
        _check_deadline(deadline)
        envelopes.append(_score_envelopes(r.n,-d[b][a],d[a][b]))
    upper=_max_from_scores(r,ranges,tuple(e[1] for e in envelopes),deadline).threshold
    best=F(1)
    for _ in range(4):
        if upper==1:break
        best=min(best,_uniform_at_level(r,d,ranges,envelopes,upper,deadline,alpha))
        if alpha is not None and best<alpha:break
        lifted=max((hi for lo_scores,hi_scores in envelopes
            for lo,hi in zip(lo_scores,hi_scores) if lo<=upper),default=upper)
        if lifted<=upper:break
        upper=lifted
    return best


def _uniform_at_level(r,d,ranges,envelopes,upper,deadline=None,alpha=None):
    """Uniform bound at a fixed level; caller proves its admissibility."""
    allow_moment_lp=len(ranges)<=12
    plus=tuple(tuple(c for c,s in enumerate(e[0]) if s<=upper) for e in envelopes)
    # Crucial: bound the larger-threshold calibration U_p(upper), so both
    # marginal events AND pair-intersection events use that SAME threshold.
    minus=tuple(tuple(c for c,s in enumerate(e[1]) if s<=upper) for e in envelopes)
    active,_=dominance_forest(r.n,r.k,ranges,plus,minus,deadline)
    ranges=tuple(ranges[j] for j in active)
    plus=tuple(plus[j] for j in active)
    minus=tuple(minus[j] for j in active)
    marg=tuple(min(score_probability_cap(r.n,-d[b][a],d[a][b],upper),tail_upper(r.n,-d[b][a],d[a][b],event))
               for (a,b),event in zip(ranges,plus))
    marginal_lower=tuple(_binomial_event_box(r.n,-d[b][a],d[a][b],event).lower
                         for (a,b),event in zip(ranges,minus))
    total=sum(marg,F(0))
    if total==0:return F(0)
    if alpha is not None and total<alpha:return total
    pairs={}
    for i,e in enumerate(ranges):
        for j in range(i+1,len(ranges)):
            _check_deadline(deadline)
            value=F(0);pair_upper=min(marg[i],marg[j])
            if (minus[i] and minus[j]) or (allow_moment_lp and plus[i] and plus[j]):
                f=ranges[j];groups=[[] for _ in range(4)]
                for index in range(r.k):
                    groups[int(e[0]<=index<e[1])+2*int(f[0]<=index<f[1])].append(index)
                membership=[]
                for group in groups:
                    # Interval groups use exact DBM support. The possible
                    # disconnected complement is bounded via its contiguous
                    # complement when available, otherwise by cell marginals.
                    if not group:membership.append((F(0),F(0)));continue
                    if group==list(range(group[0],group[-1]+1)):
                        a,b=group[0],group[-1]+1;membership.append((-d[b][a],d[a][b]));continue
                    outside=[z for z in range(r.k) if z not in group]
                    if outside and outside==list(range(outside[0],outside[-1]+1)):
                        a,b=outside[0],outside[-1]+1
                        membership.append((1-d[a][b],1+d[b][a]));continue
                    lower=sum((-d[z+1][z] for z in group),F(0))
                    upperq=min(F(1),sum((d[z][z+1] for z in group),F(0)))
                    membership.append((lower,upperq))
                cell_lo,cell_hi=pair_count_distribution_box_bounds(r.n,
                    tuple(v[0] for v in membership),tuple(v[1] for v in membership),deadline=deadline)
                value=_sum_out(cell_lo[np.ix_(minus[i],minus[j])],False)
                pair_upper=min(pair_upper,_sum_out(cell_hi[np.ix_(plus[i],plus[j])],True))
            pairs[i,j]=ProbabilityBounds(value,pair_upper)
    _,weight=_tree(len(ranges),pairs)
    hunter=min(F(1),max(F(0),total-weight))
    if not allow_moment_lp or (alpha is not None and (hunter<alpha or hunter>2*alpha)):
        return hunter
    moments=tuple(ProbabilityBounds(lo,hi) for lo,hi in zip(marginal_lower,marg))+tuple(pairs[key] for key in sorted(pairs))
    certificate,_=_moment_lp(len(ranges),moments,deadline)
    return min(hunter,certificate.upper_bound) if certificate is not None else hunter


@bounded_calculation
def project(problem,*,alpha=F(1,20),time_limit_seconds=120,tolerance_pp=.01,max_boxes=None,progress=None):
    if not isfinite(time_limit_seconds) or not 0<=time_limit_seconds<=1800:
        raise ValueError('research budget must lie in [0,1800]')
    if not isfinite(tolerance_pp) or tolerance_pp<=0:raise ValueError('positive tolerance required')
    if max_boxes is not None and (isinstance(max_boxes,bool) or not isinstance(max_boxes,int) or max_boxes<1):
        raise ValueError('positive max_boxes required')
    alpha=F(alpha)
    if not 0<alpha<1:raise ValueError('alpha must lie in (0,1)')
    start=monotonic();deadline=start+min(time_limit_seconds,1770)
    r=as_region(problem);initial=baseline_cell(r,alpha)
    ranges=tuple((a,b) for a in range(r.k) for b in range(a+1,r.k+1))
    witnesses=set();algebraic=[];histograms=set();stack=[(F(-1),0,initial)];finished=[];active=None
    serial=0
    loinner={e:F(1) for e in ranges};hiinner={e:F(0) for e in ranges}
    visited=discarded=skipped=0;status='precision_unresolved';error=None
    tol=F(str(tolerance_pp))/100
    last_progress=start
    seed_deadline=min(deadline,start+min(30,time_limit_seconds/4))
    seed_seconds=None

    def add(p,known=False):
        if not known:p=rational_proposal(p)
        if p in witnesses:return True
        if known or certify_witness(r,p,alpha,deadline)['accepted']:
            witnesses.add(p)
            for a,b in ranges:
                value=sum(p[a:b]);loinner[a,b]=min(loinner[a,b],value);hiinner[a,b]=max(hiinner[a,b],value)
            return True
        return False

    def gap(d):
        items=[(loinner[a,b]+d[b][a],a,b,False) for a,b in ranges]
        items += [(d[a][b]-hiinner[a,b],a,b,True) for a,b in ranges]
        return max(items)

    def add_algebraic(record):
        if record is None:return False
        projected={e:witness_range(record,*e) for e in ranges}
        if not any(high<loinner[e] or low>hiinner[e] for e,(low,high) in projected.items()):
            return True
        algebraic.append(record)
        for (a,b),(low,high) in projected.items():
            loinner[a,b]=min(loinner[a,b],high)
            hiinner[a,b]=max(hiinner[a,b],low)
        return True

    try:
        _check_deadline(deadline)
        midpoints=[]
        for cell in count_cells(r):
            midpoints.append(tuple(F(v,r.n) for v in point(cell)))
            # Integer potential, unlike the midpoint, is an empirical law
            # compatible with the report and hence has statistic exactly one.
            h=tuple(cell[0][j+1]-cell[0][j] for j in range(r.k))
            histograms.add(h)
            add(tuple(F(v,r.n) for v in h),known=True)
            for a,b in range_family(r.k):
                for target in (-cell[b][a],cell[a][b]):
                    support=cut_cell(cell,a,b,target,target)
                    h=tuple(support[0][j+1]-support[0][j] for j in range(r.k))
                    histograms.add(h)
                    add(tuple(F(v,r.n) for v in h),known=True)
        # Establish inexpensive, algebraically accepted empirical witnesses
        # before an optional exact calibration can consume the time budget.
        for proposal in midpoints:
            add(proposal)
        # Shared algebraic roots retain simultaneous inclusive-score ties.
        # They only add certified inner witnesses, never exclude outer cells.
        try:
            remaining=min(seed_deadline-monotonic(),10,time_limit_seconds/10)
            with deadline_scope(max(0,remaining)):
                for record in multiple_root_proposals(histograms,initial,alpha):
                    add_algebraic(record)
        except TimeoutError:pass
        # Inclusive-score ties may contain admissible algebraic laws that
        # rational floating-point proposals cannot certify, however close.
        try:
            tie_deadline=min(seed_deadline,monotonic()+min(10,time_limit_seconds/10))
            for h in sorted(histograms):
                for a,b in range_family(r.k):
                    for complement in (False,True):
                        e=set(range(a,b))
                        if complement:e=set(range(r.k))-e
                        ce=sum(h[j] for j in e)
                        if ce==r.n:continue
                        high=1+initial[b][a] if complement else initial[a][b]
                        low=F(ce,r.n)
                        for j in range(r.k):
                            if j in e or h[j]==0 or len(e)==r.k-1:continue
                            rejected=high;accepted=None
                            for z in range(16):
                                u=low+(high-low)*F(16-z,16)
                                record=tied_witness(h,e,{j},u,alpha,deadline=tie_deadline)
                                if add_algebraic(record):accepted=u;break
                                rejected=u
                            if accepted is not None:
                                for _ in range(16):
                                    u=(accepted+rejected)/2
                                    record=tied_witness(h,e,{j},u,alpha,deadline=tie_deadline)
                                    if add_algebraic(record):accepted=u
                                    else:rejected=u
        except TimeoutError:pass
        # This optional seed search owns a limited fraction of the budget.
        # Failure to produce a witness leaves the certified outer search intact.
        try:
            proposal_deadline=min(seed_deadline,monotonic()+min(10,time_limit_seconds/10))
            for proposal in support_proposals(r,tuple(witnesses),ranges,alpha,proposal_deadline):add(proposal)
        except TimeoutError:pass
        try:
            # Find support-point witnesses before refining entire probability cells.
            anchors=tuple(witnesses)
            for a,b in ranges:
                if (a,b)==(0,r.k):continue
                for high in (False,True):
                    _check_deadline(seed_deadline)
                    origin=(max if high else min)(anchors,key=lambda p:sum(p[a:b]))
                    destination=extreme(initial,a,b,initial[a][b] if high else -initial[b][a])
                    if add(destination):continue
                    l,u=F(0),F(1)
                    for _ in range(13):
                        t=(l+u)/2;p=tuple((1-t)*v+t*w for v,w in zip(origin,destination))
                        if add(p):l=t
                        else:u=t
        except TimeoutError:pass
        seed_seconds=monotonic()-start
        while stack:
            _check_deadline(deadline)
            if progress is not None and monotonic()-last_progress>=10:
                progress(dict(elapsed_seconds=monotonic()-start,boxes_visited=visited,
                    boxes_discarded=discarded,witnesses=len(witnesses),algebraic_witnesses=len(algebraic),
                    outer_gap_pp=float(100*max(gap(d)[0] for d in [*(v[2] for v in stack),*finished]))))
                last_progress=monotonic()
            if max_boxes is not None and visited>=max_boxes:status='box_limit';break
            _,_,active=heappop(stack)
            g,a,b,high=gap(active)
            # Stored gaps can only decrease when new accepted witnesses are
            # found. Refresh lazily until this is the actual greatest gap.
            if stack and g < -stack[0][0]:
                serial+=1;heappush(stack,(-g,serial,active));active=None;continue
            if witnesses and g<=tol/2:
                finished.append(active);active=None;skipped+=1;continue
            visited+=1
            if uniform_bound(r,active,deadline,alpha)<alpha:
                discarded+=1;active=None;continue
            add(point(active))
            # Endpoint priority chooses the cell, not its splitting direction.
            # Repeatedly narrowing only the target coordinate starves nuisance
            # directions and can leave the probability certificate unchanged.
            a,b=max(range_family(r.k),key=lambda e:(active[e[0]][e[1]]+active[e[1]][e[0]],e[0]-e[1]))
            low,upper=-active[b][a],active[a][b]
            # A score-tie surface may remain unresolved. Preserve this cell
            # and work on the other endpoints, rather than repeatedly bisect
            # one cell far below the requested precision.
            if upper-low<=tol/8:
                finished.append(active);active=None;continue
            split=(low+upper)/2
            if split==low or split==upper:
                finished.append(active);active=None;continue
            children=[]
            for l,u in ((low,split),(split,upper)):
                try:children.append(cut_cell(active,a,b,l,u))
                except ValueError:pass
            for child in children:
                serial+=1;heappush(stack,(-gap(child)[0],serial,child))
            active=None
    except (TimeoutError,MemoryError,ArithmeticError,RuntimeError) as exc:
        status='time_limit' if isinstance(exc,TimeoutError) else 'calculation_incomplete'
        error=f'{type(exc).__name__}: {exc}'
    if active is not None:finished.append(active)
    cover=finished+[d for _,_,d in stack]
    if not cover:
        cover=[initial];witnesses.clear();status='calculation_incomplete';error='Unexpected empty cover; restored baseline'
    intervals=[]
    for a,b in ranges:
        low=min(-d[b][a] for d in cover);upper=max(d[a][b] for d in cover)
        l,u=_float(low,False),_float(upper,True)
        il,iu=(_float(loinner[a,b],True),_float(hiinner[a,b],False)) if witnesses else (None,None)
        g=_float(100*max(F(il)-F(l),F(u)-F(iu)),True) if witnesses else None
        intervals.append(dict(start=a,stop=b,lower=l,upper=u,inner_lower=il,inner_upper=iu,endpoint_gap_pp=g))
    certified=all(v['endpoint_gap_pp'] is not None and F(v['endpoint_gap_pp'])<=F(str(tolerance_pp)) for v in intervals)
    if certified:status='precision_certified'
    return dict(status=status,precision_certified=certified,intervals=intervals,
        boxes_visited=visited,boxes_discarded=discarded,boxes_retained=len(cover),
        boxes_endpoint_irrelevant=skipped,accepted_witnesses=[list(map(str,p)) for p in sorted(witnesses)],
        algebraic_witnesses=[{key:([str(x) for x in value] if isinstance(value,tuple) else str(value)
            if isinstance(value,F) else value) for key,value in record.items()} for record in algebraic],
        elapsed_seconds=monotonic()-start,seed_seconds=seed_seconds,numeric_engine='bounded-seeds-and-lifted-thresholds',error=error,method='pairwise-range-monotone-majorant',
        confidence_level=str(1-alpha),target_precision_pp=tolerance_pp,
        target='Unchanged exact monotone Hunter/moment majorant')
