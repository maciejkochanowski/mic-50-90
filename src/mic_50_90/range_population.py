"""Simultaneous population projections from contiguous MIC count ranges.

The cutoff is fixed by sample size, panel size and confidence level. It is not
chosen from observed widths. Partial enumeration retains the entire report's
outer region. See docs/range-population-method.md for the coverage argument.
"""
from fractions import Fraction as F
from functools import lru_cache
from time import monotonic

import numpy as np


def critical_score(n, k, alpha):
    """Uniform doubled-binomial-score cutoff with a strict rejection rule."""
    if type(n) is not int or n < 1 or type(k) is not int or k < 2:
        raise ValueError('Positive sample size and at least two categories required')
    alpha = F(alpha)
    if not 0 < alpha < 1:
        raise ValueError('alpha must lie in (0,1)')
    m = k*(k-1)//2
    cutoff = alpha/m
    for r in range(1, k):
        q, remainder = divmod(k, r)
        edges = (k*k-remainder*(q+1)**2-(r-remainder)*q*q)//2
        cutoff = max(cutoff, min(2*alpha/(m+edges), 2*F(r, r+1)**n))
    return min(F(1), cutoff)


def _close(d):
    """Exact difference-constraint closure; None means an empty polytope."""
    for middle in range(len(d)):
        for a in range(len(d)):
            for b in range(len(d)):
                d[a][b] = min(d[a][b], d[a][middle]+d[middle][b])
    return None if any(d[a][a] < 0 for a in range(len(d))) else d


def _probability_cell(k, intervals):
    d = [[F(int(a < b)) for b in range(k+1)] for a in range(k+1)]
    d[k][0] = F(-1)
    for a, b, lo, hi in intervals:
        d[a][b] = min(d[a][b], F(hi))
        d[b][a] = min(d[b][a], -F(lo))
    return _close(d)


def _rounded(x, upward):
    y = float(x)
    if (F(y) < x if upward else F(y) > x):
        y = float(np.nextafter(y, np.inf if upward else -np.inf))
    return y


def _project(d, pairs, *, inner=False):
    return (np.array([_rounded(-d[b][a], inner) for a, b in pairs]),
            np.array([_rounded(d[a][b], not inner) for a, b in pairs]))


def _histograms(d, deadline):
    """Enumerate compatible integer cumulative counts with bounded stack space."""
    k = len(d)-1
    n = int(d[0][k])
    fixed = {0: 0, k: n}

    def visit(b):
        if monotonic() >= deadline:
            raise TimeoutError('Compatible histogram search reached its time limit')
        if b == k:
            yield tuple(fixed[j+1]-fixed[j] for j in range(k))
            return
        low = max(fixed[a]-int(d[b][a]) for a in fixed)
        high = min(fixed[a]+int(d[a][b]) for a in fixed)
        for count in range(low, high+1):
            fixed[b] = count
            yield from visit(b+1)
        fixed.pop(b, None)

    yield from visit(1)


def range_population(problems, *, confidence_level, time_limit_seconds,
                     tolerance_pp, include_intervals):
    # Import locally to keep population_distribution the public dispatcher.
    from .joint_population import _validate, _constraint_signature, _cp_outer, _cp_inner, _attach_intervals
    from .utility import _prefix_distances

    started = monotonic()
    n, k = _validate(problems)
    cutoff = critical_score(n, k, 1-F(float(confidence_level)))
    family = [(a, b) for a in range(k) for b in range(a+1, k)]
    pairs = [(0, b) for b in range(1, k)]+[(a, a+1) for a in range(k)]
    if include_intervals:
        pairs += [(a, b) for a in range(k) for b in range(a+1, k+1)]
    matrices = [_prefix_distances(p) for p in problems.values()]

    @lru_cache(maxsize=1024)
    def cp(x, inner):
        return (_cp_inner if inner else _cp_outer)(x, n, cutoff)

    outer_lo, outer_hi = np.ones(len(pairs)), np.zeros(len(pairs))
    inner_lo, inner_hi = np.full(len(pairs), np.inf), np.full(len(pairs), -np.inf)
    full_lo, full_hi = np.ones(len(pairs)), np.zeros(len(pairs))
    histogram_count = 0
    seen_histograms = set()

    def remember(h, *, outer=False):
        nonlocal histogram_count
        h = tuple(int(x) for x in h)
        if h in seen_histograms and not outer:
            return
        seen_histograms.add(h)
        histogram_count += 1
        cumulative = np.r_[0, np.cumsum(h)].tolist()
        intervals = []
        for a, b in family:
            endpoints = cp(cumulative[b]-cumulative[a], True)
            if endpoints is None:
                break
            intervals.append((a, b, *endpoints))
        else:
            cell = _probability_cell(k, intervals)
            if cell is not None:
                low, high = _project(cell, pairs, inner=True)
                np.minimum(inner_lo, low, out=inner_lo)
                np.maximum(inner_hi, high, out=inner_hi)
        if outer:
            cell = _probability_cell(k, [(a, b, *cp(cumulative[b]-cumulative[a], False)) for a, b in family])
            if cell is None:
                raise ArithmeticError('Population outer region unexpectedly empty')
            low, high = _project(cell, pairs)
            np.minimum(full_lo, low, out=full_lo)
            np.maximum(full_hi, high, out=full_hi)

    complete_histograms = True
    for d in matrices:
        cell = _probability_cell(k, [(a, b, cp(int(-d[b, a]), False)[0],
                                      cp(int(d[a, b]), False)[1]) for a, b in family])
        if cell is None:
            raise ArithmeticError('Population outer region unexpectedly empty')
        low, high = _project(cell, pairs)
        np.minimum(outer_lo, low, out=outer_lo)
        np.maximum(outer_hi, high, out=outer_hi)
        complete_histograms &= all(d[a, a+1] == -d[a+1, a] for a in range(k))
        # Closed integer difference constraints guarantee these are full,
        # compatible histograms; no LP rounding is used as a witness.
        remember(np.diff(d[0, :]).astype(int).tolist())
        remember(np.diff(-d[:, 0]).astype(int).tolist())

    baseline_lo, baseline_hi = outer_lo.copy(), outer_hi.copy()
    baseline_seconds = monotonic()-started
    refinement_start = monotonic()
    deadline = refinement_start+time_limit_seconds
    exhausted, failure = complete_histograms, None

    def gap():
        return max(F(0), *(F(float(i))-F(float(o)) for i, o in zip(inner_lo, outer_lo)),
                   *(F(float(o))-F(float(i)) for o, i in zip(outer_hi, inner_hi))) if np.all(np.isfinite(inner_lo)) and np.all(np.isfinite(inner_hi)) else None

    def precise():
        value = gap()
        return value is not None and value <= F(float(tolerance_pp))/100

    range_witnesses_checked = 0
    shape_certificate = dict(status='not_checked', reason='Numerical witnesses or the general refinement suffice')
    # The finite shape check is inexpensive for small samples. Larger samples
    # retain the same fixed method and use pointwise endpoint certificates.
    if not complete_histograms and not precise() and n <= 100 and monotonic() < deadline:
        from .range_certificates import binomial_shape_certificate
        shape_certificate = binomial_shape_certificate(n, cutoff, deadline)
        if shape_certificate['status'] == 'certified':
            for d in matrices:
                lows, highs = [], []
                for a,b in pairs:
                    if a == 0 and b == k:
                        low = high = 1.
                    else:
                        low = cp(int(-d[b,a]), True)[0]
                        high = cp(int(d[a,b]), True)[1]
                    lows.append(low); highs.append(high)
                # The row-lift theorem identifies these exact endpoints; inward
                # CP brackets certify their numerical locations without claiming
                # that all marginal endpoint choices form one distribution.
                np.minimum(inner_lo, lows, out=inner_lo)
                np.maximum(inner_hi, highs, out=inner_hi)
    if not complete_histograms and not precise() and monotonic() < deadline:
        # Each closed count matrix supplies K+1 feasible integer potentials.
        # Row a attains every upper count bound D[a,b]; row b attains the
        # corresponding lower bound -D[b,a]. Their population regions are
        # checked separately: count attainment alone is not enough to claim
        # population endpoint attainment. Row zero was already checked above.
        for d in matrices:
            for anchor in range(1, k+1):
                if monotonic() >= deadline or precise():
                    break
                remember(np.diff(d[anchor, :]).astype(int).tolist())
                range_witnesses_checked += 1
    probability_checks, probability_certificates = 0, []
    if not complete_histograms and not precise() and monotonic() < deadline:
        from .range_certificates import compatible_probability_witness
        try:
            for d in matrices:
                # These points are inward versions of the outer region's row
                # potentials. Membership still needs a compatible count witness.
                intervals = []
                for a, b in family:
                    lo, hi = cp(int(-d[b,a]), True), cp(int(d[a,b]), True)
                    if lo is None or hi is None:
                        break
                    intervals.append((a,b,lo[0],hi[1]))
                else:
                    cell = _probability_cell(k, intervals)
                    if cell is None:
                        continue
                    for anchor in range(k+1):
                        if precise():
                            break
                        p = tuple(cell[anchor][j+1]-cell[anchor][j] for j in range(k))
                        probability_checks += 1
                        witness = compatible_probability_witness(d, p, cutoff, deadline)
                        if witness is not None:
                            remember(witness)
                            values = [sum(p[a:b]) for a,b in pairs]
                            np.minimum(inner_lo, [_rounded(v, True) for v in values], out=inner_lo)
                            np.maximum(inner_hi, [_rounded(v, False) for v in values], out=inner_hi)
                            probability_certificates.append(dict(anchor=anchor,
                                probabilities=[str(x) for x in p], histogram=list(witness)))
        except (TimeoutError, MemoryError) as exc:
            failure = str(exc) or type(exc).__name__

    partition_count = 0
    if not complete_histograms and not precise() and monotonic() < deadline:
        from .range_certificates import split_count_cell

        def envelope(d):
            cell = _probability_cell(k, [(a,b,cp(-d[b][a],False)[0],cp(d[a][b],False)[1]) for a,b in family])
            if cell is None:
                raise ArithmeticError('Count-cell population envelope unexpectedly empty')
            return _project(cell, pairs)

        pending = []
        finished_lo, finished_hi = np.ones(len(pairs)), np.zeros(len(pairs))
        try:
            for d in matrices:
                node = d.astype(int).tolist()
                low, high = envelope(node)
                pending.append((node,low,high))
            while pending and not precise():
                if monotonic() >= deadline:
                    raise TimeoutError('Count partition refinement reached its time limit')
                # Retain the parent until both children and their envelopes
                # exist. Interruption therefore never deletes an unresolved part.
                node, _, _ = pending[-1]
                children = split_count_cell(node)
                replacements = []
                if children:
                    for child in children:
                        if monotonic() >= deadline:
                            raise TimeoutError('Count partition refinement reached its time limit')
                        low, high = envelope(child)
                        remember([child[0][j+1]-child[0][j] for j in range(k)])
                        replacements.append((child,low,high))
                    if len(pending)+len(replacements) > 10000:
                        raise MemoryError('Count partition work-list limit; all unresolved bounds retained')
                else:
                    # A singleton count cell has exactly one compatible histogram.
                    for h in _histograms(np.asarray(node), deadline):
                        remember(h, outer=True)
                    np.minimum(finished_lo, pending[-1][1], out=finished_lo)
                    np.maximum(finished_hi, pending[-1][2], out=finished_hi)
                pending.pop()
                pending.extend(replacements)
                partition_count += bool(children)
                lows = [finished_lo]+[item[1] for item in pending]
                highs = [finished_hi]+[item[2] for item in pending]
                outer_lo = np.maximum(outer_lo, np.minimum.reduce(lows))
                outer_hi = np.minimum(outer_hi, np.maximum.reduce(highs))
            exhausted = not pending
        except (TimeoutError, MemoryError) as exc:
            failure = str(exc) or type(exc).__name__

    endpoint_gap = gap()
    reached = precise()
    elapsed = monotonic()-started
    m = k-1
    result = dict(requested_method='range-calibrated', method='range-calibrated',
        confidence_level=confidence_level, constraint_signature=_constraint_signature(problems),
        family_size=len(family), family_kind='all_contiguous_ranges_up_to_complements',
        coverage_scope='all contiguous recorded category ranges on the fixed panel',
        sample_size=n, numerical_tolerance_pp=tolerance_pp, bounds_kind='conservative_outer',
        status='complete' if reached else ('time_limit' if failure else 'precision_unresolved'),
        precision_reached=reached, endpoint_gap_pp=None if endpoint_gap is None else _rounded(100*endpoint_gap, True),
        critical_score_fraction=str(cutoff), compatible_histogram_search_complete=bool(exhausted),
        evaluated_histograms=histogram_count, box_count=0, excluded_boxes=0,
        range_witnesses_checked=range_witnesses_checked,
        population_row_lift_certificate=shape_certificate,
        probability_vertices_checked=probability_checks, probability_certificates=probability_certificates,
        count_partition_splits=partition_count,
        baseline_cdf_bounds=np.column_stack((baseline_lo[:m], baseline_hi[:m])).tolist(),
        baseline_category_bounds=np.column_stack((baseline_lo[m:m+k], baseline_hi[m:m+k])).tolist(),
        cdf_bounds=np.column_stack((outer_lo[:m], outer_hi[:m])).tolist(),
        category_bounds=np.column_stack((outer_lo[m:m+k], outer_hi[m:m+k])).tolist(),
        guarantee='Simultaneous finite-sample coverage under iid sampling on the fixed recorded panel; all contiguous category ranges; no within-category reconstruction.',
        numerical_certificate='Directed binomial tail brackets and exact rational difference-constraint closure. Count and accepted probability witnesses certify inner projections. Disjoint count partitions retain an envelope for every unresolved part.',
        elapsed_seconds=elapsed, baseline_seconds=baseline_seconds,
        refinement_seconds=monotonic()-refinement_start, time_limit_scope='optional_compatible_histogram_refinement',
        question_certificates=[])
    if not reached:
        result['reason'] = failure or 'Safe population bounds are available; the endpoint gap remains unresolved.'
    if include_intervals:
        _attach_intervals(result, k, outer_lo[m+k:], outer_hi[m+k:], inner_lo[m+k:], inner_hi[m+k:])
    return result
