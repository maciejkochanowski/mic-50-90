"""Decision projections of the existing whole-distribution layers."""
from fractions import Fraction
from math import nextafter, inf
from .decisions import classify_intervals, assess_population_question
from .exact_population import _merge_integer_ranges
from .distribution_targets import read_targets, event_text, possible_objective


def _endpoint(value, upper):
    # Preserve the engine's binary value and the serialized decimal value.
    return (max if upper else min)(Fraction(value), Fraction(str(value)))


def _projection(layer, start, stop, k):
    """Project the same simultaneous region; do not add a new marginal test."""
    if start == stop:
        return Fraction(0), Fraction(0), 0., 0.
    if start == 0 and stop == k:
        return Fraction(1), Fraction(1), 1., 1.
    for row in layer.get('interval_bounds', []):
        if (row['start_index'], row['stop_index']) == (start, stop):
            return (_endpoint(row['lower'], False), _endpoint(row['upper'], True),
                    row.get('inner_lower'), row.get('inner_upper'))
    # The fixed total is at boundary k even when a caller supplies only a
    # prefix of the CDF. Missing internal boundaries carry no information.
    cdf = [(Fraction(0), Fraction(0))] + [(Fraction(0), Fraction(1))] * (k - 1)
    for i, row in enumerate(layer['cdf'][:k-1], start=1):
        cdf[i] = (_endpoint(row['lower'], False), _endpoint(row['upper'], True))
    cdf.append((Fraction(1), Fraction(1)))
    return (max(Fraction(0), cdf[stop][0] - cdf[start][1]),
            min(Fraction(1), cdf[stop][1] - cdf[start][0]), None, None)


def _outward_float(value, upper):
    result = float(value)
    if (Fraction(result) < value if upper else Fraction(result) > value):
        result = nextafter(result, inf if upper else -inf)
    return result


def distribution_decisions(raw, problems, population, calibration):
    first = next(iter(problems.values()))
    rows = []
    for metadata, objective, criterion in read_targets(raw.get('targets', []), first.panel):
        possible = possible_objective(metadata, first.panel)
        ranges = {key: [p.bounds(objective)[0].count, p.bounds(possible)[1].count]
                  for key,p in problems.items()}
        components = [list(x) for x in _merge_integer_ranges([tuple(x) for x in ranges.values()])]
        op, limit = ((criterion['decision_operator'], Fraction(criterion['decision_fraction_text']))
                     if criterion else (None, None))
        sample = dict(status=classify_intervals([[Fraction(x,first.n) for x in c] for c in components],op,limit) if criterion else 'available',count_components=components,variant_count_ranges=ranges,
                      guarantee='Sharp sample bounds over every feasible declared variant; no population claim')
        row = dict(criterion or {}, **metadata, estimand='fraction with ' + event_text(metadata), sample=sample)
        if metadata['measurement_ambiguous_categories']:
            row['measurement_explanation'] = ('The threshold lies within measured categories: ' +
                ', '.join(metadata['measurement_ambiguous_categories']) +
                '. Counts of these categories cannot locate MIC within them. More detailed measurements or documented original readings are needed to remove this ambiguity.')
        start, stop = metadata['start_index'], metadata['stop_index']
        cut = start - 1
        for name, layer in [('population',population),('calibration',calibration)]:
            value = dict(status='unavailable',reason=layer.get('reason','Compatible layer unavailable'))
            if layer.get('cdf'):
                lo, hi, inner_lo, inner_hi = _projection(layer, start, stop, first.k)
                if metadata.get('possible_start_index', start) != start:
                    _, hi, _, inner_hi = _projection(layer, metadata['possible_start_index'], stop, first.k)
                value=dict(status=classify_intervals([[lo,hi]],op,limit) if criterion else 'available',lower=_outward_float(lo, False),upper=_outward_float(hi, True),
                    guarantee=layer.get('guarantee','Projection of the simultaneous all-panel population family'),confidence_level=layer.get('confidence_level'),scope=layer.get('coverage_scope','all panel tails'))
                if name == 'population' and criterion is not None:
                    if inner_lo is None or inner_hi is None:
                        inner_lo = inner_hi = None
                    value.update(assess_population_question(lo, hi, op, limit,
                        inner_lower=inner_lo, inner_upper=inner_hi))
                    if (layer.get('method') == 'joint-exact' and metadata['question_type'] == 'threshold'
                            and not metadata['measurement_ambiguous_categories']):
                        from .joint_population import _constraint_signature
                        signature = _constraint_signature(problems)
                        for certificate in layer.get('question_certificates', []):
                            if (certificate.get('status') != 'excluded' or certificate.get('cut_index') != cut
                                or certificate.get('fraction') != str(limit)
                                or certificate.get('method') != 'joint-exact'
                                or certificate.get('constraint_signature') != signature
                                or certificate.get('confidence_level') != layer.get('confidence_level')):
                                continue
                            relation = certificate.get('tail_relation')
                            if relation not in ('<', '>'):
                                continue
                            proved = 'supported' if (op in ('<','<=')) == (relation=='<') else 'contradicted'
                            if (value['status'] not in ('undetermined', proved)
                                or value.get('calculation_assessment') == 'region_crosses_target'):
                                value.update(status='unavailable',calculation_assessment='unavailable',
                                    reason='Population certificates conflict; the sample result remains available.',
                                    interpretation='Population certificates conflict; check the analysis before using a population conclusion.')
                                break
                            value.update(status=proved,calculation_assessment='resolved',
                                further_computation_may_change_answer=False,decision_certificate=certificate,
                                interpretation='A direct calculation settles this criterion at the stated confidence level. '
                                    'The displayed population intervals remain conservative; this conclusion does not require more precise endpoints.')
            row[name]=value
        rows.append(row)
    return rows
