"""Common-result adapter for the fixed monotone Hunter/moment region."""
from fractions import Fraction
from time import monotonic

from ._hunter import score


def hunter_population(problems, *, confidence_level, time_limit_seconds,
                      tolerance_pp, include_intervals, width_target_pp=None):
    from .joint_population import _validate, _constraint_signature

    n, k = _validate(problems)
    alpha = 1-Fraction(float(confidence_level))
    started = monotonic()
    options = dict(alpha=alpha, tolerance_pp=tolerance_pp,
                   width_target_pp=width_target_pp)
    # This is the selected construction's own outer envelope. It is retained
    # if an optional allocation, solver or refinement step fails.
    baseline = score.project(problems, time_limit_seconds=0, **options)
    baseline_seconds = monotonic()-started
    raw = baseline
    failure = None
    refinement_start = monotonic()
    effective_budget = min(time_limit_seconds, 1800.)
    if effective_budget > 0 and baseline['status'] != 'width_goal_assessed':
        try:
            raw = score.project(problems, time_limit_seconds=effective_budget, **options)
        except (MemoryError, TimeoutError, ArithmeticError, RuntimeError) as exc:
            failure = type(exc).__name__ + ': ' + str(exc)

    def projections(rows):
        by_range = {(x['start'], x['stop']): x for x in rows}
        return (
            [[by_range[0,b]['lower'], by_range[0,b]['upper']] for b in range(1,k)],
            [[by_range[a,a+1]['lower'], by_range[a,a+1]['upper']] for a in range(k)])

    cdf, categories = projections(raw['intervals'])
    baseline_cdf, baseline_categories = projections(baseline['intervals'])
    gaps = [x['endpoint_gap_pp'] for x in raw['intervals']]
    status = ('calculation_incomplete' if failure else
              'complete' if raw['precision_certified'] else raw['status'])
    result = dict(requested_method='range-hunter', method='range-hunter',
        statistical_target=raw['method'], confidence_level=confidence_level,
        constraint_signature=_constraint_signature(problems),
        family_size=k*(k-1)//2, family_kind='all_contiguous_ranges_up_to_complements',
        sample_size=n, numerical_tolerance_pp=tolerance_pp,
        bounds_kind='conservative_outer', status=status,
        precision_reached=raw['precision_certified'] and failure is None,
        endpoint_gap_pp=max(gaps) if all(x is not None for x in gaps) else None,
        cdf_bounds=cdf, category_bounds=categories,
        baseline_cdf_bounds=baseline_cdf, baseline_category_bounds=baseline_categories,
        guarantee='Simultaneous finite-sample coverage under iid sampling on the fixed recorded panel; '
                  'all contiguous category ranges; no within-category reconstruction.',
        numerical_certificate='Exact count and score constraints, directed probability bounds, '
                              'certified Hunter/moment exclusions and attained inner witnesses; '
                              'unprocessed regions remain in the outer cover.',
        elapsed_seconds=monotonic()-started, baseline_seconds=baseline_seconds,
        refinement_seconds=monotonic()-refinement_start,
        time_limit_scope='optional_original_region_refinement',
        requested_time_limit_seconds=time_limit_seconds,
        effective_time_limit_seconds=effective_budget,
        box_count=raw['nodes_visited'], excluded_boxes=raw['nodes_discarded'],
        retained_nodes=raw['nodes_retained'], question_certificates=[],
        accepted_witness_count=len(raw['accepted_witnesses']),
        algebraic_witness_count=len(raw['algebraic_witnesses']))
    if 'width_goal' in raw:
        result['width_goal'] = raw['width_goal']
    if failure:
        result.update(reason='Optional refinement failure; valid bounds from the selected method are retained.',
                      calculation_diagnostic=failure)
    elif status in ('time_limit', 'calculation_incomplete', 'precision_unresolved'):
        result['reason'] = ('Valid population bounds are available. The requested numerical endpoint '
                            'precision is not yet confirmed; this does not change the confidence level.')
        if raw.get('error'):
            result['calculation_diagnostic'] = raw['error']
    if include_intervals or width_target_pp is not None:
        result['interval_bounds'] = [dict(start_index=x['start'], stop_index=x['stop'],
            lower=x['lower'], upper=x['upper'], inner_lower=x['inner_lower'],
            inner_upper=x['inner_upper'],
            **({'width_status':x['width_status']} if 'width_status' in x else {}))
            for x in raw['intervals']]
    return result


def refresh_projection_metadata(result):
    """Reassess saved width and endpoint certificates after outer intersection."""
    rows = result.get('interval_bounds')
    if not rows:
        return
    gaps = []
    target = result.get('width_goal', {}).get('target_pp_text',result.get('width_goal', {}).get('target_pp'))
    statuses = []
    for row in rows:
        lo, hi = Fraction(row['lower']), Fraction(row['upper'])
        il, iu = row.get('inner_lower'), row.get('inner_upper')
        if il is not None and iu is not None:
            il, iu = Fraction(il), Fraction(iu)
            gaps.append(max(il-lo, hi-iu, Fraction(0)))
        else:
            gaps.append(None)
        if target is not None:
            state = score.width_status(lo,hi,il,iu,Fraction(str(target))/100)
            row['width_status'] = state
            statuses.append(state)
    gap = max(gaps) if all(x is not None for x in gaps) else None
    result['endpoint_gap_pp'] = None if gap is None else score.kernel._float(100*gap,True)
    result['precision_reached'] = gap is not None and gap <= Fraction(str(result['numerical_tolerance_pp']))/100
    if result['status']=='complete' and not result['precision_reached']:
        result['status'] = 'precision_unresolved'
    if statuses:
        result['width_goal'].update(
            status='met' if all(x=='met' for x in statuses) else
                   'not_met' if any(x=='not_met' for x in statuses) else 'unresolved',
            all_ranges_assessed=all(x!='unresolved' for x in statuses))
