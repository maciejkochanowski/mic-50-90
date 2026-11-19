"""Recompute the ampicillin values of Figure 3 with the installed MIC-50-90 package.

Writes data/ampicillin_rerun.json, which build_main_figures.py compares with
data/figure4_ampicillin.csv before it draws Figure 3.

Usage, from the repository root after `python -m pip install .`:
    python figures/rerun_ampicillin.py
"""
import json
import platform
from pathlib import Path

import mic_50_90
from mic_50_90.distribution_workflow import analyse_distribution

ROOT = Path(__file__).resolve().parent.parent
INPUTS = ROOT / 'examples' / 'appendix' / 'inputs'


def category(result, layer):
    return next(c for c in result[layer]['categories'] if c['label'] == '0.5')


def main():
    results = {}
    for state, name in (('before', 'ampicillin-67-summaries'), ('after', 'ampicillin-67-with-count')):
        sample = category(analyse_distribution(json.loads((INPUTS / f'{name}.json').read_text())), 'sample')
        results[f'sample_{state}'] = [sample['count_lower'], sample['count_upper']]
        spec = json.loads((INPUTS / f'{name}-population-category.json').read_text())
        population = analyse_distribution(spec, population_method='range-calibrated')
        bounds = category(population, 'population')
        results[f'population_{state}'] = [100 * bounds['lower'], 100 * bounds['upper']]
        results[f'population_{state}_method'] = population['population']['method']
    record = {'software': 'mic_50_90', 'version': mic_50_90.__version__, 'python': platform.python_version(),
              'inputs': 'examples/appendix/inputs', 'results': results}
    out = Path(__file__).resolve().parent / 'data' / 'ampicillin_rerun.json'
    out.write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(record, indent=1))


if __name__ == '__main__':
    main()
