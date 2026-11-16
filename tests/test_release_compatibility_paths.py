"""Real saved-update and browser-fixture paths used by release validation."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def saved(tmp_path, version='1.0.0'):
    from mic_50_90.distribution_workflow import analyse_distribution
    raw={'cohort_id':'same-sample','n':20,'unit':'mg/L','panel':{'levels':[1,2]},'iid':False,
         'additional_counts':[{'threshold':1,'count':8,'n':20,'unit':'mg/L'}]}
    config={'inputs':[raw], 'population_method':'bonferroni'}
    result={'software':'MIC-50-90','software_version':version,'result_schema':'mic-50-90.distribution/1',
            'cohorts':[analyse_distribution(raw)]}
    for name,data in [('configuration',config),('results',result)]:
        (tmp_path/(name+'.json')).write_text(json.dumps(data),encoding='utf-8')
    return raw,config,result


def test_cli_update_retains_exact_parent_file_identity(tmp_path):
    from mic_50_90.distribution_workflow import _load_previous_output,analyse_distribution
    raw,_,_=saved(tmp_path)
    before={n:sha256((tmp_path/n).read_bytes()).hexdigest() for n in ['configuration.json','results.json']}
    old=_load_previous_output(tmp_path)['same-sample']
    assert old['previous_evidence']['file_sha256']==before
    updated=deepcopy(raw)
    updated['additional_counts'].append({'threshold':2,'count':3,'n':20,'unit':'mg/L'})
    result=analyse_distribution(updated,previous_analysis=old)
    assert result['previous_evidence']==old['previous_evidence']
    assert result['previous_evidence']['software_version']=='1.0.0'
    assert before=={n:sha256((tmp_path/n).read_bytes()).hexdigest() for n in before}


def test_gui_accepts_known_current_schema_with_new_producer(monkeypatch,tmp_path):
    from mic_50_90 import _version
    from mic_50_90.gui_forms import validate_payload
    raw,configuration,results=saved(tmp_path,version='1.0.1')
    monkeypatch.setattr(_version,'__version__','1.0.1')
    payload={'mode':'distribution','config':raw,'options':{},'previous':{'configuration':configuration,'results':results}}
    check=validate_payload(payload)
    assert check['valid'],check['issues']


@pytest.mark.parametrize('field,value',[('n',21),('unit','ug/mL'),('iid',True),('panel',{'levels':[1,2,4]}),('confidence_level',.9)])
def test_schema_compatibility_does_not_relax_sample_identity(tmp_path,field,value):
    from mic_50_90.gui_forms import validate_payload
    raw,configuration,results=saved(tmp_path)
    changed=deepcopy(raw);changed[field]=value
    check=validate_payload({'mode':'distribution','config':changed,'options':{},
                           'previous':{'configuration':configuration,'results':results}})
    assert not check['valid']


def test_browser_acceptance_assets_are_generated_from_shipped_examples(tmp_path):
    process=subprocess.run([sys.executable,str(ROOT/'tools/prepare_browser_fixtures.py'),'--output',str(tmp_path)],capture_output=True,text=True)
    assert process.returncode==0,process.stdout+process.stderr
    assert (tmp_path/'output/ampicillin/report.html').is_file()
    certificate=tmp_path/'windows/amikacin-certificate.json'
    assert certificate.is_file()
    assert json.loads(certificate.read_text())==json.loads((ROOT/'examples/received_report/certificate.json').read_text())
