"""Prespecified factorial stress test for MIC-50-90 v1."""

from __future__ import annotations

from itertools import product
import json
from math import ceil, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel, QuantileSummary


ROOT = Path(__file__).resolve().parents[1]
SEED = 20260809
REPLICATES = 6


def probabilities(k: int, shape: str, equal_quantiles: bool, boundary: str) -> np.ndarray:
    x = np.arange(k, dtype=float)
    if equal_quantiles:
        p = np.full(k, 0.08 / max(1, k - 1))
        p[k // 2] = 0.92
    elif shape == "unimodal":
        p = np.exp(-0.5 * ((x - (k - 1) / 2) / max(1.0, k / 6)) ** 2)
    else:
        p = np.exp(-0.5 * ((x - k * 0.25) / 0.8) ** 2)
        p += np.exp(-0.5 * ((x - k * 0.75) / 0.8) ** 2)
    if boundary == "left":
        p[0] += p.sum() * 0.35
    elif boundary == "right":
        p[-1] += p.sum() * 0.35
    return p / p.sum()


def apply_censoring(counts: np.ndarray, censoring: str) -> np.ndarray:
    result = counts.copy()
    if censoring in {"left", "both"} and len(result) >= 3:
        result[1] += result[0]
        result[0] = 0
    if censoring in {"right", "both"} and len(result) >= 3:
        result[-2] += result[-1]
        result[-1] = 0
    return result


def apply_dilution_stress(counts: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    observations = np.repeat(np.arange(len(counts)), counts)
    shifts = rng.choice([-1, 0, 1], size=len(observations), p=[0.1, 0.8, 0.1])
    shifted = np.clip(observations + shifts, 0, len(counts) - 1)
    return np.bincount(shifted, minlength=len(counts))


def quantile(counts: np.ndarray, probability: float) -> tuple[int, int]:
    rank = int(ceil(probability * counts.sum()))
    return rank, int(np.searchsorted(np.cumsum(counts), rank, side="left"))


def main() -> None:
    rng = np.random.default_rng(SEED)
    records = []
    factors = product(
        [20, 100, 500],
        [4, 8, 12],
        ["below_MIC50", "between_MIC50_MIC90", "at_MIC90"],
        [False, True],
        ["unimodal", "bimodal"],
        ["none", "left", "right"],
        ["none", "left", "right", "both"],
    )
    for n, k, relation, equal, shape, boundary, censoring in factors:
        levels = np.power(2.0, np.arange(k) - k // 2)
        panel = MICPanel.from_twofold_levels(
            levels, left_censored=False, right_censored=False
        )
        p = probabilities(k, shape, equal, boundary)
        for replicate in range(REPLICATES):
            raw = rng.multinomial(n, p)
            observed = apply_censoring(raw, censoring)
            dilution_stress = replicate % 2 == 1
            if dilution_stress:
                observed = apply_dilution_stress(observed, rng)
            rank50, q50 = quantile(observed, 0.5)
            rank90, q90 = quantile(observed, 0.9)
            if relation == "below_MIC50":
                threshold = float(levels[max(0, q50 - 1)])
            elif relation == "between_MIC50_MIC90" and q50 < q90:
                threshold = float(sqrt(levels[q50] * levels[q90]))
            else:
                threshold = float(levels[q90])
            summaries = (
                QuantileSummary(0.5, rank50, q50, panel.labels[q50], "ceiling"),
                QuantileSummary(0.9, rank90, q90, panel.labels[q90], "ceiling"),
            )
            extrema_reported = replicate % 3 == 0
            minimum = int(np.flatnonzero(observed)[0]) if extrema_reported else None
            maximum = int(np.flatnonzero(observed)[-1]) if extrema_reported else None
            objective = panel.panel_tail(threshold)
            truth = int(objective @ observed)
            base = {
                "n": n,
                "categories": k,
                "threshold_relation": relation,
                "equal_quantile_categories_requested": equal,
                "equal_quantile_categories_observed": q50 == q90,
                "shape": shape,
                "boundary_mass": boundary,
                "censoring": censoring,
                "dilution_variation_stress": dilution_stress,
                "dilution_variation_interpretation": "aggregate measurement stress only; not an isolate error model",
                "extrema_reported": extrema_reported,
                "replicate": replicate,
            }
            try:
                problem = EmpiricalProblem(
                    n=n,
                    panel=panel,
                    quantiles=summaries,
                    minimum_index=minimum,
                    maximum_index=maximum,
                )
                lower, upper = problem.bounds(objective)
                records.append(
                    {
                        **base,
                        "available": True,
                        "covered": lower.count <= truth <= upper.count,
                        "lower": lower.fraction,
                        "upper": upper.fraction,
                        "width": upper.fraction - lower.fraction,
                        "certificate_ok": lower.certificate.optimality_verified
                        and upper.certificate.optimality_verified,
                        "fallback_used": lower.certificate.fallback_used
                        or upper.certificate.fallback_used,
                    }
                )
            except (RuntimeError, ValueError) as exc:
                records.append(
                    {
                        **base,
                        "available": False,
                        "covered": False,
                        "certificate_ok": False,
                        "error": str(exc),
                    }
                )
    frame = pd.DataFrame(records)
    destination = ROOT / "results" / "stress_test_records.csv"
    frame.to_csv(destination, index=False)
    summary = {
        "prespecified": True,
        "seed": SEED,
        "records_total_denominator": int(len(frame)),
        "available": int(frame["available"].sum()),
        "failures_in_denominator": int((~frame["available"]).sum()),
        "coverage_all_denominator": float(frame["covered"].mean()),
        "certificate_success_all_denominator": float(frame["certificate_ok"].mean()),
        "fallback_rate": float(frame["fallback_used"].fillna(False).mean()),
        "mean_width_available": float(frame.loc[frame["available"], "width"].mean()),
        "worst_cells": (
            frame[frame["available"]]
            .groupby(
                [
                    "n",
                    "categories",
                    "threshold_relation",
                    "equal_quantile_categories_observed",
                    "shape",
                    "boundary_mass",
                    "censoring",
                    "dilution_variation_stress",
                ],
                as_index=False,
            )
            .agg(mean_width=("width", "mean"), coverage=("covered", "mean"))
            .sort_values("mean_width", ascending=False)
            .head(25)
            .to_dict(orient="records")
        ),
    }
    (ROOT / "results" / "stress_test_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
