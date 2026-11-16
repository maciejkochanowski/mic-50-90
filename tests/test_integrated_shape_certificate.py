"""The integrated acceleration requires an independently checked certificate."""
from copy import deepcopy
from fractions import Fraction as F
from math import comb
from time import monotonic

import pytest
from mic_50_90 import _shape_generator as generator, _shape_receiver as receiver
from mic_50_90 import range_certificates as integrated


def rational_cdf(n, x, p):
    a, b = p.numerator, p.denominator
    return F(sum(comb(n,j)*a**j*(b-a)**(n-j) for j in range(x+1)), b**n)


@pytest.mark.parametrize('n', [1, 2, 5, 10, 20, 30])
def test_complete_certificate_against_independent_integer_oracle(n):
    cutoff = F(1, 100)
    result = integrated.binomial_shape_certificate(n, cutoff, monotonic()+20)
    assert result['status'] == 'certified' and result['receiver_verified']
    cert = result['arithmetic_certificate']
    assert receiver.verify_certificate(cert)['status'] == 'certified'
    for row in cert['rows'][:-1]:
        assert rational_cdf(n,row['count'],F(row['inner_upper'])) >= cutoff/2
        assert rational_cdf(n,row['count'],F(row['outer_upper'])) <= cutoff/2
    assert result['claim'] == integrated._legacy_binomial_shape_certificate(n,cutoff,monotonic()+20)['claim']


@pytest.mark.parametrize('n', [3, 7, 12])
def test_directed_partial_sums_contain_exact_probability(n):
    for x in range(n+1):
        for p in (F(0),F(1),F(1,10),F(1,3),F(x,n)):
            truth = rational_cdf(n,x,p)
            for precision in (40,60,80,120):
                bound = receiver.cdf_bounds(n,x,p,precision=precision,max_terms=1)
                assert F(bound.lower) <= truth <= F(bound.upper)


def test_certificate_policy_is_not_shared_with_receiver():
    result = generator.generate(5,F(1,100))
    result['certificate']['numerical_policy']['receiver_precisions'][0] = 2
    assert receiver.POLICY['receiver_precisions'] == [60,120]
    assert receiver.verify_certificate(result['certificate'])['status'] == 'rejected'


@pytest.mark.parametrize('defect', ['missing','margin','endpoint','cutoff','algorithm'])
def test_altered_certificates_are_never_certified(defect):
    cert = deepcopy(generator.generate(10,F(1,100))['certificate'])
    if defect == 'missing':cert['rows'].pop()
    elif defect == 'margin':cert['second_difference_lower_bounds'][0] = '1'
    elif defect == 'endpoint':
        cert['rows'][0].update(inner_upper='1',outer_upper='1')
        cert = receiver.certificate_data(10,F(1,100),cert['rows'])
    elif defect == 'cutoff':cert['cutoff'] = '1/2'
    else:cert['algorithm'] = 'unverified'
    assert receiver.verify_certificate(cert)['status'] != 'certified'


def test_generator_claim_without_receiver_proof_cannot_be_used(monkeypatch):
    original = generator.generate
    def wrong_target(*args,**kwargs):return original(5,F(1,10))
    monkeypatch.setattr(generator,'generate',wrong_target)
    result = integrated.binomial_shape_certificate(10,F(1,100),monotonic()+20)
    assert result['status'] == 'certified'  # independent old path is still valid
    assert not result.get('receiver_verified',False)
    assert result['acceleration']['reason'] == 'Accelerated certificate target mismatch'


def test_budget_exhaustion_does_not_claim_shape():
    result = integrated.binomial_shape_certificate(10000,F(1,100),monotonic()-1)
    assert result['status'] == 'unresolved'
    assert 'arithmetic_certificate' not in result


def test_unresolved_generator_preserves_legacy_fallback(monkeypatch):
    monkeypatch.setattr(generator,'generate',lambda *a,**k: dict(status='unresolved',
        reason='constructed failure',certificate=None,elapsed_seconds=0))
    result = integrated.binomial_shape_certificate(10,F(1,100),monotonic()+20)
    assert result['status'] == 'certified'
    assert result['acceleration']['status'] == 'unresolved'
    assert 'arithmetic_certificate' not in result


@pytest.mark.parametrize('receiver_status', ['rejected', 'unresolved'])
def test_unverified_certificate_and_missing_fallback_cannot_certify(monkeypatch, receiver_status):
    from mic_50_90 import joint_population
    monkeypatch.setattr(receiver, 'verify_certificate', lambda *a, **k:
        dict(status=receiver_status, reason='injected receiver failure', elapsed_seconds=0))
    monkeypatch.setattr(joint_population, '_cp_inner', lambda *a: None)
    result = integrated.binomial_shape_certificate(10, F(1,100), monotonic()+20)
    assert result['status'] == 'unresolved'
    assert result['acceleration']['receiver_status'] == receiver_status
    assert not result.get('receiver_verified', False)
    assert 'arithmetic_certificate' not in result
