"""MIC-50-90 SoftwareX figures: six single-graph main figures and four single-graph
supplementary figures, drawn from the numeric records in data/ and efsa/.

Every plotted value is asserted against its source file before drawing. No analysis is
rerun here; the Figure 3 values are also checked against a rerun with the installed
package (data/ampicillin_rerun.json, written by rerun_ampicillin.py), and the Figure 6
values against the replay of the public EFSA data (efsa/EFSA_REPLAY_SUMMARY.json).

Appearance is fixed by this script: colours are black, greys and two muted accents,
all text is black, the font files are bundled (fonts/), and the library versions are
pinned in requirements-figures.txt.

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
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.colors import to_hex
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, Rectangle
from matplotlib.ticker import NullLocator
from PIL import Image

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
EFSA = HERE / 'efsa'
# Palette: black, greys and two muted accents. All text is black.
INK = '#000000'; WHITE = '#FFFFFF'
MUTED = '#4D4D4D'; GREY = '#8C8C8C'; GRID = '#E0E0E0'; LIGHT = '#F2F2F2'
BLUE = '#2F5D7C'; PALEBLUE = '#E4ECF1'; SLATE = '#1F3447'; OCHRE = '#9A5B3E'
PINNED = {'matplotlib': '3.11.2', 'numpy': '2.5.3', 'PIL': '12.3.0', 'fontTools': '4.67.0'}
PACKAGE_VERSION = '2.0.0'  # version of MIC-50-90 whose results the figures show

# Use only the bundled font files, whatever is installed on the computer.
font_manager.fontManager.ttflist = [f for f in font_manager.fontManager.ttflist if f.name != 'Liberation Sans']
for _font in sorted((HERE / 'fonts').glob('*.ttf')):
    font_manager.fontManager.addfont(str(_font))
FORBIDDEN = ['·', '•', '∙', '⋅']  # middle dot, bullet, bullet operator, dot operator

# Start from matplotlib's own defaults (a pristine copy is bundled), so that a matplotlibrc
# on the computer cannot change the appearance; then apply the figure style.
_NOT_STYLE = ('backend', 'interactive', 'toolbar', 'webagg.', 'tk.', 'timezone', 'datapath',
              'docstring.', 'date.epoch', 'savefig.directory', 'figure.raise_window', 'figure.max_open_warning')
_defaults = matplotlib._rc_params_in_file(
    str(HERE / 'style' / 'matplotlibrc-3.11.2-default'),
    transform=lambda line: line[1:] if line.startswith('#') else line, fail_on_error=True)
matplotlib.rcParams.update({k: v for k, v in _defaults.items() if not k.startswith(_NOT_STYLE)})

plt.rcParams.update({
    'pdf.compression': 0,  # uncompressed streams: the PDF bytes do not depend on the zlib build
    'font.family': 'Liberation Sans', 'font.size': 8.5, 'text.color': INK,
    'axes.labelcolor': INK, 'axes.edgecolor': MUTED, 'axes.linewidth': .6,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.labelsize': 9, 'xtick.labelsize': 8, 'ytick.labelsize': 8,
    'xtick.color': MUTED, 'ytick.color': MUTED, 'xtick.labelcolor': INK, 'ytick.labelcolor': INK,
    'xtick.major.width': .6, 'ytick.major.width': .6,
    'legend.fontsize': 8, 'legend.frameon': False,
    'lines.linewidth': 1.1, 'svg.fonttype': 'path', 'svg.hashsalt': 'mic-50-90',
    'pdf.fonttype': 42, 'mathtext.fontset': 'dejavusans',
    'figure.facecolor': WHITE, 'savefig.facecolor': WHITE})

OUT: Path
RECORD: list = []


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


def forest(ax):
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.grid(axis='x', color=GRID, lw=.5)
    ax.set_axisbelow(True)


def span(ax, lo, hi, y, color=BLUE, lw=2.2, cap=6):
    ax.plot([lo, hi], [y, y], color=color, lw=lw, solid_capstyle='butt', zorder=3)
    ax.plot([lo, hi], [y, y], ls='none', marker='|', ms=cap, mew=1.0, color=color, zorder=4)


def save(fig, name, values):
    """Check text placement and forbidden separators, then write four formats."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    texts = list(fig.texts)
    for ax in fig.axes:
        texts += list(ax.texts)
        if ax.axison:
            texts += [ax.xaxis.label, ax.yaxis.label, ax.title]
            texts += list(ax.get_xticklabels()) + list(ax.get_yticklabels())
        leg = ax.get_legend()
        if leg:
            texts += list(leg.get_texts())
    for leg in fig.legends:
        texts += list(leg.get_texts())
    outside, bad = [], []
    for t in texts:
        s = t.get_text()
        if not t.get_visible() or not s:
            continue
        if any(ch in s for ch in FORBIDDEN):
            bad.append(s)
        if to_hex(t.get_color()) != '#000000':
            bad.append(f'non-black text: {s}')
        bb = t.get_window_extent(r)
        if bb.x0 < -1 or bb.x1 > fig.bbox.width + 1 or bb.y0 < -1 or bb.y1 > fig.bbox.height + 1:
            outside.append(s)
    need(not outside, f'{name}: text outside canvas {outside}')
    need(not bad, f'{name}: forbidden separator or coloured text in {bad}')
    meta_svg = {'Date': None, 'Creator': 'MIC-50-90 figure build'}
    meta_pdf = {'CreationDate': None, 'ModDate': None, 'Creator': 'MIC-50-90 figure build'}
    fig.savefig(OUT / f'{name}.svg', metadata=meta_svg)
    fig.savefig(OUT / f'{name}.pdf', metadata=meta_pdf)
    fig.savefig(OUT / f'{name}.png', dpi=300)
    fig.savefig(OUT / f'{name}.tif', dpi=600, pil_kwargs={'compression': 'tiff_lzw'})
    with Image.open(OUT / f'{name}.tif') as im:
        im.convert('RGB').save(OUT / f'{name}.tif', compression='tiff_lzw', dpi=(600, 600))
    RECORD.append({'figure': name, 'inches': [round(x, 3) for x in fig.get_size_inches()],
                   'axes_with_data': sum(1 for a in fig.axes if a.axison),
                   'plotted_values': values,
                   'file_sha256': {e: sha(OUT / f'{name}.{e}') for e in ['svg', 'pdf', 'png', 'tif']},
                   'pixel_sha256': {e: pixels(OUT / f'{name}.{e}') for e in ['png', 'tif']}})
    plt.close(fig)


# ---------------------------------------------------------------- data checks
def load_ampicillin():
    recs = {(r['quantity'], r['state']): r for r in rows(DATA / 'figure3_ampicillin.csv')}
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
def figure2(amp):
    b = f"{amp[('collection','before')]['count_lower']}–{amp[('collection','before')]['count_upper']}"
    a = f"{amp[('collection','after')]['count_lower']}–{amp[('collection','after')]['count_upper']}"
    fig = plt.figure(figsize=(7.0, 3.35))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')

    def text(x, y, s, **kw):
        return ax.text(x, y, s, ha='center', va='center', **kw)

    def box(x, y, w, h, head, body, fill=WHITE):
        ax.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=GREY, lw=.8))
        text(x + w / 2, y + h - .05, head, fontweight='bold', fontsize=10.2)
        text(x + w / 2, y + h / 2 - .025, body, fontsize=9.3, linespacing=1.42)

    for x, s in zip([.255, .5, .745], ['Python API', 'Command line', 'Galaxy']):
        ax.add_patch(Rectangle((x - .095, .855), .19, .095, facecolor=WHITE, edgecolor=GREY, lw=.7))
        text(x, .9025, s, fontsize=9.6)
        ax.add_patch(FancyArrowPatch((x, .852), (.5 + (x - .5) * .25, .745), arrowstyle='-|>',
                                     mutation_scale=9, lw=.75, color=MUTED))
    box(.01, .49, .285, .27, 'Reader', 'Incomplete MIC report\nSample size, categories,\nsummaries and counts')
    box(.01, .13, .285, .27, 'Laboratory', 'Complete count table\nQuestions to preserve\nAllowed counts and costs')
    box(.365, .2, .27, .54, 'Shared calculation engine',
        'Check consistency\nBound compatible counts\nSelect useful counts\nIssue certificates', fill=PALEBLUE)
    box(.705, .49, .285, .27, 'Narrow an answer', f'67-isolate example\nOne added count:\n{b} → {a} isolates')
    box(.705, .13, .285, .27, 'Share checkable answers', '276-isolate example\nOne disclosed count\nsettles four questions')
    for y in [.625, .265]:
        ax.add_patch(FancyArrowPatch((.300, y), (.359, y), arrowstyle='-|>', mutation_scale=11, lw=.9, color=BLUE))
        ax.add_patch(FancyArrowPatch((.641, y), (.699, y), arrowstyle='-|>', mutation_scale=11, lw=.9, color=BLUE))
    text(.5, .07, 'Outputs: HTML report, CSV and JSON results, reusable input and certificates', fontsize=9.1)
    text(.5, .025, 'Optional population bounds require stated sampling assumptions', fontsize=8.8)
    save(fig, 'Figure2', {'example_before': b, 'example_after': a})


def figure1(rr):
    years = np.array([int(r['year']) for r in rr])
    same = np.isin(years, [2016, 2018, 2021])
    p = np.array([100 * int(r['middle_count']) / int(r['n']) for r in rr])
    fig = plt.figure(figsize=(6.5, 3.3))
    ax = fig.add_axes([.12, .23, .85, .63])
    ax.set_xlim(2006.55, 2021.45); ax.set_ylim(0, 36); ax.set_yticks([0, 10, 20, 30])
    ax.grid(axis='y', color=GRID, lw=.5); ax.set_axisbelow(True)
    for y in years[same]:
        ax.axvspan(y - .35, y + .35, color=LIGHT, zorder=0)
    ax.vlines(years, 0, p, color=GRID, lw=.7)
    ax.scatter(years[~same], p[~same], s=22, color=MUTED, zorder=3, label='Other years')
    ax.scatter(years[same], p[same], s=30, color=BLUE, marker='D', zorder=4,
               label='MIC$_{50}$/MIC$_{90}$ = 0.023/0.5 mg/L')
    for y, v in zip(years[same], p[same]):
        ax.annotate(f'{v:.2f}%', (y, v), (0, 7), textcoords='offset points', ha='center', fontsize=7.6)
    ax.set_ylabel('Share in (0.06, 2] mg/L (%)', labelpad=8)
    ax.set_xticks(years); ax.set_xticklabels([str(y) for y in years], rotation=45, ha='right',
                                             rotation_mode='anchor', fontsize=7.5)
    for y, r in zip(years, rr):
        ax.text(y, -.29, r['n'], transform=ax.get_xaxis_transform(), ha='center', va='center', fontsize=7.2)
    ax.text(2006.1, -.29, 'n', transform=ax.get_xaxis_transform(), ha='right', va='center', fontsize=8)
    ax.legend(loc='upper left', bbox_to_anchor=(0, 1.16), ncol=2, borderaxespad=0, columnspacing=2.2)
    save(fig, 'Figure1', {str(y): round(v, 4) for y, v in zip(years, p)})


def figure3(amp):
    fig = plt.figure(figsize=(6.5, 2.75))
    ax = fig.add_axes([.27, .2, .58, .66])
    ax.set_xlim(0, 70); ax.set_ylim(-.6, 4.1); ax.set_xticks([0, 10, 20, 30, 40, 50, 60, 70])
    ax.set_xlabel('Share in category 0.5 mg/L (%)', labelpad=6); forest(ax)
    ys = {('collection', 'before'): 3.4, ('collection', 'after'): 2.6,
          ('population', 'before'): .8, ('population', 'after'): 0}
    labels, ticks, vals = [], [], {}
    for (q, st), y in ys.items():
        r = amp[(q, st)]
        lo, hi = float(r['lower_percent']), float(r['upper_percent'])
        c = GREY if st == 'before' else BLUE
        span(ax, lo, hi, y, c, lw=2.4)
        if q == 'collection':
            s = f"{r['count_lower']}–{r['count_upper']} of 67 isolates"
        else:
            s = f'{lo:.3f}–{hi:.2f}%'
        ax.text(hi + 1.2, y, s, ha='left', va='center', fontsize=8)
        ticks.append(y); labels.append('Summaries' if st == 'before' else '+ count of 59')
        vals[f'{q}_{st}'] = [round(lo, 4), round(hi, 4)]
    ax.set_yticks(ticks); ax.set_yticklabels(labels)
    ax.text(-.395, 3.0, 'Sample', transform=ax.get_yaxis_transform(), ha='left', va='center',
            fontsize=8.8, fontweight='bold')
    ax.text(-.395, .4, 'Population\n(95%)', transform=ax.get_yaxis_transform(), ha='left', va='center',
            fontsize=8.8, fontweight='bold', linespacing=1.2)
    ax.axhline(1.7, color=GRID, lw=.8)
    save(fig, 'Figure3', vals)


def figure4():
    rr = rows(DATA / 'figure4_chloramphenicol.csv')
    at = {r['threshold']: r for r in rr}
    need(at['2.0']['certainly_above'] == '34' and at['2.0']['possibly_above'] == '67', 'chloramphenicol at 2')
    need(at['4.0']['certainly_above'] == '34' and at['8.0']['possibly_above'] == '0', 'boundaries')
    fig = plt.figure(figsize=(6.5, 3.1))
    b = fig.add_axes([.12, .17, .84, .74])
    b.set_xscale('log', base=2); b.set_xlim(.5, 16); b.set_xticks([.5, 1, 2, 4, 8, 16])
    b.set_xticklabels(['0.5', '1', '2', '4', '8', '16']); b.xaxis.set_minor_locator(NullLocator())
    b.set_ylim(-3, 71); b.set_yticks([0, 17, 34, 50, 67]); b.set_ylabel('Isolates with MIC > t', labelpad=8)
    b.set_xlabel('Threshold t (mg/L)', labelpad=6); b.grid(axis='y', color=GRID, lw=.5); b.set_axisbelow(True)
    b.fill_between([.5, 4], [34, 34], [67, 67], color=PALEBLUE, zorder=1)
    b.fill_between([4, 8], [0, 0], [34, 34], color=PALEBLUE, zorder=1)
    for x, y, c in [([.5, 4], [67, 67], BLUE), ([4, 8], [34, 34], BLUE), ([.5, 4], [34, 34], INK), ([4, 16], [0, 0], INK)]:
        b.plot(x, y, color=c, lw=1)
    b.scatter([4, 8], [34, 0], s=20, color=INK, zorder=5)
    b.scatter([4, 4, 8], [67, 0, 34], s=22, facecolor=WHITE, edgecolor=BLUE, lw=.9, zorder=6)
    b.axvline(2, color=OCHRE, lw=.8, ls=(0, (3, 3)))
    b.plot([2, 2], [34, 67], color=OCHRE, lw=1.7, zorder=7)
    b.plot([2, 2], [34, 67], ls='none', marker='_', ms=6, color=OCHRE, zorder=8)
    b.annotate('34–67 at 2 mg/L', xy=(2, 50.5), xytext=(2.48, 50.5), fontsize=8, va='center',
               arrowprops={'arrowstyle': '-', 'color': OCHRE, 'lw': .6})
    b.text(.53, 68.8, 'Upper bound', fontsize=7.6, va='bottom')
    b.text(.53, 35.7, 'Lower bound', fontsize=7.6, va='bottom')
    save(fig, 'Figure4', {'t=2': [34, 67], 't=4': [34, 34], 't=8': [0, 0]})


def figure5():
    rr = rows(DATA / 'figure5_amikacin.csv')
    need(len(rr) == 4 and all(r['n'] == '276' and r['before_max'] == '27' for r in rr), 'amikacin rows')
    need(rr[0]['after_min'] == rr[0]['after_max'] == '8' and all(r['after_max'] == '8' for r in rr), 'after')
    fig = plt.figure(figsize=(6.5, 3.3)); ax = fig.add_axes([.14, .19, .79, .60])
    ax.set_xlim(0, 10.5); ax.set_ylim(-.6, 3.65); ax.set_yticks([3, 2, 1, 0]); ax.set_yticklabels(['4', '8', '16', '32'])
    ax.set_ylabel('Threshold t (mg/L)', labelpad=10); ax.set_xlabel('Share with MIC > t (%)', labelpad=6)
    ax.set_xticks([0, 2, 4, 6, 8, 10]); forest(ax)
    ax.axvline(5, color=OCHRE, lw=.8, ls=(0, (3, 3))); ax.text(5.15, 3.52, '5% criterion', fontsize=7.5)
    vals = {}
    for i, r in enumerate(rr):
        y = 3 - i; n = int(r['n'])
        span(ax, 100 * int(r['before_min']) / n, 100 * int(r['before_max']) / n, y + .14, GREY, 1.8, 5)
        lo, hi = 100 * int(r['after_min']) / n, 100 * int(r['after_max']) / n
        if lo == hi:
            ax.scatter(lo, y - .14, s=24, color=BLUE, zorder=4)
        else:
            span(ax, lo, hi, y - .14, BLUE, 2.5, 5)
        ax.scatter(100 * int(r['laboratory_count']) / n, y - .14 if lo != hi else y - .36, marker='D', s=17,
                   facecolors=WHITE, edgecolors=INK, lw=.75, zorder=5)
        vals[r['threshold']] = {'before': [r['before_min'], r['before_max']], 'after': [r['after_min'], r['after_max']],
                                'laboratory': r['laboratory_count']}
    ax.annotate('8 of 276', (8 / 276 * 100, 2.86), (9, 0), textcoords='offset points', fontsize=7.6, va='center')
    ax.annotate('0–8 of 276', (8 / 276 * 100, -.14), (9, 0), textcoords='offset points', fontsize=7.6, va='center')
    handles = [Line2D([0], [0], color=GREY, lw=1.8, label='Summaries'),
               Line2D([0], [0], color=BLUE, lw=2.5, label='+ disclosed count'),
               Line2D([0], [0], color=INK, marker='D', ls='none', mfc=WHITE, ms=4, label='Laboratory count')]
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.53, .95), ncol=3, columnspacing=2, handletextpad=.7)
    save(fig, 'Figure5', vals)


def figure6(per, med, ident):
    fig = plt.figure(figsize=(6.5, 3.6)); a = fig.add_axes([.13, .2, .84, .72])
    colors = [GREY, BLUE, SLATE]
    offsets = np.linspace(-.13, .13, len(per))
    for off, cid in zip(offsets, sorted(per)):
        x = np.arange(3) + off
        a.plot(x, per[cid], color=GREY, alpha=.3, lw=.55, zorder=1)
        for xi, y, c in zip(x, per[cid], colors):
            a.scatter([xi], [y], s=8, color=c, alpha=.65, edgecolors='none', zorder=2)
    a.scatter(np.arange(3), med, marker='D', color=INK, s=32, zorder=4, label='Median')
    for x, y, t in zip(range(3), med, ['9.827', '0.578', '0']):
        a.annotate(t, (x, y), xytext=(0, 9), textcoords='offset points', ha='center', va='bottom', fontsize=8.6,
                   fontweight='bold', bbox={'facecolor': 'white', 'alpha': .9, 'edgecolor': 'none', 'pad': .5}, zorder=5)
    a.set_yscale('symlog', linthresh=1, linscale=1, base=10); a.set_ylim(-.16, 125)
    a.set_yticks([0, 1, 5, 10, 50, 90], labels=['0', '1', '5', '10', '50', '90'])
    a.set_xlim(-.4, 2.4)
    a.set_xticks([0, 1, 2], labels=[f'Summaries only\n0 fields; {ident[0]}/39 identified',
                                    f'+ selected counts\n113 fields; {ident[1]}/39 identified',
                                    f'Complete counts\n294 fields; {ident[2]}/39 identified'])
    a.set_ylabel('Maximum sample-range width (pp)')
    a.grid(axis='y', color=GRID, lw=.55, zorder=0)
    a.legend(loc='upper right')
    save(fig, 'Figure6', {'medians_pp': [round(m, 6) for m in med], 'identified': ident})


# ---------------------------------------------------------- supplementary
def figureS2():
    rr = rows(DATA / 'figureS2_ampicillin.csv')
    need([(r['lower_count'], r['upper_count']) for r in rr] ==
         [('34', '59'), ('0', '25'), ('2', '7'), ('0', '5'), ('1', '6')], 'S1 bounds')
    fig = plt.figure(figsize=(6.5, 3.25)); ax = fig.add_axes([.17, .19, .64, .61])
    ax.set_xlim(0, 67); ax.set_ylim(-.55, 4.55); ax.set_yticks(range(5)); ax.set_yticklabels([r['category'] for r in rr[::-1]])
    ax.set_ylabel('MIC category (mg/L)', labelpad=10); ax.set_xlabel('Feasible isolate count', labelpad=6)
    ax.set_xticks([0, 10, 20, 30, 40, 50, 60, 67]); forest(ax)
    top = ax.secondary_xaxis('top', functions=(lambda x: 100 * x / 67, lambda x: 67 * x / 100))
    top.set_xticks([0, 25, 50, 75, 100]); top.set_xlabel('Share of the collection (%)', labelpad=6)
    ax.axhspan(1.62, 2.38, color=LIGHT, zorder=0)
    for i, r in enumerate(rr):
        y = 4 - i; lo, hi = int(r['lower_count']), int(r['upper_count']); c = BLUE if i == 2 else MUTED
        span(ax, lo, hi, y, c, lw=2.5 if i == 2 else 1.6)
        ax.text(69.3, y, f'{lo}–{hi}', ha='left', va='center', fontsize=8.5, clip_on=False)
    ax.text(69.3, 4.7, 'Count bounds', fontsize=8, clip_on=False)
    goal = .15 * 67; ax.plot([goal, goal], [1.64, 2.36], ls=(0, (2, 2)), color=OCHRE, lw=.8)
    ax.annotate('15% criterion', xy=(goal, 2), xytext=(goal + 3, 1.70), fontsize=7.5,
                arrowprops={'arrowstyle': '-', 'lw': .5, 'color': OCHRE})
    save(fig, 'SupplementaryFigureS2', {r['category']: [r['lower_count'], r['upper_count']] for r in rr})


def figureS1(rr):
    years = np.array([int(r['year']) for r in rr]); same = np.isin(years, [2016, 2018, 2021])
    fig = plt.figure(figsize=(6.5, 2.9)); a = fig.add_axes([.13, .2, .84, .66])
    a.set_xlim(2006.55, 2021.45); a.grid(axis='y', color=GRID, lw=.5); a.set_axisbelow(True)
    for y in years[same]:
        a.axvspan(y - .35, y + .35, color=LIGHT, zorder=0)
    a.set_yscale('log', base=2); a.set_ylim(.012, 3.2); a.set_yticks([.016, .032, .125, .5, 2])
    a.set_yticklabels(['0.016', '0.032', '0.125', '0.5', '2']); a.yaxis.set_minor_locator(NullLocator())
    a.set_ylabel('Reported MIC (mg/L)', labelpad=8)
    a.plot(years, [float(r['mic50']) for r in rr], color=MUTED, marker='o', mfc=WHITE, mew=.9, ms=4, lw=.8, label='MIC$_{50}$')
    a.plot(years, [float(r['mic90']) for r in rr], color=BLUE, marker='s', mfc=BLUE, ms=3.5, lw=.9, label='MIC$_{90}$')
    a.legend(loc='upper left', ncol=2, bbox_to_anchor=(0, 1.17), borderaxespad=0, columnspacing=2)
    a.set_xticks(years); a.set_xticklabels([str(y) for y in years], rotation=45, ha='right', rotation_mode='anchor', fontsize=7.5)
    save(fig, 'SupplementaryFigureS1', {r['year']: [r['mic50'], r['mic90']] for r in rr})


def figureS3():
    fig = plt.figure(figsize=(6.5, 1.9)); a = fig.add_axes([.14, .3, .82, .58])
    a.set_xscale('log', base=2); a.set_xlim(.5, 16); a.set_xticks([.5, 1, 2, 4, 8, 16])
    a.set_xticklabels(['0.5', '1', '2', '4', '8', '16']); a.xaxis.set_minor_locator(NullLocator())
    a.set_ylim(-.6, 1.6); a.set_yticks([1, 0]); a.set_yticklabels(['33 isolates', '34 isolates'])
    a.spines['left'].set_visible(False); a.tick_params(axis='y', length=0); a.set_xlabel('MIC (mg/L)', labelpad=5)
    a.plot([.5, 4], [1, 1], lw=2, color=GREY); a.plot(.5, 1, '<', ms=4, color=GREY); a.plot(4, 1, 'o', ms=4, color=GREY)
    a.plot([4, 8], [0, 0], lw=2, color=BLUE); a.plot(4, 0, 'o', ms=4, mfc=WHITE, mec=BLUE); a.plot(8, 0, 'o', ms=4, color=BLUE)
    a.axvline(2, color=OCHRE, lw=.8, ls=(0, (3, 3))); a.text(2.08, 1.45, 't = 2 mg/L', fontsize=7.6)
    save(fig, 'SupplementaryFigureS3', {'<=4': 33, '(4,8]': 34})


def figureS4(cost):
    fig = plt.figure(figsize=(6.5, 3.3)); b = fig.add_axes([.12, .17, .84, .74])
    b.set_xlim(22, 166); b.set_ylim(-2, 52); b.set_xticks([37, 89, 113, 150]); b.set_yticks([0, 10, 20, 30, 40, 50])
    b.axhline(2, color=OCHRE, ls=(0, (3, 3)), lw=.8, zorder=1)
    b.text(26, 2.7, '2 pp tolerance', ha='left', va='bottom', fontsize=7.8)
    b.set_xlabel('Disclosed count fields'); b.set_ylabel('Maximum outward endpoint loss (pp)')
    b.grid(axis='y', color=GRID, lw=.55, zorder=0)
    b.scatter([c[1] for c in cost], [c[2] for c in cost], s=[40, 40, 54, 40],
              color=[GREY, GREY, BLUE, SLATE], zorder=3)
    for (lab, f, v), off, ha in zip(cost, [(6, -4), (-6, 14), (6, 26), (0, 12)], ['left', 'right', 'left', 'center']):
        b.annotate(f'{lab}: {v:.2f} pp' if v else f'{lab}: 0 pp', (f, v), xytext=off, textcoords='offset points',
                   fontsize=8, ha=ha, va='bottom',
                   arrowprops={'arrowstyle': '-', 'color': MUTED, 'lw': .6} if off[1] > 12 else None)
    save(fig, 'SupplementaryFigureS4', {lab: [f, round(v, 4)] for lab, f, v in cost})


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
    font = Path(font_manager.findfont('Liberation Sans', fallback_to_default=False)).resolve()
    need(font.parent == (HERE / 'fonts').resolve(), f'font not taken from the bundled folder: {font}')
    amp = load_ampicillin(); pne = load_pneumococci(); per, med, ident, cost = load_efsa()
    figure1(pne); figure2(amp); figure3(amp); figure4(); figure5(); figure6(per, med, ident)
    figureS1(pne); figureS2(); figureS3(); figureS4(cost)
    need(all(r['axes_with_data'] <= 1 for r in RECORD), 'a figure has more than one data axis')
    receipt = {'status': 'passed', 'versions': have,
               'rule': 'one data graph per figure; black text; palette of black, greys and two muted accents; '
                       'no middle-dot or bullet separators; all text inside canvas',
               'palette': {'ink': INK, 'dark grey': MUTED, 'grey': GREY, 'grid': GRID, 'light grey': LIGHT,
                           'blue': BLUE, 'pale blue': PALEBLUE, 'slate': SLATE, 'ochre': OCHRE},
               'fonts_sha256': {f.name: sha(f) for f in sorted((HERE / 'fonts').glob('*.ttf'))},
               'default_style_sha256': sha(HERE / 'style' / 'matplotlibrc-3.11.2-default'),
               'inputs_sha256': {str(p.relative_to(HERE)): sha(p) for p in sorted(list(DATA.glob('*')) + list(EFSA.glob('*')))},
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
