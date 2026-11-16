"""Controlled acceptance cases from the audit; executable with the installed wheel."""
from pathlib import Path
from copy import deepcopy
import json
from mic_50_90.gui_worker import execute_job
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
O=parser.parse_args().output.resolve();O.mkdir(parents=True,exist_ok=True)
base=dict(cohort_id='saved-control',n=20,unit='mg/L',panel=dict(levels=[1,2]),additional_counts=[dict(threshold=1,count=8,n=20,unit='mg/L')])
def form(raw):return dict(format='mic-50-90-guided-input',version='1.0.0',payload=dict(mode='distribution',options={},config=raw))
for i in range(3):
 raw=deepcopy(base)
 if i==1:raw['targets']=[]
 if i==2:
  raw['additional_counts'][0].update(relation='>',source='')
  raw['targets']=[dict(threshold=1,unit='mg/L')]
 (O/f'saved-{i}.json').write_text(json.dumps(form(raw)),encoding='utf-8')
 execute_job(form(raw)['payload'],O/f'saved-{i}')
 assert json.loads((O/f'saved-{i}/job-status.json').read_text())['status']=='completed'
for name,change in [('range',dict(count='',count_min=7,count_max=9,decimal_places='')),
 ('exact',dict(count=8,count_min='',count_max=None,decimal_places='')),
 ('percentage',dict(count='',count_min='',count_max=None,percentage='40.000000',decimal_places=6,rounding_rule='half_even'))]:
 raw=deepcopy(base);raw['additional_counts'][0].update(change)
 (O/f'blanks-{name}.json').write_text(json.dumps(form(raw)),encoding='utf-8')
print('Prepared three saved analyses and three count-entry forms')

# Build the two artifacts required by check_acceptance.cjs from shipped inputs.
import shutil
ROOT = Path(__file__).resolve().parents[1]
ampicillin = json.loads((ROOT/'examples/biological_cases/ampicillin-67-summaries.json').read_text(encoding='utf-8'))
execute_job(form(ampicillin)['payload'], O/'ampicillin-job')
if json.loads((O/'ampicillin-job/job-status.json').read_text(encoding='utf-8'))['status'] != 'completed':
    raise RuntimeError('Ampicillin browser reference generation failed')
(O/'output/ampicillin').mkdir(parents=True, exist_ok=True)
shutil.copyfile(O/'ampicillin-job/output/report.html', O/'output/ampicillin/report.html')
(O/'windows').mkdir(exist_ok=True)
shutil.copyfile(ROOT/'examples/received_report/certificate.json', O/'windows/amikacin-certificate.json')
print('Prepared self-contained offline report and reporting certificate')
