"""Run real browser checks against an installed package or the Windows executable.

Requires Node.js and the Playwright package/browser. No scientific result is mocked.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request


def clean_environment():
    env=dict(os.environ)
    for name in ('PYTHONPATH','PYTHONHOME'):env.pop(name,None)
    env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
    return env


def application_command(application):
    return [str(application.resolve())] if application else [sys.executable,'-m','mic_50_90.gui']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--application',type=Path)
    parser.add_argument('--node',default=shutil.which('node') or 'node')
    parser.add_argument('--chrome')
    parser.add_argument('--acceptance',action='store_true',help='Run saved-update, validation, font, export and print cases; requires --examples.')
    parser.add_argument('--examples',type=Path,help='Run the complete Appendix B before/after workflow with this examples directory.')
    args=parser.parse_args()
    if args.acceptance and not args.examples:parser.error('--acceptance requires --examples')
    root=Path(__file__).resolve().parents[1]
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    env=clean_environment()
    command=application_command(args.application)
    if args.acceptance:
        subprocess.run([sys.executable,str(root/'tools/prepare_browser_fixtures.py'),'--output',str(output)],check=True,env=env,cwd=output)
    ready=output/('session-'+str(time.time_ns())+'.json')
    command+=['--no-browser','--ready-file',str(ready),'--output-root',str(output/'jobs')]
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with (output/'application.log').open('w',encoding='utf-8') as log:
        app=subprocess.Popen(command,env=env,cwd=output,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        session=None
        try:
            deadline=time.monotonic()+60
            while not ready.exists():
                if app.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Application did not start; see application.log')
                time.sleep(.1)
            session=json.loads(ready.read_text(encoding='utf-8'))
            if args.examples:
                cmd=[args.node,str(root/('tests/browser/check_acceptance.cjs' if args.acceptance else 'tests/browser/check_worked_example.cjs')),str(ready),str(args.examples.resolve()),str(output)]
            else:
                cmd=[args.node,str(root/'tests/browser/check_reopened_options.cjs'),str(ready),str(output)]
            if args.chrome:cmd.append(args.chrome)
            subprocess.run(cmd,check=True,env=env,cwd=output,timeout=600 if args.examples else 180)
        finally:
            if session and app.poll() is None:
                origin='http://127.0.0.1:'+str(session['port'])
                request=urllib.request.Request(origin+'/api/shutdown',data=b'{}',headers={
                    'Authorization':'Bearer '+session['token'],'Origin':origin,'Content-Type':'application/json'})
                try:
                    with urllib.request.urlopen(request,timeout=10):pass
                    app.wait(timeout=15)
                finally:
                    if app.poll() is None:app.terminate();app.wait(timeout=15)
            elif app.poll() is None:app.terminate();app.wait(timeout=15)
            ready.unlink(missing_ok=True)


if __name__=='__main__':main()
