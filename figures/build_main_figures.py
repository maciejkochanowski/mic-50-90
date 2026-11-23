"""MIC-50-90 SoftwareX figures: six single-graph main figures and six single-graph
supplementary figures, drawn from the numeric records in data/ and efsa/ and from the
reporting evaluation (../evaluation/results/sufficient_reporting/tasks.csv).

Every plotted value is asserted against its source file before drawing. No program
analysis is rerun here. The ampicillin values of Figures 3 and 4 and Supplementary
Figure S2 come from a rerun with the installed package (data/ampicillin_rerun.json,
written by rerun_ampicillin.py); Figure 4 also enumerates the compatible tables with
its own calculation and compares the selected tables with the rerun. The Figure 6 values
are checked against the replay of the public EFSA data (efsa/EFSA_REPLAY_SUMMARY.json).

Appearance is fixed by figstyle.py, which all figures share: a full axes frame, black text,
and black, greys, blue, red and green as the only colours. The font files are bundled
(fonts/) and the library versions are pinned in requirements-figures.txt.

Usage:  python build_main_figures.py --out <empty folder> [--check EXPECTED_MAIN_FIGURES.json]
With --check the script compares the new files with the recorded figures and fails on any
difference: PNG and TIFF are compared by decoded pixels, SVG and PDF byte for byte.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

import figstyle as S
import matplotlib.pyplot as plt
import numpy as np
import matplotlib
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.ticker import MultipleLocator, NullLocator
from PIL import Image

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
EFSA = HERE / 'efsa'
BLACK, WHITE, GREY, BLUE, RED, GREEN = S.BLACK, S.WHITE, S.GREY, S.BLUE, S.RED, S.GREEN
PINNED = {'matplotlib': '3.11.2', 'numpy': '2.5.3', 'PIL': '12.3.0', 'fontTools': '4.67.0'}
PACKAGE_VERSION = '2.0.0'  # version of MIC-50-90 whose results the figures show
S.setup('mic-50-90')

OUT: Path
RECORD: list = []
EXTRA_INPUTS: list = []


def need(cond, msg):
    if not cond:
        raise AssertionError(msg)


def rows(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pixels(p):
    """SHA-256 of the decoded image (size and RGB values), independent of file compression."""
    with Image.open(p) as im:
        rgb = im.convert('RGB')
        return hashlib.sha256(repr(rgb.size).encode() + rgb.tobytes()).hexdigest()


def save(fig, name, values):
    """Check the text of the figure, then write four formats."""
    S.check(fig, name)
    meta_svg = {'Date': None, 'Creator': 'MIC-50-90 figure build'}
    meta_pdf = {'CreationDate': None, 'ModDate': None, 'Creator': 'MIC-50-90 figure build'}
    fig.savefig(OUT / f'{name}.svg', metadata=meta_svg)
    fig.savefig(OUT / f'{name}.pdf', metadata=meta_pdf)
    fig.savefig(OUT / f'{name}.png', dpi=300)
    fig.savefig(OUT / f'{name}.tif', dpi=600, pil_kwargs={'compression': 'tiff_lzw'})
    with Image.open(OUT / f'{name}.tif') as im:
        im.convert('RGB').save(OUT / f'{name}.tif', compression='tiff_lzw', dpi=(600, 600))
    RECORD.append({'figure': name, 'inches': [round(x, 3) for x in fig.get_size_inches()],
                   'axes_with_data': sum(1 for a in fig.axes if a.axison and a.get_label() != 'secondary'),
                   'plotted_values': values,
                   'file_sha256': {e: sha(OUT / f'{name}.{e}') for e in ['svg', 'pdf', 'png', 'tif']},
                   'pixel_sha256': {e: pixels(OUT / f'{name}.{e}') for e in ['png', 'tif']}})
    plt.close(fig)


# ---------------------------------------------------------------- data checks
def load_ampicillin():
    recs = {(r['quantity'], r['state']): r for r in rows(DATA / 'figureS2_ampicillin_category.csv')}
    rerun = json.loads((DATA / 'ampicillin_rerun.json').read_text())
    need(rerun['version'] == PACKAGE_VERSION, f'rerun not from MIC-50-90 {PACKAGE_VERSION}')
    res = rerun['results']
    for st in ['before', 'after']:
        c = recs[('collection', st)]
        p = recs[('population', st)]
        need([int(c['count_lower']), int(c['count_upper'])] == res[f'sample_{st}'], f'sample {st} differs from rerun')
        for v, w in zip([float(p['lower_percent']), float(p['upper_percent'])], res[f'population_{st}']):
            need(math.isclose(v, w, rel_tol=0, abs_tol=1e-9), f'population {st} differs from rerun')
        need(math.isclose(float(c['lower_percent']), 100 * int(c['count_lower']) / 67, abs_tol=1e-12), 'pct')
    need(res['sample_before'] == [1, 32] and res['sample_after'] == [2, 7], 'headline counts')
    for st in ['before', 'after']:
        need(len(res[f'categories_{st}']) == 5 and res[f'categories_{st}'][2][1:] == res[f'sample_{st}'], f'categories {st}')
    recs['rerun'] = res
    return recs


def load_pneumococci():
    rr = rows(DATA / 'madrid_pneumococci.csv')
    need(len(rr) == 15 and sum(int(r['n']) for r in rr) == 7133, 'Madrid: 15 years, 7133 isolates')
    for r in rr:
        need(int(r['middle_count']) == int(r['count_above_0_06']) - int(r['count_above_2']), f"middle {r['year']}")
    same = [r for r in rr if r['mic50'] == '0.023' and r['mic90'] == '0.5']
    need([r['year'] for r in same] == ['2016', '2018', '2021'], 'shared quantile years')
    pct = {r['year']: 100 * int(r['middle_count']) / int(r['n']) for r in same}
    need([f'{pct[y]:.2f}' for y in ['2016', '2018', '2021']] == ['19.64', '18.10', '29.19'], 'Madrid shares')
    return rr


def load_efsa():
    runtime = json.loads((EFSA / 'EFSA_REPLAY_SUMMARY.json').read_text())
    need(runtime['software_version'] == PACKAGE_VERSION and runtime['status'] == 'passed', 'EFSA replay')
    optimizer = json.loads((EFSA / 'OPTIMIZER_SUMMARY.json').read_text())
    ext = json.loads((EFSA / 'external_input.json').read_text())
    checks = rows(EFSA / 'ALL_RANGE_CHECKS.csv')
    sel = rows(EFSA / 'selected_113_fields.csv')
    meta = {r['id']: r for r in ext['cohorts']}
    need(len(meta) == 39 and len(checks) == 5031 and len(sel) == 113, 'EFSA dimensions')
    stages = ['summaries', 'selected_113', 'complete']
    groups = defaultdict(list)
    for r in checks:
        m = meta[r['cohort']]
        lo, hi, n = int(r['lower_count']), int(r['upper_count']), int(r['n'])
        a, b = int(r['start_index']), int(r['stop_index'])
        truth = sum(m['histogram'][a:b])
        need(n == m['n'] and lo <= truth <= hi and truth == int(r['true_count'])
             and r['package_oracle_match'] == 'True', f'range row {r}')
        if not (a == 0 and b == len(m['histogram'])):
            groups[(r['cohort'], r['stage'])].append(100 * (hi - lo) / n)
    per = {cid: [max(groups[(cid, s)]) for s in stages] for cid in sorted(meta)}
    for cid, v in per.items():
        need(v[0] >= v[1] >= v[2] == 0, f'monotonicity {cid}')
    med = [median(v[i] for v in per.values()) for i in range(3)]
    ident = [sum(v[i] == 0 for v in per.values()) for i in range(3)]
    for i, s in enumerate(stages):
        ref = runtime['stages'][s]
        need(math.isclose(med[i], ref['median_of_cohort_max_range_width_pp'], abs_tol=1e-12), 'median')
        need(ident[i] == ref['fully_identified_histograms'], 'identified')
    need([f'{m:.3f}' for m in med] == ['9.827', '0.578', '0.000'] and ident == [0, 16, 39], 'EFSA headline')
    look = {r['target']: r for r in optimizer['rows']}
    cost = []
    for t, lab in [('population_class', 'Classes only'), ('class_precision_5pp', 'Loss ≤ 5 pp'),
                   ('class_precision_2pp', 'Loss ≤ 2 pp'), ('class_precision_0pp', 'Exact endpoints')]:
        r = look[t]
        need(r['population_classes_retained'] == 294 and r['global_fields'] == r['integer_lower_bound'], t)
        cost.append((lab, r['global_fields'], r['maximum_endpoint_loss_pp']))
    need([(c[1], round(c[2], 2)) for c in cost] == [(37, 46.34), (89, 4.79), (113, 1.95), (150, 0.0)], 'cost rows')
    return per, med, ident, cost


# ---------------------------------------------------------------- main figures
def figure1(rr):
    """Madrid penicillin: share of isolates between 0.06 and 2 mg/L in each annual collection."""
    years = np.array([int(r['year']) for r in rr])
    same = np.isin(years, [2016, 2018, 2021])
    p = np.array([100 * int(r['middle_count']) / int(r['n']) for r in rr])
    fig = plt.figure(figsize=(6.5, 3.2))
    ax = fig.add_axes([.085, .245, .895, .725])
    ax.set_xlim(2006.4, 2021.6); ax.set_ylim(0, 40)
    ax.set_yticks([0, 10, 20, 30, 40]); ax.yaxis.set_minor_locator(MultipleLocator(5))
    ax.plot(years, p, color=GREY, lw=.7, zorder=2)
    ax.plot(years[~same], p[~same], ls='none', marker='o', mfc=BLACK, mec=BLACK, zorder=3)
    ax.plot(years[same], p[same], ls='none', marker='s', ms=5, mfc=BLUE, mec=BLUE, zorder=4)
    for y, v, offset, ha in zip(years[same], p[same], [(6, 4), (0, 7), (0, 7)], ['left', 'center', 'center']):
        ax.annotate(f'{v:.2f}%', (y, v), offset, textcoords='offset points', ha=ha, fontsize=S.SMALL)
    ax.set_ylabel('Isolates with MIC in (0.06, 2] mg/L (%)')
    ax.set_xticks(years); ax.set_xticklabels([str(y) for y in years])
    for y, r in zip(years, rr):
        ax.text(y, -.2, r['n'], transform=ax.get_xaxis_transform(), ha='center', va='center', fontsize=S.SMALL)
    ax.text(2006.45, -.2, S.N, transform=ax.get_xaxis_transform(), ha='right', va='center')
    S.legend(ax, [S.mark_handle('o', 'Other years'),
                  S.mark_handle('s', 'MIC$_{50}$ = 0.023 mg/L and MIC$_{90}$ = 0.5 mg/L', color=BLUE, ms=5)],
             loc='upper left')
    save(fig, 'Figure1', {str(y): round(v, 4) for y, v in zip(years, p)})


def figure2(amp):
    """Architecture: three interfaces, one calculation engine, two users and their results."""
    b = f"{amp[('collection','before')]['count_lower']}–{amp[('collection','before')]['count_upper']}"
    a = f"{amp[('collection','after')]['count_lower']}–{amp[('collection','after')]['count_upper']}"
    fig = plt.figure(figsize=(7.0, 3.3))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')

    def text(x, y, s, **kw):
        return ax.text(x, y, s, ha='center', va='center', **kw)

    def box(x, y, w, h, head, body, fill=WHITE):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=BLACK, lw=.7))
        text(x + w / 2, y + h - .052, head, fontweight='bold', fontsize=9.4)
        text(x + w / 2, y + (h - .075) / 2, body, fontsize=8.8, linespacing=1.4)

    def arrow(start, end):
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>', mutation_scale=7, lw=.7, color=BLACK,
                                     shrinkA=0, shrinkB=0))

    for i, s in enumerate(['Python API', 'Command line', 'Galaxy tools']):
        ax.add_patch(Rectangle((.275 + i * .15, .865), .15, .09, facecolor=WHITE, edgecolor=BLACK, lw=.7))
        text(.35 + i * .15, .91, s, fontsize=8.8)
    arrow((.5, .865), (.5, .765))
    box(.012, .50, .285, .26, 'Reader', 'Incomplete MIC report:\nsample size, categories,\nMIC50, MIC90, range, counts')
    box(.012, .15, .285, .26, 'Laboratory', 'Complete count table\nand the questions\nreaders will ask')
    box(.365, .15, .27, .61, 'One calculation engine',
        'Check the report\nBound every count\nRank counts to request\nSelect counts to publish\nAdd population bounds',
        fill=S.GREY_PALE)
    box(.703, .50, .285, .26, 'What the report establishes',
        f'Exact bounds on every count\nThe count to request:\n{b} → {a} of 67 isolates')
    box(.703, .15, .285, .26, 'A report readers can check',
        'The fewest counts to publish\nand a certificate:\none count, four answers')
    for y in [.63, .28]:
        arrow((.297, y), (.365, y)); arrow((.635, y), (.703, y))
    text(.5, .083, 'Outputs: HTML report, CSV and JSON results, reusable input and certificates', fontsize=8.6)
    text(.5, .035, 'Population bounds are available for independently sampled isolates', fontsize=8.6)
    save(fig, 'Figure2', {'example_before': b, 'example_after': a})


def figure3(amp):
    """Ampicillin: possible number of isolates in every category, before and after the published count."""
    res = amp['rerun']
    before, after = res['categories_before'], res['categories_after']
    need([b[0] for b in before] == [a[0] for a in after] == ['<=0.12', '0.25', '0.5', '1', '>1'], 'ampicillin categories')
    need([b[1:] for b in before] == [[34, 60], [0, 26], [1, 32], [0, 5], [1, 6]], 'bounds from the summaries')
    need([a[1:] for a in after] == [[34, 59], [0, 25], [2, 7], [0, 5], [1, 6]], 'bounds with the count')
    n = 67
    fig = plt.figure(figsize=(6.5, 3.3)); ax = fig.add_axes([.105, .15, .575, .665])
    ax.set_xlim(0, n); ax.set_ylim(4.5, -.5); ax.set_yticks(range(5))
    ax.set_yticklabels([b[0].replace('<=', '≤') for b in before])
    ax.set_ylabel('MIC category (mg/L)'); ax.set_xlabel('Possible number of isolates')
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60, n]); ax.xaxis.set_minor_locator(MultipleLocator(5))
    share = ax.secondary_xaxis('top', functions=(lambda x: 100 * x / n, lambda s: s * n / 100))
    share.set_xticks(range(0, 101, 20)); share.xaxis.set_minor_locator(MultipleLocator(10))
    share.set_xlabel('Share of the 67 isolates (%)')
    S.guides(ax, [.5, 1.5, 2.5, 3.5])
    for i, (b, a) in enumerate(zip(before, after)):
        S.hspan(ax, b[1], b[2], i - .17, BLACK)
        S.hspan(ax, a[1], a[2], i + .17, BLUE)
    S.column(ax, 1.19, [(i, f'{b[1]}–{b[2]}') for i, b in enumerate(before)], 'Summaries', -.56)
    S.column(ax, 1.40, [(i, f'{a[1]}–{a[2]}') for i, a in enumerate(after)], 'With count', -.56)
    S.legend(ax, [S.interval_handle(BLACK, 'MIC$_{50}$, MIC$_{90}$ and range'),
                  S.interval_handle(BLUE, 'with 59 isolates at ≤0.25 mg/L')], loc='lower right')
    save(fig, 'Figure3', {'before': [b[1:] for b in before], 'after': [a[1:] for a in after]})


def compatible_tables():
    """Every complete table that fits the ampicillin summaries, and the tables at the category boundaries.

    The report says: 67 isolates in five categories; MIC50 (34th result) in the first category; MIC90 (61st
    result) in the third; at least one isolate in the first and in the last category. The enumeration and the
    shortest-path closure below use no program code.
    """
    n, k = 67, 5
    tables = []
    for c0 in range(34, n + 1):
        for c1 in range(0, n - c0 + 1):
            if c0 + c1 > 60:
                break
            for c2 in range(max(0, 61 - c0 - c1), n - c0 - c1 + 1):
                rest = n - c0 - c1 - c2
                tables += [(c0, c1, c2, c3, rest - c3) for c3 in range(0, rest)]   # last category holds at least one
    big = 10 ** 6
    d = np.full((k + 1, k + 1), big, dtype=np.int64); np.fill_diagonal(d, 0)
    for u, v, w in ([(i + 1, i, 0) for i in range(k)] + [(0, k, n), (k, 0, -n), (1, 0, -34), (0, 2, 60), (3, 0, -61),
                                                          (0, 4, n - 1)]):
        d[u, v] = min(d[u, v], w)
    for m in range(k + 1):
        d = np.minimum(d, d[:, m:m + 1] + d[m:m + 1, :])
    selected = []
    for a in range(1, k + 1):
        table = [int(x) for x in np.diff(d[a, :])]
        if table not in selected:
            selected.append(table)
    return n, tables, selected


def cumulative_lines(ax, tables, n, alpha=.06):
    """Every table as a faint line of its cumulative shares; the shade grows where tables agree."""
    cumulative = np.unique(100 * np.cumsum(np.array(tables), axis=1) / n, axis=0)
    x = np.broadcast_to(np.arange(cumulative.shape[1]), cumulative.shape)
    ax.add_collection(LineCollection(np.stack([x, cumulative], axis=2), colors=[(.42, .42, .42, alpha)], linewidths=.4,
                                     zorder=2))


def figure4(amp):
    """The endpoint theorem on the ampicillin summaries: all compatible tables and the selected ones."""
    n, tables, selected = compatible_tables()
    need(len(tables) == len(set(tables)) == 7938, 'compatible tables')
    need(selected == amp['rerun']['selected_tables_before'] and len(selected) == 5, 'selected tables equal the rerun')
    need(all(tuple(t) in set(tables) for t in selected), 'selected tables are compatible')
    labels = ['≤0.12', '0.25', '0.5', '1', '>1']
    x = np.arange(5)
    fig = plt.figure(figsize=(6.5, 3.5)); ax = fig.add_axes([.095, .14, .885, .83])
    cumulative_lines(ax, tables, n)
    for table in selected:
        ax.plot(x, 100 * np.cumsum(table) / n, color=BLUE, lw=1.2, marker='o', ms=3.6, mfc=BLUE, mec=BLUE,
                clip_on=False, zorder=4)
    ax.set_xticks(x); ax.set_xticklabels(labels); ax.set_xlim(-.25, 4.25)
    ax.set_ylim(40, 103); ax.set_yticks(range(40, 101, 10)); ax.yaxis.set_minor_locator(MultipleLocator(5))
    ax.set_xlabel('MIC category (mg/L)'); ax.set_ylabel('Isolates at or below the category (%)')
    S.legend(ax, [S.line_handle(GREY, '7938 tables compatible with the report', lw=.8),
                  Line2D([0], [0], color=BLUE, lw=1.2, marker='o', ms=3.6, mfc=BLUE, mec=BLUE,
                         label='5 tables that give every population bound')], loc='lower right')
    save(fig, 'Figure4', {'compatible': len(tables), 'selected': selected})


def figure5():
    """Sixty collections and three share criteria: counts a laboratory has to publish."""
    path = HERE.parent / 'evaluation' / 'results' / 'sufficient_reporting' / 'tasks.csv'
    EXTRA_INPUTS.append(path)
    tasks = rows(path)
    need(len(tasks) == 180 and all(t['recipient_sufficient'] == 'True' for t in tasks), '180 sufficient tasks')
    groups = []
    for fraction, label in ((.05, 'Share below 5%'), (.1, 'Share below 10%'), (.2, 'Share below 20%'), (None, 'All three questions')):
        chosen = [t for t in tasks if fraction is None or float(t['fraction']) == fraction]
        groups.append((label, len(chosen), sum(int(t['answers']) for t in chosen),
                       sum(int(t['direct_fields']) for t in chosen), sum(int(t['minimal_fields']) for t in chosen)))
    need(groups[-1][1:] == (180, 1809, 405, 115), 'totals: 180 tasks, 1809 answers, 405 and 115 counts')
    fig = plt.figure(figsize=(6.5, 2.85)); ax = fig.add_axes([.235, .17, .745, .79])
    ax.set_xlim(-14, 440); ax.set_ylim(3.6, -.6); ax.set_yticks(range(4))
    ax.set_yticklabels([f'{g[0]}\n{g[1]} tasks, {g[2]} answers' for g in groups], linespacing=1.2)
    ax.set_xticks(range(0, 401, 50)); ax.xaxis.set_minor_locator(MultipleLocator(10))
    ax.set_xlabel('Counts the laboratory has to publish')
    S.guides(ax, range(4)); ax.axhline(2.5, color=BLACK, lw=.5)
    for y, (label, count, answers, direct, minimal) in enumerate(groups):
        if direct == 0:
            S.dot(ax, 0, y, color=BLUE, ms=5)
            ax.text(9, y, '0: the summaries settle every answer', ha='left', va='center', fontsize=S.SMALL,
                    bbox={'facecolor': WHITE, 'edgecolor': 'none', 'pad': 1})
            continue
        ax.plot([minimal, direct], [y, y], color=BLACK, lw=.7, zorder=2)
        S.dot(ax, direct, y, filled=False, ms=5)
        S.dot(ax, minimal, y, color=BLUE, ms=5)
        ax.text(direct + 8, y, str(direct), ha='left', va='center', fontsize=S.SMALL,
                bbox={'facecolor': WHITE, 'edgecolor': 'none', 'pad': 1})
        ax.text(minimal - 8, y, str(minimal), ha='right', va='center', fontsize=S.SMALL,
                bbox={'facecolor': WHITE, 'edgecolor': 'none', 'pad': 1})
    S.legend(ax, [S.mark_handle('o', 'Every count left open by the summaries', filled=False, ms=5),
                  S.mark_handle('o', 'Smallest sufficient set', color=BLUE, ms=5)],
             loc='center right', bbox_to_anchor=(1, .47))
    save(fig, 'Figure5', {g[0]: list(g[1:]) for g in groups})


def figure6(per, med, ident):
    """EFSA data: the widest range of each of 39 distributions at three levels of information."""
    fig = plt.figure(figsize=(6.5, 3.5)); a = fig.add_axes([.095, .185, .885, .785])
    colors = [BLACK, BLUE, GREEN]
    offsets = np.linspace(-.13, .13, len(per))
    for off, cid in zip(offsets, sorted(per)):
        x = np.arange(3) + off
        a.plot(x, per[cid], color=GREY, alpha=.45, lw=.45, zorder=1)
        for xi, y, c in zip(x, per[cid], colors):
            a.plot([xi], [y], ls='none', marker='o', ms=2.6, mfc=c, mec='none', zorder=2)
    for x, y, t in zip(range(3), med, ['9.827', '0.578', '0']):
        a.plot([x - .2, x + .2], [y, y], color=BLACK, lw=1.6, zorder=4)
        a.annotate(t, (x + .2, y), xytext=(4, 0), textcoords='offset points', ha='left', va='center', fontsize=8,
                   bbox={'facecolor': WHITE, 'edgecolor': 'none', 'pad': 1}, zorder=5)
    a.set_yscale('symlog', linthresh=1, linscale=1, base=10); a.set_ylim(-.16, 130)
    a.set_yticks([0, 1, 2, 5, 10, 20, 50, 100], labels=['0', '1', '2', '5', '10', '20', '50', '100'])
    a.yaxis.set_minor_locator(NullLocator())
    a.set_xlim(-.4, 2.45)
    a.set_xticks([0, 1, 2], labels=[f'Summaries only\n0 counts; {ident[0]} of 39 identified',
                                    f'With selected counts\n113 counts; {ident[1]} of 39 identified',
                                    f'Complete counts\n294 counts; {ident[2]} of 39 identified'], linespacing=1.25)
    a.set_ylabel('Widest range of a distribution (pp)')
    S.legend(a, [S.line_handle(BLACK, 'Median of the 39 distributions', lw=1.6)], loc='upper right')
    save(fig, 'Figure6', {'medians_pp': [round(m, 6) for m in med], 'identified': ident})


# ---------------------------------------------------------- supplementary
def figureS1(rr):
    """Madrid penicillin: the reported MIC50 and MIC90 of each annual collection."""
    years = np.array([int(r['year']) for r in rr]); same = np.isin(years, [2016, 2018, 2021])
    fig = plt.figure(figsize=(6.5, 2.9)); a = fig.add_axes([.095, .105, .885, .86])
    a.set_xlim(2006.4, 2021.6)
    S.guides(a, years[same], axis='x')
    a.set_yscale('log', base=2); a.set_ylim(.011, 3.2)
    a.set_yticks([.016, .032, .064, .125, .25, .5, 1, 2])
    a.set_yticklabels(['0.016', '0.032', '0.064', '0.125', '0.25', '0.5', '1', '2']); a.yaxis.set_minor_locator(NullLocator())
    a.set_ylabel('Reported MIC (mg/L)')
    a.plot(years, [float(r['mic90']) for r in rr], color=BLACK, marker='s', ms=4, mfc=BLACK, lw=.8, label='MIC$_{90}$')
    a.plot(years, [float(r['mic50']) for r in rr], color=BLACK, marker='o', mfc=WHITE, lw=.8, label='MIC$_{50}$')
    a.legend(loc='center left', bbox_to_anchor=(0, .46))
    a.set_xticks(years); a.set_xticklabels([str(y) for y in years])
    save(fig, 'SupplementaryFigureS1', {r['year']: [r['mic50'], r['mic90']] for r in rr})


def figureS2(amp):
    """Ampicillin category 0.5 mg/L: sample and population bounds before and after the count."""
    fig = plt.figure(figsize=(6.5, 2.5))
    ax = fig.add_axes([.29, .19, .5, .765])
    ax.set_xlim(0, 70); ax.set_ylim(4.75, -.75); ax.set_xticks(range(0, 71, 10)); ax.xaxis.set_minor_locator(MultipleLocator(5))
    ax.set_xlabel('Share in category 0.5 mg/L (%)')
    ys = {('collection', 'before'): 0, ('collection', 'after'): 1, ('population', 'before'): 3, ('population', 'after'): 4}
    labels, ticks, vals, column = [], [], {}, []
    for (q, st), y in ys.items():
        r = amp[(q, st)]
        lo, hi = float(r['lower_percent']), float(r['upper_percent'])
        S.hspan(ax, lo, hi, y, BLACK if st == 'before' else BLUE)
        column.append((y, f"{r['count_lower']}–{r['count_upper']} of 67 isolates" if q == 'collection'
                       else f'{lo:.3f}–{hi:.2f}%'))
        ticks.append(y); labels.append('Summaries' if st == 'before' else 'With count of 59')
        vals[f'{q}_{st}'] = [round(lo, 4), round(hi, 4)]
    ax.set_yticks(ticks); ax.set_yticklabels(labels)
    S.column(ax, 1.03, column, ha='left')
    for y, text in ((.5, 'Tested isolates'), (3.5, 'Population,\n95% bounds')):
        ax.text(-.56, y, text, transform=ax.get_yaxis_transform(), ha='left', va='center', fontweight='bold',
                linespacing=1.15, clip_on=False)
    ax.axhline(2, color=BLACK, lw=.5)
    save(fig, 'SupplementaryFigureS2', vals)


def figureS3():
    """Chloramphenicol: bounds on the number of isolates above every threshold."""
    rr = rows(DATA / 'figureS3_chloramphenicol.csv')
    at = {r['threshold']: r for r in rr}
    need(at['2.0']['certainly_above'] == '34' and at['2.0']['possibly_above'] == '67', 'chloramphenicol at 2')
    need(at['4.0']['certainly_above'] == '34' and at['8.0']['possibly_above'] == '0', 'boundaries')
    fig = plt.figure(figsize=(6.5, 3.1))
    b = fig.add_axes([.085, .15, .895, .815])
    b.set_xscale('log', base=2); b.set_xlim(.5, 16); b.set_xticks([.5, 1, 2, 4, 8, 16])
    b.set_xticklabels(['0.5', '1', '2', '4', '8', '16']); b.xaxis.set_minor_locator(NullLocator())
    b.set_ylim(-4, 72); b.set_yticks([0, 10, 20, 30, 40, 50, 60, 67]); b.set_ylabel(f'Isolates with MIC > {S.T}')
    b.set_xlabel(f'Threshold {S.T} (mg/L)')
    b.fill_between([.5, 4], [34, 34], [67, 67], color=S.GREY_PALE, lw=0, zorder=1)
    b.fill_between([4, 8], [0, 0], [34, 34], color=S.GREY_PALE, lw=0, zorder=1)
    for x, y in [([.5, 4], [67, 67]), ([4, 8], [34, 34]), ([.5, 4], [34, 34]), ([4, 16], [0, 0])]:
        b.plot(x, y, color=BLACK, lw=1, zorder=3)
    b.plot([4, 8], [34, 0], ls='none', marker='o', ms=4, mfc=BLACK, mec=BLACK, zorder=5, clip_on=False)
    b.plot([4, 4, 8], [67, 0, 34], ls='none', marker='o', ms=4, mfc=WHITE, mec=BLACK, zorder=6, clip_on=False)
    S.criterion(b, x=2)
    S.vspan(b, 2, 34, 67, RED, lw=1.5, zorder=7)
    b.text(2.12, 50.5, f'34–67 isolates at {S.T} = 2 mg/L', fontsize=S.SMALL, va='center')
    b.text(.54, 68.3, 'Upper bound', fontsize=S.SMALL, va='bottom')
    b.text(.54, 35.3, 'Lower bound', fontsize=S.SMALL, va='bottom')
    save(fig, 'SupplementaryFigureS3', {'t=2': [34, 67], 't=4': [34, 34], 't=8': [0, 0]})


def figureS4():
    """Chloramphenicol: the two recorded measurement intervals."""
    fig = plt.figure(figsize=(6.5, 1.8)); a = fig.add_axes([.14, .29, .84, .63])
    a.set_xscale('log', base=2); a.set_xlim(.5, 16); a.set_xticks([.5, 1, 2, 4, 8, 16])
    a.set_xticklabels(['0.5', '1', '2', '4', '8', '16']); a.xaxis.set_minor_locator(NullLocator())
    a.set_ylim(1.6, -.6); a.set_yticks([0, 1]); a.set_yticklabels(['33 isolates', '34 isolates'])
    a.set_xlabel('MIC (mg/L)')
    S.guides(a, [0, 1])
    a.plot([.5, 4], [0, 0], lw=1.2, color=BLACK, zorder=3); a.plot(4, 0, 'o', ms=4.5, mfc=BLACK, mec=BLACK, zorder=4)
    a.plot(.53, 0, '<', ms=4.5, mfc=BLACK, mec=BLACK, zorder=4)
    a.plot([4, 8], [1, 1], lw=1.2, color=BLACK, zorder=3); a.plot(4, 1, 'o', ms=4.5, mfc=WHITE, mec=BLACK, zorder=4)
    a.plot(8, 1, 'o', ms=4.5, mfc=BLACK, mec=BLACK, zorder=4)
    S.criterion(a, x=2); a.text(2.1, -.42, f'{S.T} = 2 mg/L', fontsize=S.SMALL, va='center')
    save(fig, 'SupplementaryFigureS4', {'<=4': 33, '(4,8]': 34})


def figureS5():
    """Amikacin: shares above four thresholds before and after one published count."""
    rr = rows(DATA / 'figureS5_amikacin.csv')
    need(len(rr) == 4 and all(r['n'] == '276' and r['before_max'] == '27' for r in rr), 'amikacin rows')
    need(rr[0]['after_min'] == rr[0]['after_max'] == '8' and all(r['after_max'] == '8' for r in rr), 'after')
    fig = plt.figure(figsize=(6.5, 3.2)); ax = fig.add_axes([.085, .15, .895, .735])
    ax.set_xlim(-.25, 10.5); ax.set_ylim(3.6, -.6); ax.set_yticks(range(4)); ax.set_yticklabels(['4', '8', '16', '32'])
    ax.set_ylabel(f'Threshold {S.T} (mg/L)'); ax.set_xlabel(f'Share with MIC > {S.T} (%)')
    ax.set_xticks(range(0, 11, 2)); ax.xaxis.set_minor_locator(MultipleLocator(1))
    S.guides(ax, [.5, 1.5, 2.5])
    S.criterion(ax, x=5); ax.text(5.12, -.42, '5% criterion', fontsize=S.SMALL, va='center')
    vals = {}
    for y, r in enumerate(rr):
        n = int(r['n'])
        S.hspan(ax, 100 * int(r['before_min']) / n, 100 * int(r['before_max']) / n, y - .2, BLACK)
        S.hspan(ax, 100 * int(r['after_min']) / n, 100 * int(r['after_max']) / n, y + .08, BLUE)
        S.dot(ax, 100 * int(r['laboratory_count']) / n, y + .3, marker='D', color=GREEN, ms=3.8)
        vals[r['threshold']] = {'before': [r['before_min'], r['before_max']], 'after': [r['after_min'], r['after_max']],
                                'laboratory': r['laboratory_count']}
    ax.annotate('8 of 276', (8 / 276 * 100, .08), (7, 0), textcoords='offset points', fontsize=S.SMALL, va='center')
    ax.annotate('0–8 of 276', (8 / 276 * 100, 3.08), (7, 0), textcoords='offset points', fontsize=S.SMALL, va='center')
    S.legend(fig, [S.interval_handle(BLACK, 'Summaries'), S.interval_handle(BLUE, 'With the published count'),
                   S.mark_handle('D', 'Count held by the laboratory', color=GREEN, ms=3.8)],
             loc='upper center', bbox_to_anchor=(.53, .985), ncol=3)
    save(fig, 'SupplementaryFigureS5', vals)


def figureS6(cost):
    """EFSA data: counts to publish against the precision that is kept."""
    fig = plt.figure(figsize=(6.5, 3.2)); b = fig.add_axes([.085, .145, .895, .82])
    b.set_xlim(20, 170); b.set_ylim(-2.5, 52); b.set_xticks(range(20, 171, 20)); b.set_yticks(range(0, 51, 10))
    b.xaxis.set_minor_locator(MultipleLocator(10)); b.yaxis.set_minor_locator(MultipleLocator(5))
    S.criterion(b, y=2)
    b.text(22, 2.8, '2 pp tolerance', ha='left', va='bottom', fontsize=S.SMALL)
    b.set_xlabel('Published counts'); b.set_ylabel('Largest loss at an interval end (pp)')
    b.plot([c[1] for c in cost], [c[2] for c in cost], color=GREY, lw=.7, zorder=2)
    places = [(44, 46.34), (97, 23), (118, 15.5), (139, 8)]
    for (lab, f, v), place, colour in zip(cost, places, [BLACK, BLACK, BLUE, BLACK]):
        S.dot(b, f, v, color=colour, ms=5)
        b.annotate(f'{lab}\n{f} counts, {v:.2f} pp' if v else f'{lab}\n{f} counts, 0 pp', (f, v), place,
                   fontsize=S.SMALL, ha='left', va='center', linespacing=1.2,
                   arrowprops=None if place[1] == v else dict(arrowstyle='-', color=BLACK, linewidth=.5, shrinkA=1,
                                                               shrinkB=3.5, relpos=(0, .5)))
    save(fig, 'SupplementaryFigureS6', {lab: [f, round(v, 4)] for lab, f, v in cost})


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--check', type=Path, help='EXPECTED_MAIN_FIGURES.json to compare the new figures with')
    ap.add_argument('--allow-other-versions', action='store_true',
                    help='build with library versions other than the pinned ones (appearance is then not guaranteed)')
    args = ap.parse_args(); OUT = args.out.resolve(); OUT.mkdir(parents=True, exist_ok=True)
    import PIL
    import fontTools
    have = {'matplotlib': matplotlib.__version__, 'numpy': np.__version__, 'PIL': PIL.__version__,
            'fontTools': fontTools.version}
    if have != PINNED and not args.allow_other_versions:
        raise SystemExit(f'library versions {have} differ from the pinned {PINNED}; '
                         'install requirements-figures.txt or pass --allow-other-versions')
    amp = load_ampicillin(); pne = load_pneumococci(); per, med, ident, cost = load_efsa()
    figure1(pne); figure2(amp); figure3(amp); figure4(amp); figure5(); figure6(per, med, ident)
    figureS1(pne); figureS2(amp); figureS3(); figureS4(); figureS5(); figureS6(cost)
    need(all(r['axes_with_data'] <= 1 for r in RECORD), 'a figure has more than one data axis')
    receipt = {'status': 'passed', 'versions': have,
               'rule': 'one data graph per figure; ' + S.RULE, 'palette': S.PALETTE,
               'style_sha256': sha(HERE / 'figstyle.py'),
               'fonts_sha256': {f.name: sha(f) for f in sorted((HERE / 'fonts').glob('*.ttf'))},
               'default_style_sha256': sha(HERE / 'style' / 'matplotlibrc-3.11.2-default'),
               'inputs_sha256': {**{str(p.relative_to(HERE)): sha(p) for p in sorted(list(DATA.glob('*')) + list(EFSA.glob('*')))},
                                 **{str(p.relative_to(HERE.parent)): sha(p) for p in EXTRA_INPUTS}},
               'figures': RECORD}
    (OUT / 'FIGURE_BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=1, ensure_ascii=False) + '\n')
    result = {'figures': len(RECORD), 'single_graph': True}
    if args.check:
        expected = {r['figure']: r for r in json.loads(args.check.read_text())['figures']}
        diff = []
        for r in RECORD:
            e = expected[r['figure']]
            for kind in ('png', 'tif'):
                if r['pixel_sha256'][kind] != e['pixel_sha256'][kind]:
                    diff.append(f"{r['figure']}.{kind}: pixels differ")
            for kind in ('svg', 'pdf'):
                if r['file_sha256'][kind] != e['file_sha256'][kind]:
                    diff.append(f"{r['figure']}.{kind}: file differs")
            if r['plotted_values'] != e['plotted_values']:
                diff.append(f"{r['figure']}: plotted values differ")
        result['identical_to_recorded_figures'] = not diff
        result['differences'] = diff
        print(json.dumps(result, indent=1))
        if diff:
            raise SystemExit(1)
    else:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
