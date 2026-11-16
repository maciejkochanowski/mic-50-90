"""Private fresh-process worker. Invoked by absolute path with Python -I."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import signal
import sys
import warnings


def main():
    parent_pid = int(sys.argv[1])
    if sys.platform.startswith('linux'):
        if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            raise RuntimeError('Cannot establish parent-death signal')
        if os.getppid() != parent_pid:
            raise RuntimeError('Distribution controller ended before worker startup')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    response = {'schema': 'mic5090-isolated-response/1'}
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or set(request) != {'raw', 'options'}:
            raise ValueError('Invalid isolated request')
        from mic_50_90._solver_resources import _activate_isolated_worker
        from mic_50_90.distribution_workflow import analyse_distribution
        _activate_isolated_worker()
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always')
            result = analyse_distribution(request['raw'], **request['options'])
        counts = {}
        for item in captured:
            key = (item.category.__name__, str(item.message))
            counts[key] = counts.get(key, 0) + 1
        native_threads = (len(list(Path('/proc/self/task').iterdir()))
                          if sys.platform.startswith('linux') else None)
        response.update(status='ok', result=result, execution={
            'mode': 'isolated', 'worker_pid': os.getpid(), 'solver_threads': 1,
            'observed_native_threads': native_threads,
            'warnings': [{'category': k[0], 'message': k[1], 'count': v}
                         for k, v in sorted(counts.items())]})
    except Exception as exc:
        response.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)})
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()

