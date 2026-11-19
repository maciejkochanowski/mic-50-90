"""Recompute the ampicillin values of the figures with the installed MIC-50-90 package.

Writes data/ampicillin_rerun.json, which build_main_figures.py compares with its own
calculation and with the data files before it draws Figures 3 and 4 and Supplementary Figure S2.

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


def selected_tables(name):
    """The tables that the endpoint theorem selects, one at each boundary between categories."""
    import numpy as np
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.utility import _prefix_distances
    problems, _, _ = distribution_problems(json.loads((INPUTS / f'{name}.json').read_text()))
    selected = []
    for problem in problems.values():
        d = _prefix_distances(problem)
        for row in [np.diff(d[a, :]) for a in range(1, d.shape[0])]:
            table = [int(x) for x in row]
            if table not in selected:
                selected.append(table)
    return selected


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
        full = analyse_distribution(json.loads((INPUTS / f'{name}.json').read_text()))
        results[f'categories_{state}'] = [[c['label'], c['count_lower'], c['count_upper']] for c in full['sample']['categories']]
    results['selected_tables_before'] = selected_tables('ampicillin-67-summaries-conditional-population')
    record = {'software': 'mic_50_90', 'version': mic_50_90.__version__, 'python': platform.python_version(),
              'inputs': 'examples/appendix/inputs', 'results': results}
    out = Path(__file__).resolve().parent / 'data' / 'ampicillin_rerun.json'
    out.write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(record, indent=1))


if __name__ == '__main__':
    main()
