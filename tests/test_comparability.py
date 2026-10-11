"""Whether two MIC distributions may be compared, and what happens when they may not."""
from __future__ import annotations


from mic_50_90.comparability import (
    TestedRange, comparability_graph, common_range, comparable_pair,
    matched_reference, restrict,
)
# Aliased on import: pytest's default collects any module-level name beginning with
# "test", so importing `tested_range` under its own name makes the collector try to run
# the library function as a test case and fail on its arguments.
from mic_50_90.comparability import tested_range as panel_of


def test_tested_range_reads_the_panel_from_censoring_not_from_observation():
    known = panel_of({0.5: 10, 1: 5}, {"<=0.5": 3, ">2": 7})
    assert (known.low, known.high) == (0.5, 2.0)
    assert known.fully_known
    assumed = panel_of({4: 10, 8: 5})
    assert (assumed.low, assumed.high) == (4.0, 8.0)
    assert not assumed.fully_known, "an observed range is not a known panel"


def test_one_sided_censoring_leaves_the_range_partly_assumed():
    partial = panel_of({1: 5, 2: 5}, {">2": 4})
    assert partial.high_from_censoring and not partial.low_from_censoring
    assert not partial.fully_known


def test_the_released_worst_pair_is_refused():
    """The comparison that set the released radius: an Escherichia coli trimethoprim
    cohort tested over 0.25-64 against a reference tested over 0.5-2, sharing no
    concentration at all. The 5.38 dilution steps it certified were a panel difference."""
    cohort = {0.25: 4, 32: 5, 64: 14}
    reference = {0.5: 94, 1: 33, 2: 8}
    assert comparable_pair(cohort, panel_of(cohort), reference,
                           panel_of(reference),
                           minimum_count=20, minimum_categories=3) is None


def test_a_refusal_is_not_a_score_of_zero():
    """The failure mode this guards against is silent: an absent comparison averaged in
    as a zero would pull the radius down and the level up, for pairs never measured."""
    left = {1: 30, 2: 30, 4: 30}
    right = {64: 30, 128: 30, 256: 30}
    assert common_range(panel_of(left), panel_of(right)) is None
    assert comparable_pair(left, panel_of(left), right, panel_of(right),
                           minimum_count=20, minimum_categories=3) is None


def test_restriction_must_still_satisfy_the_work_s_own_eligibility():
    cohort = {0.5: 25, 1: 25, 2: 25, 64: 25}
    reference = {0.5: 40, 1: 40, 2: 40}
    assert comparable_pair(cohort, panel_of(cohort), reference,
                           panel_of(reference),
                           minimum_count=20, minimum_categories=3) is not None
    thin = {0.5: 21, 64: 40}
    assert comparable_pair(thin, panel_of(thin), reference, panel_of(reference),
                           minimum_count=20, minimum_categories=3) is None


def test_matched_reference_keeps_partners_a_pooled_group_would_have_lost():
    """One training cohort tested over three dilutions must not shrink the reference for
    every other. Selecting comparable partners first and pooling second keeps them."""
    cohort = {0.5: 10, 1: 10, 2: 10, 4: 10}
    wide = {0.5: 30, 1: 30, 2: 30, 4: 30}
    narrow = {1: 30, 2: 30}
    built = matched_reference(cohort, panel_of(cohort),
                              [(narrow, panel_of(narrow)), (wide, panel_of(wide))],
                              minimum_count=20, minimum_categories=3)
    assert built is not None
    _target, pooled, window, used = built
    assert used >= 1 and window[0] <= 0.5 and window[1] >= 4
    assert sum(pooled.values()) >= 20


def test_matched_reference_refuses_when_nothing_is_comparable():
    cohort = {0.5: 30, 1: 30, 2: 30}
    far = {64: 30, 128: 30, 256: 30}
    assert matched_reference(cohort, panel_of(cohort), [(far, panel_of(far))],
                             minimum_count=20, minimum_categories=3) is None


class _Cohort:
    def __init__(self, identifier, counts, censored=None):
        self.identifier = identifier
        self.counts = counts
        self.censored_counts = censored or {}


def test_graph_edges_read_panels_only():
    a = _Cohort("a", {1: 30, 2: 30, 4: 30})
    b = _Cohort("b", {1: 40, 2: 40, 4: 40})
    c = _Cohort("c", {128: 30, 256: 30, 512: 30})
    graph = comparability_graph([a, b, c], lambda item: "g",
                                {"a": "A", "b": "B", "c": "C"},
                                minimum_count=20, minimum_categories=3)
    assert graph["g"]["A"] == {"B"} and graph["g"]["B"] == {"A"}
    assert "C" not in graph["g"], "a disjoint panel is not a reference"


def test_restrict_is_a_window_not_a_reweighting():
    assert restrict({1: 5, 2: 5, 8: 5}, 1, 2) == {1: 5, 2: 5}


def test_common_range_is_symmetric():
    left, right = TestedRange(0.5, 8, True, True), TestedRange(2, 32, True, True)
    assert common_range(left, right) == common_range(right, left) == (2, 8)
