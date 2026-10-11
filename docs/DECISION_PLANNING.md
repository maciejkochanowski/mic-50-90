# Choose counts that resolve your sample criteria

Use `batch --decision-plan` or `reporting-audit --decision-plan` when the targets CSV contains explicit criteria such as `decision_operator=<` and `decision_fraction=0.05`. The goal is to settle **every individual criterion** about the original sample's recorded MIC categories. A supported result means every compatible histogram satisfies that criterion; contradicted means none does. Settling these sample questions does not establish a population claim or remove uncertainty about concentrations inside interval categories.

The report names the next recorded-tail count, its acquisition cost and the greatest total remaining cost along the returned policy. After recovering that count, rerun `batch` with `--additional-counts` and retain every answer already obtained. Counts must use the original denominator and cohort. The [worked example](../examples/decision_planning/README.md) goes from three unresolved criteria to a two-count plan and a completed result.

## Costs and permitted counts

Without a query file, every internal panel cut is permitted at cost one. This makes cost the number of count requests, not time spent computing or laboratory effort. A direct count at a target is available by default. `--exclude-direct-targets` deliberately removes such cuts from both question planners and can make a criterion impossible to resolve.

Supply `--decision-queries queries.csv` to restrict candidates and prices:

```text
cohort_id,threshold,unit,cost
study-a,2,mg/L,10
study-a,4,mg/L,1
study-a,8,mg/L,10
```

Every price must be positive and expressed in the same user-chosen cost unit. Equivalent cuts cannot have two prices. A cohort missing from a supplied whitelist has no permitted questions; it does not silently regain the defaults. Costs remain fixed across answers. Batch-retrieval discounts, delays between requests, noisy counts and new-sample measurements are outside this model.

## Reading the status

| Status | What follows | Next step |
|---|---|---|
| Already resolved | Every declared criterion already has a definite sample answer | No further count is needed for these criteria. |
| Optimal | The returned policy attains the least worst-case acquisition cost within the declared model | Request its first count, then follow the corresponding answer branch or rerun with all obtained counts. |
| Impossible | Two compatible histograms give identical answers at every permitted cut but disagree on a criterion | Review the query restriction or obtain other metadata. The witness pair explains the conflict. |
| Incomplete | A time or state limit prevented a complete search | A returned fixed plan is a verified upper bound only. Increase limits if establishing optimality matters. |
| Unavailable | The optional planner's inputs are invalid | Correct the stated field. The CSV workflow preserves valid basic analysis results. |

The fixed-plan comparison in the report is a feasible baseline. It is the minimum fixed cost only when `fixed_plan_optimality_verified` is true. A union of reporting variants can sometimes be distinguished by cheaper counts elsewhere, so the direct-target baseline need not be its best fixed plan.

The default limits are five seconds and 5,000 explored states; change them with `--decision-plan-time-limit` and `--decision-plan-max-states`. General variant unions and criteria with different count boundaries can require many states. A timeout never proves impossibility. The exact cost is retained as a fraction in JSON so small price differences are not decided by display rounding.

## Why this differs from narrowing an interval

The additional-information section of a report ranks one count by its guaranteed reduction in the sum of interval widths. The decision planner minimizes the total worst-case cost until all declared criteria are settled. A wide interval can already settle a lenient criterion, while a narrow interval can straddle an important boundary. The two objectives can therefore select different questions.

For one feasible reporting interpretation and a common integer count boundary, an exact reduction gives an ordered-search algorithm whose arithmetic work is independent of sample size. With m unresolved target cuts at equal cost, it requires at most and in the worst case exactly `ceil(log2(m+1))` counts. A fixed set needs all m. General decision-tree optimization and ordered search are established methods; The implementation and independent decision-tree oracle are in src/mic_50_90/decision_planning.py and tests/test_decision_planning.py.

## Python interface

```python
from mic_50_90 import plan_decisions

plan = plan_decisions(
    specification,
    [{"threshold": 4, "unit": "mg/L",
      "decision_operator": "<", "decision_fraction": "0.05"}],
    queries=None,
    additional_counts=None,
    time_limit_seconds=5.0,
    max_states=5000,
)
```

`specification` uses the empirical JSON input contract. `queries=None` enables defaults; `queries=[]` permits none. Each explicit query contains `threshold`, `unit` and `cost`. The return value includes initial criterion statuses, allowed queries, costs, resource status, a policy and any impossibility witness. The adaptive policy is a graph with a root node, inclusive integer tail-count branch ranges, and terminal decision vectors. Exact comparisons use the original decimal criterion, not displayed percentages. An empty compatible set raises an input error; it cannot produce a successful stopping result.

## Request several counts together

The optional `--acquisition-plan` workflow compares one export with successive requests and provides a CSV to enter the answers. Counts come from existing records, not new susceptibility tests. See [the practical guide](ACQUIRING_COUNTS.md).
