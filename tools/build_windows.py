"""Build the Windows application from this source tree into a new directory.

Install PyInstaller, numpy and scipy in a dedicated build environment first.
The build receipt proves source identity, not runtime or scientific correctness.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys


def digest(path):
    h=sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def source_identity(root):
    paths=[p for p in (root/'src').rglob('*')
           if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    paths.extend(root/name for name in ('tools/build_windows.py','tools/desktop_launcher.py','pyproject.toml','LICENSE','NOTICE.md'))
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(paths)}


def verify_source_identity(root, before):
    after=source_identity(root)
    if before!=after:
        changed=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k))
        raise RuntimeError('Build source changed during execution: '+', '.join(changed))
    return after


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if sys.platform!='win32':parser.error('Build the Windows executable on Windows.')
    root=Path(__file__).resolve().parents[1]
    output=args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Use an empty output directory; existing builds are preserved.')
    output.mkdir(parents=True,exist_ok=True)
    sources=source_identity(root)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','MIC-50-90','--paths',str(root/'src'),
        '--add-data',str(root/'src/mic_50_90/gui_assets')+';mic_50_90/gui_assets',
        '--collect-all','scipy','--copy-metadata','numpy','--copy-metadata','scipy',
        '--distpath',str(output/'application'),'--workpath',str(output/'work'),
        '--specpath',str(output)]
    for module in ('pytest','hypothesis','pandas','duckdb','matplotlib','IPython','notebook','tkinter'):
        command.extend(['--exclude-module',module])
    command.append(str(Path(__file__).with_name('desktop_launcher.py')))
    with (output/'build.log').open('w',encoding='utf-8') as log:
        subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
    app=output/'application/MIC-50-90'
    for name in ('LICENSE','NOTICE.md'):
        shutil.copyfile(root/name,app/name)
    after=verify_source_identity(root,sources)
    assets=root/'src/mic_50_90/gui_assets'
    for source in assets.rglob('*'):
        if not source.is_file() or '__pycache__' in source.parts:continue
        bundled=app/'_internal/mic_50_90/gui_assets'/source.relative_to(assets)
        if not bundled.is_file() or digest(source)!=digest(bundled):
            raise RuntimeError('Missing or changed application resource: '+str(source.relative_to(assets)))
    files={p.relative_to(app).as_posix():digest(p) for p in app.rglob('*') if p.is_file()}
    receipt={'status':'built_not_yet_runtime_verified','software_version':'1.0.0',
        'created_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,
        'dependencies':{n:importlib.metadata.version(n) for n in ('PyInstaller','numpy','scipy')},
        'command':command,'source_sha256':sources,'source_sha256_after':after,
        'source_unchanged_during_build':True,'application_sha256':files}
    (output/'BUILD_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'application':str(app),'files':len(files),'status':receipt['status']}))


if __name__=='__main__':main()
