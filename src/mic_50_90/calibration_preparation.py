"""Prepare a bounded, roster-led calibration from complete category histograms.

The default reference is uniform. Optional references and transport scales are
learned from separate, complete training units on each explicit panel.
Every unit supplies exactly one prespecified cohort on each declared panel. A
missing or invalid expected cohort makes the entire calibration unavailable.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from hashlib import sha256
from html import escape
import json
from math import isfinite
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from ._version import __version__
from . import dro
from .conformal import calibrate_wasserstein_manifest, minimum_calibration_size
from .empirical import EmpiricalProblem
from .model import parse_spec
from .workflows import counts_spec, load_panels, read_csv


_ROSTER_FIELDS = {"unit_id", "cohort_id", "panel_id", "role"}
_TEXT_METADATA = ("protocol_label", "unit_definition", "cohort_selection_rule",
                  "roster_provenance", "counts_provenance")
_STEPS = 24
_SCORE_CHECK_TOLERANCE = 2e-6


def canonical_sha256(value):
    """Hash JSON data consistently, including panel censoring and category order."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return sha256(payload).hexdigest()


def _text(value, name):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be an explicit nonempty string without surrounding whitespace")
    return value


def _refuse(result, code, reason, **identifiers):
    result["refusals"].append(dict(code=code, reason=str(reason), **identifiers))


def _validate_metadata(metadata, used_panels):
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    for name in _TEXT_METADATA:
        _text(metadata.get(name), name)
    grouping = metadata.get("grouping")
    if not isinstance(grouping, dict) or not grouping:
        raise ValueError("grouping must be a nonempty object of explicit labels")
    for key, value in grouping.items():
        _text(key, "grouping key")
        _text(value, f"grouping.{key}")
    provenance = metadata.get("panel_provenance")
    if not isinstance(provenance, dict):
        raise ValueError("panel_provenance must identify the independent source of every used panel")
    for pid in used_panels:
        _text(provenance.get(pid), f"panel_provenance.{pid}")
    unknown = set(metadata)-set(_TEXT_METADATA)-{"grouping", "panel_provenance"}
    if unknown:
        raise ValueError("Unknown metadata fields: " + ", ".join(sorted(unknown)))


def _metadata_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def _invalid_json_constant(value):
    raise ValueError(f"Metadata must use standard finite JSON values; found {value}")


def _validate_roster(rows, result, *, reference_method="uniform"):
    if not rows:
        _refuse(result, "empty_roster", "The independent roster contains no expected cohorts")
        return []
    valid, seen, slots, unit_roles = [], set(), set(), defaultdict(set)
    for number, row in enumerate(rows, 2):
        try:
            if set(row) != _ROSTER_FIELDS:
                raise ValueError("roster must contain only unit_id, cohort_id, panel_id and role; target outcomes are not accepted")
            for key in _ROSTER_FIELDS:
                _text(row.get(key), key)
            allowed_roles = {"calibration", "target", "training"} if reference_method == "training" else {"calibration", "target"}
            if row["role"] not in allowed_roles:
                raise ValueError("role must be calibration or target; this fixed reference has no training role")
            if row["cohort_id"] in seen:
                raise ValueError("duplicate cohort_id in the independent roster")
            seen.add(row["cohort_id"])
            slot = (row["unit_id"], row["panel_id"])
            if slot in slots:
                raise ValueError("duplicate unit/panel slot; supply exactly one cohort per panel in each unit")
            slots.add(slot)
            unit_roles[row["unit_id"]].add(row["role"])
            valid.append(dict(row))
        except (ValueError, TypeError) as exc:
            _refuse(result, "invalid_roster", f"Roster row {number}: {exc}",
                    cohort_id=row.get("cohort_id", ""), unit_id=row.get("unit_id", ""))
    for unit, roles in unit_roles.items():
        if len(roles) != 1:
            _refuse(result, "role_overlap", "Training, calibration and target units must be disjoint", unit_id=unit)
    for role in ("calibration", "target"):
        if not any(row["role"] == role for row in valid):
            _refuse(result, "missing_role", f"The roster must contain at least one {role} unit")
    composition = defaultdict(list)
    for row in valid:
        composition[row["unit_id"]].append(row["panel_id"])
    baseline = next((sorted(composition[row["unit_id"]]) for row in valid
                     if row["role"] == "calibration"), [])
    for unit, panels in composition.items():
        if sorted(panels) != baseline:
            _refuse(result, "unit_composition", "Every calibration and target unit must contain the same prespecified panel set", unit_id=unit)
    return sorted(valid, key=lambda row: (row["role"], row["unit_id"], row["panel_id"], row["cohort_id"]))


def _exact_count(value, name):
    """Use the same exact count contract as the analysis workflows."""
    from .validation import exact_integer
    return exact_integer(value, name)


def _direct_tail_scores(spec, projected, counts):
    """Independent transport LP: fix each true tail and minimise transport cost."""
    k = len(projected)
    positions = np.log2(spec.panel.panel_values)
    costs = np.abs(positions[:, None] - positions[None, :]).ravel()
    source_margins = np.repeat(np.eye(k), k, axis=1)
    cumulative = [np.tile(np.arange(k) <= j, k).astype(float) for j in range(k)]
    upper_rows, upper_values = [], []
    for quantile in spec.quantiles:
        upper_rows.append(-cumulative[quantile.category_index])
        upper_values.append(-quantile.rank/spec.n)
        if quantile.category_index > 0:
            upper_rows.append(cumulative[quantile.category_index-1])
            upper_values.append((quantile.rank-1)/spec.n)
    rows = []
    for threshold in spec.thresholds:
        objective = spec.panel.panel_tail(threshold)
        numerator = sum(int(count) for count, selected in zip(counts, objective) if selected)
        truth = numerator/spec.n
        fitted = linprog(costs, A_ub=np.asarray(upper_rows), b_ub=np.asarray(upper_values),
                         A_eq=np.vstack([source_margins, np.tile(objective, k)]),
                         b_eq=np.r_[projected, truth], bounds=(0, None), method="highs")
        if not fitted.success or not isfinite(float(fitted.fun)) or fitted.fun < -1e-10:
            raise RuntimeError("Independent transport score failed: " + str(fitted.message))
        rows.append(dict(threshold=float(threshold), truth_count=numerator, original_n=spec.n,
                         truth=truth, score=max(0., float(fitted.fun))))
    return rows


def _histogram_spec(row, histogram, panel):
    if not histogram:
        raise ValueError("Missing expected calibration cohort; its unit cannot be omitted")
    if any(item.get("panel_id") != row["panel_id"] for item in histogram):
        raise ValueError("count panel_id does not match the independent roster")
    for item in histogram:
        _exact_count(item.get("count"), "count")
    total = sum(_exact_count(item.get("count"), "count") for item in histogram)
    if total > 2**53-1:
        raise ValueError("original denominator exceeds the exact supported integer range")
    if any("original_n" in item for item in histogram):
        supplied = {_exact_count(item.get("original_n"), "original_n") for item in histogram}
        if supplied != {total}:
            raise ValueError("original_n must agree on every category row and equal the complete count sum")
    thresholds = panel.panel_values[:-1].tolist()
    raw, counts = counts_spec(histogram, panel, thresholds, {"enabled": False})
    spec = parse_spec(raw)
    return spec, counts


def _score_cohort(row, histogram, panel, reference):
    spec, counts = _histogram_spec(row, histogram, panel)
    thresholds = spec.thresholds
    problem = EmpiricalProblem(n=spec.n, panel=panel, quantiles=spec.quantiles)
    displacement, projected = dro.project_onto_sharp_set(problem=problem, reference=np.asarray(reference))
    tail_scores = _direct_tail_scores(spec, projected, counts)
    independent = max(item["score"] for item in tail_scores)
    core = dro.critical_radius(problem=problem, reference=projected, positions=None,
                               objectives=[panel.panel_tail(t) for t in thresholds],
                               truths=[item["truth"] for item in tail_scores], steps=_STEPS)
    if not isfinite(core) or core < 0:
        raise RuntimeError("Core calibration score is not finite and nonnegative; no replacement score is allowed")
    difference = abs(core-independent)
    if difference > _SCORE_CHECK_TOLERANCE:
        raise RuntimeError(f"Core/independent transport score disagreement {difference} exceeds {_SCORE_CHECK_TOLERANCE}")
    # Retain the larger numerical solution; never clip a positive direct score down.
    return dict(status="ok", score=max(float(core), independent), core_score=float(core),
                independent_score=independent, absolute_disagreement=difference,
                original_n=spec.n, categories=panel.labels, counts=[int(value) for value in counts],
                mic50=spec.quantiles[0].category_label, mic90=spec.quantiles[1].category_label,
                rank50=spec.quantiles[0].rank, rank90=spec.quantiles[1].rank,
                projection_distance=float(displacement), projected_reference=projected.tolist(),
                tail_scores=tail_scores, reason="")


def _learn_reference(roster, groups, panels, *, scaling):
    """Learn all reference information before looking at calibration outcomes."""
    training = [row for row in roster if row["role"] == "training"]
    units = sorted({row["unit_id"] for row in training})
    if len(units) < 2:
        raise ValueError("The training method requires at least two complete independent training units")
    validated = {}
    for row in training:
        spec, counts = _histogram_spec(row, groups[row["cohort_id"]], panels[row["panel_id"]])
        validated[row["cohort_id"]] = (spec.n, [int(c) for c in counts])
    references, scales, checks = {}, {}, []
    for pid in sorted({row["panel_id"] for row in training}):
        selected = [row for row in training if row["panel_id"] == pid]
        total = [sum(validated[row["cohort_id"]][1][j] for row in selected)
                 for j in range(len(panels[pid].bins))]
        denominator = sum(total)
        references[pid] = [value/denominator for value in total]
        if scaling == "none":
            continue
        per_unit = []
        for row in selected:
            counts = validated[row["cohort_id"]][1]
            other = [value-count for value, count in zip(total, counts)]
            other_n = sum(other)
            reference = [value/other_n for value in other]
            check = _score_cohort(row, groups[row["cohort_id"]], panels[pid], reference)
            checks.append(dict(unit_id=row["unit_id"], cohort_id=row["cohort_id"], panel_id=pid,
                               excluded_training_unit=row["unit_id"], **check))
            per_unit.append(check["score"])
        minimum_step = float(np.min(np.diff(np.log2(panels[pid].panel_values))))
        minimum_n = min(validated[row["cohort_id"]][0] for row in selected)
        scales[pid] = max(minimum_step/minimum_n, max(per_unit))
        if not isfinite(scales[pid]) or scales[pid] <= 0:
            raise ValueError("Training transport scale is not finite and positive")
    return references, scales, checks, units


def _account_units(result):
    units = sorted({row.get("unit_id", "") for row in result["roster"] if row.get("role") == "calibration"})
    for unit in units:
        expected = [row for row in result["roster"] if row.get("role") == "calibration" and row.get("unit_id") == unit]
        records = [row for row in result["cohort_scores"] if row["unit_id"] == unit]
        available = [row for row in records if row["status"] == "ok"]
        complete = len(available) == len(expected) and bool(expected)
        result["unit_scores"].append(dict(unit_id=unit, expected_cohorts=len(expected),
                                         available_cohorts=len(available),
                                         status="ok" if complete else "unavailable",
                                         score=max(row["score"] for row in available) if complete else None))
    result["summary"].update(available_calibration_cohorts=sum(row["status"] == "ok" for row in result["cohort_scores"]),
                             complete_calibration_units=sum(row["status"] == "ok" for row in result["unit_scores"]))


def prepare_calibration(counts_path, *, panels_path, roster_path, metadata_path, level=.95, delimiter=",",
                        reference_method="uniform", transport_scaling="none"):
    """Prepare a manifest/mapping, or return explicit refusals with no usable mapping.

    This operation records a declared prospective protocol; it cannot establish
    that a supplied roster predates outcomes or that study units are independent.
    ``counts_path`` contains calibration and explicitly requested training outcomes. Target rows in the roster
    contain identifiers and panel IDs, never counts or target summaries.
    """
    result = dict(software_version=__version__, status="unavailable", manifest=None, calibrations={},
                  configuration=dict(software_version=__version__, level=None, inputs={}), summary={},
                  roster=[], references={}, targets=[], cohort_scores=[], unit_scores=[], refusals=[])
    configuration = result["configuration"]
    configuration.update(reference_method=reference_method, transport_scaling=transport_scaling)
    paths = dict(counts=counts_path, panels=panels_path, roster=roster_path, metadata=metadata_path)
    if reference_method not in {"uniform", "training"}:
        _refuse(result, "invalid_reference_method", "reference_method must be uniform or training")
    if transport_scaling not in {"none", "training"} or (transport_scaling == "training" and reference_method != "training"):
        _refuse(result, "invalid_transport_scaling", "Training transport scaling requires reference_method=training")
    for name, path in paths.items():
        try:
            configuration["inputs"][name] = dict(filename=Path(path).name, sha256=sha256(Path(path).read_bytes()).hexdigest())
        except (OSError, TypeError) as exc:
            _refuse(result, "input_unreadable", f"Cannot read {name}: {exc}")
    try:
        if isinstance(level, bool) or not isfinite(float(level)) or not 0 < float(level) < 1:
            raise ValueError("level must lie strictly between zero and one")
        configuration["level"] = float(level)
        result["summary"]["minimum_calibration_units"] = minimum_calibration_size(1-float(level))
    except (TypeError, ValueError) as exc:
        _refuse(result, "invalid_level", exc)
    try:
        raw_roster = read_csv(roster_path, delimiter)
        result["roster"] = raw_roster
        roster = _validate_roster(raw_roster, result, reference_method=reference_method)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        roster = []
        _refuse(result, "invalid_roster", exc)
    raw_roster = result["roster"]
    result["summary"].update(
        expected_calibration_units=len({r.get("unit_id", "") for r in raw_roster if r.get("role") == "calibration"}),
        expected_calibration_cohorts=sum(r.get("role") == "calibration" for r in raw_roster),
        target_units=len({r.get("unit_id", "") for r in raw_roster if r.get("role") == "target"}),
        target_cohorts=sum(r.get("role") == "target" for r in raw_roster))
    used_panels = sorted({r["panel_id"] for r in roster})
    try:
        panels, panel_errors = load_panels(panels_path, delimiter)
        for pid in used_panels:
            if pid in panel_errors or pid not in panels:
                _refuse(result, "invalid_panel", panel_errors.get(pid, "Panel missing; no dilution grid is inferred"), panel_id=pid)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        panels = {}
        _refuse(result, "invalid_panel", exc)
    try:
        metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8-sig"),
                              object_pairs_hook=_metadata_object, parse_constant=_invalid_json_constant)
        _validate_metadata(metadata, used_panels)
        configuration["metadata"] = metadata
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        metadata = {}
        _refuse(result, "invalid_metadata", exc)
    try:
        rows = read_csv(counts_path, delimiter)
        if not rows:
            raise ValueError("Calibration counts contain no rows")
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        rows = []
        _refuse(result, "invalid_counts", exc)
    preflight_valid = not result["refusals"]
    if preflight_valid:
        result["roster"] = roster
        result["references"] = {pid: [1./len(panels[pid].bins)]*len(panels[pid].bins) for pid in used_panels}
        composition = sorted(row["panel_id"] for row in roster if row["unit_id"] == roster[0]["unit_id"])
        configuration.update(unit_composition=composition, panels={pid: panels[pid].as_dict() for pid in used_panels},
                             summary_policy="ceiling_50_90_no_range", reference_rule="projected_uniform_per_panel",
                             functional_scope="all_internal_recorded_panel_tails", unit_score_aggregation="max",
                             training_units=[], core_bisection_steps=_STEPS,
                             score_check_tolerance_log2=_SCORE_CHECK_TOLERANCE)
    groups = defaultdict(list)
    lookup = {row["cohort_id"]: row for row in roster}
    for number, row in enumerate(rows, 2):
        cid = row.get("cohort_id", "")
        if not cid or cid not in lookup:
            _refuse(result, "unplanned_count", f"Count row {number} has no expected calibration cohort", cohort_id=cid)
        elif lookup[cid]["role"] == "target":
            _refuse(result, "target_outcome", "Target counts are not accepted; target outcomes must remain separate", cohort_id=cid)
        else:
            groups[cid].append(row)
    if preflight_valid and reference_method == "training":
        try:
            references, scales, checks, training_units = _learn_reference(roster, groups, panels, scaling=transport_scaling)
            result.update(references=references, transport_scales=scales, training_scores=checks)
            configuration.update(reference_method="training", transport_scaling=transport_scaling,
                                 reference_rule="projected_pooled_training_per_panel", training_units=training_units,
                                 transport_scales=scales)
            if transport_scaling == "training":
                configuration["training_scale_rule"] = "max(leave-one-training-unit-out critical radius, min(log2 panel step)/min(training n))"
            result["summary"].update(training_units=len(training_units), training_cohorts=sum(row["role"] == "training" for row in roster))
        except (ValueError, RuntimeError, ArithmeticError, KeyError, TypeError) as exc:
            preflight_valid = False
            _refuse(result, "training_unavailable", exc)
    for row in roster:
        if row["role"] != "calibration":
            continue
        record = {key: row[key] for key in ("unit_id", "cohort_id", "panel_id")}
        record.update(status="unavailable", score=None, original_n=None, reason="Input preflight failed")
        if preflight_valid:
            try:
                record.update(_score_cohort(row, groups[row["cohort_id"]], panels[row["panel_id"]],
                                            result["references"][row["panel_id"]]))
                if transport_scaling == "training":
                    scale = result["transport_scales"][row["panel_id"]]
                    if not isfinite(record["score"]/scale):
                        raise ValueError("Normalized calibration score must be finite")
                    record.update(physical_score=record["score"], transport_scale=scale,
                                  score=record["score"]/scale)
            except (ValueError, RuntimeError, ArithmeticError, KeyError, TypeError) as exc:
                record.update(status="unavailable", score=None, reason=str(exc))
                _refuse(result, "cohort_unavailable", exc, cohort_id=row["cohort_id"], unit_id=row["unit_id"], panel_id=row["panel_id"])
        result["cohort_scores"].append(record)
    _account_units(result)
    for name, recorded in configuration["inputs"].items():
        try:
            if sha256(Path(paths[name]).read_bytes()).hexdigest() != recorded["sha256"]:
                _refuse(result, "input_changed", f"Input {name} changed during preparation; use a stable snapshot")
        except OSError as exc:
            _refuse(result, "input_changed", f"Cannot recheck input {name}: {exc}")
    minimum = result["summary"].get("minimum_calibration_units")
    if minimum is not None and result["summary"]["expected_calibration_units"] < minimum:
        _refuse(result, "insufficient_units", f"Requested level needs at least {minimum} calibration units; the requested level is not lowered and no fallback is selected")
    if result["refusals"]:
        return result

    protocol_hash = canonical_sha256({key: value for key, value in configuration.items() if key != "inputs"})
    protocol = metadata["protocol_label"] + ":sha256:" + protocol_hash
    configuration["reference_protocol"] = protocol
    hashes = {f"input:{name}": item["sha256"] for name, item in configuration["inputs"].items()}
    hashes.update(roster=canonical_sha256(roster), unit_composition=canonical_sha256(composition),
                  preparation_configuration=canonical_sha256(configuration), references=canonical_sha256(result["references"]))
    hashes.update({f"panel:{pid}": canonical_sha256(panels[pid].as_dict()) for pid in used_panels})
    bindings = {}
    for row in roster:
        if row["role"] != "target":
            continue
        cid, pid = row["cohort_id"], row["panel_id"]
        thresholds = panels[pid].panel_values[:-1]
        bindings[cid] = dict(binding_version="1.0", cohort_id=cid, unit_id=row["unit_id"], panel_id=pid,
                             panel_sha256=hashes[f"panel:{pid}"], reference_sha256=canonical_sha256(result["references"][pid]),
                             reference_protocol=protocol, roster_sha256=hashes["roster"],
                             composition_sha256=hashes["unit_composition"],
                             allowed_tail_vectors=[panels[pid].panel_tail(t).tolist() for t in thresholds])
        hashes[f"target_binding:{cid}"] = canonical_sha256(bindings[cid])
        result["targets"].extend(dict(cohort_id=cid, threshold=float(t), unit="mg/L") for t in thresholds)
    hashes["cohort_scores"] = canonical_sha256(result["cohort_scores"])
    contract = dict(score_kind="simultaneous_tail_intervals", reference_rule="projected", functional_scope="all_panel_tails",
                    transport_unit="log2_mg_L", summary_policy="ceiling_50_90_no_range", reference_protocol=protocol,
                    unit_definition=metadata["unit_definition"])
    if transport_scaling == "training":
        contract.update(transport_unit="normalized_log2_mg_L", transport_scaling=dict(
            method="training_loo_max", training_unit_labels=configuration["training_units"],
            panels={pid: dict(scale=result["transport_scales"][pid], panel_sha256=hashes[f"panel:{pid}"])
                    for pid in used_panels}))
    try:
        manifest = calibrate_wasserstein_manifest(
            group_scores=[row["score"] for row in result["cohort_scores"]],
            group_units=[row["unit_id"] for row in result["cohort_scores"]], alpha=1-float(level),
            grouping=metadata["grouping"], source=metadata["protocol_label"], data_hashes=hashes,
            calibrate_on="units", unit_aggregation="max", calibration_contract=contract).as_dict()
    except (ValueError, RuntimeError, ArithmeticError) as exc:
        _refuse(result, "manifest_unavailable", exc)
        return result
    result["manifest"] = manifest
    result["calibrations"] = {
        cid: dict(reference_distribution=result["references"][binding["panel_id"]], wasserstein_calibration_manifest=manifest,
                  calibration_context=dict(unit="mg/L", reference_protocol=protocol, grouping=metadata["grouping"],
                                           **({"panel_id": binding["panel_id"]} if transport_scaling == "training" else {}),
                                           preparation_binding=binding)) for cid, binding in bindings.items()}
    result["status"] = "ready"
    return result


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def _write_csv(path, rows, fields, *, spreadsheet=True):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            rendered = {key: row.get(key, "") for key in fields}
            if spreadsheet:
                rendered = {key: "'"+value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r"))
                            else value for key, value in rendered.items()}
            writer.writerow(rendered)


def _report_html(result):
    from .typography import html_with_typography
    summary, manifest = result["summary"], result["manifest"]
    trained = result["configuration"].get("reference_method") == "training"
    reference_description = ("Pooled reference from separate training units on each explicit panel"
                             if trained else "Fixed uniform reference on each explicit panel")
    body = [f'<h1>Calibration preparation: {escape(result["status"])}</h1>',
            '<p>' + reference_description + '; ceiling MIC50/MIC90 without extrema; '
            'one score per unit is the maximum over every prespecified cohort and internal recorded panel cut.</p>',
            '<dl>']
    for label, name in (("Expected calibration units", "expected_calibration_units"),
                        ("Expected calibration cohorts", "expected_calibration_cohorts"),
                        ("Complete calibration units", "complete_calibration_units"),
                        ("Target units", "target_units"), ("Target cohorts", "target_cohorts")):
        body.append(f'<dt>{label}</dt><dd>{summary.get(name, 0)}</dd>')
    body.append('</dl>')
    if trained:
        body.append(f'<p>Training units: {summary.get("training_units", 0)}. Training, calibration and target roles are separate.</p>')
    if manifest:
        radius_unit = 'normalized score units' if manifest['manifest_version'] == '1.3' else 'log2 dilution steps'
        body.append(f'<p>Requested level: {manifest["requested_level"]:.6g}; fixed-rank marginal level: '
                    f'{manifest["confidence_level"]:.6g}; rank {manifest["rank"]} of '
                    f'{manifest["calibration_size"]} units; radius {manifest["radius"]:.9g} {radius_unit}.</p>')
        body.append('<p>' + escape(manifest["coverage_statement"]) + '</p>')
        if result.get("transport_scales"):
            body.append('<h2>Panel scales and applied radii</h2><table><thead><tr><th>Panel</th><th>Training scale</th><th>Physical radius in log2 dilution steps</th></tr></thead><tbody>')
            for pid, scale in result["transport_scales"].items():
                body.append(f'<tr><td>{escape(pid)}</td><td>{scale:.9g}</td><td>{manifest["radius"]*scale:.9g}</td></tr>')
            body.append('</tbody></table>')
    else:
        body.append('<p>No usable calibration manifest or target mapping was issued. Every expected unit remains in the accounting.</p>')
    body.append('<p>Roster provenance, panel provenance and unit independence are declarations supplied by the user. '
                'Hashes check consistency; this report does not independently verify those declarations, establish independence, '
                'or demonstrate a PAC guarantee or held-out coverage. Target outcomes were not used.</p>')
    if result["refusals"]:
        body.append('<h2>Refusals</h2><ul>')
        for row in result["refusals"]:
            label = ' / '.join(str(row.get(key, '')) for key in ('unit_id', 'cohort_id', 'panel_id') if row.get(key))
            body.append('<li>' + escape((label+': ' if label else '')+row["reason"]) + '</li>')
        body.append('</ul>')
    body.append('<h2>Unit scores</h2><table><thead><tr><th>Unit</th><th>Available / expected cohorts</th><th>Score</th><th>Status</th></tr></thead><tbody>')
    for row in result["unit_scores"]:
        score = 'unavailable' if row["score"] is None else f'{row["score"]:.9g}'
        body.append(f'<tr><td>{escape(row["unit_id"])}</td><td>{row["available_cohorts"]} / {row["expected_cohorts"]}</td><td>{score}</td><td>{row["status"]}</td></tr>')
    body.append('</tbody></table><p>Retained files: configuration.json, preparation.json, intended-roster.csv, references.json, '
                'calibration-cohort-scores.csv, calibration-unit-scores.csv, calibration-tail-scores.csv, refusals.csv, '
                'manifest.json, calibrations.json, targets.csv and artifact-hashes.json.</p>')
    return html_with_typography('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Calibration preparation</title><style>body{font:16px system-ui,sans-serif;max-width:1000px;margin:3rem auto;padding:0 1rem;color:#172b3a;line-height:1.55}'
            'table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.5rem;border-bottom:1px solid #b7c8d4}dt{font-weight:600}dd{margin-bottom:.4rem}</style>'
            '</head><body>' + ''.join(body) + '</body></html>')


def run_calibration_prepare(args):
    """CLI adapter; an unavailable calibration always returns exit status 2."""
    from .file_safety import check_output_paths
    output = Path(args.output_dir)
    check_output_paths(
        [args.input, args.panels, args.roster, args.metadata],
        [output / name for name in ("manifest.json", "calibrations.json", "configuration.json",
         "preparation.json", "references.json", "intended-roster.csv", "calibration-cohort-scores.csv",
         "calibration-unit-scores.csv", "calibration-tail-scores.csv", "refusals.csv", "targets.csv",
         "report.html", "artifact-hashes.json")])
    delimiter = {"comma": ",", "semicolon": ";", "tab": "\t"}[getattr(args, "delimiter", "comma")]
    result = prepare_calibration(args.input, panels_path=args.panels, roster_path=args.roster,
                                 metadata_path=args.metadata, level=args.level, delimiter=delimiter,
                                 reference_method=getattr(args, "reference_method", "uniform"),
                                 transport_scaling=getattr(args, "transport_scaling", "none"))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    # Invalidate old products before writing a new run into an existing directory.
    _write_json(output/"manifest.json", None)
    _write_json(output/"calibrations.json", {})
    for name, value in (("configuration.json", result["configuration"]), ("preparation.json", result),
                        ("references.json", result["references"]), ("manifest.json", result["manifest"]),
                        ("calibrations.json", result["calibrations"])):
        _write_json(output/name, value)
    _write_csv(output/"intended-roster.csv", result["roster"], ["unit_id", "cohort_id", "panel_id", "role"])
    _write_csv(output/"calibration-cohort-scores.csv", result["cohort_scores"],
               ["unit_id", "cohort_id", "panel_id", "status", "original_n", "mic50", "mic90", "rank50", "rank90",
                "score", "physical_score", "transport_scale", "core_score", "independent_score", "absolute_disagreement", "projection_distance", "reason"])
    _write_csv(output/"calibration-unit-scores.csv", result["unit_scores"],
               ["unit_id", "status", "expected_cohorts", "available_cohorts", "score"])
    tails = [dict(unit_id=row["unit_id"], cohort_id=row["cohort_id"], panel_id=row["panel_id"], **tail)
             for row in result["cohort_scores"] for tail in row.get("tail_scores", [])]
    _write_csv(output/"calibration-tail-scores.csv", tails,
               ["unit_id", "cohort_id", "panel_id", "threshold", "truth_count", "original_n", "truth", "score"])
    _write_csv(output/"refusals.csv", result["refusals"], ["code", "unit_id", "cohort_id", "panel_id", "reason"])
    # This file is machine input for batch, so exact identifiers must round-trip.
    _write_csv(output/"targets.csv", result["targets"], ["cohort_id", "threshold", "unit"], spreadsheet=False)
    (output/"report.html").write_text(_report_html(result), encoding="utf-8")
    names = ("manifest.json", "calibrations.json", "configuration.json", "preparation.json", "references.json",
             "intended-roster.csv", "calibration-cohort-scores.csv", "calibration-unit-scores.csv",
             "calibration-tail-scores.csv", "refusals.csv", "targets.csv", "report.html")
    _write_json(output/"artifact-hashes.json", {name: sha256((output/name).read_bytes()).hexdigest() for name in names})
    return 0 if result["status"] == "ready" else 2
