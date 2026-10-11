"""Independent training and scale contracts for simultaneous calibration."""
from copy import deepcopy
import json

import numpy as np
import pytest

from mic_50_90 import calibration_preparation as preparation
from mic_50_90.conformal import validate_calibration_manifest
from mic_50_90.model import parse_spec
from mic_50_90.workflows import load_panels, summary_spec
from test_calibration_preparation import fixture_inputs, save_inputs


def training_inputs(tmp_path):
    data=fixture_inputs(tmp_path)
    patterns={'R1':[8,1,1],'R2':[6,2,2]}
    for unit,counts in patterns.items():
        for pid in ('P1','P2'):
            cid=f'{unit}-{pid}'
            data['roster'].append(dict(unit_id=unit,cohort_id=cid,panel_id=pid,role='training'))
            labels=[r['category'] for r in data['panels'] if r['panel_id']==pid]
            data['counts'].extend(dict(cohort_id=cid,panel_id=pid,category=label,count=count,
                rank_convention='ceiling',original_n=10) for label,count in zip(labels,counts))
    return data


def prepare(data,scaling='training'):
    return preparation.prepare_calibration(**save_inputs(data),level=.75,
        reference_method='training',transport_scaling=scaling)


def target_spec(tmp_path,result,pid='P1'):
    panel=load_panels(tmp_path/'panels.csv')[0][pid]
    raw=summary_spec([dict(variant_id='primary',n=10,mic50=panel.labels[0],
        mic90=panel.labels[1],rank_convention='ceiling')],panel,panel.panel_values[:-1].tolist(),{'enabled':False})
    return {**raw,**deepcopy(result['calibrations'][f'T1-{pid}'])}


def test_training_references_use_only_the_independent_training_units(tmp_path):
    data=training_inputs(tmp_path);result=prepare(data)
    assert result['status']=='ready',result['refusals']
    assert result['references']['P1']==pytest.approx([.7,.15,.15])
    assert result['configuration']['training_units']==['R1','R2']
    assert result['manifest']['manifest_version']=='1.3'
    assert result['manifest']['calibration_size']==3
    assert set(result['manifest']['exchangeable_unit_labels'])=={'C1','C2','C3'}
    assert result['transport_scales']['P1']==pytest.approx(.2,abs=2e-6)
    assert result['transport_scales']['P2']==pytest.approx(.2,abs=2e-6)
    # A changed calibration histogram must not alter learned quantities.
    for row in data['counts']:
        if row['cohort_id']=='C1-P1':
            row['count']={'<=1':5,'2':4,'>2':1}[row['category']]
    changed=prepare(data)
    assert changed['references']==result['references']
    assert changed['transport_scales']==result['transport_scales']


def test_normalized_radius_is_converted_to_the_correct_physical_radius(tmp_path):
    result=prepare(training_inputs(tmp_path));assert result['status']=='ready',result['refusals']
    validate_calibration_manifest(result['manifest'])
    spec=parse_spec(target_spec(tmp_path,result))
    import jsonschema
    from pathlib import Path
    schema=json.loads((Path(__file__).resolve().parents[1]/'schemas/input.schema.json').read_bytes())
    jsonschema.Draft202012Validator(schema).validate(target_spec(tmp_path,result))
    assert spec.wasserstein_radius==pytest.approx(result['manifest']['radius']*result['transport_scales']['P1'])
    assert spec.reference_distribution.tolist()==pytest.approx([.7,.15,.15])
    raw=target_spec(tmp_path,result)
    raw['calibration_context']['panel_id']='foreign'
    with pytest.raises(ValueError,match='panel'):
        parse_spec(raw)


def test_unscaled_training_references_keep_the_original_manifest_contract(tmp_path):
    result=prepare(training_inputs(tmp_path),scaling='none')
    assert result['status']=='ready',result['refusals']
    assert result['manifest']['manifest_version']=='1.2'
    assert parse_spec(target_spec(tmp_path,result)).wasserstein_radius==result['manifest']['radius']


@pytest.mark.parametrize('case',['missing_training_category','target_outcome','role_overlap','only_one_training_unit'])
def test_incomplete_or_overlapping_training_never_produces_a_manifest(tmp_path,case):
    data=training_inputs(tmp_path)
    if case=='missing_training_category':
        data['counts']=[r for r in data['counts'] if not(r['cohort_id']=='R1-P1' and r['category']=='2')]
    elif case=='target_outcome':
        data['counts'].append({**data['counts'][0],'cohort_id':'T1-P1'})
    elif case=='role_overlap':
        next(r for r in data['roster'] if r['cohort_id']=='R1-P1')['unit_id']='C1'
    else:
        data['roster']=[r for r in data['roster'] if r['unit_id']!='R2']
        data['counts']=[r for r in data['counts'] if not r['cohort_id'].startswith('R2-')]
    result=prepare(data)
    assert result['status']=='unavailable' and result['manifest'] is None
    assert result['calibrations']=={} and result['refusals']
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('bad',[0,-1,float('nan'),float('inf'),True,.7])
def test_scale_changes_are_detected_before_application(tmp_path,bad):
    result=prepare(training_inputs(tmp_path));assert result['status']=='ready'
    raw=target_spec(tmp_path,result)
    raw['wasserstein_calibration_manifest']['calibration_contract']['transport_scaling']['panels']['P1']['scale']=bad
    with pytest.raises(ValueError):
        parse_spec(raw)


def test_scales_need_explicit_training_and_training_needs_an_explicit_method(tmp_path):
    data=training_inputs(tmp_path)
    result=preparation.prepare_calibration(**save_inputs(data),level=.75)
    assert result['status']=='unavailable'
    result=preparation.prepare_calibration(**save_inputs(fixture_inputs(tmp_path)),level=.75,
        transport_scaling='training')
    assert result['status']=='unavailable'


def test_panel_hash_is_checked_even_if_scale_contract_hash_is_recomputed(tmp_path):
    result=prepare(training_inputs(tmp_path));assert result['status']=='ready'
    raw=target_spec(tmp_path,result)
    contract=raw['wasserstein_calibration_manifest']['calibration_contract']['transport_scaling']
    contract['panels']['P1']['panel_sha256']='0'*64
    raw['wasserstein_calibration_manifest']['data_hashes']['transport_scaling']=preparation.canonical_sha256(contract)
    with pytest.raises(ValueError,match='panel'):
        parse_spec(raw)


def test_leave_one_out_rank_event_is_simultaneous_for_fixed_positive_scales():
    # An independent finite rank argument: each row is a whole two-panel unit.
    physical=np.array([[.1,1.2],[.4,.8],[.3,2.0],[.6,.2]])
    scales=np.array([.2,2.0]);scores=np.max(physical/scales,axis=1)
    successes=[]
    for held in range(4):
        radius=max(np.delete(scores,held))
        joint=bool(np.all(physical[held]<=radius*scales+1e-12))
        assert joint==bool(scores[held]<=radius+1e-12)
        successes.append(joint)
    assert sum(successes)==3


def test_public_analysis_and_count_update_keep_the_scaled_event(tmp_path):
    from mic_50_90.analysis import analyse_spec
    from mic_50_90.count_updates import analyse_with_counts
    from mic_50_90.report import render_html
    result=prepare(training_inputs(tmp_path));assert result['status']=='ready'
    raw=target_spec(tmp_path,result)
    raw['question_utility']={'enabled':False}
    analysed=analyse_spec(raw)
    conf=analysed['assumption_dependent_scenarios']['wasserstein_ambiguity_set']
    assert conf['guarantee_class']=='conformal_new_cohort'
    assert conf['transport_scale']==result['transport_scales']['P1']
    assert conf['radius']==pytest.approx(conf['normalized_radius']*conf['transport_scale'])
    assert all(row['envelope'] is not None for row in conf['threshold_results'])
    rendered=render_html(analysed,tmp_path/'trained-report.html').read_text(encoding='utf-8')
    assert 'Normalized calibration radius' in rendered and 'applied physical radius' in rendered
    calibration={key:raw.pop(key) for key in ('reference_distribution','wasserstein_calibration_manifest','calibration_context')}
    updated=analyse_with_counts(raw,[dict(threshold=1,unit='mg/L',count=2,n=10)],calibration=calibration)
    after=updated['assumption_dependent_scenarios']['wasserstein_ambiguity_set']
    assert after['normalized_radius']==conf['normalized_radius']
    assert after['transport_scale']==conf['transport_scale']
    assert after['radius']==conf['radius']
    assert after['threshold_results'][0]['envelope']['lower']==pytest.approx(.2)
    assert after['threshold_results'][0]['envelope']['upper']==pytest.approx(.2)


def test_fallback_checks_selected_calibration_units(tmp_path):
    from mic_50_90.conformal import calibrate_wasserstein_manifest
    result = prepare(training_inputs(tmp_path))
    options = dict(alpha=.25, grouping={'source':'example'}, source='test',
                   data_hashes={'example':'fixed'}, calibrate_on='units',
                   unit_aggregation='max', calibration_contract=result['manifest']['calibration_contract'])
    with pytest.raises(ValueError, match='disjoint'):
        calibrate_wasserstein_manifest(group_scores=[.1], group_units=['C0'],
            global_scores=[.1,.2,.3], global_units=['R1','C1','C2'], **options)
    manifest = calibrate_wasserstein_manifest(group_scores=[.1], group_units=['R1'],
        global_scores=[.1,.2,.3], global_units=['C1','C2','C3'], **options).as_dict()
    validate_calibration_manifest(manifest)
    assert manifest['fallback_used']


def test_bad_hash_mapping_is_an_input_error(tmp_path):
    result = prepare(training_inputs(tmp_path))
    for bad in (None, [], 42, 'bad'):
        manifest = deepcopy(result['manifest'])
        manifest['data_hashes'] = bad
        with pytest.raises(ValueError, match='data_hashes'):
            validate_calibration_manifest(manifest)


def test_training_refusal_retains_requested_method(tmp_path):
    data = training_inputs(tmp_path)
    data['counts'] = [r for r in data['counts'] if not (r['cohort_id']=='R1-P1' and r['category']=='2')]
    result = prepare(data)
    assert result['status']=='unavailable'
    assert result['configuration']['reference_method']=='training'
    html = preparation._report_html(result)
    assert 'Pooled reference from separate training units' in html
    assert 'Fixed uniform reference' not in html


def test_audit_reports_manifest_training_label_check(tmp_path):
    from mic_50_90.calibration_audit import audit_calibration
    result = prepare(training_inputs(tmp_path))
    roster = [dict(unit_id='T1',cohort_id='T1-P1',target_id='gt:1')]
    observations = [dict(**roster[0],status='ok',truth=.2,lower=.1,upper=.3)]
    audit = audit_calibration(roster, observations, manifest=result['manifest'])
    assert audit['assumptions']['training_disjointness']=='No exact unit-label overlap; biological overlap is not verified'
