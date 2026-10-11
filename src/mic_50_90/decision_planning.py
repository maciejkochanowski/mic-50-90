"""Exact acquisition plans for decisions about recorded sample proportions.

The state is a union of integer, monotone prefix-count boxes. This representation
is specific to reported order statistics, extrema and truthful recorded-tail
counts; it does not stand in for a general linear-constraint solver.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from fractions import Fraction
from math import ceil, floor, isfinite
from time import monotonic

from .count_updates import _observations, _count_range
from .decisions import parse_criterion
from .model import parse_spec


@dataclass(frozen=True, order=True)
class _Box:
    lower: tuple[int, ...]
    upper: tuple[int, ...]


def _close(lower, upper):
    lower, upper = list(lower), list(upper)
    for j in range(1, len(lower)):
        lower[j] = max(lower[j], lower[j-1])
    for j in range(len(upper)-2, -1, -1):
        upper[j] = min(upper[j], upper[j+1])
    if any(a > b for a, b in zip(lower, upper)):
        return None
    return _Box(tuple(lower), tuple(upper))


def _condition(state, cut, lower, upper):
    boxes = set()
    for box in state:
        lo, hi = list(box.lower), list(box.upper)
        lo[cut], hi[cut] = max(lo[cut], lower), min(hi[cut], upper)
        closed = _close(lo, hi)
        if closed is not None:
            boxes.add(closed)
    return tuple(sorted(boxes))


def _state(spec, observations):
    size, n, boxes = len(spec.panel.bins), spec.n, set()
    for variant in spec.all_reporting_variants:
        lo, hi = [0]*(size+1), [n]*(size+1)
        lo[-1], hi[0] = n, 0
        for item in variant.quantiles:
            j = item.category_index
            hi[j], lo[j+1] = min(hi[j], item.rank-1), max(lo[j+1], item.rank)
        if variant.minimum_index is not None:
            j = variant.minimum_index
            hi[j], lo[j+1] = 0, max(lo[j+1], 1)
        if variant.maximum_index is not None:
            j = variant.maximum_index
            hi[j], lo[j+1] = min(hi[j], n-1), n
        box = _close(lo, hi)
        if box is not None:
            boxes.add(box)
    state = tuple(sorted(boxes))
    for row in observations:
        if 'start_category' in row:
            raise ValueError('Threshold decision planning does not accept interior counts; use the distribution workflow for these counts')
        cut = _cut(spec, row['threshold'])
        low, high = _count_range(row)
        state = _condition(state, cut, n-high, n-low)
    if not state:
        raise ValueError('No histogram satisfies the declared summaries and additional counts')
    return state


def _cut(spec, threshold):
    return sum(item.panel_value <= threshold for item in spec.panel.bins)


def _threshold(row, label):
    if row.get('unit') not in {'mg/L', 'ug/mL', 'µg/mL', 'μg/mL'}:
        raise ValueError(f'{label} unit must explicitly be mg/L or equivalent ug/mL')
    try:
        value = float(row['threshold'])
    except (KeyError, ValueError, TypeError, OverflowError):
        raise ValueError(f'{label} threshold must be finite and positive') from None
    if isinstance(row['threshold'], bool) or not isfinite(value) or value <= 0:
        raise ValueError(f'{label} threshold must be finite and positive')
    return value


def _criteria(rows, spec):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError('Supply at least one recorded-sample decision criterion')
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {
            'threshold', 'unit', 'decision_operator', 'decision_fraction', 'decision_fraction_text'
        }:
            raise ValueError('Decision criteria require threshold, unit, decision_operator and decision_fraction')
        threshold = _threshold(row, 'Decision')
        raw = dict(row)
        if 'decision_fraction_text' in row:
            raw['decision_fraction'] = row['decision_fraction_text']
        item = parse_criterion(raw)
        if item is None:
            raise ValueError('Each decision criterion requires an operator and fraction')
        op = item['decision_operator']
        fraction = Fraction(item['decision_fraction_text'])
        product = spec.n*fraction
        boundary = spec.n-ceil(product)+1 if op in {'<', '>='} else spec.n-floor(product)
        result.append(dict(item, threshold=threshold, unit='mg/L', cut=_cut(spec, threshold),
                           boundary=boundary, high_true=op in {'<', '<='}))
    return result


def _queries(rows, spec):
    if rows is None:
        rows = [dict(threshold=b.panel_value, unit='mg/L', cost=1) for b in spec.panel.bins[:-1]]
    if not isinstance(rows, (list, tuple)):
        raise ValueError('Decision queries must be a list; an empty list permits no queries')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) - {'threshold', 'unit', 'cost'}:
            raise ValueError('Decision query fields are threshold, unit and positive cost')
        threshold = _threshold(row, 'Query')
        try:
            cost = Fraction(str(row.get('cost')))
            display_cost = float(cost)
        except (ValueError, ZeroDivisionError, OverflowError):
            raise ValueError('Query cost must be a finite positive number') from None
        if cost <= 0 or not isfinite(display_cost) or display_cost <= 0:
            raise ValueError('Query cost must be a finite positive number')
        cut = _cut(spec, threshold)
        if cut in result:
            raise ValueError('Duplicate or equivalent query cuts; supply one cost per recorded tail')
        result[cut] = dict(threshold=threshold, unit='mg/L', cost=float(cost), cost_exact=str(cost),
                           cut_index=cut-1, category_label=spec.panel.bins[cut-1].label if cut else 'below panel')
    try:
        total = float(sum((Fraction(q['cost_exact']) for q in result.values()), Fraction(0)))
    except OverflowError:
        raise ValueError('Total permitted query cost exceeds the finite range of report exports') from None
    if not isfinite(total):
        raise ValueError('Total permitted query cost exceeds the finite range of report exports')
    return result


def _statuses(state, criteria):
    result = []
    for item in criteria:
        lo = min(box.lower[item['cut']] for box in state)
        hi = max(box.upper[item['cut']] for box in state)
        if lo < item['boundary'] <= hi:
            result.append('undetermined')
        else:
            truth = (lo >= item['boundary']) == item['high_true']
            result.append('supported' if truth else 'contradicted')
    return result


class _BudgetExceeded(Exception):
    pass


class _Budget:
    def __init__(self, seconds, states):
        try:
            seconds = float(seconds)
            integer = int(states)
            if not isfinite(seconds) or seconds < 0 or isinstance(states, bool) or integer != float(states) or integer < 1:
                raise ValueError
        except (ValueError, TypeError, OverflowError):
            raise ValueError('Decision planning requires a finite nonnegative time limit and positive integer max_states') from None
        self.start = monotonic()
        self.deadline = self.start+seconds
        self.limit = integer
        self.states = 0

    def check(self, new_state=False):
        if monotonic() >= self.deadline or (new_state and self.states >= self.limit):
            raise _BudgetExceeded
        if new_state:
            self.states += 1


def _paired_witness(left, right, query_cuts, budget):
    """Integer difference constraints, with each allowed prefix tied across states."""
    size = len(left.lower)
    anchor, vertices = 2*size, 2*size+1
    edges = []
    for offset, box in ((0, left), (size, right)):
        for j in range(size):
            edges.extend(((anchor, offset+j, box.upper[j]), (offset+j, anchor, -box.lower[j])))
        edges.extend((offset+j+1, offset+j, 0) for j in range(size-1))
    for j in query_cuts:
        edges.extend(((j, size+j, 0), (size+j, j, 0)))
    distance = [0]*vertices
    for _ in range(vertices):
        budget.check()
        changed = False
        for source, target, weight in edges:
            if distance[target] > distance[source]+weight:
                distance[target] = distance[source]+weight
                changed = True
        if not changed:
            prefix = [value-distance[anchor] for value in distance[:-1]]
            return [[prefix[offset+j+1]-prefix[offset+j] for j in range(size-1)]
                    for offset in (0, size)]
    return None


def _impossibility(state, criteria, queries, budget):
    n = state[0].lower[-1]
    for index, item in enumerate(criteria):
        low = _condition(state, item['cut'], 0, item['boundary']-1)
        high = _condition(state, item['cut'], item['boundary'], n)
        for left in low:
            for right in high:
                budget.check(new_state=True)
                witness = _paired_witness(left, right, queries, budget)
                if witness is not None:
                    states = []
                    for histogram in witness:
                        prefix = [0]
                        for count in histogram:
                            prefix.append(prefix[-1]+count)
                        point = (_Box(tuple(prefix), tuple(prefix)),)
                        states.append(dict(histogram=histogram, decisions=_statuses(point, criteria)))
                    return dict(criterion_index=index, states=states)
    return None


def _fixed_policy(cuts, queries):
    return dict(kind='fixed_order', questions=[queries[q] for q in sorted(cuts)],
                stop_when_all_criteria_resolved=True)


def _ordered_plan(state, criteria, queries, budget):
    """Weighted ordered search for one prefix box and one integer decision boundary."""
    unresolved = [c for c, s in zip(criteria, _statuses(state, criteria)) if s == 'undetermined']
    boundary = unresolved[0]['boundary']
    targets = tuple(sorted({c['cut'] for c in unresolved}))
    positions = {cut: j for j, cut in enumerate(targets)}
    candidates = [(q, Fraction(query['cost_exact']), bisect_left(targets, q), bisect_right(targets, q))
                  for q, query in sorted(queries.items())]
    memo = {}

    def value(first, last):
        if first > last:
            return Fraction(0), None
        if (first, last) in memo:
            return memo[first, last]
        budget.check(new_state=True)
        best = None
        for q, price, left_end, right_start in candidates:
            budget.check()
            if not targets[first] <= q <= targets[last]:
                continue
            left = value(first, left_end-1)[0]
            right = value(right_start, last)[0]
            candidate = price+max(left, right)
            if best is None or candidate < best[0]:
                best = candidate, q
        memo[first, last] = best
        return best

    cost = value(0, len(targets)-1)[0]
    nodes = {}

    def build(current):
        budget.check()
        statuses = _statuses(current, criteria)
        identifier = f's{len(nodes)}'
        node = dict(decisions=statuses, worst_case_cost=0)
        nodes[identifier] = node
        remaining = tuple(sorted({c['cut'] for c, s in zip(criteria, statuses) if s == 'undetermined'}))
        if not remaining:
            return identifier
        node_cost, cut = value(positions[remaining[0]], positions[remaining[-1]])
        node.update(question=queries[cut], branches=[], worst_case_cost=float(node_cost),
                    worst_case_cost_exact=str(node_cost))
        box, n = current[0], current[0].lower[-1]
        for lo, hi in ((box.lower[cut], min(box.upper[cut], boundary-1)),
                       (max(box.lower[cut], boundary), box.upper[cut])):
            if lo <= hi:
                child = _condition(current, cut, lo, hi)
                node['branches'].append(dict(count_min=n-hi, count_max=n-lo, next_node=build(child)))
        return identifier

    root = build(state)
    return cost, dict(kind='adaptive_tree', root=root, nodes=nodes)


def _general_plan(state, criteria, queries, budget):
    memo, choices = {}, {}

    def solve(current):
        if current in memo:
            return memo[current]
        budget.check(new_state=True)
        if 'undetermined' not in _statuses(current, criteria):
            memo[current] = Fraction(0)
            return memo[current]
        best, best_cut, best_children = None, None, None
        for cut, query in sorted(queries.items()):
            budget.check()
            lo, hi = min(b.lower[cut] for b in current), max(b.upper[cut] for b in current)
            if lo == hi:
                continue
            children, worst = [], Fraction(0)
            for answer in range(lo, hi+1):
                budget.check()
                child = _condition(current, cut, answer, answer)
                if not child:
                    continue
                worst = max(worst, solve(child))
                children.append((state[0].lower[-1]-answer, child))
            candidate = Fraction(query['cost_exact'])+worst
            if best is None or candidate < best:
                best, best_cut, best_children = candidate, cut, children
        if best is None:
            raise RuntimeError('Separating-query certificate conflicts with a nonterminal state')
        memo[current], choices[current] = best, (best_cut, best_children)
        return best

    cost = solve(state)
    identifiers, nodes = {}, {}

    def build(current):
        budget.check()
        if current in identifiers:
            return identifiers[current]
        identifier = f's{len(nodes)}'
        identifiers[current] = identifier
        node = dict(decisions=_statuses(current, criteria), worst_case_cost=float(memo[current]),
                    worst_case_cost_exact=str(memo[current]))
        nodes[identifier] = node
        if current in choices:
            cut, children = choices[current]
            node.update(question=queries[cut], branches=[])
            for count, child in children:
                node['branches'].append(dict(count_min=count, count_max=count, next_node=build(child)))
        return identifier

    root = build(state)
    return cost, dict(kind='adaptive_tree', root=root, nodes=nodes)


def plan_decisions(specification, criteria, *, queries=None, additional_counts=None,
                   time_limit_seconds=5.0, max_states=5000):
    """Minimise the worst-case cost of resolving every recorded-sample criterion.

    Query costs must be positive and share a unit chosen by the user. Omitted
    queries allow every internal panel cut at unit cost; an empty list allows
    none. Returned counts must belong to the original sample. A time/state limit
    returns an incomplete search, retaining a verified fixed-plan upper bound
    when available. Population and latent within-category claims are outside
    this planner's scope. General decision-tree optimality is established theory;
    the prefix reduction and its conditions are described in the supplement.
    """
    budget = _Budget(time_limit_seconds, max_states)
    spec = parse_spec(specification)
    if spec.mode != 'empirical':
        raise ValueError('Decision planning requires empirical recorded-sample summaries')
    parsed_criteria, query_map = _criteria(criteria, spec), _queries(queries, spec)
    if additional_counts is None or additional_counts == []:
        observations = []
    else:
        observations = _observations(additional_counts, spec)
    state = _state(spec, observations)
    statuses = _statuses(state, parsed_criteria)
    targets = {c['cut'] for c, s in zip(parsed_criteria, statuses) if s == 'undetermined'}
    public_criteria = [dict((key, value) for key, value in c.items()
                           if key not in {'cut', 'boundary', 'high_true'}) for c in parsed_criteria]
    for row, status in zip(public_criteria, statuses):
        row['initial_status'] = status
    result = dict(status='incomplete', available=True, scope='recorded_sample_decisions',
                  sample_size=spec.n, criteria=public_criteria, worst_case_cost=None,
                  worst_case_cost_exact=None, fixed_plan_cost=None, fixed_plan_cost_exact=None,
                  fixed_plan_optimality_verified=False,
                  cost_interpretation='unavailable', optimality_verified=False, next_question=None,
                  impossibility_witness=None, policy=None, method='integer_prefix_decision_tree',
                  allowed_queries=list(query_map.values()), additional_counts=observations,
                  assumptions='Truthful recorded-tail counts from the same sample; every declared criterion is resolved separately; fixed positive acquisition costs; no population or latent-MIC stopping claim.',
                  reason=None)

    def incumbent(cuts):
        cost = sum((Fraction(query_map[q]['cost_exact']) for q in cuts), Fraction(0))
        result.update(worst_case_cost=float(cost), worst_case_cost_exact=str(cost),
                      fixed_plan_cost=float(cost), fixed_plan_cost_exact=str(cost),
                      fixed_plan_optimality_verified=(not targets or (len(state) == 1 and cuts == targets)),
                      cost_interpretation='verified_upper_bound', policy=_fixed_policy(cuts, query_map))
        if cuts:
            result['next_question'] = query_map[min(cuts)]

    if not targets:
        incumbent(set())
        result.update(status='already_resolved', optimality_verified=True,
                      cost_interpretation='exact_minimax', method='no_additional_information_required')
    else:
        if targets <= query_map.keys():
            incumbent(targets)
        try:
            budget.check()
            common = len(state) == 1 and len({c['boundary'] for c, s in zip(parsed_criteria, statuses)
                                             if s == 'undetermined'}) == 1
            # Each unresolved target cut is necessary for a single coherent box.
            if not targets <= query_map.keys():
                witness = _impossibility(state, parsed_criteria, query_map, budget)
                if witness is not None:
                    result.update(status='impossible', impossibility_witness=witness,
                                  reason='Two feasible histograms agree on every allowed count and disagree on a criterion.')
                elif result['policy'] is None:
                    incumbent(set(query_map))
            if result['status'] != 'impossible':
                if common:
                    cost, policy = _ordered_plan(state, parsed_criteria, query_map, budget)
                    result['method'] = 'weighted_ordered_prefix_search'
                else:
                    cost, policy = _general_plan(state, parsed_criteria, query_map, budget)
                result.update(status='optimal', worst_case_cost=float(cost), worst_case_cost_exact=str(cost),
                              optimality_verified=True, cost_interpretation='exact_minimax', policy=policy,
                              next_question=policy['nodes'][policy['root']].get('question'))
        except _BudgetExceeded:
            result['reason'] = 'The time or state limit was reached; no optimality or impossibility is claimed.'
        except RecursionError:
            result['reason'] = 'The interpreter recursion capacity was reached; no optimality or impossibility is claimed.'
    result['search'] = dict(states=budget.states, elapsed_seconds=monotonic()-budget.start,
                            complete=result['status'] != 'incomplete')
    return result
