import json
from pathlib import Path
from unittest.mock import patch
import pytest

from mic_50_90 import analyse_spec, parse_spec


def population():
    raw=json.loads(Path('examples/population.json').read_text())
    raw['population'].update(profile_likelihood_enabled=True,bayes_enabled=False,profile_grid_size=11)
    return raw


@pytest.mark.parametrize('value',[1.5,True,float('inf')])
def test_sample_size_is_not_silently_truncated(value):
    raw=population();raw['n']=value
    with pytest.raises(ValueError,match='integer'):
        parse_spec(raw)


@pytest.mark.parametrize('value',[4.5,True,float('inf')])
def test_declared_rank_is_not_silently_truncated(value):
    raw=population();raw['summaries']['quantiles'][0]['rank']=value
    with pytest.raises(ValueError,match='integer'):
        parse_spec(raw)


def test_mle_failure_does_not_remove_exact_population_interval():
    with patch('mic_50_90.analysis.fit_population_mle',side_effect=RuntimeError('MLE unavailable')):
        result=analyse_spec(population())
    assert result['threshold_results'][0]['exact_count_confidence']['marginal']['confidence_set_hull']
    assert result['threshold_results'][0]['optional_efficiency_analysis']['available'] is False


def test_failed_mle_status_is_not_presented_as_valid_estimate():
    from mic_50_90.population import PopulationMLE
    failed=PopulationMLE((.5,.5),-10,False,'did not converge',10)
    with patch('mic_50_90.analysis.fit_population_mle',return_value=failed):
        result=analyse_spec(population())
    assert result['population_mle'] is None
    assert result['threshold_results'][0]['optional_efficiency_analysis']['available'] is False


def test_bayesian_failure_does_not_remove_exact_population_interval():
    raw=population();raw['population'].update(profile_likelihood_enabled=False,bayes_enabled=True)
    with patch('mic_50_90.analysis.dirichlet_posterior_tail',side_effect=RuntimeError('weights unavailable')):
        result=analyse_spec(raw)
    assert result['threshold_results'][0]['exact_count_confidence']['marginal']['confidence_set_hull']
    assert result['threshold_results'][0]['bayesian_sensitivity']['available'] is False
