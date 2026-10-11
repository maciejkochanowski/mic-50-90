"""High-level v1 analysis orchestration and strict output contract."""

from __future__ import annotations

from math import isfinite
from typing import Any

import numpy as np

from ._version import __version__
from .bayes import dirichlet_posterior_tail
from .dro import wasserstein_bounds, project_onto_sharp_set
from .empirical import EmpiricalIdentification, EmpiricalProblem, empirical_bounds
from .exact_population import exact_count_confidence, _bonferroni_level
from .model import ParsedSpec, ReportingVariant, _nonnegative_integer, parse_spec
from .population import fit_population_mle, profile_likelihood
from .scenarios import kl_projection, maximum_entropy
from .utility import rank_robust_tail_count_questions, QuestionSearchTimeout


def json_safe(value: Any) -> Any:
    """Convert nested NumPy values and non-finite floats to strict JSON values."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return [json_safe(item) for item in value.tolist()]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        numeric = float(value)
        return numeric if isfinite(numeric) else None
    return value


def _metadata(spec: ParsedSpec) -> dict[str, Any]:
    adapter = None
    if spec.input_contract_version == "4.0":
        adapter = {
            "from": "4.0",
            "to": "1.0",
            "semantic_change": False,
            "note": "The v4 summaries are treated as the single primary reporting variant.",
        }
    return {
        "software": "MIC-50-90",
        "version": __version__,
        "contract_version": "1.0",
        "input_contract_version": spec.input_contract_version,
        "input_adapter": adapter,
        "mode": spec.mode,
        "inference_requested": {"population": spec.mode == "population",
                                "calibration": spec.wasserstein_calibration_manifest is not None},
        "sample_size": spec.n,
        **({"reported_summaries_variant": spec.representative_variant_id,
            "declared_reporting_summaries": list(spec.declared_reporting_summaries)}
           if spec.representative_variant_id != "primary" else {}),
        "panel": spec.panel.as_dict(),
        "reported_summaries": {
            "quantiles": [item.as_dict() for item in spec.quantiles],
            "minimum": (
                None
                if spec.minimum_index is None
                else spec.panel.bins[spec.minimum_index].label
            ),
            "maximum": (
                None
                if spec.maximum_index is None
                else spec.panel.bins[spec.maximum_index].label
            ),
        },
        "thresholds": list(spec.thresholds),
        "guarantee_classes": [
            "sharp_finite_sample",
            "exact_iid_population",
            "conformal_new_cohort",
            "assumption_scenario",
        ],
    }


def _variant_problem(spec: ParsedSpec, variant: ReportingVariant) -> EmpiricalProblem:
    return EmpiricalProblem(
        n=spec.n,
        panel=spec.panel,
        quantiles=variant.quantiles,
        minimum_index=variant.minimum_index,
        maximum_index=variant.maximum_index,
    )


def _feasible_variants(
    spec: ParsedSpec,
) -> tuple[dict[str, EmpiricalProblem], dict[str, ReportingVariant], list[dict[str, str]]]:
    problems: dict[str, EmpiricalProblem] = {}
    variants: dict[str, ReportingVariant] = {}
    rejected = [dict(item) for item in spec.rejected_reporting_variants]
    for variant in spec.all_reporting_variants:
        try:
            problems[variant.identifier] = _variant_problem(spec, variant)
            variants[variant.identifier] = variant
        except ValueError as exc:
            rejected.append({"id": variant.identifier, "reason": str(exc)})
    if not problems:
        raise ValueError("Every declared reporting variant is mathematically impossible")
    return problems, variants, rejected


def _variant_identification(
    spec: ParsedSpec, variant: ReportingVariant
) -> list[EmpiricalIdentification]:
    return [
        empirical_bounds(
            n=spec.n,
            panel=spec.panel,
            quantiles=variant.quantiles,
            threshold=threshold,
            minimum_index=variant.minimum_index,
            maximum_index=variant.maximum_index,
        )
        for threshold in spec.thresholds
    ]


def _sharp_reporting_envelope(
    *,
    spec: ParsedSpec,
    variants: dict[str, ReportingVariant],
    rejected: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, list[EmpiricalIdentification]]]:
    labels = spec.panel.labels
    raw_results = {
        identifier: _variant_identification(spec, variant)
        for identifier, variant in variants.items()
    }
    per_variant = []
    for identifier, variant in variants.items():
        per_variant.append(
            {
                "id": identifier,
                "declared_summary": variant.as_dict(spec.panel)["summaries"],
                "guarantee_class": "sharp_finite_sample",
                "identification": [item.as_dict(labels) for item in raw_results[identifier]],
            }
        )
    envelope: list[dict[str, Any]] = []
    for index, threshold in enumerate(spec.thresholds):
        indexed = [(identifier, values[index]) for identifier, values in raw_results.items()]

        def endpoint(estimand: str, direction: str) -> dict[str, Any]:
            attribute = f"{estimand}_{direction}"
            candidates = [
                (identifier, getattr(result, attribute)) for identifier, result in indexed
            ]
            chosen = (
                min(candidates, key=lambda item: item[1].count)
                if direction == "lower"
                else max(candidates, key=lambda item: item[1].count)
            )
            return {
                "reporting_variant": chosen[0],
                **chosen[1].as_dict(labels),
            }

        panel_lower = endpoint("panel", "lower")
        panel_upper = endpoint("panel", "upper")
        latent_lower = endpoint("latent", "lower")
        latent_upper = endpoint("latent", "upper")
        envelope.append(
            {
                "threshold": threshold,
                "guarantee_class": "sharp_finite_sample",
                "panel_recorded_estimand": {
                    "lower": panel_lower,
                    "upper": panel_upper,
                    "width": panel_upper["fraction"] - panel_lower["fraction"],
                    "sharp_over_declared_union": True,
                },
                "latent_interval_estimand": {
                    "lower": latent_lower,
                    "upper": latent_upper,
                    "width": latent_upper["fraction"] - latent_lower["fraction"],
                    "sharp_over_declared_union": True,
                },
            }
        )
    return (
        {
            "guarantee_class": "sharp_finite_sample",
            "variant_probabilities_assigned": False,
            "automatic_reporting_convention_guessing": False,
            "per_variant": per_variant,
            "envelope": envelope,
            "rejected_variants": rejected,
        },
        raw_results,
    )


def _wasserstein_scenario(
    *, spec: ParsedSpec, problems: dict[str, EmpiricalProblem], warnings: list[str]
) -> dict[str, Any] | None:
    if spec.reference_distribution is None or spec.wasserstein_radius is None:
        return None
    manifest = spec.wasserstein_calibration_manifest
    contract = {} if manifest is None else manifest["calibration_contract"]
    reference_rule = contract.get("reference_rule", "raw")
    references = {}
    reference_errors = {}
    for identifier, problem in problems.items():
        try:
            references[identifier] = (project_onto_sharp_set(problem=problem, reference=spec.reference_distribution)[1]
                                     if reference_rule == "projected" else spec.reference_distribution)
        except (ValueError, RuntimeError) as exc:
            reference_errors[identifier] = str(exc)
    threshold_results: list[dict[str, Any]] = []
    for threshold in spec.thresholds:
        objective = spec.panel.panel_tail(threshold)
        variant_results: list[dict[str, Any]] = []
        for identifier, problem in problems.items():
            try:
                if identifier in reference_errors:
                    raise RuntimeError(reference_errors[identifier])
                bound = wasserstein_bounds(
                    problem=problem,
                    reference=references[identifier],
                    radius=spec.wasserstein_radius,
                    objective=objective,
                )
                variant_results.append({"id": identifier, **bound.as_dict(spec.panel.labels)})
            except (ValueError, RuntimeError) as exc:
                variant_results.append(
                    {"id": identifier, "available": False, "conflict": str(exc)}
                )
                warnings.append(f"Wasserstein variant {identifier}: {exc}")
        available = [item for item in variant_results if item.get("available", True)]
        threshold_results.append(
            {
                "threshold": threshold,
                "per_variant": variant_results,
                "envelope": None
                if len(available) != len(problems)
                else {
                    "lower": min(float(item["lower"]) for item in available),
                    "upper": max(float(item["upper"]) for item in available),
                },
            }
        )
    calibrated = spec.wasserstein_calibration_manifest is not None
    return {
        "guarantee_class": (
            "conformal_new_cohort" if calibrated else "assumption_scenario"
        ),
        "single_set_simultaneous_for_all_thresholds": True,
        "distribution_coverage_claimed": contract.get("score_kind") == "distribution_distance",
        "reference_rule": reference_rule,
        "coverage_scope": contract.get("functional_scope", "assumption scenario"),
        "calibration_manifest": spec.wasserstein_calibration_manifest,
        "radius": spec.wasserstein_radius,
        **({"normalized_radius": manifest["radius"], "transport_scale": spec.calibration_transport_scale}
           if contract.get("transport_scaling") is not None else {}),
        "threshold_results": threshold_results,
        "interpretation": (
            manifest["coverage_statement"]
            if calibrated
            else "User-specified Wasserstein sensitivity scenario without a coverage guarantee."
        ),
    }


def _empirical_analysis(spec: ParsedSpec) -> dict[str, Any]:
    problems, variants, rejected = _feasible_variants(spec)
    reporting_envelope, raw_identification = _sharp_reporting_envelope(
        spec=spec, variants=variants, rejected=rejected
    )
    selected_id = "primary" if "primary" in variants else next(iter(variants))
    selected_problem = problems[selected_id]
    selected_identification = raw_identification[selected_id]
    labels = spec.panel.labels
    warnings: list[str] = []

    scenarios: dict[str, Any] = {}
    try:
        entropy = maximum_entropy(selected_problem)
        scenarios["maximum_entropy"] = {
            "guarantee_class": "assumption_scenario",
            "reporting_variant": selected_id,
            **entropy.as_dict(labels),
            "tail_estimates": {
                f"{threshold:g}": entropy.tail(spec.panel.panel_tail(threshold))
                for threshold in spec.thresholds
            },
        }
    except (ValueError, RuntimeError) as exc:
        scenarios["maximum_entropy"] = {
            "guarantee_class": "assumption_scenario", "available": False,
            "reporting_variant": selected_id, "conflict": str(exc),
        }
        warnings.append("Maximum-entropy scenario unavailable: " + str(exc))
    if spec.reference_distribution is not None:
        try:
            projection = kl_projection(selected_problem, spec.reference_distribution)
            scenarios["kl_reference_projection"] = {
                "guarantee_class": "assumption_scenario",
                "reporting_variant": selected_id,
                **projection.as_dict(labels),
                "tail_estimates": {
                    f"{threshold:g}": projection.tail(spec.panel.panel_tail(threshold))
                    for threshold in spec.thresholds
                },
            }
        except (ValueError, RuntimeError) as exc:
            scenarios["kl_reference_projection"] = {
                "guarantee_class": "assumption_scenario",
                "available": False,
                "conflict": str(exc),
            }
            warnings.append(str(exc))
    wasserstein = _wasserstein_scenario(spec=spec, problems=problems, warnings=warnings)
    if wasserstein is not None:
        scenarios["wasserstein_ambiguity_set"] = wasserstein

    utility: dict[str, Any] | None = None
    if bool(spec.question_options.get("enabled", True)):
        search_complete = True
        try:
            ranked = rank_robust_tail_count_questions(
                problems=problems,
                target_objectives=[spec.panel.panel_tail(value) for value in spec.thresholds],
                exclude_direct_targets=bool(
                    spec.question_options.get("exclude_direct_target_questions", False)
                ),
                costs=dict(spec.question_options.get("costs", {})),
                time_limit_seconds=spec.question_options.get("time_limit_seconds", 10.0),
            )
        except QuestionSearchTimeout as exc:
            search_complete = False
            ranked = sorted(exc.completed_scores, key=lambda q: q.score_per_cost, reverse=True)
            warnings.append(str(exc))
        except RuntimeError as exc:
            search_complete = False
            ranked = []
            warnings.append("Question search failed: " + str(exc))
        utility = {
            "guarantee_class": "sharp_finite_sample",
            "criterion": (
                "exact minimax reduction in the sum of envelope widths across all thresholds "
                "and all declared reporting variants, per unit acquisition cost"
            ),
            "search_complete": search_complete,
            "optimality_claimed": search_complete,
            "best_question": (ranked[0].as_dict() if search_complete and ranked
                              and ranked[0].minimax_width_reduction > 1e-12 else None),
            "ranked_questions": [item.as_dict() for item in ranked[:10]],
            "direct_target_questions_excluded": bool(
                spec.question_options.get("exclude_direct_target_questions", False)
            ),
        }

    return {
        **_metadata(spec),
        "guarantee_class": "sharp_finite_sample",
        "estimand": (
            "finite-sample fraction of isolates above each threshold; no source-population interpretation"
        ),
        "identification": [item.as_dict(labels) for item in selected_identification],
        "reporting_uncertainty_envelope": reporting_envelope,
        "assumption_dependent_scenarios": scenarios,
        "one_question_recovery": utility,
        "warnings": warnings,
        "interpretation_notes": [
            "Compatible histograms are mathematical witnesses, not reconstructed observations.",
            "No probabilities are assigned to declared reporting variants.",
            "Maximum-entropy and KL outputs are assumption scenarios, not identified estimates.",
            "The tool does not estimate ECOFFs, resistance prevalence, breakpoints, or clinical decisions.",
        ],
    }


def _population_analysis(spec: ParsedSpec) -> dict[str, Any]:
    problems, variants, rejected = _feasible_variants(spec)
    reporting_envelope, raw_identification = _sharp_reporting_envelope(
        spec=spec, variants=variants, rejected=rejected
    )
    selected_id = "primary" if "primary" in variants else next(iter(variants))
    selected = variants[selected_id]
    labels = spec.panel.labels
    options = spec.population_options
    exact_options = dict(options.get("exact_count_confidence", {}))
    confidence_level = float(
        exact_options.get("confidence_level", options.get("confidence_level", 0.95))
    )
    if not 0 < confidence_level < 1:
        raise ValueError("population confidence level must lie in (0, 1)")
    multiplicity = str(exact_options.get("multiplicity", "bonferroni"))
    if multiplicity not in {"bonferroni", "none"}:
        raise ValueError("exact_count_confidence.multiplicity must be 'bonferroni' or 'none'")
    simultaneous_level = _bonferroni_level(confidence_level, len(spec.thresholds))

    efficiency_enabled = bool(options.get("profile_likelihood_enabled", True))
    bayes_enabled = bool(options.get("bayes_enabled", False))
    mle = None
    optional_warnings = []
    mle_reason = None
    if efficiency_enabled:
        try:
            mle = fit_population_mle(
                k=len(spec.panel.bins), n=spec.n, quantiles=selected.quantiles,
                minimum_index=selected.minimum_index, maximum_index=selected.maximum_index,
                reference=spec.reference_distribution,
            )
            if not mle.success:
                raise RuntimeError("MLE optimization did not converge: " + mle.message)
        except (ValueError, TypeError, OverflowError, RuntimeError) as exc:
            mle_reason = str(exc)
            mle = None
            optional_warnings.append("Optional likelihood analysis unavailable: " + mle_reason)

    threshold_results: list[dict[str, Any]] = []
    for index, threshold in enumerate(spec.thresholds):
        tail = spec.panel.panel_tail(threshold)
        marginal = exact_count_confidence(
            problems=problems,
            objective=tail,
            confidence_level=confidence_level,
        )
        simultaneous = None
        if multiplicity == "bonferroni" and len(spec.thresholds) > 1:
            simultaneous = exact_count_confidence(
                problems=problems,
                objective=tail,
                confidence_level=simultaneous_level,
            ).as_dict()
        efficiency: dict[str, Any] = {"enabled": efficiency_enabled, "available": False,
                                      "reason": mle_reason or "disabled"}
        if efficiency_enabled and mle is not None:
            try:
                profile = profile_likelihood(
                    mle=mle, tail=tail, n=spec.n, quantiles=selected.quantiles,
                    minimum_index=selected.minimum_index, maximum_index=selected.maximum_index,
                    grid_size=options.get("profile_grid_size", 41), confidence_level=confidence_level,
                )
                efficiency = {
                    "enabled": True, "available": True, "guarantee_class": "assumption_scenario",
                    "reporting_variant": selected_id,
                    "population_tail_mle": float(tail @ np.asarray(mle.probabilities)),
                    "profile_likelihood": profile.as_dict(),
                }
            except (ValueError, TypeError, OverflowError, RuntimeError) as exc:
                efficiency["reason"] = str(exc)
                optional_warnings.append(f"Optional profile at {threshold:g}: {exc}")
        bayes: dict[str, Any] = {"enabled": False}
        if bayes_enabled:
            try:
                bayes_result = dirichlet_posterior_tail(
                    tail=tail, n=spec.n, quantiles=selected.quantiles,
                    minimum_index=selected.minimum_index, maximum_index=selected.maximum_index,
                    draws=options.get("bayes_draws", 5000),
                    seed=_nonnegative_integer(options.get("seed", 20260809), "seed") + index,
                    concentration=float(options.get("dirichlet_concentration", 10.0)),
                    reference=spec.reference_distribution, confidence_level=confidence_level,
                )
                bayes = {
                    "enabled": True, "available": True, "guarantee_class": "assumption_scenario",
                    "reporting_variant": selected_id, **bayes_result.as_dict(labels),
                }
            except (ValueError, TypeError, OverflowError, RuntimeError) as exc:
                bayes = {"enabled": True, "available": False, "reason": str(exc)}
                optional_warnings.append(f"Optional Bayesian analysis at {threshold:g}: {exc}")
        threshold_results.append(
            {
                "threshold": threshold,
                "guarantee_class": "exact_iid_population",
                "exact_count_confidence": {
                    "marginal": marginal.as_dict(),
                    "simultaneous_bonferroni": simultaneous,
                    "multiplicity_rule": multiplicity,
                    "family_size": len(spec.thresholds),
                },
                "optional_efficiency_analysis": efficiency,
                "bayesian_sensitivity": bayes,
                "separate_observed_sample_identification": raw_identification[selected_id][
                    index
                ].as_dict(labels),
            }
        )
    warnings = optional_warnings + [
        "Exact population confidence sets require iid sampling and concern recorded panel MIC categories.",
        "Marginal intervals do not by themselves provide simultaneous multi-threshold coverage.",
        "The optional chi-square likelihood-ratio calibration can fail at irregular boundaries.",
        "Bayesian results, when requested, are sensitivity analyses conditional on the displayed prior.",
    ]
    return {
        **_metadata(spec),
        "guarantee_class": "exact_iid_population",
        "estimand": "source-population probability P(recorded panel MIC > threshold)",
        "sampling_model": "iid categorical sampling",
        "reporting_uncertainty_envelope": reporting_envelope,
        "population_mle": None if mle is None else mle.as_dict(labels),
        "threshold_results": threshold_results,
        "warnings": warnings,
        "prohibited_interpretations": [
            "ECOFF estimation",
            "resistance prevalence without a separately justified breakpoint and sampling frame",
            "clinical susceptibility classification",
            "automatic attribution of probabilities to reporting variants",
        ],
    }


def analyse_spec(raw_spec: dict[str, Any]) -> dict[str, Any]:
    spec = parse_spec(raw_spec)
    if raw_spec.get("wasserstein_calibration_manifest") is not None:
        from .calibration_binding import validate_prepared_calibration
        validate_prepared_calibration(raw_spec, {key: raw_spec.get(key) for key in (
            "reference_distribution", "wasserstein_calibration_manifest", "calibration_context")})
    result = _empirical_analysis(spec) if spec.mode == "empirical" else _population_analysis(spec)
    return json_safe(result)
