"""Exact-count and split-conformal finite-sample coverage simulations."""

from __future__ import annotations

import json
from math import ceil
from pathlib import Path

import numpy as np
import pandas as pd

from mic_50_90.conformal import split_conformal_radius
from mic_50_90.empirical import closed_form_tail_counts
from mic_50_90.exact_population import clopper_pearson
from mic_50_90.model import QuantileSummary


ROOT = Path(__file__).resolve().parents[1]
SEED = 20260809
REPETITIONS = 3000


def quantile_summary(counts: np.ndarray, probability: float) -> QuantileSummary:
    rank = int(ceil(probability * counts.sum()))
    index = int(np.searchsorted(np.cumsum(counts), rank, side="left"))
    return QuantileSummary(probability, rank, index, str(index), "ceiling")


def population_shape(k: int, shape: str) -> np.ndarray:
    x = np.arange(k, dtype=float)
    if shape == "unimodal":
        p = np.exp(-0.5 * ((x - 3.0) / 1.2) ** 2)
    elif shape == "bimodal":
        p = np.exp(-0.5 * ((x - 1.5) / 0.7) ** 2)
        p += np.exp(-0.5 * ((x - 5.5) / 0.7) ** 2)
    else:
        p = np.exp(-0.5 * ((x - 3.0) / 1.2) ** 2)
        p[-1] += p.sum() * 0.6
    return p / p.sum()


def main() -> None:
    rng = np.random.default_rng(SEED)
    records = []
    for n in (20, 50, 100):
        for shape in ("unimodal", "bimodal", "boundary"):
            p = population_shape(8, shape)
            objectives = []
            for cut in (2, 4):
                tail = np.zeros(8, dtype=int)
                tail[cut + 1 :] = 1
                objectives.append(tail)
            truth_probabilities = [float(item @ p) for item in objectives]
            for replicate in range(REPETITIONS):
                counts = rng.multinomial(n, p)
                summaries = (
                    quantile_summary(counts, 0.5),
                    quantile_summary(counts, 0.9),
                )
                marginal_covered = []
                simultaneous_covered = []
                widths = []
                simultaneous_level = 1.0 - 0.05 / len(objectives)
                for objective, truth in zip(objectives, truth_probabilities):
                    lower_count, upper_count = closed_form_tail_counts(
                        n=n,
                        tail=objective,
                        quantiles=summaries,
                        minimum_index=None,
                        maximum_index=None,
                    )
                    marginal = (
                        clopper_pearson(lower_count, n, 0.95)[0],
                        clopper_pearson(upper_count, n, 0.95)[1],
                    )
                    simultaneous = (
                        clopper_pearson(lower_count, n, simultaneous_level)[0],
                        clopper_pearson(upper_count, n, simultaneous_level)[1],
                    )
                    marginal_covered.append(marginal[0] <= truth <= marginal[1])
                    simultaneous_covered.append(
                        simultaneous[0] <= truth <= simultaneous[1]
                    )
                    widths.append(marginal[1] - marginal[0])
                records.append(
                    {
                        "n": n,
                        "shape": shape,
                        "replicate": replicate,
                        "marginal_threshold_1_covered": marginal_covered[0],
                        "marginal_threshold_2_covered": marginal_covered[1],
                        "both_marginal_sets_cover": all(marginal_covered),
                        "bonferroni_simultaneous_covered": all(simultaneous_covered),
                        "mean_marginal_width": float(np.mean(widths)),
                    }
                )
    frame = pd.DataFrame(records)
    frame.to_csv(ROOT / "results" / "exact_population_coverage_records.csv", index=False)
    grouped = (
        frame.groupby(["n", "shape"], as_index=False)
        .agg(
            marginal_1_coverage=("marginal_threshold_1_covered", "mean"),
            marginal_2_coverage=("marginal_threshold_2_covered", "mean"),
            unadjusted_joint_coverage=("both_marginal_sets_cover", "mean"),
            bonferroni_joint_coverage=("bonferroni_simultaneous_covered", "mean"),
            mean_width=("mean_marginal_width", "mean"),
        )
        .to_dict(orient="records")
    )

    conformal = []
    for calibration_size in (19, 39, 99):
        for shifted in (False, True):
            covered = 0
            for _ in range(10000):
                calibration = rng.exponential(1.0, calibration_size)
                radius, rank = split_conformal_radius(calibration, 0.05)
                new_score = rng.exponential(3.0 if shifted else 1.0)
                covered += new_score <= radius
            conformal.append(
                {
                    "calibration_size": calibration_size,
                    "rank": rank,
                    "exchangeable": not shifted,
                    "coverage": covered / 10000,
                }
            )
    summary = {
        "seed": SEED,
        "repetitions_per_exact_cell": REPETITIONS,
        "exact_iid_population": grouped,
        "split_conformal": conformal,
        "distribution_shift_experiment_has_no_coverage_guarantee": True,
    }
    (ROOT / "results" / "v1_coverage_simulation_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
