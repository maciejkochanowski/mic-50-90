import csv
import json

import pytest

from mic_50_90.cli import main


def fixture(tmp_path, targets, *, missing=False, n=10, iid=False, alternate=False, provenance=None):
    def write(name, rows):
        with (tmp_path/name).open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    write('panels.csv', [dict(panel_id='P', unit='mg/L', category=str(x), lower=x, upper=x,
          lower_closed='true', upper_closed='true', panel_value=x) for x in (1, 2, 4, 8)])
    row = dict(cohort_id='C', panel_id='' if missing else 'P', variant_id='primary', n=n,
               mic50='2', mic90='4', rank_convention='' if missing else 'ceiling',
               rank50='', rank90='', iid=str(iid).lower())
    row.update(provenance or {})
    rows = [row]
    if alternate:
        rows.append({**row, 'variant_id':'adjacent', 'rank_convention':'explicit', 'rank50':4, 'rank90':8})
    write('summaries.csv', rows)
    write('targets.csv', [dict(cohort_id='C', threshold=4, unit='mg/L', **t) for t in targets])
    assert main(['batch', str(tmp_path/'summaries.csv'), '--panels', str(tmp_path/'panels.csv'),
                 '--targets', str(tmp_path/'targets.csv'), '--output-dir', str(tmp_path/'out')]) == 0
    return json.loads((tmp_path/'out/results.json').read_text())[0], (tmp_path/'out/report.html').read_text(encoding='utf-8')


@pytest.mark.parametrize('operator,limit,expected', [
    ('<=','0.1','supported'), ('<','0.1','undetermined'),
    ('>','0.1','contradicted'), ('>=','0.1','undetermined'),
    ('>=','0','supported'), ('<','0','contradicted'),
])
def test_sample_decisions_respect_strict_boundary(tmp_path, operator, limit, expected):
    # At MIC90 for n=10 the feasible recorded tail counts are exactly 0 or 1.
    r, report = fixture(tmp_path, [dict(decision_operator=operator, decision_fraction=limit)])
    assert r['status'] == 'ok'
    d = r['result'].get('decision_results')
    assert d is not None, 'CSV criterion must produce an interpreted result'
    assert d[0]['sample']['status'] == expected
    assert d[0]['population']['status'] == 'unavailable'
    assert d[0]['conformal']['status'] == 'unavailable'
    assert 'Your questions' in report
    assert '<svg' in report and 'role="img"' in report
    assert 'True' not in report and 'None' not in report and 'False' not in report
    with (tmp_path/'out/results.csv').open(newline='') as f:
        assert next(csv.DictReader(f))['sample_decision'] == expected


def test_all_reporting_variants_control_decision(tmp_path):
    r, _ = fixture(tmp_path, [dict(decision_operator='<=', decision_fraction='.1')], alternate=True)
    # Adjacent rank 8 admits 2/10 above the reported MIC90.
    assert r['result'].get('decision_results', [{}])[0].get('sample', {}).get('status') == 'undetermined'


def test_missing_metadata_are_collected_together(tmp_path):
    r, report = fixture(tmp_path, [{}], missing=True)
    assert r['status'] == 'refused'
    assert 'panel' in r['reason'].lower() and 'rank_convention' in r['reason']
    assert len(r.get('input_issues', [])) >= 2
    assert 'rank_convention' in report


@pytest.mark.parametrize('target', [
    dict(decision_operator='<'), dict(decision_fraction='.05'),
    dict(decision_operator='=', decision_fraction='.05'),
    dict(decision_operator='<', decision_fraction='5'),
    dict(decision_operator='<', decision_fraction='nan'),
])
def test_invalid_criteria_are_refused_instead_of_ignored(tmp_path, target):
    r, _ = fixture(tmp_path, [target])
    assert r['status'] == 'refused'
    assert 'decision' in r['reason']


def test_single_observation_gets_actionable_minimum_message(tmp_path):
    r, _ = fixture(tmp_path, [{}], n=1)
    assert r['status'] == 'refused'
    assert 'two observations' in r['reason']


def test_population_decision_is_not_the_sample_decision(tmp_path):
    r, report = fixture(tmp_path, [dict(decision_operator='<=', decision_fraction='.1')], iid=True)
    d = r['result'].get('decision_results')
    assert d is not None
    assert d[0]['sample']['status'] == 'supported'
    assert d[0]['population']['status'] == 'undetermined'
    assert d[0]['population']['confidence_level'] == .95
    assert 'confidence set' in report


def test_exact_sample_fraction_does_not_round_into_criterion(tmp_path):
    # 1/11 exceeds this decimal, although both become the same binary float.
    from mic_50_90.decisions import decision_results, parse_criterion
    criterion=parse_criterion({'decision_operator':'<=',
        'decision_fraction':'0.090909090909090905'})
    result={'sample_size':11, 'reporting_uncertainty_envelope':{'envelope':[
        {'threshold':4, 'panel_recorded_estimand':{
            'lower':{'count':1}, 'upper':{'count':1}}}]}}
    assert decision_results(result,[criterion])[0]['sample']['status']=='contradicted'


def test_calibrated_decision_keeps_manifest_level_and_event(tmp_path):
    from pathlib import Path
    inputs=Path('examples/csv')
    targets=tmp_path/'targets.csv'
    targets.write_text('cohort_id,threshold,unit,decision_operator,decision_fraction\nexample,2,mg/L,>=,0\n')
    assert main(['batch',str(inputs/'summaries-calibrated.csv'),'--panels',str(inputs/'panels.csv'),
        '--targets',str(targets),'--calibrations',str(inputs/'calibrations.json'),
        '--output-dir',str(tmp_path/'out')])==0
    result=json.loads((tmp_path/'out/results.json').read_bytes())[0]['result']
    layer=result['decision_results'][0]['conformal']
    manifest=result['assumption_dependent_scenarios']['wasserstein_ambiguity_set']['calibration_manifest']
    assert layer['status']=='supported'
    assert layer['confidence_level']==manifest['confidence_level']
    assert layer['guarantee']==manifest['coverage_statement']
    assert layer['scope']==manifest['guarantee_scope']


def test_panel_preflight_lists_all_missing_required_fields(tmp_path):
    fixture(tmp_path, [{}])
    rows = list(csv.DictReader((tmp_path/'panels.csv').open()))
    for key in ('unit', 'lower_closed', 'upper_closed'):
        rows[0][key] = ''
    with (tmp_path/'panels.csv').open('w', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    main(['batch',str(tmp_path/'summaries.csv'),'--panels',str(tmp_path/'panels.csv'),
          '--targets',str(tmp_path/'targets.csv'),'--output-dir',str(tmp_path/'out')])
    r=json.loads((tmp_path/'out/results.json').read_text())[0]
    assert r['status']=='refused'
    assert all(key in r['reason'] for key in ('unit','lower_closed','upper_closed'))


def test_declared_provenance_survives_report_and_configuration(tmp_path):
    r, report = fixture(tmp_path, [{}], provenance={'source_doi':'10.example/test',
        'source_location':'Table 1 <source>', 'metadata_basis':'conditional',
        'rank_basis':'Analyst-declared ranks; not established by the paper'})
    assert r.get('provenance',{}).get('metadata_basis') == 'conditional'
    assert 'Analyst-declared ranks' in report and 'Table 1 &lt;source&gt;' in report
    assert report.index('Source and sample') < report.index('Your questions')
    config=json.loads((tmp_path/'out/configuration.json').read_text())
    assert config['cohorts'][0]['provenance']['source_doi']=='10.example/test'
