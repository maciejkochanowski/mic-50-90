"""Shared helpers for the evaluation scripts.

Import this module before NumPy or SciPy: it limits BLAS and OpenMP to one thread
per process, so that parallel workers do not compete for cores.
"""
from __future__ import annotations

import os

for _name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(_name, '1')

import argparse
import csv
import gzip
import io
import hashlib
import importlib.metadata
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
RESULTS = HERE / 'results'
METHODS = ('bonferroni', 'joint-exact', 'range-calibrated', 'range-hunter')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value, indent=1):
    """Write JSON atomically, so that an interrupted run never leaves a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, indent=indent, allow_nan=False, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def read_jsonl(path):
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(key for row in rows for key in row))
    if path.suffix == '.gz':
        handle = io.TextIOWrapper(gzip.GzipFile(path, 'wb', mtime=0), encoding='utf-8', newline='')
    else:
        handle = path.open('w', encoding='utf-8', newline='')
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def environment():
    """Package version and the machine, recorded in every output."""
    import mic_50_90
    record = dict(package='mic-50-90', package_version=mic_50_90.__version__,
                  python=platform.python_version(), platform=platform.platform(),
                  machine=platform.machine(), node=platform.node(), logical_cpus=os.cpu_count(),
                  versions={name: _version(name) for name in ('numpy', 'scipy')},
                  thread_limits={key: os.environ.get(key) for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
                  protocol_sha256=sha256(HERE / 'PROTOCOL.md'))
    if sys.platform.startswith('linux'):
        try:
            text = Path('/proc/cpuinfo').read_text()
            record['processor'] = next(line.split(':', 1)[1].strip() for line in text.splitlines() if line.startswith('model name'))
            record['available_cpus'] = len(os.sched_getaffinity(0))
        except (OSError, StopIteration):
            pass
    return record


def _version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def parser(description, workers=True):
    result = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    result.add_argument('--output', type=Path, default=RESULTS,
                        help='results folder; each comparison writes its own subfolder (default: evaluation/results)')
    if workers:
        result.add_argument('--workers', type=int, default=os.cpu_count(), help='parallel processes (default: all CPUs)')
    return result


def population_cohorts():
    """The twenty cohorts: ten FDA animal-pathogen and ten NORM 2024 human cohorts, in a fixed order."""
    rows = read_json(DATA / 'population_cohorts.json')
    assert len(rows) == 20 and len({r['case'] for r in rows}) == 20
    return rows


def range_kind(start, stop, k):
    """Cumulative: starts at the first or ends at the last category; single: one internal category."""
    if start == 0 or stop == k:
        return 'cumulative'
    return 'single' if stop - start == 1 else 'internal'


def proper_ranges(result):
    """Interval bounds of every contiguous range except the whole panel."""
    k = len(result['category_bounds'])
    return k, [b for b in result['interval_bounds'] if not (b['start_index'] == 0 and b['stop_index'] == k)]


def check_settings(path, settings):
    """Resume only a run with the same settings; otherwise ask for a new output folder."""
    path = Path(path)
    if path.exists():
        saved = read_json(path)['settings']
        if saved != settings:
            raise SystemExit(f'{path.parent} holds a run with other settings {saved}; use another --output or delete it')


def gzip_text(path):
    """A text handle for a gzip file with a fixed header time, so that equal content gives equal bytes."""
    return io.TextIOWrapper(gzip.GzipFile(path, 'wb', mtime=0, compresslevel=9), encoding='utf-8')
