"""Readable numerical evidence, using the stored certificate without recomputation."""
from html import escape
from math import isfinite


def _number(value):
    if value is None or isinstance(value, bool):
        return "Not recorded"
    try:
        return f"{float(value):.6g}" if isfinite(float(value)) else "Not recorded"
    except (TypeError, ValueError):
        return "Not recorded"


def population_checks(layer):
    if layer.get("status") == "unavailable":
        return ""
    rows = []
    def row(key, title, text):
        rows.append('<tr data-check="' + key + '"><th>' + escape(title) + '</th><td>' + escape(text) + '</td></tr>')
    row("method", "Statistical method", str(layer.get("method", "Not recorded")))
    level = layer.get("confidence_level")
    if level is not None:
        row("confidence", "Simultaneous confidence", _number(100 * level) + "% under the stated sampling assumptions")
    if "numerical_tolerance_pp" in layer:
        row("endpoint-precision", "Requested numerical precision", _number(layer["numerical_tolerance_pp"]) + " percentage points")
    if "endpoint_gap_pp" in layer:
        row("endpoint-gap", "Remaining certified endpoint gap", _number(layer["endpoint_gap_pp"]) + " percentage points")
    reached = layer.get("precision_reached")
    row("confirmation", "Endpoint confirmation", "Requested precision confirmed" if reached is True else
        "Requested precision not confirmed; returned outer bounds retain unresolved possibilities" if reached is False else
        str(layer.get("numerical_status", "Numerical endpoint confirmation is not recorded for this method")))
    if "evaluated_histograms" in layer:
        row("evaluated-histograms", "Compatible tables actually evaluated", str(layer["evaluated_histograms"]))
    certificate = layer.get("population_row_lift_certificate")
    p6 = ""
    if certificate is not None:
        certified = certificate.get("status") == "certified"
        status = "certified" if certified else "not_certified"
        explanation = ("The P6 condition was verified. At most K distinct compatible tables suffice for the contiguous-range endpoints in each reporting interpretation; K is the number of MIC categories."
                       if certified else "The P6 condition was not certified for this calculation. This does not establish that the condition is false.")
        if certificate.get("reason"):
            explanation += " " + str(certificate["reason"])
        p6 = '<p data-check="p6" data-status="' + status + '">' + escape(explanation) + '</p>'
    return ('<details class="result-checks"><summary>How this result was checked</summary>'
            '<p>Statistical confidence describes sampling uncertainty. Numerical precision describes how closely the interval endpoints have been confirmed.</p>'
            '<table><thead><tr><th>Check</th><th>Recorded evidence</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>' + p6 +
            '<p>' + ('The theoretical table bound and the number actually evaluated are different quantities. ' if certificate else '') +
            '<a href="results.json">Full numerical results</a> retain the certificates and all recorded checks.</p></details>')
