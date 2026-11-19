"""MIC-50-90 appendix and Technical Archive figures, drawn from the results in this repository.

Figures A.1-A.2, C.1-C.6, D.1-D.8 and TA1-TA3. Every value comes from the evaluation results and
example inputs of the repository, or is computed by the installed package; the script asserts the
values that the captions and texts print before drawing.

Appearance is fixed by this script: the font files are bundled (fonts/), matplotlib starts from
its pristine defaults (style/), and the library versions are pinned in requirements-figures.txt.

Usage, from the repository root after `python -m pip install .`:
    python figures/build_appendix_figures.py --out <empty folder>
           [--check figures/EXPECTED_APPENDIX_FIGURES.json] [--only A1,D3]
With --check the script compares the new files with the recorded figures and fails on any
difference: PNG by decoded pixels, SVG and PDF byte for byte, and the plotted values.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from PIL import Image

HERE = Path(__file__).resolve().parent
MM = 1 / 25.4
WIDTH = 140 * MM
# Palette of the appendix figures.
INK = '#000000'; DARK = '#1F1F1F'; TICK = '#333333'; SPINE = '#555555'; GREY = '#8A8A8A'
GRID = '#E3E3E3'; WHITE = '#FFFFFF'; ORANGE = '#CC6A10'; BLUE = '#1F5C99'; HAZE = '#A9BCCC'
SLATE = '#4E6A85'
FORBIDDEN = ['·', '•', '∙', '⋅']
PINNED = {'matplotlib': '3.11.2', 'numpy': '2.5.3', 'scipy': '1.18.0', 'PIL': '12.3.0', 'fontTools': '4.67.0'}
PACKAGE_VERSION = '2.0.0'  # version of MIC-50-90 whose results the figures show

font_manager.fontManager.ttflist = [f for f in font_manager.fontManager.ttflist if f.name != 'Liberation Sans']
for _font in sorted((HERE / 'fonts').glob('*.ttf')):
    font_manager.fontManager.addfont(str(_font))
_NOT_STYLE = ('backend', 'interactive', 'toolbar', 'webagg.', 'tk.', 'timezone', 'datapath',
              'docstring.', 'date.epoch', 'savefig.directory', 'figure.raise_window', 'figure.max_open_warning')
_defaults = matplotlib._rc_params_in_file(
    str(HERE / 'style' / 'matplotlibrc-3.11.2-default'),
    transform=lambda line: line[1:] if line.startswith('#') else line, fail_on_error=True)
matplotlib.rcParams.update({k: v for k, v in _defaults.items() if not k.startswith(_NOT_STYLE)})
plt.rcParams.update({
    'pdf.compression': 0, 'font.family': 'Liberation Sans', 'font.size': 7.5, 'text.color': INK,
    'axes.labelcolor': INK, 'axes.edgecolor': SPINE, 'axes.linewidth': .6,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.labelsize': 8,
    'xtick.labelsize': 7.5, 'ytick.labelsize': 7.5, 'xtick.color': SPINE, 'ytick.color': SPINE,
    'xtick.labelcolor': TICK, 'ytick.labelcolor': TICK, 'xtick.major.width': .6, 'ytick.major.width': .6,
    'xtick.major.size': 3, 'ytick.major.size': 3, 'legend.fontsize': 7.5, 'legend.frameon': False,
    'lines.linewidth': 1.0, 'svg.fonttype': 'path', 'svg.hashsalt': 'mic-50-90-appendix',
    'pdf.fonttype': 42, 'mathtext.fontset': 'dejavusans', 'figure.facecolor': WHITE, 'savefig.facecolor': WHITE})

REPO = HERE.parent
OUT: Path
RECORD: list = []
INPUTS: set = set()


def need(condition, message):
    if not condition:
        raise SystemExit('Value check failed: ' + message)


def load(relative):
    path = REPO / relative
    INPUTS.add(relative)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            return [json.loads(line) for line in handle] if path.name.endswith('.jsonl.gz') else json.load(handle)
    if path.suffix == '.csv':
        with path.open(newline='', encoding='utf-8') as handle:
            return list(csv.DictReader(handle))
    return json.loads(path.read_text(encoding='utf-8'))


def grid_y(ax):
    ax.grid(axis='y', color=GRID, linewidth=.6, zorder=0)
    ax.set_axisbelow(True)


def grid_x(ax):
    ax.grid(axis='x', color=GRID, linewidth=.6, zorder=0)
    ax.set_axisbelow(True)


def save(fig, name, values):
    for text in fig.findobj(matplotlib.text.Text):
        need(not any(mark in text.get_text() for mark in FORBIDDEN), f'{name}: forbidden separator')
    fig.savefig(OUT / f'{name}.png', dpi=300, metadata={'Software': None})
    fig.savefig(OUT / f'{name}.pdf', metadata={'Creator': None, 'Producer': None, 'CreationDate': None})
    fig.savefig(OUT / f'{name}.svg', metadata={'Date': None, 'Creator': None})
    plt.close(fig)
    RECORD.append(dict(figure=name, values=json.loads(json.dumps(values)),
                       file_sha256={ext: sha(OUT / f'{name}.{ext}') for ext in ('png', 'pdf', 'svg')},
                       png_pixel_sha256=pixels(OUT / f'{name}.png')))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- Appendix A
def ceiling_rank(n, p):
    return math.ceil(round(p * n, 12))


def figure_A1():
    """Width of the share between the ceiling ranks of MIC50 and MIC90, n = 2..500."""
    ns = np.arange(2, 501)
    width = np.array([100 * max(ceiling_rank(n, .9) - ceiling_rank(n, .5) - 1, 0) / n for n in ns])
    marks = {5: 20, 10: 30, 20: 35, 50: 38, 100: 39}
    for n, value in marks.items():
        need(round(width[n - 2]) == value, f'A.1 n = {n}')
    fig, ax = plt.subplots(figsize=(WIDTH, 62 * MM))
    fig.subplots_adjust(left=.115, right=.975, bottom=.2, top=.97)
    ax.axhline(40, color=GREY, linewidth=.9, linestyle=(0, (3, 2)), zorder=1)
    ax.text(470, 41.2, 'limit 40 points', color=GREY, ha='right', va='bottom', fontsize=7.5)
    ax.plot(ns, width, color=DARK, linewidth=1.0, zorder=3)
    offsets = {5: (0, -5.5), 10: (2, -5), 20: (3.5, -5), 50: (-0.5, -5), 100: (2, -5)}
    for n, value in marks.items():
        ax.plot(n, width[n - 2], 'o', color=DARK, markersize=5.2, zorder=4)
        ax.text(n * (1 + offsets[n][0] / 100), width[n - 2] + offsets[n][1], f'n = {n}: {value}',
                ha='center', va='center', fontsize=7, color=DARK)
    ax.set_xscale('log')
    ax.set_xticks([2, 5, 10, 20, 50, 100, 200, 500], ['2', '5', '10', '20', '50', '100', '200', '500'])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_xlim(1.85, 560)
    ax.set_ylim(-1, 45)
    ax.set_yticks([0, 10, 20, 30, 40])
    grid_y(ax)
    ax.set_xlabel('Number of isolates, n (log scale)')
    ax.set_ylabel('Width of the possible share\n(percentage points)')
    save(fig, 'Figure_A1', {str(n): v for n, v in marks.items()})


def ampicillin_tables(name):
    """Every compatible table and the selected row-potential tables of one ampicillin report."""
    from time import monotonic
    from mic_50_90.distribution_workflow import distribution_problems
    from mic_50_90.range_population import _histograms
    from mic_50_90.utility import _prefix_distances
    spec = load(f'examples/appendix/inputs/{name}.json')
    problems, _, _ = distribution_problems(spec)
    tables, selected = set(), []
    for problem in problems.values():
        d = _prefix_distances(problem)
        tables.update(_histograms(d, monotonic() + 3600))
        # One table at each category boundary: the row potentials anchored at boundaries 1..K.
        for row in [np.diff(d[a, :]) for a in range(1, d.shape[0])]:
            table = tuple(int(x) for x in row)
            if table not in selected:
                selected.append(table)
    from mic_50_90.model import MICPanel
    labels = [b.label.replace('<=', '≤').replace('>=', '≥') for b in MICPanel.from_dict(spec['panel']).bins]
    return labels, sorted(tables), selected, spec['n']


def figure_A2():
    """Compatible tables and the selected tables for ampicillin, before and after the count."""
    before = ampicillin_tables('ampicillin-67-summaries-conditional-population')
    after = ampicillin_tables('ampicillin-67-with-count-conditional-population')
    need(len(before[1]) == 7938 and len(after[1]) == 546, 'A.2 compatible tables')
    need(len(before[2]) == 5 and len(after[2]) == 4, 'A.2 selected tables')
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 78 * MM), sharey=True)
    fig.subplots_adjust(left=.1, right=.965, bottom=.15, top=.9, wspace=.1)
    for ax, (labels, tables, selected, n), colour, title, note in (
            (axes[0], before, ORANGE, 'MIC50, MIC90 and range', '5 selected tables give\nevery population endpoint'),
            (axes[1], after, BLUE, 'plus 59 of 67 at ≤0.25 mg/L', '4 selected tables give\nevery population endpoint')):
        x = np.arange(len(labels))
        for table in tables:
            ax.plot(x, 100 * np.cumsum(table) / n, color=HAZE, linewidth=.5, zorder=2)
        for table in selected:
            ax.plot(x, 100 * np.cumsum(table) / n, color=colour, linewidth=1.4, marker='o', markersize=3.0, zorder=4)
        ax.text(.0, 1.035, title, transform=ax.transAxes, color=colour, fontsize=8.5, ha='left', va='bottom')
        ax.text(.97, .3, f'{len(tables)} compatible tables', transform=ax.transAxes, color=SLATE, ha='right', fontsize=7.5)
        ax.text(.97, .13, note, transform=ax.transAxes, color=colour, ha='right', va='center', fontsize=7.5)
        ax.set_xticks(x, labels)
        ax.set_xlim(-.25, len(labels) - .75)
        ax.set_xlabel('MIC category (mg/L)')
        grid_y(ax)
    axes[1].plot(1, 100 * 59 / 67, marker='D', color=DARK, markersize=6.5, markeredgecolor=WHITE, zorder=6)
    axes[1].annotate('published: 59 of 67\nat ≤0.25 mg/L', xy=(1.05, 100 * 59 / 67 - .5), xytext=(2.3, 72.5),
                     fontsize=7.5, color=DARK, ha='left', va='center',
                     arrowprops=dict(arrowstyle='-', color=DARK, linewidth=.6))
    axes[0].set_ylim(40, 101.5)
    axes[0].set_yticks(range(40, 101, 10))
    axes[0].set_ylabel('Isolates at or below the category (%)')
    save(fig, 'Figure_A2', dict(compatible=[len(before[1]), len(after[1])], selected=[len(before[2]), len(after[2])]))


# ---------------------------------------------------------------- Appendix C
def figure_C3():
    """Seconds per calculation of the same 95% endpoints: selected tables against all tables."""
    summary = load('evaluation/results/endpoint_selection/summary.json')['reports']
    before = ampicillin_tables('ampicillin-67-summaries-conditional-population')
    after = ampicillin_tables('ampicillin-67-with-count-conditional-population')
    rows = []
    for key, tables, colour, label in (('summaries', before, ORANGE, 'MIC50, MIC90 and range'),
                                       ('with count', after, BLUE, 'plus 59 of 67 at ≤0.25 mg/L')):
        report = summary[key]
        need(report['compatible_tables'] == len(tables[1]), f'C.3 {key} tables')
        low, high = report['category_05']['lower_pp'], report['category_05']['upper_pp']
        rows.append((f'{label}\nendpoints {low:.3f}–{high:.2f}%', report['median_seconds_selected'],
                     report['median_seconds_exhaustive'], len(tables[2]), len(tables[1]), colour))
    fig, ax = plt.subplots(figsize=(WIDTH, 58 * MM))
    fig.subplots_adjust(left=.26, right=.975, bottom=.2, top=.97)
    for y, (label, fast, slow, selected, total, colour) in zip((1, 0), rows):
        ax.plot([fast, slow], [y, y], color=colour, linewidth=1.4, zorder=2)
        ax.plot(fast, y, 'o', color=colour, markersize=6.5, zorder=3)
        ax.plot(slow, y, 'o', color=colour, markerfacecolor=WHITE, markeredgewidth=1.4, markersize=6.5, zorder=3)
        for x, top, bottom in ((fast, f'{fast:.3f} s', f'{selected} selected tables'),
                               (slow, f'{slow:.3f} s', f'all {total} tables')):
            ax.text(x, y + .21, top, color=colour, ha='center', va='bottom', fontsize=7.5)
            ax.text(x, y - .21, bottom, color=colour, ha='center', va='top', fontsize=7.5)
        ax.text(-.02, y, label, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=7.5,
                color=TICK, linespacing=1.15)
    ax.set_xscale('log')
    ax.set_xticks([.05, .1, .2, .5, 1, 2, 5], ['0.05', '0.1', '0.2', '0.5', '1', '2', '5'])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_xlim(.035, 8)
    ax.set_ylim(-.6, 1.6)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Seconds per calculation of the same 95% endpoints (log scale)')
    save(fig, 'Figure_C3', {key: [summary[key]['median_seconds_selected'], summary[key]['median_seconds_exhaustive']]
                            for key in summary})


def figure_C4():
    """Chloramphenicol: the two recorded measurement intervals against the source threshold."""
    from mic_50_90.distribution_workflow import analyse_distribution
    result = analyse_distribution(load('examples/appendix/inputs/chloramphenicol-67-censored.json'))
    counts = {c['label']: (c['count_lower'], c['count_upper']) for c in result['sample']['categories']}
    need(counts['<=4'] == (33, 33) and counts['8'] == (34, 34), 'C.4 recorded counts')
    need(result['decisions'][0]['sample']['count_components'] == [[34, 67]], 'C.4 answer above 2 mg/L')
    low = 100 * 34 / 67
    log = math.log2
    fig, ax = plt.subplots(figsize=(WIDTH, 56 * MM))
    fig.subplots_adjust(left=.04, right=.975, bottom=.22, top=.97)
    ax.axvline(log(2), color=GREY, linewidth=.9, linestyle=(0, (3, 2)), zorder=1, ymax=.95)
    ax.text(log(2) - .08, 3.05, 'source threshold 2 mg/L', color=GREY, ha='right', va='center', fontsize=7.5)
    ax.annotate('', xy=(log(.25) + .05, 2.25), xytext=(log(4), 2.25),
                arrowprops=dict(arrowstyle='-|>', color=HAZE, linewidth=3, mutation_scale=9, shrinkA=0, shrinkB=0))
    ax.plot(log(4), 2.25, 'o', color=HAZE, markersize=7, zorder=3)
    ax.text(log(.25) + .32, 2.55, 'no lower limit', color=SLATE, ha='left', va='center', fontsize=7.5)
    ax.text(log(4) + .17, 2.25, '33 isolates, MIC ≤4 mg/L: possibly above 2', color=SLATE, ha='left', va='center',
            fontsize=7.5)
    ax.plot([log(4), log(8)], [1.25, 1.25], color=DARK, linewidth=2.6, zorder=2)
    ax.plot(log(4), 1.25, 'o', color=DARK, markerfacecolor=WHITE, markeredgewidth=1.4, markersize=7, zorder=3)
    ax.plot(log(8), 1.25, 'o', color=DARK, markersize=7, zorder=3)
    ax.text(log(8) + .17, 1.25, '34 isolates, 4 < MIC ≤8 mg/L: certainly above 2', color=DARK, ha='left',
            va='center', fontsize=7.5)
    ax.text(log(2) + .12, .62, f'Above 2 mg/L: 34–67 of 67 isolates ({low:.2f}–100%)', color=DARK,
            ha='left', va='center', fontsize=7.5)
    ax.set_xlim(log(.25) - .06, log(16) + 2.65)
    ax.set_ylim(0, 3.35)
    ax.set_xticks([log(v) for v in (.25, .5, 1, 2, 4, 8, 16)], ['0.25', '0.5', '1', '2', '4', '8', '16'])
    ax.spines['bottom'].set_bounds(log(.25), log(16))
    ax.spines['left'].set_visible(False)
    ax.set_yticks([])
    ax.set_xlabel('MIC (mg/L, log2 scale)', x=.37)
    save(fig, 'Figure_C4', dict(recorded=[33, 34], above_2=[34, 67], percent=[round(low, 2), 100]))


# ---------------------------------------------------------------- Appendix D: twenty development cohorts
GROUPS = (('FDA', 'Dogs, FDA animal-pathogen data'), ('NORM', 'People, NORM 2024 streptococci'))


def cohort_label(row):
    organism = row['organism']
    if organism.startswith('Streptococcus '):
        organism = 'S. ' + organism.split(' ', 1)[1]
    elif organism == 'Klebsiella spp':
        organism = 'Klebsiella spp.'
    drug = ' '.join(word if len(word) == 1 else word.lower() for word in row['drug'].replace('/', '-').split(' '))
    return f"{organism}, {drug}, n = {row['n']}"


def cohort_layout():
    """Rows of the twenty cohorts: two sources, larger collections first."""
    cohorts = load('evaluation/data/population_cohorts.json')
    need(len(cohorts) == 20, 'twenty development cohorts')
    rows, headers, y = [], [], 0.
    for key, title in GROUPS:
        members = [c for c in cohorts if (key == 'NORM') == ('NORM' in c['source'])]
        members.sort(key=lambda c: (-c['n'], [-int(part) for part in c['case'].split('-')[1:]]))
        headers.append((y - .86, title))
        for member in members:
            rows.append((y, member['case'], cohort_label(member)))
            y += 1
        y += 1.36
    return rows, headers


def cohort_axes(height_mm=112):
    fig, ax = plt.subplots(figsize=(WIDTH, height_mm * MM))
    fig.subplots_adjust(left=.477, right=.965, bottom=.115, top=.975)
    rows, headers = cohort_layout()
    for y, _, label in rows:
        ax.text(-.02, y, label, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=7.5, color=TICK)
    for y, title in headers:
        ax.text(-.02, y, title, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8,
                fontweight='bold', color=DARK)
    ax.set_ylim(rows[-1][0] + .7, headers[0][0] - .45)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    return fig, ax, rows


def figure_D1():
    """Coverage of the 95% population bounds in the coverage simulation, by cohort."""
    summary = load('evaluation/results/coverage/summary.json')
    coverage = {c['case']: c for c in summary['cohorts']}
    fig, ax, rows = cohort_axes()
    for y, case, _ in rows:
        bonferroni = 100 * coverage[case]['bonferroni']['coverage']
        calibrated = 100 * coverage[case]['range-calibrated']['coverage']
        ax.plot(bonferroni, y - .15, 'o', color=DARK, markersize=5.2, zorder=3)
        ax.plot(calibrated, y + .15, 'D', color=DARK, markerfacecolor=WHITE, markeredgewidth=1.2, markersize=4.9, zorder=3)
    y0, case0, _ = rows[0]
    ax.text(100 * coverage[case0]['bonferroni']['coverage'] + .03, y0 - .15 - .2, 'Bonferroni', ha='left',
            va='center', fontsize=7.5, color=DARK)
    ax.text(100 * coverage[case0]['range-calibrated']['coverage'] - .03, y0 + .15 - .03, 'range-calibrated',
            ha='right', va='center', fontsize=7.5, color=DARK)
    lowest = min(min(c['bonferroni']['coverage'], c['range-calibrated']['coverage']) for c in coverage.values())
    need(lowest >= .99, 'D.1 axis starts at 99%')
    ax.set_xlim(99, 100.05)
    ax.set_xticks([99, 99.2, 99.4, 99.6, 99.8, 100], ['99.0', '99.2', '99.4', '99.6', '99.8', '100.0'])
    ax.spines['bottom'].set_bounds(99, 100.05)
    ax.set_xlabel('Reports with every range share inside the 95% bounds (%)')
    save(fig, 'Figure_D1', {case: [coverage[case]['bonferroni']['coverage'], coverage[case]['range-calibrated']['coverage']]
                            for _, case, _ in rows})


def figure_D2():
    """Mean width of the 95% Bonferroni intervals: complete table against MIC50, MIC90 and one count."""
    summary = load('evaluation/results/complete_tables/summary.json')
    cohorts = {c['case']: c['bonferroni'] for c in summary['cohorts']}
    median_ratio = summary['summary']['bonferroni']['median_width_ratio']
    need(f'{median_ratio:.1f}' == '3.7', 'D.2 median ratio 3.7')
    fig, ax, rows = cohort_axes()
    for y, case, _ in rows:
        complete, report = cohorts[case]['complete']['mean_width_pp'], cohorts[case]['report']['mean_width_pp']
        ax.plot([complete, report], [y, y], color=HAZE, linewidth=3, solid_capstyle='butt', zorder=2)
        ax.plot(complete, y, 'o', color=DARK, markersize=5.8, zorder=3)
        ax.plot(report, y, 'o', color=SLATE, markerfacecolor=WHITE, markeredgewidth=1.4, markersize=5.8, zorder=3)
        ax.text(report + .9, y - .02, f"{cohorts[case]['width_ratio']:.1f}×", ha='left', va='center', fontsize=7.5,
                color=GREY)
    top = rows[0][0] - .7
    ax.text(3, top, 'complete table', ha='left', va='center', fontsize=7.5, color=DARK)
    ax.text(79, top, 'MIC50, MIC90 and one count', ha='right', va='center', fontsize=7.5, color=SLATE)
    ax.set_xlim(0, 80)
    ax.set_xticks(range(0, 81, 10))
    ax.set_xlabel('Mean width of the 95% population intervals (pp)')
    save(fig, 'Figure_D2', {case: [cohorts[case]['complete']['mean_width_pp'], cohorts[case]['report']['mean_width_pp']]
                            for _, case, _ in rows})


def figure_D3():
    """Seconds per cohort for the four constructions."""
    summary = load('evaluation/results/population/summary.json')
    budget = summary['settings']['budget_seconds']
    need(round(budget) == 120, 'D.3 budget 120 s')
    seconds = {(c['case'], c['method']): c['seconds'] for c in summary['cohorts']}
    marks = {'bonferroni': ('o', DARK, DARK, -.2), 'range-calibrated': ('D', DARK, DARK, .2),
             'joint-exact': ('s', DARK, WHITE, -.2), 'range-hunter': ('^', DARK, WHITE, .2)}
    fig, ax, rows = cohort_axes()
    ax.axvline(budget, color=GREY, linewidth=.9, linestyle=(0, (3, 2)), zorder=1)
    ax.text(budget * .9, rows[0][0] - 1.25, f'{budget:.0f} s budget', ha='right', va='center', fontsize=7.5, color=GREY)
    for y, case, _ in rows:
        for method, (marker, edge, face, dy) in marks.items():
            ax.plot(seconds[(case, method)], y + dy, marker, color=edge, markerfacecolor=face, markeredgewidth=1.3,
                    markersize=5.2 if marker != 'D' else 4.9, zorder=3)
    y_last, case_last, _ = rows[-1]
    ax.text(seconds[(case_last, 'bonferroni')] * 1.25, y_last - .2, 'Bonferroni', ha='left', va='center', fontsize=7.5)
    ax.text(seconds[(case_last, 'bonferroni')] * 1.25, y_last + .2, 'range-calibrated', ha='left', va='center',
            fontsize=7.5)
    ax.text(seconds[(case_last, 'joint-exact')] * .8, y_last - .2, 'joint-exact', ha='right', va='center', fontsize=7.5)
    ax.text(seconds[(case_last, 'joint-exact')] * .8, y_last + .2, 'range-hunter', ha='right', va='center', fontsize=7.5)
    ax.set_xscale('log')
    ax.set_xticks([.01, .1, 1, 10, 100], ['0.01', '0.1', '1', '10', '100'])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_xlim(.005, 300)
    ax.set_xlabel('Seconds per cohort (log scale)')
    save(fig, 'Figure_D3', {f'{case}|{method}': seconds[(case, method)] for _, case, _ in rows for method in marks})


def figure_D4():
    """Fifteen deterministic test reports with uniform profiles: seconds to confirm every endpoint."""
    probes = load('evaluation/results/controlled_reports/records.json')['scaling_probes']
    need(len(probes) == 15 and all(p['precision_reached'] for p in probes), 'D.4 fifteen confirmed probes')
    sizes = [(200, 5), (200, 8), (200, 16), (1000, 5), (1000, 8)]
    seconds = {(p['n'], p['k'], p['information']): p['seconds'] for p in probes}
    marks = (('summaries', 'o', DARK, 'summaries alone'), ('interior', 'D', WHITE, 'plus one interior count'),
             ('two_counts', 's', DARK, 'plus two cumulative counts'))
    fig, ax = plt.subplots(figsize=(WIDTH, 62 * MM))
    fig.subplots_adjust(left=.162, right=.975, bottom=.2, top=.97)
    for y, (n, k) in enumerate(sizes):
        ax.text(-.012, y, f'n = {n}, K = {k}', transform=ax.get_yaxis_transform(), ha='right', va='center',
                fontsize=7.5, color=TICK)
        for information, marker, face, _ in marks[::-1]:
            ax.plot(seconds[(n, k, information)], y, marker, color=DARK, markerfacecolor=face, markeredgewidth=1.3,
                    markersize=5.6 if marker != 'D' else 5.4, zorder=3)
    y_last = len(sizes) - 1
    n, k = sizes[-1]
    ax.text(seconds[(n, k, 'summaries')], y_last - .4, marks[0][3], ha='center', va='center', fontsize=7)
    ax.text(seconds[(n, k, 'interior')], y_last + .36, marks[1][3], ha='center', va='center', fontsize=7)
    ax.text(seconds[(n, k, 'two_counts')], y_last - .4, marks[2][3], ha='center', va='center', fontsize=7)
    ax.set_xlim(0, .32)
    ax.set_xticks(np.arange(0, .31, .05), [f'{v:.2f}' for v in np.arange(0, .31, .05)])
    ax.set_ylim(y_last + .75, -.6)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Seconds to confirm every population endpoint (uniform profiles)', x=.55)
    save(fig, 'Figure_D4', {f'{n}|{k}|{i}': s for (n, k, i), s in seconds.items()})


def jitter(count, salt):
    """Deterministic vertical spread in [-1, 1] for overlapping points."""
    return np.array([((i + 1) * 0.6180339887498949 + salt * 0.37) % 1 * 2 - 1 for i in range(count)])


def figure_D5():
    """Coverage of the 95% bounds on the confirmation data and the synthetic populations."""
    confirmation = load('evaluation/results/confirmation_coverage/configurations.json.gz')
    synthetic = load('evaluation/results/synthetic_coverage/configurations.json.gz')
    families = [('Resampled surveillance tables', confirmation, '610 cohorts, 3 reports, 2000 reports each'),
                ('Log-normal mixtures', [c for c in synthetic if c['generator'] == 'G2'], '840 populations, 1000 reports each'),
                ('Dirichlet draws', [c for c in synthetic if c['generator'] == 'G3'], '540 populations, 1000 reports each'),
                ('Rare categories', [c for c in synthetic if c['generator'] == 'G4'], '360 populations, 1000 reports each')]
    need([len(f[1]) for f in families] == [1830, 840, 540, 360], 'D.5 configuration counts')
    fig, ax = plt.subplots(figsize=(WIDTH, 88 * MM))
    fig.subplots_adjust(left=.38, right=.975, bottom=.15, top=.97)
    ax.axvline(95, color=GREY, linewidth=.9, linestyle=(0, (3, 2)), zorder=1)
    ax.text(95.06, -.82, 'nominal 95%', color=GREY, ha='left', va='center', fontsize=7.5)
    lowest = {}
    for row, (title, configurations, detail) in enumerate(families):
        ax.text(-.02, row * 1.45, f'{title}\n{detail}', transform=ax.get_yaxis_transform(), ha='right', va='center',
                fontsize=7.5, color=TICK, linespacing=1.25)
        for offset, method, face in ((-.33, 'bonferroni', None), (.17, 'range-calibrated', 'none')):
            values = np.array([100 * c[method]['covered'] / c[method]['replicates'] for c in configurations])
            spread = jitter(len(values), row * 2 + (offset > 0)) * .11
            if face is None:
                ax.scatter(values, row * 1.45 + offset + spread, s=6, color=DARK, alpha=.55, linewidths=0, zorder=2)
            else:
                ax.scatter(values, row * 1.45 + offset + spread, s=9, facecolors='none', edgecolors=DARK, alpha=.55,
                           linewidths=.6, zorder=2)
            ax.plot([values.min()] * 2, [row * 1.45 + offset - .16, row * 1.45 + offset + .16], color=DARK,
                    linewidth=1.6, zorder=3)
            lowest[f'{title}|{method}'] = float(values.min())
    ax.text(100.08, -.33, 'Bonferroni', ha='left', va='center', fontsize=7.5)
    ax.text(100.08, .17, 'range-calibrated', ha='left', va='center', fontsize=7.5)
    ax.set_xlim(94.8, 101.6)
    ax.set_xticks(range(95, 101))
    ax.set_ylim(3 * 1.45 + .55, -1.05)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Simulated reports with every range share inside the 95% bounds (%)')
    save(fig, 'Figure_D5', lowest)


def figure_D6():
    """FSIS poultry data, 30 held-out plant groups: calibrated intervals of the shares the summaries leave open."""
    import io
    INPUTS.add('evaluation/results/calibration/fsis-trained/intervals.csv.gz')
    raw = gzip.open(REPO / 'evaluation/results/calibration/fsis-trained/intervals.csv.gz', 'rt', encoding='utf-8').read()
    rows = [r for r in csv.DictReader(io.StringIO(raw))
            if float(r['baseline_lower']) != float(r['baseline_upper'])]
    need(len(rows) == 1524 and len({r['unit_id'] for r in rows}) == 30, 'D.6 1524 open shares in 30 groups')
    covered = sum(r['covered'] == 'True' for r in rows)
    need(covered == 1524, 'D.6 every share inside its bounds')
    rows.sort(key=lambda r: (float(r['truth']), float(r['lower']), float(r['upper'])))
    x = np.arange(1, len(rows) + 1)
    truth = np.array([100 * float(r['truth']) for r in rows])
    lower = np.array([100 * float(r['lower']) for r in rows])
    upper = np.array([100 * float(r['upper']) for r in rows])
    fig, ax = plt.subplots(figsize=(WIDTH, 70 * MM))
    fig.subplots_adjust(left=.1, right=.955, bottom=.17, top=.97)
    ax.vlines(x, lower, upper, color=HAZE, linewidth=.75, zorder=2)
    ax.step(x, truth, where='mid', color=DARK, linewidth=1.2, zorder=3)
    ax.text(.04, .93, 'calibrated bounds', transform=ax.transAxes, color=SLATE, fontsize=8, ha='left', va='center')
    ax.annotate('true share in the plant group', xy=(840, 34), xytext=(780, 71), fontsize=7.5, color=DARK,
                ha='center', va='center', arrowprops=dict(arrowstyle='-', color=DARK, linewidth=.6, shrinkB=0))
    ax.text(.99, .045, f'{covered} of {len(rows)} inside their bounds', transform=ax.transAxes, ha='right',
            va='center', fontsize=7.5, color=DARK)
    ax.set_xlim(1, len(rows))
    ax.set_xticks([1, 500, 1000, len(rows)])
    ax.set_ylim(0, 100)
    ax.set_yticks(range(0, 101, 20))
    grid_y(ax)
    ax.set_xlabel('Shares not fixed by the summaries in the 30 held-out plant groups, sorted by true share')
    ax.set_ylabel('Share above the threshold (%)')
    save(fig, 'Figure_D6', dict(shares=len(rows), covered=covered))


def figure_D7():
    """Study-unit calibration with synthetic units."""
    settings = {s['setting']: s for s in load('evaluation/results/external_calibration/summary.json')['synthetic']['settings']}
    tests = [('SU1', 'Exchangeable with the calibration units'), ('SU2|weight=0.05', 'Non-wild-type share raised by 0.05'),
             ('SU2|weight=0.1', 'Non-wild-type share raised by 0.1'), ('SU2|weight=0.2', 'Non-wild-type share raised by 0.2'),
             ('SU2|shift_all=1', 'Every MIC one dilution higher'), ('SU3', 'Own wild-type center for each test unit')]
    marks = [('c=20|M=19', 'o', DARK, -.27, 'c = 20, 19 units'), ('c=20|M=39', 'D', DARK, -.09, 'c = 20, 39 units'),
             ('c=100|M=19', 'o', WHITE, .09, 'c = 100, 19 units'), ('c=100|M=39', 'D', WHITE, .27, 'c = 100, 39 units')]
    for key, *_ in marks:
        need(all(settings[key]['tests'][t]['test_units'] == 20000 for t, _ in tests), f'D.7 {key} test units')
    fig, ax = plt.subplots(figsize=(WIDTH, 80 * MM))
    fig.subplots_adjust(left=.358, right=.975, bottom=.15, top=.97)
    ax.axvline(95, color=GREY, linewidth=.9, linestyle=(0, (3, 2)), zorder=1)
    ax.text(95.15, len(tests) - .3, 'nominal 95%', color=GREY, ha='left', va='center', fontsize=7.5)
    for y, (test, label) in enumerate(tests):
        ax.text(-.02, y, label, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=7.5, color=TICK)
        for key, marker, face, dy, _ in marks:
            ax.plot(100 * settings[key]['tests'][test]['coverage'], y + dy, marker, color=DARK, markerfacecolor=face,
                    markeredgewidth=1.3, markersize=5.6 if marker != 'D' else 5.2, zorder=3)
    for i, (_, marker, face, _, label) in enumerate(marks):
        ax.plot(86.6, 1 + i * .32 - .1, marker, color=DARK, markerfacecolor=face, markeredgewidth=1.2,
                markersize=4.8 if marker != 'D' else 4.6, zorder=3)
        ax.text(87.0, 1 + i * .32 - .1, label, ha='left', va='center', fontsize=7.5)
    ax.set_xlim(86, 100.6)
    ax.set_xticks(range(86, 101, 2))
    ax.set_ylim(len(tests) - .2, -.55)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Test units with every share inside the calibrated bounds (%)')
    save(fig, 'Figure_D7', {f'{key}|{test}': settings[key]['tests'][test]['coverage'] for key, *_ in marks for test, _ in tests})


def figure_D8():
    """Sixty drug cohorts and three share criteria: counts a laboratory has to disclose."""
    tasks = load('evaluation/results/sufficient_reporting/tasks.csv')
    need(len(tasks) == 180 and all(t['recipient_sufficient'] == 'True' for t in tasks), 'D.8 180 sufficient tasks')
    groups = []
    for fraction, label in (('0.05', 'share below 5%'), ('0.1', 'share below 10%'), ('0.2', 'share below 20%'), (None, 'all three questions')):
        chosen = [t for t in tasks if fraction is None or float(t['fraction']) == float(fraction)]
        groups.append((label, len(chosen), sum(int(t['answers']) for t in chosen),
                       sum(int(t['direct_fields']) for t in chosen), sum(int(t['minimal_fields']) for t in chosen)))
    need(groups[-1][2:] == (1809, 405, 115), 'D.8 totals 1809 answers, 405 and 115 counts')
    fig, ax = plt.subplots(figsize=(WIDTH, 62 * MM))
    fig.subplots_adjust(left=.24, right=.975, bottom=.2, top=.97)
    for y, (label, count, answers, direct, minimal) in enumerate(groups):
        ax.text(-.02, y, f'{label}\n{count} tasks, {answers} answers', transform=ax.get_yaxis_transform(), ha='right',
                va='center', fontsize=7.5, color=TICK, linespacing=1.15)
        if direct == 0:
            ax.plot(0, y, 'o', color=DARK, markersize=6.3, zorder=3)
            ax.text(8, y, f'summaries alone answer all {count} tasks', ha='left', va='center', fontsize=7.5, color=DARK)
            continue
        ax.plot([minimal, direct], [y, y], color=GREY, linewidth=1.4, zorder=2)
        ax.plot(minimal, y, 'o', color=BLUE, markersize=6.3, zorder=3)
        ax.plot(direct, y, 'o', color=ORANGE, markersize=6.3, zorder=3)
        ax.text(direct, y - .32, f'{direct} counts, every unresolved count', ha='right' if direct > 200 else 'left',
                va='center', fontsize=7.5, color=ORANGE)
        ax.text(minimal, y + .3, f'{minimal} counts, smallest sufficient set', ha='left', va='center', fontsize=7.5,
                color=BLUE)
    ax.axhline(2.5, color=GRID, linewidth=1, zorder=1)
    ax.set_xlim(-8, 430)
    ax.set_xticks(range(0, 401, 50))
    ax.set_ylim(3.7, -.6)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Counts the laboratory has to disclose so that every answer can be checked')
    save(fig, 'Figure_D8', {g[0]: list(g[1:]) for g in groups})


# ---------------------------------------------------------------- Technical Archive
def figure_TA1():
    """Width between the ceiling ranks as a fraction of n, n = 10..100."""
    ns = np.arange(10, 101)
    width = np.array([max(ceiling_rank(n, .9) - ceiling_rank(n, .5) - 1, 0) / n for n in ns])
    need(f'{width[10]:.3f}' == '0.350' and f'{width[11]:.3f}' == '0.333', 'TA1 n = 20, 21')
    fig, ax = plt.subplots(figsize=(WIDTH, 62 * MM))
    fig.subplots_adjust(left=.13, right=.975, bottom=.2, top=.97)
    ax.axhline(.40, color=GREY, linewidth=.9, linestyle=(0, (3, 2)), zorder=1)
    ax.text(100, .4035, 'limit 0.40', color=GREY, ha='right', va='bottom', fontsize=7.5)
    ax.plot(ns, width, color=DARK, linewidth=1.0, zorder=3)
    for n, text, y in ((20, 'n = 20: 0.350', .318), (21, 'n = 21: 0.333, narrower with more isolates', .302)):
        ax.plot(n, width[n - 10], 'o', color=DARK, markersize=6, zorder=4)
        ax.annotate(text, xy=(n, width[n - 10]), xytext=(26, y), fontsize=7.5, color=DARK, ha='left', va='center',
                    arrowprops=dict(arrowstyle='-', color=DARK, linewidth=.6, shrinkA=0, shrinkB=3))
    ax.set_xlim(8, 102)
    ax.set_xticks(range(10, 101, 10))
    ax.set_ylim(.26, .42)
    ax.set_yticks([.26, .30, .34, .38, .42], ['0.26', '0.30', '0.34', '0.38', '0.42'])
    grid_y(ax)
    ax.set_xlabel('Number of isolates, n')
    ax.set_ylabel('Width of the possible share\nbetween the ceiling ranks (fraction of n)')
    save(fig, 'Figure_TA1', {'20': round(float(width[10]), 3), '21': round(float(width[11]), 3)})


def figure_TA2():
    """The canonical additional-count calculation, n = 100."""
    n = 100
    low, high = ceiling_rank(n, .5), ceiling_rank(n, .9) - 1
    need((low, high) == (50, 89), 'TA2 L = 50 and U = 89')
    gap = (high - low) / n
    rows = [('One target', gap, gap), ('Two targets', 2 * gap, gap)]
    fig, ax = plt.subplots(figsize=(WIDTH, 50 * MM))
    fig.subplots_adjust(left=.127, right=.945, bottom=.24, top=.97)
    for y, (label, alone, counted) in enumerate(rows):
        ax.text(-.012, y, label, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8, color=TICK)
        for dy, value, colour, text in ((-.23, alone, ORANGE, f'summaries alone: {alone:.2f}'),
                                        (.23, counted, BLUE, f'with one intermediate count: {counted:.2f}')):
            ax.plot([0, value], [y + dy] * 2, color=GRID, linewidth=1.2, zorder=1)
            ax.plot(value, y + dy, 'o', color=colour, markersize=6.5, zorder=3)
            ax.text(value + .013, y + dy, text, ha='left', va='center', fontsize=8, color=colour)
    ax.set_xlim(0, 1)
    ax.set_xticks(np.arange(0, 1.01, .2), [f'{v:.1f}' for v in np.arange(0, 1.01, .2)])
    ax.set_ylim(1.55, -.55)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Sum of worst-case interval widths (fraction of n), n = 100')
    save(fig, 'Figure_TA2', dict(L=low, U=high, gap=gap))


def figure_TA3():
    """Four-observation counterexample: original bands, a restricted transport ball and added counts."""
    # Exact constructed fractions of the Technical Archive table (tails after categories 1 and 2).
    cuts = [('First cut: tail above category 1, returned count 3 of 4', .75,
             [((.75, 1.0), ORANGE, '75–100%'), ((.75, .75), BLUE, '75% only'), ((.75, .75), BLUE, '75% only')]),
            ('Second cut: tail above category 2, true count 1 of 4', .25,
             [((.25, .50), ORANGE, '25–50%'), ((.50, .50), BLUE, '50% only, excludes the true 25%'),
              ((.25, .50), BLUE, '25–50%')])]
    labels = ['Original bands', 'Fixed ball restricted\nto the count', 'Original bands kept,\ncount added']
    for _, truth, bands in cuts:
        need(bands[0][0][0] <= truth <= bands[0][0][1] and bands[2][0][0] <= truth <= bands[2][0][1], 'TA3 truths inside')
    need(not cuts[1][2][1][0][0] <= cuts[1][1] <= cuts[1][2][1][0][1], 'TA3 restricted ball excludes the truth')
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH, 92 * MM), sharex=True)
    fig.subplots_adjust(left=.198, right=.86, bottom=.12, top=.93, hspace=.42)
    for ax, (title, truth, bands) in zip(axes, cuts):
        ax.set_title(title, loc='left', fontsize=8, color=INK, pad=6)
        for y, ((low, high), colour, text) in enumerate(bands):
            ax.text(-.015, y, labels[y], transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8,
                    color=TICK, linespacing=1.1)
            ax.plot([100 * low, 100 * high], [y, y], color=colour, linewidth=3.2, solid_capstyle='butt', zorder=2)
            ax.plot([100 * low, 100 * high], [y, y], linestyle='none', marker='|', markersize=11, markeredgewidth=1.8,
                    color=colour, zorder=2)
            ax.plot(100 * truth, y, 'o', color=DARK, markersize=6.5, zorder=3)
            ax.text(100 * high + 2, y, text, ha='left', va='center', fontsize=8, color=colour)
        if truth == .75:
            ax.annotate('true fraction', xy=(100 * truth, 0), xytext=(57, 0), fontsize=7.5, color=DARK, ha='right',
                        va='center', arrowprops=dict(arrowstyle='-', color=DARK, linewidth=.6, shrinkA=3, shrinkB=0))
        ax.set_ylim(2.6, -.6)
        ax.set_yticks([])
        ax.spines['left'].set_visible(False)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100])
        grid_x(ax)
    axes[1].set_xlabel('Share of the 4 observations in the tail (%)')
    save(fig, 'Figure_TA3', dict(truths=[c[1] for c in cuts]))


# ---------------------------------------------------------------- Appendix C, examples
def figure_C1():
    """Madrid penicillin: the same MIC50 and MIC90 in 2016, 2018 and 2021 with different group shares."""
    published = {int(r['year']): r for r in load_local('madrid_pneumococci.csv')}
    years = (2016, 2018, 2021)
    need(len({(published[y]['mic50'], published[y]['mic90']) for y in years}) == 1, 'C.1 same MIC50 and MIC90')
    groups = {}
    for year in years:
        spec = load(f'examples/appendix/inputs/penicillin-annual/{year}.json')
        above = {float(c['threshold']): int(c['count']) for c in spec['additional_counts']}
        n = int(spec['n'])
        need((above[.06], above[2]) == (int(published[year]['count_above_0_06']), int(published[year]['count_above_2'])),
             f'C.1 {year} counts')
        groups[year] = (n, [n - above[.06], above[.06] - above[2], above[2]])
    shapes = {2016: 'o', 2018: 's', 2021: '^'}
    labels = ['≤0.06 mg/L', '>0.06 to 2 mg/L', '>2 mg/L']
    fig, ax = plt.subplots(figsize=(WIDTH, 72 * MM))
    fig.subplots_adjust(left=.165, right=.96, bottom=.17, top=.9)
    for row, label in enumerate(labels):
        ax.text(-.012, row, label, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8, color=TICK)
        for i, year in enumerate(years):
            n, counts = groups[year]
            share = 100 * counts[row] / n
            y = row + (i - 1) * .24
            ax.plot(share, y, shapes[year], color=DARK, markersize=6.2, zorder=3)
            text = f'{year}: {counts[row]} of {n}, {share:.2f}%'
            if share > 60:
                ax.text(share - 1.4, y, text, ha='right', va='center', fontsize=7.5, color=DARK)
            else:
                ax.text(share + 1.4, y, text, ha='left', va='center', fontsize=7.5, color=DARK)
    for row in range(3):
        for i in range(3):
            ax.axhline(row + (i - 1) * .24, color=GRID, linewidth=.6, zorder=0)
    mic50, mic90 = published[years[0]]['mic50'], published[years[0]]['mic90']
    ax.set_title(f'Same MIC50 ({mic50} mg/L) and MIC90 ({mic90} mg/L) in all three years', loc='left', fontsize=8,
                 color=INK, pad=8)
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 10))
    ax.set_ylim(2.55, -.55)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Isolates in the MIC group (%)')
    save(fig, 'Figure_C1', {str(y): groups[y][1] for y in years})


def figure_C2():
    """Ampicillin: possible counts in each category before and after the published count, and two witnesses."""
    from mic_50_90.distribution_workflow import analyse_distribution
    before = analyse_distribution(load('examples/appendix/inputs/ampicillin-67-summaries.json'))['sample']['categories']
    after = analyse_distribution(load('examples/appendix/inputs/ampicillin-67-with-count.json'))['sample']['categories']
    tables = set(ampicillin_tables('ampicillin-67-with-count-conditional-population')[1])
    fewest, most = (34, 25, 2, 0, 6), (34, 25, 7, 0, 1)
    need(fewest in tables and most in tables, 'C.2 witnesses are compatible tables')
    need((after[2]['count_lower'], after[2]['count_upper']) == (2, 7) and (fewest[2], most[2]) == (2, 7),
         'C.2 witnesses attain 2 and 7 in category 0.5')
    labels = [c['label'].replace('<=', '≤') for c in before]
    fig, ax = plt.subplots(figsize=(WIDTH, 80 * MM))
    fig.subplots_adjust(left=.119, right=.68, bottom=.15, top=.85)
    for y, (b, a) in enumerate(zip(before, after)):
        ax.add_patch(matplotlib.patches.Rectangle((b['count_lower'], y - .2), b['count_upper'] - b['count_lower'], .4,
                                                  facecolor=HAZE, edgecolor=ORANGE, linewidth=1.2, zorder=2))
        ax.plot([a['count_lower'], a['count_upper']], [y, y], color=BLUE, linewidth=3, solid_capstyle='butt', zorder=3)
        ax.plot([a['count_lower'], a['count_upper']], [y, y], linestyle='none', marker='|', markersize=8,
                markeredgewidth=1.6, color=BLUE, zorder=3)
        ax.plot(fewest[y], y - .33, 'o', color=DARK, markerfacecolor=WHITE, markeredgewidth=1.4, markersize=8, zorder=4)
        ax.plot(most[y], y - .33, 'D', color=DARK, markersize=5.2, zorder=5)
        ax.text(-.06, y, labels[y], transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8, color=TICK)
        for x, text, colour in ((1.076, f"{b['count_lower']}–{b['count_upper']}", ORANGE),
                                (1.253, f"{a['count_lower']}–{a['count_upper']}", BLUE),
                                (1.381, str(fewest[y]), DARK), (1.485, str(most[y]), DARK)):
            ax.text(x, y, text, transform=ax.get_yaxis_transform(), ha='center', va='center', fontsize=8, color=colour)
    for x, text, colour in ((1.076, 'MIC50, MIC90\nand range', ORANGE), (1.253, 'plus 59\nat ≤0.25', BLUE),
                            (1.381, 'fewest\nin 0.5', DARK), (1.485, 'most\nin 0.5', DARK)):
        ax.text(x, -.9, text, transform=ax.get_yaxis_transform(), ha='center', va='center', fontsize=7, color=colour,
                linespacing=1.1)
    ax.annotate('fewest in 0.5', xy=(fewest[2] + .7, 2 - .36), xytext=(5, 1.4), fontsize=7.5, color=DARK, ha='left',
                va='center', arrowprops=dict(arrowstyle='-', color=DARK, linewidth=.6, shrinkA=0, shrinkB=2))
    ax.annotate('most in 0.5', xy=(most[2] + .6, 2 - .33), xytext=(10, 1.67), fontsize=7.5, color=DARK, ha='left',
                va='center', arrowprops=dict(arrowstyle='-', color=DARK, linewidth=.6, shrinkA=0, shrinkB=2))
    ax.set_xlim(0, 67)
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60, 67])
    ax.set_ylim(4.55, -.7)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_ylabel('MIC category (mg/L)')
    ax.yaxis.set_label_coords(-.155, .5)
    ax.set_xlabel('Isolates in the category (of 67)')
    save(fig, 'Figure_C2', dict(before=[[b['count_lower'], b['count_upper']] for b in before],
                                after=[[a['count_lower'], a['count_upper']] for a in after]))


def figure_C5():
    """Penicillin 2018: 95% simultaneous population intervals with one or two counts."""
    from mic_50_90.distribution_workflow import analyse_distribution
    results = {}
    for name in ('before', 'after'):
        spec = load(f'examples/appendix/inputs/penicillin-2018-precision-{name}.json')
        results[name] = analyse_distribution(spec, population_method='range-calibrated', population_precision_pp='10')
    one = [[100 * v for v in pair] for pair in results['before']['population']['category_bounds']]
    two = [[100 * v for v in pair] for pair in results['after']['population']['category_bounds']]
    merged = [b for b in results['before']['population_resolution']['bins'] if b['stop_index'] - b['start_index'] == 2]
    need(len(merged) == 1, 'C.5 one merged group with one count')
    merged = [100 * merged[0]['lower'], 100 * merged[0]['upper']]
    need(results['before']['population_resolution']['guaranteed_number_of_bins'] == 2 and
         results['after']['population_resolution']['guaranteed_number_of_bins'] == 3, 'C.5 confirmed groups 2 and 3')
    labels = ['≤0.06 mg/L', '>0.06 to 2 mg/L', '>2 mg/L']
    fig, ax = plt.subplots(figsize=(WIDTH, 78 * MM))
    fig.subplots_adjust(left=.172, right=.96, bottom=.15, top=.97)

    def bar(low, high, y, colour, text):
        ax.plot([low, high], [y, y], color=colour, linewidth=3, solid_capstyle='butt', zorder=3)
        ax.plot([low, high], [y, y], linestyle='none', marker='|', markersize=10, markeredgewidth=1.6, color=colour,
                zorder=3)
        if low > 60:
            ax.text(low - 1.2, y, text, ha='right', va='center', fontsize=7.3, color=colour)
        else:
            ax.text(high + 1.2, y, text, ha='left', va='center', fontsize=7.3, color=colour)

    for row, label in enumerate(labels):
        ax.text(-.012, row, label, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=8, color=TICK)
        bar(*one[row], row - .2, ORANGE, f'count above 0.06: {one[row][0]:.2f}–{one[row][1]:.2f}%')
        bar(*two[row], row + .2, BLUE, f'counts above 0.06 and 2: {two[row][0]:.2f}–{two[row][1]:.2f}%')
    ax.axhline(2.8, color=GRID, linewidth=1.2, zorder=1)
    ax.text(-.012, 3.55, '>0.06 mg/L\n(last two merged)', transform=ax.get_yaxis_transform(), ha='right', va='center',
            fontsize=8, color=TICK, linespacing=1.15)
    bar(*merged, 3.55, ORANGE, f'count above 0.06: {merged[0]:.2f}–{merged[1]:.2f}%')
    ax.text(100, 3.55, 'with one count, the groups that meet\nthe 10-point target are ≤0.06 and >0.06', ha='right',
            va='center', fontsize=6.8, color=GREY, linespacing=1.15)
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 10))
    ax.set_ylim(4.3, -.6)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    grid_x(ax)
    ax.set_xlabel('Population share of the MIC group, 95% simultaneous interval (%)')
    save(fig, 'Figure_C5', dict(one=one, two=two, merged=merged))


def figure_C6():
    """Two tables that fit one historical MIC summary yet answer a question differently."""
    certificate = load_local('AMBIGUITY_WITNESS_CERTIFICATE.json')
    support = [float(x) for x in certificate['mathematical_support_points']]
    counts = [w['counts'] for w in certificate['witnesses'][:2]]
    need(counts == [[1, 16, 14, 1], [1, 16, 13, 2]] and certificate['n'] == 32, 'C.6 witnesses A and B')
    for table in counts:
        values = np.repeat(support, table)
        for method in ('inverted_cdf', 'averaged_inverted_cdf', 'closest_observation', 'interpolated_inverted_cdf',
                       'hazen', 'weibull', 'linear', 'median_unbiased', 'normal_unbiased'):
            need(np.quantile(values, .5, method=method) == 1 and np.quantile(values, .9, method=method) == 2,
                 f'C.6 MIC50 and MIC90 under {method}')
        need(values.min() == .25 and values.max() == 32, 'C.6 range 0.25-32')
    ink, teal, grey, muted, ochre = '#252B30', '#28627C', '#89949B', '#58636B', '#9B592F'
    style = {'text.color': ink, 'axes.labelcolor': ink, 'axes.edgecolor': muted, 'xtick.color': muted,
             'ytick.color': muted, 'xtick.labelcolor': muted, 'ytick.labelcolor': muted, 'font.size': 8.5,
             'axes.labelsize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8, 'legend.fontsize': 8}
    with plt.rc_context(style):
        fig = plt.figure(figsize=(6.5, 3.2))
        grid = fig.add_gridspec(1, 2, left=.10, right=.98, bottom=.24, top=.80, wspace=.45, width_ratios=[1.35, 1])
        a, b = fig.add_subplot(grid[0]), fig.add_subplot(grid[1])
        x = np.arange(4)
        for offset, values, colour, label in ((-.17, counts[0], grey, 'Witness A'), (.17, counts[1], teal, 'Witness B')):
            a.bar(x + offset, values, width=.29, color=colour, label=label)
            for i, v in enumerate(values):
                a.text(i + offset, v + .5, str(v), ha='center', fontsize=7.3, color=colour)
        a.set_ylim(0, 19)
        a.set_yticks([0, 4, 8, 12, 16])
        a.set_xticks(x, ['0.25', '1', '2', '32'])
        a.set_ylabel('Isolate count', labelpad=8)
        a.set_xlabel('Mathematical support (mg/L)', labelpad=7)
        a.grid(axis='y', color='#E2E6E8', linewidth=.5)
        a.set_axisbelow(True)
        b.set_xlim(0, 8)
        b.set_ylim(-.65, 1.65)
        b.set_yticks([1, 0], ['A', 'B'])
        b.set_xticks([0, 2, 4, 6, 8])
        b.set_xlabel('Share with MIC >8 mg/L (%)', labelpad=7)
        b.spines['left'].set_visible(False)
        b.tick_params(axis='y', length=0)
        b.grid(axis='x', color='#E2E6E8', linewidth=.5)
        b.set_axisbelow(True)
        for ax, letter in ((a, 'a'), (b, 'b')):
            ax.text(-.105, 1.035, letter, transform=ax.transAxes, fontsize=10, fontweight='bold', va='bottom')
        for y, k, colour in ((1, counts[0][3], grey), (0, counts[1][3], teal)):
            v = 100 * k / 32
            b.plot([0, v], [y, y], color=colour, linewidth=1)
            b.plot(v, y, 'o', color=colour, markersize=4)
            b.annotate(f'{k}/32 = {v:g}%', (v, y), (0, 8), textcoords='offset points', ha='center', fontsize=7.6,
                       color=colour, bbox={'facecolor': 'white', 'edgecolor': 'none', 'pad': .6})
        b.axvline(5, color=ochre, linewidth=.8, linestyle=(0, (3, 3)))
        b.text(5.15, 1.5, '5%', fontsize=7.5, color=ochre)
        fig.legend(*a.get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.32, .98), ncol=2,
                   columnspacing=2, frameon=False, handlelength=2)
        save(fig, 'Figure_C6', dict(A=counts[0], B=counts[1]))


def load_local(name):
    path = HERE / 'data' / name
    INPUTS.add(f'figures/data/{name}')
    if path.suffix == '.csv':
        with path.open(newline='', encoding='utf-8') as handle:
            return list(csv.DictReader(handle))
    return json.loads(path.read_text(encoding='utf-8'))


FIGURES = {'A1': figure_A1, 'A2': figure_A2, 'C1': figure_C1, 'C2': figure_C2, 'C3': figure_C3, 'C4': figure_C4,
           'C5': figure_C5, 'C6': figure_C6, 'D1': figure_D1, 'D2': figure_D2, 'D3': figure_D3, 'D4': figure_D4,
           'D5': figure_D5, 'D6': figure_D6, 'D7': figure_D7, 'D8': figure_D8, 'TA1': figure_TA1, 'TA2': figure_TA2,
           'TA3': figure_TA3}


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', type=Path, help='EXPECTED_APPENDIX_FIGURES.json to compare the new figures with')
    parser.add_argument('--only', help='comma-separated figure keys, for example A1,D3')
    parser.add_argument('--allow-other-versions', action='store_true',
                        help='build with library versions other than the pinned ones (appearance is then not guaranteed)')
    args = parser.parse_args()
    import PIL
    import fontTools
    import scipy
    import mic_50_90
    have = {'matplotlib': matplotlib.__version__, 'numpy': np.__version__, 'scipy': scipy.__version__,
            'PIL': PIL.__version__, 'fontTools': fontTools.version}
    if have != PINNED and not args.allow_other_versions:
        raise SystemExit(f'library versions {have} differ from the pinned {PINNED}; '
                         'install figures/requirements-figures.txt or pass --allow-other-versions')
    need(mic_50_90.__version__ == PACKAGE_VERSION, f'installed MIC-50-90 is {mic_50_90.__version__}, not {PACKAGE_VERSION}')
    font = Path(font_manager.findfont('Liberation Sans', fallback_to_default=False)).resolve()
    need(font.parent == (HERE / 'fonts').resolve(), f'font not taken from the bundled folder: {font}')
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    chosen = args.only.split(',') if args.only else list(FIGURES)
    for key in chosen:
        FIGURES[key]()
    receipt = {'status': 'passed', 'package_version': mic_50_90.__version__, 'versions': have,
               'fonts_sha256': {f.name: sha(f) for f in sorted((HERE / 'fonts').glob('*.ttf'))},
               'default_style_sha256': sha(HERE / 'style' / 'matplotlibrc-3.11.2-default'),
               'inputs_sha256': {name: sha(REPO / name) for name in sorted(INPUTS)},
               'figures': RECORD}
    (OUT / 'APPENDIX_FIGURE_BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=1, ensure_ascii=False) + '\n',
                                                            encoding='utf-8')
    result = {'figures': len(RECORD)}
    if args.check:
        expected = {row['figure']: row for row in json.loads(args.check.read_text(encoding='utf-8'))['figures']}
        differences = []
        for row in RECORD:
            old = expected.get(row['figure'])
            if old is None:
                differences.append(row['figure'] + ': not recorded')
                continue
            for ext in ('pdf', 'svg'):
                if old['file_sha256'][ext] != row['file_sha256'][ext]:
                    differences.append(f"{row['figure']}.{ext}: file differs")
            if old['png_pixel_sha256'] != row['png_pixel_sha256']:
                differences.append(f"{row['figure']}.png: pixels differ")
            if old['values'] != row['values']:
                differences.append(f"{row['figure']}: plotted values differ")
        result['identical_to_recorded_figures'] = not differences
        result['differences'] = differences
        print(json.dumps(result, indent=1))
        if differences:
            raise SystemExit(1)
    else:
        print(json.dumps(result))


def pixels(path):
    image = Image.open(path)
    return hashlib.sha256(np.asarray(image.convert('RGBA')).tobytes() + str(image.size).encode()).hexdigest()


if __name__ == '__main__':
    main()
