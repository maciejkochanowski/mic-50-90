"""MIC-50-90 public API (the ``mic_50_90`` module name is retained for compatibility)."""

from ._version import __version__
from .analysis import analyse_spec
from .calibration_audit import audit_calibration, plan_calibration
from .calibration_preparation import prepare_calibration
from .count_updates import analyse_with_counts, counts_from_percentage
from .decision_planning import plan_decisions
from .acquisition import plan_acquisition
from .sufficient_reporting import plan_reporting, verify_reporting
from .conformal import (
    WassersteinCalibrationManifest,
    calibrate_wasserstein_manifest,
    split_conformal_radius,
)
from .empirical import EmpiricalIdentification, empirical_bounds
from .exact_population import clopper_pearson, exact_count_confidence
from .likelihood import log_order_event_probability, order_event_probability
from .model import MICBin, MICPanel, QuantileSummary, ReportingVariant, parse_spec

__all__ = [
    "__version__",
    "MICBin",
    "MICPanel",
    "QuantileSummary",
    "ReportingVariant",
    "EmpiricalIdentification",
    "WassersteinCalibrationManifest",
    "analyse_spec",
    "analyse_with_counts",
    "counts_from_percentage",
    "plan_decisions",
    "plan_acquisition",
    "plan_reporting",
    "verify_reporting",
    "prepare_calibration",
    "audit_calibration",
    "plan_calibration",
    "empirical_bounds",
    "clopper_pearson",
    "exact_count_confidence",
    "calibrate_wasserstein_manifest",
    "split_conformal_radius",
    "log_order_event_probability",
    "order_event_probability",
    "parse_spec",
]
