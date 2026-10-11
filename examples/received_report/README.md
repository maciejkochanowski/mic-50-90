# Check a received laboratory report

Open the local MIC-50-90 form, choose **Verify a received report**, and load
`certificate.json`. No complete histogram is supplied. The expected conclusion
is that all four recorded-sample questions are supported.

The source is the FDA animal-pathogen AMR collection, NAHLN 2024: 276 canine
E. coli isolates, other tissues/body sites, amikacin. The source categories are
at or below 4, (4,8], (8,16], (16,32] and above 32 mg/L. Ceiling-rank MIC50 and
MIC90 are generated from these published category counts; this example does
not attribute a quantile convention to the source publication.

From these summaries alone each count strictly above 4, 8, 16 or 32 mg/L can
range from 0 to 27. One disclosed count, **8 above 4 mg/L**, fixes the first
count and limits each higher count to at most 8. Because 8/276 is below 5%,
all four sample questions are answered. This does not recover the complete
histogram or establish a population prevalence below 5%.

Verification checks logical sufficiency assuming truthful counts; it does not
authenticate the source. Removing the disclosure makes all four questions
undetermined. `expected.json` records the before/after calculation. The same
cohort is part of the retained sixty-cohort reporting comparison; it is not a
new independent validation set.

Source: https://www.fda.gov/animal-veterinary/national-antimicrobial-resistance-monitoring-system/2017-2024-animal-pathogen-amr-data
