"""Deadlines and observable stages must not alter inferential guarantees."""
from time import monotonic
from fractions import Fraction
import numpy as np
import pytest
from mic_50_90 import joint_population as joint
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICBin, MICPanel


def fixture():
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in (1, 2, 3)))
    return {'a': EmpiricalProblem(n=5, panel=panel, quantiles=[],
        count_intervals=[(np.array([1., 1., 0.]), 2, 4)])}


def test_tail_probability_work_can_be_interrupted():
    with pytest.raises(TimeoutError):
        joint._binomial_tails(200, .371, deadline=monotonic()-1)


def test_point_certificate_respects_expired_budget_before_work():
    with pytest.raises(TimeoutError):
        joint._point_lower(200, [], [.371, .721], monotonic()-1)


def test_result_separates_baseline_and_refinement_timing():
    r = joint.population_distribution(fixture(), method='joint-exact', time_limit_seconds=0)
    assert r['status'] == 'time_limit'
    assert r['baseline_seconds'] >= 0
    assert r['refinement_seconds'] >= 0
    assert r['elapsed_seconds'] >= r['baseline_seconds']
    assert r['time_limit_scope'] == 'optional_joint_refinement'
    assert r['cdf_bounds'] == r['baseline_cdf_bounds']


def test_early_exclusion_returns_valid_upper_bound():
    p = fixture()
    matrices = [joint._prefix_distances(x) for x in p.values()]
    a = joint._box_upper(5, matrices, [.001, .002], [.002, .003], reject_below=Fraction(1,20))
    assert a < .05
    for x,y in ((.001,.002),(.002,.003),(.0015,.0025)):
        assert a >= joint.joint_report_pvalue(p,[x,y-x,1-y])-1e-12
