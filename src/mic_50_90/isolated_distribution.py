"""Fresh-interpreter execution without changing the caller's native solver."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

_ERRORS = {cls.__name__: cls for cls in (ValueError, TypeError, KeyError,
    RuntimeError, TimeoutError, MemoryError, ArithmeticError)}
_THREAD_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
               'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS')


def _stop(process):
    if process.poll() is not None:
        return
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        process.kill()
    process.communicate()


def analyse_isolated(raw, options, timeout):
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError('solver_timeout must be a finite positive number of seconds')
    # This private Python-to-Python transport preserves existing nonfinite-option
    # diagnostics. Successful public results are serialized with allow_nan=False.
    payload = json.dumps({'raw': raw, 'options': options}, ensure_ascii=False)
    worker = Path(__file__).with_name('_isolated_distribution_worker.py')
    env = os.environ.copy()
    env.update({name: '1' for name in _THREAD_ENV})
    started = time.perf_counter()
    executable = sys.executable
    # CPython's Windows venv redirector creates another process. Bypass it so
    # Popen owns the actual worker PID (also essential for timeout cleanup),
    # retaining the venv through the same mechanism as multiprocessing.
    if sys.platform == 'win32' and not getattr(sys, 'frozen', False):
        base_executable = getattr(sys, '_base_executable', sys.executable)
        if os.path.normcase(base_executable) != os.path.normcase(sys.executable):
            executable = base_executable
            env['__PYVENV_LAUNCHER__'] = sys.executable
    process = subprocess.Popen([executable, '-I', str(worker), str(os.getpid())],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', env=env, start_new_session=(os.name == 'posix'))
    try:
        stdout, stderr = process.communicate(payload, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _stop(process)
        raise TimeoutError(f'Isolated distribution exceeded {timeout:g} seconds') from exc
    except BaseException:
        _stop(process)
        raise
    if process.returncode:
        raise RuntimeError(f'Isolated distribution worker exited with status '
                           f'{process.returncode}: {stderr[-2000:]}')
    try:
        response = json.loads(stdout)
        if response.get('schema') != 'mic5090-isolated-response/1':
            raise ValueError('unknown response schema')
        if response.get('status') == 'error':
            error = response.get('error', {})
            error_type = _ERRORS.get(error.get('type'), RuntimeError)
            message = str(error.get('message', 'Unspecified worker error'))
        elif response.get('status') == 'ok' and isinstance(response.get('result'), dict):
            result = response['result']
            info = response['execution']
            if (info.get('solver_threads') != 1 or info.get('worker_pid') != process.pid
                    or info.get('mode') != 'isolated'):
                raise ValueError('worker execution metadata mismatch')
            result['execution'] = {**info, 'wall_limit_seconds': timeout,
                'elapsed_seconds': time.perf_counter() - started}
            return result
        else:
            raise ValueError('incomplete response')
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RuntimeError('Invalid isolated distribution response: ' + str(exc)) from exc
    raise error_type(message)

