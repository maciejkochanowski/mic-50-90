"""Direct count witnesses must certify population endpoints separately."""
from itertools import product

import numpy as np
import pytest

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.joint_population import population_distribution
from mic_50_90.model import MICBin, MICPanel
from mic_50_90.utility import _prefix_distances


def problem(h, constraints=()):
    n, k = sum(h), len(h)
    panel = MICPanel(tuple(MICBin(str(j), j, j, True, True, j) for j in range(k)))
    rows = list(constraints)
    for rank in ((n+1)//2, (9*n+9)//10):
        category = next(j for j, c in enumerate(np.cumsum(h)) if c >= rank)
        if category:
            rows.append((np.array([int(j < category) for j in range(k)]), 0, rank-1))
        rows.append((np.array([int(j <= category) for j in range(k)]), rank, n))
    return EmpiricalProblem(n=n, panel=panel, quantiles=[], count_intervals=rows)


def test_rows_are_feasible_and_attain_every_range_count_extremum():
    obj = problem((1, 1, 1, 1), [(np.array([0, 1, 1, 0]), 1, 3)])
    d = _prefix_distances(obj)
    matrix, low, high = obj.linear_constraints
    feasible = [np.array(h) for h in product(range(5), repeat=4) if sum(h) == 4
        and np.all(matrix@h >= low) and np.all(matrix@h <= high)]
    rows = [np.diff(row).astype(int) for row in d]
    for h in rows:
        assert np.all(h >= 0) and sum(h) == obj.n
        assert np.all(matrix@h >= low) and np.all(matrix@h <= high)
    for a in range(4):
        for b in range(a+1, 5):
            assert sum(rows[a][a:b]) == max(sum(h[a:b]) for h in feasible)
            assert sum(rows[b][a:b]) == min(sum(h[a:b]) for h in feasible)


@pytest.mark.parametrize('h', [(4, 4, 5, 3, 4), (13, 13, 13, 13, 16, 8, 12, 12)])
def test_incomplete_distribution_certified_without_histogram_enumeration(h, monkeypatch):
    import mic_50_90.range_population as engine
    def forbid(*args):
        raise AssertionError('Histogram enumeration is unnecessary for this control')
    monkeypatch.setattr(engine, '_histograms', forbid)
    result = population_distribution({'a': problem(h)}, method='range-calibrated', time_limit_seconds=15, include_intervals=True)
    assert result['precision_reached'] and result['endpoint_gap_pp'] < .01
    assert (0 < result['range_witnesses_checked'] <= len(h)
            or result['population_row_lift_certificate']['status'] == 'certified')
    assert not result['compatible_histogram_search_complete']


def test_failed_population_witness_does_not_become_an_attainment_claim(monkeypatch):
    import mic_50_90.joint_population as joint
    obj = problem((1, 1, 1))
    monkeypatch.setattr(joint, '_cp_inner', lambda *args: None)
    result = population_distribution({'a': obj}, method='range-calibrated', time_limit_seconds=1, include_intervals=True)
    assert result['compatible_histogram_search_complete']
    assert not result['precision_reached']
    assert all(row['inner_lower'] is None for row in result['interval_bounds'])
    for row in result['interval_bounds']:
        assert row['lower'] <= (row['stop_index']-row['start_index'])/3 <= row['upper']


def test_multiple_variants_retain_both_populations():
    left, right = problem((4, 3, 2, 1)), problem((1, 2, 3, 4))
    together = population_distribution({'left': left, 'right': right}, method='range-calibrated', time_limit_seconds=1, include_intervals=True)
    for obj in (left, right):
        one = population_distribution({'one': obj}, method='range-calibrated', time_limit_seconds=1, include_intervals=True)
        for a, b in zip(together['interval_bounds'], one['interval_bounds']):
            assert a['lower'] <= b['inner_lower'] <= b['inner_upper'] <= a['upper']
