"""Portable typography and display status must survive real output boundaries."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import re
import threading
from urllib.parse import unquote

from mic_50_90.distribution_workflow import analyse_distribution
from mic_50_90.distribution_report import render_distribution_html
from mic_50_90.result_view import chart_block


def test_calibration_planning_report_has_offline_typography():
    from mic_50_90.calibration_audit import _page
    text = _page('Calibration planning', '<p>95% confidence</p>')
    assert 'data:font/woff;base64,' in text and 'CMU Serif' in text


def test_calibration_preparation_report_has_offline_typography():
    from mic_50_90.calibration_preparation import _report_html
    text = _report_html(dict(summary={},manifest=None,configuration={},status='unavailable',refusals=[],unit_scores=[]))
    assert 'data:font/woff;base64,' in text and 'CMU Serif' in text


def record():
    return analyse_distribution(dict(cohort_id='font-control', n=20, unit='mg/L',
        panel=dict(levels=[1, 2]), additional_counts=[dict(threshold=1, count=8, n=20, unit='mg/L')],
        targets=[dict(threshold=1, unit='mg/L', decision_operator='<', decision_fraction='.5')]))


def test_html_and_svg_embed_actual_fonts_for_offline_reading(tmp_path):
    html_file = tmp_path/'report.html'
    render_distribution_html(dict(software_version='1.0.0', cohorts=[record()]), html_file)
    text = html_file.read_text(encoding='utf-8')
    assert 'CMU Serif' in text and 'CMU Typewriter' in text
    embedded = re.findall(r'data:font/woff;base64,([A-Za-z0-9+/=]+)', text)
    assert embedded and all(base64.b64decode(font)[:4] == b'wOFF' for font in embedded)
    chart = chart_block([dict(label='MIC \u22644', count_lower=2, count_upper=7)], 20)
    svg = unquote(re.search(r'href="data:image/svg\+xml;charset=utf-8,([^"]+)"', chart)[1])
    assert 'data:font/woff;base64,' in svg
    assert 'DejaVu Sans' in svg


def test_unrequested_layer_has_same_readable_status_in_details(tmp_path):
    html_file = tmp_path/'report.html'
    render_distribution_html(dict(software_version='1.0.0', cohorts=[record()]), html_file)
    text = html_file.read_text(encoding='utf-8')
    assert 'Population: Not requested' in text
    assert 'Calibration: Not requested' in text
    assert 'Population: unavailable' not in text
    assert not re.search(r'[{}]\s*article\s*\{break-before:page', text)


def test_packaged_fonts_are_integral_and_served_by_explicit_local_routes(tmp_path):
    from mic_50_90 import typography
    from mic_50_90.gui import create_server
    for name, info in typography.FONT_FILES.items():
        data = (typography.FONT_DIR/name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info['sha256']
        assert data[:4] == b'wOFF'
    server = create_server(output_root=tmp_path/'jobs')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def get(path):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
        connection.request('GET', path)
        response = connection.getresponse()
        data = response.read()
        result = response.status, dict(response.headers), data
        connection.close()
        return result
    try:
        name = next(iter(typography.FONT_FILES))
        status, headers, data = get('/assets/fonts/'+name)
        assert status == 200 and data == (typography.FONT_DIR/name).read_bytes()
        assert headers['Content-Type'] == 'font/woff'
        assert get('/assets/fonts/../../gui.py')[0] == 404
        assert get('/assets/fonts/unknown.woff')[0] == 404
        css_status, _, css = get('/assets/typography.css')
        assert css_status == 200 and b'CMU Serif' in css
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
