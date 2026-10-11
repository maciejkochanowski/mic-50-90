"""Presentation of analysis intent, separate from numerical result codes."""
from html import escape


def inference_status(layer, *, requested=True):
    if not requested:
        return "not_requested"
    status = layer.get("status", "unavailable")
    if status in ("refused", "invalid"):
        return "refused"
    if status == "unavailable":
        return status
    if (status in ("timeout", "interrupted", "incomplete")
            or layer.get("calculation_assessment") == "numerically_unresolved"
            or layer.get("precision_reached") is False):
        return "incomplete"
    return "available"


LABELS = {"not_requested": "Not requested", "available": "Available",
          "unavailable": "Unavailable", "incomplete": "Incomplete", "refused": "Input refused"}


def status_paragraph(status, explanation, title=None):
    heading = ("<strong>" + escape(title) + "</strong>") if title else ""
    return ('<p data-layer-status="' + status + '">' + heading +
            '<strong>' + LABELS[status] + '.</strong> ' + escape(explanation) + '</p>')


def threshold_layer_state(result, kind):
    """Use saved request flags; read older reports without requiring migration."""
    population = kind == "population"
    layer = ((result if result.get("mode") == "population" else result.get("population_layer"))
             if population else result.get("assumption_dependent_scenarios", {}).get("wasserstein_ambiguity_set"))
    reason_key = "population_unavailable_reason" if population else "conformal_unavailable_reason"
    default_reason = ("iid population analysis was not requested; declare iid sampling explicitly to use this layer"
                      if population else "No compatible reference and calibration manifest supplied")
    reason = result.get(reason_key, default_reason)
    available = bool(layer) and (population or layer.get("guarantee_class") == "conformal_new_cohort")
    requested = result.get("inference_requested", {}).get(kind)
    if requested is None:
        # Earlier output contracts recorded intent in these specific reasons.
        requested = available or (not (reason.startswith("iid sampling was not declared") or
                     "was not requested" in reason) if population else reason != default_reason)
    if not requested:
        next_step = (" Declare independent sampling from the same population to request population inference."
                     if population else " Supply a compatible reference and calibration manifest to request this layer.")
        return "not_requested", "This optional analysis was not selected. The sample analysis does not require it." + next_step
    if not available:
        return "unavailable", reason
    if not population:
        intervals = layer.get("threshold_results", [])
        missing = sum(row.get("envelope") is None for row in intervals)
        if not intervals or missing == len(intervals):
            return "unavailable", result.get(reason_key, "No calibrated interval is available for the requested thresholds.")
        if missing:
            return "incomplete", ("Some requested calibrated intervals are unavailable. " +
                                  result.get(reason_key, "Read the individual threshold results below."))
    status = inference_status({"status": "available", **layer})
    explanation = ("Confidence sets require independent observations from the same population on the declared panel; each set states its level and multiplicity."
                   if population else "Calibrated intervals state their level, study unit and reference contract. Exchangeability of the study units is required.")
    if status == "incomplete":
        explanation = "Conservative bounds are retained; inspect the numerical confirmation below. " + explanation
    return status, explanation
