# What to ask for when MIC50 and MIC90 are not enough

MIC-50-90 version **1.0.0**.

You have read a paper reporting MIC50 and MIC90, but need to know whether fewer than 5% of its isolates exceeded another concentration. The program first checks whether those summaries already answer your question. If they do not, it identifies counts that would answer it. These are counts of **existing results in the same original sample**, not requests for new susceptibility tests.

For a laboratory preparing a report, the question is different: which numbers should accompany MIC50 and MIC90 so that readers can answer the stated questions? If the results are easy to export together, requesting all necessary counts at once may be best.

## Ask for counts together or one at a time

Add `--acquisition-plan` to the usual `batch` or `reporting-audit` command. The threshold table must specify at least one question through `decision_operator` and `decision_fraction`. For example, `<` and `0.05` asks whether the recorded fraction strictly above the specified concentration is below 5%.

`--round-cost 2` charges two declared units each time a new request/export round is needed. Count costs default to one. A `--decision-queries` CSV can give each permitted count its own nonnegative cost. Set the count costs to zero and the round cost to one to represent one export whose marginal counts are free. These are scenarios specified by you, not measured staff times. Use the same cost unit throughout. Costs must also remain representable in the numeric report; extreme values that underflow or overflow are refused.

The report shows the next counts to **request together**, a sufficient fixed request, and a comparison with requesting one count per round. Remaining cost means the largest cost that the saved plan could require over compatible answers. It does not describe average cost or previously completed work. Maximum rounds and maximum counts are separate bounds and need not occur on the same path.

## Enter the answers

The output directory contains `requested_counts.csv`. The template uses the selected input delimiter, so semicolon and tab workflows can read it back directly. Cohort identifiers for this editable template must not start with =, +, - or @; use a consistent plain identifier across the input tables. Previous accepted answers are retained; new requested counts have blank `count` cells. Enter an exact nonnegative integer count, or fill the count-range or explicit percentage fields described in [returned information](RETURNED_COUNTS.md). Keep the original `n` and save the completed file. Do not replace blanks with zero unless zero is the verified answer. A count is strictly above the stated threshold and concerns the recorded category value.

Rerun the same inputs with `--additional-counts path/to/completed.csv` and a **different output directory**. The program checks all answers together and updates the results. Partial information is allowed: remove unanswered rows before analysis, retaining all completed rows. A blank count is an input error, not an assumed zero. Stop when all selected sample questions have a definite answer.

This stopping instruction applies to the original sample. Population confidence and calibration for a new study unit remain separate. An arbitrary concentration is not automatically a clinical breakpoint, and a fraction above it is not automatically a resistance percentage.

## If a plan is unavailable

An incomplete search can still provide a sufficient request, but it does not establish the cheapest strategy. The default planning deadline is five seconds; `--decision-plan-time-limit` and `--decision-plan-max-states` also control the acquisition mode. Basic valid analysis is preserved if optional planning fails. If the permitted counts cannot settle the question, the JSON contains compatible samples demonstrating why.

`--decision-plan` uses positive per-count costs and requests one count at a time. Choose one planning mode per run. The Python equivalent is `plan_acquisition(specification, criteria, queries=None, round_cost=0, additional_counts=None)`. `max_batch_size=1` restricts `plan_acquisition` to one count per round. The result includes `next_questions`, a complete policy, exact rational costs and search status.

## Worked examples

Run [the request-and-answer tutorial](../examples/acquisition/README.md), then use the [original-publication examples](../examples/published_summaries/README.md). The former illustrates how work organisation changes the recommendation; the latter starts from published summaries and distinguishes source metadata from declared assumptions.

An unfinished acquisition search can show a certified cost interval: the lower endpoint comes from two compatible samples that cannot be distinguished without paying for at least one separating count; the upper endpoint comes from a request already known to suffice. The report gives the remaining gap. A zero gap proves the cost but does not certify unfinished tie-breaking. The two histograms are hypothetical explanations, not individual data.
