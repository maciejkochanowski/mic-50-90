"""Final independent review regressions."""
import csv
import json
from pathlib import Path

import pytest

from mic_50_90.cli import main
from mic_50_90 import workflows
from mic_50_90.report import result_sections


def summary():
    folder=Path('examples/csv')
    panel=workflows.load_panels(folder/'panels.csv')[0]['P1']
    return workflows.summary_spec(workflows.read_csv(folder/'summaries-calibrated.csv'),
        panel,[1,2,4],{'enabled':False})


def test_near_one_family_confidence_does_not_discard_sample():
    from fractions import Fraction
    from scipy.stats import binom
    confidence=0.9999999999999999
    raw=summary()
    result=workflows.analyse_layers(raw,True,confidence)
    sample_only=workflows.analyse_layers(raw,False,confidence)
    assert result['reporting_uncertainty_envelope']==sample_only['reporting_uncertainty_envelope']
    assert 'population_unavailable_reason' not in result
    population=result['population_layer']
    rows=population['threshold_results']
    expected_level=1-(1-Fraction(confidence))/len(rows)
    for row in rows:
        marginal=row['exact_count_confidence']['marginal']['confidence_set_hull']
        simultaneous=row['exact_count_confidence']['simultaneous_bonferroni']
        assert Fraction(simultaneous['confidence_level_exact'])==expected_level
        assert simultaneous['confidence_level_is_rounded'] is True
        lo,hi=simultaneous['confidence_set_hull']
        assert 0<=lo<=marginal[0]<=marginal[1]<=hi<=1
        minimum=simultaneous['admissible_count_ranges'][0][0]
        if minimum>0:
            # Independent binomial-tail equation for the lower CP endpoint.
            assert binom.sf(minimum-1,population['sample_size'],lo)==pytest.approx(
                float((1-expected_level)/2),rel=1e-10,abs=0)
    assert 'extremely close' in result_sections(result)


def test_population_failure_does_not_prevent_valid_calibration(monkeypatch):
    original=workflows.analyse_spec
    def failing_population(raw):
        if raw['mode']=='population':
            raise RuntimeError('controlled population solver failure')
        return original(raw)
    monkeypatch.setattr(workflows,'analyse_spec',failing_population)
    calibration=json.loads(Path('examples/csv/calibrations.json').read_bytes())['example']
    result=workflows.analyse_layers(summary(),True,.95,calibration)
    assert result['reporting_uncertainty_envelope']['envelope']
    assert 'controlled population solver failure' in result['population_unavailable_reason']
    assert result['assumption_dependent_scenarios']['wasserstein_ambiguity_set']['guarantee_class']=='conformal_new_cohort'


@pytest.mark.parametrize('filename,keys',[
    ('panels.csv',['panel_id','unit','category','panel_value','lower_closed','upper_closed']),
    ('summaries.csv',['cohort_id','panel_id','variant_id','n','mic50','mic90','rank_convention']),
    ('targets.csv',['cohort_id','threshold','unit']),
])
def test_missing_join_key_does_not_hide_other_missing_fields(tmp_path,capsys,filename,keys):
    for name in ('panels.csv','summaries.csv','targets.csv'):
        rows=workflows.read_csv(Path('examples/csv')/name)
        if name==filename:
            rows[0].update({key:'' for key in keys})
        with (tmp_path/name).open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with pytest.raises(SystemExit) as exc:
        main(['batch',str(tmp_path/'summaries.csv'),'--panels',str(tmp_path/'panels.csv'),
            '--targets',str(tmp_path/'targets.csv'),'--output-dir',str(tmp_path/'out')])
    assert exc.value.code==2
    error=capsys.readouterr().err
    assert all(key in error for key in keys)
    assert filename in error and 'row 2' in error
