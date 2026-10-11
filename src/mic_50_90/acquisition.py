"""Request existing recorded MIC counts together or in successive rounds.

All costs concern information still to be obtained. No new susceptibility assay
or population-inference stopping rule is represented by this module.
"""
from fractions import Fraction
from itertools import combinations
from math import isfinite
from time import monotonic

from .decision_planning import (
    _Budget, _BudgetExceeded, _condition, _criteria, _cut, _impossibility,
    _observations, _state, _statuses, _threshold,
)
from .model import parse_spec


def _cost(value):
    try:
        if isinstance(value, bool):
            raise ValueError
        exact = Fraction(str(value))
        display = float(exact)
        if exact < 0 or not isfinite(display) or (exact > 0 and display == 0):
            raise ValueError
        return exact
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        raise ValueError('Acquisition cost must be nonnegative and representable as a finite nonzero number when positive') from None


def _query_map(rows, spec):
    if rows is None:
        rows = [dict(threshold=b.panel_value, unit='mg/L', cost=1)
                for b in spec.panel.bins[:-1]]
    if not isinstance(rows, (list, tuple)):
        raise ValueError('Acquisition queries must be a list; [] permits none')
    result = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'threshold', 'unit', 'cost'}:
            raise ValueError('Acquisition query fields must be threshold, unit and cost')
        threshold = _threshold(row, 'Query')
        price = _cost(row['cost'])
        cut = _cut(spec, threshold)
        if cut in result:
            raise ValueError('Duplicate or equivalent acquisition query cuts')
        result[cut] = dict(threshold=threshold, unit='mg/L', cost=float(price),
                           cost_exact=str(price), cut_index=cut-1)
    return result


def _answers(state, batch, budget, boundary=None):
    """Yield jointly feasible answers, conditioning before the next component."""
    n = state[0].lower[-1]

    def visit(current, index, ranges):
        budget.check()
        if index == len(batch):
            yield ranges, current
            return
        cut = batch[index]
        low = min(b.lower[cut] for b in current)
        high = max(b.upper[cut] for b in current)
        intervals = ((v, v) for v in range(low, high+1)) if boundary is None else (
            (low, min(high, boundary-1)), (max(low, boundary), high))
        for lo, hi in intervals:
            budget.check()
            if lo > hi:
                continue
            child = _condition(current, cut, lo, hi)
            if child:
                yield from visit(child, index+1, ranges+[dict(count_min=n-hi, count_max=n-lo)])
    yield from visit(state, 0, [])


def _solve(state, criteria, queries, rho, budget, maximum):
    common = len(state) == 1 and len({c['boundary'] for c,s in
        zip(criteria, _statuses(state, criteria)) if s == 'undetermined'}) == 1
    boundary = next(c['boundary'] for c,s in zip(criteria, _statuses(state, criteria))
                    if s == 'undetermined') if common else None
    memo, choices = {}, {}

    def key(current):
        # With one common boundary the remaining ordered target cuts completely
        # describe the worst-case problem (see supplement, acquisition theorem).
        if common:
            return tuple(sorted({c['cut'] for c,s in zip(criteria, _statuses(current,criteria))
                                 if s == 'undetermined'}))
        return current

    def value(current):
        identity = key(current)
        if identity in memo:
            return memo[identity]
        budget.check(new_state=True)
        statuses = _statuses(current, criteria)
        if 'undetermined' not in statuses:
            memo[identity] = (Fraction(0), 0, 0)
            return memo[identity]
        active = [q for q in sorted(queries)
                  if min(b.lower[q] for b in current) < max(b.upper[q] for b in current)]
        if common:
            targets = key(current)
            active = [q for q in active if targets[0] <= q <= targets[-1]]
        best = None
        for size in range(min(maximum, len(active)), 0, -1):
            for batch in combinations(active, size):
                budget.check()
                price = rho+sum((Fraction(queries[q]['cost_exact']) for q in batch), Fraction(0))
                if best is not None and price > best[0]:
                    continue
                children = [value(child) for _,child in _answers(current,batch,budget,boundary)]
                candidate = (price+max(c[0] for c in children),
                             1+max(c[1] for c in children), size+max(c[2] for c in children))
                if best is None or candidate < best:
                    best, choices[identity] = candidate, batch
        if best is None:
            raise RuntimeError('No separating request is available')
        memo[identity] = best
        return best

    optimum = value(state)
    nodes = {}

    def build(current):
        budget.check()
        identity = key(current)
        identifier = f's{len(nodes)}'
        cost, rounds, counts = memo[identity]
        node = dict(decisions=_statuses(current, criteria), worst_case_cost=float(cost),
                    worst_case_cost_exact=str(cost), maximum_rounds=rounds, maximum_counts=counts)
        nodes[identifier] = node
        if identity in choices:
            batch = choices[identity]
            node['questions'] = [queries[q] for q in batch]
            node['branches'] = [dict(answers=answers, next_node=build(child))
                for answers,child in _answers(current,batch,budget,boundary)]
        return identifier

    root = build(state)
    return optimum, dict(kind='acquisition_tree', root=root, nodes=nodes), common


def _cost_lower_bound(state, criteria, queries, rho):
    """A separating count is necessary for each pair with opposite decisions.

    A policy follows the same path for the two histograms until it asks a cut
    where they differ. Its worst cost is therefore at least one round plus the
    cheapest such cut. Take the maximum of these pair bounds, never their sum.
    """
    lower, pairs = Fraction(0), []
    n = state[0].lower[-1]
    for index, (item, status) in enumerate(zip(criteria, _statuses(state, criteria))):
        if status != 'undetermined':
            continue
        cut, boundary = item['cut'], item['boundary']
        crossing = next((b for b in state if b.lower[cut] < boundary <= b.upper[cut]), None)
        if crossing is not None:
            # These feasible neighbours differ only at this prefix coordinate.
            # They move one isolate between the two adjacent MIC categories.
            left = [max(v, boundary) if j > cut else v for j,v in enumerate(crossing.lower)]
            left[cut] = boundary-1
            right = list(left)
            right[cut] = boundary
        else:
            left = _condition(state, cut, 0, boundary-1)[0].lower
            right = _condition(state, cut, boundary, n)[0].lower
        histograms = [[p[j+1]-p[j] for j in range(len(p)-1)] for p in (left, right)]
        separating = [q for q in sorted(queries) if left[q] != right[q]]
        if not separating:
            # This pair proves impossibility; the main search supplies the
            # established impossibility contract. There is no finite cost bracket.
            return None, dict(method='feasible_pair_separation', pairs=pairs,
                              nonseparable_pair=histograms)
        value = rho+min(Fraction(queries[q]['cost_exact']) for q in separating)
        lower = max(lower, value)
        pairs.append(dict(criterion_index=index, criterion_cut=cut, histograms=histograms,
            separating_cut_indices=[q-1 for q in separating], cost_lower_bound_exact=str(value)))
    return lower, dict(method='feasible_pair_separation', pairs=pairs)


def plan_acquisition(specification, criteria, *, queries=None, additional_counts=None,
                     round_cost=0, time_limit_seconds=5.0, max_states=5000,
                     max_batch_size=None):
    """Minimise worst-case remaining cost of resolving recorded-sample criteria.

    One round costs round_cost + sum(count costs); costs may be zero. All counts
    must refer to the original sample. None permits every internal cut at cost
    one; [] permits none. A batch returns a jointly feasible vector of exact
    counts. max_batch_size can restrict how many counts can be requested together.
    An incomplete search retains a sufficient request when one was verified.
    """
    budget = _Budget(time_limit_seconds, max_states)
    rho = _cost(round_cost)
    spec = parse_spec(specification)
    if spec.mode != 'empirical':
        raise ValueError('Acquisition planning requires empirical recorded-sample summaries')
    parsed = _criteria(criteria, spec)
    query_map = _query_map(queries, spec)
    _cost(rho*max(1,len(query_map))+sum((Fraction(q['cost_exact']) for q in query_map.values()),Fraction(0)))
    maximum = max(1, len(query_map)) if max_batch_size is None else max_batch_size
    if isinstance(maximum, bool) or not isinstance(maximum,int) or maximum < 1:
        raise ValueError('max_batch_size must be a positive integer')
    observations = [] if additional_counts is None or additional_counts == [] else _observations(additional_counts,spec)
    state = _state(spec,observations)
    statuses = _statuses(state,parsed)
    lower_bound, lower_certificate = _cost_lower_bound(state, parsed, query_map, rho)
    targets = {c['cut'] for c,s in zip(parsed,statuses) if s == 'undetermined'}
    public = [dict({k:v for k,v in c.items() if k not in {'cut','boundary','high_true'}}, initial_status=s)
              for c,s in zip(parsed,statuses)]
    result = dict(status='incomplete', available=True, scope='recorded_sample_decisions',
                  sample_size=spec.n, criteria=public, allowed_queries=list(query_map.values()),
                  additional_counts=observations, round_cost=float(rho), round_cost_exact=str(rho),
                  worst_case_cost=None, worst_case_cost_exact=None, fixed_plan_cost=None,
                  fixed_plan_cost_exact=None, optimality_verified=False, next_questions=[],
                  maximum_rounds=None, maximum_counts=None, policy=None, impossibility_witness=None,
                  method='joint_integer_prefix_acquisition', cost_interpretation='unavailable', reason=None,
                  lower_bound_certificate=lower_certificate,
                  assumptions='Exact recorded counts from the original sample; nonnegative declared costs; '
                              'no new assays, measured labour savings or population stopping guarantee.')

    def incumbent(cuts):
        cuts = sorted(cuts)
        batches = [cuts[i:i+maximum] for i in range(0,len(cuts),maximum)]
        cost = rho*len(batches)+sum((Fraction(query_map[q]['cost_exact']) for q in cuts),Fraction(0))
        result.update(worst_case_cost=float(cost), worst_case_cost_exact=str(cost),
                      fixed_plan_cost=float(cost), fixed_plan_cost_exact=str(cost),
                      maximum_rounds=len(batches), maximum_counts=len(cuts),
                      cost_interpretation='verified_upper_bound',
                      next_questions=[query_map[q] for q in batches[0]] if batches else [],
                      policy=dict(kind='fixed_batches', batches=[[query_map[q] for q in b] for b in batches],
                                  stop_when_all_criteria_resolved=True))

    if not targets:
        incumbent([])
        result.update(status='already_resolved',optimality_verified=True,cost_interpretation='exact_minimax')
    else:
        if targets <= query_map.keys():
            incumbent(targets)
        try:
            budget.check()
            if not targets <= query_map.keys():
                witness = _impossibility(state,parsed,query_map,budget)
                if witness is not None:
                    result.update(status='impossible',impossibility_witness=witness,
                                  reason='The permitted counts cannot distinguish two compatible samples with different answers.')
                else:
                    incumbent(query_map)
            if result['status'] != 'impossible':
                (cost,rounds,counts),policy,common = _solve(state,parsed,query_map,rho,budget,maximum)
                result.update(status='optimal',optimality_verified=True,cost_interpretation='exact_minimax',
                              worst_case_cost=float(cost),worst_case_cost_exact=str(cost),
                              maximum_rounds=rounds,maximum_counts=counts,policy=policy,
                              next_questions=policy['nodes'][policy['root']].get('questions',[]),
                              method='ordered_batch_search' if common else 'joint_integer_prefix_acquisition')
        except (_BudgetExceeded,RecursionError):
            result['reason'] = ('Search limit reached. The saved sufficient request is not certified cheapest.'
                if result['policy'] is not None else 'Search limit reached; no sufficient request has been verified.')
    result['search'] = dict(states=budget.states,elapsed_seconds=monotonic()-budget.start,
                          complete=result['status'] != 'incomplete')
    if result['optimality_verified']:
        lower_bound = Fraction(result['worst_case_cost_exact'])
    upper_bound = Fraction(result['worst_case_cost_exact']) if result['worst_case_cost_exact'] is not None else None
    gap = upper_bound-lower_bound if upper_bound is not None and lower_bound is not None else None
    for name, value in (('cost_lower_bound', lower_bound), ('cost_upper_bound', upper_bound), ('cost_gap', gap)):
        result[name] = float(value) if value is not None else None
        result[name+'_exact'] = str(value) if value is not None else None
    result['cost_bound_basis'] = 'complete_search' if result['optimality_verified'] else 'feasible_pairs_and_sufficient_requests'
    return result
