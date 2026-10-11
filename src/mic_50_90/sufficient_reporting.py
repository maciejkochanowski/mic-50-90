"""Minimum-cost truthful reports for specified decisions about an existing sample.

The laboratory knows the histogram; the recipient receives only the summaries
and selected counts. This is certificate selection, not prospective acquisition.
"""
from fractions import Fraction
from heapq import heappop, heappush
from time import monotonic

from .acquisition import _cost, _query_map
from .decision_planning import (
    _Budget, _BudgetExceeded, _condition, _criteria, _observations, _state, _statuses,
)
from .model import parse_spec
from .validation import exact_integer
from .exact_population import _merge_integer_ranges


def _inputs(specification, criteria):
    spec = parse_spec(specification)
    if spec.mode != 'empirical':
        raise ValueError('Sufficient reporting requires empirical recorded-sample summaries')
    return spec, _criteria(criteria, spec)


def verify_reporting(specification, criteria, disclosures):
    """Check logical sufficiency without access to the original histogram.

    This checks consequences of declared truthful counts, not their provenance
    or a population statement. Wrong denominators and contradictions are refused.
    """
    spec, parsed = _inputs(specification, criteria)
    observations = [] if disclosures == [] else _observations(disclosures, spec)
    state = _state(spec, observations)
    statuses = _statuses(state, parsed)
    bounds = []
    for criterion, status in zip(parsed, statuses):
        q = criterion['cut']
        bounds.append(dict(threshold=criterion['threshold'], unit='mg/L',
                           decision_operator=criterion['decision_operator'],
                           decision_fraction_text=criterion['decision_fraction_text'],
                           count_min=spec.n-max(b.upper[q] for b in state),
                           count_max=spec.n-min(b.lower[q] for b in state),
                           count_components=[list(component) for component in _merge_integer_ranges(
                               [(spec.n-b.upper[q], spec.n-b.lower[q]) for b in state])],
                           n=spec.n, status=status))
    return dict(sufficient='undetermined' not in statuses, decisions=statuses,
                bounds=bounds, sample_size=spec.n, scope='recorded_sample_decisions',
                guarantee='Logical implication of the declared summaries and truthful counts; '
                          'no new population or calibration guarantee')


def _apply(state, cuts, prefix):
    for q in cuts:
        state = _condition(state, q, prefix[q], prefix[q])
    return state


def _boundary_certificate(state, parsed, prefix, queries, budget):
    unresolved = [c for c,s in zip(parsed,_statuses(state,parsed)) if s == 'undetermined']
    if len(state) != 1 or len({c['boundary'] for c in unresolved}) != 1:
        return None
    boundary = unresolved[0]['boundary']
    below = [c['cut'] for c in unresolved if prefix[c['cut']] < boundary]
    above = [c['cut'] for c in unresolved if prefix[c['cut']] >= boundary]
    chosen = []
    for side in (below, above):
        budget.check(new_state=True)
        if not side:
            continue
        if side is below:
            candidates = [q for q in queries if q >= max(side) and prefix[q] < boundary]
        else:
            candidates = [q for q in queries if q <= min(side) and prefix[q] >= boundary]
        if not candidates:
            return None
        chosen.append(min(candidates,key=lambda q:(Fraction(queries[q]['cost_exact']),q)))
    return tuple(sorted(chosen))


def plan_reporting(specification, histogram, criteria, *, queries=None,
                   time_limit_seconds=5.0, max_states=5000):
    """Choose a cheapest sufficient report after the full histogram is known.

    Query costs are nonnegative rational reporting costs. A common-boundary,
    single-variant problem admits a proved two-boundary solution. Other cases
    use cost-ordered subset search. Limits preserve a verified sufficient report
    and a lower cost bound, without declaring optimality.
    """
    budget = _Budget(time_limit_seconds, max_states)
    spec, parsed = _inputs(specification, criteria)
    if isinstance(histogram,(str,bytes,dict)):
        raise ValueError('histogram must contain one count per panel category')
    try:
        counts = [exact_integer(v,'histogram count') for v in histogram]
    except TypeError:
        raise ValueError('histogram must contain one count per panel category') from None
    if len(counts) != len(spec.panel.bins) or sum(counts) != spec.n:
        raise ValueError('histogram must include every category and sum to the original n')
    prefix = [0]
    for v in counts:
        prefix.append(prefix[-1]+v)
    state = _state(spec, [])
    if not any(all(lo <= f <= hi for lo,f,hi in zip(b.lower,prefix,b.upper)) for b in state):
        raise ValueError('histogram is incompatible with every declared reporting interpretation')
    query_map = _query_map(queries, spec)
    costs = {q:Fraction(row['cost_exact']) for q,row in query_map.items()}
    _cost(sum(costs.values(),Fraction(0)))
    initial = _statuses(state, parsed)
    result = dict(status='incomplete', sufficient=False, optimality_verified=False,
                  scope='recorded_sample_decisions', sample_size=spec.n,
                  initial_decisions=initial, disclosures=[], selected_queries=[],
                  report_cost=None, report_cost_exact=None, cost_lower_bound=0.0,
                  cost_lower_bound_exact='0', method='cost_ordered_report_subsets',
                  reason=None, verification=None,
                  assumptions='Complete histogram known to the reporter; truthful counts from the same '
                              'sample. Preserves only the declared recorded-sample decisions. '
                              'Costs do not measure staff time or information-acquisition cost.')

    def retain(cuts):
        rows = [dict(threshold=query_map[q]['threshold'],unit='mg/L',count=spec.n-prefix[q],n=spec.n)
                for q in sorted(cuts)]
        checked = verify_reporting(specification,criteria,rows)
        if not checked['sufficient']:
            raise RuntimeError('Candidate reporting set did not pass recipient verification')
        cost = sum((costs[q] for q in cuts),Fraction(0))
        result.update(sufficient=True, disclosures=rows, verification=checked,
                      selected_queries=[query_map[q] for q in sorted(cuts)],
                      report_cost=float(cost),report_cost_exact=str(cost))

    def finish():
        result['search'] = dict(states=budget.states,elapsed_seconds=monotonic()-budget.start,
                                complete=result['status'] in {'optimal','already_resolved','impossible'})
        return result

    if 'undetermined' not in initial:
        retain(())
        result.update(status='already_resolved',optimality_verified=True)
        return finish()
    all_state = _apply(state,query_map,prefix)
    if 'undetermined' in _statuses(all_state,parsed):
        result.update(status='impossible',reason='Even all permitted truthful counts leave at least one '
                      'declared decision unresolved for this histogram.')
        return finish()
    # This sufficient fallback does not depend on optimization completing.
    retain(tuple(query_map))
    lower = Fraction(0)
    queue = [(Fraction(0),0,(),-1,state)]
    try:
        budget.check()
        chosen = _boundary_certificate(state,parsed,prefix,query_map,budget)
        if chosen is not None:
            retain(chosen)
            result.update(status='optimal',optimality_verified=True,
                          method='observed_boundary_certificate')
        else:
            keys = tuple(sorted(query_map))
            while queue:
                lower = queue[0][0]
                budget.check(new_state=True)
                cost,_,chosen,last,current = heappop(queue)
                if 'undetermined' not in _statuses(current,parsed):
                    retain(chosen)
                    result.update(status='optimal',optimality_verified=True)
                    break
                for j in range(last+1,len(keys)):
                    q=keys[j]
                    child=_condition(current,q,prefix[q],prefix[q])
                    if child == current:
                        continue
                    new=chosen+(q,)
                    heappush(queue,(cost+costs[q],len(new),new,j,child))
            else:
                raise RuntimeError('Sufficient report was lost from subset search')
    except _BudgetExceeded:
        result['reason']='Search limit reached; the displayed report is sufficient but may not be cheapest.'
    if result['optimality_verified']:
        lower=Fraction(result['report_cost_exact'])
    lower=min(lower,Fraction(result['report_cost_exact']))
    result.update(cost_lower_bound=float(lower),cost_lower_bound_exact=str(lower))
    return finish()
