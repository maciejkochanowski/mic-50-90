"""Where the package places a category, and the one place two conventions could collide.

Three different things get called "where the category sits", and they are not the same
quantity. Nothing was wrong with having three; what was missing was anything that fails
when they drift or meet.

* ``MICPanel.from_twofold_levels`` gives the open top category a *representative
  concentration*, one dilution above the last tested level. It feeds the recorded-panel
  estimand, never the sharp bounds.
* The ATLAS benchmark gives a right-censored reading an *ordering score*, a quarter
  dilution above its boundary, so that ``>32`` sorts immediately after ``32`` without
  claiming a whole dilution of separation.
* The transport cost uses *positions in log2 mg/L*, with the printing convention undone
  where the panel is a twofold series and left alone where it is a gradient strip.

The released external pipeline builds a closed panel and carries censoring in the score,
so the first two never meet there. That is the property worth pinning: if someone opens
the panel in that path, the representative and the score would both be placing the same
mass and this test says so before the numbers do.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mic_50_90.model import MICPanel  # noqa: E402

# The campaign adapter is included in the source distribution. This marker also permits
# testing a deliberately library-only checkout, with the omission reported as a skip.
pipeline = pytest.mark.skipif(
    not (ROOT / "scripts" / "run_external_validation.py").exists(),
    reason="needs scripts/run_external_validation.py from the source or reproduction distribution",
)


def test_open_top_category_representative_is_one_dilution_above_the_panel():
    panel = MICPanel.from_twofold_levels([0.5, 1, 2, 4, 8], right_censored=True)
    top = panel.bins[-1]
    assert top.label == ">8"
    assert top.lower == 8.0 and top.upper is None
    assert top.panel_value == 16.0, "the representative is a convention; state it, do not move it"


def test_lowest_category_is_left_censored_unless_the_caller_says_otherwise():
    default = MICPanel.from_twofold_levels([0.5, 1, 2])
    assert default.bins[0].label == "<=0.5"
    assert default.bins[0].lower is None, "a dilution reading resolves nothing below the panel"

    closed = MICPanel.from_twofold_levels([0.5, 1, 2], left_censored=False)
    assert closed.bins[0].label != "<=0.5"


def test_a_threshold_inside_a_category_is_ambiguous_rather_than_assigned():
    panel = MICPanel.from_twofold_levels([1, 2, 4], left_censored=False, right_censored=False)
    inside = next(b for b in panel.bins if b.lower == 2.0 and b.upper == 4.0)
    assert inside.latent_status(3.0) == "ambiguous"
    assert inside.latent_status(4.0) == "below"
    assert inside.latent_status(1.5) == "above"


@pipeline
def test_the_released_external_pipeline_builds_a_closed_panel():
    """The one place the representative and the ordering score could describe the same mass."""
    source = (ROOT / "scripts" / "run_external_validation.py").read_text(encoding="utf-8")
    assert "left_censored=False" in source and "right_censored=False" in source, (
        "the external validation must build a closed panel: censoring is carried in the "
        "score, so an open category here would place the same mass twice"
    )


@pipeline
@pytest.mark.parametrize('settings', [dict(calibrate_on='cohorts'), dict(score='distance'),
                                       dict(require_comparable=False), dict(centre='unknown')])
def test_legacy_calibration_settings_refuse_before_reading_cohorts(settings):
    from scripts.run_external_validation import conformal_external_validation
    class UnreadableCohorts:
        def __iter__(self):
            raise AssertionError('Invalid calibration settings must fail before data processing')
    with pytest.raises(ValueError, match='explicit contract|centre'):
        conformal_external_validation(UnreadableCohorts(), 'unused', **settings)


@pipeline
def test_transport_positions_undo_printing_only_on_a_twofold_panel():
    from scripts.run_external_validation import transport_positions

    # EUCAST prints these three for concentrations exactly one dilution apart.
    printed = np.array([0.016, 0.03, 0.06, 0.125, 0.25])
    positions = transport_positions(printed)
    assert np.allclose(np.diff(positions), 1.0), "a twofold panel must step by one dilution"

    # A gradient strip really does carry these, about half a dilution apart. Snapping them
    # would collapse distinct categories, so they must survive untouched.
    gradient = np.array([0.016, 0.023, 0.032, 0.047, 0.064])
    kept = transport_positions(gradient)
    assert np.allclose(kept, np.log2(gradient))
    assert np.all(np.diff(kept) > 0)

    # A twofold panel with a gap keeps the gap: two dilutions apart is two, not one.
    gapped = np.array([1.0, 2.0, 8.0])
    assert np.allclose(np.diff(transport_positions(gapped)), [1.0, 2.0])


@pipeline
def test_printing_tolerance_cannot_swallow_a_gradient_step():
    from scripts.run_external_validation import _PRINTING_TOLERANCE_LOG2

    worst_printing_error = abs(math.log2(0.03) - math.log2(0.03125))
    smallest_gradient_step = 0.5
    assert worst_printing_error < _PRINTING_TOLERANCE_LOG2 < smallest_gradient_step - 0.1, (
        "the tolerance must separate a printed label from a real half-dilution step"
    )
