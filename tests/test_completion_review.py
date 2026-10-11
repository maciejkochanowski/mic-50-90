"""Regression cases found by the independent completion review."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

from scipy.optimize import OptimizeResult

from mic_50_90 import analyse_spec, parse_spec
from mic_50_90.model import MICPanel
from mic_50_90.report import result_sections


def test_html_preserves_disconnected_exact_confidence_set():
    def summary(category):
        return {'quantiles':[{'probability':.5,'category':category},
                             {'probability':.9,'category':category}],
                'minimum':category,'maximum':category}
    raw={'contract_version':'1.0','mode':'population','n':100,
         'panel':MICPanel.from_twofold_levels([1,2,4],left_censored=False,right_censored=False).as_dict(),
         'summaries':summary('1'),'thresholds':[2],
         'reporting_envelope':{'variants':[{'id':'all_high','summaries':summary('4')}]},
         'population':{'profile_likelihood_enabled':False,'bayes_enabled':False}}
    result=analyse_spec(raw)
    components=result['threshold_results'][0]['exact_count_confidence']['marginal']['confidence_set_components']
    assert len(components)==2
    text=result_sections(result)
    assert '0.00% to 3.62%' in text and '96.38% to 100.00%' in text
    assert ' ∪ ' in text


def test_returned_profile_failure_keeps_exact_but_refuses_profile():
    raw=json.loads(Path('examples/population.json').read_text())
    raw['population'].update(profile_grid_size=11,bayes_enabled=False)
    def failed(objective,x0,**kwargs):
        return OptimizeResult(x=x0,fun=objective(x0),success=False,message='simulated profile line search failure')
    from mic_50_90.population import fit_population_mle
    spec=parse_spec(raw)
    mle=fit_population_mle(k=len(spec.panel.bins),n=spec.n,quantiles=spec.quantiles,
                           minimum_index=spec.minimum_index,maximum_index=spec.maximum_index)
    with patch('mic_50_90.analysis.fit_population_mle',return_value=mle), \
         patch('mic_50_90.population.minimize',side_effect=failed):
        result=analyse_spec(raw)
    row=result['threshold_results'][0]
    assert row['exact_count_confidence']['marginal']['confidence_set_hull']
    assert row['optional_efficiency_analysis']['available'] is False
    assert 'simulated profile line search failure' in result_sections(result)


def test_optional_transport_failure_preserves_exact_results():
    raw=json.loads(Path('examples/empirical.json').read_text())
    raw.update(reference_distribution=[1/11]*11,wasserstein_radius=8)
    with patch('mic_50_90.analysis.wasserstein_bounds',side_effect=RuntimeError('simulated transport failure')):
        result=analyse_spec(raw)
    assert result['reporting_uncertainty_envelope']['envelope']
    scenario=result['assumption_dependent_scenarios']['wasserstein_ambiguity_set']
    assert all(row['envelope'] is None for row in scenario['threshold_results'])
    assert 'simulated transport failure' in result_sections(result)


def test_optional_reference_projection_failure_preserves_exact_results():
    raw=json.loads(Path('examples/empirical.json').read_text())
    raw.update(reference_distribution=[1/11]*11,wasserstein_radius=8)
    spec=replace(parse_spec(raw),wasserstein_calibration_manifest={
        'calibration_contract':{'reference_rule':'projected'},'coverage_statement':'test contract'})
    with patch('mic_50_90.analysis.parse_spec',return_value=spec), \
         patch('mic_50_90.analysis.project_onto_sharp_set',side_effect=RuntimeError('simulated projection failure')):
        result=analyse_spec(raw)
    assert result['reporting_uncertainty_envelope']['envelope']
    scenario=result['assumption_dependent_scenarios']['wasserstein_ambiguity_set']
    assert all(row['envelope'] is None for row in scenario['threshold_results'])
    assert any('simulated projection failure' in x for x in result['warnings'])
