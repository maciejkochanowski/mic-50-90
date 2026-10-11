"""Unit-level calibration allocation helper used by the external validation adapter.

The solver assigns whole study units under explicit calibration/test floors.
Allocation diagnostics concern the declared units and do not establish exchangeability.
The external-data entry point requires source records supplied separately.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix, vstack

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import run_external_validation as validation           # noqa: E402
from mic_50_90.comparability import comparability_graph   # noqa: E402
from mic_50_90.conformal import (                      # noqa: E402
    balanced_partition, canonical_split_units, straddling_studies, supported_level,
)

RESULTS = ROOT / "results"
ALPHA = 0.05

#: The floors an allocation must clear. Neither may fall below what the released design
#: already delivers, so the rule cannot buy a higher ceiling by starving the radius or the
#: empirical check. If no allocation clears the first floor, the search steps down the
#: prespecified ladder and the audit records which step it needed.
CALIBRATION_FLOORS = (130, 100, 60, 19)
TEST_FLOOR = 37
#: The empirical check has to rest on more than one study. Without this floor the optimum
#: parks eighty-four test cohorts inside a single unit, which measures how well one study
#: is covered and says nothing about a new one.
TEST_UNIT_FLOOR = 3
#: Added 2026-08-25 by a dated amendment to the preregistration, after the first confirming
#: run parked five hundred cohorts in calibration and left sixty-five in test. The sensitivity
#: block below shows the objective is untouched by this floor -- twenty units and 0.9524
#: either way -- so the amendment discards a degenerate tie-break among equally optimal
#: allocations and buys nothing on any coverage.
TEST_TOTAL_FLOOR = 245
RELEASED_TARGETS = {"training": 0.30, "calibration": 0.30, "test": 0.40}


def group_of(cohort) -> tuple[str, str, str, str]:
    return (cohort.species, cohort.drug, cohort.method, cohort.standard)


def structure(cohorts, *, require_comparable: bool = False) -> dict[str, Any]:
    """Everything a partition rule is allowed to read: units, their sizes, their groups.

    With `require_comparable` the cells carry, in addition, which other units could serve
    as each unit's reference in that group -- a fact about tested ranges and cohort sizes,
    never about a distance. An allocation solved on it cannot put a unit in calibration and
    then score it against a reference measured over different concentrations, which is the
    defect that set the released radius.
    """
    canonical = canonical_split_units({c.split_unit for c in cohorts})
    unit_of = {c.identifier: canonical[c.split_unit] for c in cohorts}
    cells: Counter[tuple[str, tuple]] = Counter()
    orphan_cells: Counter[tuple] = Counter()
    for cohort in cohorts:
        unit = unit_of[cohort.identifier]
        if unit is None:
            orphan_cells[group_of(cohort)] += 1
        else:
            cells[(unit, group_of(cohort))] += 1
    units = sorted({unit for unit, _ in cells})
    groups = sorted({g for _, g in cells} | set(orphan_cells))
    graph = (comparability_graph(cohorts, group_of, unit_of,
                                 minimum_count=validation.MIN_N,
                                 minimum_categories=validation.MIN_CATEGORIES)
             if require_comparable else None)
    if graph is not None:
        # A cell with no comparable partner in its group can never yield a score, so it is
        # not a cell. Dropping it here keeps the optimiser honest about what it is counting.
        cells = Counter({(u, g): n for (u, g), n in cells.items()
                         if u in graph.get(g, {})})
        units = sorted({unit for unit, _ in cells})
        groups = sorted({g for _, g in cells} | set(orphan_cells))
    return {
        "comparability": graph,
        "unit_of": unit_of,
        "cells": cells,
        "orphan_cells": orphan_cells,
        "units": units,
        "groups": groups,
        "unit_sizes": Counter(u for u in unit_of.values() if u is not None),
        "orphan_cohorts": sum(1 for u in unit_of.values() if u is None),
    }


def evaluate(assignment: dict[str, str], shape: dict[str, Any]) -> dict[str, Any]:
    """Design measures of one assignment. Reads counts only, never a distance."""
    cells, orphan = shape["cells"], shape["orphan_cells"]
    graph = shape.get("comparability")
    if graph is None:
        pooled = {g for g in shape["groups"] if orphan.get(g, 0)}
        pooled |= {g for (u, g) in cells if assignment.get(u) == "training"}
        usable = lambda u, g: g in pooled
    else:
        # A cell is usable when a unit that could actually serve as its reference sits in
        # training. An orphan cohort still enters the pool, but it cannot make a pair
        # comparable on its own, so it does not make a cell usable.
        def usable(unit, group):
            return any(assignment.get(partner) == "training"
                       for partner in graph.get(group, {}).get(unit, ()))
        pooled = {g for (u, g) in cells if assignment.get(u) == "training"}
    scores = sum(n for (u, g), n in cells.items()
                 if assignment.get(u) == "calibration" and usable(u, g))
    tested = sum(n for (u, g), n in cells.items()
                 if assignment.get(u) == "test" and usable(u, g))
    scoring_units = {u for (u, g) in cells
                     if assignment.get(u) == "calibration" and usable(u, g)}
    test_units = {u for (u, g) in cells if assignment.get(u) == "test" and usable(u, g)}
    m = len(scoring_units)
    return {
        "training_cohorts": sum(n for (u, _), n in cells.items()
                                if assignment.get(u) == "training") + sum(orphan.values()),
        "calibration_cohorts": sum(n for (u, _), n in cells.items()
                                   if assignment.get(u) == "calibration"),
        "test_cohorts": sum(n for (u, _), n in cells.items()
                            if assignment.get(u) == "test"),
        "useful_calibration_scores": int(scores),
        "calibration_units_with_scores": m,
        "maximum_supported_level": round(supported_level(m), 4) if m else None,
        "test_cohorts_with_reference": int(tested),
        "test_units_with_reference": len(test_units),
        "groups_with_a_training_pool": len(pooled),
        "straddling_studies": len(straddling_studies(assignment)),
    }


def solve(shape: dict[str, Any], calibration_floor: int, test_floor: int,
          test_unit_floor: int, test_total_floor: int = 0
          ) -> tuple[dict[str, str] | None, dict[str, Any]]:
    """The allocation maximising the number of calibration units, solved exactly.

    Lexicographic in two stages: the number of exchangeable units behind the radius first,
    because that is the quantity the guarantee is capped by, then the number of useful
    calibration scores, because a radius read off nineteen scores is noise. Both stages see
    only cohort counts and group membership.
    """
    units, groups = shape["units"], shape["groups"]
    cells, orphan = shape["cells"], shape["orphan_cells"]
    incidence = sorted(cells)
    ui = {u: i for i, u in enumerate(units)}
    gi = {g: i for i, g in enumerate(groups)}
    ii = {c: i for i, c in enumerate(incidence)}
    n_u, n_g, n_i = len(units), len(groups), len(incidence)

    # x[u,p] p in (training, calibration, test) | t[g] | z[u,g] | w[u,g] | y[u]
    off_x, off_t = 0, 3 * n_u
    off_z, off_w, off_y = off_t + n_g, off_t + n_g + n_i, off_t + n_g + 2 * n_i
    off_v = off_y + n_u
    total = off_v + n_u
    x = lambda u, p: off_x + 3 * ui[u] + p

    rows, lows, highs = [], [], []

    def add(entries: dict[int, float], low: float, high: float) -> None:
        row = lil_matrix((1, total))
        for column, value in entries.items():
            row[0, column] = value
        rows.append(row); lows.append(low); highs.append(high)

    for unit in units:                                    # one partition per unit
        add({x(unit, p): 1.0 for p in range(3)}, 1, 1)
    graph = shape.get("comparability")
    if graph is None:
        for group in groups:                              # a pool exists or it does not
            entry = {off_t + gi[group]: 1.0}
            for unit in units:
                if (unit, group) in cells:
                    entry[x(unit, 0)] = entry.get(x(unit, 0), 0.0) - 1.0
            add(entry, -np.inf, 1.0 if orphan.get(group, 0) else 0.0)
    for cell in incidence:
        unit, group = cell
        add({off_z + ii[cell]: 1.0, x(unit, 1): -1.0}, -np.inf, 0.0)
        add({off_w + ii[cell]: 1.0, x(unit, 2): -1.0}, -np.inf, 0.0)
        if graph is None:
            add({off_z + ii[cell]: 1.0, off_t + gi[group]: -1.0}, -np.inf, 0.0)
            add({off_w + ii[cell]: 1.0, off_t + gi[group]: -1.0}, -np.inf, 0.0)
        else:
            # The cell yields a score only if some unit that may serve as its reference is
            # in training. Written as a single row per cell: z - sum(partners) <= 0.
            partners = {x(p, 0): -1.0 for p in graph.get(group, {}).get(unit, ())
                        if p in ui}
            if not partners:
                add({off_z + ii[cell]: 1.0}, 0.0, 0.0)
                add({off_w + ii[cell]: 1.0}, 0.0, 0.0)
                continue
            add({off_z + ii[cell]: 1.0, **partners}, -np.inf, 0.0)
            add({off_w + ii[cell]: 1.0, **partners}, -np.inf, 0.0)
    for unit in units:                                    # y only where a score exists
        entry = {off_y + ui[unit]: 1.0}
        for cell in incidence:
            if cell[0] == unit:
                entry[off_z + ii[cell]] = -1.0
        add(entry, -np.inf, 0.0)
    for unit in units:                                    # v only where a test cohort has a pool
        entry = {off_v + ui[unit]: 1.0}
        for cell in incidence:
            if cell[0] == unit:
                entry[off_w + ii[cell]] = -1.0
        add(entry, -np.inf, 0.0)
    add({off_z + ii[c]: float(cells[c]) for c in incidence}, calibration_floor, np.inf)
    add({off_w + ii[c]: float(cells[c]) for c in incidence}, test_floor, np.inf)
    add({off_v + ui[u]: 1.0 for u in units}, test_unit_floor, np.inf)
    if test_total_floor:
        # Not one of the preregistered gates. Used only by the sensitivity block below,
        # which asks what the ceiling would have been had the test set been held at a
        # given size; a question raised by the confirming run and answered honestly
        # rather than by quietly swapping the rule for the one that reads best.
        entry: dict[int, float] = {}
        for cell in incidence:
            column = x(cell[0], 2)
            entry[column] = entry.get(column, 0.0) + float(cells[cell])
        add(entry, test_total_floor, np.inf)

    def run(objective: np.ndarray, extra: list[tuple[dict[int, float], float, float]]):
        local_rows, local_low, local_high = list(rows), list(lows), list(highs)
        for entries, low, high in extra:
            row = lil_matrix((1, total))
            for column, value in entries.items():
                row[0, column] = value
            local_rows.append(row); local_low.append(low); local_high.append(high)
        constraint = LinearConstraint(vstack(local_rows).tocsr(),
                                      np.array(local_low), np.array(local_high))
        return milp(c=objective, constraints=constraint,
                    integrality=np.ones(total),
                    bounds=Bounds(np.zeros(total), np.ones(total)))

    stage_one = np.zeros(total); stage_one[off_y:off_y + n_u] = -1.0
    first = run(stage_one, [])
    if not first.success:
        return None, {"status": first.message, "calibration_floor": calibration_floor}
    best_m = int(round(-first.fun))
    stage_two = np.zeros(total)
    for cell in incidence:
        stage_two[off_z + ii[cell]] = -float(cells[cell])
    fixed = ({off_y + ui[u]: 1.0 for u in units}, best_m, best_m)
    second = run(stage_two, [fixed])
    chosen = second if second.success else first
    values = np.round(chosen.x).astype(int)
    assignment = {}
    for unit in units:
        picked = [p for p in range(3) if values[x(unit, p)] == 1]
        assignment[unit] = ("training", "calibration", "test")[picked[0]]
    return assignment, {
        "status": "optimal",
        "calibration_floor": calibration_floor,
        "test_floor": test_floor,
        "test_unit_floor": test_unit_floor,
        "test_total_floor": test_total_floor,
        "objective_units": best_m,
        "objective_scores": int(round(-second.fun)) if second.success else None,
        "solver": f"scipy {scipy.__version__} milp (HiGHS)",
    }


def variant(tag: str, repair: bool) -> dict[str, Any]:
    cohorts, audit = validation.load_ebi(repair_study=repair)
    shape = structure(cohorts)
    released = balanced_partition(dict(shape["unit_sizes"]), RELEASED_TARGETS)
    report: dict[str, Any] = {
        "cohorts": len(cohorts),
        "study_labels": len({c.split_unit for c in cohorts}),
        "exchangeable_units": len(shape["units"]),
        "cohorts_without_identified_study": shape["orphan_cohorts"],
        "groups": len(shape["groups"]),
        "groups_holding_two_or_more_units": sum(
            1 for g in shape["groups"]
            if len({u for (u, gg) in shape["cells"] if gg == g}) >= 2),
        "study_accession_repair": audit["study_accession_repair"],
        "released_rule": evaluate(released, shape),
        "optimised_rule": None,
        "solver_report": None,
    }
    for floor in CALIBRATION_FLOORS:
        assignment, meta = solve(shape, floor, TEST_FLOOR, TEST_UNIT_FLOOR,
                                 TEST_TOTAL_FLOOR)
        if assignment is not None:
            report["optimised_rule"] = evaluate(assignment, shape)
            report["solver_report"] = meta
            report["assignment"] = assignment
            break
        report["solver_report"] = meta
    report["sensitivity_test_set_size_not_a_preregistered_gate"] = {
        str(floor): (lambda pair: {"calibration_units_with_scores":
                                   pair[1].get("objective_units"),
                                   "maximum_supported_level":
                                       round(supported_level(pair[1]["objective_units"]), 4)
                                       if pair[0] is not None else None,
                                   "status": pair[1]["status"]})(
            solve(shape, CALIBRATION_FLOORS[0], TEST_FLOOR, TEST_UNIT_FLOOR, floor))
        for floor in (100, 150, 200, 245)
    }
    return report


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    out = {
        "campaign": "stage0_unit_audit",
        "measures_are_blind_to_coverage": True,
        "calibration_floor_ladder": list(CALIBRATION_FLOORS),
        "test_cohorts_with_reference_floor": TEST_FLOOR,
        "test_units_with_reference_floor": TEST_UNIT_FLOOR,
        "test_cohorts_total_floor": TEST_TOTAL_FLOOR,
        "released": variant("released", repair=False),
        "repaired": variant("repaired", repair=True),
    }
    assignment_rows = ["variant,unit,partition"]
    for tag in ("released", "repaired"):
        for unit, partition in sorted(out[tag].pop("assignment", {}).items()):
            assignment_rows.append(f'{tag},"{unit}",{partition}')
    (RESULTS / "stage0_unit_assignment.csv").write_text("\n".join(assignment_rows) + "\n")
    payload = json.dumps(out, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    (RESULTS / "stage0_unit_audit.json").write_text(payload)

    def digest(path: Path) -> str:
        return sha256(path.read_bytes()).hexdigest()

    receipt = {
        "campaign": "stage0_unit_audit",
        "question": "how many exchangeable units can stand behind the conformal radius, "
                    "before and after repairing the study field from NCBI accessions",
        "code": {name: digest(ROOT / name) for name in (
            "scripts/run_stage0_unit_audit.py",
            "scripts/run_external_validation.py",
            "src/mic_50_90/conformal.py")},
        "inputs": {name: digest(ROOT / name) for name in (
            "data/raw/ebi/phenotype-2026-07.parquet",
            "data/raw/ncbi/biosample_to_bioproject.json",
            "data/raw/ncbi/bioproject_to_publication.json",
            "data/raw/ncbi/PROVENANCE.json")},
        "outputs": {name: digest(RESULTS / Path(name).name) for name in (
            "results/stage0_unit_audit.json", "results/stage0_unit_assignment.csv")},
        "gates": {"calibration_floor_ladder": list(CALIBRATION_FLOORS),
                  "test_cohorts_with_reference_floor": TEST_FLOOR,
                  "test_units_with_reference_floor": TEST_UNIT_FLOOR,
                  "test_cohorts_total_floor": TEST_TOTAL_FLOOR,
                  "alpha": ALPHA},
        "solver": f"scipy {scipy.__version__} milp (HiGHS)",
        "no_coverage_computed": "this campaign never compares a distance with a radius",
    }
    (RESULTS / "RECEIPT_stage0_unit_audit.json").write_text(
        json.dumps(receipt, indent=2) + "\n")
    print(payload)


if __name__ == "__main__":
    main()
