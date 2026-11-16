"""HiGHS options confined to a freshly launched distribution worker.

The ordinary library never changes the native scheduler or its thread count.
"""
from scipy.optimize import linprog as _scipy_linprog, milp as _scipy_milp

_ISOLATED_WORKER = False


def _activate_isolated_worker():
    global _ISOLATED_WORKER
    _ISOLATED_WORKER = True


def _controlled_options(kwargs):
    if not _ISOLATED_WORKER:
        return kwargs
    result = dict(kwargs)
    result['options'] = {**(result.get('options') or {}), 'threads': 1}
    return result


def linprog(*args, **kwargs):
    return _scipy_linprog(*args, **_controlled_options(kwargs))


def milp(*args, **kwargs):
    return _scipy_milp(*args, **_controlled_options(kwargs))

