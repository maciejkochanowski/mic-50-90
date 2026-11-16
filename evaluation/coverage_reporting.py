"""Evidence from finite coverage simulations; never a proof of a guarantee.

The interval describes Monte Carlo uncertainty for one fixed configuration with
independent replicates. It is not an interval for a biological population share.
Rows with computation errors keep both denominators but receive no coverage CI.
Pooling different configurations is descriptive: their success probabilities need
not be identical, so a pooled ordinary binomial interval is not reported.
"""
from __future__ import annotations

import math
from numbers import Integral

from scipy.stats import binom, binomtest


def _count(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f'{name} must be an integer count')
    if value < 0:
        raise ValueError(f'{name} must be nonnegative')
    return int(value)


def _probability(value, name):
    if isinstance(value, bool):
        raise TypeError(f'{name} must be a probability')
    value = float(value)
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError(f'{name} must be finite and strictly between zero and one')
    return value


def coverage_evidence(covered, completed, *, failed=0, expected=None,
                      nominal=.95, test_level=.001, mc_level=.95):
    """Summarize counts without treating nonrejection as a confirmed guarantee.

    ``coverage`` retains the historical completed-replicate denominator.
    ``coverage_over_attempted_replicates`` includes execution failures in its
    denominator and is a descriptive availability-and-containment fraction.
    The historical strict p-value boundary is retained. With failures, its
    p-value refers only to completed runs and cannot establish coverage of the
    complete planned procedure; ``coverage_assessment`` explicitly says so.
    """
    covered = _count(covered, 'covered')
    completed = _count(completed, 'completed')
    failed = _count(failed, 'failed')
    if covered > completed:
        raise ValueError('covered cannot exceed completed')
    attempted = completed + failed
    expected = attempted if expected is None else _count(expected, 'expected')
    if expected != attempted:
        raise ValueError('expected replicates must equal completed plus failed; account for every attempt')
    nominal = _probability(nominal, 'nominal')
    test_level = _probability(test_level, 'test_level')
    mc_level = _probability(mc_level, 'mc_level')
    coverage = covered / completed if completed else None
    pvalue = float(binom.cdf(covered, completed, nominal)) if completed else None
    detected = bool(pvalue is not None and pvalue < test_level)
    interval = None
    standard_error = None
    if completed and not failed:
        bounds = binomtest(covered, completed).proportion_ci(confidence_level=mc_level, method='exact')
        interval = dict(method='Clopper-Pearson', level=mc_level, lower=float(bounds.low), upper=float(bounds.high),
                        denominator=completed, unit='fraction', estimand='coverage_probability_of_one_fixed_configuration',
                        simultaneous_across_configurations=False)
        standard_error = math.sqrt(coverage * (1 - coverage) / completed)
    assessment = ('execution_errors_present' if failed else
                  'no_replicates' if not completed else
                  'undercoverage_detected' if detected else 'no_undercoverage_detected')
    return dict(replicates_expected=expected, replicates_attempted=attempted, replicates_completed=completed,
                replicates_failed=failed, coverage=coverage, coverage_denominator='completed_replicates',
                coverage_over_attempted_replicates=covered / attempted if attempted else None,
                monte_carlo_interval=interval, monte_carlo_standard_error=standard_error,
                monte_carlo_standard_error_method='plug_in_binomial_for_fixed_configuration_without_execution_errors',
                undercoverage=detected, undercoverage_pvalue=pvalue, undercoverage_nominal=nominal,
                undercoverage_test_level=test_level, undercoverage_denominator='completed_replicates',
                undercoverage_rule='one_sided_exact_binomial_pvalue < test_level', coverage_assessment=assessment,
                empirical_check_confirms_guarantee=False)


def pooled_coverage_evidence(values):
    """Aggregate fixed-configuration summaries without a false iid pooled CI."""
    completed = sum(v.get('replicates_completed', v.get('replicates', 0)) for v in values)
    covered = sum(v['covered'] for v in values)
    failures = [len(v['errors']) if isinstance(v['errors'], list) else v['errors'] for v in values]
    errors = sum(failures)
    coverages = [v['coverage'] for v in values if v['coverage'] is not None]
    detected = sum(v.get('undercoverage', False) for v in values)
    assessment = ('no_configurations' if not values else 'execution_errors_present' if errors else
                  'no_replicates' if not completed else 'undercoverage_detected' if detected else
                  'no_undercoverage_detected')
    return dict(configurations=len(values), replicates=completed, replicates_completed=completed,
                replicates_attempted=completed + errors, covered=covered, errors=errors,
                coverage=covered / completed if completed else None, coverage_denominator='completed_replicates',
                coverage_over_attempted_replicates=covered / (completed + errors) if completed + errors else None,
                lowest_coverage=min(coverages) if coverages else None,
                configurations_with_undercoverage=detected,
                configurations_with_execution_errors=sum(bool(n) for n in failures),
                pooled_interval=None, pooled_interval_reason='different_fixed_configuration_probabilities; use per-configuration Monte Carlo intervals',
                coverage_assessment=assessment, empirical_check_confirms_guarantee=False)
