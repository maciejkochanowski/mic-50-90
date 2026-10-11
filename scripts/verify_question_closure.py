"""Independent LP parity and timing evidence for the cumulative-count search."""
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from mic_50_90.empirical import EmpiricalProblem
from mic_50_90.model import MICPanel, QuantileSummary
from mic_50_90.utility import rank_robust_tail_count_questions, _rank_robust_tail_count_questions_lp

ROOT = Path(__file__).resolve().parents[1]


def main():
    rng = np.random.default_rng(20260926)
    records = []
    for case in range(30):
        k = int(rng.integers(4, 8))
        n = int(rng.integers(6, 25))
        panel = MICPanel.from_twofold_levels([2.0**i for i in range(k)],
                                           left_censored=False, right_censored=False)
        counts = rng.multinomial(n, np.full(k, 1/k))
        cumulative = counts.cumsum()
        problems = {}
        for name, shift in [("ceiling", 0), ("alternative", -1)]:
            ranks = [max(1, int(np.ceil(p*n))+shift) for p in (.5, .9)]
            categories = [int(np.searchsorted(cumulative, r)) for r in ranks]
            problems[name] = EmpiricalProblem(n=n, panel=panel,
                quantiles=[QuantileSummary(p, r, c, panel.bins[c].label)
                           for p, r, c in zip((.5, .9), ranks, categories)],
                minimum_index=int(np.flatnonzero(counts)[0]) if case % 2 else None,
                maximum_index=int(np.flatnonzero(counts)[-1]) if case % 2 else None)
        targets = [panel.panel_tail(panel.bins[j].panel_value)
                   for j in sorted(rng.choice(k-1, size=min(3, k-1), replace=False))]
        kwargs = dict(problems=problems, target_objectives=targets,
                      exclude_direct_targets=bool(case % 3 == 0))
        start = perf_counter()
        reference = _rank_robust_tail_count_questions_lp(**kwargs)
        lp_seconds = perf_counter()-start
        start = perf_counter()
        actual = rank_robust_tail_count_questions(**kwargs)
        closure_seconds = perf_counter()-start
        repeated = rank_robust_tail_count_questions(**kwargs)
        assert [asdict(s) for s in actual] == [asdict(s) for s in repeated]
        by_cut = {s.cut_index: s for s in actual}
        assert set(by_cut) == {s.cut_index for s in reference}
        max_difference = 0.0
        for expected in reference:
            found = by_cut[expected.cut_index]
            for field in ("feasible_answer_min", "feasible_answer_max", "feasible_answers_evaluated",
                          "reporting_variants_considered"):
                assert getattr(found, field) == getattr(expected, field), (case, field)
            for field in ("baseline_total_width", "worst_case_residual_width", "minimax_width_reduction",
                          "score_per_cost"):
                difference = abs(getattr(found, field)-getattr(expected, field))
                max_difference = max(max_difference, difference)
                assert difference < 1e-9, (case, field, difference)
        records.append(dict(case=case, n=n, categories=k, candidates=len(actual),
                            max_difference=max_difference, lp_seconds=lp_seconds,
                            closure_seconds=closure_seconds, deterministic_repeat=True))
    output = ROOT / "results/v1.0.0/question-closure"
    output.mkdir(parents=True, exist_ok=True)
    summary = dict(seed=20260926, cases=len(records), all_passed=True, records=records,
                   timing_scope="Shared workstation; algorithm comparison, not a dedicated hardware benchmark",
                   lp_seconds=sum(r["lp_seconds"] for r in records),
                   closure_seconds=sum(r["closure_seconds"] for r in records),
                   maximum_absolute_difference=max(r["max_difference"] for r in records))
    (output/"results.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    paths = [Path(__file__)] + list((ROOT/"src/mic_50_90").glob("*.py"))
    receipt = dict(campaign="question_closure", status="executed",
                   code={str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in paths},
                   outputs={"results.json": sha256((output/"results.json").read_bytes()).hexdigest()})
    (output/"RECEIPT.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k != "records"}, indent=2))


if __name__ == "__main__":
    main()
