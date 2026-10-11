"""Exercise retained compatibility, calibration entry point and general fallback."""
import json
from itertools import product
from pathlib import Path
import numpy as np
import pytest

from mic_50_90.cli import main
from mic_50_90.conformal import assign_partition
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel, QuantileSummary
from mic_50_90.utility import rank_robust_tail_count_questions


def test_legacy_unit_partition_is_stable_and_exhaustive():
    labels=[f'study-{i}' for i in range(100)]
    forward={s:assign_partition(s) for s in labels}
    reverse={s:assign_partition(s) for s in reversed(labels)}
    assert forward==reverse
    assert set(forward.values())=={'training','calibration','test'}


def test_calibration_cli_preserves_version_12_contract(tmp_path):
    destination=tmp_path/'manifest.json'
    assert main(['calibrate-wasserstein','examples/wasserstein_calibration.json',
                 '--output',str(destination)])==0
    result=json.loads(destination.read_text())
    assert result['manifest_version']=='1.2'
    assert result['calibration_contract']['functional_scope']=='all_panel_tails'


def test_general_question_fallback_matches_independent_integer_counts():
    panel=MICPanel.from_twofold_levels([1,2,4],left_censored=False,right_censored=False)
    problem=EmpiricalProblem(n=4,panel=panel,quantiles=(QuantileSummary(.5,2,1,'2'),),
                             equalities=((np.array([1.,0.,1.]),2),))
    h=[x for x in product(range(5),repeat=3) if sum(x)==4 and x[0]+x[2]==2 and x[0]<2<=x[0]+x[1]]
    assert not problem.has_total_unimodular_canonical_matrix
    target=panel.panel_tail(2)
    baseline=(max(x[2] for x in h)-min(x[2] for x in h))/4
    results=rank_robust_tail_count_questions(problems={'primary':problem},target_objectives=[target])
    for score in results:
        answers={sum(x[score.cut_index+1:]) for x in h}
        residual=max((max(x[2] for x in h if sum(x[score.cut_index+1:])==a)-
                      min(x[2] for x in h if sum(x[score.cut_index+1:])==a))/4 for a in answers)
        assert score.minimax_width_reduction==pytest.approx(baseline-residual)


def test_profile_report_uses_actual_serialized_field_names():
    from mic_50_90 import analyse_spec
    from mic_50_90.population import ProfileLikelihoodResult
    from mic_50_90.report import result_sections
    raw=json.loads(Path('examples/population.json').read_text())
    raw['population'].update(profile_likelihood_enabled=False,bayes_enabled=False)
    result=analyse_spec(raw)
    profile=ProfileLikelihoodResult((.1,.2),(-7.4321,-6.1234),(2.6174,0.),.95,3.8415,
                                    .1,.2,'asymptotic chi-square',2,True).as_dict()
    result['threshold_results'][0]['optional_efficiency_analysis']={
        'enabled':True,'available':True,'population_tail_mle':.2,
        'reporting_variant':'primary','profile_likelihood':profile}
    text=result_sections(result)
    for value in ('-7.4321','3.8415','asymptotic chi-square','10.00% to 20.00%',
                  'boundary or weak identification warning=yes'):
        assert value in text
