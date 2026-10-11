"""Interpret declared one-sided criteria without rounding or changing guarantees."""
from fractions import Fraction
import operator


OPERATORS = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}


def parse_criterion(row):
    """Return an optional criterion; CSV fractions are decimal values on [0, 1]."""
    op = str(row.get('decision_operator', '')).strip()
    value = str(row.get('decision_fraction', '')).strip()
    if not op and not value:
        return None
    if not op or not value:
        raise ValueError('decision_operator and decision_fraction must be supplied together')
    if op not in OPERATORS:
        raise ValueError('decision_operator must be <, <=, > or >=')
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('decision_fraction must be a finite fraction on the 0 to 1 scale') from exc
    if not 0 <= fraction <= 1:
        raise ValueError('decision_fraction must be between 0 and 1; enter 0.05 for 5%')
    return {'decision_operator': op, 'decision_fraction': float(fraction),
            'decision_fraction_text': value}


def classify_intervals(intervals, op, limit):
    """Classify a nonempty union for a monotone inequality, including endpoints."""
    if not intervals:
        return 'unavailable'
    compare = OPERATORS[op]
    endpoints = [compare(x, limit) for interval in intervals for x in interval]
    return 'supported' if all(endpoints) else 'contradicted' if not any(endpoints) else 'undetermined'


def assess_population_question(lower, upper, op, limit, *, inner_lower=None, inner_upper=None):
    """Assess one projection of a fixed confidence region without a gap gate.

    The contract is lower <= inf(R) <= inner_lower <= inner_upper <= sup(R)
    <= upper. Inner endpoints need not be attained. Strict straddling alone
    certifies both answers remain possible; equality is left unresolved.
    This function neither constructs nor changes a confidence region.
    """
    lo, hi, target = Fraction(lower), Fraction(upper), Fraction(limit)
    if not 0 <= lo <= hi <= 1 or not 0 <= target <= 1:
        raise ValueError('Population bounds and target must lie in [0,1]')
    if (inner_lower is None) != (inner_upper is None):
        raise ValueError('Both population inner endpoints are required together')
    il = ih = None
    if inner_lower is not None:
        il, ih = Fraction(inner_lower), Fraction(inner_upper)
        if not lo <= il <= ih <= hi:
            raise ValueError('Invalid population inner endpoints')
    status = classify_intervals([[lo, hi]], op, target)
    if status != 'undetermined':
        assessment = 'resolved'
        text = ('The population bounds settle this question at the stated confidence level. '
                'More precise endpoints are not needed for this answer.')
    elif il is not None and il < target < ih:
        assessment = 'region_crosses_target'
        text = ('The confidence region contains proportions on both sides of the target. '
                'More computation alone cannot settle this question with the same method and information. '
                'Additional information may help; its benefit is not guaranteed.')
    else:
        assessment = 'numerically_unresolved'
        text = ('The retained population bounds do not settle this question. '
                'Further computation may help, but a decisive answer is not guaranteed.')
    return dict(status=status, calculation_assessment=assessment,
        further_computation_may_change_answer=assessment == 'numerically_unresolved',
        interpretation=text,
        assessment_scope='The selected fixed confidence region and supplied information; no sample-size recommendation.')


def decision_results(result, criteria):
    """Keep sample arithmetic exact and confidence/calibration interpretations distinct."""
    sample = result['reporting_uncertainty_envelope']['envelope']
    population = result.get('population_layer', {}).get('threshold_results', [])
    conformal = result.get('assumption_dependent_scenarios', {}).get('wasserstein_ambiguity_set', {})
    calibrated = conformal.get('guarantee_class') == 'conformal_new_cohort'
    rows = []
    for index, criterion in enumerate(criteria):
        if criterion is None:
            continue
        limit = Fraction(criterion['decision_fraction_text'])
        op = criterion['decision_operator']
        bound = sample[index]['panel_recorded_estimand']
        interval = [[Fraction(bound[side]['count'], result['sample_size']) for side in ('lower', 'upper')]]
        row = dict(criterion, threshold=sample[index]['threshold'], unit='mg/L',
                   estimand='fraction of recorded panel values strictly above the MIC threshold',
                   sample={'status': classify_intervals(interval, op, limit),
                           'guarantee': 'Sharp finite-sample bounds over all feasible declared variants; no population claim'},
                   population={'status': 'unavailable', 'reason': result.get('population_unavailable_reason', 'iid population analysis unavailable')},
                   conformal={'status': 'unavailable', 'reason': result.get('conformal_unavailable_reason', 'Compatible calibrated result unavailable')})
        if row['sample']['status'] == 'undetermined':
            row['sample']['compatible_examples'] = [dict(
                histogram=bound[side]['compatible_histogram'], count=bound[side]['count'],
                fraction=bound[side]['count']/result['sample_size'],
                reporting_variant=bound[side].get('reporting_variant', 'primary'),
                criterion_satisfied=OPERATORS[op](Fraction(bound[side]['count'], result['sample_size']), limit))
                for side in ('lower', 'upper')]
            row['sample']['examples_are_observed_data'] = False
        if population:
            exact = population[index]['exact_count_confidence']
            confidence = exact.get('simultaneous_bonferroni') or exact['marginal']
            intervals = [[Fraction(str(v)) for v in pair] for pair in confidence['confidence_set_components']]
            row['population'] = dict(status=classify_intervals(intervals, op, limit),
                confidence_level=exact['marginal']['confidence_level'],
                multiplicity='Bonferroni family' if exact.get('simultaneous_bonferroni') else 'marginal',
                guarantee='Compatibility with the exact iid confidence set, not certainty about the population')
        if calibrated:
            envelope = conformal['threshold_results'][index].get('envelope')
            if envelope is not None:
                intervals = [[Fraction(str(envelope[s])) for s in ('lower', 'upper')]]
                manifest = conformal['calibration_manifest']
                row['conformal'] = dict(status=classify_intervals(intervals, op, limit),
                    confidence_level=manifest['confidence_level'], guarantee=manifest['coverage_statement'],
                    scope=manifest['guarantee_scope'])
        rows.append(row)
    return rows
