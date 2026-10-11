"""The readable report must expose computed assumptions, diagnostics and gains."""
import json
from pathlib import Path
from unittest.mock import patch


from mic_50_90 import analyse_spec
from mic_50_90.report import result_sections, audit_section
from mic_50_90.workflows import audit_histogram


def empirical():
    return json.loads(Path('examples/empirical.json').read_text())


def test_report_exposes_computed_scenarios_witnesses_and_question_costs():
    raw=empirical()
    raw['reference_distribution']=[1/11]*11
    raw['wasserstein_radius']=8
    result=analyse_spec(raw)
    text=result_sections(result)
    for phrase in ('Maximum entropy','KL reference projection','Uncalibrated Wasserstein',
                   'Solver certificates','Compatible histogram','Per-variant bounds',
                   'Acquisition cost','Gain per cost','Feasible answers'):
        assert phrase in text
    entropy=result['assumption_dependent_scenarios']['maximum_entropy']['tail_estimates']['2']
    assert f'{100*entropy:.2f}%' in text


def test_report_shows_prior_ess_mcse_and_optional_optimization_status():
    # A retained output contract fixture keeps this rendering check independent of
    # the expensive Monte Carlo/profile calculation, covered in test_population.
    result=analyse_spec(empirical())
    raw=json.loads(Path('examples/population.json').read_text())
    raw['population'].update(profile_likelihood_enabled=False,bayes_enabled=False)
    population=analyse_spec(raw)
    population['threshold_results'][0]['bayesian_sensitivity']={
        'enabled':True,'reporting_variant':'primary','prior_alpha':{'A':2,'B':8},
        'draws':1000,'effective_sample_size':12.5,
        'prior_tail':{'mean':.2,'equal_tail_interval':[.01,.5]},
        'posterior_tail':{'mean':.3,'median':.28,'equal_tail_interval':[.12,.48],
                          'mcse_of_mean':.004},
        'warnings':['Weights are concentrated <check>']}
    result['population_layer']=population
    text=result_sections(result)
    for phrase in ('Prior alpha','Effective sample size','12.5000','Monte Carlo',
                   '0.40%','12.00%','48.00%','Weights are concentrated &lt;check&gt;'):
        assert phrase in text
    assert 'Weights are concentrated <check>' not in text


def test_optional_entropy_failure_keeps_exact_sample_bounds():
    with patch('mic_50_90.analysis.maximum_entropy',side_effect=RuntimeError('simulated optimizer failure')):
        result=analyse_spec(empirical())
    assert result['reporting_uncertainty_envelope']['envelope']
    failed=result['assumption_dependent_scenarios']['maximum_entropy']
    assert failed['available'] is False
    assert 'simulated optimizer failure' in result_sections(result)


def test_reporting_audit_exposes_bounds_after_observed_answer():
    from mic_50_90.model import MICPanel
    import numpy as np
    raw=dict(contract_version='1.0',mode='empirical',n=10,
             panel=MICPanel.from_twofold_levels([1,2,4,8,16],left_censored=False,right_censored=False).as_dict(),
             summaries={'quantiles':[{'probability':.5,'category':'2'},
                                     {'probability':.9,'category':'16'}]},thresholds=[2,8])
    result=analyse_spec(raw)
    audit=audit_histogram(raw,np.array([1,4,2,1,2]),result)
    assert len(audit['per_threshold'])==2
    assert all(x['one_count_recorded_bounds'][0] <= x['known_recorded_fraction'] <= x['one_count_recorded_bounds'][1]
               for x in audit['per_threshold'])
    assert 'After the observed answer' in audit_section(audit)


def test_report_is_explicit_when_question_search_is_disabled():
    raw=empirical();raw['question_utility']={'enabled':False}
    assert 'Additional-count search was not requested' in result_sections(analyse_spec(raw))
