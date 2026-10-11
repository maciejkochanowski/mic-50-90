from fractions import Fraction as F
from functools import lru_cache
from math import comb,factorial,prod,lcm
import numpy as np
from scipy.special import bdtr,bdtrc
from . import pairwise as core

def compositions(n,k):
    if k==1:
        yield (n,)
        return
    for first in range(n+1):
        for rest in compositions(n-first,k-1):yield (first,*rest)


@lru_cache(maxsize=16)
def space(n,k):
    hist=tuple(compositions(n,k))
    coeff=tuple(factorial(n)//prod(factorial(c) for c in h) for h in hist)
    return hist,coeff


def direct_union(region,p,alpha=F(1,20),deadline=None):
    r=core.as_region(region);p=tuple(map(F,p))
    if comb(r.n+r.k-1,r.k-1)>3000:return None
    core._check_deadline(deadline)
    s=core.max_compatible_statistic(r,p,deadline=deadline).threshold
    fam=core.range_family(r.k)
    scores=tuple(core.exact_binomial_scores(r.n,sum(p[a:b])) for a,b in fam)
    denominator=lcm(*(v.denominator for v in p));weights=tuple(int(v*denominator) for v in p)
    hist,coeff=space(r.n,r.k);total=0
    for h,c in zip(hist,coeff):
        if any(scores[j][sum(h[a:b])]<=s for j,(a,b) in enumerate(fam)):
            total+=c*prod(w**v for w,v in zip(weights,h))
    return F(total,denominator**r.n)


def proposals(r,anchors,ranges,alpha,deadline):
    from .endpoint import rational_proposal
    if comb(r.n+r.k-1,r.k-1)>3000:return
    hist,coeff=space(r.n,r.k);hist=np.array(hist);coeff=np.array(coeff,float)
    fam=core.range_family(r.k)
    counts=np.array([hist[:,a:b].sum(axis=1) for a,b in fam]).T
    eligible=np.array([any(all(l<=sum(h[a:b])<=u for a,b,l,u in variant)
                           for variant in r.variants) for h in hist])
    rng=np.random.default_rng(610031)
    pool=np.array(anchors,float)
    def evaluate(p):
        q=np.clip(np.array([p[:,a:b].sum(axis=1) for a,b in fam]).T,0,1)
        cdf=bdtr(counts[None,:,:],r.n,q[:,None,:])
        sf=bdtrc(counts[None,:,:]-1,r.n,q[:,None,:])
        sf=np.where(counts[None,:,:]==0,1,sf)
        scores=np.minimum(1,2*np.minimum(cdf,sf))
        statistic=scores.min(axis=2);observed=statistic[:,eligible].max(axis=1)
        mass=coeff[None,:]*np.prod(p[:,None,:]**hist[None,:,:],axis=2)
        return np.sum(mass*(statistic<=observed[:,None]+1e-14),axis=1)
    def retain(candidates):
        nonlocal pool
        valid=candidates[evaluate(candidates)>=float(alpha)+1e-5]
        if len(valid):pool=np.vstack((pool,valid))
        chosen=set()
        for a,b in ranges:
            values=pool[:,a:b].sum(axis=1)
            # Several starts protect against disconnected acceptance regions.
            chosen.update(np.argsort(values)[:4]);chosen.update(np.argsort(values)[-4:])
        pool=pool[sorted(chosen)]
    for shape in (.05,.1,.2,.5,1,2):
        for _ in range(4):
            core._check_deadline(deadline)
            retain(rng.dirichlet(np.full(r.k,shape),size=256))
    for generation in range(60):
        core._check_deadline(deadline)
        parents=pool[rng.integers(len(pool),size=256)]
        scale=(1,.3,.1,.03,.01)[generation%5]
        logits=np.log(np.maximum(parents,1e-12))+rng.normal(0,scale,parents.shape)
        logits-=logits.max(axis=1)[:,None]
        candidate=np.exp(logits);candidate/=candidate.sum(axis=1)[:,None]
        retain(candidate)
        if generation%10==9:
            for p in pool:
                q=tuple(F(float(v)) for v in p)
                yield rational_proposal(tuple(v/sum(q) for v in q))
    for p in pool:
        q=tuple(F(float(v)) for v in p)
        yield rational_proposal(tuple(v/sum(q) for v in q))

