"""Redraw every figure and recompute the example numbers of the article with the installed package.

Run from a source copy of the repository, in an environment that holds the released package and
the libraries of figures/requirements-figures.txt:

    python reproducibility/reproduce_article.py --out reproduction-output

Steps:
  1. the offline self-test of the source copy (reproducibility/self_test.py);
  2. Figures 1-6 and Supplementary Figures S1-S6 (figures/build_main_figures.py);
  3. the figures of Appendices A, C and D and of the Technical Archive (figures/build_appendix_figures.py);
  4. the numbers that Appendices B and C and the examples of the article report (evaluation/examples_check.py).

Every new figure is compared with the recorded figure, and every recomputed number with the value
printed in the documents. The run passes when all 31 figures are identical to the recorded figures
and all 122 numbers match. figures/README.md states what the figure comparison covers on each
platform. The figures, numbers.csv and REPRODUCTION.json are written to the output
folder; REPRODUCTION.json records the result and the environment.
"""
import argparse
import json
import platform
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIGURES = 31
NUMBERS = 122


def run(label, arguments):
    print(f'[{label}]', flush=True)
    start = time.monotonic()
    result = subprocess.run([sys.executable] + [str(a) for a in arguments], cwd=ROOT, capture_output=True, text=True)
    seconds = round(time.monotonic() - start, 1)
    if result.returncode != 0:
        print(result.stdout + result.stderr, flush=True)
    return result, seconds


def figure_step(label, script, expected, folder):
    result, seconds = run(label, [ROOT / 'figures' / script, '--out', folder, '--check', ROOT / 'figures' / expected])
    report = json.loads(result.stdout) if result.returncode == 0 else {'figures': 0, 'identical_to_recorded_figures': False}
    identical = report['figures'] if report['identical_to_recorded_figures'] else 0
    return dict(step=label, seconds=seconds, figures=report['figures'], identical=identical, compared=report.get('compared'))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True, help='folder for the figures, numbers.csv and REPRODUCTION.json')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    self_test, seconds = run('self-test', [ROOT / 'reproducibility' / 'self_test.py'])
    steps = [dict(step='self-test', seconds=seconds, passed=self_test.returncode == 0)]
    steps.append(figure_step('main figures', 'build_main_figures.py', 'EXPECTED_MAIN_FIGURES.json', out / 'figures' / 'main'))
    steps.append(figure_step('appendix figures', 'build_appendix_figures.py', 'EXPECTED_APPENDIX_FIGURES.json',
                             out / 'figures' / 'appendix'))
    examples, seconds = run('example numbers', [ROOT / 'evaluation' / 'examples_check.py', '--output', out])
    summary = out / 'examples' / 'summary.json'
    statuses = json.loads(summary.read_text(encoding='utf-8'))['statuses'] if examples.returncode == 0 else {}
    steps.append(dict(step='example numbers', seconds=seconds, numbers=sum(statuses.values()), match=statuses.get('match', 0)))

    identical = steps[1]['identical'] + steps[2]['identical']
    match = steps[3]['match']
    passed = steps[0]['passed'] and identical == FIGURES and match == NUMBERS and steps[3]['numbers'] == NUMBERS
    record = dict(passed=passed, figures_identical=identical, figures_expected=FIGURES, numbers_match=match,
                  numbers_expected=NUMBERS, steps=steps,
                  environment={'python': platform.python_version(), 'platform': platform.platform(),
                               'machine': platform.machine(),
                               **{name: version(name) for name in ('mic-50-90', 'numpy', 'scipy', 'matplotlib')}})
    (out / 'REPRODUCTION.json').write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')
    print(f"Figures compared by: {steps[2]['compared']}")
    print(f"{'REPRODUCED' if passed else 'NOT REPRODUCED'}: {identical} of {FIGURES} figures identical to the recorded "
          f"figures, {match} of {NUMBERS} numbers match")
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
