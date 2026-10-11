"""Retain only laws that can attain an upper bound on observed min-score.

Research contraction of the original existential histogram/score cover.
No tail inversion or floating score authorizes a statistical rejection.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache

from .endpoint import count_cells,cut_cell,range_family,_score_envelopes,_check_deadline
from .pairwise import HistRegion
from mic_50_90.joint_population import _cp_inner

@dataclass(frozen=True)
class Branch:
    region: object
    cell: tuple

@lru_cache(maxsize=8192)
def tail_outer(c,n,t):
    inner=_cp_inner(c,n,t)
    return None if inner is None else tuple(map(F,inner))

def upper_branches(region,cell,score_hi,deadline=None):
    """Cover min-range-score <= score_hi, with the same observed histogram.

    A minimum lies below t only if some range does. That score's two tails
    supply a union of half-space/count branches. Endpoints remain inclusive.
    """
    t=F(score_hi)
    if not 0<t<=1:raise ValueError('Upper score must lie in (0,1]')
    if t==1:return (Branch(region,cell),)
    family=range_family(region.k);result=[];seen=set()
    envelopes={e:_score_envelopes(region.n,-cell[e[1]][e[0]],cell[e[0]][e[1]]) for e in family}
    for variant in region.variants:
        single=HistRegion(region.n,region.k,(variant,))
        try:counts=count_cells(single)[0]
        except ValueError:continue
        for a,b in family:
            _check_deadline(deadline)
            for c in range(int(-counts[b][a]),int(counts[a][b])+1):
                if envelopes[a,b][0][c]>t:continue
                try:cut_cell(counts,a,b,c,c)
                except ValueError:continue
                tails=tail_outer(c,region.n,t)
                # Failure to bracket a root cannot remove an admissible law.
                if tails is None:
                    return (Branch(region,cell),)
                sides=[]
                if c>0:sides.append((F(0),tails[0]))
                if c<region.n:sides.append((tails[1],F(1)))
                for lo,hi in sides:
                    try:new_cell=cut_cell(cell,a,b,lo,hi)
                    except ValueError:continue
                    constraints=variant+((a,b,c,c),)
                    key=(constraints,new_cell)
                    if key in seen:continue
                    seen.add(key)
                    result.append(Branch(HistRegion(region.n,region.k,(constraints,)),new_cell))
    return tuple(result)
