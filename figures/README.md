# Figures

This folder draws every figure of the article and its supplements with Python (matplotlib):

| Script | Figures |
|---|---|
| `build_main_figures.py` | Figures 1–6 and Supplementary Figures S1–S6 |
| `build_appendix_figures.py` | Figures A.1–A.2, C.1–C.6, D.1–D.8 and the Technical Archive figures TA1–TA3 |

Each script checks every value that a caption or the text prints before it draws, and writes SVG,
PDF and PNG (300 dpi) files; the main figures are also written as TIFF (600 dpi).

## Where the values come from

`build_main_figures.py` reads the numeric records in `data/` and `efsa/`:

| File | Used for |
|---|---|
| `data/madrid_pneumococci.csv` | Figure 1 and Supplementary Figure S1 (published Madrid data) |
| `data/ampicillin_rerun.json` | Figures 3 and 4 and Supplementary Figure S2: the ampicillin bounds of every category before and after the published count, the selected tables and the population bounds, written by `rerun_ampicillin.py` with the installed package. Figure 4 also enumerates all 7938 compatible tables itself and checks that the selected tables of the program are among them |
| `../evaluation/results/sufficient_reporting/tasks.csv` | Figure 5 (180 reporting tasks) |
| `data/figureS2_ampicillin_category.csv` | Supplementary Figure S2; must agree with the rerun file |
| `data/figureS3_chloramphenicol.csv` | Supplementary Figures S3 and S4 |
| `data/figureS5_amikacin.csv` | Supplementary Figure S5 |
| `efsa/` | Figure 6 and Supplementary Figure S6: the public EFSA inputs, the range checks and summary of their replay with the installed package, and the summary of the reporting-cost optimizer |

`build_appendix_figures.py` reads the example inputs (`examples/appendix/inputs/`) and the
evaluation results (`evaluation/results/`) of this repository, and computes the worked examples
with the installed package. `data/AMBIGUITY_WITNESS_CERTIFICATE.json` holds the two witness tables
of Figure C.6.

## Appearance

`figstyle.py` fixes the appearance of all 31 figures, and both scripts import it. Every figure has
a full axes frame with outward ticks, black text in Liberation Sans (symbols such as *n* in its
italic), a white background, and one small palette:

| Colour | Meaning |
|---|---|
| black and greys | what a report states, and reference lines |
| blue `#2166AC` | the same quantity after counts were added; in the table plots, the selected tables |
| red `#B2182B` | decision criteria and nominal levels (dashed lines), or the alternative that fails |
| green `#1B7837` | values known only from the complete data |

Intervals are thin lines with end caps, rows are separated by dotted guides, and methods are told
apart by filled and open symbols. Both scripts stop if any text is not black, lies outside the
canvas or contains a middle-dot or bullet separator.

## Drawing the figures

From the repository root:

```
python -m venv fig-env
fig-env/bin/pip install -r figures/requirements-figures.txt      (Windows: fig-env\Scripts\pip)
fig-env/bin/pip install --no-deps .
fig-env/bin/python figures/build_main_figures.py --out new-figures/main --check figures/EXPECTED_MAIN_FIGURES.json
fig-env/bin/python figures/build_appendix_figures.py --out new-figures/appendix --check figures/EXPECTED_APPENDIX_FIGURES.json
```

Each command ends with `"identical_to_recorded_figures": true` or with a list of differences. PNG
and TIFF files are compared by their decoded pixels, SVG and PDF files byte for byte, and the
plotted values one by one. `--only A1,D3` draws selected appendix figures.

`python figures/rerun_ampicillin.py` recomputes `data/ampicillin_rerun.json` with the installed
package.

## Why the result is identical

- The library versions are pinned in `requirements-figures.txt`; the scripts refuse other versions
  unless `--allow-other-versions` is given.
- Liberation Sans 2.1.5 (regular, bold and italic) is bundled in `fonts/` (SIL Open Font License
  1.1) and is the only font used, whatever fonts the computer has.
- matplotlib starts from a bundled pristine copy of its default settings (`style/`), so a local
  `matplotlibrc` cannot change the appearance.
- The files carry no dates; SVG files use a fixed `hashsalt`, and PDF streams are not compressed,
  so they do not depend on the zlib build.

The recorded files were drawn on Linux with Python 3.13.18 and checked with Python 3.12.3 and
3.14.6; all three gave identical pixels and identical SVG and PDF bytes for all 31 figures.
