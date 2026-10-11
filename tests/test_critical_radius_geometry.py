"""Critical radii must distinguish a limited search from an impossible truth."""
import numpy as np
import pytest

from mic_50_90.dro import critical_radius
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel


def wide_problem():
    panel = MICPanel.from_twofold_levels([1, 2**20], left_censored=False, right_censored=False)
    return EmpiricalProblem(n=2, panel=panel, quantiles=())


def test_default_radius_search_covers_the_declared_panel_diameter():
    result = critical_radius(problem=wide_problem(), reference=np.array([1., 0.]),
                             positions=None, objectives=[np.array([0., 1.])], truths=[1.])
    assert result == pytest.approx(20., abs=2e-6)


def test_explicit_short_search_is_reported_as_incomplete():
    with pytest.raises(RuntimeError, match='search ceiling'):
        critical_radius(problem=wide_problem(), reference=np.array([1., 0.]),
                        positions=None, objectives=[np.array([0., 1.])], truths=[1.], ceiling=8.)


def test_outside_sharp_truth_remains_impossible():
    result = critical_radius(problem=wide_problem(), reference=np.array([1., 0.]),
                             positions=None, objectives=[np.array([0., 1.])], truths=[2.])
    assert result == float('inf')


def test_custom_positions_determine_safe_search_range():
    result = critical_radius(problem=wide_problem(), reference=np.array([1., 0.]),
                             positions=np.array([0., 40.]), objectives=[np.array([0., 1.])], truths=[1.])
    assert result == pytest.approx(40., abs=4e-6)
