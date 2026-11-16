"""Finite controls of sufficient reporting: an independent histogram filter and exhaustive subset search.

For n = 2 to 7 isolates on the five-category panel 1, 2, 4, 8, 16 mg/L, every histogram is
summarized by its ceiling-rank MIC50 and MIC90. The independent oracle groups all histograms by
these summaries, keeps the compatible histograms whose threshold answers differ from the true
ones, and searches every subset of the allowed cumulative counts for the cheapest one that
excludes all of them. The oracle uses only integer compositions and exact fractions. The package
(plan_reporting, then verify_reporting by the recipient) must return the same minimum cost, or
report that no allowed subset suffices exactly when the oracle finds none.

  common-boundary cases  every histogram, "<" questions at 1, 2, 4 and 8 mg/L with a common
                         fraction (0.05, 0.25, 0.5), unit costs and the unequal costs 0, 0.1, 2,
                         0.7: 4716 cases. The minimal report has at most two counts.
  variant cases          50 seeded cases for each n: unions of up to four summary variants, mixed
                         operators (<, <=, >, >=) and fractions per question, and a random subset
                         of the four counts with costs 0 to 3: 300 cases.

Output: OUTPUT/reporting_controls/summary.json and cases.csv.gz.
"""
from __future__ import annotations

import common

import json
from collections import Counter
from fractions import Fraction
from itertools import combinations
from random import Random
from time import perf_counter

from common import now, write_csv, write_json

LEVELS = (1, 2, 4, 8, 16)
THRESHOLDS = (1, 2, 4, 8)
SEED = 29092026


def compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for first in range(n + 1):
            for rest in compositions(n - first, k - 1):
                yield (first, *rest)


def ranks(h):
    """Categories at the ceiling ranks of MIC50 and MIC90, read from the sorted observations."""
    data = [j for j, count in enumerate(h) for _ in range(count)]
    n = len(data)
    return data[(n + 1) // 2 - 1], data[(9 * n + 9) // 10 - 1]


def specification(n, cats, variants=()):
    def summaries(pair):
        return {'quantiles': [{'probability': p, 'category': str(LEVELS[c]), 'convention': 'ceiling'} for p, c in zip((.5, .9), pair)]}
    return {'n': n, 'panel': {'levels': list(LEVELS), 'left_censored': False, 'right_censored': False},
            'summaries': summaries(cats), 'thresholds': list(THRESHOLDS),
            'reporting_envelope': {'variants': [{'id': str(i), 'summaries': summaries(pair)} for i, pair in enumerate(variants)]}}


def tail(h, threshold):
    return sum(c for j, c in enumerate(h) if LEVELS[j] > threshold)


def truth(h, criteria):
    n = sum(h)
    result = []
    for row in criteria:
        v, a = Fraction(tail(h, row['threshold']), n), Fraction(str(row['decision_fraction']))
        result.append({'<': v < a, '<=': v <= a, '>': v > a, '>=': v >= a}[row['decision_operator']])
    return tuple(result)


def oracle(compatible, h, criteria, queries):
    """Cheapest subset of the allowed counts that excludes every compatible histogram with other answers; None if none does."""
    values = [tail(h, q['threshold']) for q in queries]
    target = truth(h, criteria)
    alternatives = [g for g in compatible if truth(g, criteria) != target]
    best = None
    for size in range(len(queries) + 1):
        for selected in combinations(range(len(queries)), size):
            if any(all(tail(g, queries[i]['threshold']) == values[i] for i in selected) for g in alternatives):
                continue
            cost = sum((Fraction(str(queries[i]['cost'])) for i in selected), Fraction(0))
            if best is None or cost < best:
                best = cost
    return best


def compare(kind, n, spec, h, criteria, queries, expected):
    """Run the package on one case and compare it with the oracle."""
    from mic_50_90 import plan_reporting, verify_reporting
    plan = plan_reporting(spec, h, criteria, queries=queries)
    row = dict(kind=kind, n=n, histogram=' '.join(map(str, h)), questions=len(criteria), allowed_counts=len(queries),
               oracle_cost='' if expected is None else str(expected), status=plan['status'],
               package_cost=plan.get('report_cost_exact') or '', fields=len(plan['disclosures']))
    if expected is None:
        row['agrees'] = plan['status'] == 'impossible' and not plan['sufficient']
    else:
        row['agrees'] = bool(plan['optimality_verified'] and Fraction(plan['report_cost_exact']) == expected
                             and verify_reporting(spec, criteria, plan['disclosures'])['sufficient']
                             and (kind != 'common-boundary' or len(plan['disclosures']) <= 2))
    return row


def cases():
    rows = []
    rng = Random(SEED)
    for n in range(2, 8):
        universe = list(compositions(n, len(LEVELS)))
        groups = {}
        for h in universe:
            groups.setdefault(ranks(h), []).append(h)
        for h in universe:
            spec = specification(n, ranks(h))
            for fraction in ('.05', '.25', '.5'):
                criteria = [dict(threshold=t, unit='mg/L', decision_operator='<', decision_fraction=fraction) for t in THRESHOLDS]
                for prices in ((1, 1, 1, 1), ('0', '0.1', '2', '0.7')):
                    queries = [dict(threshold=t, unit='mg/L', cost=c) for t, c in zip(THRESHOLDS, prices)]
                    expected = oracle(groups[ranks(h)], h, criteria, queries)
                    rows.append(compare('common-boundary', n, spec, h, criteria, queries, expected))
        for _ in range(50):
            h = rng.choice(universe)
            pairs = rng.sample(list(groups), min(3, len(groups)))
            pairs = list(dict.fromkeys([ranks(h), *pairs]))
            spec = specification(n, pairs[0], pairs[1:])
            criteria = [dict(threshold=t, unit='mg/L', decision_operator=rng.choice(('<', '<=', '>', '>=')),
                             decision_fraction=rng.choice(('.05', '.25', '.5', '.75'))) for t in THRESHOLDS]
            queries = [dict(threshold=t, unit='mg/L', cost=rng.choice((0, 1, 2, 3))) for t in rng.sample(THRESHOLDS, rng.randrange(5))]
            expected = oracle([g for g in universe if ranks(g) in pairs], h, criteria, queries)
            row = compare('variant', n, spec, h, criteria, queries, expected)
            row['variants'] = len(pairs)
            rows.append(row)
    return rows


def main():
    parser = common.parser(__doc__, workers=False)
    args = parser.parse_args()
    folder = args.output.resolve() / 'reporting_controls'
    started = perf_counter()
    rows = cases()
    kinds = Counter(r['kind'] for r in rows)
    agree = Counter(r['kind'] for r in rows if r['agrees'])
    impossible = [r for r in rows if r['oracle_cost'] == '']
    summary = dict(comparison='reporting_controls', created_utc=now(), status='complete', full_design=True,
                   elapsed_seconds=perf_counter() - started, environment=common.environment(), seed=SEED,
                   counts=dict(cases=len(rows), common_boundary=kinds['common-boundary'], variant=kinds['variant'],
                               agreements=sum(agree.values()), common_boundary_agreements=agree['common-boundary'],
                               variant_agreements=agree['variant'], disagreements=len(rows) - sum(agree.values()),
                               impossible=len(impossible), impossible_identified=sum(r['agrees'] for r in impossible),
                               package_impossible=sum(r['status'] == 'impossible' for r in rows)),
                   disagreements=[r for r in rows if not r['agrees']][:20])
    summary['all_agree'] = summary['counts']['disagreements'] == 0
    write_csv(folder / 'cases.csv.gz', rows)
    write_json(folder / 'summary.json', summary)
    print(json.dumps(dict(counts=summary['counts'], seconds=round(summary['elapsed_seconds'], 1)), indent=1))


if __name__ == '__main__':
    main()
