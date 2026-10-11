"""Check prepared calibration mappings against the actual analysis input."""
from .calibration_preparation import canonical_sha256
from .model import parse_spec


def validate_prepared_calibration(raw, calibration, *, cohort_id=None, panel_id=None):
    """Reject accidental remapping without claiming to authenticate provenance.

Legacy manually constructed manifests have no preparation binding and continue
through the existing manifest validator. A prepared manifest may not silently
lose its binding.
"""
    if not isinstance(calibration, dict):
        raise ValueError("Calibration must be an object with reference, manifest and context")
    context = calibration.get("calibration_context", {})
    manifest = calibration.get("wasserstein_calibration_manifest", {})
    if not isinstance(context, dict):
        raise ValueError("calibration_context must be an object")
    if not isinstance(manifest, dict):
        raise ValueError("wasserstein_calibration_manifest must be an object")
    hashes = manifest.get("data_hashes", {})
    if not isinstance(hashes, dict):
        raise ValueError("Calibration data_hashes must be an object")
    binding = context.get("preparation_binding")
    prepared = "preparation_configuration" in hashes
    if binding is None and not prepared:
        return
    if not isinstance(binding, dict) or binding.get("binding_version") != "1.0":
        raise ValueError("Prepared calibration needs its original preparation binding")
    cid, pid = binding.get("cohort_id"), binding.get("panel_id")
    if (cohort_id is not None and cid != cohort_id) or (panel_id is not None and pid != panel_id):
        raise ValueError("Prepared calibration cohort_id or panel_id does not match this input")
    if hashes.get(f"target_binding:{cid}") != canonical_sha256(binding):
        raise ValueError("Prepared calibration binding differs from its manifest hash")
    spec = parse_spec(raw)
    panel_hash = canonical_sha256(spec.panel.as_dict())
    contract = manifest.get("calibration_contract", {})
    checks = (
        (binding.get("panel_sha256"), panel_hash, "panel geometry"),
        (hashes.get(f"panel:{pid}"), panel_hash, "manifest panel geometry"),
        (binding.get("reference_sha256"), canonical_sha256(calibration.get("reference_distribution")), "reference"),
        (binding.get("reference_protocol"), contract.get("reference_protocol"), "reference protocol"),
        (binding.get("reference_protocol"), context.get("reference_protocol"), "context protocol"),
        (binding.get("roster_sha256"), hashes.get("roster"), "roster"),
        (binding.get("composition_sha256"), hashes.get("unit_composition"), "unit composition"),
    )
    for expected, actual, label in checks:
        if expected is None or expected != actual:
            raise ValueError("Prepared calibration mismatch: "+label)
    if binding.get("unit_id") in manifest.get("exchangeable_unit_labels", []):
        raise ValueError("A calibration unit cannot be reused as a target unit")
    if binding.get("unit_id") in contract.get("transport_scaling", {}).get("training_unit_labels", []):
        raise ValueError("A training unit cannot be reused as a target unit")
    allowed = binding.get("allowed_tail_vectors", [])
    if any(spec.panel.panel_tail(t).tolist() not in allowed for t in spec.thresholds):
        raise ValueError("Requested target is outside the prepared calibration tail family")
