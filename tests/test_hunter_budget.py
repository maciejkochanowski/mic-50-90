"""Exact arithmetic must stop without converting unfinished work to rejection."""
from fractions import Fraction as F
from math import comb

import pytest


def test_nested_deadline_is_restored():
    from mic_50_90._hunter.budget import deadline_scope
    from mic_50_90._hunter.pairwise import _check_deadline
    with deadline_scope(10):
        with deadline_scope(0):
            with pytest.raises(TimeoutError):_check_deadline(None)
        _check_deadline(None)
    _check_deadline(None)


def test_exact_mass_loop_obeys_active_deadline():
    from mic_50_90._hunter.budget import deadline_scope
    from mic_50_90._hunter.pairwise import _binomial_masses
    _binomial_masses.cache_clear()
    with deadline_scope(0):
        with pytest.raises(TimeoutError):_binomial_masses(31,F(7,13))


def test_exact_pair_loop_obeys_active_deadline():
    from mic_50_90._hunter.budget import deadline_scope
    from mic_50_90._hunter.pairwise import _pair_exact
    with deadline_scope(0):
        with pytest.raises(TimeoutError):_pair_exact(31,(F(1,4),)*4)


@pytest.mark.parametrize('n',[1,2,3,10,20,100])
def test_integer_recurrence_matches_direct_binomial_formula(n):
    from mic_50_90._hunter.pairwise import _binomial_masses,exact_binomial_scores
    for q in [F(0),F(1),F(1,1000),F(1,3),F(99,100)]:
        expected=tuple(F(comb(n,c))*q**c*(1-q)**(n-c) for c in range(n+1))
        assert _binomial_masses(n,q)==expected
        assert exact_binomial_scores(n,q)==tuple(min(F(1),2*sum(expected[:c+1]),2*sum(expected[c:])) for c in range(n+1))


def test_slow_optional_proposal_cannot_erase_empirical_witnesses(monkeypatch):
    from mic_50_90._hunter import endpoint,pairwise
    region=pairwise.HistRegion(1000,3,(((0,1,300,300),(1,2,400,400),(2,3,300,300)),))
    def stop(*a,**kw):raise TimeoutError('optional work exhausted budget')
    monkeypatch.setattr(endpoint,'tied_witness',stop)
    monkeypatch.setattr(endpoint,'support_proposals',stop)
    monkeypatch.setattr(endpoint,'certify_witness',stop)
    r=endpoint.project(region,time_limit_seconds=1,max_boxes=1)
    assert [str(F(3,10)),str(F(2,5)),str(F(3,10))] in r['accepted_witnesses']
    assert all(x['inner_lower'] is not None for x in r['intervals'])
