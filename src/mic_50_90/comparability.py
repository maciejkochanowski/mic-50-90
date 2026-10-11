"""Whether two MIC distributions may be compared at all.

A transport distance between two MIC histograms is only a statement about the organisms
if both were measured over the same concentrations. Where they were not, the distance
measures the panels. The failure is not hypothetical and it is not small: in the released
external corpus the largest calibration score came from an *Escherichia coli* trimethoprim
cohort tested over 0.25-64 mg/L scored against a reference tested over 0.5-2 mg/L, with
**no shared concentration at all**. Trimethoprim resistance in *E. coli* sits at 8 mg/L and
above, so the reference could not see a resistant isolate; every one it held was reported
off-scale and dropped by the exact-value filter. The 5.38 dilution steps that radius
certified were the width of a panel difference.

That single pair set the conformal radius, because at twenty exchangeable units a 95%
guarantee takes the largest unit score. Removing incomparable pairs takes the radius from
5.38 to 2.74 without touching the guarantee.

The rule here introduces no new threshold. Two distributions are restricted to the range
both were tested over, and the pair is admissible only if each restriction still satisfies
the eligibility this work already applies to every cohort: at least `minimum_count`
observations across at least `minimum_categories` concentrations. Those are the same 20 and
3 that decide which cohorts exist in the first place.

The tested range of a cohort is read from its censoring operators, not assumed: a `<=x`
record marks x as the lowest concentration on the panel and a `>y` record marks y as the
highest, exactly as W7 reads a tested range. Where a cohort carries no censored
observation the observed range is all the data support, and this module says so rather
than inventing a panel: `tested_range` reports whether the bounds came from censoring or
from observation, so a caller can tell a known panel from an assumed one.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable, Mapping

_CENSORED = re.compile(r"^(<=|<|>=|>)([0-9]+(?:[.][0-9]+)?)$")


@dataclass(frozen=True)
class TestedRange:
    """The concentrations a cohort was tested over, and how the bounds were established."""

    #: Not a test class. The domain term is "tested range" -- W7 turns on
    #: `tested_range_known` -- so the name stays, and pytest is told to leave it alone
    #: rather than the vocabulary being bent around a collection convention.
    __test__ = False

    low: float
    high: float
    low_from_censoring: bool
    high_from_censoring: bool

    @property
    def fully_known(self) -> bool:
        """True when both bounds come from a censoring operator rather than from data.

        The distinction W7 exists to make: an observed range is a lower bound on the panel,
        and treating it as the panel is the assumption that no isolate fell off either end.
        """
        return self.low_from_censoring and self.high_from_censoring


def tested_range(counts: Mapping[float, int],
                 censored_counts: Mapping[str, int] | None = None) -> TestedRange:
    low = min(counts)
    high = max(counts)
    low_censored = high_censored = False
    for label in (censored_counts or {}):
        match = _CENSORED.match(label.strip())
        if match is None:
            continue
        operator, value = match.group(1), float(match.group(2))
        if operator in {"<=", "<"} and value <= low:
            low, low_censored = value, True
        elif operator in {">=", ">"} and value >= high:
            high, high_censored = value, True
    return TestedRange(float(low), float(high), low_censored, high_censored)


def restrict(counts: Mapping[float, int], low: float, high: float) -> Counter:
    return Counter({value: number for value, number in counts.items()
                    if low <= value <= high})


def common_range(left: TestedRange, right: TestedRange) -> tuple[float, float] | None:
    low, high = max(left.low, right.low), min(left.high, right.high)
    return None if low > high else (low, high)


def comparable_pair(left: Mapping[float, int], left_range: TestedRange,
                    right: Mapping[float, int], right_range: TestedRange,
                    *, minimum_count: int, minimum_categories: int
                    ) -> tuple[Counter, Counter] | None:
    """The two distributions restricted to their common tested range, or None.

    None means the pair carries no admissible comparison: either the panels do not meet, or
    what survives the restriction is below the size at which this work lets a cohort exist.
    A caller must treat that as an absent score, never as a score of zero -- the pair is
    unmeasured, not identical.
    """
    window = common_range(left_range, right_range)
    if window is None:
        return None
    low, high = window
    first, second = restrict(left, low, high), restrict(right, low, high)
    for part in (first, second):
        if sum(part.values()) < minimum_count or len(part) < minimum_categories:
            return None
    return first, second


def comparability_graph(cohorts: Iterable, key, unit_of: Mapping[str, str | None], *,
                        minimum_count: int, minimum_categories: int
                        ) -> dict[tuple, dict[str, set[str]]]:
    """Per group, which exchangeable units could serve as each other's reference.

    An edge is a fact about panels and cohort sizes only. Nothing here reads a distance, so
    an allocation built on this graph cannot be steered toward a coverage.
    """
    grouped: dict[tuple, list] = {}
    for cohort in cohorts:
        if unit_of.get(cohort.identifier) is None:
            continue
        grouped.setdefault(key(cohort), []).append(cohort)
    graph: dict[tuple, dict[str, set[str]]] = {}
    for group, members in grouped.items():
        ranges = {c.identifier: tested_range(c.counts, c.censored_counts) for c in members}
        edges: dict[str, set[str]] = {}
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                first, second = unit_of[left.identifier], unit_of[right.identifier]
                if first == second:
                    continue
                if comparable_pair(left.counts, ranges[left.identifier],
                                   right.counts, ranges[right.identifier],
                                   minimum_count=minimum_count,
                                   minimum_categories=minimum_categories) is None:
                    continue
                edges.setdefault(first, set()).add(second)
                edges.setdefault(second, set()).add(first)
        if edges:
            graph[group] = edges
    return graph


def matched_reference(counts: Mapping[float, int], own_range: TestedRange,
                      candidates: Iterable[tuple[Mapping[float, int], TestedRange]], *,
                      minimum_count: int, minimum_categories: int
                      ) -> tuple[Counter, Counter, tuple[float, float], int] | None:
    """Build the reference from the training cohorts this one may actually be compared to.

    Pooling a whole group and then asking whether the target is comparable with the pool
    lets one training cohort tested over three dilutions shrink the pooled range for every
    other, and throws away references that were perfectly usable. Selecting first and
    pooling second keeps them.

    Candidates are taken widest common window first, and one is admitted only while the
    running window still leaves both sides eligible. Deterministic, and it reads tested
    ranges and cohort sizes only -- no distance is computed here, so a reference built this
    way cannot have been chosen for the answer it gives.

    Returns the restricted target, the restricted reference, the window, and how many
    training cohorts went into it; or None when no admissible reference exists.
    """
    ranked = []
    for other, other_range in candidates:
        window = common_range(own_range, other_range)
        if window is None:
            continue
        if comparable_pair(counts, own_range, other, other_range,
                           minimum_count=minimum_count,
                           minimum_categories=minimum_categories) is None:
            continue
        ranked.append((window[1] / window[0] if window[0] > 0 else 0.0,
                       window, other))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], min(item[2]), max(item[2])))
    window = ranked[0][1]
    pooled: Counter = Counter()
    used = 0
    for _width, candidate_window, other in ranked:
        low = max(window[0], candidate_window[0])
        high = min(window[1], candidate_window[1])
        if low > high:
            continue
        trial = Counter(pooled)
        trial.update(restrict(other, low, high))
        target = restrict(counts, low, high)
        if (sum(target.values()) < minimum_count or len(target) < minimum_categories
                or sum(trial.values()) < minimum_count
                or len(trial) < minimum_categories):
            continue
        pooled, window, used = trial, (low, high), used + 1
    if used == 0:
        return None
    target = restrict(counts, *window)
    pooled = restrict(pooled, *window)
    if (sum(target.values()) < minimum_count or len(target) < minimum_categories
            or sum(pooled.values()) < minimum_count or len(pooled) < minimum_categories):
        return None
    return target, pooled, window, used
