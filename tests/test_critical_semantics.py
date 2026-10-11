"""Small decisive checks for mutations that can change a scientific answer."""
from fractions import Fraction as F
from time import monotonic

import pytest

from mic_50_90 import joint_population, range_certificates
from mic_50_90.count_updates import counts_from_percentage
from mic_50_90.decisions import classify_intervals, assess_population_question
from mic_50_90.model import MICBin
from mic_50_90.range_certificates import binomial_shape_certificate, close_counts, split_count_cell
from mic_50_90.range_population import _rounded


@pytest.mark.parametrize('op,answer', [('<','contradicted'),('<=','supported'),('>','contradicted'),('>=','supported')])
def test_decision_at_exact_equality(op, answer):
    assert classify_intervals([[F(1,20),F(1,20)]], op, F(1,20)) == answer
    assert classify_intervals([[0, F(1,10)]], op, F(1,20)) == 'undetermined'
    assert classify_intervals([], op, F(1,20)) == 'unavailable'


def test_disjoint_possibilities_must_not_be_intersected():
    assert classify_intervals([[F(1,100),F(2,100)], [F(8,100),F(9,100)]], '<', F(5,100)) == 'undetermined'


def test_unconfirmed_population_endpoint_cannot_settle_question():
    result = assess_population_question(0, 1, '<', F(1,2), inner_lower=F(1,2), inner_upper=F(3,4))
    assert result['status'] == 'undetermined'
    assert result['calculation_assessment'] == 'numerically_unresolved'
    assert result['further_computation_may_change_answer']
    result = assess_population_question(0, 1, '<', F(1,2), inner_lower=F(1,4), inner_upper=F(3,4))
    assert result['calculation_assessment'] == 'region_crosses_target'
    assert not result['further_computation_may_change_answer']


@pytest.mark.parametrize('places,percentage,n,rule,expected', [
    (0,'12',200,'half_up',(23,24)), (0,'12',200,'half_even',(23,25)),
    (0,'13',200,'half_even',(26,26)), (0,'12',200,'floor',(24,25)),
    (0,'12',200,'ceiling',(23,24)), (0,'0',200,'half_up',(0,0)),
    (0,'100',200,'half_up',(199,200)), (1,'12.5',8,'half_up',(1,1)),
])
def test_rounding_boundaries(places,percentage,n,rule,expected):
    assert counts_from_percentage(percentage,n=n,decimal_places=places,rounding_rule=rule) == expected


def test_invalid_percentage_cannot_supply_a_constraint():
    for percentage,n,places,rule in [('101',5,0,'half_up'),('12.2',5,0,'half_up'),('20',0,0,'floor'),('20',5,7,'floor'),('20',5,0,'unknown'),('12',3,0,'half_up')]:
        with pytest.raises(ValueError):
            counts_from_percentage(percentage,n=n,decimal_places=places,rounding_rule=rule)


@pytest.mark.parametrize('lower,upper,closed,c,answer', [
    (None,4,False,2,'ambiguous'), (None,4,False,4,'below'),
    (32,None,False,32,'above'), (32,None,True,32,'ambiguous'),
    (32,None,False,64,'ambiguous'), (4,8,False,3,'above'),
])
def test_measurement_boundaries(lower,upper,closed,c,answer):
    b=MICBin('measured',lower,upper,closed,True,8)
    assert b.latent_status(c) == answer


def test_outward_fraction_conversion_contains_rational_truth():
    for q in (F(1,10),F(1,3),F(7,13)):
        assert F(_rounded(q,False)) <= q <= F(_rounded(q,True))


def test_unresolved_shape_comparison_is_not_a_false_certificate(monkeypatch):
    lo = [F(1,8),F(1,2),F(1)]
    hi = [F(3,8),F(3,4),F(1)]
    monkeypatch.setattr(joint_population,'_cp_inner',lambda x,n,c:(0,lo[x]))
    monkeypatch.setattr(joint_population,'_cp_outer',lambda x,n,c:(0,hi[x]))
    result=binomial_shape_certificate(2,F(1,20),monotonic()+10)
    assert result['status']=='unresolved'
    assert isinstance(result.get('reason'), str) and result['reason'].strip()


def test_exact_shape_equality_is_a_valid_certificate(monkeypatch):
    monkeypatch.setattr(joint_population,'_cp_inner',lambda x,n,c:(0,F(x+1,4)))
    monkeypatch.setattr(joint_population,'_cp_outer',lambda x,n,c:(0,F(x+1,4)))
    result=binomial_shape_certificate(3,F(1,20),monotonic()+10)
    assert result['status']=='certified'
    assert result['minimum_concavity_margin']=='0'


def test_expired_or_missing_shape_certificate_remains_unresolved(monkeypatch):
    result = binomial_shape_certificate(2,F(1,20),0)
    assert result['status']=='unresolved'
    assert isinstance(result.get('reason'), str) and result['reason'].strip()
    monkeypatch.setattr(joint_population,'_cp_inner',lambda *args:None)
    result = binomial_shape_certificate(2,F(1,20),monotonic()+10)
    assert result['status']=='unresolved'
    assert isinstance(result.get('reason'), str) and result['reason'].strip()


@pytest.mark.parametrize('n', [1, 3, 7])
def test_real_shape_certificate_retains_its_scope(n):
    cutoff = F(1, 37)
    result = binomial_shape_certificate(n, cutoff, monotonic()+30)
    assert result['status'] == 'certified'
    assert result['n'] == n
    assert F(result['critical_score_fraction']) == cutoff
    assert isinstance(result['claim'], str) and result['claim'].strip()
    if n == 1:
        assert result['minimum_concavity_margin'] is None
    else:
        assert F(result['minimum_concavity_margin']) >= 0


def test_exact_deadline_does_not_start_endpoint_calculation(monkeypatch):
    monkeypatch.setattr(range_certificates, 'monotonic', lambda: 100)
    monkeypatch.setattr(joint_population, '_cp_inner', lambda *args: pytest.fail('deadline reached'))
    result = binomial_shape_certificate(2, F(1,20), 100)
    assert result['status'] == 'unresolved'


def test_inconsistent_difference_cycle_is_refused():
    assert close_counts([[0,1],[-2,0]]) is None
    assert close_counts([[0,1],[-1,0]]) == [[0,1],[-1,0]]


def test_integer_partition_does_not_round_through_binary_float():
    # Exercise the integer arithmetic contract independently of sample enumeration.
    n = 2**54 + 1
    parent = close_counts([[0,n,n],[0,0,n],[-n,0,0]])
    left, right = split_count_cell(parent)
    intersection = [[min(a,b) for a,b in zip(l,r)] for l,r in zip(left,right)]
    assert close_counts(intersection) is None
    assert left[0][1] + right[1][0] == -1
    assert left[0][1] == n//2
