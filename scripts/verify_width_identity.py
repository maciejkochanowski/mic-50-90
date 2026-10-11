"""Check sample-width identities and count-question planning on configured cases.

Part 1 requires a separately supplied results/external_validation_records.csv.
Part 2 runs controlled panel geometries through the count-question planner.
These checks validate the stated configurations; they are not a general proof.

Run from the source directory with the external records present:
    PYTHONPATH=src python scripts/verify_width_identity.py
Use --skip-minimax to perform only the record-based width check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "results" / "external_validation_records.csv"


def part1_width_identity() -> None:
    d = pd.read_csv(RECORDS)
    n = d["n"].astype(int).to_numpy()
    r50 = np.ceil(0.5 * n).astype(int)
    r90 = np.ceil(0.9 * n).astype(int)
    rel = d["threshold_relation"].to_numpy()
    eq = d["quantile_categories_equal"].to_numpy()
    w = d["width"].to_numpy()

    w_gap = (r90 - r50 - 1) / n      # threshold inside the reported rank gap
    w_top = (n - r90) / n            # at or above MIC90, panel extends higher

    interior = rel == "between_MIC50_MIC90"
    at50_distinct = (rel == "at_MIC50") & (~eq)
    branch = np.where(interior | at50_distinct, w_gap, w_top)

    print("=== Proposition 1: width identity ===")
    print(f"records: {len(d)}")
    for name, mask, pred in [
        ("threshold strictly between MIC50 and MIC90", interior, w_gap),
        ("threshold at MIC50, distinct quantile categories", at50_distinct, w_gap),
    ]:
        hit = int((np.abs(w[mask] - pred[mask]) < 1e-12).sum())
        print(f"  {name:52s} {hit}/{int(mask.sum())} exact")
    covered = (np.abs(w - branch) < 1e-12) | (w == 0.0)
    print(f"  every record in {{closed-form value, 0}}          {int(covered.sum())}/{len(w)}")

    # the zero branch is the top-dilution case, not a small-n artefact
    at90 = rel == "at_MIC90"
    zero = at90 & (w == 0.0)
    print(f"  zero-width at_MIC90 explained by n<10 (r90==n)     "
          f"{int((zero & (n == r90)).sum())}/{int(zero.sum())} "
          f"(the rest are MIC90 at the top tested dilution)")

    print("\n--- the width grows with sample size, it does not shrink ---")
    rho = spearmanr(n[interior], w[interior])
    print(f"  Spearman(n, width) over interior records = {rho.statistic:.3f} (p = {rho.pvalue:.1e})")
    for lo, hi in [(0, 50), (50, 100), (100, 200), (200, 500), (500, 10**9)]:
        m = interior & (n >= lo) & (n < hi)
        if m.sum():
            label = f"[{lo},{hi})" if hi < 10**9 else f">={lo}"
            print(f"    n {label:>10s}  k={int(m.sum()):4d}  mean width = {w[m].mean():.4f}")
    print("  limit as n grows: 0.4")

    print("\n--- so a group ranking by width is a ranking by cohort size ---")
    e = d[d.source == "EMBL-EBI AMR Portal 2026-07"]
    g = e.groupby(["species", "drug"]).agg(
        mw=("width", "mean"), mn=("n", "median"), k=("width", "size")
    )
    g = g[g.k >= 3]
    rho = spearmanr(g.mw, g.mn)
    top8 = g.sort_values("mw", ascending=False).head(8)
    print(f"  {len(g)} organism-drug groups with >=3 threshold records")
    print(f"  Spearman(group mean width, group median n) = {rho.statistic:.3f} (p = {rho.pvalue:.1e})")
    print(f"  the 8 widest groups have median n {top8.mn.min():.0f} to {top8.mn.max():.0f}")
    print(f"  every zero-width group has median n <= {g[g.mw == 0].mn.max():.0f}")


def part2_minimax() -> None:
    from mic_50_90.empirical import EmpiricalProblem, QuantileSummary
    from mic_50_90.model import MICPanel
    from mic_50_90.utility import rank_tail_count_questions

    def build(n: int, k: int, k50: int, k90: int):
        levels = np.array([0.25 * 2.0**i for i in range(k)])
        panel = MICPanel.from_twofold_levels(levels, left_censored=False, right_censored=False)
        r50, r90 = int(np.ceil(0.5 * n)), int(np.ceil(0.9 * n))
        return EmpiricalProblem(
            n=n,
            panel=panel,
            quantiles=(
                QuantileSummary(0.5, r50, k50, panel.labels[k50], "ceiling"),
                QuantileSummary(0.9, r90, k90, panel.labels[k90], "ceiling"),
            ),
        )

    def tail(k: int, cut: int) -> np.ndarray:
        o = np.zeros(k)
        o[cut + 1:] = 1.0
        return o

    rng = np.random.default_rng(20260819)
    geometries = [(12, 5, 1, 3), (12, 6, 1, 4), (16, 6, 2, 4),
                  (20, 5, 1, 3), (20, 6, 1, 3), (24, 6, 2, 4)]
    while len(geometries) < 30:
        k = int(rng.integers(5, 9))
        n = int(rng.integers(12, 60))
        k50 = int(rng.integers(1, k - 2))
        k90 = int(rng.integers(k50 + 1, k - 1))
        geometries.append((n, k, k50, k90))

    single_max, single_pairs, questions = 0.0, 0, 0
    multi_max, multi_geoms = 0.0, 0
    exact_hits, exact_total = 0, 0

    print("\n=== Proposition 2: minimax value of one extra cumulative count ===")
    for n, k, k50, k90 in geometries:
        prob = build(n, k, k50, k90)
        targets = list(range(k50, k90 + 1))
        for t in targets:
            scores = rank_tail_count_questions(problem=prob, target_objectives=[tail(k, t)])
            if not scores:
                continue
            single_pairs += 1
            questions += len(scores)
            single_max = max(single_max, max(s.minimax_width_reduction for s in scores))
        joint = sorted({k50, (k50 + k90) // 2, k90})
        scores = rank_tail_count_questions(
            problem=prob, target_objectives=[tail(k, t) for t in joint]
        )
        if scores:
            multi_geoms += 1
            multi_max = max(multi_max, max(s.minimax_width_reduction for s in scores))
        # the count at the threshold itself identifies the fraction exactly
        for t in targets:
            objective = tail(k, t)
            lo, hi = prob.bounds(objective)
            for answer in range(lo.count, hi.count + 1):
                try:
                    conditional = prob.with_equality(objective, answer)
                except ValueError:
                    continue
                cl, cu = conditional.bounds(objective)
                exact_total += 1
                exact_hits += int(cu.fraction - cl.fraction == 0.0)
        print(f"  done n={n} K={k} k50={k50} k90={k90}", flush=True)

    print(f"\n  geometries: {len(geometries)}")
    print(f"  single target: {single_pairs} target-geometry pairs, "
          f"{questions} candidate questions scored")
    print(f"    largest minimax width reduction over every candidate = {single_max:.3e}")
    print(f"  2-3 simultaneous targets: {multi_geoms} geometries")
    print(f"    largest minimax width reduction = {multi_max:.3e}")
    print(f"  count AT the threshold: width 0 in {exact_hits}/{exact_total} "
          f"(answer, geometry) pairs")


if __name__ == "__main__":
    part1_width_identity()
    if "--skip-minimax" not in sys.argv:
        part2_minimax()
