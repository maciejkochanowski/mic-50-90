"""Independent exact-rational enumeration; no production or scipy imports."""
from collections import defaultdict
from fractions import Fraction
from math import comb, factorial


def compositions(n, k):
    if k == 1:
        yield (n,)
    else:
        for count in range(n + 1):
            for rest in compositions(n - count, k - 1):
                yield (count,) + rest


def binomial_tables(n, probability):
    probability = Fraction(probability)
    mass = [Fraction(comb(n, x)) * probability**x * (1-probability)**(n-x)
            for x in range(n+1)]
    total = Fraction(0)
    equal_tail = []
    for atom in mass:
        survival = 1-total
        total += atom
        equal_tail.append(min(Fraction(1), 2*min(total, survival)))
    grouped = defaultdict(Fraction)
    for atom in mass:
        grouped[atom] += atom
    sums, total = {}, Fraction(0)
    for atom, contribution in sorted(grouped.items()):
        total += contribution
        sums[atom] = total
    return equal_tail, [sums[atom] for atom in mass]


def multinomial_mass(histogram, probabilities):
    coefficient = factorial(sum(histogram))
    for count in histogram:
        coefficient //= factorial(count)
    # Sequential integer divisions of factorial products remain exact because
    # each partial denominator divides n! for a composition of n.
    probability = Fraction(coefficient)
    for count, p in zip(histogram, probabilities):
        probability *= p**count
    return probability


def calibrated_tail(scores, masses, *, reverse=False):
    atoms = defaultdict(Fraction)
    for score, mass in zip(scores, masses):
        atoms[score] += mass
    total, values = Fraction(0), {}
    for score, mass in sorted(atoms.items(), reverse=reverse):
        total += mass
        values[score] = total
    return [values[score] for score in scores]


def exact_null(n, probabilities):
    probabilities = tuple(Fraction(p) for p in probabilities)
    if n < 1 or len(probabilities) < 2 or sum(probabilities) != 1 or min(probabilities) < 0:
        raise ValueError('Positive n and a categorical probability vector are required')
    histograms = list(compositions(n, len(probabilities)))
    cumulative, total = [], Fraction(0)
    for p in probabilities[:-1]:
        total += p
        cumulative.append(total)
    tables = [binomial_tables(n, p) for p in cumulative]
    scores, bonf, sterne, ks, masses = [], [], [], [], []
    for histogram in histograms:
        prefix, count = [], 0
        for h in histogram[:-1]:
            count += h
            prefix.append(count)
        score = min(table[0][x] for table, x in zip(tables, prefix))
        scores.append(score)
        bonf.append(min(Fraction(1), len(cumulative)*score))
        sterne.append(min(Fraction(1), len(cumulative)*min(
            table[1][x] for table, x in zip(tables, prefix))))
        ks.append(max(abs(Fraction(x, n)-p) for x, p in zip(prefix, cumulative)))
        masses.append(multinomial_mass(histogram, probabilities))
    assert sum(masses) == 1
    return dict(n=n, probabilities=probabilities, histograms=histograms, masses=masses,
                statistic=scores, minp=calibrated_tail(scores, masses),
                bonferroni=bonf, sterne_bonferroni=sterne,
                ks=calibrated_tail(ks, masses, reverse=True))


def summary_pair(histogram):
    sample = [j for j, count in enumerate(histogram) for _ in range(count)]
    n = len(sample)
    return sample[(n+1)//2-1], sample[(9*n+9)//10-1]


def group_indices(null):
    groups = defaultdict(list)
    for index, h in enumerate(null['histograms']):
        groups[summary_pair(h)].append(index)
    return dict(groups)


def partial_values(null, indices):
    if not indices:
        raise ValueError('No compatible histogram')
    return {name: max(null[name][i] for i in indices)
            for name in ('minp', 'bonferroni', 'sterne_bonferroni', 'ks')}


def null_sizes(null):
    return {name: {str(alpha): str(sum((mass for p, mass in zip(null[name], null['masses'])
                                     if p <= alpha), Fraction(0)))
                   for alpha in (Fraction(1,100), Fraction(1,20), Fraction(1,10))}
            for name in ('minp', 'bonferroni', 'sterne_bonferroni', 'ks')}


NULLS = {
    2: [('1/2','1/2'), ('1/5','4/5'), ('1/100','99/100'), ('0','1'), ('1','0')],
    3: [('1/3','1/3','1/3'), ('1/5','3/10','1/2'), ('1/100','98/100','1/100'),
        ('0','2/5','3/5'), ('1','0','0')],
    4: [('1/4',)*4, ('1/10','2/10','3/10','4/10'), ('1/100','1/100','97/100','1/100'),
        ('0','1/5','3/10','1/2'), ('0','0','1','0')],
}


def frozen_cases():
    for n in (2,5,10,20,50,100):
        for k in ((2,3,4) if n <= 20 else (2,3)):
            for p in NULLS[k]:
                yield n, p
