"""Input contracts, planner equivalence, MLE/profile precision and MILP certificates."""
import json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
import mic_50_90
from mic_50_90.gui_forms import validate_payload
from mic_50_90.model import MICPanel,parse_spec
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.population import fit_population_mle,profile_likelihood
from mic_50_90.decision_planning import plan_decisions
from mic_50_90.acquisition import plan_acquisition
from mic_50_90.gui import DesktopServer
I=Path(__file__).resolve().parent/'fixtures/contracts'
ASSETS=Path(mic_50_90.__file__).parent/'gui_assets'
def spec(name):return parse_spec(json.loads((I/(name+'.json')).read_text()))
def fit(s):return fit_population_mle(k=len(s.panel.bins),n=s.n,quantiles=s.quantiles,minimum_index=s.minimum_index,maximum_index=s.maximum_index)

def test_population_import_without_targets_is_refused():
 raw=json.loads((I/'case_audit_unit.json').read_text())
 payload={'mode':'distribution','config':raw,'options':{},'histogram':[],'targets':[],'previous':None}
 assert not validate_payload(payload)['valid'], 'Unsupported analyse contract must not become a successful distribution job'

@pytest.mark.parametrize('planner',[plan_decisions,plan_acquisition])
def test_recorded_tail_count_matches_threshold_count(planner):
 raw={'n':20,'panel':{'levels':[1,2,4,8],'left_censored':False,'right_censored':False},'summaries':{'quantiles':[{'probability':.5,'category':'2','convention':'ceiling'},{'probability':.9,'category':'8','convention':'ceiling'}]},'thresholds':[4]}
 criteria=[{'threshold':4,'unit':'mg/L','decision_operator':'<','decision_fraction':'.25'}]
 row={'threshold':2,'unit':'mg/L','n':20,'count':8}
 a=planner(raw,criteria,additional_counts=[row]);b=planner(raw,criteria,additional_counts=[{**row,'source_scale':'recorded'}])
 for key in ['status','worst_case_cost','next_question','next_questions']:
  assert a.get(key)==b.get(key)

def test_profile_matches_independent_binomial_roots():
 s=spec('case_audit_unit');m=fit(s)
 r=profile_likelihood(mle=m,tail=np.array([0,1]),n=s.n,quantiles=s.quantiles,minimum_index=s.minimum_index,maximum_index=s.maximum_index,grid_size=41)
 np.testing.assert_allclose([r.confidence_set_lower,r.confidence_set_upper],[.004634262641920887,.24965931746947617],rtol=0,atol=1e-8)

def test_ampicillin_mle_tail_is_precise():
 m=fit(spec('case_amp'))
 assert abs(sum(m.probabilities[2:])-.2821213142684807)<1e-6

@pytest.mark.parametrize('scale',[1.,1e-8,1e-12])
def test_rescaled_equality_does_not_change_bounds(scale):
 panel=MICPanel.from_twofold_levels([1,2],left_censored=False,right_censored=False)
 low,high=EmpiricalProblem(n=3,panel=panel,quantiles=[],equalities=[(np.array([scale,0.]),0)]).bounds(np.array([1,0]))
 assert (low.count,high.count)==(0,0)

@pytest.mark.parametrize('token',['20.0','2e1'])
def test_integral_json_tokens_are_exactly_normalized(token):
 js='const m=require(process.argv[1]);process.stdout.write(JSON.stringify(m.integer(process.argv[2])));'
 p=subprocess.run(['node','-e',js,str(ASSETS/'model.js'),token],text=True,capture_output=True)
 assert p.returncode==0,p.stderr
 assert json.loads(p.stdout)=='20'

@pytest.mark.parametrize('unit',['\u00b5g/mL','\u03bcg/mL'])
def test_micro_sign_units_open_as_form_unit(unit):
 js='const m=require(process.argv[1]);const r=m.importInput(JSON.parse(process.argv[2]));process.stdout.write(JSON.stringify([r.config.unit,r.config.additional_counts[0].unit]));'
 raw={'n':67,'unit':unit,'panel':{'levels':[0.12,0.25]},'additional_counts':[{'threshold':0.12,'count':3,'n':67,'unit':unit}]}
 p=subprocess.run(['node','-e',js,str(ASSETS/'model.js'),json.dumps(raw)],text=True,capture_output=True)
 assert p.returncode==0,p.stderr
 assert json.loads(p.stdout)==['ug/mL','ug/mL']

def test_certificates_of_this_release_are_accepted_by_every_checker():
    from mic_50_90.gui_documents import validate_document
    root=Path(__file__).resolve().parents[1]
    doc=json.loads((root/'examples/received_report/certificate.json').read_text(encoding='utf-8'))
    for version in ('1.0.0',mic_50_90.__version__):
        doc['version']=version
        assert validate_document({'mode':'verify-report','certificate':doc})['valid']
        js='const m=require(process.argv[1]);process.stdout.write(m.importText(process.argv[2]).mode);'
        p=subprocess.run(['node','-e',js,str(ASSETS/'model.js'),json.dumps(doc)],text=True,capture_output=True)
        assert p.returncode==0 and p.stdout=='verify-report',p.stderr

def test_header_only_distribution_is_refused(tmp_path):
 inp=tmp_path/'empty.csv';inp.write_text((I/'a02/summaries.csv').read_text().splitlines()[0]+'\n')
 p=subprocess.run([sys.executable,'-m','mic_50_90','distribution',str(inp),'--panels',str(I/'a02/panels.csv'),'--output-dir',str(tmp_path/'out'),'--fail-on-refusal'],text=True,capture_output=True)
 assert p.returncode!=0

def test_generated_checksums_are_exported(tmp_path):
 out=tmp_path/'output';out.mkdir();(out/'checksums.sha256').write_text('audit fixture\n')
 server=SimpleNamespace(jobs={'fixture':{'directory':tmp_path}})
 assert 'checksums.sha256' in DesktopServer.allowed_files(server,'fixture')
