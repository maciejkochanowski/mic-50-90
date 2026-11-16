"""Upper-endpoint certificate generator; SciPy seeds are untrusted."""
from __future__ import annotations

import argparse
from decimal import DecimalException
from fractions import Fraction
import json
import math
from pathlib import Path
import sys
import time

from scipy.special import betainccinv

from ._shape_receiver import Budget, BudgetExhausted, POLICY, cdf_bounds, certificate_data, require


def upper_float(value):
    proposal = float(value)
    if Fraction(proposal) < value:
        proposal = math.nextafter(proposal, math.inf)
    return proposal


def generate(n, cutoff, *, deadline=None, term_operation_cap=None, progress=None):
    require(type(n) is int and 1 <= n <= POLICY['max_n'], 'Invalid n')
    cutoff = Fraction(cutoff); require(0 < cutoff <= 1, 'Invalid cutoff')
    started, cpu = time.perf_counter(), time.process_time(); budget = Budget(deadline, term_operation_cap)
    rows, diagnostics = [], []; coefficient = 1
    try:
        budget.check()
        for x in range(n + 1):
            budget.check()
            if x == n:
                rows.append(dict(count=x, inner_upper='1', outer_upper='1'))
                diagnostics.append(dict(count=x, boundary=True)); continue
            target = cutoff / 2
            seed = float(betainccinv(x + 1, n - x, float(target)))
            fallback = not math.isfinite(seed) or not 0 < seed <= 1
            if fallback:
                seed = 1.
            floor = upper_float(Fraction(x, n))
            record = dict(count=x, seed_hex=seed.hex(), fallback_seed=fallback, floor_hex=floor.hex(), sides={})
            endpoints = []
            for side, relation in [('inner_upper', 'at_least'), ('outer_upper', 'at_most')]:
                delta = max(1e-12, 8 * math.ulp(seed)); trials = []; proved = False
                for attempt in range(50):
                    budget.check()
                    point = max(floor, seed - delta) if side == 'inner_upper' else min(1., seed + delta)
                    point = Fraction(point); bounds = []
                    for precision in POLICY['generator_precisions']:
                        bound = cdf_bounds(n, x, point, precision=precision, target=target, relation=relation,
                                           budget=budget, coefficient=coefficient)
                        bounds.append(bound.as_dict())
                        proved = Fraction(bound.lower) >= target if side == 'inner_upper' else Fraction(bound.upper) <= target
                        if proved or bound.stop == 'opposite_comparison_proved':
                            break
                    trials.append(dict(attempt=attempt, point=str(point), delta_hex=delta.hex(), bounds=bounds, proved=proved))
                    if proved:
                        endpoints.append(point); break
                    delta *= 2
                record['sides'][side] = trials
                if not proved:
                    diagnostics.append(record)
                    return dict(status='unresolved', reason='Upper endpoint proposal limit', certificate=None,
                                completed_rows=rows, diagnostics=diagnostics, terms=budget.terms,
                                elapsed_seconds=time.perf_counter() - started, process_cpu_seconds=time.process_time() - cpu)
            rows.append(dict(count=x, inner_upper=str(endpoints[0]), outer_upper=str(endpoints[1])))
            diagnostics.append(record)
            if progress is not None:
                progress(dict(completed_rows=len(rows), count=x, terms=budget.terms))
            coefficient, remainder = divmod(coefficient * (n - x), x + 1)
            require(remainder == 0, 'Nonintegral binomial coefficient recurrence')
        certificate = certificate_data(n, cutoff, rows)
        margins = list(map(Fraction, certificate['second_difference_lower_bounds']))
        status = 'certified' if all(value >= 0 for value in margins) else 'unresolved'
        return dict(status=status, reason=None if status == 'certified' else 'Negative sufficient margin',
                    certificate=certificate, diagnostics=diagnostics, terms=budget.terms,
                    elapsed_seconds=time.perf_counter() - started, process_cpu_seconds=time.process_time() - cpu)
    except (BudgetExhausted, DecimalException) as error:
        return dict(status='unresolved', reason=str(error), error_type=type(error).__name__, certificate=None,
                    completed_rows=rows, diagnostics=diagnostics, terms=budget.terms,
                    elapsed_seconds=time.perf_counter() - started, process_cpu_seconds=time.process_time() - cpu)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--n', type=int, required=True); parser.add_argument('--cutoff', required=True)
    parser.add_argument('--seconds', type=float, default=10.); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); require(args.seconds > 0, 'Positive generator time limit required')
    require(not args.output.exists(), 'Refusing to replace a generator result')
    result = generate(args.n, Fraction(args.cutoff), deadline=time.monotonic() + args.seconds)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in ['status', 'reason', 'terms', 'elapsed_seconds']}))


if __name__ == '__main__':
    main()
