# Figures

This folder draws every figure of the article and its supplements with Python (matplotlib):

| Script | Figures |
|---|---|
| `build_main_figures.py` | Figures 1–6 and Supplementary Figures S1–S4 |
| `build_appendix_figures.py` | Figures A.1–A.2, C.1–C.6, D.1–D.8 and the Technical Archive figures TA1–TA3 |

Each script checks every value that a caption or the text prints before it draws, and writes SVG,
PDF and PNG (300 dpi) files; the main figures are also written as TIFF (600 dpi).

## Where the values come from

`build_main_figures.py` reads the numeric records in `data/` and `efsa/`:

| File | Used for |
|---|---|
| `data/madrid_pneumococci.csv` | Figure 1 and Supplementary Figure S1 (published Madrid data) |
| `data/figure3_ampicillin.csv`, `data/ampicillin_rerun.json` | Figure 3; the rerun file is written by `rerun_ampicillin.py` with the installed package and must agree with the CSV file |
| `data/figure4_chloramphenicol.csv` | Figure 4 |
| `data/figure5_amikacin.csv` | Figure 5 |
| `data/figureS2_ampicillin.csv` | Supplementary Figure S2 |
| `efsa/` | Figure 6 and Supplementary Figure S4: the public EFSA inputs, the range checks and summary of their replay with the installed package, and the summary of the reporting-cost optimizer |

`build_appendix_figures.py` reads the example inputs (`examples/appendix/inputs/`) and the
evaluation results (`evaluation/results/`) of this repository, and computes the worked examples
with the installed package. `data/AMBIGUITY_WITNESS_CERTIFICATE.json` holds the two witness tables
of Figure C.6.

## Appearance

The main figures use black text, greys and two muted accents: blue `#2F5D7C` (with the light
background `#E4ECF1` and the darker `#1F3447`) and ochre `#9A5B3E` for criterion lines; the script
stops if any text is not black. The appendix figures use near-black `#1F1F1F`, greys, orange
`#CC6A10` and blue `#1F5C99`. No figure text uses middle-dot or bullet separators, and both scripts
stop if one appears.

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
- Liberation Sans 2.1.5 is bundled in `fonts/` (SIL Open Font License 1.1) and is the only font
  used, whatever fonts the computer has.
- matplotlib starts from a bundled pristine copy of its default settings (`style/`), so a local
  `matplotlibrc` cannot change the appearance.
- The files carry no dates; SVG files use a fixed `hashsalt`, and PDF streams are not compressed,
  so they do not depend on the zlib build.

The recorded files were drawn on Linux with Python 3.12.13 and checked with Python 3.14.6; both
gave identical pixels and identical SVG and PDF bytes for all 29 figures.
