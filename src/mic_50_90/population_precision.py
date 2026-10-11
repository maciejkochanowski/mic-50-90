"""Certified resolution of one fixed simultaneous population confidence region.

Each edge joins adjacent categories. Outer projection widths admit an edge;
accepted-point widths can rule it out. Longest paths bound the finest possible
partition without treating a numerical timeout as a scientific impossibility.
"""
from __future__ import annotations

from fractions import Fraction
from math import isfinite

from .validation import decimal_number, exact_integer


def maximum_population_partition(population, panel, *, precision_pp, required_cuts=()):
    precision = decimal_number(precision_pp, 'population_precision_pp')
    if not 0 <= precision <= 100:
        raise ValueError('population_precision_pp must lie in [0,100]')
    k = len(panel.bins)
    mandatory = {exact_integer(c, 'required cut', 1) for c in required_cuts}
    if any(c >= k for c in mandatory):
        raise ValueError('Required cuts must be interior panel boundaries')
    rows = {(r['start_index'], r['stop_index']): r for r in population['interval_bounds']}
    expected = {(a,b) for a in range(k) for b in range(a+1,k+1)}
    if set(rows) != expected:
        raise ValueError('Population precision requires every contiguous interval')
    for r in rows.values():
        if not all(isfinite(r[s]) for s in ('lower','upper')) or not 0 <= r['lower'] <= r['upper'] <= 1:
            raise ValueError('Invalid population outer bounds')
        lo, hi = r.get('inner_lower'), r.get('inner_upper')
        if (lo is None) != (hi is None) or (lo is not None and not r['lower'] <= lo <= hi <= r['upper']):
            raise ValueError('Invalid population inner witnesses')
    target = Fraction(precision)/100
    def width(r, possible):
        lo, hi = (r.get('inner_lower'),r.get('inner_upper')) if possible else (r['lower'],r['upper'])
        return Fraction(0) if lo is None else Fraction(hi)-Fraction(lo)
    def path(possible):
        best = {0:(0,)}
        for b in range(1,k+1):
            candidates = [(*best[a],b) for a in range(b) if a in best
                and not any(a < c < b for c in mandatory)
                and width(rows[a,b],possible) <= target and width(rows[0,b],possible) <= target]
            if candidates:
                best[b] = min(candidates,key=lambda x:(-len(x),x))
        return best.get(k,())
    certain, possible = path(False), path(True)
    low, high = max(0,len(certain)-1), max(0,len(possible)-1)
    bins = []
    for a,b in zip(certain,certain[1:]):
        r = rows[a,b]
        bins.append(dict(r,label=' through '.join(dict.fromkeys([panel.labels[a],panel.labels[b-1]])),
            width_pp=float(100*width(r,False)), cumulative_width_pp=float(100*width(rows[0,b],False))))
    return dict(status='achieved' if low else ('no_partition' if not high else 'numerically_unresolved'),
        precision_pp=float(precision), confidence_level=population['confidence_level'],
        guaranteed_number_of_bins=low, possible_number_of_bins=high,
        maximum_number_verified=low==high, cut_indices=list(certain), possible_cut_indices=list(possible),
        required_cuts=sorted(mandatory), bins=bins, original_number_of_categories=k,
        interpretation='All displayed groups and retained cumulative boundaries meet the requested width for the same simultaneous population region. Merging groups reduces detail; it does not add observations.',
        scope='The selected fixed population method and current information; no sample-size recommendation or impossibility after future counts is implied.')
