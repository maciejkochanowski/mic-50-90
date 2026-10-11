"""Conservative projection with a joint cover of counts, laws and test scores.

The statistical target is unchanged. A node represents an existential
histogram whose minimum binomial score belongs to its score interval.
Rejecting a score node does not reject the other score nodes at that law.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from heapq import heappush, heappop
from math import isfinite
from time import monotonic

from . import endpoint as kernel
from .contractor import propagate
from .upper_score import upper_branches,tail_outer,cut_cell
from .budget import bounded_calculation
from .count_partition import split_counts


@dataclass(frozen=True)
class Node:
    region: object
    cell: tuple
    score_lo: F
    score_hi: F
    anchor: tuple | None = None


def score_split(lo, hi):
    lo, hi = F(lo), F(hi)
    if not 0 < lo < hi <= 1:
        raise ValueError('score interval must satisfy 0 < lower < upper <= 1')
    mid = 2 * lo * hi / (lo + hi)
    return ((lo, mid), (mid, hi))


def _lower_narrow(region, cell, score_lo, score_hi, deadline=None):
    """A safe cover, including a witness exactly on a score boundary."""
    result = []
    for child in propagate(region, cell, score_lo, rounds=2, deadline=deadline):
        family = kernel.range_family(region.k)
        envelopes = tuple(kernel._score_envelopes(region.n, -child.cell[b][a],
                                                child.cell[a][b]) for a, b in family)
        upper = kernel._max_from_scores(child.region, family,
                    tuple(e[1] for e in envelopes), deadline).threshold
        if upper >= score_lo:
            result.append(Node(child.region, child.cell, F(score_lo), min(F(score_hi), upper)))
    return tuple(result)


def bound(node, alpha, deadline):
    family = kernel.range_family(node.region.k)
    envelopes = tuple(kernel._score_envelopes(node.region.n, -node.cell[b][a],
                                            node.cell[a][b]) for a, b in family)
    upper, best = node.score_hi, F(1)
    # Every lifted level is >= the score represented by this node.
    for _ in range(4):
        kernel._check_deadline(deadline)
        if upper == 1:
            break
        best = min(best, kernel._uniform_at_level(node.region, node.cell, family,
                                                envelopes, upper, deadline, alpha))
        if best < alpha:
            break
        lifted = max((hi for lows, highs in envelopes for lo, hi in zip(lows, highs)
                      if lo <= upper), default=upper)
        if lifted <= upper:
            break
        upper = lifted
    return best


def width_status(lower, upper, inner_lower, inner_upper, target):
    """Assess a width goal using outer bounds and attained inner witnesses.

    The inner bracket is a bound on endpoint attainment in the same confidence
    region, not another confidence interval. No midpoint is used.
    """
    if upper-lower <= target:
        return 'met'
    if inner_lower is not None and inner_upper is not None and inner_upper-inner_lower > target:
        return 'not_met'
    return 'unresolved'


@bounded_calculation
def project(problem, *, alpha=F(1, 20), time_limit_seconds=120,
            tolerance_pp=.01, seed_seconds=None, progress=None,
            width_target_pp=None):
    if not isfinite(time_limit_seconds) or not 0 <= time_limit_seconds <= 1800:
        raise ValueError('research budget must lie in [0,1800]')
    if not isfinite(tolerance_pp) or tolerance_pp <= 0:
        raise ValueError('positive tolerance required')
    if seed_seconds is not None and (not isfinite(seed_seconds) or seed_seconds < 0):
        raise ValueError('nonnegative seed budget required')
    width_target = None
    if width_target_pp is not None:
        try:
            width_target = F(str(width_target_pp))/100
        except (ValueError, ZeroDivisionError):
            raise ValueError('width target must lie in [0,100] percentage points') from None
        if isinstance(width_target_pp,bool) or not 0 <= width_target <= 1:
            raise ValueError('width target must lie in [0,100] percentage points')
    alpha = F(alpha)
    if not 0 < alpha < 1:
        raise ValueError('alpha must lie in (0,1)')
    start = monotonic()
    deadline = start + min(1770, time_limit_seconds)
    r = kernel.as_region(problem)
    initial = kernel.baseline_cell(r, alpha)
    ranges = tuple((a, b) for a in range(r.k) for b in range(a + 1, r.k + 1))
    family = kernel.range_family(r.k)
    cutoff = alpha / len(family)
    if 2 * cutoff <= F(1, 2 ** (r.n - 1)):
        cutoff *= 2
    root = Node(r, initial, cutoff, F(1))
    queue = [(F(-1), 0, root)]
    finished, active = [], None
    innerlo = {e: F(1) for e in ranges}
    innerhi = {e: F(0) for e in ranges}
    witnesses, algebraic = set(), []
    serial = visited = discarded = score_splits = probability_splits = count_splits = 0
    status, error = 'precision_unresolved', None
    tol = F(str(tolerance_pp)) / 100
    last_progress = start
    seed_elapsed = 0
    last_width_check = float('-inf')

    def width_assessed():
        if width_target is None:
            return False
        cover = [*(x[2] for x in queue), *finished]
        return all(width_status(min(-x.cell[b][a] for x in cover),
                    max(x.cell[a][b] for x in cover),
                    innerlo[a,b] if witnesses else None,
                    innerhi[a,b] if witnesses else None, width_target) != 'unresolved'
                   for a,b in ranges)

    def gap(node):
        d = node.cell
        return max([innerlo[a, b] + d[b][a] for a, b in ranges] +
                   [d[a][b] - innerhi[a, b] for a, b in ranges])

    def enqueue(node):
        nonlocal serial
        serial += 1
        heappush(queue, (-gap(node), serial, node))

    def add(p):
        p = kernel.rational_proposal(p)
        if p in witnesses:
            return
        if kernel.certify_witness(r, p, alpha, deadline)['accepted']:
            witnesses.add(p)
            for a, b in ranges:
                value = sum(p[a:b])
                innerlo[a, b] = min(innerlo[a, b], value)
                innerhi[a, b] = max(innerhi[a, b], value)

    try:
        ready_at_start = width_assessed()
        if not ready_at_start:
            kernel._check_deadline(deadline)
        # Existing seed routine supplies only certified inner points. Its
        # outer search is not used to discard any of our score nodes.
        budget = 0 if ready_at_start else min(time_limit_seconds, 120 if seed_seconds is None else 4 * seed_seconds)
        if budget > 0:
            seed = kernel.project(r, alpha=alpha, time_limit_seconds=budget,
                                  tolerance_pp=tolerance_pp, max_boxes=1)
            witnesses.update(tuple(map(F, p)) for p in seed['accepted_witnesses'])
            algebraic = seed['algebraic_witnesses']
            for row in seed['intervals']:
                e = row['start'], row['stop']
                if row['inner_lower'] is not None:
                    innerlo[e], innerhi[e] = F(row['inner_lower']), F(row['inner_upper'])
        seed_elapsed = monotonic() - start
        while queue:
            if width_target is not None and monotonic()-last_width_check >= 1:
                last_width_check = monotonic()
                if width_assessed():
                    status = 'width_goal_assessed'
                    break
            kernel._check_deadline(deadline)
            if progress is not None and monotonic() - last_progress >= 10:
                progress(dict(elapsed_seconds=monotonic() - start, nodes_visited=visited,
                    nodes_discarded=discarded, score_splits=score_splits,
                    probability_splits=probability_splits,
                    endpoint_gap_pp=float(100 * max(gap(n) for n in [*(x[2] for x in queue), *finished]))))
                last_progress = monotonic()
            _, _, active = heappop(queue)
            g = gap(active)
            if queue and g < -queue[0][0]:
                enqueue(active)
                active = None
                continue
            if witnesses and g <= tol / 2:
                finished.append(active)
                active = None
                continue
            visited += 1
            children = narrow(active.region, active.cell, active.score_lo, active.score_hi, deadline, active.anchor)
            # Build all replacements before committing them: on any exception
            # the parent remains in the final cover.
            replacements, resolved = [], []
            local_discarded = local_score = local_probability = local_count = 0
            for child in children:
                kernel._check_deadline(deadline)
                if bound(child, alpha, deadline) < alpha:
                    local_discarded += 1
                    continue
                add(kernel.point(child.cell))
                if child.score_hi > child.score_lo * F(5, 4):
                    replacements.extend(Node(child.region, child.cell, lo, hi, child.anchor)
                                        for lo, hi in score_split(child.score_lo, child.score_hi))
                    local_score += 1
                    continue
                count_parts = split_counts(child.region,max_span=2)
                if len(count_parts)>1:
                    replacements.extend(Node(part,child.cell,child.score_lo,child.score_hi,child.anchor)
                                        for part in count_parts)
                    local_count += 1
                    continue
                a, b = max(family, key=lambda e: (child.cell[e[0]][e[1]] + child.cell[e[1]][e[0]], e[0] - e[1]))
                lo, hi = -child.cell[b][a], child.cell[a][b]
                if hi - lo <= tol / 8:
                    resolved.append(child)
                    continue
                mid = (lo + hi) / 2
                for left, right in ((lo, mid), (mid, hi)):
                    try:
                        cell = kernel.cut_cell(child.cell, a, b, left, right)
                    except ValueError:
                        continue
                    replacements.append(Node(child.region, cell, child.score_lo, child.score_hi, child.anchor))
                local_probability += 1
            for child in replacements:
                enqueue(child)
            finished.extend(resolved)
            discarded += local_discarded + int(not children)
            score_splits += local_score
            probability_splits += local_probability
            count_splits += local_count
            active = None
    except (TimeoutError, MemoryError, ArithmeticError, RuntimeError) as exc:
        status = 'time_limit' if isinstance(exc, TimeoutError) else 'calculation_incomplete'
        error = f'{type(exc).__name__}: {exc}'
    if active is not None:
        finished.append(active)
    cover = finished + [v[2] for v in queue]
    if not cover:
        cover = [root]
        status, error = 'calculation_incomplete', 'Unexpected empty cover; restored baseline'
    rows = []
    for a, b in ranges:
        lo = min(-node.cell[b][a] for node in cover)
        hi = max(node.cell[a][b] for node in cover)
        lower, upper = kernel._float(lo, False), kernel._float(hi, True)
        il, iu = (kernel._float(innerlo[a,b], True), kernel._float(innerhi[a,b], False)) if witnesses else (None, None)
        distance = kernel._float(100 * max(F(il) - F(lower), F(upper) - F(iu)), True) if witnesses else None
        rows.append(dict(start=a, stop=b, lower=lower, upper=upper,
                         inner_lower=il, inner_upper=iu, endpoint_gap_pp=distance))
        if width_target is not None:
            rows[-1]['width_status'] = width_status(lo, hi,
                innerlo[a,b] if witnesses else None, innerhi[a,b] if witnesses else None, width_target)
    certified = all(v['endpoint_gap_pp'] is not None and F(v['endpoint_gap_pp']) <= F(str(tolerance_pp)) for v in rows)
    if certified:
        status = 'precision_certified'
    result = dict(status=status, precision_certified=certified, intervals=rows,
        nodes_visited=visited, nodes_discarded=discarded, nodes_retained=len(cover),
        score_splits=score_splits, probability_splits=probability_splits, count_splits=count_splits,
        accepted_witnesses=[list(map(str, p)) for p in sorted(witnesses)],
        algebraic_witnesses=algebraic, elapsed_seconds=monotonic()-start,
        seed_seconds=seed_elapsed, numeric_engine='joint-count-law-score-partition',
        error=error, method='pairwise-range-monotone-majorant', confidence_level=str(1-alpha),
        target_precision_pp=tolerance_pp, target='Unchanged exact monotone Hunter/moment majorant')
    if width_target is not None:
        statuses = [x['width_status'] for x in rows]
        result['width_goal'] = dict(target_pp=float(100*width_target),target_pp_text=str(100*width_target),
            status=('met' if all(x=='met' for x in statuses) else
                    'not_met' if any(x=='not_met' for x in statuses) else 'unresolved'),
            all_ranges_assessed=all(x!='unresolved' for x in statuses),
            scope='All contiguous category ranges under the same confidence construction and supplied report',
            interpretation='A not_met result cannot be repaired by endpoint refinement alone. '
                           'It does not assert that complete counts or more isolates would be insufficient.')
    return result


def narrow(region,cell,lo,hi,deadline=None,anchor=None):
    nodes=[]
    for parent in _lower_narrow(region,cell,lo,hi,deadline):
        if anchor is not None:
            a,b,c,side=anchor;tails=tail_outer(c,region.n,parent.score_hi)
            if tails is None:
                nodes.append(Node(parent.region,parent.cell,parent.score_lo,parent.score_hi,anchor));continue
            lower,upper=(F(0),tails[0]) if side==0 else (tails[1],F(1))
            try:new_cell=cut_cell(parent.cell,a,b,lower,upper)
            except ValueError:continue
            nodes.append(Node(parent.region,new_cell,parent.score_lo,parent.score_hi,anchor))
        else:
            for child in upper_branches(parent.region,parent.cell,parent.score_hi,deadline):
                chosen=None
                if child.region!=parent.region or child.cell!=parent.cell:
                    a,b,c,c2=child.region.variants[0][-1];assert c==c2
                    tails=tail_outer(c,region.n,parent.score_hi)
                    if tails is not None:
                        if c>0 and child.cell[a][b]<=tails[0]:chosen=(a,b,c,0)
                        elif c<region.n and -child.cell[b][a]>=tails[1]:chosen=(a,b,c,1)
                nodes.append(Node(child.region,child.cell,parent.score_lo,parent.score_hi,chosen))
    return tuple(nodes)

