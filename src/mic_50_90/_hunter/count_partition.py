"""Disjoint integer-count refinements of an existential histogram cover."""
from .endpoint import count_cells
from .pairwise import HistRegion, _check_deadline


def split_counts(region, *, max_span=None):
    """Preserve all compatible histograms in an exact union of children.

    max_span optionally postpones wide count intervals in favor of another
    numerical partition. It does not remove them or limit valid sample sizes.
    """
    _check_deadline(None)
    if len(region.variants)>1:
        return tuple(HistRegion(region.n,region.k,(v,)) for v in region.variants)
    d=count_cells(region)[0]
    choices=[(d[a][a+1]+d[a+1][a],a,-d[a+1][a],d[a][a+1])
             for a in range(region.k) if d[a][a+1]>-d[a+1][a]]
    if not choices:
        return (region,)
    span,a,lo,hi=min(choices)
    if max_span is not None and span>max_span:
        return (region,)
    mid=(lo+hi)//2
    return tuple(HistRegion(region.n,region.k,
        (region.variants[0]+((a,a+1,l,u),),))
        for l,u in ((lo,mid),(mid+1,hi)))
