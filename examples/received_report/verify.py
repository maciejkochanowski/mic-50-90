"""Companion command-line example using the public recipient-verification API."""
import argparse,json
from pathlib import Path
from mic_50_90 import verify_reporting
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('certificate',type=Path)
args=parser.parse_args()
document=json.loads(args.certificate.read_text(encoding='utf-8'))
if document.get('version')!='1.0.0':raise ValueError('Expected a version 1.0.0 certificate')
records=document['certificates']
if not records:raise ValueError('Certificate list is empty')
success=True
for row in records:
    result=verify_reporting(row['specification'],row['criteria'],row['disclosures'])
    print(row.get('cohort_id','Collection'),':', 'Sufficient' if result['sufficient'] else 'More information required')
    for item in result['bounds']:
        print('  MIC >',item['threshold'],'mg/L:',item['count_min'],'to',item['count_max'],
              'of',item['n'],'isolates;',item['status'])
    success=success and result['sufficient']
raise SystemExit(0 if success else 2)
