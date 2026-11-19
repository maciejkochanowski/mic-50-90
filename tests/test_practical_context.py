"""Context must survive adapters without becoming statistical evidence."""
from copy import deepcopy
import json

import pytest

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.cli import main
from mic_50_90.input_context import THRESHOLD_FIELDS
from mic_50_90.model import MICPanel
from worked_inputs import worked_inputs
from mic_50_90.result_view import distribution_overview


def payload():
    return deepcopy(next(row['payload'] for row in worked_inputs() if row['id'] == 'summary20'))


def write_csv(path, rows):
    import csv
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


def csv_inputs(value, folder):
    """Panels, summaries or counts, and targets of one worked input as command-line CSV files."""
    raw = value['config']
    panel = MICPanel.from_dict(raw['panel'])
    panels = [dict(panel_id='p', unit=raw['unit'], category=item.label, panel_value=item.panel_value,
                   lower=item.lower, upper=item.upper, lower_closed=str(item.lower_closed).lower(),
                   upper_closed=str(item.upper_closed).lower()) for item in panel.bins]
    shared = dict(cohort_id=raw['cohort_id'], panel_id='p', iid='false', confidence_level=.95,
                  sample_context=json.dumps(raw['sample_context'], ensure_ascii=False))
    if value['mode'] == 'batch':
        rows = [dict(shared, variant_id='primary', n=raw['n'], mic50='<=1', mic90='2', rank50=10, rank90=18,
                     rank_convention='ceiling')]
    else:
        rows = [dict(shared, rank_convention='ceiling', **row) for row in value['histogram']]
    targets = [dict({key: '' for key in ('decision_operator', 'decision_fraction', *THRESHOLD_FIELDS)},
                    cohort_id=raw['cohort_id'], **row) for row in value['targets']]
    return (write_csv(folder / 'input.csv', rows), write_csv(folder / 'panels.csv', panels),
            write_csv(folder / 'targets.csv', targets))


def add_context(value):
    value['config']['sample_context'] = {
        'host_species': 'cattle', 'specimen': 'milk', 'repeat_sampling': 'yes',
        'grouping_notes': 'Several animals from each farm', 'intended_population': 'Regional dairy herds',
        'source_note': 'Table 3, retained extension field'}
    return value


def test_distribution_context_roundtrip_does_not_infer_iid_or_change_bounds(tmp_path):
    value = payload()
    baseline = analyse_distribution(value['config'])
    add_context(value)
    source = tmp_path / 'input.json'
    source.write_text(json.dumps(value['config']), encoding='utf-8')
    assert main(['distribution', str(source), '--output-dir', str(tmp_path / 'output')]) == 0
    result = json.loads((tmp_path / 'output/results.json').read_text())['cohorts'][0]
    assert result['provenance']['sample_context'] == value['config']['sample_context']
    assert result['sample'] == baseline['sample']
    assert result['inference_requested']['population'] is False
    assert json.loads((tmp_path / 'output/configuration.json').read_text())['inputs'][0]['sample_context'] == value['config']['sample_context']
    html = (tmp_path / 'output/report.html').read_text(encoding='utf-8')
    assert 'Regional dairy herds' in html and 'Several animals from each farm' in html
    assert 'Source facts supplied with the input' in html
    assert 'User assumptions and interpretation' in html


@pytest.mark.parametrize('mode', ['batch', 'reporting-audit'])
def test_table_adapter_keeps_context_and_threshold_provenance(tmp_path, mode):
    value = add_context(payload())
    value['mode'] = mode
    value['options'] = {}
    value['targets'] = [{'threshold': 1, 'unit': 'mg/L', 'threshold_kind': 'clinical',
        'threshold_source': 'User supplied standard', 'threshold_version': '2026',
        'threshold_applicability': 'cattle / milk / organism / drug / method'}]
    if mode == 'reporting-audit':
        value['rank_convention'] = 'ceiling'
        value['histogram'] = [{'category': '<=1', 'count': 8}, {'category': '2', 'count': 10}, {'category': '>2', 'count': 2}]
    source, panels, targets = csv_inputs(value, tmp_path)
    assert main([mode, source, '--panels', panels, '--targets', targets, '--output-dir', str(tmp_path / 'output')]) == 0
    result = json.loads((tmp_path / 'output/results.json').read_text())[0]
    assert result['provenance']['sample_context'] == value['config']['sample_context']
    assert result['provenance']['threshold_context'][0]['threshold_source'] == 'User supplied standard'
    html = (tmp_path / 'output/report.html').read_text(encoding='utf-8')
    assert 'User supplied standard' in html and 'Regional dairy herds' in html


def test_missing_clinical_provenance_allows_descriptive_analysis():
    value = payload()
    value['config']['targets'] = [{'threshold': 1, 'unit': 'mg/L', 'threshold_kind': 'clinical'}]
    record = analyse_distribution(value['config'])
    html = distribution_overview(record)
    assert 'neutral MIC wording' in html
    assert 'clinically resistant' not in html


def test_repeat_sampling_enum_is_validated_without_rewriting_input():
    value = add_context(payload())
    value['config']['sample_context']['repeat_sampling'] = 'maybe'
    with pytest.raises(ValueError, match='Repeat sampling must be yes, no or unknown'):
        analyse_distribution(value['config'])
    assert value['config']['sample_context']['repeat_sampling'] == 'maybe'


def test_suggested_count_request_identifies_sample_denominator_and_exact_categories():
    record = analyse_distribution(payload()['config'])
    request = record['interpretation'].get('count_request', '')
    assert '20' in request and 'mg/L' in request
    assert record['cohort_id'] in request
    assert 'same original isolates' in request
    assert 'including' in request
    assert 'recorded' in request
    assert 'Ready-to-copy count request' in distribution_overview(record)


def test_context_is_escaped_in_report():
    value = add_context(payload())
    value['config']['sample_context']['host_species'] = '<img src=x onerror=alert(1)>'
    html = distribution_overview(analyse_distribution(value['config']))
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert '<img src=x onerror=alert(1)>' not in html


def test_generic_distribution_csv_retains_sample_context_and_source(tmp_path):
    import csv
    from mic_50_90.cli import main
    from mic_50_90.model import MICPanel

    def write(name, rows):
        with (tmp_path/name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    context = {'host_species': 'cattle', 'specimen': 'milk', 'repeat_sampling': 'unknown',
               'intended_population': 'QA herds', 'retained_extension': {'table': 3}}
    panel = MICPanel.from_dict({'levels': [1, 2]})
    write('panels.csv', [dict(panel_id='P', unit='mg/L', category=x.label, panel_value=x.panel_value,
        lower=x.lower, upper=x.upper, lower_closed=str(x.lower_closed).lower(),
        upper_closed=str(x.upper_closed).lower()) for x in panel.bins])
    write('summaries.csv', [dict(cohort_id='csv-context', panel_id='P', variant_id='primary', n=20,
        organism='QA organism', antimicrobial='QA drug', source='QA source',
        sample_context=json.dumps(context))])
    write('counts.csv', [dict(cohort_id='csv-context', threshold=1, count=8, n=20, unit='mg/L')])
    assert main(['distribution', str(tmp_path/'summaries.csv'), '--panels', str(tmp_path/'panels.csv'),
        '--additional-counts', str(tmp_path/'counts.csv'), '--output-dir', str(tmp_path/'output')]) == 0
    saved = json.loads((tmp_path/'output/configuration.json').read_text())['inputs'][0]
    record = json.loads((tmp_path/'output/results.json').read_text())['cohorts'][0]
    assert saved['sample_context'] == record['provenance']['sample_context'] == context
    assert saved['organism'] == record['provenance']['organism'] == 'QA organism'
    assert saved['source'] == record['provenance']['source'] == 'QA source'
    assert record['inference_requested']['population'] is False
    html = (tmp_path/'output/report.html').read_text(encoding='utf-8')
    assert 'QA herds' in html and 'QA organism' in html and 'QA source' in html
