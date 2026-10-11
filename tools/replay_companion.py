"""Run the documented command-line examples from an extracted article companion.

Install the supplied wheel first. This writes the output/ folders named in
COMMANDS.txt and a separate receipt. Installation and shell-setup instructions
are deliberately not executed by this helper.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time


def cli_identity(env, cwd):
    """Measure the package in the same child context used for documented commands."""
    code = """import json,sys
from pathlib import Path
from importlib import metadata
import mic_50_90
d=metadata.distribution('mic-50-90')
module=Path(mic_50_90.__file__).resolve()
expected=Path(d.locate_file('mic_50_90/__init__.py')).resolve()
base=Path(d.locate_file('')).resolve()
print(json.dumps(dict(module=str(module),distribution_module=str(expected),distribution_root=str(base),
    installed_distribution_import=module==expected and module.is_relative_to(base),
    python=sys.version,package_version=d.version,dependencies={n:metadata.version(n) for n in ('numpy','scipy')})))
"""
    probe = subprocess.run([sys.executable, '-c', code], cwd=cwd, env=env, check=True,
                           capture_output=True, text=True, encoding='utf-8', timeout=60)
    identity = json.loads(probe.stdout)
    if not identity['installed_distribution_import']:
        raise RuntimeError('CLI import does not match the installed distribution: ' + identity['module'])
    return identity


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    package=args.package.resolve(); receipt=args.receipt.resolve()
    commands=package/'COMMANDS.txt'
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
    env['PYTHONDONTWRITEBYTECODE']='1'
    jobs=[]
    for line_number,line in enumerate(commands.read_text(encoding='utf-8').splitlines(),1):
        line=line.strip()
        if line=='mic-50-90 gui': continue
        if line.startswith('mic-50-90 '):command=[sys.executable,'-m','mic_50_90',*shlex.split(line)[1:]]
        elif line.startswith('python verify_report.py '):command=[sys.executable,*shlex.split(line)[1:]]
        else:continue
        jobs.append((line_number,line,command))
    if not jobs:
        parser.error('COMMANDS.txt contains no supported command-line examples')
    logs=[receipt.parent/('command-'+str(i).zfill(2)+'.log') for i in range(1,len(jobs)+1)]
    destinations=[receipt,*logs]
    if len(set(destinations)) != len(destinations) or any(path.exists() for path in destinations):
        parser.error('Use a new receipt and log directory; existing inputs and evidence must not be overwritten')
    output_directories=[(package/'output').resolve()]
    output_files=[]
    for _,_,command in jobs:
        for index,argument in enumerate(command):
            flag,separator,value=argument.partition('=')
            if flag not in ('--output-dir','--output','--html'):
                continue
            if not separator:
                if index+1 == len(command):
                    parser.error('Missing output path in a documented command')
                value=command[index+1]
            destination=(package/value).resolve()
            (output_directories if flag=='--output-dir' else output_files).append(destination)
    if any(path.is_relative_to(directory) for path in destinations for directory in output_directories) or any(
        path == output for path in destinations for output in output_files
    ):
        parser.error('Receipt and logs must be separate from calculated command outputs')
    identity=cli_identity(env,package)
    receipt.parent.mkdir(parents=True,exist_ok=True)
    result={'scope':'Executed companion commands; no source-path override',
            'commands_sha256':sha256(commands.read_bytes()).hexdigest(),
            'python':identity['python'],'module':identity['module'],'cli_identity':identity,
            'dependencies':identity['dependencies'],'runs':[]}
    for index,(line_number,line,command) in enumerate(jobs,1):
        start=time.monotonic()
        run=subprocess.run(command,cwd=package,env=env,capture_output=True,text=True,encoding='utf-8',timeout=300)
        log=logs[index-1]
        log.write_text(run.stdout+run.stderr,encoding='utf-8')
        result['runs'].append({'line':line_number,'documented_command':line,'executed':command,
            'exit_code':run.returncode,'seconds':time.monotonic()-start,'log':log.name})
        result['status']='running'
        receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(index,len(jobs),run.returncode,line,flush=True)
        if run.returncode:raise RuntimeError('Companion command failed: '+line+'; see '+str(log))
    result['status']='passed'
    result['outputs']={p.relative_to(package).as_posix():sha256(p.read_bytes()).hexdigest()
                       for p in (package/'output').rglob('*') if p.is_file()}
    receipt.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
