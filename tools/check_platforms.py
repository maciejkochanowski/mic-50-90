"""Check an installed wheel against tests extracted from its matching sdist.

On Windows, --linux also runs the selected checks under the Ubuntu WSL distro.
The complete Python test suite is measured separately. All imports use installed
packages, not a source-path override. Environments and logs are preserved.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile
import time

TESTS = [
    'tests/test_report_interface_consistency.py', 'tests/test_report_typography.py',
    'tests/test_result_explanations.py', 'tests/test_count_updates.py',
    'tests/test_gui_input_repairs.py', 'tests/test_gui_backend.py',
    'tests/test_distribution_calibration_reporting.py', 'tests/test_range_population.py',
    'tests/test_exact_population.py', 'tests/test_hunter_audit_safety.py',
    'tests/test_hunter_budget.py', 'tests/test_hunter_independent_boundaries.py',
    'tests/test_verifier_repairs.py',
]


def wsl_path(path):
    path=path.resolve()
    if not path.drive or len(path.drive)!=2:
        raise ValueError('Use a local Windows drive for WSL inputs.')
    return '/mnt/'+path.drive[0].lower()+'/'+path.as_posix()[3:]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',type=Path,required=True)
    parser.add_argument('--sdist',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--uv',default='uv')
    parser.add_argument('--linux',action='store_true')
    parser.add_argument('--versions',nargs='+',default=['3.11','3.12','3.13'])
    args=parser.parse_args()
    if any(v not in ('3.11','3.12','3.13') for v in args.versions):
        parser.error('Supported verification versions: 3.11, 3.12, 3.13.')
    output=args.output.resolve(); output.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
    env['PYTHONDONTWRITEBYTECODE']='1'; env['PYTHONUNBUFFERED']='1'
    wheel=args.wheel.resolve(); sdist=args.sdist.resolve()
    rows=[]
    for platform in (['windows','linux'] if args.linux else ['windows']):
        for version in args.versions:
            name=platform+'-'+version; work=output/name; work.mkdir(exist_ok=True)
            log=work/'run.log'; start=time.monotonic()
            command_log=[]; code=0
            if platform=='windows':
                with tarfile.open(sdist) as archive: archive.extractall(work,filter='data')
                source=work/'mic_50_90-1.0.0'; venv=work/'venv'
                python=venv/'Scripts/python.exe'
                commands=[
                    [args.uv,'venv','--allow-existing','--python',version,str(venv)],
                    [args.uv,'pip','install','--reinstall-package','mic-50-90','--python',str(python),str(wheel)+'[test]'],
                    [str(python),'-c','import sys, mic_50_90; print(sys.version); print(mic_50_90.__file__)'],
                    [str(python),'-B','-m','pytest','-q','-p','no:cacheprovider','--basetemp',str(work/'test-temporary'),'-o','tmp_path_retention_policy=failed',*TESTS],
                ]
            else:
                target='/tmp/mic-complete-audit-'+str(output.name)+'-'+version
                shell='set -e\nmkdir -p '+shlex.quote(target)+'\ncd '+shlex.quote(target)+'\n'
                shell+='tar -xzf '+shlex.quote(wsl_path(sdist))+'\n'
                shell+='uv venv --allow-existing --python '+shlex.quote(version)+' venv\n'
                shell+='uv pip install --reinstall-package mic-50-90 --python venv/bin/python '+shlex.quote(wsl_path(wheel)+'[test]')+'\n'
                shell+='cd mic_50_90-1.0.0\n'
                shell+='../venv/bin/python -c '+shlex.quote('import sys,mic_50_90; print(sys.version); print(mic_50_90.__file__)')+'\n'
                shell+='../venv/bin/python -B -m pytest -q -p no:cacheprovider --basetemp ../test-temporary -o tmp_path_retention_policy=failed '+shlex.join(TESTS)+'\n'
                commands=[['wsl','-d','Ubuntu','--','bash','-lc',shell]]; source=output
            with log.open('w',encoding='utf-8') as stream:
                for command in commands:
                    command_log.append(command)
                    run=subprocess.run(command,cwd=source,env=env,stdout=stream,stderr=subprocess.STDOUT)
                    if run.returncode:
                        code=run.returncode; break
            content=log.read_text(encoding='utf-8',errors='replace')
            counts=re.findall(r'(\d+) passed',content)
            row={'platform':platform,'python_requested':version,'exit_code':code,
                 'passed_tests':int(counts[-1]) if counts else 0,'elapsed_seconds':time.monotonic()-start,
                 'status':'passed' if code==0 and counts else 'failed','test_files':TESTS,
                 'wheel_sha256':sha256(wheel.read_bytes()).hexdigest(),
                 'sdist_sha256':sha256(sdist.read_bytes()).hexdigest(),
                 'commands':command_log,'log':log.relative_to(output).as_posix(),
                 'scope':'Selected installed-package regressions from matching extracted sdist; full test suite checked separately.'}
            rows.append(row)
            (output/'PLATFORM_MATRIX.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
            print(name,row['status'],row['passed_tests'],flush=True)
    return int(any(r['status']!='passed' for r in rows))


if __name__=='__main__':sys.exit(main())
