"""Real calibration jobs keep their shard when other jobs finish or a run resumes."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest


@pytest.mark.parametrize('order', [(0, 1), (1, 0)])
@pytest.mark.parametrize('partial_completion', [False, True])
def test_real_shards_keep_ownership_after_staggered_completion(
    tmp_path, monkeypatch, order, partial_completion
):
    evaluation = Path(__file__).resolve().parents[1] / 'evaluation'
    monkeypatch.syspath_prepend(str(evaluation))
    spec = importlib.util.spec_from_file_location(
        'external_calibration_under_test', evaluation / 'external_calibration.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    datasets = {
        'alpha': {'level': .9},
        'ineligible': {'level': None, 'units': 4},
        'beta': {'level': .95},
        'gamma': {'level': .9},
    }
    data = tmp_path / 'data'
    (data / 'benchmark').mkdir(parents=True)
    (data / 'benchmark' / 'summary.json').write_text(
        json.dumps({'calibration_datasets': datasets}), encoding='utf-8'
    )
    monkeypatch.setattr(module, 'DATA', data)
    output = tmp_path / 'output'

    def summary_path(job):
        name, reference = job
        return output / 'external_calibration' / f'{name}-{reference}' / 'summary.json'

    # These are the owners in the original complete, eligible job list.
    expected = {
        0: [('alpha', 'uniform'), ('beta', 'uniform'), ('gamma', 'uniform')],
        1: [('alpha', 'trained'), ('beta', 'trained'), ('gamma', 'trained')],
    }
    completed = {('alpha', 'uniform'), ('beta', 'trained')} if partial_completion else set()
    for job in completed:
        path = summary_path(job)
        path.parent.mkdir(parents=True)
        path.write_text('{"preserved": true}\n', encoding='utf-8')

    executed = []

    def record_job(task):
        name, reference, info, folder, keep_work = task
        job = (name, reference)
        assert info == datasets[name]
        assert folder == output / 'external_calibration'
        assert keep_work is False
        path = summary_path(job)
        assert not path.exists(), 'A completed job must never execute again'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"completed": true}\n', encoding='utf-8')
        executed.append(job)
        return job

    class InlineExecutor:
        """Run the actual main-loop scheduling without expensive calibration workers."""
        def __init__(self, max_workers):
            assert max_workers == 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def map(self, function, tasks):
            return map(function, tasks)

    monkeypatch.setattr(module, 'real_job', record_job)
    monkeypatch.setattr(module, 'ProcessPoolExecutor', InlineExecutor)

    def run_shard(shard):
        monkeypatch.setattr(sys, 'argv', [
            'external_calibration.py', '--parts', 'real', '--workers', '1',
            '--shard', f'{shard}/2', '--output', str(output),
        ])
        start = len(executed)
        module.main()
        return executed[start:]

    # The second shard starts after the first has written all of its summaries.
    for shard in order:
        assert run_shard(shard) == [job for job in expected[shard] if job not in completed]
    assert set(executed) | completed == set(expected[0] + expected[1])
    assert len(executed) == len(set(executed))
    for shard in reversed(order):
        assert run_shard(shard) == []
    for job in completed:
        assert summary_path(job).read_text(encoding='utf-8') == '{"preserved": true}\n'
