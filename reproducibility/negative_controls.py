"""Negative controls of the reproduction: one changed input value must be detected.

    python reproducibility/negative_controls.py figures
    python reproducibility/negative_controls.py numbers

Each control works on a temporary copy of the source and leaves the repository unchanged.

figures  One isolate is added to a published count of the Madrid data (2007, isolates above
         2 mg/L: 13 becomes 14, with the middle count and its percentage adjusted to agree). The
         comparison of Figures 1-6 and Supplementary Figures S1-S6 with the recorded figures must
         fail.
numbers  The count printed in the ampicillin example is lowered by one isolate (59 becomes 58).
         The comparison of the recomputed numbers with the printed values must report a difference.

A control passes when the comparison itself reports the change; the exit status is then 0.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPIED = ('figures', 'evaluation', 'examples')


def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise SystemExit(f'{path.name}: expected exactly one occurrence of {old!r}')
    path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')


def figures(copy):
    replace_once(copy / 'figures' / 'data' / 'madrid_pneumococci.csv', '2007,539,0.023,1,136,13,123,22.82', '2007,539,0.023,1,136,14,122,22.6345')
    result = subprocess.run([sys.executable, str(copy / 'figures' / 'build_main_figures.py'), '--out', str(copy / 'out'),
                             '--check', str(copy / 'figures' / 'EXPECTED_MAIN_FIGURES.json')], capture_output=True, text=True)
    if result.returncode == 0:
        return False, 'the comparison passed'
    try:
        differences = json.loads(result.stdout)['differences']
    except (ValueError, KeyError):
        raise SystemExit('The figure script stopped before the comparison:\n' + result.stdout + result.stderr) from None
    return bool(differences), f'{len(differences)} differences from the recorded figures, the first: {differences[0]}'


def numbers(copy):
    replace_once(copy / 'examples' / 'appendix' / 'inputs' / 'ampicillin-67-with-count-category.json', '"count": 59', '"count": 58')
    result = subprocess.run([sys.executable, str(copy / 'evaluation' / 'examples_check.py'), '--output', str(copy / 'out')],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit('The examples stopped before the comparison:\n' + result.stdout + result.stderr)
    statuses = json.loads((copy / 'out' / 'examples' / 'summary.json').read_text(encoding='utf-8'))['statuses']
    return statuses['differs'] > 0, f"{statuses['differs']} of {sum(statuses.values())} numbers differ from the printed values"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('control', choices=('figures', 'numbers'))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mic-50-90-control-') as folder:
        copy = Path(folder)
        for name in COPIED:
            shutil.copytree(ROOT / name, copy / name, ignore=shutil.ignore_patterns('__pycache__'))
        detected, evidence = (figures if args.control == 'figures' else numbers)(copy)
    print(f"{'DETECTED' if detected else 'NOT DETECTED'}: changed input in the {args.control} control; {evidence}")
    sys.exit(0 if detected else 1)


if __name__ == '__main__':
    main()
