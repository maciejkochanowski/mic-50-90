"""Context must survive adapters without becoming statistical evidence."""
from copy import deepcopy
import json

import pytest

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.gui_forms import validate_payload, desktop_examples
from mic_50_90.gui_worker import execute_job
from mic_50_90.result_view import distribution_overview


def payload():
    return deepcopy(next(row['payload'] for row in desktop_examples() if row['id'] == 'summary20'))


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
    execute_job(value, tmp_path)
    result = json.loads((tmp_path / 'output/results.json').read_text())['cohorts'][0]
    assert result['provenance']['sample_context'] == value['config']['sample_context']
    assert result['sample'] == baseline['sample']
    assert result['inference_requested']['population'] is False
    assert json.loads((tmp_path / 'output/gui-input.json').read_text()) == value
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
    execute_job(value, tmp_path)
    status = json.loads((tmp_path / 'job-status.json').read_text())
    assert status['status'] == 'completed', status
    result = json.loads((tmp_path / 'output/results.json').read_text())[0]
    assert result['provenance']['sample_context'] == value['config']['sample_context']
    assert result['provenance']['threshold_context'][0]['threshold_source'] == 'User supplied standard'
    html = (tmp_path / 'output/report.html').read_text(encoding='utf-8')
    assert 'User supplied standard' in html and 'Regional dairy herds' in html


def test_missing_clinical_provenance_warns_but_allows_descriptive_analysis():
    value = payload()
    value['config']['targets'] = [{'threshold': 1, 'unit': 'mg/L', 'threshold_kind': 'clinical'}]
    checked = validate_payload(value)
    assert checked['valid'], checked
    assert any('threshold_source' in item['message'] for item in checked['warnings'])
    record = analyse_distribution(value['config'])
    html = distribution_overview(record)
    assert 'neutral MIC wording' in html
    assert 'clinically resistant' not in html


def test_repeat_sampling_enum_is_validated_without_rewriting_input():
    value = add_context(payload())
    value['config']['sample_context']['repeat_sampling'] = 'maybe'
    checked = validate_payload(value)
    assert not checked['valid']
    assert any(item['field'] == 'config.sample_context' for item in checked['issues'])
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
