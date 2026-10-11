"""Refine existing MIC summaries with truthful counts from the same sample.

Calibrated tail bands are retained before conditioning. Their witness histograms
need not contain the observed sample, so conditioning a transport ball directly
would not preserve a tail-only calibration guarantee.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from math import ceil, floor, isfinite
from time import monotonic

import numpy as np

from .analysis import _feasible_variants, json_safe
from .empirical import EmpiricalIdentification, EmpiricalProblem
from .exact_population import exact_count_confidence, _bonferroni_level
from .model import parse_spec
from .scenarios import maximum_entropy, kl_projection
from .utility import rank_robust_tail_count_questions, QuestionSearchTimeout
from .validation import exact_integer, positive_concentration


def _integer(value, field):
    return exact_integer(value, f"Additional count {field}", minimum=None)


def counts_from_percentage(percentage, *, n, decimal_places, rounding_rule):
    """Return all integer counts consistent with an explicitly rounded percentage.

    Values use the 0..100 scale. Supported rules are half_up, half_even, floor,
    and ceiling. Calculations use exact fractions, including boundary ties.
    """
    n = exact_integer(n, "n", minimum=1)
    places = exact_integer(decimal_places, "decimal_places", minimum=0)
    if places > 6:
        raise ValueError("decimal_places must be between 0 and 6")
    try:
        if isinstance(percentage, bool):
            raise ValueError
        value = Fraction(str(percentage))
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        raise ValueError("percentage must be a finite number on the 0..100 scale") from None
    step = Fraction(1, 10**places)
    if not 0 <= value <= 100 or (value / step).denominator != 1:
        raise ValueError("percentage must lie in 0..100 and match decimal_places")
    if rounding_rule in {"half_up", "half_even"}:
        low, high = value-step/2, value+step/2
        low_closed = rounding_rule == "half_up" or int(value/step) % 2 == 0
        high_closed = rounding_rule == "half_even" and int(value/step) % 2 == 0
    elif rounding_rule == "floor":
        low, high, low_closed, high_closed = value, value+step, True, False
    elif rounding_rule == "ceiling":
        low, high, low_closed, high_closed = value-step, value, False, True
    else:
        raise ValueError("rounding_rule must be half_up, half_even, floor or ceiling")
    low, high = n*low/100, n*high/100
    lo = max(0, ceil(low) if low_closed else floor(low)+1)
    hi = min(n, floor(high) if high_closed else ceil(high)-1)
    if lo > hi:
        raise ValueError("No integer count with this n produces the reported percentage and rounding rule")
    return lo, hi


def _count_range(row):
    return (row["count"], row["count"]) if "count" in row else (row["count_min"], row["count_max"])


def available_observations(rows, spec):
    """Defer only missing rounding metadata; malformed or conflicting data fail."""
    if not isinstance(rows, list):
        raise ValueError('additional_counts must be a list')
    usable, issues = [], []
    for index, row in enumerate(rows):
        missing = [k for k in ('decimal_places', 'rounding_rule') if isinstance(row, dict) and row.get(k) in (None, '')]
        defer = (isinstance(row, dict) and row.get('percentage') not in (None, '') and missing
                 and all(row.get(k) in (None, '') for k in ('count', 'count_min', 'count_max')))
        if not defer:
            usable.append(row)
            continue
        try:
            value = Fraction(str(row['percentage']))
        except (ValueError, ZeroDivisionError):
            raise ValueError('percentage must be a finite number on the 0..100 scale') from None
        if not 0 <= value <= 100:
            raise ValueError('percentage must lie in 0..100')
        if row.get('decimal_places') not in (None, ''):
            places = exact_integer(row['decimal_places'], 'decimal_places', 0)
            if places > 6 or (value * 10**places).denominator != 1:
                raise ValueError('percentage must match decimal_places between 0 and 6')
        if row.get('rounding_rule') not in (None, '', 'half_up', 'half_even', 'floor', 'ceiling'):
            raise ValueError('rounding_rule must be half_up, half_even, floor or ceiling')
        probe = {k: v for k, v in row.items() if k not in ('percentage', 'decimal_places', 'rounding_rule', 'count', 'count_min', 'count_max')}
        _observations([dict(probe, count=0)], spec)
        issues.append(dict(observation_number=index+1, status='not_used', original=deepcopy(row),
            missing_fields=missing, reason='Rounding information is missing: ' + ', '.join(missing) +
            '. This percentage imposes no count constraint; other valid information is retained.'))
    return (_observations(usable, spec) if usable else []), issues


def observation_coefficients(row, panel):
    """Select whole recorded categories; never split a censored category."""
    if "start_category" not in row:
        return panel.panel_tail(row["threshold"])
    a, b = panel.index(row["start_category"]), panel.index(row["end_category"])
    if a > b:
        raise ValueError("start_category must not follow end_category")
    values = np.zeros(len(panel.bins))
    values[a:b+1] = 1
    return values


def observation_label(row):
    original = row.get('source_information', {})
    if isinstance(original, dict) and original.get('source_scale') in {'recorded', 'interval'}:
        scale = 'recorded categories' if original['source_scale'] == 'recorded' else 'measurement intervals'
        details = f" (source: MIC {original.get('relation', '>')} {original.get('threshold')} mg/L; {scale})"
    else:
        details = ''
    if "start_category" in row:
        return f"in recorded categories {row['start_category']} through {row['end_category']} mg/L (both included)" + details
    try:
        threshold = f"{float(row['threshold']):g}"
    except (ValueError,TypeError):
        threshold = str(row['threshold'])
    return f"strictly above {threshold} mg/L"


class CountInformationConflict(ValueError):
    """An incompatible subset of supplied answers, conditional on the summaries."""

    def __init__(self, spec, observations):
        # Prefix closure is an exact independent feasibility calculation for
        # this contract. Deletion gives an irreducible subset, not a smallest one.
        def compatible(rows):
            for variant in spec.all_reporting_variants:
                try:
                    return EmpiricalProblem(n=spec.n, panel=spec.panel, quantiles=variant.quantiles,
                        minimum_index=variant.minimum_index, maximum_index=variant.maximum_index,
                        count_intervals=[(observation_coefficients(row, spec.panel), *_count_range(row)) for row in rows])
                except ValueError:
                    continue
            raise ValueError("No compatible reporting variant")
        indices = list(range(len(observations)))
        deadline = monotonic() + .25
        complete = True
        for index in list(indices):
            if monotonic() >= deadline:
                complete = False
                break
            trial = [j for j in indices if j != index]
            try:
                compatible([observations[j] for j in trial])
            except ValueError:
                indices = trial
        self.conflict_details = dict(observation_numbers=[i+1 for i in indices],
            observations=[observations[i] for i in indices],
            irreducible_given_summaries=complete, minimum_cardinality_claimed=False,
            conditional_on="All declared MIC summaries, rank variants and panel categories")
        descriptions = []
        for i in indices:
            row = observations[i]
            lo, hi = _count_range(row)
            count = str(lo) if lo == hi else f"{lo} to {hi}"
            descriptions.append(f"answer {i+1}: {count}/{spec.n} {observation_label(row)}")
        super().__init__("Additional counts are incompatible with every declared reporting variant. "
            "Conflicting information: " + "; ".join(descriptions) + ". Check these answers against the "
            "reported MIC50/MIC90, rank convention and panel; confirm the same original sample and "
            "denominator and the use of strictly above (>), rather than at or above (>=). No input was changed.")


def _observations(rows, spec):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("Supply at least one additional count")
    normalised, seen = [], {}
    for row in rows:
        fields = {"threshold", "unit", "count", "count_min", "count_max", "n", "source",
                  "percentage", "decimal_places", "rounding_rule", "relation", "source_relation", "source_threshold", "source_information",
                  "start_category", "end_category", "source_scale"}
        if not isinstance(row, dict) or set(row) - fields:
            raise ValueError("Additional count fields are threshold, unit, n, source and either count, count_min/count_max, or percentage/decimal_places/rounding_rule")
        if row.get("unit") not in {"mg/L", "ug/mL", "µg/mL", "μg/mL"}:
            raise ValueError("Additional count unit must explicitly be mg/L or equivalent ug/mL")
        n = _integer(row.get("n"), "n")
        present = lambda key: row.get(key) is not None and str(row[key]).strip() != ""
        exact = present("count")
        interval = any(present(k) for k in ("count_min", "count_max"))
        rounded = any(present(k) for k in ("percentage", "decimal_places", "rounding_rule"))
        if interval and rounded and not exact:
            preimage = counts_from_percentage(row.get("percentage"), n=n,
                decimal_places=row.get("decimal_places"), rounding_rule=row.get("rounding_rule"))
            if tuple(_integer(row.get(k), k) for k in ("count_min", "count_max")) != preimage:
                raise ValueError("Percentage preimage disagrees with the supplied count interval")
            interval = False
        if sum((exact, interval, rounded)) != 1:
            raise ValueError("Supply exactly one count, count_min/count_max pair, or percentage with decimal_places and rounding_rule")
        if exact:
            low = high = _integer(row["count"], "count")
            information = dict(count=low)
        elif interval:
            low, high = (_integer(row.get(k), k) for k in ("count_min", "count_max"))
            information = dict(count_min=low, count_max=high)
        else:
            low, high = counts_from_percentage(row.get("percentage"), n=n,
                decimal_places=row.get("decimal_places"), rounding_rule=row.get("rounding_rule"))
            information = dict(count_min=low, count_max=high, percentage=str(row["percentage"]),
                decimal_places=_integer(row["decimal_places"], "decimal_places"), rounding_rule=row["rounding_rule"])
        if n != spec.n or not 0 <= low <= high <= n:
            raise ValueError("Additional information must use the original n and satisfy 0 <= count_min <= count_max <= n")
        scale = row.get('source_scale') or None
        if scale not in {None, 'recorded', 'interval'}:
            raise ValueError("source_scale must be recorded or interval")
        if scale == 'interval' and (present('start_category') or present('end_category')):
            raise ValueError("A category range counts recorded categories; use source_scale=recorded")
        if scale is not None and not (present('start_category') or present('end_category')):
            threshold = positive_concentration(row.get('threshold'), 'Additional count threshold')
            relation = row.get('relation') or '>'
            if relation not in {'>', '>=', '<', '<='}:
                raise ValueError("Source relation must be <, <=, > or >=")
            if scale == 'recorded':
                comparisons = {'>': lambda x: x > threshold, '>=': lambda x: x >= threshold,
                               '<': lambda x: x < threshold, '<=': lambda x: x <= threshold}
                selected = [comparisons[relation](v) for v in spec.panel.panel_values]
            else:
                selected = []
                for category in spec.panel.bins:
                    if relation in {'>', '<='}:
                        above = category.lower is not None and (category.lower > threshold or
                                  (category.lower == threshold and not category.lower_closed))
                        below = category.upper is not None and category.upper <= threshold
                    else:
                        above = category.lower is not None and category.lower >= threshold
                        below = category.upper is not None and (category.upper < threshold or
                                  (category.upper == threshold and not category.upper_closed))
                    if not above and not below:
                        raise ValueError(f"Source interval relation crosses MIC category {category.label}; "
                                         "provide a count of whole categories or a documented finer measurement")
                    selected.append(above if relation in {'>', '>='} else below)
            original = deepcopy(row)
            indices = [i for i, included in enumerate(selected) if included]
            normalized = dict(unit='mg/L', n=n, source=str(row.get('source', '')),
                              source_information=original, **information)
            if indices:
                normalized.update(start_category=spec.panel.labels[indices[0]],
                                  end_category=spec.panel.labels[indices[-1]])
            else:
                # A zero-objective tail retains an explicitly empty category set.
                if not low <= 0 <= high:
                    raise ValueError("The source relation selects no recorded categories, so its count must allow zero")
                normalized.update(threshold=float(spec.panel.panel_values[-1]))
            row = normalized
            scale = None
        if present("start_category") or present("end_category"):
            if not all(present(k) for k in ("start_category", "end_category")):
                raise ValueError("Supply both start_category and end_category from the panel")
            if any(present(k) for k in ("threshold", "relation", "source_relation", "source_threshold")):
                raise ValueError("Choose a category interval OR a threshold relation, not both")
            if any(row[k] not in spec.panel.labels for k in ("start_category", "end_category")):
                raise ValueError("Interval endpoints must be exact category labels from the declared panel")
            key = tuple(observation_coefficients(row, spec.panel))
            if key in seen and exact and seen[key]:
                raise ValueError("Duplicate or equivalent exact additional counts")
            seen[key] = seen.get(key, False) or exact
            normalised.append(dict(start_category=row["start_category"], end_category=row["end_category"],
                unit="mg/L", **information, n=n, source=str(row.get("source", "")),
                **({"source_information": row['source_information']} if 'source_information' in row else {})))
            continue
        threshold = positive_concentration(row.get("threshold"), "Additional count threshold")
        relation = row.get("relation", ">") or ">"
        if relation not in {">", ">=", "<", "<="}:
            raise ValueError("Source relation must be <, <=, > or >=")
        original_threshold = threshold
        if relation in {"<", ">="}:
            # Equality cannot be assigned using a censored category representative.
            selected = []
            for category in spec.panel.bins:
                below = category.upper is not None and (category.upper < threshold or
                    (category.upper == threshold and not category.upper_closed))
                above = category.lower is not None and category.lower >= threshold
                if not below and not above:
                    raise ValueError("Source relation cuts an ambiguous MIC category; provide category-consistent counts or a documented finer panel")
                selected.append(int(above))
            candidates = [float(v) for v in spec.panel.panel_values if tuple(spec.panel.panel_tail(float(v))) == tuple(selected)]
            if not candidates:
                raise ValueError("Source relation cannot map to a recorded category tail; provide a documented category-consistent panel")
            threshold = candidates[0]
        if relation in {"<", "<="}:
            low, high = n-high, n-low
        if relation != ">":
            information = dict(count=low) if exact else dict(count_min=low, count_max=high)
        key = tuple(spec.panel.panel_tail(threshold))
        if key in seen and exact and seen[key]:
            raise ValueError("Duplicate or equivalent exact additional-count cuts; retain one exact count per recorded tail")
        seen[key] = seen.get(key, False) or exact
        normalised.append(dict(threshold=threshold, unit="mg/L", **information, n=n,
                               source=str(row.get("source", "")), **({"source_relation": relation,
                                   "source_threshold": original_threshold, "source_information": dict(row)} if "relation" in row else
                                   {k: row[k] for k in ("source_relation", "source_threshold", "source_information") if k in row})))
    return normalised


def _identify(spec, problem):
    results = []
    for threshold in spec.thresholds:
        lo, hi = problem.bounds(spec.panel.panel_tail(threshold))
        latent_lo = problem.bounds(spec.panel.latent_tail(threshold, upper=False))[0]
        latent_hi = problem.bounds(spec.panel.latent_tail(threshold, upper=True))[1]
        item = EmpiricalIdentification(threshold, lo, hi, latent_lo, latent_hi,
            tuple(b.label for b in spec.panel.bins if b.latent_status(threshold) == "ambiguous"), False)
        results.append(item.as_dict(spec.panel.labels))
    return results


def _envelope(spec, problems, variants, rejected):
    by_variant = {key: _identify(spec, problem) for key, problem in problems.items()}
    rows = []
    for index, threshold in enumerate(spec.thresholds):
        row = dict(threshold=threshold, guarantee_class="sharp_finite_sample")
        for estimand in ("panel_recorded_estimand", "latent_interval_estimand"):
            ends = {}
            for direction, choose in (("lower", min), ("upper", max)):
                key, value = choose(((key, value[index][estimand][direction])
                                    for key, value in by_variant.items()), key=lambda pair: pair[1]["count"])
                ends[direction] = dict(value, reporting_variant=key)
            row[estimand] = dict(ends, width=ends["upper"]["fraction"]-ends["lower"]["fraction"],
                                 sharp_over_declared_union=True)
        rows.append(row)
    return dict(guarantee_class="sharp_finite_sample", variant_probabilities_assigned=False,
                automatic_reporting_convention_guessing=False, envelope=rows,
                rejected_variants=rejected, per_variant=[dict(id=key,
                    declared_summary=variants[key].as_dict(spec.panel)["summaries"],
                    guarantee_class="sharp_finite_sample", identification=value)
                    for key, value in by_variant.items()]), by_variant


class _BandProblem(EmpiricalProblem):
    """An integer prefix polytope restricted by the original calibrated bands."""
    def __init__(self, problem, bands):
        self.bands = bands
        super().__init__(n=problem.n, panel=problem.panel, quantiles=problem.quantiles,
                         minimum_index=problem.minimum_index, maximum_index=problem.maximum_index,
                         equalities=problem.equalities, count_intervals=problem.count_intervals)

    def _build_constraints(self):
        matrix, lower, upper = super()._build_constraints()
        return (np.vstack([matrix]+[x[0] for x in self.bands]),
                np.r_[lower, [x[1] for x in self.bands]], np.r_[upper, [x[2] for x in self.bands]])


def _calibrated_update(result, spec, problems):
    conf = result["assumption_dependent_scenarios"].get("wasserstein_ambiguity_set")
    if not conf:
        return
    original = deepcopy(conf["threshold_results"])
    calibrated = conf.get("guarantee_class") == "conformal_new_cohort" and conf.get("calibration_manifest") is not None
    conf["original_threshold_results"] = original
    conf["update_rule"] = "unchanged_tail_bands_and_truthful_counts"
    conf["distribution_coverage_claimed"] = False
    conf["coverage_scope"] = "original requested recorded panel tails"
    allowance = max(1e-7, 8*spec.n*np.finfo(float).eps)
    conf["integer_endpoint_allowance_counts"] = allowance
    try:
        bands = []
        for row in original:
            band = row.get("envelope")
            if not band or not all(isfinite(band[x]) for x in ("lower", "upper")):
                raise ValueError("Original calibration has an unavailable tail band")
            lo, hi = band["lower"], band["upper"]
            if lo < -1e-12 or hi > 1+1e-12 or lo > hi+1e-12:
                raise ValueError("Original calibration has an invalid tail band")
            bands.append((spec.panel.panel_tail(row["threshold"]),
                          max(0, ceil(spec.n*lo-allowance)), min(spec.n, floor(spec.n*hi+allowance))))
        lifted, conflicts = {}, []
        for key, problem in problems.items():
            try:
                lifted[key] = _BandProblem(problem, bands)
            except ValueError as exc:
                conflicts.append(dict(id=key, reason=str(exc)))
        conf["count_incompatible_variants"] = conflicts
        if not lifted:
            raise ValueError("Additional counts are incompatible with the original calibrated tail bands")
        updated = []
        for threshold in spec.thresholds:
            values = []
            for key, problem in lifted.items():
                lo, hi = problem.bounds(spec.panel.panel_tail(threshold))
                values.append(dict(id=key, available=True, lower=lo.fraction, upper=hi.fraction,
                                   lower_witness=lo.as_dict(spec.panel.labels), upper_witness=hi.as_dict(spec.panel.labels)))
            updated.append(dict(threshold=threshold, per_variant=values, envelope=dict(
                lower=min(x["lower"] for x in values), upper=max(x["upper"] for x in values))))
        conf["threshold_results"] = updated
        if calibrated:
            result.pop("conformal_unavailable_reason", None)
        conf["update_interpretation"] = ("The original simultaneous tail event is preserved for truthful counts from the same sample, "
            "including adaptively selected counts. The reference, radius, target family and guarantee level are unchanged. "
            "No full-distribution or latent-MIC coverage is added. The displayed integer allowance is numerical, not a solver-error bound." if calibrated else
            "Uncalibrated sensitivity scenario restricted by truthful counts. No coverage guarantee is assigned.")
    except (ValueError, RuntimeError, ArithmeticError) as exc:
        reason = "Calibrated update unavailable: "+str(exc)
        result["conformal_unavailable_reason"] = reason
        conf["threshold_results"] = [dict(threshold=t, per_variant=[], envelope=None, reason=reason) for t in spec.thresholds]


def _population_update(result, spec, problems, confidence, envelope, selected):
    try:
        rows = []
        for index, threshold in enumerate(spec.thresholds):
            objective = spec.panel.panel_tail(threshold)
            marginal = exact_count_confidence(problems=problems, objective=objective, confidence_level=confidence).as_dict()
            simultaneous = None if len(spec.thresholds) == 1 else exact_count_confidence(
                problems=problems, objective=objective,
                confidence_level=_bonferroni_level(confidence,len(spec.thresholds))).as_dict()
            rows.append(dict(threshold=threshold, guarantee_class="exact_iid_population",
                exact_count_confidence=dict(marginal=marginal, simultaneous_bonferroni=simultaneous,
                    multiplicity_rule="bonferroni", family_size=len(spec.thresholds)),
                optional_efficiency_analysis=dict(enabled=False, available=False, reason="disabled in count-update workflow"),
                bayesian_sensitivity=dict(enabled=False), separate_observed_sample_identification=selected[index]))
        result["population_layer"] = dict(guarantee_class="exact_iid_population", sample_size=spec.n,
            sampling_model="iid categorical sampling", reporting_uncertainty_envelope=envelope,
            threshold_results=rows, population_mle=None,
            warnings=["The target family must be fixed before observing the returned counts; truthful adaptive queries are permitted."])
        result.pop("population_unavailable_reason", None)
    except (ValueError, RuntimeError, ArithmeticError) as exc:
        result.pop("population_layer", None)
        result["population_unavailable_reason"] = "Population update failed: "+str(exc)


def _scenarios_and_questions(result, spec, problems, selected_id):
    scenarios = result["assumption_dependent_scenarios"]
    for name, calculate in (("maximum_entropy", lambda: maximum_entropy(problems[selected_id])),
        ("kl_reference_projection", lambda: kl_projection(problems[selected_id], spec.reference_distribution))):
        if name == "kl_reference_projection" and spec.reference_distribution is None:
            scenarios.pop(name, None)
            continue
        try:
            value = calculate()
            scenarios[name] = dict(guarantee_class="assumption_scenario", reporting_variant=selected_id,
                **value.as_dict(spec.panel.labels), tail_estimates={f"{t:g}": value.tail(spec.panel.panel_tail(t)) for t in spec.thresholds})
        except (ValueError, RuntimeError, ArithmeticError) as exc:
            scenarios[name] = dict(guarantee_class="assumption_scenario", available=False, conflict=str(exc))
    result["one_question_recovery"] = None
    if spec.question_options.get("enabled", True):
        complete = True
        try:
            ranked = rank_robust_tail_count_questions(problems=problems,
                target_objectives=[spec.panel.panel_tail(t) for t in spec.thresholds],
                exclude_direct_targets=bool(spec.question_options.get("exclude_direct_target_questions", False)),
                costs=dict(spec.question_options.get("costs", {})),
                time_limit_seconds=spec.question_options.get("time_limit_seconds", 10.0))
        except QuestionSearchTimeout as exc:
            complete = False
            ranked = sorted(exc.completed_scores, key=lambda x: x.score_per_cost, reverse=True)
            result["warnings"].append(str(exc))
        except (ValueError, RuntimeError, ArithmeticError) as exc:
            complete, ranked = False, []
            result["warnings"].append("Updated question search failed: "+str(exc))
        result["one_question_recovery"] = dict(guarantee_class="sharp_finite_sample",
            criterion="exact minimax reduction in the sum of remaining envelope widths per unit acquisition cost",
            search_complete=complete, optimality_claimed=complete,
            best_question=ranked[0].as_dict() if complete and ranked and ranked[0].minimax_width_reduction > 1e-12 else None,
            ranked_questions=[x.as_dict() for x in ranked[:10]],
            direct_target_questions_excluded=bool(spec.question_options.get("exclude_direct_target_questions", False)))


def analyse_with_counts(raw_spec, additional_counts, *, iid=False, confidence=.95, calibration=None):
    """Apply recorded-tail counts, retaining the original calibration event.

All counts must concern the original cohort and denominator. The target family,
panel and declared rank variants stay fixed. This API accepts empirical inputs;
``iid=True`` additionally requests exact population confidence sets.
"""
    from .workflows import analyse_layers
    spec = parse_spec(raw_spec)
    if spec.mode != "empirical":
        raise ValueError("Additional counts require an empirical specification; use iid=True for the population layer")
    if not isinstance(iid, bool) or isinstance(confidence, bool) or not 0 < confidence < 1:
        raise ValueError("iid must be boolean and confidence must lie strictly in (0, 1)")
    observations = _observations(additional_counts, spec)
    baseline = analyse_layers(raw_spec, iid, confidence, calibration)
    result = deepcopy(baseline)
    info = dict(status="applied", observations=observations, estimand="recorded panel MIC > threshold",
                original_denominator=spec.n, original_target_family=list(spec.thresholds),
                assumptions="Truthful aggregate counts from the same original cohort; no replacement or additional isolates")
    try:
        original_problems, variants, rejected = _feasible_variants(spec)
        problems = {}
        for key, problem in original_problems.items():
            try:
                for observation in observations:
                    coefficients = observation_coefficients(observation, spec.panel)
                    if "count" in observation:
                        problem = problem.with_equality(coefficients, observation["count"])
                    else:
                        problem = problem.with_count_interval(coefficients, *_count_range(observation))
                problems[key] = problem
            except ValueError as exc:
                rejected.append(dict(id=key, reason="Additional counts: "+str(exc)))
        if not problems:
            raise CountInformationConflict(spec, observations)
        envelope, by_variant = _envelope(spec, problems, variants, rejected)
    except RuntimeError as exc:
        result["additional_information"] = dict(info, status="unavailable", reason=str(exc), observed_width_reduction=None)
        result["warnings"].append("Additional-count analysis failed; displayed results use the original summaries only: "+str(exc))
        return json_safe(result)
    selected_id = "primary" if "primary" in problems else next(iter(problems))
    result["reporting_uncertainty_envelope"] = envelope
    result["identification"] = by_variant[selected_id]
    before = baseline["reporting_uncertainty_envelope"]["envelope"]
    comparisons = []
    for old, new in zip(before, envelope["envelope"]):
        comparisons.append(dict(threshold=new["threshold"],
            before_counts=[old["panel_recorded_estimand"][x]["count"] for x in ("lower", "upper")],
            after_counts=[new["panel_recorded_estimand"][x]["count"] for x in ("lower", "upper")]))
    info.update(per_threshold=comparisons, observed_width_reduction=sum(
        (x["before_counts"][1]-x["before_counts"][0]-x["after_counts"][1]+x["after_counts"][0])/spec.n for x in comparisons))
    result["additional_information"] = info
    if iid:
        _population_update(result, spec, problems, confidence, envelope, by_variant[selected_id])
    _calibrated_update(result, spec, problems)
    _scenarios_and_questions(result, spec, problems, selected_id)
    return json_safe(result)
