"""Certified propagation between report counts and population probabilities."""
from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache

from .endpoint import (as_region, close, count_cells, _score_envelopes,
    _cp_outer, _check_deadline, range_family)
from .pairwise import HistRegion


@dataclass(frozen=True)
class Node:
    region: HistRegion
    cell: tuple


@lru_cache(maxsize=8192)
def cp(count, n, cutoff):
    """Outward endpoints whose binomial comparisons are independently checked."""
    return tuple(map(F, _cp_outer(count, n, cutoff)))


def propagate(problem, cell, cutoff, *, rounds=8, deadline=None):
    """Enclose laws having a compatible histogram with all scores >= cutoff.

    This routine does not decide whether a cutoff is statistically admissible.
    Its caller must supply that certificate before using it to contract the
    confidence region. Each reporting variant is propagated separately.
    """
    region = as_region(problem)
    cutoff = F(cutoff)
    if not 0 < cutoff < 1:
        raise ValueError("score cutoff must lie strictly between zero and one")
    if rounds < 1:
        raise ValueError("at least one propagation round is required")
    ranges = tuple((a, b) for a in range(region.k) for b in range(a + 1, region.k + 1))
    answer = []
    for variant in region.variants:
        _check_deadline(deadline)
        single = HistRegion(region.n, region.k, (variant,))
        try:
            counts = count_cells(single)[0]
        except ValueError:
            continue
        current = cell
        for _ in range(rounds):
            _check_deadline(deadline)
            restricted = [list(row) for row in counts]
            impossible = False
            for a, b in ranges:
                upper_scores = _score_envelopes(region.n, -current[b][a], current[a][b])[1]
                allowed = [c for c in range(-counts[b][a], counts[a][b] + 1)
                           if upper_scores[c] >= cutoff]
                if not allowed:
                    impossible = True
                    break
                # Only extremal allowed counts are required for a safe hull;
                # no assumption about absence of interior holes is needed.
                restricted[a][b] = min(restricted[a][b], allowed[-1])
                restricted[b][a] = min(restricted[b][a], -allowed[0])
            if impossible:
                break
            try:
                updated_counts = close(restricted)
                probabilities = [list(row) for row in current]
                for a, b in ranges:
                    lower = cp(-updated_counts[b][a], region.n, cutoff)[0]
                    upper = cp(updated_counts[a][b], region.n, cutoff)[1]
                    probabilities[a][b] = min(probabilities[a][b], upper)
                    probabilities[b][a] = min(probabilities[b][a], -lower)
                updated_cell = close(probabilities)
            except ValueError:
                impossible = True
                break
            fixed = updated_counts == counts and updated_cell == current
            counts, current = updated_counts, updated_cell
            if fixed:
                break
        if not impossible:
            constraints = tuple((a, b, -counts[b][a], counts[a][b]) for a, b in ranges)
            answer.append(Node(HistRegion(region.n, region.k, (constraints,)), current))
    return tuple(answer)

