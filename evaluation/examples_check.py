"""Recompute every number that Appendices B and C and the article's examples report.

The commands of examples/appendix/COMMANDS.txt are run on the supplied inputs (the Windows forms
store the same inputs), and each reported number is read from the program's output files and
compared with the value printed in the documents, at the printed precision.

Output: OUTPUT/examples/summary.json and OUTPUT/examples/numbers.csv. The command outputs are kept
in OUTPUT/examples/runs/.
"""
from __future__ import annotations

import common

import json
import shutil
import subprocess
import tempfile
import sys
from decimal import Decimal
from pathlib import Path

from common import HERE, now, read_json, write_csv, write_json

EXAMPLES = HERE.parent / 'examples' / 'appendix'
CLI = [sys.executable, '-m', 'mic_50_90']
YEARS = range(2007, 2022)


def commands():
    runs = {
        'ampicillin-before': ['distribution', 'inputs/ampicillin-67-summaries-category.json'],
        'ampicillin-after': ['distribution', 'inputs/ampicillin-67-with-count-category.json'],
        'ampicillin-rank60': ['distribution', 'inputs/ampicillin-67-with-count-rank60.json'],
        'guide-before': ['distribution', 'inputs/guide-ampicillin-before.json', '--population-method', 'range-calibrated',
                         '--population-time-limit', '120', '--population-tolerance-pp', '0.01'],
        'guide-after': ['distribution', 'inputs/guide-ampicillin-after.json', '--population-method', 'range-calibrated',
                        '--population-time-limit', '120', '--population-tolerance-pp', '0.01', '--previous-output', '{runs}/guide-before'],
        'chloramphenicol': ['distribution', 'inputs/chloramphenicol-67-censored.json'],
        'precision-before': ['distribution', 'inputs/penicillin-2018-precision-before.json', '--population-method', 'range-calibrated',
                             '--population-precision-pp', '10'],
        'precision-after': ['distribution', 'inputs/penicillin-2018-precision-after.json', '--population-method', 'range-calibrated',
                            '--population-precision-pp', '10'],
        'amikacin': ['reporting-audit', 'inputs/laboratory/counts.csv', '--panels', 'inputs/laboratory/panels.csv', '--targets',
                     'inputs/laboratory/targets.csv', '--reporting-plan'],
        'request-sequential': ['batch', 'inputs/acquisition-teaching/summaries.csv', '--panels', 'inputs/acquisition-teaching/panels.csv',
                               '--targets', 'inputs/acquisition-teaching/targets.csv', '--acquisition-plan', '--round-cost', '0'],
        'request-batch': ['batch', 'inputs/acquisition-teaching/summaries.csv', '--panels', 'inputs/acquisition-teaching/panels.csv',
                          '--targets', 'inputs/acquisition-teaching/targets.csv', '--acquisition-plan', '--round-cost', '2'],
        'laboratory-requests': ['reporting-audit', 'inputs/acquisition-laboratory/counts.csv', '--panels',
                                'inputs/acquisition-laboratory/panels.csv', '--targets', 'inputs/acquisition-laboratory/targets.csv',
                                '--acquisition-plan', '--round-cost', '1'],
        'fsis-calibration': ['batch', 'inputs/fsis-calibration/summaries.csv', '--panels', 'inputs/fsis-calibration/panels.csv', '--targets',
                             'inputs/fsis-calibration/targets.csv', '--calibrations', 'inputs/fsis-calibration/calibrations.json',
                             '--question-time-limit', '0.01'],
    }
    for year in YEARS:
        runs[f'penicillin-{year}'] = ['distribution', f'inputs/penicillin-annual/{year}.json']
    analyses = {'scenarios': 'inputs/advanced/ampicillin-scenarios.json', 'reference-wide': 'inputs/advanced/ampicillin-reference-wide.json',
                'models': 'inputs/advanced/ampicillin-models.json'}
    return runs, analyses


def cohort(runs, name):
    return read_json(runs / name / 'results.json')['cohorts'][0]


def category(result, label):
    return next(c for c in result['sample']['categories'] if c['label'] == label)


def population_category(result, index):
    return result['population']['category_bounds'][index]


def numbers(runs):
    """(document, quantity, printed value, reproduced value, scale) for every reported number."""
    out = []
    add = lambda doc, quantity, printed, value, scale=1: out.append((doc, quantity, printed, value, scale))
    before, after = cohort(runs, 'ampicillin-before'), cohort(runs, 'ampicillin-after')
    for doc in ('Article 3.2', 'Appendix B.5/B.7', 'Appendix C.3'):
        add(doc, 'ampicillin 0.5 mg/L, summaries: lowest count', '1', category(before, '0.5')['count_lower'])
        add(doc, 'ampicillin 0.5 mg/L, summaries: highest count', '32', category(before, '0.5')['count_upper'])
        add(doc, 'ampicillin 0.5 mg/L, with 59 at <=0.25: lowest count', '2', category(after, '0.5')['count_lower'])
        add(doc, 'ampicillin 0.5 mg/L, with 59 at <=0.25: highest count', '7', category(after, '0.5')['count_upper'])
    add('Appendix C.3', 'ampicillin 0.5 mg/L, MIC90 rank 60: lowest count', '1', category(cohort(runs, 'ampicillin-rank60'), '0.5')['count_lower'])
    add('Appendix C.3', 'ampicillin 0.5 mg/L, MIC90 rank 60: highest count', '7', category(cohort(runs, 'ampicillin-rank60'), '0.5')['count_upper'])
    add('Article 3.2', 'ampicillin 0.5 mg/L share, lower (%)', '2.99', category(after, '0.5')['fraction_lower'], 100)
    add('Article 3.2', 'ampicillin 0.5 mg/L share, upper (%)', '10.45', category(after, '0.5')['fraction_upper'], 100)
    add('Appendix B.5', 'ampicillin 0.5 mg/L share before the count, lower (%)', '1.49', category(before, '0.5')['fraction_lower'], 100)
    add('Appendix B.5', 'ampicillin 0.5 mg/L share before the count, upper (%)', '47.76', category(before, '0.5')['fraction_upper'], 100)
    guide_before, guide_after = cohort(runs, 'guide-before'), cohort(runs, 'guide-after')
    for doc in ('Article 3.3', 'Appendix B.6/B.7', 'Appendix C.4'):
        add(doc, 'population interval, category 0.5, summaries: lower (%)', '0.004', population_category(guide_before, 2)[0], 100)
        add(doc, 'population interval, category 0.5, summaries: upper (%)', '65.22', population_category(guide_before, 2)[1], 100)
        add(doc, 'population interval, category 0.5, with count: lower (%)', '0.109', population_category(guide_after, 2)[0], 100)
        add(doc, 'population interval, category 0.5, with count: upper (%)', '25.00', population_category(guide_after, 2)[1], 100)
    add('Appendix B.6', 'compatible tables evaluated, summaries', '2', guide_before['population']['evaluated_histograms'])
    add('Appendix B.6', 'compatible tables evaluated, with count', '2', guide_after['population']['evaluated_histograms'])
    chloramphenicol = cohort(runs, 'chloramphenicol')
    question = chloramphenicol['decisions'][0]['sample']['count_components'][0]
    for doc in ('Article 3.4', 'Appendix C.5'):
        add(doc, 'chloramphenicol above 2 mg/L: lowest count', '34', question[0])
        add(doc, 'chloramphenicol above 2 mg/L: highest count', '67', question[1])
    add('Article 3.4', 'chloramphenicol above 2 mg/L: lowest share (%)', '50.75', question[0] / 67, 100)
    add('Appendix C.5', 'chloramphenicol: results recorded <=4', '33', category(chloramphenicol, '<=4')['count_lower'])
    shares = {}
    for year in YEARS:
        result = cohort(runs, f'penicillin-{year}')
        middle = category(result, '(0.06,2]')
        assert middle['count_lower'] == middle['count_upper']
        shares[year] = (middle['count_lower'], result['n'])
        add('Article Figure 3', f'penicillin {year}: isolates >0.06 to 2 mg/L', str(middle['count_lower']), middle['count_lower'])
        add('Article Figure 3', f'penicillin {year}: isolates', str(result['n']), result['n'])
        add('Article Figure 3', f'penicillin {year}: share >0.06 to 2 mg/L (%)', f'{100 * middle["count_lower"] / result["n"]:.1f}',
            middle['count_lower'] / result['n'], 100)
    for year, printed in ((2016, '19.64'), (2018, '18.10'), (2021, '29.19')):
        add('Article 3.1 / Appendix C.2', f'penicillin {year}: share >0.06 to 2 mg/L (%)', printed, shares[year][0] / shares[year][1], 100)
    add('Article 3.1', 'isolates 2007-2021', '7133', sum(n for _, n in shares.values()))
    for name, printed in (('precision-before', ((75.62, 83.67), (0, 24.38), (0, 24.38), 2)),
                          ('precision-after', ((75.62, 83.67), (14.47, 22.20), (0.90, 3.88), 3))):
        result = cohort(runs, name)
        for index, label in enumerate(('<=0.06', '>0.06 to 2', '>2')):
            low, high = population_category(result, index)
            add('Appendix C.6', f'{name}: {label}, lower (%)', f'{printed[index][0]:.2f}', low, 100)
            add('Appendix C.6', f'{name}: {label}, upper (%)', f'{printed[index][1]:.2f}', high, 100)
        add('Appendix C.6', f'{name}: confirmed groups', str(printed[3]), result['population_resolution']['guaranteed_number_of_bins'])
    sequential = read_json(runs / 'request-sequential' / 'results.json')[0]['result']['acquisition_plan']
    grouped = read_json(runs / 'request-batch' / 'results.json')[0]['result']['acquisition_plan']
    for doc in ('Appendix A.7', 'Appendix C.7'):
        add(doc, 'teaching request, no round cost: worst-case cost', '2', sequential['worst_case_cost'])
        add(doc, 'teaching request, round cost 2: worst-case cost', '5', grouped['worst_case_cost'])
    laboratory = read_json(runs / 'laboratory-requests' / 'results.json')[0]['result']
    add('Appendix A.7 / C.7', 'laboratory cohort: counts requested (worst case)', '0', laboratory['acquisition_plan']['worst_case_cost'])
    add('Appendix A.7 / C.7', 'laboratory cohort: observations', '266', laboratory['sample_size'])
    models = read_json(runs / 'models.json')['threshold_results'][0]
    scenarios = read_json(runs / 'scenarios.json')['assumption_dependent_scenarios']
    wide = read_json(runs / 'reference-wide.json')['assumption_dependent_scenarios']['wasserstein_ambiguity_set']['threshold_results'][0]['envelope']
    efficiency, bayes = models['optional_efficiency_analysis'], models['bayesian_sensitivity']
    for doc in ('Appendix A (at a glance)', 'Appendix C.10'):
        add(doc, 'maximum entropy, share above 0.25 mg/L (%)', '29.10', scenarios['maximum_entropy']['tail_estimates']['0.25'], 100)
        add(doc, 'multinomial likelihood, share above 0.25 mg/L (%)', '28.21', efficiency['population_tail_mle'], 100)
    add('Appendix C.10', 'KL projection to a uniform reference (%)', '29.10', scenarios['kl_reference_projection']['tail_estimates']['0.25'], 100)
    add('Appendix C.10', 'transport radius 1: lower (%)', '34.65', wide['lower'], 100)
    add('Appendix C.10', 'transport radius 1: upper (%)', '49.25', wide['upper'], 100)
    add('Appendix C.10', 'profile likelihood: lower (%)', '6.448', efficiency['profile_likelihood']['confidence_set'][0], 100)
    add('Appendix C.10', 'profile likelihood: upper (%)', '56.400', efficiency['profile_likelihood']['confidence_set'][1], 100)
    add('Appendix C.10', 'Dirichlet posterior mean (%)', '25.62', bayes['posterior_tail']['mean'], 100)
    add('Appendix C.10', 'Dirichlet posterior interval: lower (%)', '9.89', bayes['posterior_tail']['equal_tail_interval'][0], 100)
    add('Appendix C.10', 'Dirichlet posterior interval: upper (%)', '47.95', bayes['posterior_tail']['equal_tail_interval'][1], 100)
    add('Appendix C.10', 'Dirichlet effective sample size', '2168', bayes['effective_sample_size'])
    add('Appendix C.10', 'Dirichlet posterior mean, Monte Carlo standard error (pp)', '0.197', bayes['posterior_tail']['mcse_of_mean'], 100)
    return out


def compare(printed, value, scale):
    if value is None:
        return '', 'not run'
    value = float(value) * scale
    decimals = max(0, -Decimal(printed).as_tuple().exponent)
    shown = f'{value:.{decimals}f}'
    return shown, 'match' if shown == printed else 'differs'


def main():
    parser = common.parser(__doc__, workers=False)
    parser.add_argument('--keep-runs', action='store_true', help='keep the analysis outputs in OUTPUT/examples/runs')
    args = parser.parse_args()
    folder = args.output.resolve() / 'examples'
    if args.keep_runs:
        runs = folder / 'runs'
        shutil.rmtree(runs, ignore_errors=True)
    else:
        runs = Path(tempfile.mkdtemp(prefix='mic-50-90-examples-'))
    runs.mkdir(parents=True, exist_ok=True)
    table, analyses = commands()
    for name, arguments in table.items():
        arguments = [a.replace('{runs}', str(runs)) for a in arguments]
        result = subprocess.run(CLI + arguments + ['--output-dir', str(runs / name)], cwd=EXAMPLES, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f'{name} failed:\n{result.stdout}\n{result.stderr}')
    for name, path in analyses.items():
        result = subprocess.run(CLI + ['analyse', path, '--output', str(runs / f'{name}.json')], cwd=EXAMPLES, capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f'{name} failed:\n{result.stdout}\n{result.stderr}')
    verify = subprocess.run([sys.executable, str(HERE.parent / 'examples' / 'received_report' / 'verify.py'),
                             str(runs / 'amikacin' / 'reporting_certificates.json')], capture_output=True, text=True)
    rows = []
    for doc, quantity, printed, value, scale in numbers(runs):
        shown, status = compare(printed, value, scale)
        rows.append(dict(document=doc, quantity=quantity, printed=printed, reproduced=shown, status=status))
    rows.append(dict(document='Appendix B.9 / C.8', quantity='recipient check of the amikacin certificate (exit status)', printed='0',
                     reproduced=str(verify.returncode), status='match' if verify.returncode == 0 else 'differs'))
    write_csv(folder / 'numbers.csv', rows)
    counts = {s: sum(r['status'] == s for r in rows) for s in ('match', 'differs', 'not run')}
    write_json(folder / 'summary.json', dict(comparison='examples', created_utc=now(), status='complete', full_design=True, statuses=counts,
               environment=common.environment(), numbers=rows))
    if not args.keep_runs:
        shutil.rmtree(runs, ignore_errors=True)
    for r in rows:
        if r['status'] != 'match':
            print(r)
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
