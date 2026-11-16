"""Self-contained standard-library receiver for finite upper-CP shape certificates.

The decimal kernel uses only exact integer conversion and directed arithmetic.
It does not call a probability library, transcendental power or the MIC package.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from decimal import (Context, Decimal, ROUND_CEILING, ROUND_FLOOR, InvalidOperation,
                     DivisionByZero, Overflow, Underflow, Subnormal, Clamped,
                     FloatOperation, DecimalException)
from fractions import Fraction
import json
from math import comb
from pathlib import Path
import time

SCHEMA = 'mic5090-upper-shape-certificate/1'
ALGORITHM = 'directed-upper-reverse-geometric-v1'
CLAIM = 'finite_discrete_concavity_of_upper_equal_tailed_binomial_endpoints'
POLICY = dict(generator_precisions=[40, 80], receiver_precisions=[60, 120],
              Emin=-999999999, Emax=999999999, max_n=10000)
ZERO, ONE = Decimal(0), Decimal(1)


def require(condition, message):
    if not condition:
        raise ValueError(message)


class BudgetExhausted(TimeoutError):
    pass


class Budget:
    def __init__(self, deadline=None, term_limit=None):
        self.deadline, self.term_limit, self.terms = deadline, term_limit, 0

    def check(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise BudgetExhausted('Directed arithmetic deadline reached')

    def term(self):
        self.check()
        if self.term_limit is not None and self.terms >= self.term_limit:
            raise BudgetExhausted('Directed tail term-operation cap reached')
        self.terms += 1


def contexts(precision):
    require(type(precision) is int and 2 <= precision <= 120, 'Unsupported decimal precision')
    result = []
    for rounding in (ROUND_FLOOR, ROUND_CEILING):
        context = Context(prec=precision, rounding=rounding, Emin=POLICY['Emin'], Emax=POLICY['Emax'])
        for signal in (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal, Clamped, FloatOperation):
            context.traps[signal] = True
        result.append(context)
    return result


def integer_power(context, base, exponent, budget):
    """Monotone nonnegative products only; no Decimal.power call."""
    require(type(exponent) is int and exponent >= 0 and base >= ZERO, 'Invalid power input')
    value = ONE
    while exponent:
        budget.check()
        if exponent & 1:
            value = context.multiply(value, base)
        exponent >>= 1
        if exponent:
            base = context.multiply(base, base)
    return value


@dataclass(frozen=True)
class CDFBound:
    lower: Decimal
    upper: Decimal
    included_terms: int
    last_count: int
    geometric_remainder: bool
    precision: int
    stop: str

    def as_dict(self):
        return dict(lower=str(self.lower), upper=str(self.upper), included_terms=self.included_terms,
                    last_count=self.last_count, geometric_remainder=self.geometric_remainder,
                    precision=self.precision, stop=self.stop)


def cdf_bounds(n, x, probability, *, precision=40, target=None, relation=None,
               max_terms=None, budget=None, coefficient=None):
    """Enclose Pr(Bin(n,p)<=x); target comparisons use exact rational values.

    max_terms is an oracle-test stopping control, not a certification tolerance.
    The optional exact coefficient is supplied only by checked internal loops.
    """
    require(type(n) is int and 1 <= n <= POLICY['max_n'] and type(x) is int and 0 <= x <= n,
            'Invalid n/count')
    p = Fraction(probability)
    require(0 <= p <= 1, 'Probability outside [0,1]')
    require(relation in {None, 'at_least', 'at_most'} and ((target is None) == (relation is None)),
            'Target and comparison must be supplied together')
    target = None if target is None else Fraction(target)
    require(target is None or 0 <= target <= 1, 'Invalid target')
    require(max_terms is None or type(max_terms) is int and max_terms > 0, 'Invalid term stopping point')
    budget = budget or Budget(); budget.check()
    if x == n or p == 0 or p == 1:
        exact = ONE if x == n or p == 0 else ZERO
        return CDFBound(exact, exact, 0, x, False, precision, 'exact_boundary')
    down, up = contexts(precision)
    a, b = p.numerator, p.denominator
    choose = comb(n, x) if coefficient is None else coefficient
    require(type(choose) is int and choose > 0, 'Invalid exact binomial coefficient')
    masses = []
    for context in (down, up):
        pp = context.divide(Decimal(a), Decimal(b))
        qq = context.divide(Decimal(b - a), Decimal(b))
        mass = context.multiply(Decimal(choose), context.multiply(
            integer_power(context, pp, x, budget), integer_power(context, qq, n - x, budget)))
        masses.append(mass)
    low, high = masses; budget.term()
    sum_low, sum_high, j, included = low, high, x, 1
    while True:
        budget.check(); geometric = False
        if j == 0:
            cdf_high = min(ONE, sum_high)
        else:
            numerator, denominator = Decimal(j * (b - a)), Decimal((n - j + 1) * a)
            ratio_high = up.divide(numerator, denominator)
            if ratio_high < ONE:
                divisor_low = down.subtract(ONE, ratio_high)
                if divisor_low > ZERO:
                    remainder_high = up.divide(up.multiply(high, ratio_high), divisor_low)
                    cdf_high = min(ONE, up.add(sum_high, remainder_high)); geometric = True
                else:
                    cdf_high = ONE
            else:
                cdf_high = ONE
        cdf_low = min(ONE, sum_low)
        stop = None
        if target is not None:
            # Decimal values are exact rationals here. No rounded target is used.
            lower_pass = Fraction(cdf_low) >= target
            upper_pass = Fraction(cdf_high) <= target
            if (relation == 'at_least' and lower_pass) or (relation == 'at_most' and upper_pass):
                stop = 'comparison_proved'
            elif (relation == 'at_least' and Fraction(cdf_high) < target) or (
                    relation == 'at_most' and Fraction(cdf_low) > target):
                stop = 'opposite_comparison_proved'
        if stop is None and j == 0:
            stop = 'full_sum'
        if stop is None and max_terms is not None and included >= max_terms:
            stop = 'requested_partial_sum'
        if stop is not None:
            require(ZERO <= cdf_low <= cdf_high <= ONE, 'Invalid directed CDF enclosure')
            return CDFBound(cdf_low, cdf_high, included, j, geometric, precision, stop)
        budget.term()
        low = down.divide(down.multiply(low, numerator), denominator)
        high = up.divide(up.multiply(high, numerator), denominator)
        sum_low, sum_high = down.add(sum_low, low), up.add(sum_high, high)
        j -= 1; included += 1


def parse_fraction(value):
    require(isinstance(value, str) and 0 < len(value) <= 4096, 'Malformed rational field')
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise ValueError('Malformed rational field') from error
    require(str(result) == value, 'Noncanonical rational field')
    return result


def certificate_data(n, cutoff, rows):
    parsed = [(Fraction(row['inner_upper']), Fraction(row['outer_upper'])) for row in rows]
    margins = [str(2 * parsed[x][0] - parsed[x - 1][1] - parsed[x + 1][1]) for x in range(1, n)]
    return dict(schema=SCHEMA, algorithm=ALGORITHM, claim=CLAIM, n=n, cutoff=str(Fraction(cutoff)),
                rows=rows, second_difference_lower_bounds=margins, numerical_policy=deepcopy(POLICY))


def verify_certificate(certificate, *, deadline=None, term_operation_cap=None):
    """Recompute every endpoint inequality, then every exact rational margin."""
    started, cpu = time.perf_counter(), time.process_time(); budget = Budget(deadline, term_operation_cap)
    checks = []; partial = dict(endpoint_checks=checks)
    try:
        budget.check()
        fields = {'schema', 'algorithm', 'claim', 'n', 'cutoff', 'rows',
                  'second_difference_lower_bounds', 'numerical_policy'}
        require(isinstance(certificate, dict) and set(certificate) == fields, 'Unknown certificate fields')
        require(certificate['schema'] == SCHEMA and certificate['algorithm'] == ALGORITHM and
                certificate['claim'] == CLAIM and certificate['numerical_policy'] == POLICY,
                'Unknown algorithm, claim or numerical policy')
        n = certificate['n']; cutoff = parse_fraction(certificate['cutoff'])
        require(type(n) is int and 1 <= n <= POLICY['max_n'] and 0 < cutoff <= 1, 'Invalid n or cutoff')
        rows = certificate['rows']; require(isinstance(rows, list) and len(rows) == n + 1, 'Incomplete endpoint rows')
        brackets = []
        for x, row in enumerate(rows):
            require(isinstance(row, dict) and set(row) == {'count', 'inner_upper', 'outer_upper'} and
                    type(row['count']) is int and row['count'] == x, 'Endpoint row order/identity mismatch')
            lower, upper = parse_fraction(row['inner_upper']), parse_fraction(row['outer_upper'])
            require(0 <= lower <= upper <= 1, 'Invalid endpoint bracket')
            brackets.append((lower, upper))
        require(brackets[-1] == (Fraction(1), Fraction(1)), 'Incorrect n boundary')
        margins = [2 * brackets[x][0] - brackets[x - 1][1] - brackets[x + 1][1] for x in range(1, n)]
        saved = certificate['second_difference_lower_bounds']
        require(isinstance(saved, list) and len(saved) == n - 1 and
                [parse_fraction(value) for value in saved] == margins, 'Stored rational margin mismatch')
        coefficient = 1
        for x, (lower, upper) in enumerate(brackets):
            budget.check()
            if x < n:
                for point, relation, side in [(lower, 'at_least', 'inner_upper'), (upper, 'at_most', 'outer_upper')]:
                    attempt = []
                    for precision in POLICY['receiver_precisions']:
                        bound = cdf_bounds(n, x, point, precision=precision, target=cutoff / 2,
                                           relation=relation, budget=budget, coefficient=coefficient)
                        attempt.append(bound.as_dict())
                        proved = Fraction(bound.lower) >= cutoff / 2 if relation == 'at_least' else Fraction(bound.upper) <= cutoff / 2
                        if proved:
                            break
                        if bound.stop == 'opposite_comparison_proved':
                            break
                    checks.append(dict(count=x, side=side, point=str(point), attempts=attempt, proved=proved))
                    if not proved:
                        return dict(status='unresolved', reason='An upper endpoint inequality was not certified',
                                    **partial, terms=budget.terms, elapsed_seconds=time.perf_counter() - started,
                                    process_cpu_seconds=time.process_time() - cpu)
            if x < n:
                coefficient, remainder = divmod(coefficient * (n - x), x + 1)
                require(remainder == 0, 'Nonintegral binomial coefficient recurrence')
        negative = [x for x, margin in enumerate(margins, 1) if margin < 0]
        return dict(status='unresolved' if negative else 'certified',
                    reason='Negative sufficient margin' if negative else None, n=n, cutoff=str(cutoff),
                    endpoint_rows=n + 1, rational_margin_checks=len(margins), negative_margin_indices=negative,
                    minimum_concavity_margin=str(min(margins)) if margins else None,
                    terms=budget.terms, **partial, elapsed_seconds=time.perf_counter() - started,
                    process_cpu_seconds=time.process_time() - cpu)
    except (BudgetExhausted, DecimalException) as error:
        return dict(status='unresolved', reason=str(error), error_type=type(error).__name__, terms=budget.terms,
                    **partial, elapsed_seconds=time.perf_counter() - started,
                    process_cpu_seconds=time.process_time() - cpu)
    except (ValueError, KeyError, TypeError) as error:
        return dict(status='rejected', reason=str(error), error_type=type(error).__name__, terms=budget.terms,
                    **partial, elapsed_seconds=time.perf_counter() - started,
                    process_cpu_seconds=time.process_time() - cpu)


def read_certificate(path):
    def no_duplicate(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'Duplicate JSON object field')
            value[key] = item
        return value
    path = Path(path); require(path.stat().st_size <= 16 * 1024 * 1024, 'Certificate exceeds receiver size limit')
    return json.loads(path.read_text(), object_pairs_hook=no_duplicate)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('certificate', type=Path); parser.add_argument('--seconds', type=float, default=10.)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); require(args.seconds > 0, 'Positive receiver time limit required')
    result = verify_certificate(read_certificate(args.certificate), deadline=time.monotonic() + args.seconds)
    text = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        require(not args.output.exists(), 'Refusing to replace a receiver result'); args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
