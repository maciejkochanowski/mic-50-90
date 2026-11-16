"""Isolation must preserve numerical answers and the caller's solver state."""
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

from mic_50_90.cli import main
from mic_50_90.distribution_workflow import analyse_distribution


def specimen():
    return dict(cohort_id='isolation-test', n=20, unit='mg/L', iid=True,
        panel={'levels': [1, 2]}, additional_counts=[
            dict(threshold=1, count=8, n=20, unit='mg/L'),
            dict(threshold=2, count=2, n=20, unit='mg/L')])


def scientific_result(value):
    if isinstance(value, dict):
        return {k: scientific_result(v) for k, v in value.items()
                if k != 'execution' and not k.endswith('_seconds')}
    if isinstance(value, list):
        return [scientific_result(v) for v in value]
    return value


@pytest.mark.parametrize('method', ['bonferroni', 'joint-exact', 'range-calibrated', 'range-hunter'])
def test_actual_worker_preserves_results_and_single_thread(method):
    options = dict(population_method=method, population_time_limit=0)
    direct = analyse_distribution(specimen(), **options)
    isolated = analyse_distribution(specimen(), **options, solver_execution='isolated')
    assert scientific_result(direct) == scientific_result(isolated)
    assert isolated['execution']['worker_pid'] != os.getpid()
    assert isolated['execution']['solver_threads'] == 1
    if sys.platform.startswith('linux'):
        assert isolated['execution']['observed_native_threads'] == 1


def test_invalid_input_is_a_validation_error_not_a_result():
    raw = specimen(); raw['additional_counts'][1]['count'] = 19
    with pytest.raises(ValueError):
        analyse_distribution(raw, solver_execution='isolated')


@pytest.mark.parametrize('timeout', [True, 0, -1, math.inf, math.nan, '1'])
def test_invalid_wall_limits_are_refused(timeout):
    with pytest.raises(ValueError, match='solver_timeout'):
        analyse_distribution(specimen(), solver_execution='isolated', solver_timeout=timeout)


def test_unknown_execution_mode_is_refused():
    with pytest.raises(ValueError, match='solver_execution'):
        analyse_distribution(specimen(), solver_execution='fork')


def test_actual_timeout_reaps_worker(monkeypatch):
    import mic_50_90.isolated_distribution as worker
    actual = worker.subprocess.Popen
    children = []
    def observed(*a, **kw):
        process = actual(*a, **kw); children.append(process); return process
    monkeypatch.setattr(worker.subprocess, 'Popen', observed)
    with pytest.raises(TimeoutError):
        analyse_distribution(specimen(), solver_execution='isolated', solver_timeout=.001)
    assert len(children) == 1 and children[0].poll() is not None


def test_optional_nonfinite_setting_retains_layer_diagnostics():
    direct = analyse_distribution(specimen(), population_planning_time_limit=math.inf)
    isolated = analyse_distribution(specimen(), population_planning_time_limit=math.inf,
                                    solver_execution='isolated')
    assert scientific_result(direct) == scientific_result(isolated)


def test_cli_exports_isolation_and_resume(tmp_path):
    source = tmp_path / 'input.json'; source.write_text(json.dumps(specimen()))
    output = tmp_path / 'result'
    args = ['distribution', str(source), '--output-dir', str(output),
            '--solver-execution', 'isolated', '--solver-timeout', '30']
    assert main(args) == 0
    configuration = json.loads((output / 'configuration.json').read_text())
    assert configuration['solver_execution'] == 'isolated'
    assert configuration['solver_timeout'] == 30
    result = json.loads((output / 'results.json').read_text())['cohorts'][0]
    assert result['execution']['solver_threads'] == 1
    updated = tmp_path / 'updated'
    assert main(['distribution', str(source), '--output-dir', str(updated),
        '--previous-output', str(output), '--solver-execution', 'isolated']) == 0
    again = json.loads((updated / 'results.json').read_text())['cohorts'][0]
    assert again['sample'] == result['sample']


@pytest.mark.parametrize('sequence', [
    ('lp-auto', 'lp-one'), ('lp-one', 'lp-auto'), ('lp-one', 'lp-one'),
    ('milp-auto', 'lp-one'), ('lp-auto', 'milp-one'), ('milp-one', 'milp-one')])
def test_six_native_scheduler_sequences_with_fresh_workers(sequence):
    # Each pair has a new parent scheduler. A one-thread call is executed in a
    # new interpreter; the parent's automatic scheduler is never reconfigured.
    import mic_50_90
    package_root = str(Path(mic_50_90.__file__).resolve().parent.parent)
    operation = '''
import json,os,sys,warnings
from pathlib import Path
import numpy as np
from scipy.optimize import linprog,milp,Bounds,LinearConstraint
def solve(kind,controlled=False):
    if controlled:
        from mic_50_90._solver_resources import _activate_isolated_worker
        from mic_50_90._solver_resources import linprog as lp,milp as ip
        _activate_isolated_worker()
    else:lp,ip=linprog,milp
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        r=lp([-1.,-2.],A_ub=[[1.,1.]],b_ub=[3.],bounds=[(0,10)]*2) if kind=='lp' else ip(
            [-1.,-2.],integrality=[1,1],bounds=Bounds([0,0],[10,10]),
            constraints=LinearConstraint([[1.,1.]],[-np.inf],[3.]))
    return dict(success=bool(r.success),value=float(r.fun),pid=os.getpid(),
        threads=len(list(Path('/proc/self/task').iterdir())) if Path('/proc/self/task').exists() else None)
'''
    controller = operation + '''
import subprocess
root,sequence,operation=json.loads(sys.argv[1])
sys.path.insert(0,root)
rows=[]
for entry in sequence:
    kind,mode=entry.split('-')
    if mode=='one':
        before=len(list(Path('/proc/self/task').iterdir())) if Path('/proc/self/task').exists() else None
        code='import sys;sys.path.insert(0,'+repr(root)+')\\n'+operation+'\\nprint(json.dumps(solve('+repr(kind)+',True)))'
        env=os.environ.copy();env.update({x:'1' for x in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']})
        p=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,timeout=20,env=env,check=True)
        row=json.loads(p.stdout)
        after=len(list(Path('/proc/self/task').iterdir())) if Path('/proc/self/task').exists() else None
        assert before==after
    else:row=solve(kind)
    rows.append(row)
print(json.dumps(rows))
'''
    process = subprocess.run([sys.executable, '-c', controller,
        json.dumps([package_root, sequence, operation])], capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stderr
    rows = json.loads(process.stdout)
    assert len(rows) == 2
    for entry, row in zip(sequence, rows):
        assert row['success'] and row['value'] == -6
        if entry.endswith('one') and sys.platform.startswith('linux'):
            assert row['threads'] == 1


@pytest.mark.parametrize('parent_solver', ['none', 'lp', 'milp'])
def test_public_analysis_after_parent_solver_use(parent_solver):
    import mic_50_90
    root=str(Path(mic_50_90.__file__).resolve().parent.parent)
    code='''
import sys,json,os
from pathlib import Path
root,kind,raw=json.loads(sys.argv[1]);sys.path.insert(0,root)
import numpy as np
from scipy.optimize import linprog,milp,Bounds,LinearConstraint
from mic_50_90.distribution_workflow import analyse_distribution
def solve():
    if kind=='none':return None
    if kind=='lp':r=linprog([-1.,-2.],A_ub=[[1.,1.]],b_ub=[3.],bounds=[(0,10)]*2)
    else:r=milp([-1.,-2.],integrality=[1,1],bounds=Bounds([0,0],[10,10]),constraints=LinearConstraint([[1.,1.]],[-np.inf],[3.]))
    assert r.success and r.fun==-6
    return float(r.fun)
before_value=solve();threads=lambda:len(list(Path('/proc/self/task').iterdir())) if Path('/proc/self/task').exists() else None
before=threads();result=analyse_distribution(raw,solver_execution='isolated')
assert threads()==before and result['execution']['worker_pid']!=os.getpid()
assert solve()==before_value and threads()==before
print(json.dumps(result))
'''
    process=subprocess.run([sys.executable,'-I','-c',code,json.dumps([root,parent_solver,specimen()])],
        capture_output=True,text=True,timeout=60)
    assert process.returncode==0,process.stderr
    result=json.loads(process.stdout)
    assert scientific_result(result)==scientific_result(analyse_distribution(specimen()))
    if sys.platform.startswith('linux'):assert result['execution']['observed_native_threads']==1
