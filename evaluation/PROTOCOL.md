# Evaluation protocol

The data, reports, quantities and criteria below were fixed for the MIC-50-90 1.0.1
confirmation evaluation. The 2026-11-14 reporting amendment corrects the interpretation of
nonrejection and makes simulation uncertainty and denominators explicit. It does not change
the sampling design, test thresholds, held-out data or recorded results. The original protocol
is preserved byte-for-byte in `protocols/PROTOCOL_1_0_1.md`, with its SHA-256 alongside it;
historical result hashes continue to identify that original file. New executions record the
hash of this amended protocol.

Development data select settings and confirmation data evaluate the fixed procedure. Finite
simulation checks test implementation and applicability in the chosen configurations; the
coverage guarantee itself requires a mathematical argument under stated assumptions. The
module-specific interpretation is described in `../docs/VALIDATION_SCOPE.md`.

## 1. Development and confirmation

**Development data** are the twenty cohorts of `data/population_cohorts.json` (ten FDA
animal-pathogen and ten NORM 2024 human cohorts), the FSIS 2020–2021 plant groups and the NARMS
2021 collection blocks (`data/calibration/`). On these data the default construction (Bonferroni
for cumulative questions, range-calibrated for single categories and internal ranges), the
120-second budget, the 0.1-percentage-point endpoint target, the uniform and the trained
transport references and the scoring rule of study-unit calibration were chosen. The scripts
`population_comparison.py`, `coverage_simulation.py`, `complete_tables.py` and `calibration.py`
report these data.

**Confirmation data** are isolate-level public surveillance records that were not used for any
choice: NARMS retail meats (FDA, 2002–2021), NARMS slaughter samples (USDA, 1997–2023), NARMS
cecal samples (USDA FSIS, 2013–2023), NARMS minor species (USDA FSIS, 2020–2022) and the FDA
animal-pathogen data (Vet-LIRN and NAHLN, dogs, 2017–2024). `download_sources.py` fetches the six
files and checks their SHA-256 values; `prepare_benchmark.py` builds every table from them by
the rules below. No setting of the program is changed for the confirmation.

## 2. Complete tables from isolate records

- A record is one isolate and one drug with a sign (`<=`, `=`, `>`) and a value in mg/L. Records
  with other signs, a missing value or growth not recorded as yes are not used.
- A value is placed on the doubling-dilution scale by e = round(log2 value); a value further
  than 0.07 from its log2 step (not a doubling dilution) excludes its panel group.
- A **panel group** is source, agency, genus, year and drug. Its panel runs from L, the lowest
  step recorded, to H, the highest. The categories are `<= 2^L`, then one category per doubling
  step up to `2^H`, then `> 2^H`. A record `<= v` falls in the lowest category and `> v` in the
  highest. The group is excluded when it has more than one `<=` step or more than one `>` step,
  when a `=` value lies below the `<=` step or above the `>` step, or when the panel has fewer
  than 3 or more than 12 categories.
- A **cohort** is a panel group and one host species. It is eligible with 20 to 1000 isolates and
  at least two occupied categories. Cohorts of the FDA animal-pathogen source that share agency,
  year, genus and drug with a development cohort are excluded.
- A **stratum** is source, host species and genus. Within each stratum the eligible cohorts are
  ordered by the SHA-256 of their identifier and the first ten are taken (all, if fewer).

## 3. Reports

Every complete table is shortened in three ways. All use ceiling-rank MIC50 and MIC90.

| Report | Added to MIC50 and MIC90 |
|---|---|
| R1 count | the count of the middle category, index floor(K/2) (the development rule) |
| R2 range | the lowest and the highest occupied category (observed minimum and maximum) |
| R3 percentage | the percentage above the upper limit of the middle category, rounded half up to a whole number |

## 4. Population bounds on confirmation cohorts

`confirmation_population.py`: every cohort and report, 95% simultaneous bounds for every proper
contiguous range, endpoint target 0.1 percentage points, process budget 120 seconds. Bonferroni
and range-calibrated run on R1, R2 and R3; joint-exact and range-hunter on R1. Questions: is the
share below 5%, 10% and 20%; a question is resolved when the interval lies on one side.

Criteria, fixed in advance:

1. *Default rule.* The rule is confirmed when, for R1, Bonferroni has the smaller mean width for
   cumulative ranges in at least 80% of cohorts and range-calibrated has the smaller mean width
   for single categories in at least 80% of cohorts. R2 and R3 are reported the same way.
2. *Endpoint target.* Share of cohorts in which each construction meets the 0.1-point target
   within the budget; median and maximum seconds.
3. *Searching constructions.* Summed-width reduction of joint-exact against Bonferroni and of
   range-hunter against range-calibrated on R1.

## 5. Coverage

A replicate covers when every proper contiguous range contains its population share. For
each fixed configuration and construction, report the numbers of attempted, completed,
failed and covering replicates. The historical `coverage` field is the fraction among
completed replicates; its denominator is explicitly labelled. The additional
`coverage_over_attempted_replicates` includes execution failures in the denominator and
describes availability and containment together. Failed runs must not disappear from the
accounting or be treated as evidence of successful coverage.

Undercoverage of a configuration is detected when the one-sided exact binomial p-value for
coverage >= 95% is strictly below 0.001, retaining the original numerical rejection rule.
If none is detected, the conclusion is **"no undercoverage detected in the examined
configurations"**. Nonrejection does not confirm a guarantee or establish equivalence to
nominal coverage. With execution errors, the assessment is incomplete; a p-value based only
on completed runs does not evaluate the full planned procedure.

For each configuration without execution errors, `coverage_reporting.py` adds a two-sided
95% Clopper-Pearson interval and a labelled plug-in Monte Carlo standard error for its
coverage probability. These are uncertainty measures across independent simulation
replicates, not intervals for MIC population shares. They are pointwise across configurations,
not simultaneous. The plug-in standard error can be zero at all successes or all failures;
the exact interval still retains finite-simulation uncertainty. No ordinary binomial interval
is assigned to the pooled fraction across heterogeneous configurations. The original
per-configuration diagnostic threshold is not a familywise error claim across configurations.

At true coverage 94% rather than 95%, this level-0.001 test has power only 3.93% with 1000
replicates and 13.99% with 2000 replicates (exact binomial calculation for one configuration).
These numbers describe sensitivity of the diagnostic, not the actual coverage of the program.

Random numbers: `numpy.random.default_rng([seed, generator, configuration, replicate])`, so
any replicate can be recomputed alone. The simulation design treats the specified shares
as a population and draws iid samples; it does not establish iid sampling in the surveillance
data from which some population shares were constructed.

**G1 Resampling** (`confirmation_coverage.py`): each confirmation cohort is the population;
2000 replicates per cohort and report, sample size the cohort's n, shortened as R1, R2 or R3.

**Synthetic populations** (`synthetic_coverage.py`), sample sizes n = 10, 30, 100, 300, 1000,
panels with K = 3, 5, 8 and 12 categories, reports R1, R2 and R3, 1000 replicates each:

- **G2 Mixture.** log2 MIC follows a wild-type normal component (standard deviation 0.5 or 1
  dilution, centred one step above the lowest category) and, with weight 0, 0.05, 0.2 or 0.5, a
  non-wild-type component 3 or 6 dilutions higher with the same spread; the probability of a
  category is the probability of its log2 interval.
- **G3 Dirichlet.** Category probabilities drawn from a symmetric Dirichlet distribution with
  concentration 0.3, 1 or 3; three populations per concentration.
- **G4 Rare categories.** A Dirichlet(1) population in which one or two categories are set to an
  expected count of 0.5, 2 or 5 isolates at the given n, the rest rescaled.

## 6. Study-unit calibration on later data

`external_calibration.py`. A unit is a state within one year (a state-year). Each dataset has
a training year T, a calibration year C and a test year V = C + 1 = T + 2; no unit-year enters
two roles. The same states can recur across years. This is temporal validation within a
monitoring system, not validation on independent geographic units or in an independent
monitoring system. Different year labels do not by themselves establish exchangeability or
remove dependence and drift.

| Dataset | Source |
|---|---|
| Dogs, *E. coli* | FDA animal pathogens |
| Dogs, *S. pseudintermedius* | FDA animal pathogens |
| Retail meats, *Salmonella*, *Campylobacter*, *E. coli*, *Enterococcus* | NARMS retail meats |

- Drugs: those whose panel (L, H) is the same in T, C and V. A unit enters a role when it has at
  least five isolates for every included drug in that year.
- Years and agency: the latest three consecutive years with at least three such drugs and at
  least nine units in every role; among agencies, the one with more units in year C. These
  choices use only panels and unit counts, never an outcome.
- Level: 95% when there are at least 19 calibration units, otherwise 90% when there are at least
  nine; a dataset with fewer than nine is reported as not evaluable.
- Both references are applied and reported: *uniform* (equal weight on every panel category,
  no training data) and *trained* (the `calibration-prepare` command on year T units, with
  training-only transport scaling).
- The calibrated intervals for year V are produced by the public `batch` command from MIC50 and
  MIC90 alone. A unit is covered when every tail of every included drug lies inside its interval.

The denominator for that simultaneous event is the number of intended test units, not the
number of individual tails. The unchanged retail *E. coli* check uses training 2017,
calibration 2018 and test 2019, with the same 13 states in calibration and test. The recorded
trained and uniform references cover 8/13 and 11/13 test units respectively at a manifest
level of 13/14 (92.86%), the discrete rank level corresponding to the requested 90%.
Their individual-target counts, 1099/1105 and 1101/1105, answer a
different question and cannot replace the whole-unit results. These adverse outcomes remain
reported. Changing or selecting the procedure after inspecting 2019 would require a new
independent assessment; 2019 cannot be reused as untouched confirmation of that change.

**Synthetic units.** Each repetition draws units, calibrates on M units with the uniform reference
and tests on 100 new units; 200 repetitions per setting; M = 19 and 39, both at 95%. Unit sizes are 20, 50 or 100
isolates with equal probability; the panel has six categories.

- **SU1 Exchangeable.** Unit probabilities are Dirichlet(c p0) with c = 20 or 100 around the G2
  population p0 (spread 0.75, non-wild-type weight 0.2, shift 4 dilutions).
- **SU2 Drift.** Calibration units as in SU1; test units around p0 with the non-wild-type weight
  raised by 0.05, 0.1 or 0.2, or with the whole distribution shifted one dilution up.
- **SU3 Other generator.** Calibration units as in SU1; test units from the G2 model with a
  unit-level wild-type centre drawn from a normal distribution (standard deviation 0.5 dilution).

For SU1 the expected coverage of a new unit is at least the nominal level; SU2 and SU3 measure
how coverage changes when the test units are not exchangeable with the calibration units.
The independent replication unit for uncertainty about this fitted procedure is the whole
calibration-and-test repetition. Its 100 test units share a fitted calibration. Existing
pooled fractions and the lowest/highest repetition are descriptive; they are not binomial
Monte Carlo intervals based on 100 times the repetition count.

## 7. Reporting

`summarize.py` collects every number. Development and confirmation results are reported side by
side with their criteria; no result is omitted, and a criterion that is not met is reported as
not met.
