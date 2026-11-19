"""Control flow of binomial_shape_certificate: time budget, accelerated certificate, receiver check and fallback.

The accelerated certificate is used only after the independent receiver has verified it. Every
other path keeps a record of the attempt in 'acceleration' and falls back to the legacy check.
"""
from fractions import Fraction as F

import numpy as np
import pytest

from mic_50_90 import _shape_generator as generator
from mic_50_90 import _shape_receiver as receiver
from mic_50_90 import range_certificates as rc

CLAIM = ('At most K distinct histograms from K+1 indexed count rows attain all contiguous population '
         'projection endpoints in each reporting variant; no equality of full regions is claimed')


def fixed_clock(monkeypatch, *values):
    """monotonic() returns the given values in turn and then repeats the last one."""
    values = list(values)

    def clock():
        return values.pop(0) if len(values) > 1 else values[0]
    monkeypatch.setattr(rc, 'monotonic', clock)


def legacy_spy(monkeypatch, result=None):
    calls = []

    def legacy(n, cutoff, deadline):
        calls.append((n, cutoff, deadline))
        return dict(result or dict(status='certified', source='legacy'))
    monkeypatch.setattr(rc, '_legacy_binomial_shape_certificate', legacy)
    return calls


def generator_returning(monkeypatch, **produced):
    calls = []

    def generate(n, cutoff, *, deadline):
        calls.append((n, cutoff, deadline))
        return dict(produced)
    monkeypatch.setattr(generator, 'generate', generate)
    return calls


def receiver_returning(monkeypatch, **checked):
    calls = []

    def verify(certificate, *, deadline):
        calls.append((certificate, deadline))
        return dict(checked)
    monkeypatch.setattr(receiver, 'verify_certificate', verify)
    return calls


def test_no_time_left_at_the_start(monkeypatch):
    fixed_clock(monkeypatch, 5.0)
    calls = legacy_spy(monkeypatch)
    assert rc.binomial_shape_certificate(3, F(1, 37), 5.0) == dict(status='unresolved', reason='Shape certificate time limit')
    assert rc.binomial_shape_certificate(3, F(1, 37), 4.0) == dict(status='unresolved', reason='Shape certificate time limit')
    assert calls == []


def test_receiver_verified_certificate_end_to_end():
    result = rc.binomial_shape_certificate(3, '2/74', float('inf'))
    assert set(result) == {'status', 'n', 'critical_score_fraction', 'minimum_concavity_margin', 'claim', 'algorithm',
                           'arithmetic_certificate', 'receiver_verified', 'acceleration'}
    certificate = result['arithmetic_certificate']
    checked = receiver.verify_certificate(certificate)
    assert checked['status'] == 'certified'
    assert result['status'] == 'certified' and result['n'] == 3 and result['critical_score_fraction'] == '1/37'
    assert result['minimum_concavity_margin'] == checked['minimum_concavity_margin']
    assert result['claim'] == CLAIM and result['algorithm'] == receiver.ALGORITHM and result['receiver_verified'] is True
    assert certificate['n'] == 3 and certificate['cutoff'] == '1/37'
    attempt = result['acceleration']
    assert set(attempt) == {'status', 'reason', 'generator_seconds', 'receiver_status', 'receiver_reason', 'receiver_seconds'}
    assert attempt['status'] == 'certified' and attempt['reason'] is None
    assert attempt['receiver_status'] == 'certified' and attempt['receiver_reason'] is None
    assert attempt['generator_seconds'] >= 0 and attempt['receiver_seconds'] >= 0


def test_generator_and_receiver_budget_shares(monkeypatch):
    fixed_clock(monkeypatch, 100.0)
    certificate = dict(n=3, cutoff='1/37')
    generated = generator_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=.5, certificate=certificate)
    checked = receiver_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=.25,
                                 minimum_concavity_margin='1/9')
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(3, '2/74', 110.0)
    assert generated == [(3, F(1, 37), 100.0 + .45 * 10.0)]
    assert checked == [(certificate, 100.0 + .9 * 10.0)]
    assert calls == []
    assert result == dict(status='certified', n=3, critical_score_fraction='1/37', minimum_concavity_margin='1/9',
                          claim=CLAIM, algorithm=receiver.ALGORITHM, arithmetic_certificate=certificate,
                          receiver_verified=True,
                          acceleration=dict(status='certified', reason=None, generator_seconds=.5,
                                            receiver_status='certified', receiver_reason=None, receiver_seconds=.25))


@pytest.mark.parametrize('n', [0, 10001, np.int64(3), 3.0, True])
def test_outside_the_accelerated_domain(monkeypatch, n):
    generated = generator_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=0., certificate=None)
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(n, F(1, 37), float('inf'))
    assert generated == []
    assert calls == [(n, F(1, 37), float('inf'))]
    assert result == dict(status='certified', source='legacy',
                          acceleration=dict(status='not_attempted', reason='Outside accelerated n domain'))


@pytest.mark.parametrize('n', [1, 10000])
def test_domain_limits_are_attempted(monkeypatch, n):
    generated = generator_returning(monkeypatch, status='unresolved', reason='limit', elapsed_seconds=.75, certificate=None)
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(n, F(1, 37), float('inf'))
    assert len(generated) == 1 and generated[0][0] == n
    assert calls == [(n, F(1, 37), float('inf'))]
    assert result == dict(status='certified', source='legacy',
                          acceleration=dict(status='unresolved', reason='limit', generator_seconds=.75))


@pytest.mark.parametrize('error', [ValueError('bad value'), ArithmeticError('bad arithmetic'),
                                   RuntimeError('bad run'), MemoryError('no memory')])
def test_generator_errors_are_recorded(monkeypatch, error):
    def generate(n, cutoff, *, deadline):
        raise error
    monkeypatch.setattr(generator, 'generate', generate)
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(3, F(1, 37), float('inf'))
    assert calls == [(3, F(1, 37), float('inf'))]
    assert result == dict(status='certified', source='legacy',
                          acceleration=dict(status='unresolved', reason=str(error), error_type=type(error).__name__))


@pytest.mark.parametrize('certificate', [dict(n=4, cutoff='1/37'), dict(n=3, cutoff='1/36'), dict(cutoff='1/37'),
                                         dict(n=3)])
def test_certificate_for_another_target_is_refused(monkeypatch, certificate):
    generator_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=.5, certificate=certificate)
    checked = receiver_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=.25,
                                 minimum_concavity_margin='1/9')
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(3, '2/74', float('inf'))
    assert checked == []
    assert calls == [(3, '2/74', float('inf'))]
    assert result == dict(status='certified', source='legacy',
                          acceleration=dict(status='unresolved', reason='Accelerated certificate target mismatch',
                                            generator_seconds=.5, error_type='ValueError'))


@pytest.mark.parametrize('status', ['rejected', 'unresolved'])
def test_receiver_must_certify(monkeypatch, status):
    certificate = dict(n=3, cutoff='1/37')
    generator_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=.5, certificate=certificate)
    receiver_returning(monkeypatch, status=status, reason='not proved', elapsed_seconds=.25)
    calls = legacy_spy(monkeypatch, dict(status='unresolved', reason='legacy reason'))
    result = rc.binomial_shape_certificate(3, F(1, 37), float('inf'))
    assert calls == [(3, F(1, 37), float('inf'))]
    assert result == dict(status='unresolved', reason='legacy reason',
                          acceleration=dict(status='certified', reason=None, generator_seconds=.5,
                                            receiver_status=status, receiver_reason='not proved', receiver_seconds=.25))


def test_no_certificate_from_the_generator(monkeypatch):
    generator_returning(monkeypatch, status='unresolved', reason='Negative sufficient margin', elapsed_seconds=.5,
                        certificate=None)
    checked = receiver_returning(monkeypatch, status='certified', reason=None, elapsed_seconds=0.)
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(3, F(1, 37), float('inf'))
    assert checked == [] and len(calls) == 1
    assert result['acceleration'] == dict(status='unresolved', reason='Negative sufficient margin', generator_seconds=.5)


@pytest.mark.parametrize('second, legacy_used', [(10.0, False), (11.0, False), (9.999, True)])
def test_deadline_after_the_accelerated_attempt(monkeypatch, second, legacy_used):
    fixed_clock(monkeypatch, 0.0, second)
    generator_returning(monkeypatch, status='unresolved', reason='limit', elapsed_seconds=.5, certificate=None)
    calls = legacy_spy(monkeypatch)
    result = rc.binomial_shape_certificate(3, F(1, 37), 10.0)
    attempt = dict(status='unresolved', reason='limit', generator_seconds=.5)
    if legacy_used:
        assert calls == [(3, F(1, 37), 10.0)]
        assert result == dict(status='certified', source='legacy', acceleration=attempt)
    else:
        assert calls == []
        assert result == dict(status='unresolved', reason='Shape certificate time limit', acceleration=attempt)
