import pytest

from mic_50_90 import analyse_with_counts
from mic_50_90.decisions import decision_results, parse_criterion
from mic_50_90.workflows import analyse_layers
from test_count_updates import specification
from test_decision_workflow import _inputs, _run, _write


def test_unresolved_question_has_two_real_feasible_opposite_examples():
    raw = specification()
    result = analyse_layers(raw, False, .95)
    criteria = [parse_criterion(dict(decision_operator='<', decision_fraction='.5')), None]
    row = decision_results(result, criteria)[0]
    examples = row['sample'].get('compatible_examples')
    assert examples and len(examples) == 2
    assert {e['criterion_satisfied'] for e in examples} == {False, True}
    for example in examples:
        h = [example['histogram'][label] for label in ('1','2','4')]
        assert sum(h) == 6 and h[0] >= 3 and h[0]+h[1] <= 5
        assert example['count'] == h[1]+h[2]
        assert example['criterion_satisfied'] == (h[1]+h[2] < 3)
    assert row['sample']['examples_are_observed_data'] is False


def test_conflict_identifies_combination_not_an_innocent_count():
    rows = [dict(threshold=t, unit='mg/L', count=c, n=6, source=f'table {t}')
            for t,c in [(4,0),(1,2),(2,3)]]
    with pytest.raises(ValueError) as caught:
        analyse_with_counts(specification(), rows)
    details = getattr(caught.value, 'conflict_details', None)
    assert details is not None
    assert details['observation_numbers'] == [2,3]
    assert details['irreducible_given_summaries'] is True
    assert details['minimum_cardinality_claimed'] is False
    assert '2 mg/L' in str(caught.value) and 'same' in str(caught.value)


def test_html_shows_examples_and_source_before_diagnostics(tmp_path):
    _inputs(tmp_path)
    with (tmp_path/'summaries.csv').open() as stream:
        import csv
        rows = list(csv.DictReader(stream))
    rows[0].update(organism='Escherichia coli', antimicrobial='ampicillin', source_location='Table 2')
    _write(tmp_path/'summaries.csv', list(rows[0]), rows)
    _run(tmp_path)
    report = (tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert 'Escherichia coli' in report and 'ampicillin' in report
    assert report.index('Table 2') < report.index('Your questions')
    assert 'Two possible samples' in report and 'not observed or reconstructed isolate data' in report
    # The numerical answer must precede the illustrative histograms.
    first_answer = report.split('Your questions', 1)[1].split('Two possible samples', 1)[0]
    assert '0/10 to 1/10 isolates' in first_answer
    assert '0.00% to 10.00%' in first_answer


def test_refused_csv_preserves_actionable_conflict_details(tmp_path):
    _inputs(tmp_path)
    rows = [dict(cohort_id='C', threshold=t, unit='mg/L', count=c, n=10) for t,c in [(2,0),(4,1)]]
    _write(tmp_path/'answers.csv', list(rows[0]), rows)
    record = _run(tmp_path, '--additional-counts', str(tmp_path/'answers.csv'))[0]
    assert record['status'] == 'refused'
    assert record.get('conflict_details', {}).get('observation_numbers') == [1,2]
    report = (tmp_path/'out/report.html').read_text(encoding='utf-8')
    assert 'Check' in report and '2 mg/L' in report


def test_failed_optional_count_update_labels_baseline_before_its_witnesses(monkeypatch):
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.report import result_sections

    def failed_update(*args, **kwargs):
        raise RuntimeError('injected count update failure')

    monkeypatch.setattr(EmpiricalProblem, 'with_equality', failed_update)
    result = analyse_with_counts(specification(), [dict(threshold=1, unit='mg/L', count=2, n=6)])
    result['decision_results'] = decision_results(result, [
        parse_criterion(dict(decision_operator='<', decision_fraction='.5')), None])
    assert result['additional_information']['status'] == 'unavailable'
    examples = result['decision_results'][0]['sample']['compatible_examples']
    assert {row['count'] for row in examples} == {1, 3}
    report = result_sections(result)
    assert 'The supplied additional counts could not be applied' in report
    assert report.index('The supplied additional counts could not be applied') < report.index('This sample')
    assert 'Both examples agree with the original summaries only' in report
    assert 'and additional counts, but they give opposite answers' not in report
