"""Integer rank boundaries must tolerate float complement roundoff."""
import pytest

from mic_50_90.calibration_audit import plan_calibration
from mic_50_90.conformal import conformal_rank


@pytest.mark.parametrize('level,alpha,m,rank', [
    (.90, .10, 9, 9), (.95, .05, 19, 19), (.99, .01, 99, 99),
    (.56, .44, 24, 14), (.28, .72, 24, 7), (.42, .58, 49, 21),
    (59/60, 1/60, 59, 59),
])
def test_literal_and_complemented_levels_agree(level, alpha, m, rank):
    assert conformal_rank(m, alpha) == rank
    assert conformal_rank(m, 1-level) == rank
    assert plan_calibration(level=level, calibration_units=m)['marginal_rank'] == rank


def test_levels_clearly_beyond_roundoff_retain_distinct_ranks():
    assert conformal_rank(24, .44-1e-10) == 15
    assert conformal_rank(24, .44+1e-10) == 14
    assert plan_calibration(level=.56+1e-10, calibration_units=24)['marginal_rank'] == 15
    assert plan_calibration(level=.56-1e-10, calibration_units=24)['marginal_rank'] == 14
