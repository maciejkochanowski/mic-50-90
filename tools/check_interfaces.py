"""Compare eleven current worked examples in a built Windows application and installed CLI.

Scientific outputs are compared exactly after removing only enumerated timing fields.
Report text differences remain explicit; they are not automatically called equivalent.
"""
import hashlib, html, json, os, re, subprocess, sys, time, urllib.request
from html.parser import HTMLParser
from pathlib import Path

# Inputs and outputs are explicit; the audit can run from an extracted delivery.
RECORDS=OUT=PACKAGE=EXE=READY=None

def cli_identity(env, cwd):
    """Measure imports in the CLI child, not the potentially different parent."""
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


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.ignore=0; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.ignore+=1
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.ignore-=1
        if tag in ('p','tr','h2','h3','h4','li','summary'): self.parts.append('\n')
    def handle_data(self,data):
        if not self.ignore:self.parts.append(data)
    def text(self): return re.sub(r'[ \t\r\f\v]+',' ',''.join(self.parts))

def text(path):
    parser=VisibleText(); parser.feed(path.read_text(encoding='utf-8')); return parser.text()

timing={'elapsed_seconds','baseline_seconds','refinement_seconds','seconds','runtime_seconds',
        'solve_seconds','elapsed','total_seconds','wall_seconds','search_seconds'}
def clean(v):
    if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in timing}
    if isinstance(v,list):return [clean(x) for x in v]
    return v

def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        result=[]
        for k in a.keys() | b.keys():
            if k not in a or k not in b:result.append([path+'/'+k,a.get(k),b.get(k)])
            else:result+=differences(a[k],b[k],path+'/'+k)
        return result
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):return [[path+'/length',len(a),len(b)]]
        return sum((differences(x,y,path+'/'+str(i)) for i,(x,y) in enumerate(zip(a,b))),[])
    return [] if a==b else [[path,a,b]]

def cli_args(payload,work,destination):
    mode=payload['mode']; opts=payload.get('options',{}); args=[mode]
    if mode=='distribution':
        if payload.get('input_format')=='tables':
            args += [str(work/'input.csv'),'--panels',str(work/'panels.csv')]
            if (work/'targets.csv').exists():args += ['--targets',str(work/'targets.csv')]
            if (work/'additional_counts.csv').exists():args += ['--additional-counts',str(work/'additional_counts.csv')]
        else:args += [str(work/'input.json')]
        keys=('population_method','population_time_limit','population_tolerance_pp','precision_pp',
              'population_precision_pp','population_count_plan','population_minimum_bins','population_planning_time_limit')
    else:
        source='input.csv' if payload.get('input_format')=='tables' else ('counts.csv' if mode=='reporting-audit' else 'summaries.csv')
        args += [str(work/source),'--panels',str(work/'panels.csv'),'--targets',str(work/'targets.csv')]
        for name,flag in [('calibrations.json','--calibrations'),('additional-counts.csv','--additional-counts'),('additional_counts.csv','--additional-counts')]:
            if (work/name).exists():args += [flag,str(work/name)]
        keys=('question_time_limit','report_page_size','exclude_direct_targets','decision_plan','acquisition_plan',
              'reporting_plan','round_cost','decision_plan_time_limit','decision_plan_max_states')
    for key in keys:
        value=opts.get(key)
        if value is None or value is False:continue
        args.append('--'+key.replace('_','-'))
        if value is not True:args.append(str(value))
    return args+['--output-dir',str(destination)]

def main():
    import argparse
    global OUT, PACKAGE, EXE, READY
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application',type=Path,required=True)
    parser.add_argument('--examples',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    OUT=args.output.resolve(); OUT.mkdir(parents=True,exist_ok=True)
    PACKAGE=args.examples.resolve(); EXE=args.application.resolve()
    READY=OUT/('runtime-ready-'+str(time.time_ns())+'.json')
    env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}; env['PYTHONDONTWRITEBYTECODE']='1'
    identity=cli_identity(env,OUT)
    frozenenv=os.environ.copy(); frozenenv.pop('PYTHONPATH',None)
    proc=subprocess.Popen([str(EXE),'--no-browser','--output-root',str(OUT/'windows-jobs'),'--ready-file',str(READY)],
        cwd=OUT,env=frozenenv,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+45
        while not READY.exists():
            if proc.poll() is not None:raise RuntimeError('Windows runtime exited before readiness')
            if time.monotonic()>deadline:raise TimeoutError('Windows startup')
            time.sleep(.1)
        while True:
            try:
                ready=json.loads(READY.read_text(encoding='utf-8'))
                origin='http://127.0.0.1:'+str(ready['port'])
                assert ready['token']
                break
            except (OSError,json.JSONDecodeError,KeyError):
                if time.monotonic()>deadline:raise TimeoutError('Windows readiness record')
                time.sleep(.05)
        def request(path,data=None):
            body=None if data is None else json.dumps(data).encode('utf-8')
            req=urllib.request.Request(origin+path,data=body,headers={'Authorization':'Bearer '+ready['token'],
                'Content-Type':'application/json','Origin':origin})
            with urllib.request.urlopen(req,timeout=90) as f:return json.load(f)
        cases=['ampicillin-67-summaries-category','ampicillin-67-with-count-category',
               'ampicillin-67-with-count-population-category','chloramphenicol-67-censored',
               'penicillin-7133-two-counts','penicillin-2018-precision-before','penicillin-2018-precision-after',
               'guide-csv','amikacin-laboratory','acquisition-teaching','fsis-calibration']
        records=[]
        for name in cases:
            payload=json.loads((PACKAGE/'windows'/f'{name}.json').read_text(encoding='utf-8'))['payload']
            result=request('/api/jobs',payload); deadline=time.monotonic()+240
            while result['status']=='running':
                if time.monotonic()>deadline:raise TimeoutError(name)
                time.sleep(.15); result=request('/api/jobs/'+result['job_id'])
            windows=Path(result['output_directory']); cli=OUT/'cli'/name; work=windows.parent/'input'
            args=cli_args(payload,work,cli)
            command=[sys.executable,'-m','mic_50_90',*args]
            run=subprocess.run(command,cwd=OUT,env=env,capture_output=True,text=True,encoding='utf-8',timeout=240)
            row={'case':name,'mode':payload['mode'],'windows_status':result['status'],'cli_exit':run.returncode,
                 'windows_output':str(windows),'cli_output':str(cli),'cli_args':args}
            if (windows/'results.json').exists() and (cli/'results.json').exists():
                a=json.loads((windows/'results.json').read_text(encoding='utf-8'));b=json.loads((cli/'results.json').read_text(encoding='utf-8'))
                diffs=differences(clean(a),clean(b));row['result_differences']=diffs[:50];row['result_difference_count']=len(diffs)
                row['report_bytes_equal']=(windows/'report.html').read_bytes()==(cli/'report.html').read_bytes()
                wtext=text(windows/'report.html');ctext=text(cli/'report.html')
                (OUT/(name+'-windows-report.txt')).write_text(wtext,encoding='utf-8')
                (OUT/(name+'-cli-report.txt')).write_text(ctext,encoding='utf-8')
                row['report_text_equal']=wtext==ctext
                row['cohorts']=len(a if isinstance(a,list) else a.get('cohorts',[]))
                row['both_reports_exist']=True
            else:row['error']=run.stderr or result['message']
            records.append(row); save('INTERFACE_COMPARISON.json',{'timing_fields_excluded':sorted(timing),'cases':records})
            print(name,result['status'],run.returncode,'differences',row.get('result_difference_count'),flush=True)
        assert len(records)==11 and all(r.get('result_difference_count')==0 and r['cli_exit']==0 and r['windows_status']=='completed' for r in records), records
        save('RUNTIME_SCOPE.json',{'installed_cli_module':identity['module'],'cli_identity':identity,'source_checkout_used_for_cli_import':not identity['installed_distribution_import'],'portable_exe':str(EXE),'sha256':hashlib.sha256(EXE.read_bytes()).hexdigest(),
            'interface':'final frozen Windows runtime via localhost jobs API; command-line module on same normalized scientific inputs',
            'browser_validation':'This check exercises the packaged jobs API; separate real-browser receipts are required for form interactions and exports.'})
    finally:
        if READY.exists():
            try:request('/api/shutdown',{})
            except Exception:pass
        try:proc.wait(timeout=12)
        except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=8)
        READY.unlink(missing_ok=True)

if __name__=='__main__': main()
