"""Nested, context-local cooperative deadlines for exact numerical work."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from math import isfinite
from time import monotonic

_deadline = ContextVar('mic_hunter_deadline', default=None)


def effective_deadline(explicit=None):
    active = _deadline.get()
    if explicit is None:return active
    return explicit if active is None else min(explicit,active)


@contextmanager
def deadline_scope(seconds):
    if not isfinite(seconds) or seconds < 0:
        raise ValueError('Calculation budget must be finite and nonnegative')
    token = _deadline.set(effective_deadline(monotonic()+seconds))
    try:
        yield
    finally:
        _deadline.reset(token)


def bounded_calculation(function):
    @wraps(function)
    def run(*args, **kwargs):
        with deadline_scope(kwargs.get('time_limit_seconds',120)):
            return function(*args,**kwargs)
    return run
