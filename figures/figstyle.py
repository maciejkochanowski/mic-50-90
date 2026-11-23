"""Shared appearance of every MIC-50-90 figure.

One style for the article, its supplementary figures, the appendices and the Technical Archive:
a full axes frame with outward ticks, black text in one bundled typeface, and a small palette.

    black and greys   the information in a report and reference lines
    blue              the same quantity after counts were added; in the table plots, the selected tables
    red               decision criteria and nominal levels (dashed lines), or the alternative that fails
    green             values known only from the complete data

Intervals are thin lines with short end caps; rows are separated by dotted guides; methods are told
apart by filled and open symbols. No figure uses coloured text or decorative separators.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import to_hex
from matplotlib.legend_handler import HandlerLine2D
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
BLACK = '#000000'; WHITE = '#FFFFFF'
GREY_DARK = '#4D4D4D'; GREY = '#7F7F7F'; GREY_LIGHT = '#BFBFBF'; GREY_PALE = '#EBEBEB'
BLUE = '#2166AC'; BLUE_LIGHT = '#92C5DE'; BLUE_PALE = '#D1E5F0'
RED = '#B2182B'
GREEN = '#1B7837'
PALETTE = {'black': BLACK, 'dark grey': GREY_DARK, 'grey': GREY, 'light grey': GREY_LIGHT, 'pale grey': GREY_PALE,
           'blue': BLUE, 'light blue': BLUE_LIGHT, 'pale blue': BLUE_PALE, 'red': RED, 'green': GREEN, 'white': WHITE}
RULE = ('full axes frame with outward ticks; black text in Liberation Sans; palette of black, greys, blue, red and '
        'green; intervals with end caps; white background; no middle-dot or bullet separators; all text inside '
        'the canvas')
FORBIDDEN = ['·', '•', '∙', '⋅']  # middle dot, bullet, bullet operator, dot operator
N, T, K = r'$\mathit{n}$', r'$\mathit{t}$', r'$\mathit{K}$'  # italic symbols for axis labels
DASH = (0, (4, 2.5))
DOTS = (0, (1, 2.5))
SMALL = 7.5

_NOT_STYLE = ('backend', 'interactive', 'toolbar', 'webagg.', 'tk.', 'timezone', 'datapath',
              'docstring.', 'date.epoch', 'savefig.directory', 'figure.raise_window', 'figure.max_open_warning')


def setup(hashsalt):
    """Use only the bundled fonts and matplotlib's own defaults, then apply the figure style."""
    font_manager.fontManager.ttflist = [f for f in font_manager.fontManager.ttflist if f.name != 'Liberation Sans']
    for font in sorted((HERE / 'fonts').glob('*.ttf')):
        font_manager.fontManager.addfont(str(font))
    defaults = matplotlib._rc_params_in_file(
        str(HERE / 'style' / 'matplotlibrc-3.11.2-default'),
        transform=lambda line: line[1:] if line.startswith('#') else line, fail_on_error=True)
    matplotlib.rcParams.update({k: v for k, v in defaults.items() if not k.startswith(_NOT_STYLE)})
    plt.rcParams.update({
        'pdf.compression': 0,  # uncompressed streams: the PDF bytes do not depend on the zlib build
        'svg.fonttype': 'path', 'svg.hashsalt': hashsalt, 'pdf.fonttype': 42,
        'figure.facecolor': WHITE, 'savefig.facecolor': WHITE,
        'font.family': 'Liberation Sans', 'font.size': 8, 'text.color': BLACK,
        'mathtext.fontset': 'custom', 'mathtext.rm': 'Liberation Sans', 'mathtext.it': 'Liberation Sans:italic',
        'mathtext.bf': 'Liberation Sans:bold', 'mathtext.sf': 'Liberation Sans', 'mathtext.default': 'regular',
        'mathtext.cal': 'Liberation Sans:italic', 'mathtext.tt': 'Liberation Sans', 'mathtext.bfit': 'Liberation Sans:bold',
        'axes.labelcolor': BLACK, 'axes.edgecolor': BLACK, 'axes.linewidth': .6, 'axes.labelsize': 8.5,
        'axes.labelpad': 4, 'axes.spines.top': True, 'axes.spines.right': True, 'axes.axisbelow': True,
        'axes.grid': False, 'axes.titlesize': 8.5, 'axes.titlepad': 5,
        'xtick.labelsize': 8, 'ytick.labelsize': 8, 'xtick.color': BLACK, 'ytick.color': BLACK,
        'xtick.labelcolor': BLACK, 'ytick.labelcolor': BLACK, 'xtick.direction': 'out', 'ytick.direction': 'out',
        'xtick.major.size': 3, 'ytick.major.size': 3, 'xtick.major.width': .6, 'ytick.major.width': .6,
        'xtick.minor.size': 1.7, 'ytick.minor.size': 1.7, 'xtick.minor.width': .5, 'ytick.minor.width': .5,
        'xtick.major.pad': 2.5, 'ytick.major.pad': 2.5,
        'lines.linewidth': 1.0, 'lines.markersize': 4.5, 'lines.markeredgewidth': .8, 'lines.solid_capstyle': 'butt',
        'patch.linewidth': .6, 'hatch.linewidth': .5,
        'legend.fontsize': 8, 'legend.frameon': False, 'legend.handlelength': 2.0, 'legend.handletextpad': .6,
        'legend.columnspacing': 1.8, 'legend.labelspacing': .35, 'legend.borderaxespad': .6, 'legend.borderpad': .2})
    font = Path(font_manager.findfont('Liberation Sans', fallback_to_default=False)).resolve()
    if font.parent != (HERE / 'fonts').resolve():
        raise SystemExit(f'font not taken from the bundled folder: {font}')


class Interval(Line2D):
    """Legend handle of an interval: a line with a cap at each end."""


def interval_handle(color, label, lw=1.1, cap=3.0):
    return Interval([0], [0], color=color, lw=lw, marker='|', ms=2 * cap, mew=lw, label=label)


def line_handle(color, label, lw=1.0, ls='-', **kw):
    return Line2D([0], [0], color=color, lw=lw, ls=ls, label=label, **kw)


def mark_handle(marker, label, color=BLACK, filled=True, ms=4.5, mew=.8):
    return Line2D([0], [0], ls='none', marker=marker, ms=ms, mew=mew, mec=color, mfc=color if filled else WHITE,
                  label=label)


def legend(target, handles, **kw):
    """Frameless legend; interval handles show both caps."""
    kw.setdefault('handler_map', {Interval: HandlerLine2D(numpoints=2)})
    return target.legend(handles=handles, **kw)


def hspan(ax, lo, hi, y, color=BLACK, lw=1.1, cap=3.0, zorder=3):
    """Horizontal interval with short end caps; a single value is drawn as one cap."""
    if hi != lo:
        ax.plot([lo, hi], [y, y], color=color, lw=lw, zorder=zorder)
    ax.plot([lo, hi] if hi != lo else [lo], [y, y] if hi != lo else [y], ls='none', marker='|', ms=2 * cap, mew=lw,
            color=color, zorder=zorder)


def vspan(ax, x, lo, hi, color=BLACK, lw=1.1, cap=3.0, zorder=3):
    """Vertical interval with short end caps."""
    ax.plot([x, x], [lo, hi], color=color, lw=lw, zorder=zorder)
    ax.plot([x, x], [lo, hi], ls='none', marker='_', ms=2 * cap, mew=lw, color=color, zorder=zorder)


def dot(ax, x, y, marker='o', color=BLACK, filled=True, ms=4.5, mew=.8, zorder=4):
    ax.plot([x], [y], ls='none', marker=marker, ms=ms, mew=mew, mec=color, mfc=color if filled else WHITE,
            zorder=zorder)


def guides(ax, values, axis='y'):
    """Dotted guides across the frame, one for each row (or column) of a dot chart."""
    for v in values:
        (ax.axhline if axis == 'y' else ax.axvline)(v, color=GREY_LIGHT, lw=.5, ls=DOTS, zorder=0)


def criterion(ax, x=None, y=None, **kw):
    """Decision criterion or nominal level: red dashed line."""
    kw = {'color': RED, 'lw': .8, 'ls': DASH, 'zorder': 1, **kw}
    return ax.axvline(x, **kw) if x is not None else ax.axhline(y, **kw)


def limit(ax, x=None, y=None, **kw):
    """Limit, budget or other reference value: grey dashed line."""
    kw = {'color': GREY, 'lw': .8, 'ls': DASH, 'zorder': 1, **kw}
    return ax.axvline(x, **kw) if x is not None else ax.axhline(y, **kw)


def column(ax, x, rows, header=None, header_y=None, ha='right', fontsize=8):
    """A column of values beside the frame: x in axes fractions, y in data coordinates."""
    for y, text in rows:
        ax.text(x, y, text, transform=ax.get_yaxis_transform(), ha=ha, va='center', fontsize=fontsize, clip_on=False)
    if header is not None:
        ax.text(x, header_y, header, transform=ax.get_yaxis_transform(), ha=ha, va='bottom', fontsize=fontsize,
                linespacing=1.15, clip_on=False)


def row_labels(ax, rows, x=-.02, fontsize=8, **kw):
    """Row labels left of the frame, for rows that are not on tick positions."""
    for y, text in rows:
        ax.text(x, y, text, transform=ax.get_yaxis_transform(), ha='right', va='center', fontsize=fontsize,
                linespacing=1.15, clip_on=False, **kw)


def panel(ax, letter, x=0., y=1.03):
    ax.text(x, y, letter, transform=ax.transAxes, ha='left', va='bottom', fontsize=8.5, fontweight='bold')


def check(fig, name):
    """Every text is black, free of forbidden separators and inside the canvas."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    outside, bad = [], []
    for text in fig.findobj(matplotlib.text.Text):
        s = text.get_text()
        if not text.get_visible() or not s.strip():
            continue
        if any(mark in s for mark in FORBIDDEN):
            bad.append(s)
        if to_hex(text.get_color()) != BLACK:
            bad.append(f'non-black text: {s}')
        box = text.get_window_extent(renderer)
        if box.x0 < -1 or box.x1 > fig.bbox.width + 1 or box.y0 < -1 or box.y1 > fig.bbox.height + 1:
            outside.append(s)
    if outside:
        raise SystemExit(f'{name}: text outside the canvas {outside}')
    if bad:
        raise SystemExit(f'{name}: forbidden separator or coloured text in {bad}')
