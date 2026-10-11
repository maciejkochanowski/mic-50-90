"""Independent review findings: reject false accounting, retain valid layers."""
from copy import deepcopy

import pytest

from mic_50_90.analysis import analyse_spec
from mic_50_90.conformal import calibrate_wasserstein_manifest, validate_calibration_manifest
from mic_50_90.workflows import analyse_layers
from test_release_contract import contract, manifest, raw_spec


@pytest.mark.parametrize("labels", [["same-study"]*19, [""]*19, [None]*19])
def test_manifest_needs_distinct_identifiable_units(labels):
    changed = manifest()
    changed["exchangeable_unit_labels"] = labels
    with pytest.raises(ValueError, match="label"):
        validate_calibration_manifest(changed)


@pytest.mark.parametrize("field", ["calibration_size", "exchangeable_units", "rank", "minimum_group_calibration_size"])
def test_manifest_never_truncates_fractional_accounting(field):
    changed = manifest()
    changed[field] += .8
    with pytest.raises(ValueError, match="integer"):
        validate_calibration_manifest(changed)


@pytest.mark.parametrize("bad_score", [-1.0, float("nan")])
def test_raw_invalid_scores_cannot_disappear_under_unit_max(bad_score):
    with pytest.raises(ValueError, match="score"):
        calibrate_wasserstein_manifest(group_scores=[bad_score, 0]+[.1]*18,
            group_units=["study-0", "study-0"]+[f"study-{i}" for i in range(1,19)],
            alpha=.1, calibrate_on="units", grouping={"source":"test"}, source="controlled",
            data_hashes={"controlled":"a"*64}, calibration_contract=contract())


@pytest.mark.parametrize("labels", [[""]*19, [None]*19])
def test_calibration_builder_refuses_unidentified_unit_labels(labels):
    with pytest.raises(ValueError, match="label"):
        calibrate_wasserstein_manifest(group_scores=[.1]*19, group_units=labels,
            alpha=.1, calibrate_on="units", grouping={}, source="controlled",
            data_hashes={"controlled":"a"*64}, calibration_contract=contract())


@pytest.mark.parametrize("context", [None, [], "invalid"])
def test_malformed_optional_calibration_preserves_sample_result(context):
    raw = raw_spec()
    calibration = {"reference_distribution":[1,0,0,0,0],
                   "wasserstein_calibration_manifest":manifest(),
                   "calibration_context":context}
    result = analyse_layers(raw, iid=False, confidence=.95, calibration=calibration)
    assert result["identification"][0]["panel_recorded_estimand"]["lower"]["count"] == 2
    assert "calibration_context must be an object" in result["conformal_unavailable_reason"]
    # The low-level JSON API gives a controlled validation error as well.
    with pytest.raises(ValueError, match="calibration_context must be an object"):
        analyse_spec({**raw, **deepcopy(calibration)})
