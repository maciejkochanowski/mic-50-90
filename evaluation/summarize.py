"""Collect the numbers reported in the article from the comparison outputs.

These are the numbers of the evaluation reported in Section 2.5 and Appendix D of the article:
the development comparisons (Appendix D.1, D.3, D.4, D.8 and D.9; Technical Archive T7.3-T7.8),
the confirmation on independent data (Appendix D.5 and D.8, Technical Archive T7.10) and the finite
controls of the Technical Archive (T7.5, T7.6 and T8.2). Development and confirmation results are
listed side by side (PROTOCOL.md, section 7).

Reads OUTPUT/<comparison>/summary.json for every comparison that has been run and writes
OUTPUT/SUMMARY.json and CSV tables in OUTPUT/tables/. Each number is listed with the value given
in the article and a status:

  match        the reproduced value equals the article value at the article's precision (for a
               stated upper bound: does not exceed it);
  differs      it does not (see the comparison's summary.json for details);
  timing       a time in seconds; it depends on the machine and is shown for information;
  reduced run  the comparison was run with reduced settings, so the value is not comparable;
  not run      the comparison has no output yet.
"""
from __future__ import annotations

import common

import json
from decimal import ROUND_HALF_UP, Decimal

from common import now, read_json, write_csv, write_json

COMPARISONS = ('population', 'coverage', 'complete_tables', 'controlled_reports', 'sufficient_reporting', 'calibration', 'pba_comparison',
               'reporting_controls', 'planning_controls', 'count_extrema', 'population_controls', 'confirmation_population',
               'confirmation_coverage', 'synthetic_coverage', 'external_calibration', 'endpoint_selection', 'examples',
               'next_count/confirmation', 'next_count/development', 'next_count/benchmark')
NAMES = {'bonferroni': 'Bonferroni', 'joint-exact': 'joint-exact', 'range-calibrated': 'range-calibrated', 'range-hunter': 'range-hunter'}

# (comparison, quantity, value in the article, path in summary.json, scale, kind)
ARTICLE = [
    *[row for method, values in {
        'bonferroni': ('28.617', '309', '29.730', '67', '31.734', '440', '20', '0.214'),
        'joint-exact': ('28.481', '309', '29.466', '67', '31.571', '440', '0', '115.627'),
        'range-calibrated': ('29.731', '303', '26.073', '84', '31.247', '454', '20', '0.108'),
        'range-hunter': ('29.739', '303', '25.993', '84', '31.236', '454', '0', '115.103')}.items()
      for row in (
        ('population', f'{NAMES[method]}: mean width, cumulative ranges (pp)', values[0], f'constructions/{method}/cumulative/mean_width_pp', 1, 'value'),
        ('population', f'{NAMES[method]}: resolved questions, cumulative ranges (of 480)', values[1], f'constructions/{method}/cumulative/resolved_questions', 1, 'value'),
        ('population', f'{NAMES[method]}: mean width, single categories (pp)', values[2], f'constructions/{method}/single/mean_width_pp', 1, 'value'),
        ('population', f'{NAMES[method]}: resolved questions, single categories (of 180)', values[3], f'constructions/{method}/single/resolved_questions', 1, 'value'),
        ('population', f'{NAMES[method]}: mean width, all ranges (pp)', values[4], f'constructions/{method}/all/mean_width_pp', 1, 'value'),
        ('population', f'{NAMES[method]}: resolved questions, all ranges (of 840)', values[5], f'constructions/{method}/all/resolved_questions', 1, 'value'),
        ('population', f'{NAMES[method]}: cohorts meeting the endpoint target (of 20)', values[6], f'constructions/{method}/cohorts_meeting_endpoint_target', 1, 'value'),
        ('population', f'{NAMES[method]}: median seconds per cohort', values[7], f'constructions/{method}/median_seconds', 1, 'timing'))],
    ('population', 'Bonferroni narrower than range-calibrated for cumulative ranges (cohorts of 20)', '20', 'pair:bonferroni:range-calibrated/cumulative/wider', 1, 'value'),
    ('population', 'range-calibrated narrower than Bonferroni for single categories (cohorts of 20)', '20', 'pair:bonferroni:range-calibrated/single/narrower', 1, 'value'),
    ('population', 'range-calibrated narrower than Bonferroni for internal ranges (cohorts of 20)', '15', 'pair:bonferroni:range-calibrated/internal/narrower', 1, 'value'),
    ('population', 'joint-exact: summed-width reduction against Bonferroni (%)', '0.513', 'pair:bonferroni:joint-exact/summed_width_reduction_percent', 1, 'value'),
    ('population', 'range-hunter: summed-width reduction against range-calibrated (%)', '0.033', 'pair:range-calibrated:range-hunter/summed_width_reduction_percent', 1, 'value'),
    ('coverage', 'Bonferroni: replicates', '100000', 'totals/bonferroni/replicates', 1, 'value'),
    ('coverage', 'Bonferroni: covered replicates', '99845', 'totals/bonferroni/covered', 1, 'value'),
    ('coverage', 'Bonferroni: lowest cohort coverage (%)', '99.44', 'totals/bonferroni/lowest_cohort_coverage', 100, 'value'),
    ('coverage', 'range-calibrated: replicates', '100000', 'totals/range-calibrated/replicates', 1, 'value'),
    ('coverage', 'range-calibrated: covered replicates', '99828', 'totals/range-calibrated/covered', 1, 'value'),
    ('coverage', 'range-calibrated: lowest cohort coverage (%)', '99.40', 'totals/range-calibrated/lowest_cohort_coverage', 100, 'value'),
    ('complete_tables', 'Bonferroni: mean width from the incomplete reports (pp)', '31.73', 'summary/bonferroni/mean_width_report_pp', 1, 'value'),
    ('complete_tables', 'Bonferroni: mean width from the complete tables (pp)', '10.62', 'summary/bonferroni/mean_width_complete_pp', 1, 'value'),
    ('complete_tables', 'Bonferroni: median width ratio, report to complete table', '3.7', 'summary/bonferroni/median_width_ratio', 1, 'value'),
    ('complete_tables', 'range-calibrated: mean width from the incomplete reports (pp)', '31.25', 'summary/range-calibrated/mean_width_report_pp', 1, 'value'),
    ('complete_tables', 'range-calibrated: mean width from the complete tables (pp)', '9.59', 'summary/range-calibrated/mean_width_complete_pp', 1, 'value'),
    ('complete_tables', 'range-calibrated: median width ratio, report to complete table', '4.71', 'summary/range-calibrated/median_width_ratio', 1, 'value'),
    ('controlled_reports', 'controlled reports', '144', 'cutoff_comparison/reports', 1, 'value'),
    ('controlled_reports', 'proper-range projections', '3528', 'cutoff_comparison/proper_range_projections', 1, 'value'),
    ('controlled_reports', 'aggregate width reduction, range-calibrated against Bonferroni cutoff (%)', '0.416', 'cutoff_comparison/aggregate_relative_reduction_percent', 1, 'value'),
    ('controlled_reports', 'reports with narrower bounds', '90', 'cutoff_comparison/narrower', 1, 'value'),
    ('controlled_reports', 'reports with equal bounds', '54', 'cutoff_comparison/equal', 1, 'value'),
    ('controlled_reports', 'reports whose endpoints are confirmed', '144', 'endpoint_checks/confirmed', 1, 'value'),
    ('controlled_reports', 'confirmed by the shape condition', '142', 'endpoint_checks/shape_condition', 1, 'value'),
    ('controlled_reports', 'confirmed by direct witnesses', '2', 'endpoint_checks/direct_witness', 1, 'value'),
    ('controlled_reports', 'deterministic probes confirmed (of 15)', '15', 'scaling_probes/confirmed', 1, 'value'),
    ('controlled_reports', 'largest probe sample size', '1000', 'scaling_probes/maximum_n', 1, 'value'),
    ('controlled_reports', 'largest probe category count', '16', 'scaling_probes/maximum_k', 1, 'value'),
    ('sufficient_reporting', 'drug cohorts', '60', 'cohorts', 1, 'value'),
    ('sufficient_reporting', 'tasks', '180', 'totals/tasks', 1, 'value'),
    ('sufficient_reporting', 'threshold answers', '1809', 'totals/answers', 1, 'value'),
    ('sufficient_reporting', 'counts sent by direct reporting', '405', 'totals/direct_fields', 1, 'value'),
    ('sufficient_reporting', 'counts in the minimal sufficient reports', '115', 'totals/minimal_fields', 1, 'value'),
    ('sufficient_reporting', 'answers preserved by every rule', '1809', 'totals/answers_preserved', 1, 'value'),
    ('sufficient_reporting', 'tasks resolved by the summaries alone', '95', 'totals/summaries_only', 1, 'value'),
    ('sufficient_reporting', 'tasks needing counts', '85', 'totals/needing_counts', 1, 'value'),
    ('sufficient_reporting', 'tasks needing fewer counts than direct reporting', '58', 'totals/fewer', 1, 'value'),
    ('sufficient_reporting', 'tasks needing the same number of counts', '27', 'totals/same', 1, 'value'),
    ('sufficient_reporting', 'counts kept by greedy deletion', '115', 'totals/greedy_fields', 1, 'value'),
    ('sufficient_reporting', 'unequal-cost example: minimal report cost', '1', 'unequal_cost_example/minimal_cost', 1, 'value'),
    ('sufficient_reporting', 'unequal-cost example: greedy deletion cost', '10', 'unequal_cost_example/greedy_cost', 1, 'value'),
    ('calibration', 'NARMS: test blocks covered', '5', 'parts/narms/test_blocks_covered', 1, 'value'),
    ('calibration', 'NARMS: test blocks', '6', 'parts/narms/test_blocks', 1, 'value'),
    ('calibration', 'FSIS: calibration groups', '19', 'parts/fsis-uniform/calibration_groups', 1, 'value'),
    ('calibration', 'FSIS: evaluation groups', '30', 'parts/fsis-uniform/test_groups', 1, 'value'),
    ('calibration', 'FSIS uniform scaling: groups covered (of 30)', '27', 'parts/fsis-uniform/test_groups_covered', 1, 'value'),
    ('calibration', 'FSIS trained scaling: groups covered (of 30)', '30', 'parts/fsis-trained/test_groups_covered', 1, 'value'),
    ('calibration', 'FSIS trained scaling: mean width (pp)', '14.5639', 'parts/fsis-trained/mean_width_pp', 1, 'value'),
    ('calibration', 'FSIS uniform scaling: mean width (pp)', '15.2127', 'parts/fsis-uniform/mean_width_pp', 1, 'value'),
    ('pba_comparison', 'feasibility decisions', '8800', 'counts/tasks', 1, 'value'),
    ('pba_comparison', 'feasibility decisions where PBA agrees', '8800', 'counts/pba_feasibility_matches', 1, 'value'),
    ('pba_comparison', 'feasibility decisions where mic-50-90 agrees', '8800', 'counts/package_feasibility_matches', 1, 'value'),
    ('pba_comparison', 'sample intervals', '17658', 'counts/target_comparisons', 1, 'value'),
    ('pba_comparison', 'sample intervals where PBA agrees', '17658', 'counts/pba_endpoint_matches', 1, 'value'),
    ('pba_comparison', 'sample intervals where mic-50-90 agrees', '17658', 'counts/package_endpoint_matches', 1, 'value'),
    ('reporting_controls', 'finite cases', '5016', 'counts/cases', 1, 'value'),
    ('reporting_controls', 'cases where oracle and package agree', '5016', 'counts/agreements', 1, 'value'),
    ('reporting_controls', 'common-boundary cases', '4716', 'counts/common_boundary', 1, 'value'),
    ('reporting_controls', 'fixed-seed cases with variant unions', '300', 'counts/variant', 1, 'value'),
    ('reporting_controls', 'impossible-disclosure cases', '132', 'counts/impossible', 1, 'value'),
    ('reporting_controls', 'impossible-disclosure cases correctly identified', '132', 'counts/impossible_identified', 1, 'value'),
    ('planning_controls', 'controlled tasks', '2400', 'controlled/tasks', 1, 'value'),
    ('planning_controls', 'controlled tasks where oracle and package agree', '2400', 'controlled/agreements', 1, 'value'),
    ('planning_controls', 'controlled: already resolved', '2064', 'controlled/status_counts/already_resolved', 1, 'value'),
    ('planning_controls', 'controlled: nonzero optimal plan', '196', 'controlled/status_counts/optimal', 1, 'value'),
    ('planning_controls', 'controlled: impossible under the allowed cuts', '140', 'controlled/status_counts/impossible', 1, 'value'),
    ('planning_controls', 'controlled: checked finite-policy histogram paths', '8828', 'controlled/checked_histogram_paths', 1, 'value'),
    ('planning_controls', 'controlled: checked impossibility witnesses', '140', 'controlled/checked_witnesses', 1, 'value'),
    ('planning_controls', 'stress cases', '128', 'stress/tasks', 1, 'value'),
    ('planning_controls', 'stress cases where oracle and package agree', '128', 'stress/agreements', 1, 'value'),
    ('planning_controls', 'stress: already resolved', '49', 'stress/status_counts/already_resolved', 1, 'value'),
    ('planning_controls', 'stress: optimal', '62', 'stress/status_counts/optimal', 1, 'value'),
    ('planning_controls', 'stress: impossible', '17', 'stress/status_counts/impossible', 1, 'value'),
    ('planning_controls', 'stress: checked histogram paths', '1015', 'stress/checked_histogram_paths', 1, 'value'),
    ('planning_controls', 'stress: checked impossibility witnesses', '17', 'stress/checked_witnesses', 1, 'value'),
    ('planning_controls', 'input/contract controls', '31', 'contract/controls', 1, 'value'),
    ('planning_controls', 'input/contract controls passing', '31', 'contract/passed', 1, 'value'),
    ('count_extrema', 'nonempty reports', '268', 'counts/nonempty_reports', 1, 'value'),
    ('count_extrema', 'P5 rows', '1182', 'counts/P5_rows', 1, 'value'),
    ('count_extrema', 'range-endpoint pairs', '2086', 'counts/range_endpoint_pairs', 1, 'value'),
    ('count_extrema', 'seeded reports with additional counts', '160', 'counts/augmented_reports', 1, 'value'),
    ('count_extrema', 'objective pairs with additional counts', '720', 'counts/augmented_objective_pairs', 1, 'value'),
    ('count_extrema', 'feasibility decisions', '154', 'counts/feasibility_decisions', 1, 'value'),
    ('count_extrema', 'infeasible reports', '50', 'counts/infeasible_reports', 1, 'value'),
    ('count_extrema', 'failed checks', '0', 'failed_checks', 1, 'value'),
    ('population_controls', 'population projection pairs', '2832', 'counts/projection_pairs', 1, 'value'),
    ('population_controls', 'maximum absolute fraction difference (x 10^-12, rounded upward; bound)', '2.001',
     'maximum_absolute_difference_e12_rounded_up', 1, 'bound'),
    ('population_controls', 'zero-budget projection pairs keeping the conservative result', '1416', 'counts/zero_budget_projection_pairs', 1, 'value'),
    ('population_controls', 'probability witness queries', '267', 'counts/probability_witness_queries', 1, 'value'),
    ('population_controls', 'probability witnesses returned', '222', 'counts/probability_witnesses_returned', 1, 'value'),
    ('population_controls', 'accepted-range checks', '747', 'counts/accepted_probability_range_checks', 1, 'value'),
    ('population_controls', 'failed checks', '0', 'failed_checks', 1, 'value'),
    *[row for block, values in {
        'confirmation': ('601', '3570', '84.2', '55.3', '1353', '3482', '3002', '16.7', '86.3', '4171', '3570'),
        'development': ('545', '3324', '83.8', '55.3', '1226', '3270', '2802', '16.7', '86.1', '3869', '3324'),
        'benchmark': ('610', '3599', '84.8', '55.4', '1404', '3507', '3057', '17.6', '87.3', '4209', '3599')}.items()
      for row in (
        (f'next_count/{block}', f'count to request, {block} block: cohorts', values[0], 'cohorts', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: open categories (tasks)', values[1], 'all_tasks/tasks', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: median narrowing (%)', values[2], 'all_tasks/relative_reduction/median', 100, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: lower quartile of the narrowing (%)', values[3], 'all_tasks/relative_reduction/lower_quartile', 100, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: categories fixed exactly', values[4], 'all_tasks/fixed_exactly', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: tasks with more than one candidate', values[5], 'all_tasks/tasks_with_alternatives', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: tasks in which no other count narrows more', values[6], 'all_tasks/no_alternative_narrower', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: median narrowing by the other counts (%)', values[7], 'all_tasks/mean_alternative_reduction/median', 100, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: median narrowing by the best single count (%)', values[8], 'all_tasks/best_single_count_relative_reduction/median', 100, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: sets of bounds compared with the independent calculation', values[9], 'independent_check/bound_comparisons', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: sets of bounds that differ', '0', 'independent_check/bound_mismatches', 1, 'value'),
        (f'next_count/{block}', f'count to request, {block} block: tasks in which the program names the count of the rule', values[10], 'independent_check/suggestion_follows_the_rule', 1, 'value'))],
    ('next_count/confirmation', 'count to request, confirmation block: tasks with a guaranteed narrowing', '1781', 'selection_rule/guaranteed', 1, 'value'),
    ('next_count/confirmation', 'count to request, confirmation block: tasks without a guaranteed narrowing', '1789', 'selection_rule/average', 1, 'value'),
    ('next_count/confirmation', 'count to request, confirmation block: median narrowing without a guarantee (%)', '62.5', 'by_rule/average/relative_reduction/median', 100, 'value'),
    ('next_count/confirmation', 'count to request, confirmation block: median narrowing, cohorts with equal weight (%)', '77.6', 'cohorts_equal_weight/relative_reduction/median', 100, 'value'),
]

CONFIRMATION_WIDTHS = {  # Appendix D, Table D.5: mean width (pp) for cumulative, single and internal ranges
    'bonferroni|R1': ('40.14', '42.85', '56.99'), 'range-calibrated|R1': ('42.20', '40.63', '55.00'),
    'bonferroni|R2': ('38.64', '46.25', '55.13'), 'range-calibrated|R2': ('40.60', '45.84', '53.38'),
    'bonferroni|R3': ('33.39', '40.21', '54.06'), 'range-calibrated|R3': ('35.46', '39.08', '51.78')}
CONFIRMATION_MEDIANS = {  # Appendix D, Table D.5: median seconds per cohort
    'bonferroni|R1': '0.170', 'range-calibrated|R1': '0.173', 'bonferroni|R2': '0.043', 'range-calibrated|R2': '0.147',
    'bonferroni|R3': '0.056', 'range-calibrated|R3': '0.183'}
NARROWER = {'R1': ('534', '426'), 'R2': ('303', '426'), 'R3': ('378', '456')}  # range-calibrated narrower: single, internal
CALIBRATION = {'dogs-ecoli': ('20', '19'), 'dogs-spseud': ('18', '18'), 'retail-salmonella': ('19', '21'),
               'retail-campylobacter': ('18', '18'), 'retail-ecoli': ('11', '8'), 'retail-enterococcus': ('17', '17')}
SYNTHETIC_UNITS = {'c=20|M=19': ('95.66', '96.68', '97.67', '99.04', '99.84', '92.91'),
                   'c=20|M=39': ('95.74', '96.67', '97.89', '99.13', '99.93', '92.35'),
                   'c=100|M=19': ('95.99', '98.03', '98.98', '99.79', '99.99', '89.78'),
                   'c=100|M=39': ('95.48', '97.76', '98.92', '99.77', '99.99', '88.45')}
SU = ('SU1', 'SU2|weight=0.05', 'SU2|weight=0.1', 'SU2|weight=0.2', 'SU2|shift_all=1', 'SU3')
ARTICLE += [
    *[row for key, values in CONFIRMATION_WIDTHS.items() for row in (
        ('confirmation_population', f'{key}: cohorts meeting the endpoint target (of 610)', '610', f'constructions/{key}/meeting_endpoint_target', 1, 'value'),
        *[('confirmation_population', f'{key}: mean width, {kind} ranges (pp)', value, f'constructions/{key}/{kind}/mean_width_pp', 1, 'value')
          for kind, value in zip(('cumulative', 'single', 'internal'), values)],
        ('confirmation_population', f'{key}: median seconds per cohort', CONFIRMATION_MEDIANS[key], f'constructions/{key}/median_seconds', 1, 'timing'))],
    ('confirmation_population', 'bonferroni|R1: maximum seconds per cohort', '5.66', 'constructions/bonferroni|R1/maximum_seconds', 1, 'timing'),
    ('confirmation_population', 'joint-exact|R1: cohorts meeting the endpoint target', '1', 'constructions/joint-exact|R1/meeting_endpoint_target', 1, 'value'),
    ('confirmation_population', 'range-hunter|R1: cohorts meeting the endpoint target', '2', 'constructions/range-hunter|R1/meeting_endpoint_target', 1, 'value'),
    *[row for report, (single, internal) in NARROWER.items() for row in (
        ('confirmation_population', f'{report}: range-calibrated narrower for cumulative ranges (cohorts of 610)', '0',
         f'pair:bonferroni:range-calibrated:{report}/cumulative/candidate_narrower', 1, 'value'),
        ('confirmation_population', f'{report}: range-calibrated narrower for single categories (cohorts of 610)', single,
         f'pair:bonferroni:range-calibrated:{report}/single/candidate_narrower', 1, 'value'),
        ('confirmation_population', f'{report}: range-calibrated narrower for internal ranges (cohorts of 592)', internal,
         f'pair:bonferroni:range-calibrated:{report}/internal/candidate_narrower', 1, 'value'))],
    ('confirmation_population', 'R1: default rule confirmed (1 = yes)', '1', 'default_rule/R1/confirmed', 1, 'value'),
    ('confirmation_population', 'R1: range-calibrated narrower for single categories (% of cohorts)', '87.5', 'default_rule/R1/range_calibrated_narrower_single', 100, 'value'),
    ('confirmation_population', 'R2: range-calibrated narrower for single categories (% of cohorts)', '49.7', 'default_rule/R2/range_calibrated_narrower_single', 100, 'value'),
    ('confirmation_population', 'R3: range-calibrated narrower for single categories (% of cohorts)', '62.0', 'default_rule/R3/range_calibrated_narrower_single', 100, 'value'),
    ('confirmation_population', 'joint-exact: summed-width change against Bonferroni, R1 (%)', '-0.042', 'pair:bonferroni:joint-exact:R1/all/summed_width_change_percent', 1, 'value'),
    ('confirmation_population', 'range-hunter: summed-width change against range-calibrated, R1 (%)', '0.099', 'pair:range-calibrated:range-hunter:R1/all/summed_width_change_percent', 1, 'value'),
    *[row for method, covered, lowest in (('bonferroni', '3653145', '97.75'), ('range-calibrated', '3656701', '97.60')) for row in (
        ('confirmation_coverage', f'{method}: replicates', '3660000', f'overall/{method}/replicates', 1, 'value'),
        ('confirmation_coverage', f'{method}: covered replicates', covered, f'overall/{method}/covered', 1, 'value'),
        ('confirmation_coverage', f'{method}: lowest configuration coverage (%)', lowest, f'overall/{method}/lowest_coverage', 100, 'value'),
        ('confirmation_coverage', f'{method}: configurations with undercoverage', '0', f'overall/{method}/configurations_with_undercoverage', 1, 'value'),
        ('confirmation_coverage', f'{method}: failed calculations', '0', f'overall/{method}/errors', 1, 'value'))],
    *[('confirmation_coverage', f'{report}, {method}: coverage (%)', value, f'totals/{report}/{method}/coverage', 100, 'value')
      for report, method, value in (('R1', 'bonferroni', '99.884'), ('R1', 'range-calibrated', '99.881'), ('R2', 'bonferroni', '99.891'),
                                    ('R2', 'range-calibrated', '99.960'), ('R3', 'bonferroni', '99.662'), ('R3', 'range-calibrated', '99.889'))],
    *[row for method, coverage in (('bonferroni', '99.679'), ('range-calibrated', '99.724')) for row in (
        ('synthetic_coverage', f'{method}: coverage (%)', coverage, f'overall/{method}/coverage', 100, 'value'),
        ('synthetic_coverage', f'{method}: lowest configuration coverage (%)', '96.9', f'overall/{method}/lowest_coverage', 100, 'value'),
        ('synthetic_coverage', f'{method}: configurations with undercoverage', '0', f'overall/{method}/configurations_with_undercoverage', 1, 'value'))],
    ('external_calibration', 'test units', '109', 'sum:real[reference=uniform]/test_units', 1, 'value'),
    ('external_calibration', 'test units covered, uniform reference', '103', 'sum:real[reference=uniform]/test_units_covered', 1, 'value'),
    ('external_calibration', 'test units covered, trained reference', '101', 'sum:real[reference=trained]/test_units_covered', 1, 'value'),
    *[row for dataset, (uniform, trained) in CALIBRATION.items() for row in (
        ('external_calibration', f'{dataset}: test units covered, uniform reference', uniform, f'sum:real[dataset={dataset}][reference=uniform]/test_units_covered', 1, 'value'),
        ('external_calibration', f'{dataset}: test units covered, trained reference', trained, f'sum:real[dataset={dataset}][reference=trained]/test_units_covered', 1, 'value'))],
    *[('external_calibration', f'synthetic {setting}, {test}: coverage (%)', value, f'sum:synthetic/settings[setting={setting}]/tests/{test}/coverage', 100, 'value')
      for setting, values in SYNTHETIC_UNITS.items() for test, value in zip(SU, values)],
    ('endpoint_selection', 'compatible tables before the count', '7938', 'reports/summaries/compatible_tables', 1, 'value'),
    ('endpoint_selection', 'compatible tables after the count', '546', 'reports/with count/compatible_tables', 1, 'value'),
    ('endpoint_selection', 'checked endpoints', '60', 'all_endpoints', 1, 'value'),
    ('endpoint_selection', 'largest endpoint difference (pp; bound)', '0.000000001', 'largest_endpoint_difference_pp', 1, 'bound'),
    ('endpoint_selection', 'selected tables, median seconds before the count', '0.063', 'reports/summaries/median_seconds_selected', 1, 'timing'),
    ('endpoint_selection', 'all tables, median seconds before the count', '4.665', 'reports/summaries/median_seconds_exhaustive', 1, 'timing'),
    ('endpoint_selection', 'selected tables, median seconds after the count', '0.064', 'reports/with count/median_seconds_selected', 1, 'timing'),
    ('endpoint_selection', 'all tables, median seconds after the count', '0.356', 'reports/with count/median_seconds_exhaustive', 1, 'timing'),
    ('examples', 'printed numbers that differ from the program output', '0', 'statuses/differs', 1, 'value'),
]


def lookup(summary, path):
    """Follow PATH in SUMMARY. 'pair:BASE:CANDIDATE[:REPORT]/...' selects a pair; 'sum:...' adds the values reached
    through list items selected by [key=value] filters."""
    if path.startswith('sum:'):
        nodes = [summary]
        for part in path[4:].split('/'):
            name, *filters = part.replace(']', '').split('[')
            nodes = [n.get(name) if isinstance(n, dict) else None for n in nodes]
            nodes = [x for n in nodes for x in (n if isinstance(n, list) else [n])]
            for f in filters:
                key, value = f.split('=', 1)
                nodes = [n for n in nodes if isinstance(n, dict) and str(n.get(key)) == value]
        values = [n for n in nodes if isinstance(n, (int, float)) and not isinstance(n, bool)]
        return sum(values) if values else None
    if path.startswith('pair:'):
        head, rest = path.split('/', 1)
        _, base, candidate, *report = head.split(':')
        node = next((p for p in summary.get('pairs', []) if p['baseline'] == base and p['candidate'] == candidate
                     and (not report or p.get('report') == report[0])), None)
        path = rest
    else:
        node = summary
    for part in path.split('/'):
        if node is None:
            return None
        node = node.get(part) if isinstance(node, dict) else None
    return node


def compare(article, value, scale, kind, summary):
    if summary is None or value is None:
        return None, 'not run'
    value = Decimal(repr(value)) * scale if isinstance(value, float) else Decimal(int(value)) * scale
    decimals = -Decimal(article).as_tuple().exponent
    shown = str(value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP))  # printed values are rounded half up
    if kind == 'timing':
        return shown, 'timing'
    if not summary.get('full_design', False):
        return shown, 'reduced run'
    if kind == 'bound':
        return shown, 'match' if value <= Decimal(article) else 'differs'
    return shown, 'match' if shown == article else 'differs'


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    out = args.output.resolve()
    summaries = {c: read_json(out / c / 'summary.json') if (out / c / 'summary.json').exists() else None for c in COMPARISONS}
    numbers = []
    for number, (comparison, quantity, article, path, scale, kind) in enumerate(ARTICLE, 1):
        summary = summaries[comparison]
        value = lookup(summary, path) if summary else None
        shown, status = compare(article, value, scale, kind, summary)
        numbers.append(dict(number=number, comparison=comparison, quantity=quantity, article=article,
                            reproduced='' if shown is None else shown, status=status))
    tables = out / 'tables'
    write_csv(tables / 'article_numbers.csv', numbers)
    population = summaries['population']
    if population:
        write_csv(tables / 'population_table3.csv', [dict(
            construction=m, cohorts=e['cohorts'],
            cumulative_mean_width_pp=e['cumulative']['mean_width_pp'], cumulative_resolved=e['cumulative']['resolved_questions'],
            cumulative_questions=e['cumulative']['questions'], single_mean_width_pp=e['single']['mean_width_pp'],
            single_resolved=e['single']['resolved_questions'], single_questions=e['single']['questions'],
            internal_mean_width_pp=e['internal']['mean_width_pp'], internal_resolved=e['internal']['resolved_questions'],
            all_mean_width_pp=e['all']['mean_width_pp'], all_resolved=e['all']['resolved_questions'], all_questions=e['all']['questions'],
            cohorts_meeting_endpoint_target=e['cohorts_meeting_endpoint_target'], median_seconds=e['median_seconds'],
            maximum_seconds=e['maximum_seconds']) for m, e in population['constructions'].items()])
        write_csv(tables / 'population_pairs.csv', [dict(baseline=p['baseline'], candidate=p['candidate'], kind=kind, cohorts=p['cohorts'],
                  **p[kind]) for p in population['pairs'] for kind in ('cumulative', 'single', 'internal', 'all')])
    if summaries['coverage']:
        write_csv(tables / 'coverage.csv', [dict(case=c['case'], n=c['n'], replicates=c['replicates'],
                  **{f'{m}_{k}': c[m][k] for m in ('bonferroni', 'range-calibrated') for k in ('covered', 'coverage', 'errors', 'mean_width_pp')})
                  for c in summaries['coverage']['cohorts']])
    if summaries['complete_tables']:
        write_csv(tables / 'complete_tables.csv', [dict(case=c['case'], n=c['n'],
                  **{f'{m}_{k}': v for m in ('bonferroni', 'range-calibrated') for k, v in (
                      ('complete_mean_width_pp', c[m]['complete']['mean_width_pp']), ('report_mean_width_pp', c[m]['report']['mean_width_pp']),
                      ('width_ratio', c[m]['width_ratio']))}) for c in summaries['complete_tables']['cohorts']])
    counts = {s: sum(n['status'] == s for n in numbers) for s in ('match', 'differs', 'timing', 'reduced run', 'not run')}
    write_json(out / 'SUMMARY.json', dict(
        created_utc=now(), environment=common.environment(), statuses=counts,
        comparisons={c: None if s is None else dict(status=s.get('status'), full_design=s.get('full_design'), created_utc=s.get('created_utc'),
                                                    package_version=s['environment']['package_version'], platform=s['environment']['platform'])
                     for c, s in summaries.items()},
        numbers=numbers))
    width = max(len(n['quantity']) for n in numbers)
    for n in numbers:
        print(f"{n['comparison']:<21} {n['quantity']:<{width}} {n['article']:>9} {str(n['reproduced']):>9}  {n['status']}")
    print(json.dumps(counts))


if __name__ == '__main__':
    main()
