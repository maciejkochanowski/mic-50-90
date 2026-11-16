"""Finite controls of population projections and probability witnesses against complete-table regions.

For n = 1 to 5 isolates and K = 2 to 4 categories the reports are: the denominator alone; three
ceiling-rank MIC50/MIC90 reports (the first, middle and last in a fixed order of all reports that
occur); and the union of the first and last report (two interpretations). For each report,
confidence level 0.1, 0.8 or 0.95, and method:

  oracle      every compatible complete table is enumerated. For each table the Clopper-Pearson
              region of the category probabilities is built independently (roots by exact rational
              bisection; all contiguous ranges for range-calibrated with its cutoff computed here,
              cumulative ranges at alpha/(K-1) for Bonferroni) and projected onto every contiguous
              range with a linear program. The population interval of a range is the union over
              tables of these projections.
  projection  population_distribution (2-second budget) must contain every oracle endpoint
              (2 x 10^-9 tolerance) and, when it certifies its precision, agree within 2 x 10^-8:
              2832 projection pairs; the maximum absolute difference is reported.
  interrupted range-calibrated with zero search budget must still contain every oracle endpoint:
              1416 projection pairs.
  witnesses   for each report interpretation (range-calibrated), compatible_probability_witness is
              asked for a compatible table that the region of the probability vector of the first
              compatible table accepts. Every returned table must match the report and be accepted
              by the exact binomial score on every proper contiguous range: 267 queries, 222
              witnesses, 747 accepted-range checks.

The exact-count confidence sets of every cumulative tail are also compared with the literal
count support and the union of Clopper-Pearson intervals (447 projections).

Output: OUTPUT/population_controls/summary.json.
"""
from __future__ import annotations

import common

import json
import time
from collections import Counter
from decimal import ROUND_CEILING, Decimal
from fractions import Fraction as F
from functools import lru_cache
from math import comb
from time import perf_counter

import numpy as np

from common import now, write_json
from count_extrema_controls import Checks, histograms, make_problem, matches, range_mask, report_key


def exact_tail(n, count, q, upper=False):
    q = F(q)
    first, last = (count, n) if upper else (0, count)
    numerator = sum(comb(n, j) * q.numerator**j * (q.denominator - q.numerator)**(n - j) for j in range(first, last + 1))
    return F(numerator, q.denominator**n)


@lru_cache(None)
def root_upper(count, n, cutoff):
    if count == n:
        return F(1), F(1)
    lo, hi = F(0), F(1)
    for _ in range(58):
        mid = (lo + hi) / 2
        if exact_tail(n, count, mid) >= cutoff / 2:
            lo = mid
        else:
            hi = mid
    return lo, hi


def root_pair(count, n, cutoff):
    """Clopper-Pearson interval at level 1 - cutoff, from exact rational bisection."""
    other, upper = root_upper(n - count, n, cutoff), root_upper(count, n, cutoff)
    return float(1 - (other[0] + other[1]) / 2), float((upper[0] + upper[1]) / 2)


def range_calibrated_cutoff(n, k, alpha):
    m = comb(k, 2)
    candidates = [alpha / m]
    for r in range(1, k):
        sizes = [len(range(part, k, r)) for part in range(r)]
        edges = sum(sizes[a] * sizes[b] for a in range(r) for b in range(a + 1, r))
        candidates.append(min(2 * alpha / (m + edges), 2 * F(r, r + 1)**n))
    return min(F(1), max(candidates))


class Regions:
    """Projections of the complete-table probability region onto every contiguous range."""

    def __init__(self):
        self.solves = 0
        self.region = lru_cache(None)(self._region)

    def _region(self, h, cutoff, kind):
        from scipy.optimize import linprog
        n, k = sum(h), len(h)
        family = [(0, b) for b in range(1, k)] if kind == 'prefix' else [(a, b) for a in range(k) for b in range(a + 1, k)]
        constraints, rhs = [], []
        for a, b in family:
            lo, hi = root_pair(sum(h[a:b]), n, cutoff)
            row = range_mask(k, a, b)
            constraints.extend([row, -row])
            rhs.extend([hi, -lo])
        endpoints = []
        for a in range(k):
            for b in range(a + 1, k + 1):
                objective = range_mask(k, a, b)
                fits = [linprog(sign * objective, A_ub=constraints, b_ub=rhs, A_eq=[np.ones(k)], b_eq=[1.], bounds=[(0, 1)] * k,
                                method='highs') for sign in (1, -1)]
                self.solves += 2
                if not all(x.success for x in fits):
                    raise AssertionError(('complete-table linear program failed', h, str(cutoff), kind))
                endpoints.append((float(fits[0].fun), float(-fits[1].fun)))
        return tuple(endpoints)


def run(check):
    from mic_50_90.exact_population import exact_count_confidence
    from mic_50_90.joint_population import population_distribution
    from mic_50_90.range_certificates import compatible_probability_witness
    from mic_50_90.utility import _prefix_distances
    stats, statuses, regions, maximum = check.stats, Counter(), Regions(), 0.
    for n in range(1, 6):
        for k in range(2, 5):
            hs = histograms(n, k)
            keys = sorted({report_key(h) for h in hs}, key=str)
            selected = [keys[0], keys[len(keys) // 2], keys[-1]]
            bundles = [[((), None, None)]] + [[key] for key in dict.fromkeys(selected)] + [[keys[0], keys[-1]]]
            for confidence in (.1, .8, .95):
                for bundle in bundles:
                    problems = {str(i): make_problem(n, k, key) for i, key in enumerate(bundle)}
                    feasible = [h for h in hs if any(matches(h, key) for key in bundle)]
                    for method, kind in (('range-calibrated', 'all'), ('bonferroni', 'prefix')):
                        alpha = F(1) - F(confidence)
                        cutoff = range_calibrated_cutoff(n, k, alpha) if kind == 'all' else alpha / (k - 1)
                        table = np.array([regions.region(h, cutoff, kind) for h in feasible])
                        expected = np.column_stack((table[:, :, 0].min(axis=0), table[:, :, 1].max(axis=0)))
                        got = population_distribution(problems, method=method, confidence_level=confidence, time_limit_seconds=2.,
                                                      tolerance_pp=1e-6, include_intervals=True)
                        statuses[f"{method}:{got['status']}"] += 1
                        for row, (low, high) in zip(got['interval_bounds'], expected):
                            error = max(abs(row['lower'] - low), abs(row['upper'] - high))
                            maximum = max(maximum, float(error))
                            check(row['lower'] <= low + 2e-9 and row['upper'] >= high - 2e-9, 'population interval loses an oracle endpoint',
                                  [n, k, confidence, bundle, method, row, low, high])
                            if got['precision_reached']:
                                check(error <= 2e-8, 'certified endpoint differs from the complete-table oracle', [n, k, confidence, method, error])
                            stats['projection_pairs'] += 1
                        if method == 'range-calibrated':
                            interrupted = population_distribution(problems, method=method, confidence_level=confidence,
                                                                  time_limit_seconds=0., tolerance_pp=1e-10, include_intervals=True)
                            for row, (low, high) in zip(interrupted['interval_bounds'], expected):
                                check(row['lower'] <= low + 2e-9 and row['upper'] >= high - 2e-9,
                                      'zero-budget result loses an oracle endpoint', [n, k, confidence, bundle, row])
                                stats['zero_budget_projection_pairs'] += 1
                            for key, problem in problems.items():
                                d = _prefix_distances(problem)
                                p = tuple(F(x, n) for x in feasible[0])
                                witness = compatible_probability_witness(d, p, cutoff, time.monotonic() + 5)
                                stats['probability_witness_queries'] += 1
                                if witness is not None:
                                    check(matches(witness, bundle[int(key)]), 'probability witness does not match the report', [n, k, witness])
                                    for a in range(k):
                                        for b in range(a + 1, k):
                                            q, x = sum(p[a:b]), sum(witness[a:b])
                                            score = min(F(1), 2 * exact_tail(n, x, q), 2 * exact_tail(n, x, q, True))
                                            check(score >= cutoff, 'probability witness is not exactly accepted', [n, k, p, witness, a, b])
                                            stats['accepted_probability_range_checks'] += 1
                                    stats['probability_witnesses_returned'] += 1
                        stats['report_method_cases'] += 1
                    for a in range(1, k):
                        support = sorted({sum(h[a:]) for h in feasible})
                        got = exact_count_confidence(problems=problems, objective=range_mask(k, a, k), confidence_level=confidence)
                        actual = sorted({x for lo, hi in got.count_ranges for x in range(lo, hi + 1)})
                        check(actual == support, 'exact-count union fills missing integer counts', [n, k, bundle, a])
                        merged = []
                        for lo, hi in sorted(root_pair(x, n, F(1) - F(confidence)) for x in support):
                            if not merged or lo > merged[-1][1] + 1e-14:
                                merged.append([lo, hi])
                            else:
                                merged[-1][1] = max(merged[-1][1], hi)
                        check(len(merged) == len(got.probability_components)
                              and np.allclose(merged, got.probability_components, atol=3e-14, rtol=0),
                              'exact-count probability union differs', [n, k, bundle, a])
                        stats['exact_count_union_projections'] += 1
    stats['complete_table_regions'] = regions.region.cache_info().currsize
    stats['oracle_linear_programs'] = regions.solves
    return statuses, maximum


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    folder = args.output.resolve() / 'population_controls'
    started = perf_counter()
    check = Checks()
    statuses, maximum = run(check)
    counts = dict(check.stats)
    checks = counts.pop('checks')
    rounded = float((Decimal(repr(maximum)) * Decimal(10)**12).quantize(Decimal('0.001'), rounding=ROUND_CEILING))
    write_json(folder / 'summary.json', dict(
        comparison='population_controls', created_utc=now(), status='complete', full_design=True,
        elapsed_seconds=perf_counter() - started, environment=common.environment(), counts=counts, statuses=dict(statuses),
        maximum_absolute_difference=maximum, maximum_absolute_difference_e12_rounded_up=rounded,
        checks=checks, failed_checks=len(check.failures), all_agree=not check.failures, failures=check.failures[:50]))
    print(json.dumps(dict(counts=counts, statuses=statuses, maximum_absolute_difference=maximum, rounded_e12=rounded, checks=checks,
                          failed_checks=len(check.failures), seconds=round(perf_counter() - started, 1)), indent=1))


if __name__ == '__main__':
    main()
