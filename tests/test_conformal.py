from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import numpy as np
import pytest

from mic_50_90.conformal import (
    aggregate_unit_scores,
    atomic_studies,
    attained_level,
    balanced_partition,
    calibrate_wasserstein_manifest,
    canonical_split_units,
    conformal_rank,
    minimum_calibration_size,
    radius_unit_rank,
    split_conformal_radius,
    split_unit,
    straddling_studies,
    supported_level,
    validate_calibration_manifest,
)
from mic_50_90.dro import wasserstein_1d, wasserstein_bounds
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import parse_spec


def _legacy_manifest(name):
    """Read a frozen diagnostic record; never recreate a legacy guarantee."""
    path = Path(__file__).parent / 'fixtures/legacy-calibration-manifests.json'
    return deepcopy(json.loads(path.read_text(encoding='utf-8'))['fixtures'][name])


def test_external_split_keeps_every_study_in_one_partition():
    # The property the design rests on, stated over study identifiers rather than over
    # label strings. The previous version of this test compared two identical labels and
    # asserted they hashed alike, which is true of any function; meanwhile a cohort citing
    # "A;B" and a cohort citing "B" hashed to different labels and study B was assigned to
    # two partitions at once, in 19 of the 47 labels of the released run.
    labels = [
        split_unit("EMBL-EBI", "111;222"),
        split_unit("EMBL-EBI", "222"),
        split_unit("EMBL-EBI", "222;333"),
        split_unit("EMBL-EBI", "444"),
    ]
    units = canonical_split_units(labels)

    # 111, 222 and 333 are chained by co-citation and must form one unit; 444 stands alone.
    assert units[labels[0]] == units[labels[1]] == units[labels[2]] == "111;222;333"
    assert units[labels[3]] == "444"

    partition = balanced_partition(
        {"111;222;333": 3, "444": 1},
        {"training": 0.30, "calibration": 0.30, "test": 0.40},
    )
    assert straddling_studies(partition) == []

    # A cohort with no publication accession has no identifiable study and therefore no
    # unit: a repository name is not a study, and two deposits in one repository are
    # neither one study nor demonstrably two.
    assert canonical_split_units([split_unit("EMBL-EBI", "PATRIC")]) == {
        "EMBL-EBI|PATRIC": None
    }


def test_straddling_studies_reports_a_split_study():
    # The failure the released design could not report, because it recorded the overlap
    # count as the literal zero and asserted that literal in its own release gate.
    partition = {"111;222": "calibration", "222;333": "test"}
    assert straddling_studies(partition) == ["222"]


def test_balanced_partition_is_deterministic_and_hits_its_quotas():
    sizes = {"a": 185, "b": 144, "c": 48, "d": 39, "e": 4, "f": 1}
    targets = {"training": 0.30, "calibration": 0.30, "test": 0.40}
    first = balanced_partition(sizes, targets)
    assert first == balanced_partition(dict(reversed(list(sizes.items()))), targets)

    total = sum(sizes.values())
    for name, want in targets.items():
        got = sum(size for unit, size in sizes.items() if first[unit] == name)
        # Whole units are indivisible, so the largest single unit bounds the achievable
        # error; the test asserts that bound rather than a share no partition could hit.
        assert abs(got - want * total) <= max(sizes.values())


def test_95_percent_group_requires_19_calibration_cohorts():
    assert minimum_calibration_size(0.05) == 19
    assert conformal_rank(19, 0.05) == 19
    with pytest.raises(ValueError, match="global fallback"):
        split_conformal_radius(np.arange(18), 0.05)


def test_small_group_forces_global_fallback_manifest():
    manifest = _legacy_manifest('small_group_global')
    assert manifest["fallback_used"] is True
    assert manifest["guarantee_scope"] == "global_marginal"
    assert manifest["calibration_size"] == 40
    validate_calibration_manifest(manifest)


def test_manifest_validator_rejects_unknown_keys_and_false_scope_claims():
    manifest = _legacy_manifest('declared_group')

    with pytest.raises(ValueError, match="unknown keys"):
        validate_calibration_manifest({**manifest, "undeclared_claim": True})

    false_scope = {**manifest, "guarantee_scope": "global_marginal"}
    with pytest.raises(ValueError, match="declared_group_marginal"):
        validate_calibration_manifest(false_scope)

    false_grouping = {**manifest, "grouping": {"scope": "global"}}
    with pytest.raises(ValueError, match="declared_group_marginal"):
        validate_calibration_manifest(false_grouping)


def test_split_conformal_simulation_has_nominal_exchangeable_coverage_and_loses_it_under_shift():
    rng = np.random.default_rng(20260809)
    covered = 0
    shifted_covered = 0
    repetitions = 4000
    for _ in range(repetitions):
        calibration = rng.exponential(1.0, 39)
        radius, _ = split_conformal_radius(calibration, 0.05)
        covered += bool(rng.exponential(1.0) <= radius)
        shifted_covered += bool(rng.exponential(3.0) <= radius)
    exchangeable_rate = covered / repetitions
    shifted_rate = shifted_covered / repetitions
    assert exchangeable_rate >= 0.94
    assert shifted_rate < exchangeable_rate - 0.15


def test_one_wasserstein_set_bounds_multiple_thresholds_simultaneously():
    raw = {
        "contract_version": "1.0",
        "mode": "empirical",
        "n": 20,
        "panel": {"levels": [1, 2, 4, 8], "left_censored": False, "right_censored": False},
        "summaries": {"quantiles": [
            {"probability": 0.5, "category": "2"},
            {"probability": 0.9, "category": "8"}
        ]},
        "thresholds": [1, 2]
    }
    spec = parse_spec(raw)
    problem = EmpiricalProblem(n=20, panel=spec.panel, quantiles=spec.quantiles)
    true_distribution = np.asarray([0.3, 0.3, 0.2, 0.2])
    reference = np.asarray([0.35, 0.25, 0.25, 0.15])
    positions = np.log2(spec.panel.panel_values)
    radius = wasserstein_1d(true_distribution, reference, positions) + 1e-10
    for threshold in spec.thresholds:
        objective = spec.panel.panel_tail(threshold)
        result = wasserstein_bounds(
            problem=problem,
            reference=reference,
            radius=radius,
            objective=objective,
        )
        truth = float(objective @ true_distribution)
        assert result.lower - 1e-8 <= truth <= result.upper + 1e-8


def test_supported_level_is_the_inverse_of_minimum_calibration_size():
    # A level is attainable exactly when the rank it needs is at most m. The two functions
    # are the same statement read from opposite ends, so they must agree at every boundary.
    for units in range(1, 60):
        level = supported_level(units)
        assert conformal_rank(units, 1.0 - level) <= units
        assert conformal_rank(units, 1.0 - (level + 1e-9)) > units
    assert supported_level(8) == pytest.approx(8 / 9)
    assert supported_level(19) == pytest.approx(0.95)
    assert minimum_calibration_size(1.0 - supported_level(19)) == 19
    with pytest.raises(ValueError):
        supported_level(0)


def _clustered_scores():
    """Forty cohort scores from four studies, the last carrying one extreme cohort."""
    scores, units = [], []
    for study, base in (("s1", 0.1), ("s2", 1.0), ("s3", 2.0), ("s4", 3.0)):
        for step in range(10):
            scores.append(base + 0.1 * step)
            units.append(study)
    scores[-1] = 10.0
    return scores, units


def test_counting_cohorts_as_units_inflates_the_level_a_radius_appears_to_carry():
    scores, units = _clustered_scores()
    radius, rank = split_conformal_radius(scores, 0.05)
    per_cohort_level = rank / (len(scores) + 1)
    collapsed, labels = aggregate_unit_scores(scores, units)
    assert labels == ["s1", "s2", "s3", "s4"]
    assert collapsed.tolist() == pytest.approx([1.0, 1.9, 2.9, 10.0])
    gained = attained_level(radius, collapsed)
    # The per-cohort rank suggests 0.95; four independent studies cannot carry more than
    # 0.8, and this radius sits third among them, so it carries 0.6.
    assert per_cohort_level == pytest.approx(39 / 41)
    assert supported_level(len(labels)) == pytest.approx(0.8)
    assert radius_unit_rank(radius, collapsed) == 3
    assert gained == pytest.approx(3 / 5)
    assert gained < supported_level(len(labels)) < per_cohort_level
    median_collapsed, _ = aggregate_unit_scores(scores, units, aggregate="median")
    assert median_collapsed.tolist() == pytest.approx([0.55, 1.45, 2.45, 3.45])
    with pytest.raises(ValueError):
        aggregate_unit_scores(scores, units[:-1])


def test_manifest_reports_units_and_rejects_partial_or_overclaimed_unit_accounting():
    manifest = _legacy_manifest('clustered_global')
    validate_calibration_manifest(manifest)
    assert manifest["calibration_size"] == 40
    assert manifest["exchangeable_units"] == 4
    assert manifest["exchangeable_unit_definition"] == "source|study"
    assert manifest["unit_score_aggregation"] == "max"
    assert manifest["maximum_supported_level"] == pytest.approx(0.8)
    assert manifest["attained_level"] == pytest.approx(0.6)
    # These fields are checked for historical structural consistency only.
    # Their post-hoc rank fractions do not establish a coverage guarantee.
    assert manifest["manifest_version"] == "1.1"
    assert manifest["confidence_level"] == pytest.approx(0.6)
    assert manifest["requested_level"] == pytest.approx(0.95)
    assert manifest["requested_level_supported"] is False
    assert manifest["confidence_level"] <= manifest["maximum_supported_level"]

    raised = dict(manifest)
    raised["confidence_level"] = 0.95
    with pytest.raises(ValueError, match="cannot exceed the level"):
        validate_calibration_manifest(raised)

    detached = dict(manifest)
    detached["confidence_level"] = 0.4
    with pytest.raises(ValueError, match="must be the level the units certify"):
        validate_calibration_manifest(detached)

    lying_flag = dict(manifest)
    lying_flag["requested_level_supported"] = True
    with pytest.raises(ValueError, match="whether the declared level met the request"):
        validate_calibration_manifest(lying_flag)

    stale_version = dict(manifest)
    stale_version["manifest_version"] = "1.0"
    with pytest.raises(ValueError, match="requires manifest version 1.1"):
        validate_calibration_manifest(stale_version)

    partial = dict(manifest)
    partial.pop("attained_level")
    with pytest.raises(ValueError, match="complete or absent"):
        validate_calibration_manifest(partial)

    overclaimed = dict(manifest)
    overclaimed["attained_level"] = 0.99
    with pytest.raises(ValueError, match="cannot exceed the level"):
        validate_calibration_manifest(overclaimed)

    mislabelled = dict(manifest)
    mislabelled["exchangeable_unit_labels"] = ["s1"]
    with pytest.raises(ValueError, match="exactly exchangeable_units"):
        validate_calibration_manifest(mislabelled)


def test_new_calibration_refuses_undeclared_legacy_score_semantics():
    """A radius and a post-hoc position cannot replace a calibration contract."""
    scores, units = _clustered_scores()
    with pytest.raises(ValueError, match="calibration_contract"):
        calibrate_wasserstein_manifest(
            group_scores=[],
            global_scores=scores,
            group_units=[],
            global_units=units,
            alpha=0.9,
            grouping={"species": "Escherichia coli"},
            source="unit test",
            data_hashes={"x": "y"},
        )


def test_manifests_without_unit_accounting_still_validate():
    manifest = _legacy_manifest('without_units')
    validate_calibration_manifest(manifest)
    assert "exchangeable_units" not in manifest


def test_bioproject_accession_identifies_a_study():
    """A deposit without a paper still names a study, and the corpus is thirty percent
    such deposits. Admitting only digits left every one of them with no unit at all."""
    assert atomic_studies("PRJNA292661") == ("PRJNA292661",)
    assert atomic_studies("PRJDB7087;NCBI_antibiogram") == ("PRJDB7087",)
    assert atomic_studies("NCBI_antibiogram;NDARO") == ()


def test_repaired_and_published_cohorts_of_one_study_form_one_unit():
    """The failure this guards against is silent and inflates the level: a study that
    reached the corpus twice, once with its paper and once only as a deposit, would be
    counted as two exchangeable units and m/(m+1) would rise on a study counted twice."""
    labels = [split_unit("EBI", "PRJNA1;77"), split_unit("EBI", "77"),
              split_unit("EBI", "PRJNA9")]
    units = canonical_split_units(labels)
    assert units[labels[0]] == units[labels[1]] == "77;PRJNA1"
    assert units[labels[2]] == "PRJNA9"
    assert len(set(units.values())) == 2


def test_unit_calibration_declares_the_level_it_was_asked_for():
    """Counting the rank over cohorts while claiming a per-study guarantee is what made
    the declared level fall below the request; counting it over units removes the
    mismatch instead of papering over it afterwards."""
    from test_release_contract import contract
    scores = [0.1, 0.2, 5.0, 0.3, 0.4, 0.5, 0.6]
    units = ["a", "a", "a", "b", "c", "d", "e"]
    grouping = {"scope": "test"}
    common = dict(alpha=0.5, grouping=grouping, source="test", data_hashes={'fixture':'fixed'},
                  group_units=units, global_units=units, global_scores=scores)
    by_cohort = _legacy_manifest('unequal_cohort_ranking')
    by_unit = calibrate_wasserstein_manifest(group_scores=scores,
        calibrate_on="units", calibration_contract=contract(), **common).as_dict()
    assert by_cohort["conformal_rank_counts"] == "cohorts"
    assert by_unit["conformal_rank_counts"] == "units"
    assert by_cohort["calibration_size"] == 7
    assert by_unit["calibration_size"] == 5
    assert by_unit["confidence_level"] >= by_cohort["confidence_level"]
    assert by_unit["requested_level_supported"] is True


def test_unit_calibration_refuses_without_units():
    from test_release_contract import contract
    with pytest.raises(ValueError, match="exchangeable unit"):
        calibrate_wasserstein_manifest(group_scores=[0.1, 0.2, 0.3], alpha=0.5,
                                       grouping={}, source="t", data_hashes={},
                                       calibrate_on="units", calibration_contract=contract())


def test_the_projection_lies_in_the_sharp_set_and_bounds_every_score_from_below():
    """The distance from the reference to the sharp set is an additive floor on the score.

    Not an observation about this corpus: for any candidate P in the sharp identified set,
    W1(P, reference) >= dist(reference, sharp set) by the definition of the projection, so
    every unit score carries that distance before a question about the organisms is asked.
    Centring the ball on the projection removes it exactly.
    """
    import numpy as np
    from mic_50_90.dro import project_onto_sharp_set, wasserstein_1d
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICPanel, QuantileSummary

    levels = np.array([0.25, 0.5, 1.0, 2.0, 4.0])
    panel = MICPanel.from_twofold_levels(levels, left_censored=False, right_censored=False)
    problem = EmpiricalProblem(n=100, panel=panel, quantiles=(
        QuantileSummary(0.5, 50, 2, panel.labels[2], "ceiling"),
        QuantileSummary(0.9, 90, 3, panel.labels[3], "ceiling")))
    positions = np.log2(levels)

    # A reference concentrated where this cohort's own MIC50 says the mass is not.
    reference = np.array([0.8, 0.2, 0.0, 0.0, 0.0])
    distance, projected = project_onto_sharp_set(problem=problem, reference=reference,
                                                 positions=positions)
    assert distance > 0.0

    # The projection is feasible: its own distance to the sharp set is zero.
    again, _ = project_onto_sharp_set(problem=problem, reference=projected,
                                      positions=positions)
    assert again == pytest.approx(0.0, abs=1e-7)

    # And nothing in the sharp set is nearer to the reference than the projection is.
    for candidate in (projected, np.array([0.0, 0.1, 0.45, 0.35, 0.10])):
        if abs(candidate.sum() - 1.0) > 1e-9:
            continue
        assert wasserstein_1d(candidate, reference, positions) >= distance - 1e-7


def test_projecting_a_reference_that_does_not_match_the_panel_is_refused():
    import numpy as np
    from mic_50_90.dro import project_onto_sharp_set
    from mic_50_90.empirical import EmpiricalProblem
    from mic_50_90.model import MICPanel, QuantileSummary

    levels = np.array([0.25, 0.5, 1.0, 2.0, 4.0])
    panel = MICPanel.from_twofold_levels(levels, left_censored=False, right_censored=False)
    problem = EmpiricalProblem(n=100, panel=panel, quantiles=(
        QuantileSummary(0.5, 50, 2, panel.labels[2], "ceiling"),
        QuantileSummary(0.9, 90, 3, panel.labels[3], "ceiling")))
    with pytest.raises(ValueError, match="match the panel"):
        project_onto_sharp_set(problem=problem, reference=np.array([0.5, 0.5]))
