"""Find the finest contiguous sample description meeting a stated precision.

For each reporting variant, integer difference-constraint closure gives sharp
bounds for every category interval. A path through admissible intervals is a
partition. Longest-path dynamic programming therefore maximises its number of
bins; equal-length paths are resolved by lexicographic cut order. The graph is
an application of standard longest-path dynamic programming, not a new graph
algorithm. No independence between interval bounds is assumed.
"""
from __future__ import annotations

from fractions import Fraction

from .empirical import EmpiricalProblem
from .exact_population import _merge_integer_ranges
from .utility import _prefix_distances
from .validation import decimal_number


def maximum_resolvable_partition(problems: dict[str, EmpiricalProblem], *, precision_pp):
    """Maximise contiguous bins under simultaneous deterministic width criteria.

The supplied absolute percentage-point tolerance applies both to each bin's
sample proportion and to the cumulative proportion at every retained boundary.
It is not a confidence level or a numerical solver tolerance. All declared
variants are united before widths are assessed. Results are conditional on the
actual information, including interior interval-count constraints.
"""
    precision = decimal_number(precision_pp, "precision_pp")
    if not 0 <= precision <= 100:
        raise ValueError("precision_pp must lie in [0, 100]")
    if not problems:
        raise ValueError("At least one feasible reporting variant is required")
    first = next(iter(problems.values()))
    if any(problem.n != first.n or problem.panel != first.panel for problem in problems.values()):
        raise ValueError("Reporting variants must have the same sample size and panel")
    if any(not problem.has_total_unimodular_canonical_matrix or not problem._integral_rhs
           for problem in problems.values()):
        raise ValueError("Resolution requires integral contiguous-category constraints")
    maximum_count_width = int(Fraction(precision) * first.n / 100)
    distances = {key: _prefix_distances(problem) for key, problem in problems.items()}

    def interval(a, b):
        ranges = {key: (int(-matrix[b, a]), int(matrix[a, b])) for key, matrix in distances.items()}
        return min(lo for lo, _ in ranges.values()), max(hi for _, hi in ranges.values()), ranges

    cumulative = [interval(0, cut) for cut in range(first.k + 1)]
    best = {0: (0,)}
    interval_bounds = {}
    admitted_edges = 0
    for b in range(1, first.k + 1):
        if cumulative[b][1] - cumulative[b][0] > maximum_count_width:
            continue
        candidates = []
        for a in range(b):
            lower, upper, variants = interval(a, b)
            interval_bounds[a, b] = lower, upper, variants
            if upper - lower <= maximum_count_width:
                admitted_edges += 1
                if a in best:
                    candidates.append((*best[a], b))
        if candidates:
            best[b] = min(candidates, key=lambda path: (-len(path), path))
    # [0,K] always has exactly n observations and zero cumulative uncertainty.
    cuts = best[first.k]
    rows = []
    for a, b in zip(cuts, cuts[1:]):
        lower, upper, variants = interval_bounds[a, b]
        components = _merge_integer_ranges(list(variants.values()))
        label = first.panel.labels[a] if b == a + 1 else f"{first.panel.labels[a]} through {first.panel.labels[b - 1]}"
        rows.append({"start_index": a, "stop_index": b, "label": label,
            "categories": first.panel.labels[a:b], "count_lower": lower, "count_upper": upper,
            "fraction_lower": lower / first.n, "fraction_upper": upper / first.n,
            "count_components": [list(pair) for pair in components],
            "fraction_components": [[lo / first.n, hi / first.n] for lo, hi in components],
            "width_pp": 100 * (upper - lower) / first.n,
            "cumulative_count_lower": cumulative[b][0], "cumulative_count_upper": cumulative[b][1],
            "cumulative_width_pp": 100 * (cumulative[b][1] - cumulative[b][0]) / first.n,
            "variant_count_ranges": {key: list(pair) for key, pair in variants.items()}})
    return {"status": "complete", "precision_pp": float(precision), "precision_pp_decimal": str(precision), "maximum_count_width": maximum_count_width,
            "number_of_bins": len(rows), "original_number_of_categories": first.k,
            "cut_indices": list(cuts), "bins": rows, "optimality_verified": True,
            "admissible_edges": admitted_edges, "tie_rule": "lexicographically smallest cut sequence",
            "guarantee": "Maximum number of contiguous sample bins whose bin and cumulative widths meet the declared precision",
            "population_confidence_claimed": False,
            "interpretation": "Resolution describes this sample conditional on its supplied information; it is not population confidence or a reconstruction of within-category MIC."}
