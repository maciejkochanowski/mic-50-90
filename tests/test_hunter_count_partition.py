from itertools import product

from mic_50_90._hunter.pairwise import HistRegion


def members(region):
    return {h for h in product(range(region.n+1),repeat=region.k)
            if sum(h)==region.n and any(all(lo<=sum(h[a:b])<=hi for a,b,lo,hi in v)
                                       for v in region.variants)}


def test_count_partition_preserves_exact_union():
    from mic_50_90._hunter.count_partition import split_counts
    for region in [HistRegion(3,3,((),)),
                   HistRegion(3,5,(((1,2,1,2),(2,3,0,0)),)),
                   HistRegion(3,3,(((0,1,0,1),),((1,3,2,3),)))]:
        parts=split_counts(region)
        assert set().union(*(members(x) for x in parts))==members(region)
        if len(region.variants)==1:
            assert not members(parts[0]) & members(parts[1])


def test_fixed_counts_are_not_split():
    from mic_50_90._hunter.count_partition import split_counts
    r=HistRegion(3,3,(((0,1,1,1),(1,2,1,1),(2,3,1,1)),))
    assert split_counts(r)==(r,)
