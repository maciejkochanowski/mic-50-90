"""Whole-category questions use the same event in every user-facing path."""
from copy import deepcopy
import csv
import json

import pytest

from mic_50_90.distribution_workflow import analyse_distribution, distribution_problems
from mic_50_90.distribution_decisions import distribution_decisions


def specimen():
    # Twelve, six and two observed isolates; no reconstructed individual data.
    return dict(cohort_id='range-example', n=20, unit='mg/L', panel={'levels': [1, 2]},
        additional_counts=[dict(threshold=1, count=8, n=20, unit='mg/L'),
                           dict(threshold=2, count=2, n=20, unit='mg/L')],
        targets=[dict(start_category='2', end_category='2', unit='mg/L',
                      decision_operator='<=', decision_fraction='.3')])


def test_interior_question_uses_its_own_count_and_exact_criterion():
    raw = specimen()
    decision = analyse_distribution(raw)['decisions'][0]
    assert decision['sample']['count_components'] == [[6, 6]]
    assert decision['sample']['status'] == 'supported'
    raw['targets'][0]['decision_operator'] = '<'
    assert analyse_distribution(raw)['decisions'][0]['sample']['status'] == 'contradicted'


def test_disconnected_variants_remain_disconnected_for_range_questions():
    raw = specimen()
    raw.pop('additional_counts')
    raw['n'] = 10
    raw['summaries'] = dict(minimum='2', maximum='2')
    raw['reporting_envelope'] = {'variants': [dict(id='other', summaries=dict(minimum='<=1', maximum='<=1'))]}
    row = analyse_distribution(raw)['decisions'][0]
    assert row['sample']['count_components'] == [[0, 0], [10, 10]]
    assert row['sample']['status'] == 'undetermined'


@pytest.mark.parametrize('change', [
    {'threshold': 1}, {'end_category': None}, {'start_category': '>2', 'end_category': '2'},
    {'start_category': '1.5'}, {'start_category': True},
])
def test_ambiguous_or_split_category_questions_are_refused(change):
    raw = specimen()
    raw['targets'][0].update(change)
    with pytest.raises(ValueError):
        analyse_distribution(raw)


def test_population_uses_certified_range_projection_not_difference_of_loose_cdf_bounds():
    raw = specimen()
    raw['targets'][0]['decision_fraction'] = '.5'
    problems, _, _ = distribution_problems(raw)
    layer = dict(method='range-calibrated', confidence_level=.95, guarantee='simultaneous',
        cdf=[dict(lower=0, upper=1), dict(lower=0, upper=1)],
        interval_bounds=[dict(start_index=1, stop_index=2, lower=.2, upper=.4,
                              inner_lower=.25, inner_upper=.35)])
    row = distribution_decisions(raw, problems, layer, {'reason': 'No reference'})[0]
    assert row['population']['status'] == 'supported'
    assert row['population']['lower'] <= .2
    assert row['population']['lower'] == pytest.approx(.2)
    assert row['population']['upper'] >= .4
    assert row['population']['upper'] == pytest.approx(.4)
    assert row['population']['confidence_level'] == .95


def test_calibration_projects_joint_cdf_event_without_assuming_independence():
    raw = specimen()
    problems, _, _ = distribution_problems(raw)
    layer = dict(confidence_level=.9, guarantee='new compatible study unit',
        cdf=[dict(lower=.4, upper=.6), dict(lower=.8, upper=.9)])
    row = distribution_decisions(raw, problems, {}, layer)[0]
    assert row['calibration']['lower'] == pytest.approx(.2)
    assert row['calibration']['upper'] == pytest.approx(.5)
    assert row['calibration']['status'] == 'undetermined'


def test_gui_json_cli_and_csv_keep_range_question_and_display_its_meaning(tmp_path):
    from mic_50_90.cli import main
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    raw = specimen()
    payload = dict(mode='distribution', config=deepcopy(raw), options={})
    validation = validate_payload(payload)
    assert validation['valid'], validation
    job = tmp_path/'desktop'
    job.mkdir()
    execute_job(payload, job)
    desktop = json.loads((job/'output/results.json').read_text())['cohorts'][0]
    source = tmp_path/'input.json'
    source.write_text(json.dumps(raw))
    out = tmp_path/'cli'
    assert main(['distribution', str(source), '--output-dir', str(out)]) == 0
    command = json.loads((out/'results.json').read_text())['cohorts'][0]
    assert desktop['decisions'] == command['decisions']
    html = (out/'report.html').read_text(encoding='utf8')
    assert 'recorded MIC category 2 mg/L' in html
    assert '6 of 20 isolates' in html
    with (out/'decisions.csv').open(encoding='utf8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]['start_category'] == rows[0]['end_category'] == '2'
    assert rows[0]['threshold'] == ''


def test_full_panel_and_empty_tail_are_exact_in_optional_layers():
    raw = specimen()
    raw['targets'][0].update(start_category='<=1', end_category='>2', decision_fraction='1')
    raw['iid'] = True
    row = analyse_distribution(raw)['decisions'][0]
    assert row['sample']['count_components'] == [[20, 20]]
    assert row['population']['lower'] == row['population']['upper'] == 1


def test_update_preserves_range_question_and_all_previous_counts():
    raw = specimen()
    last = raw['additional_counts'].pop()
    before = analyse_distribution(raw)
    assert before['decisions'][0]['sample']['count_components'] == [[0, 8]]
    saved = dict(input=deepcopy(raw), result=before, population_method='bonferroni')
    raw['additional_counts'].append(last)
    after = analyse_distribution(raw, previous_analysis=saved)
    assert after['decisions'][0]['sample']['count_components'] == [[6, 6]]
    assert after['decisions'][0]['sample']['status'] == 'supported'


def test_all_contiguous_sample_events_agree_with_independent_integer_enumeration():
    from itertools import product
    from fractions import Fraction
    labels = ['<=1', '2', '4', '>4']
    histograms = [(*x, 5-sum(x)) for x in product(range(6), repeat=3)
        if sum(x) <= 5 and x[0] >= 1 and 5-sum(x) >= 1
        and x[0] < 3 <= x[0]+x[1] and 1 <= x[1]+x[2] <= 3]
    assert histograms
    raw = dict(n=5, unit='mg/L', panel={'levels': [1, 2, 4]},
        summaries=dict(minimum='<=1', maximum='>4', quantiles=[
            dict(probability='.5', category='2', rank=3)]),
        additional_counts=[dict(start_category='2', end_category='4',
            count_min=1, count_max=3, n=5, unit='mg/L')],
        targets=[dict(start_category=labels[a], end_category=labels[b-1], unit='mg/L',
                      decision_operator='<', decision_fraction='1/2')
                 for a in range(4) for b in range(a+1, 5)])
    for row in analyse_distribution(raw)['decisions']:
        a, b = row['start_index'], row['stop_index']
        counts = {sum(h[a:b]) for h in histograms}
        received = {x for lo, hi in row['sample']['count_components'] for x in range(lo, hi+1)}
        assert received == counts
        answers = {Fraction(x, 5) < Fraction(1, 2) for x in counts}
        assert row['sample']['status'] == ({True: 'supported', False: 'contradicted'}[next(iter(answers))]
                                          if len(answers) == 1 else 'undetermined')


def test_csv_range_selector_is_not_dropped_when_reading_multiple_cohorts(tmp_path):
    from mic_50_90.cli import main
    from mic_50_90.model import MICPanel
    def write(name, fields, rows):
        with (tmp_path/name).open('w', encoding='utf8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    panel = MICPanel.from_dict(specimen()['panel'])
    write('panels.csv', ['panel_id', 'unit', 'category', 'panel_value', 'lower', 'upper', 'lower_closed', 'upper_closed'],
        [dict(panel_id='P', unit='mg/L', category=b.label, panel_value=b.panel_value,
              lower=b.lower, upper=b.upper, lower_closed=str(b.lower_closed).lower(),
              upper_closed=str(b.upper_closed).lower()) for b in panel.bins])
    write('samples.csv', ['cohort_id', 'panel_id', 'variant_id', 'n'],
          [dict(cohort_id=c, panel_id='P', variant_id='primary', n=20) for c in ('A', 'B')])
    write('counts.csv', ['cohort_id', 'threshold', 'count', 'n', 'unit'],
          [dict(cohort_id=c, **row) for c in ('A', 'B') for row in specimen()['additional_counts']])
    write('targets.csv', ['cohort_id', 'threshold', 'start_category', 'end_category', 'unit', 'decision_operator', 'decision_fraction'],
          [dict(cohort_id=c, **specimen()['targets'][0]) for c in ('A', 'B')])
    out = tmp_path/'out'
    assert main(['distribution', str(tmp_path/'samples.csv'), '--panels', str(tmp_path/'panels.csv'),
        '--additional-counts', str(tmp_path/'counts.csv'), '--targets', str(tmp_path/'targets.csv'),
        '--output-dir', str(out)]) == 0
    rows = json.loads((out/'results.json').read_text())['cohorts']
    assert len(rows) == 2
    assert all(r['decisions'][0]['sample']['count_components'] == [[6, 6]] for r in rows)
    # The Windows text-table route must accept the identical no-threshold CSV.
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_documents import run_tables
    payload = dict(mode='distribution', input_format='tables', tables={
        key: dict(text=(tmp_path/name).read_text(encoding='utf8'), delimiter='comma')
        for key, name in [('input','samples.csv'),('panels','panels.csv'),
                          ('targets','targets.csv'),('additional_counts','counts.csv')]})
    # Remove the unused legacy header, matching a category-only user's table.
    payload['tables']['targets']['text'] = payload['tables']['targets']['text'].replace(
        'cohort_id,threshold,', 'cohort_id,').replace('A,,','A,').replace('B,,','B,')
    checked = validate_payload(payload)
    assert checked['valid'], checked['issues']
    gui_work, gui_out = tmp_path/'gui-work', tmp_path/'gui-out'
    gui_work.mkdir(); gui_out.mkdir()
    run_tables(payload, gui_work, gui_out)
    received = json.loads((gui_out/'results.json').read_text())['cohorts']
    assert all(r['decisions'][0]['sample']['count_components'] == [[6, 6]] for r in received)


@pytest.mark.parametrize('mode', ['batch','reporting-audit'])
def test_legacy_table_modes_still_require_threshold_questions(mode):
    from mic_50_90.gui_documents import validate_document
    result = validate_document(dict(mode=mode, tables={'targets': dict(delimiter='comma',
        text='cohort_id,start_category,end_category,unit\nA,2,2,mg/L\n')}))
    assert any(r['field']=='tables.targets' and 'threshold' in r['message'] for r in result['issues'])
