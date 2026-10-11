# Find and use additional information in a published MIC table

MIC-50-90 1.0.0. These examples use original aggregate counts from four independent publications. They describe the assayed isolates in two or three broad MIC groups. They do not reconstruct the full assay panel or claim treatment susceptibility.

## Start with the published count

```console
mic-50-90 distribution examples/publication_review/cefiderocol-25-counts.json --output-dir output/cefiderocol-25 --fail-on-refusal
```

Open `output/cefiderocol-25/report.html`. The paper reports 24 of 25 OXA-232-producing K. pneumoniae isolates at or below 4 mg/L. Therefore one isolate, or 4%, is above 4 mg/L. The chart shows these two groups; it cannot locate each isolate within its group.

| File prefix | Published information | Answer in the original sample | Primary source |
|---|---|---|---|
| cefiderocol-25 | 24 of 25 <=4 mg/L | 1/25 >4 mg/L, 4.00% | [Tables 2–3](https://doi.org/10.3390/antibiotics15090844) |
| doxycycline-68 | 65 of 68 >=16 mg/L | 65/68 >=16 mg/L, 95.59% | [Table 1; Supplementary Table S4](https://doi.org/10.3390/antibiotics15090933) |
| ampicillin-227 | 18 of 227 >=2 mg/L | 18/227 >=2 mg/L, 7.93% | [Table 1](https://doi.org/10.1016/j.onehlt.2026.101453) |
| penicillin-21 | 2 of 21 >=2 mg/L | 2/21 >=2 mg/L, 9.52% | [Tables 4–6](https://doi.org/10.3390/vetsci9040173) |

For penicillin G the second available count, 19 values <=0.5 mg/L, also identifies the intermediate broad group: 19, 0 and 2 isolates in <=0.5, (0.5,2) and >=2 mg/L, respectively.

Replace the filename in the command with any `*-counts.json` above. The reports use counts only and do not assume a quantile convention. All examples leave population inference off: a source table does not itself establish independent, identically distributed sampling. In the 21-isolate example, repeated observations from 14 cows are explicitly documented.

## See what one extra count adds

The `*-conditional-before.json` files map the published MIC50/MIC90 to the same broad groups under **analyst-declared ceiling ranks**. The `*-conditional-after.json` files add the exact published count. These are conditional comparisons; the original papers have not all confirmed this rank convention.

| Isolates and group | Summaries under ceiling ranks | Same summaries plus the count |
|---|---:|---:|
| 25; MIC >4 | 0–2 | 1 |
| 68; MIC >=16 | 35–68 | 65 |
| 227; MIC >=2 | 0–22 | 18 |
| 21; MIC >=2 | 0–2 | 2 |

Run a before/after comparison while retaining the same sample:

```console
mic-50-90 distribution examples/publication_review/doxycycline-68-conditional-before.json --output-dir output/doxycycline-before
mic-50-90 distribution examples/publication_review/doxycycline-68-conditional-after.json --previous-output output/doxycycline-before --output-dir output/doxycycline-after
```

The second report shows both stages. The additional count reduces missing information about these 68 isolates. It does not increase the sample size or prove that the population proportion is exactly 95.59%.

## A conflict that needs source clarification

`amikacin-14-conflict.json` retains a real source inconsistency under ceiling ranks: MIC90=4 in 14 isolates allows at most one value above 4, whereas two values are reported >=16. The prepared input is expected to be refused. Do not change the denominator or silently discard a source value to force a numerical answer.

The complete extraction register, inspected-supplement descriptions and source hashes are in `results/v1.0.0/publication-methods-20261001/`. Fourteen previously examined papers and 16 newly extracted papers make up its purposive 30-paper review. These examples are demonstrations of using published data, not a human usability study or evidence of a new statistical method.
