"""Presentation checks: geometry must preserve the engine's information."""
import xml.etree.ElementTree as ET

from mic_50_90.result_view import count_chart


def elements(svg, name):
    return ET.fromstring(svg).findall('{http://www.w3.org/2000/svg}' + name)


def test_disjoint_ranges_remain_separate_and_carry_exact_counts():
    svg = count_chart([dict(label='Test <group>', count_lower=0, count_upper=20,
                           count_components=[[0, 2], [18, 20]])], 20)
    segments = [e for e in elements(svg, 'line') if 'data-count-lower' in e.attrib]
    assert [(e.attrib['data-count-lower'], e.attrib['data-count-upper'])
            for e in segments] == [('0', '2'), ('18', '20')]
    assert float(segments[0].attrib['x2']) < float(segments[1].attrib['x1'])
    assert 'Test &lt;group&gt;' in svg
    assert '0–2 or 18–20' in svg
    assert 'Sample share (%)' in svg
    assert 'Count / 20' in svg


def test_exact_zero_and_full_sample_have_honest_bar_lengths():
    svg = count_chart([dict(label='Zero', count_lower=0, count_upper=0),
                       dict(label='All', count_lower=50, count_upper=50)], 50)
    bars = [e for e in elements(svg, 'rect') if 'data-count-lower' in e.attrib]
    assert float(bars[0].attrib['width']) == 0
    assert float(bars[1].attrib['width']) == 440
    assert '100.00%' in svg
    assert 'DejaVu Sans' in svg


def test_long_labels_and_many_components_fit_without_inventing_a_midpoint():
    svg = count_chart([dict(label='>0.000000125 to 0.000000250 mg/L',
                           count_lower=0, count_upper=100,
                           count_components=[[0, 10], [40, 50], [90, 100]])], 100)
    root = ET.fromstring(svg)
    height = float(root.attrib['viewBox'].split()[3])
    for e in elements(svg, 'text'):
        assert 0 < float(e.attrib['y']) < height
    assert len([e for e in elements(svg, 'line') if 'data-count-lower' in e.attrib]) == 3
    assert not elements(svg, 'circle')
