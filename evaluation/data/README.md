# Evaluation inputs

These files are the only inputs of the evaluation scripts. They are derived count tables, not the
source workbooks or reports. All are UTF-8 text. Total size is under 1 MB.

## Files

| File | Content | Used by |
|---|---|---|
| `population_cohorts.json` | 20 cohorts. For each: `counts`, the complete grouped table of the cohort, and `input`, the incomplete report given to the program (n, panel, ceiling-rank MIC50 and MIC90, one disclosed category count). The order is fixed; the coverage simulation uses the position of a cohort in its random seed. | population comparison, coverage simulation, complete tables |
| `reporting_cohorts.json` | 60 complete-category drug cohorts (30 FDA, 30 NORM). For each: the histogram and the specification (panel, n, ceiling-rank MIC50 and MIC90, thresholds). | sufficient reporting |
| `controlled_reports.json` | 144 constructed histograms with an information pattern (summaries only, two cumulative counts, one interior count). K = 5 or 8 categories, n = 10, 20, 50 or 100, six profiles. No source data. | controlled reports |
| `calibration/panels.json` | The 14 CMV5AGNF drug panels: every tested level plus the censored end categories. | calibration |
| `calibration/narms_histograms.jsonl` | 266 NARMS cohorts (19 collection blocks x 14 drugs) with the fixed split into training, calibration and test blocks. | calibration |
| `calibration/fsis_histograms.jsonl` | 686 FSIS cohorts (49 plant groups, establishments under one owner, with at least five isolates x 14 drugs). | calibration |
| `calibration/fsis_split.csv` | The fixed assignment of the 49 groups: 19 calibration, 30 test. | calibration |
| `calibration/fsis_panels.csv` | The same panels in the CSV form read by the `batch` command. | calibration |
| `calibration/fsis_uniform_references.json` | The fixed uniform reference of each drug panel. | calibration |
| `calibration/trained_counts.csv`, `trained_roster.csv`, `trained_metadata.json` | Inputs of the `calibration-prepare` command for the trained reference: NARMS training tables and FSIS calibration tables (no test table), the unit roster and the metadata. | calibration |

## Sources

**FDA animal pathogens.** U.S. Food and Drug Administration, 2017–2024 Animal Pathogen AMR Data
(Vet-LIRN and NAHLN isolates from dogs),
<https://www.fda.gov/animal-veterinary/national-antimicrobial-resistance-monitoring-system/2017-2024-animal-pathogen-amr-data>.
Each cohort is one source, year, organism, host, body site and drug. Adjacent MIC categories are
merged into at most five groups as shown in each panel. The cohort identifier names the source row.

**NORM 2024.** NORM/NORM-VET 2024, the Norwegian report on antimicrobial use and resistance,
<https://www.fhi.no/contentassets/00f0b4a7a3d242c89b931c3badefdaf3/norm-norm-vet-2024-komplett.pdf>.
Only integer count tables reconstructed from the MIC distribution tables are kept (the table number
is part of the cohort identifier, for example `NORM2024|T88|Cefotaxime`). A percentage table was
used only when its stated precision allowed exactly one integer count in every cell and the counts
summed to n. The report itself is not redistributed.

**NARMS retail meat 2021.** FDA NARMS retail-meat isolate workbook (Integrated Reports/Summaries
page of the FDA NARMS website), 2021, *Salmonella enterica*, growth = yes. Isolates are grouped into
collection blocks of a collecting region or laboratory (CA+HI, SD+ND and TX+OK merged); blocks with
fewer than 20 isolates are excluded (19 blocks, 970 isolates). The split into 4 training, 9
calibration and 6 test blocks follows the ascending SHA-256 of the block identifier.

**FSIS raw poultry 2020–2021.** USDA Food Safety and Inspection Service raw-poultry *Salmonella*
isolates linked to their FDA NARMS MIC records. Establishments under one owner form one plant group,
pooled over years and projects. Groups with at least five isolates (49) are split by the
ascending SHA-256 of the group identifier into 19 calibration and 30 test groups.

**Panels.** CMV5AGNF was assigned for 2020–2021 NARMS *Salmonella* testing following the NARMS
investigators' article in Microbiology Spectrum, doi:10.1128/spectrum.03485-23 (Materials and Methods). Concentration grids are from the Thermo
Fisher Sensititre U.S. plate guide (printed page 52) and the FDA concentration table
(<https://www.fda.gov/media/108187/download>). The assignment is a program-year assignment, not
a check of each plate lot.

## Terms

FDA, NARMS and FSIS data are U.S. federal public data. Keep the attribution to the agencies above;
nothing here implies their endorsement. The NORM counts are factual values taken from a public
Norwegian report; cite the report when you reuse them. The constructed controlled reports carry
the MIT license of the software. The derived tables do not change the terms of their sources.
