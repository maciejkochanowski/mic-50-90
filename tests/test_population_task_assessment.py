"""Question-specific certification must not depend on a global endpoint gap."""
from fractions import Fraction

import pytest

from mic_50_90.decisions import assess_population_question


@pytest.mark.parametrize('op,limit,expected', [
    ('<', '.7', 'supported'), ('<=', '.6', 'supported'),
    ('>', '.05', 'supported'), ('>=', '.1', 'supported'),
    ('<', '.1', 'contradicted'), ('<=', '.05', 'contradicted'),
    ('>', '.6', 'contradicted'), ('>=', '.7', 'contradicted'),
])
def test_outer_bounds_resolve_question_without_endpoint_precision(op, limit, expected):
    result = assess_population_question(Fraction('0.1'), Fraction('0.6'), op, Fraction(limit))
    assert result['status'] == expected
    assert result['calculation_assessment'] == 'resolved'
    assert not result['further_computation_may_change_answer']


@pytest.mark.parametrize('op', ['<', '<=', '>', '>='])
def test_certified_inner_extremes_on_both_sides_prove_inconclusive(op):
    result = assess_population_question(0, 1, op, Fraction('0.5'),
        inner_lower=Fraction('0.4'), inner_upper=Fraction('0.6'))
    assert result['status'] == 'undetermined'
    assert result['calculation_assessment'] == 'region_crosses_target'
    assert not result['further_computation_may_change_answer']


def test_missing_inner_information_does_not_prove_statistical_ambiguity():
    result = assess_population_question(0, 1, '<', Fraction('0.5'))
    assert result['calculation_assessment'] == 'numerically_unresolved'
    assert result['further_computation_may_change_answer']


def test_equality_to_inner_enclosure_is_not_assumed_attained():
    result = assess_population_question(0, 1, '<', Fraction('0.5'),
        inner_lower=Fraction('0.3'), inner_upper=Fraction('0.5'))
    assert result['calculation_assessment'] == 'numerically_unresolved'


def test_invalid_inner_information_is_rejected():
    with pytest.raises(ValueError, match='inner'):
        assess_population_question(.1, .8, '<', .5, inner_lower=0, inner_upper=1)


def test_all_small_disconnected_regions_against_direct_membership():
    from itertools import combinations
    import operator
    grid = [Fraction(i, 4) for i in range(5)]
    comparisons = {'<': operator.lt, '<=': operator.le, '>': operator.gt, '>=': operator.ge}
    for size in range(1, 6):
        for region in combinations(grid, size):
            for target in [Fraction(i, 8) for i in range(9)]:
                for op, compare in comparisons.items():
                    result = assess_population_question(0, 1, op, target,
                        inner_lower=min(region), inner_upper=max(region))
                    truths = {compare(p, target) for p in region}
                    if result['calculation_assessment'] == 'region_crosses_target':
                        assert truths == {False, True}
                    if result['status'] == 'supported':
                        assert truths == {True}
                    if result['status'] == 'contradicted':
                        assert truths == {False}


def test_exact_decimal_target_is_not_compared_to_rounded_endpoint():
    # float(.1) lies above 1/10; replacing it with its printed decimal could
    # incorrectly resolve <= 10%.
    result = assess_population_question(0, .1, '<=', Fraction(1, 10))
    assert result['status'] == 'undetermined'


def test_distribution_question_exports_and_displays_reason(tmp_path):
    import json
    from mic_50_90.cli import main
    raw = dict(cohort_id='known-counts', n=20, unit='mg/L', iid=True,
        panel={'levels': [1, 2]}, additional_counts=[
            dict(threshold=1, count=8, n=20, unit='mg/L'),
            dict(threshold=2, count=2, n=20, unit='mg/L')],
        targets=[dict(threshold=1, unit='mg/L', decision_operator='<', decision_fraction='.4')])
    path = tmp_path/'input.json'
    path.write_text(json.dumps(raw), encoding='utf8')
    out = tmp_path/'out'
    assert main(['distribution', str(path), '--output-dir', str(out)]) == 0
    data = json.loads((out/'results.json').read_text(encoding='utf8'))
    decision = data['cohorts'][0]['decisions'][0]['population']
    assert decision['calculation_assessment'] == 'region_crosses_target'
    html = (out/'report.html').read_text(encoding='utf8')
    assert 'More computation alone cannot settle this question' in html
    assert 'calculation_assessment' in (out/'decisions.csv').read_text(encoding='utf8')
