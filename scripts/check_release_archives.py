"""Install wheel and sdist in separate environments and run real CLI examples."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def check(archive, directory):
    environment = directory/archive.suffix.replace('.', '')
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    env = dict(os.environ)
    for name in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'):
        env.pop(name,None)
    def run(args):
        return subprocess.run([str(python),*args],cwd=directory,env=env,
            check=True,capture_output=True,text=True,encoding='utf8',errors='replace').stdout
    run(['-m','pip','install',str(archive)])
    location=run(['-I','-c','import mic_50_90;print(mic_50_90.__file__)']).strip()
    assert Path(location).is_relative_to(environment), location
    sample=dict(n=20,unit='mg/L',panel={'levels':[1,2,4]},
        additional_counts=[dict(threshold=1,count=8,n=20,unit='mg/L'),
                           dict(threshold=2,count=2,n=20,unit='mg/L')],
        targets=[dict(start_category='2',end_category='2',unit='mg/L',
                      decision_operator='<=',decision_fraction='.3')])
    source=directory/'sample.json'
    source.write_text(json.dumps(sample),encoding='utf8')
    output=directory/('result-'+archive.suffix[1:])
    run(['-I','-m','mic_50_90.cli','distribution',str(source),'--output-dir',str(output)])
    result=json.loads((output/'results.json').read_text(encoding='utf8'))
    row=result['cohorts'][0]['decisions'][0]
    assert row['sample']['count_components']==[[6,6]]
    assert row['sample']['status']=='supported'
    assert 'recorded MIC category 2 mg/L' in (output/'report.html').read_text(encoding='utf8')
    return dict(archive=archive.name,sha256=sha256(archive.read_bytes()).hexdigest(),
                installed_path=location,passed=True,expected_count=6)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('directory',type=Path)
    parser.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args()
    wheels=list(args.directory.glob('*.whl'))
    sources=list(args.directory.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error('Expected exactly one wheel and exactly one source archive')
    archives=wheels+sources
    args.receipt=args.receipt.resolve()
    if args.receipt.exists():
        parser.error('Use a new receipt path; existing archives and evidence must not be overwritten')
    temporary=Path(tempfile.mkdtemp(prefix='MIC archive verification '))
    rows=[check(path.resolve(),temporary) for path in archives]
    receipt=dict(python=sys.version,platform=sys.platform,passed=True,archives=rows)
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    with args.receipt.open('x',encoding='utf8') as stream:
        stream.write(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    main()
