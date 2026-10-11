"""Whole-category counts must reach the same integer problem as tail counts."""
from types import SimpleNamespace

import numpy as np
import pytest

from mic_50_90.count_updates import _observations
from mic_50_90.distribution_workflow import analyse_distribution, distribution_problems
from mic_50_90.model import MICPanel


def raw_count(**information):
    panel = MICPanel.from_dict({'levels': [.25, .5, 1, 2]})
    return dict(n=50, unit='mg/L', panel=panel.as_dict(), additional_counts=[
        dict(start_category=panel.labels[1], end_category=panel.labels[2],
             n=50, unit='mg/L', **information)])


@pytest.mark.parametrize('information,expected', [({'count': 7}, (7, 7)),
    ({'count_min': 6, 'count_max': 8}, (6, 8)),
    ({'percentage': '14', 'decimal_places': 0, 'rounding_rule': 'half_up'}, (7, 7))])
def test_internal_counts_enter_joint_constraints(information, expected):
    problems, rows, _ = distribution_problems(raw_count(**information))
    result = next(iter(problems.values())).bounds(np.array([0, 1, 1, 0, 0]))
    assert tuple(x.count for x in result) == expected
    assert rows[0]['start_category'] == '0.5'
    assert analyse_distribution(raw_count(**information))['status'] == 'ok'


def test_interval_normalization_is_idempotent():
    raw = raw_count(percentage='14', decimal_places=0, rounding_rule='half_up')
    spec = SimpleNamespace(n=50, panel=MICPanel.from_dict(raw['panel']))
    once = _observations(raw['additional_counts'], spec)
    assert _observations(once, spec) == once


@pytest.mark.parametrize('updates', [dict(threshold=.5), dict(relation='>'),
    dict(start_category='0.3'), dict(start_category='2', end_category='0.5'),
    dict(end_category=None), dict(n=51)])
def test_ambiguous_or_invalid_intervals_are_refused(updates):
    raw = raw_count(count=7)
    raw['additional_counts'][0].update(updates)
    with pytest.raises(ValueError):
        distribution_problems(raw)


def test_interval_and_tail_must_hold_together():
    raw = raw_count(count=7)
    raw['additional_counts'].append(dict(threshold=.25, count=6, n=50, unit='mg/L'))
    with pytest.raises(ValueError, match='incompatible'):
        distribution_problems(raw)


def test_desktop_worker_and_html_keep_interval_and_population_target(tmp_path):
    import json
    from mic_50_90.gui_forms import validate_payload
    from mic_50_90.gui_worker import execute_job
    raw = raw_count(count=7)
    raw['iid'] = True
    payload = dict(mode='distribution', config=raw, options=dict(population_precision_pp=40))
    validation = validate_payload(payload)
    assert validation['valid'], validation
    assert not any('not used' in w['message'] for w in validation['warnings'])
    execute_job(payload,tmp_path)
    record = json.loads((tmp_path/'output/results.json').read_text())['cohorts'][0]
    assert record['population_resolution']['precision_pp'] == 40
    html = (tmp_path/'output/report.html').read_text(encoding='utf-8')
    assert 'Population precision requested' in html
    assert '0.5 through 1' in html
