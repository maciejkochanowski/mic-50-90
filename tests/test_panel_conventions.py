"""Where the package places a category.

``MICPanel.from_twofold_levels`` gives the open top category a *representative
concentration*, one dilution above the last tested level. It feeds the recorded-panel
estimand, never the sharp bounds. The lowest category is left-censored unless the caller
closes it, and a threshold strictly inside a category is ambiguous rather than assigned.
"""
from __future__ import annotations

from mic_50_90.model import MICPanel


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

