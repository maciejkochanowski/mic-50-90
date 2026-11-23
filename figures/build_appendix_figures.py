"""MIC-50-90 appendix and Technical Archive figures, drawn from the results in this repository.

Figures A.1-A.2, C.1-C.6, D.1-D.8 and TA1-TA3. Every value comes from the evaluation results and
example inputs of the repository, or is computed by the installed package; the script asserts the
values that the captions and texts print before drawing.

Appearance is fixed by figstyle.py, which all figures share: a full axes frame, black text, and
black, greys, blue, red and green as the only colours. The font files are bundled (fonts/),
matplotlib starts from its pristine defaults (style/), and the library versions are pinned in
requirements-figures.txt.

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

import figstyle as S
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, NullLocator
from PIL import Image

HERE = Path(__file__).resolve().parent
MM = 1 / 25.4
WIDTH = 140 * MM
BLACK, WHITE, GREY, BLUE, RED, GREEN = S.BLACK, S.WHITE, S.GREY, S.BLUE, S.RED, S.GREEN
MIC50, MIC90 = 'MIC$_{50}$', 'MIC$_{90}$'
PINNED = {'matplotlib': '3.11.2', 'numpy': '2.5.3', 'scipy': '1.18.0', 'PIL': '12.3.0', 'fontTools': '4.67.0'}
PACKAGE_VERSION = '2.0.0'  # version of MIC-50-90 whose results the figures show
S.setup('mic-50-90-appendix')

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


def load_local(name):
    path = HERE / 'data' / name
    INPUTS.add(f'figures/data/{name}')
    if path.suffix == '.csv':
        with path.open(newline='', encoding='utf-8') as handle:
            return list(csv.DictReader(handle))
    return json.loads(path.read_text(encoding='utf-8'))


def save(fig, name, values):
    """Check the text of the figure, then write three formats."""
    S.check(fig, name)
    fig.savefig(OUT / f'{name}.png', dpi=300, metadata={'Software': None})
    fig.savefig(OUT / f'{name}.pdf', metadata={'Creator': None, 'Producer': None, 'CreationDate': None})
    with open(OUT / f'{name}.svg', 'w', encoding='utf-8', newline='\n') as handle:
        fig.savefig(handle, format='svg', metadata={'Date': None, 'Creator': None})
    plt.close(fig)
    RECORD.append(dict(figure=name, values=json.loads(json.dumps(values)),
                       file_sha256={ext: sha(OUT / f'{name}.{ext}') for ext in ('png', 'pdf', 'svg')},
                       png_pixel_sha256=pixels(OUT / f'{name}.png')))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixels(path):
    image = Image.open(path)
    return hashlib.sha256(np.asarray(image.convert('RGBA')).tobytes() + str(image.size).encode()).hexdigest()


def note(ax, x, y, text, **kw):
    """Small label on a white ground, so that it stays legible over guides."""
    kw = {'fontsize': S.SMALL, 'ha': 'left', 'va': 'center', 'zorder': 5,
          'bbox': {'facecolor': WHITE, 'edgecolor': 'none', 'pad': 1}, **kw}
    return ax.text(x, y, text, **kw)


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
    fig = plt.figure(figsize=(WIDTH, 62 * MM)); ax = fig.add_axes([.1, .185, .88, .785])
    S.limit(ax, y=40)
    ax.text(2.1, 40.7, 'Limit: 40 pp', ha='left', va='bottom', fontsize=S.SMALL)
    ax.plot(ns, width, color=BLACK, lw=.8, zorder=3)
    places = {5: (6.6, 12.5), 10: (13.2, 18.5), 20: (26.5, 24), 50: (66, 29.5), 100: (132, 34.5)}
    for n, value in marks.items():
        S.dot(ax, n, width[n - 2], ms=4.2)
        ax.annotate(f'{S.N} = {n}: {value} pp', (n, width[n - 2]), places[n], ha='left', va='center', fontsize=S.SMALL,
                    arrowprops=dict(arrowstyle='-', color=BLACK, linewidth=.5, shrinkA=1, shrinkB=3, relpos=(0, .5)))
    ax.set_xscale('log')
    ax.set_xticks([2, 5, 10, 20, 50, 100, 200, 500], ['2', '5', '10', '20', '50', '100', '200', '500'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(1.85, 560)
    ax.set_ylim(-1.5, 45)
    ax.set_yticks([0, 10, 20, 30, 40]); ax.yaxis.set_minor_locator(MultipleLocator(5))
    ax.set_xlabel(f'Number of isolates, {S.N}')
    ax.set_ylabel('Width of the possible share (pp)')
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


def table_lines(ax, tables, selected, n, alpha):
    """Every table as a faint line of its cumulative shares; the selected tables in blue."""
    cumulative = np.unique(100 * np.cumsum(np.array(tables), axis=1) / n, axis=0)
    x = np.broadcast_to(np.arange(cumulative.shape[1]), cumulative.shape)
    ax.add_collection(LineCollection(np.stack([x, cumulative], axis=2), colors=[(.42, .42, .42, alpha)],
                                     linewidths=.4, zorder=2))
    for table in selected:
        ax.plot(np.arange(len(table)), 100 * np.cumsum(table) / n, color=BLUE, lw=1.1, marker='o', ms=3.2,
                mfc=BLUE, mec=BLUE, clip_on=False, zorder=4)
    S.legend(ax, [S.line_handle(GREY, f'{len(tables)} compatible tables', lw=.8),
                  Line2D([0], [0], color=BLUE, lw=1.1, marker='o', ms=3.2, mfc=BLUE, mec=BLUE,
                         label=f'{len(selected)} selected tables')], loc='lower right')


def figure_A2():
    """Compatible tables and the selected tables for ampicillin, before and after the count."""
    before = ampicillin_tables('ampicillin-67-summaries-conditional-population')
    after = ampicillin_tables('ampicillin-67-with-count-conditional-population')
    need(len(before[1]) == 7938 and len(after[1]) == 546, 'A.2 compatible tables')
    need(len(before[2]) == 5 and len(after[2]) == 4, 'A.2 selected tables')
    fig = plt.figure(figsize=(WIDTH, 76 * MM))
    axes = [fig.add_axes([.095, .145, .425, .775]), fig.add_axes([.555, .145, .425, .775])]
    for ax, (labels, tables, selected, n), title, alpha in (
            (axes[0], before, f'{MIC50}, {MIC90} and range', .06),
            (axes[1], after, 'With 59 of 67 at ≤0.25 mg/L', .16)):
        table_lines(ax, tables, selected, n, alpha)
        ax.set_title(title, loc='left')
        ax.set_xticks(range(len(labels)), labels)
        ax.set_xlim(-.25, len(labels) - .75)
        ax.set_ylim(40, 103); ax.set_yticks(range(40, 101, 10)); ax.yaxis.set_minor_locator(MultipleLocator(5))
        ax.set_xlabel('MIC category (mg/L)')
    S.dot(axes[1], 1, 100 * 59 / 67, marker='D', filled=False, ms=5.4, mew=1.0, zorder=6)
    axes[1].annotate('Published count:\n59 of 67', xy=(1.07, 100 * 59 / 67 - .9), xytext=(1.75, 76), fontsize=S.SMALL,
                     ha='left', va='center', linespacing=1.15,
                     arrowprops=dict(arrowstyle='-', color=BLACK, linewidth=.5, shrinkA=1, shrinkB=0))
    axes[1].tick_params(labelleft=False)
    axes[0].set_ylabel('Isolates at or below the category (%)')
    save(fig, 'Figure_A2', dict(compatible=[len(before[1]), len(after[1])], selected=[len(before[2]), len(after[2])]))


# ---------------------------------------------------------------- Appendix C
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
    labels = ['≤0.06 mg/L', '>0.06 to 2 mg/L', '>2 mg/L']
    fig = plt.figure(figsize=(WIDTH, 70 * MM)); ax = fig.add_axes([.315, .165, .39, .755])
    ticks, isolates, shares = [], [], []
    for row, label in enumerate(labels):
        ax.text(-.79, row * 4 + 1, label, transform=ax.get_yaxis_transform(), ha='left', va='center',
                fontweight='bold', clip_on=False)
        for i, year in enumerate(years):
            n, counts = groups[year]
            share, y = 100 * counts[row] / n, row * 4 + i
            S.dot(ax, share, y)
            ticks.append(y); isolates.append((y, f'{counts[row]} of {n}')); shares.append((y, f'{share:.2f}%'))
    S.guides(ax, ticks)
    for y in (3, 7):
        ax.axhline(y, color=BLACK, lw=.5)
    ax.set_yticks(ticks, [str(year) for year in years] * 3)
    S.column(ax, 1.3, isolates, 'Isolates', -1.1)
    S.column(ax, 1.52, shares, 'Share', -1.1)
    ax.set_xlim(0, 100); ax.set_xticks(range(0, 101, 20)); ax.xaxis.set_minor_locator(MultipleLocator(10))
    ax.set_ylim(11, -1)
    ax.set_xlabel('Isolates in the MIC range (%)')
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
    fig = plt.figure(figsize=(WIDTH, 84 * MM)); ax = fig.add_axes([.105, .13, .475, .655])
    for y, (b, a) in enumerate(zip(before, after)):
        S.hspan(ax, b['count_lower'], b['count_upper'], y - .27, BLACK)
        S.hspan(ax, a['count_lower'], a['count_upper'], y, BLUE)
        S.dot(ax, fewest[y], y + .27, color=BLUE, filled=False, ms=6.4, zorder=4)
        S.dot(ax, most[y], y + .27, marker='D', color=BLUE, ms=3.2, zorder=5)
    S.guides(ax, [.5, 1.5, 2.5, 3.5])
    for x, header, values in ((1.2, 'Summaries', [f"{b['count_lower']}–{b['count_upper']}" for b in before]),
                              (1.42, 'With count', [f"{a['count_lower']}–{a['count_upper']}" for a in after]),
                              (1.6, 'Fewest', [str(v) for v in fewest]), (1.76, 'Most', [str(v) for v in most])):
        S.column(ax, x, list(enumerate(values)), header, -.67)
    ax.set_yticks(range(5), labels)
    ax.set_xlim(0, 67); ax.set_xticks([0, 10, 20, 30, 40, 50, 60, 67]); ax.xaxis.set_minor_locator(MultipleLocator(5))
    ax.set_ylim(4.6, -.6)
    ax.set_ylabel('MIC category (mg/L)')
    ax.set_xlabel('Isolates in the category (of 67)')
    S.legend(fig, [S.interval_handle(BLACK, f'{MIC50}, {MIC90} and range'),
                   S.interval_handle(BLUE, 'With 59 isolates at ≤0.25 mg/L'),
                   S.mark_handle('o', 'Table with the fewest isolates in 0.5', color=BLUE, filled=False, ms=6.4),
                   S.mark_handle('D', 'Table with the most isolates in 0.5', color=BLUE, ms=3.2)],
             loc='upper left', bbox_to_anchor=(.095, .995), ncol=2, columnspacing=2.2)
    save(fig, 'Figure_C2', dict(before=[[b['count_lower'], b['count_upper']] for b in before],
                                after=[[a['count_lower'], a['count_upper']] for a in after]))


def figure_C3():
    """Seconds per calculation of the same 95% endpoints: selected tables against all tables."""
    summary = load('evaluation/results/endpoint_selection/summary.json')['reports']
    before = ampicillin_tables('ampicillin-67-summaries-conditional-population')
    after = ampicillin_tables('ampicillin-67-with-count-conditional-population')
    rows = []
    for key, tables, colour, label in (('summaries', before, BLACK, 'Summaries'), ('with count', after, BLUE, 'With count')):
        report = summary[key]
        need(report['compatible_tables'] == len(tables[1]), f'C.3 {key} tables')
        low, high = report['category_05']['lower_pp'], report['category_05']['upper_pp']
        rows.append((f'{label}\nbounds {low:.3f}–{high:.2f}%', report['median_seconds_selected'],
                     report['median_seconds_exhaustive'], len(tables[2]), len(tables[1]), colour))
    fig = plt.figure(figsize=(WIDTH, 56 * MM)); ax = fig.add_axes([.245, .215, .735, .625])
    for y, (label, fast, slow, selected, total, colour) in enumerate(rows):
        ax.plot([fast, slow], [y, y], color=colour, lw=.7, zorder=2)
        S.dot(ax, fast, y, color=colour, ms=5)
        S.dot(ax, slow, y, color=colour, filled=False, ms=5)
        for x, time, count in ((fast, f'{fast:.3f} s', f'{selected} tables'), (slow, f'{slow:.3f} s', f'{total} tables')):
            ax.annotate(time, (x, y), (0, 7), textcoords='offset points', ha='center', va='bottom', fontsize=S.SMALL)
            ax.annotate(count, (x, y), (0, -7), textcoords='offset points', ha='center', va='top', fontsize=S.SMALL)
    ax.set_yticks(range(2), [r[0] for r in rows], linespacing=1.2)
    ax.set_xscale('log')
    ax.set_xticks([.05, .1, .2, .5, 1, 2, 5], ['0.05', '0.1', '0.2', '0.5', '1', '2', '5'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(.035, 8)
    ax.set_ylim(1.62, -.62)
    ax.set_xlabel('Time to compute the same 95% bounds (s)')
    S.legend(fig, [S.mark_handle('o', 'Selected tables', ms=5), S.mark_handle('o', 'All compatible tables', filled=False, ms=5)],
             loc='upper center', bbox_to_anchor=(.6125, .995), ncol=2)
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
    fig = plt.figure(figsize=(WIDTH, 48 * MM)); ax = fig.add_axes([.215, .25, .5, .65])
    ax.set_xscale('log', base=2); ax.set_xlim(.25, 16)
    ax.set_xticks([.25, .5, 1, 2, 4, 8, 16], ['0.25', '0.5', '1', '2', '4', '8', '16'])
    ax.xaxis.set_minor_locator(NullLocator())
    S.guides(ax, [0, 1])
    S.criterion(ax, x=2)
    note(ax, 2.1, -.45, 'Threshold 2 mg/L', bbox=None)
    ax.plot([.25, 4], [0, 0], color=BLACK, lw=1.2, zorder=3)
    ax.plot(.275, 0, '<', ms=4.5, mfc=BLACK, mec=BLACK, zorder=4)
    S.dot(ax, 4, 0)
    ax.plot([4, 8], [1, 1], color=BLACK, lw=1.2, zorder=3)
    S.dot(ax, 4, 1, filled=False); S.dot(ax, 8, 1)
    ax.set_yticks([0, 1], ['33 isolates\nMIC ≤4 mg/L', '34 isolates\n4 < MIC ≤8 mg/L'], linespacing=1.2)
    S.column(ax, 1.03, [(0, 'possibly above 2 mg/L'), (1, 'certainly above 2 mg/L')], ha='left')
    ax.set_ylim(1.6, -.75)
    ax.set_xlabel('MIC (mg/L)')
    save(fig, 'Figure_C4', dict(recorded=[33, 34], above_2=[34, 67], percent=[round(low, 2), 100]))


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
    labels = ['≤0.06 mg/L', '>0.06 to 2 mg/L', '>2 mg/L', '>0.06 mg/L\n(two ranges merged)']
    fig = plt.figure(figsize=(WIDTH, 74 * MM)); ax = fig.add_axes([.215, .155, .415, .665])
    for row in range(3):
        S.hspan(ax, *one[row], row - .17, BLACK)
        S.hspan(ax, *two[row], row + .17, BLUE)
    S.hspan(ax, *merged, 3.4, BLACK)
    S.guides(ax, [.5, 1.5])
    ax.axhline(2.7, color=BLACK, lw=.5)
    ax.set_yticks([0, 1, 2, 3.4], labels, linespacing=1.2)
    S.column(ax, 1.36, [(row, f'{one[row][0]:.2f}–{one[row][1]:.2f}') for row in range(3)] +
             [(3.4, f'{merged[0]:.2f}–{merged[1]:.2f}')], 'One count', -.67)
    S.column(ax, 1.72, [(row, f'{two[row][0]:.2f}–{two[row][1]:.2f}') for row in range(3)], 'Two counts', -.67)
    ax.set_xlim(0, 100); ax.set_xticks(range(0, 101, 20)); ax.xaxis.set_minor_locator(MultipleLocator(10))
    ax.set_ylim(4.1, -.6)
    ax.set_xlabel('Population share, 95% interval (%)')
    S.legend(fig, [S.interval_handle(BLACK, 'Count above 0.06 mg/L'),
                   S.interval_handle(BLUE, 'Counts above 0.06 and 2 mg/L')],
             loc='upper left', bbox_to_anchor=(.2, .995), ncol=2)
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
    fig = plt.figure(figsize=(WIDTH, 64 * MM))
    a, b = fig.add_axes([.085, .185, .445, .7]), fig.add_axes([.7, .185, .28, .7])
    x = np.arange(4)
    for offset, values, face, edge, label in ((-.17, counts[0], WHITE, BLACK, 'Table A'), (.17, counts[1], BLUE, BLUE, 'Table B')):
        a.bar(x + offset, values, width=.3, facecolor=face, edgecolor=edge, linewidth=.7, label=label, zorder=2)
        for i, v in enumerate(values):
            a.text(i + offset, v + .35, str(v), ha='center', va='bottom', fontsize=S.SMALL)
    a.set_ylim(0, 19); a.set_yticks([0, 4, 8, 12, 16]); a.yaxis.set_minor_locator(MultipleLocator(2))
    a.set_xticks(x, ['0.25', '1', '2', '32']); a.tick_params(axis='x', length=0)
    a.set_xlim(-.6, 3.6)
    a.set_ylabel('Isolates'); a.set_xlabel('Support point (mg/L)')
    a.legend(loc='upper right')
    S.guides(b, [0, 1])
    S.criterion(b, x=5)
    note(b, 5.15, -.45, '5%', bbox=None)
    for y, k, colour, filled in ((0, counts[0][3], BLACK, False), (1, counts[1][3], BLUE, True)):
        v = 100 * k / 32
        S.dot(b, v, y, color=colour, filled=filled, ms=5)
        b.annotate(f'{v:g}%', (v, y), (0, 7), textcoords='offset points', ha='center', va='bottom', fontsize=S.SMALL)
    b.set_xlim(0, 8); b.set_xticks([0, 2, 4, 6, 8]); b.xaxis.set_minor_locator(MultipleLocator(1))
    b.set_ylim(1.6, -.75); b.set_yticks([0, 1], ['Table A', 'Table B'])
    b.set_xlabel('Share with MIC >8 mg/L (%)')
    S.panel(a, 'a', x=-.17); S.panel(b, 'b', x=-.3)
    save(fig, 'Figure_C6', dict(A=counts[0], B=counts[1]))


# ---------------------------------------------------------------- Appendix D: twenty development cohorts
GROUPS = (('FDA', 'Dogs, FDA animal-pathogen data'), ('NORM', 'People, NORM 2024 streptococci'))


def italic(name):
    return r'$\mathit{' + name.replace(' ', r'\,') + '}$'


def cohort_label(row):
    organism = row['organism']
    if organism.startswith('Streptococcus '):
        organism = 'S. ' + organism.split(' ', 1)[1]
    organism = italic('Klebsiella') + ' spp.' if organism == 'Klebsiella spp' else italic(organism)
    drug = ' '.join(word if len(word) == 1 else word.lower() for word in row['drug'].replace('/', '-').split(' '))
    return f"{organism}, {drug}, {S.N} = {row['n']}"


def cohort_layout():
    """Rows of the twenty cohorts: two sources, larger collections first."""
    cohorts = load('evaluation/data/population_cohorts.json')
    need(len(cohorts) == 20, 'twenty development cohorts')
    rows, headers, y = [], [], 0.
    for key, title in GROUPS:
        members = [c for c in cohorts if (key == 'NORM') == ('NORM' in c['source'])]
        members.sort(key=lambda c: (-c['n'], [-int(part) for part in c['case'].split('-')[1:]]))
        headers.append((y - 1., title))
        for member in members:
            rows.append((y, member['case'], cohort_label(member)))
            y += 1
        y += 1.5
    return rows, headers


def cohort_axes(right=.978, height_mm=116):
    """Dot chart with one row for each cohort and a bold header for each source."""
    fig = plt.figure(figsize=(WIDTH, height_mm * MM)); ax = fig.add_axes([.515, .105, right - .515, .835])
    rows, headers = cohort_layout()
    ax.set_yticks([y for y, _, _ in rows], [label for _, _, label in rows], fontsize=S.SMALL)
    for y, title in headers:
        ax.text(-.02, y, title, transform=ax.get_yaxis_transform(), ha='right', va='center', fontweight='bold',
                clip_on=False)
    S.guides(ax, [y for y, _, _ in rows])
    ax.set_ylim(rows[-1][0] + .75, headers[0][0] - .65)
    return fig, ax, rows


def legend_above(fig, ax, handles, **kw):
    """Legend in the top margin, centred on the frame."""
    box = ax.get_position()
    kw = {'loc': 'upper center', 'bbox_to_anchor': ((box.x0 + box.x1) / 2, .998), 'ncol': len(handles), **kw}
    return S.legend(fig, handles, **kw)


def figure_D1():
    """Coverage of the 95% population bounds in the coverage simulation, by cohort."""
    summary = load('evaluation/results/coverage/summary.json')
    coverage = {c['case']: c for c in summary['cohorts']}
    fig, ax, rows = cohort_axes()
    for y, case, _ in rows:
        S.dot(ax, 100 * coverage[case]['bonferroni']['coverage'], y - .17, ms=4.2)
        S.dot(ax, 100 * coverage[case]['range-calibrated']['coverage'], y + .17, marker='D', filled=False, ms=3.8)
    lowest = min(min(c['bonferroni']['coverage'], c['range-calibrated']['coverage']) for c in coverage.values())
    need(lowest >= .99, 'D.1 axis starts at 99%')
    ax.set_xlim(99, 100.04)
    ax.set_xticks([99, 99.2, 99.4, 99.6, 99.8, 100], ['99.0', '99.2', '99.4', '99.6', '99.8', '100.0'])
    ax.xaxis.set_minor_locator(MultipleLocator(.1))
    ax.set_xlabel('Reports with every share inside the 95% bounds (%)', loc='right')
    legend_above(fig, ax, [S.mark_handle('o', 'Bonferroni', ms=4.2),
                           S.mark_handle('D', 'Range-calibrated', filled=False, ms=3.8)])
    save(fig, 'Figure_D1', {case: [coverage[case]['bonferroni']['coverage'], coverage[case]['range-calibrated']['coverage']]
                            for _, case, _ in rows})


def figure_D2():
    """Mean width of the 95% Bonferroni intervals: complete table against MIC50, MIC90 and one count."""
    summary = load('evaluation/results/complete_tables/summary.json')
    cohorts = {c['case']: c['bonferroni'] for c in summary['cohorts']}
    median_ratio = summary['summary']['bonferroni']['median_width_ratio']
    need(f'{median_ratio:.1f}' == '3.7', 'D.2 median ratio 3.7')
    fig, ax, rows = cohort_axes(right=.905)
    for y, case, _ in rows:
        complete, report = cohorts[case]['complete']['mean_width_pp'], cohorts[case]['report']['mean_width_pp']
        ax.plot([complete, report], [y, y], color=BLACK, lw=.6, zorder=2)
        S.dot(ax, complete, y, ms=4.2)
        S.dot(ax, report, y, filled=False, ms=4.2)
    S.column(ax, 1.14, [(y, f"{cohorts[case]['width_ratio']:.1f}") for y, case, _ in rows], 'Ratio', rows[0][0] - .7)
    ax.set_xlim(0, 80); ax.set_xticks(range(0, 81, 20)); ax.xaxis.set_minor_locator(MultipleLocator(10))
    ax.set_xlabel('Mean width of the 95% intervals (pp)')
    legend_above(fig, ax, [S.mark_handle('o', 'Complete table', ms=4.2),
                           S.mark_handle('o', f'{MIC50}, {MIC90} and one count', filled=False, ms=4.2)],
                 bbox_to_anchor=(.64, .998))
    save(fig, 'Figure_D2', {case: [cohorts[case]['complete']['mean_width_pp'], cohorts[case]['report']['mean_width_pp']]
                            for _, case, _ in rows})


def figure_D3():
    """Seconds per cohort for the four constructions."""
    summary = load('evaluation/results/population/summary.json')
    budget = summary['settings']['budget_seconds']
    need(round(budget) == 120, 'D.3 budget 120 s')
    seconds = {(c['case'], c['method']): c['seconds'] for c in summary['cohorts']}
    marks = {'bonferroni': ('o', True, -.18, 'Bonferroni'), 'range-calibrated': ('D', True, .18, 'Range-calibrated'),
             'joint-exact': ('s', False, -.18, 'Joint-exact'), 'range-hunter': ('^', False, .18, 'Range-hunter')}
    size = {'o': 4.2, 'D': 3.7, 's': 3.9, '^': 4.3}
    fig, ax, rows = cohort_axes()
    S.limit(ax, x=budget)
    note(ax, budget * .86, rows[0][0] - 1., f'{budget:.0f} s budget', ha='right', bbox=None)
    for y, case, _ in rows:
        for method, (marker, filled, dy, _) in marks.items():
            S.dot(ax, seconds[(case, method)], y + dy, marker=marker, filled=filled, ms=size[marker])
    ax.set_xscale('log')
    ax.set_xticks([.01, .1, 1, 10, 100], ['0.01', '0.1', '1', '10', '100'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xlim(.005, 300)
    ax.set_xlabel('Time per cohort (s)')
    legend_above(fig, ax, [S.mark_handle(marker, label, filled=filled, ms=size[marker])
                           for marker, filled, _, label in marks.values()],
                 bbox_to_anchor=(.5, .998), columnspacing=1.4, handletextpad=.3)
    save(fig, 'Figure_D3', {f'{case}|{method}': seconds[(case, method)] for _, case, _ in rows for method in marks})


def figure_D4():
    """Fifteen deterministic test reports with uniform profiles: seconds to confirm every endpoint."""
    probes = load('evaluation/results/controlled_reports/records.json')['scaling_probes']
    need(len(probes) == 15 and all(p['precision_reached'] for p in probes), 'D.4 fifteen confirmed probes')
    sizes = [(200, 5), (200, 8), (200, 16), (1000, 5), (1000, 8)]
    seconds = {(p['n'], p['k'], p['information']): p['seconds'] for p in probes}
    marks = (('summaries', 'o', True, 4.4, 'Summaries alone'), ('interior', 'D', False, 4.0, 'With one interior count'),
             ('two_counts', 's', True, 4.0, 'With two cumulative counts'))
    fig = plt.figure(figsize=(WIDTH, 58 * MM)); ax = fig.add_axes([.19, .205, .79, .665])
    S.guides(ax, range(len(sizes)))
    for y, (n, k) in enumerate(sizes):
        for information, marker, filled, ms, _ in marks[::-1]:
            S.dot(ax, seconds[(n, k, information)], y, marker=marker, filled=filled, ms=ms)
    ax.set_yticks(range(len(sizes)), [f'{S.N} = {n}, {S.K} = {k}' for n, k in sizes])
    ax.set_xlim(0, .32)
    ax.set_xticks(np.arange(0, .31, .05), [f'{v:.2f}' for v in np.arange(0, .31, .05)])
    ax.xaxis.set_minor_locator(MultipleLocator(.01))
    ax.set_ylim(len(sizes) - .4, -.6)
    ax.set_xlabel('Time to confirm every population bound (s)')
    legend_above(fig, ax, [S.mark_handle(marker, label, filled=filled, ms=ms) for _, marker, filled, ms, label in marks],
                 bbox_to_anchor=(.5, .998), columnspacing=1.4, handletextpad=.3)
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
    fig = plt.figure(figsize=(WIDTH, 84 * MM)); ax = fig.add_axes([.415, .145, .565, .765])
    S.criterion(ax, x=95)
    lowest = {}
    for row, (title, configurations, detail) in enumerate(families):
        for offset, method, filled in ((-.25, 'bonferroni', True), (.25, 'range-calibrated', False)):
            values = np.array([100 * c[method]['covered'] / c[method]['replicates'] for c in configurations])
            y = row * 1.45 + offset
            spread = jitter(len(values), row * 2 + (offset > 0)) * .13
            if filled:
                ax.scatter(values, y + spread, s=5, color=BLACK, alpha=.45, linewidths=0, zorder=2)
            else:
                ax.scatter(values, y + spread, s=8, facecolors='none', edgecolors=BLACK, alpha=.5, linewidths=.5, zorder=2)
            ax.plot([values.min()] * 2, [y - .2, y + .2], color=BLACK, lw=1.3, zorder=3)
            lowest[f'{title}|{method}'] = float(values.min())
        if row:
            ax.axhline(row * 1.45 - .725, color=S.GREY_LIGHT, lw=.5, ls=S.DOTS, zorder=0)
    note(ax, 95.08, -.78, 'Nominal 95%', bbox=None)
    ax.set_yticks([row * 1.45 for row in range(4)], [f'{title}\n{detail}' for title, _, detail in families], linespacing=1.25)
    ax.set_xlim(94.7, 100.3)
    ax.set_xticks(range(95, 101)); ax.xaxis.set_minor_locator(MultipleLocator(.5))
    ax.set_ylim(3 * 1.45 + .6, -1.0)
    ax.set_xlabel('Reports with every share inside the 95% bounds (%)', loc='right')
    legend_above(fig, ax, [S.mark_handle('o', 'Bonferroni', ms=3.2), S.mark_handle('o', 'Range-calibrated', filled=False, ms=3.6, mew=.6),
                           S.mark_handle('|', 'Lowest configuration', ms=8, mew=1.3)],
                 bbox_to_anchor=(.5, .998), columnspacing=1.4, handletextpad=.3)
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
    fig = plt.figure(figsize=(WIDTH, 70 * MM)); ax = fig.add_axes([.095, .165, .885, .805])
    ax.vlines(x, lower, upper, color=S.GREY_LIGHT, linewidth=.55, zorder=2)
    ax.step(x, truth, where='mid', color=BLACK, linewidth=1.1, zorder=3)
    S.legend(ax, [Line2D([0], [0], ls='none', marker='|', ms=9, mew=1.4, color=S.GREY_LIGHT, label='95% calibrated bounds'),
                  S.line_handle(BLACK, 'Observed share in the held-out isolates', lw=1.1)], loc='upper left')
    ax.text(.985, .045, f'{covered} of {len(rows)} shares inside their bounds', transform=ax.transAxes, ha='right',
            va='center', fontsize=S.SMALL)
    ax.set_xlim(-10, len(rows) + 11)
    ax.set_xticks([1, 250, 500, 750, 1000, 1250, len(rows)])
    ax.set_ylim(-2, 102)
    ax.set_yticks(range(0, 101, 20)); ax.yaxis.set_minor_locator(MultipleLocator(10))
    ax.set_xlabel('Shares left open by the summaries, sorted by the observed share')
    ax.set_ylabel('Share above the threshold (%)')
    save(fig, 'Figure_D6', dict(shares=len(rows), covered=covered))


def figure_D7():
    """Study-unit calibration with synthetic units."""
    settings = {s['setting']: s for s in load('evaluation/results/external_calibration/summary.json')['synthetic']['settings']}
    tests = [('SU1', 'Exchangeable with the calibration units'), ('SU2|weight=0.05', 'Non-wild-type share raised by 0.05'),
             ('SU2|weight=0.1', 'Non-wild-type share raised by 0.1'), ('SU2|weight=0.2', 'Non-wild-type share raised by 0.2'),
             ('SU2|shift_all=1', 'Every MIC one dilution higher'), ('SU3', 'Own wild-type center for each test unit')]
    c = r'$\mathit{c}$'
    marks = [('c=20|M=19', 'o', True, -.27, f'{c} = 20, 19 units'), ('c=20|M=39', 'D', True, -.09, f'{c} = 20, 39 units'),
             ('c=100|M=19', 'o', False, .09, f'{c} = 100, 19 units'), ('c=100|M=39', 'D', False, .27, f'{c} = 100, 39 units')]
    for key, *_ in marks:
        need(all(settings[key]['tests'][t]['test_units'] == 20000 for t, _ in tests), f'D.7 {key} test units')
    fig = plt.figure(figsize=(WIDTH, 76 * MM)); ax = fig.add_axes([.365, .16, .615, .74])
    S.criterion(ax, x=95)
    note(ax, 94.85, -.5, 'Nominal 95%', ha='right', bbox=None)
    S.guides(ax, [y + .5 for y in range(len(tests) - 1)])
    for y, (test, _) in enumerate(tests):
        for key, marker, filled, dy, _ in marks:
            S.dot(ax, 100 * settings[key]['tests'][test]['coverage'], y + dy, marker=marker, filled=filled,
                  ms=4.2 if marker == 'o' else 3.7)
    ax.set_yticks(range(len(tests)), [label for _, label in tests])
    ax.set_xlim(86, 100.5)
    ax.set_xticks(range(86, 101, 2)); ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.set_ylim(len(tests) - .4, -.75)
    ax.set_xlabel('Test units with every share inside the 95% bounds (%)')
    legend_above(fig, ax, [S.mark_handle(marker, label, filled=filled, ms=4.2 if marker == 'o' else 3.7)
                           for _, marker, filled, _, label in marks],
                 bbox_to_anchor=(.5, .998), columnspacing=1.2, handletextpad=.3)
    save(fig, 'Figure_D7', {f'{key}|{test}': settings[key]['tests'][test]['coverage'] for key, *_ in marks for test, _ in tests})


def figure_D8():
    """Sixty drug cohorts and three share criteria: counts a laboratory has to disclose."""
    tasks = load('evaluation/results/sufficient_reporting/tasks.csv')
    need(len(tasks) == 180 and all(t['recipient_sufficient'] == 'True' for t in tasks), 'D.8 180 sufficient tasks')
    groups = []
    for fraction, label in (('0.05', 'Share below 5%'), ('0.1', 'Share below 10%'), ('0.2', 'Share below 20%'), (None, 'All three questions')):
        chosen = [t for t in tasks if fraction is None or float(t['fraction']) == float(fraction)]
        groups.append((label, len(chosen), sum(int(t['answers']) for t in chosen),
                       sum(int(t['direct_fields']) for t in chosen), sum(int(t['minimal_fields']) for t in chosen)))
    need(groups[-1][2:] == (1809, 405, 115), 'D.8 totals 1809 answers, 405 and 115 counts')
    fig = plt.figure(figsize=(WIDTH, 62 * MM)); ax = fig.add_axes([.27, .2, .71, .765])
    S.guides(ax, range(4)); ax.axhline(2.5, color=BLACK, lw=.5)
    for y, (label, count, answers, direct, minimal) in enumerate(groups):
        if direct == 0:
            S.dot(ax, 0, y, color=BLUE, ms=5)
            note(ax, 10, y, '0: the summaries settle every answer')
            continue
        ax.plot([minimal, direct], [y, y], color=BLACK, lw=.7, zorder=2)
        S.dot(ax, direct, y, filled=False, ms=5)
        S.dot(ax, minimal, y, color=BLUE, ms=5)
        note(ax, direct + 9, y, str(direct))
        note(ax, minimal - 9, y, str(minimal), ha='right')
    ax.set_yticks(range(4), [f'{g[0]}\n{g[1]} tasks, {g[2]} answers' for g in groups], linespacing=1.2)
    ax.set_xlim(-16, 445)
    ax.set_xticks(range(0, 401, 100)); ax.xaxis.set_minor_locator(MultipleLocator(50))
    ax.set_ylim(3.6, -.6)
    ax.set_xlabel('Counts the laboratory has to disclose')
    S.legend(ax, [S.mark_handle('o', 'Every count left open by the summaries', filled=False, ms=5),
                  S.mark_handle('o', 'Smallest sufficient set', color=BLUE, ms=5)],
             loc='center right', bbox_to_anchor=(1, .47))
    save(fig, 'Figure_D8', {g[0].lower(): list(g[1:]) for g in groups})


# ---------------------------------------------------------------- Technical Archive
def figure_TA1():
    """Width between the ceiling ranks as a fraction of n, n = 10..100."""
    ns = np.arange(10, 101)
    width = np.array([max(ceiling_rank(n, .9) - ceiling_rank(n, .5) - 1, 0) / n for n in ns])
    need(f'{width[10]:.3f}' == '0.350' and f'{width[11]:.3f}' == '0.333', 'TA1 n = 20, 21')
    fig = plt.figure(figsize=(WIDTH, 62 * MM)); ax = fig.add_axes([.135, .185, .845, .785])
    S.limit(ax, y=.40)
    ax.text(100, .4025, 'Limit: 0.40', ha='right', va='bottom', fontsize=S.SMALL)
    ax.plot(ns, width, color=BLACK, lw=.8, marker='o', ms=1.8, mfc=BLACK, mec=BLACK, zorder=3)
    for n, text, y in ((20, f'{S.N} = 20: 0.350', .322), (21, f'{S.N} = 21: 0.333', .306)):
        S.dot(ax, n, width[n - 10], ms=4.6)
        ax.annotate(text, xy=(n, width[n - 10]), xytext=(27, y), fontsize=S.SMALL, ha='left', va='center',
                    arrowprops=dict(arrowstyle='-', color=BLACK, linewidth=.5, shrinkA=1, shrinkB=3))
    ax.set_xlim(8, 102)
    ax.set_xticks(range(10, 101, 10)); ax.xaxis.set_minor_locator(MultipleLocator(5))
    ax.set_ylim(.26, .42)
    ax.set_yticks([.26, .30, .34, .38, .42], ['0.26', '0.30', '0.34', '0.38', '0.42'])
    ax.yaxis.set_minor_locator(MultipleLocator(.02))
    ax.set_xlabel(f'Number of isolates, {S.N}')
    ax.set_ylabel(f'Width of the possible share\n(fraction of {S.N})', linespacing=1.2)
    save(fig, 'Figure_TA1', {'20': round(float(width[10]), 3), '21': round(float(width[11]), 3)})


def figure_TA2():
    """The canonical additional-count calculation, n = 100."""
    n = 100
    low, high = ceiling_rank(n, .5), ceiling_rank(n, .9) - 1
    need((low, high) == (50, 89), 'TA2 L = 50 and U = 89')
    gap = (high - low) / n
    rows = [('One target', gap, gap), ('Two targets', 2 * gap, gap)]
    fig = plt.figure(figsize=(WIDTH, 48 * MM)); ax = fig.add_axes([.135, .25, .55, .525])
    S.guides(ax, [.5])
    for y, (label, alone, counted) in enumerate(rows):
        S.dot(ax, alone, y - .18, ms=5)
        S.dot(ax, counted, y + .18, color=BLUE, ms=5)
    S.column(ax, 1.2, [(y, f'{alone:.2f}') for y, (_, alone, _) in enumerate(rows)], 'Summaries', -.62)
    S.column(ax, 1.44, [(y, f'{counted:.2f}') for y, (_, _, counted) in enumerate(rows)], 'With count', -.62)
    ax.set_yticks(range(2), [r[0] for r in rows])
    ax.set_xlim(0, 1)
    ax.set_xticks(np.arange(0, 1.01, .2), [f'{v:.1f}' for v in np.arange(0, 1.01, .2)])
    ax.xaxis.set_minor_locator(MultipleLocator(.1))
    ax.set_ylim(1.55, -.55)
    ax.set_xlabel(f'Sum of worst-case widths (fraction of {S.N}), {S.N} = 100')
    S.legend(fig, [S.mark_handle('o', 'Summaries alone', ms=5), S.mark_handle('o', 'With one count between the targets', color=BLUE, ms=5)],
             loc='upper left', bbox_to_anchor=(.12, .995), ncol=2)
    save(fig, 'Figure_TA2', dict(L=low, U=high, gap=gap))


def figure_TA3():
    """Four-observation counterexample: original bands, a restricted transport ball and added counts."""
    # Exact constructed fractions of the Technical Archive table (tails after categories 1 and 2).
    cuts = [('First cut: tail above category 1, returned count 3 of 4', .75,
             [((.75, 1.0), '75–100%'), ((.75, .75), '75% only'), ((.75, .75), '75% only')]),
            ('Second cut: tail above category 2, true count 1 of 4', .25,
             [((.25, .50), '25–50%'), ((.50, .50), '50% only'), ((.25, .50), '25–50%')])]
    labels = ['Original bands', 'Ball restricted\nto the count', 'Original bands,\ncount added']
    colours = [BLACK, RED, BLUE]
    for _, truth, bands in cuts:
        need(bands[0][0][0] <= truth <= bands[0][0][1] and bands[2][0][0] <= truth <= bands[2][0][1], 'TA3 truths inside')
    need(not cuts[1][2][1][0][0] <= cuts[1][1] <= cuts[1][2][1][0][1], 'TA3 restricted ball excludes the truth')
    fig = plt.figure(figsize=(WIDTH, 88 * MM))
    axes = [fig.add_axes([.2, .6, .6, .3]), fig.add_axes([.2, .125, .6, .3])]
    for ax, (title, truth, bands) in zip(axes, cuts):
        ax.set_title(title, loc='left')
        ax.axvline(100 * truth, color=GREEN, lw=1.0, zorder=1)
        S.guides(ax, [.5, 1.5])
        for y, ((low, high), text) in enumerate(bands):
            S.hspan(ax, 100 * low, 100 * high, y, colours[y], lw=1.6, cap=4.5)
        S.column(ax, 1.03, [(y, text) for y, (_, text) in enumerate(bands)], ha='left')
        ax.set_yticks(range(3), labels, linespacing=1.15)
        ax.set_ylim(2.6, -.6)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100])
    axes[0].tick_params(labelbottom=False)
    S.legend(axes[0], [S.line_handle(GREEN, 'True share', lw=1.0)], loc='center left', bbox_to_anchor=(.02, .5))
    axes[1].set_xlabel('Share of the 4 observations in the tail (%)')
    save(fig, 'Figure_TA3', dict(truths=[c[1] for c in cuts]))


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
    OUT = args.out.resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    chosen = args.only.split(',') if args.only else list(FIGURES)
    for key in chosen:
        FIGURES[key]()
    receipt = {'status': 'passed', 'package_version': mic_50_90.__version__, 'versions': have,
               'rule': S.RULE, 'palette': S.PALETTE, 'style_sha256': sha(HERE / 'figstyle.py'),
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


if __name__ == '__main__':
    main()
