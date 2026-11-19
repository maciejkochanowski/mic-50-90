# Protocol: the count to request

Version 2, fixed on 19 November 2026 before the confirmation run. The scripts are
`evaluation/next_count_rules.py` (choice of the rule) and `evaluation/next_count.py` (evaluation of the
program); their summaries record the SHA-256 of this file.

## Question

When a report gives only MIC50, MIC90 and the observed range, the program names one cumulative count to
request for a stated question. How much does that one count narrow the answer on real collections, and is
it the best single count that could have been requested?

## Data and report

The eligible cohorts of PROTOCOL.md, section 2 (`data/benchmark/eligible.csv.gz`), each with its complete
table. Within every stratum the cohorts are ordered by hash (column `rank`). Three blocks that share no
cohort are used:

| Block | Hash ranks | Cohorts | Use |
|---|---|---|---|
| benchmark | 1 to 10 | 610 | the confirmation cohorts of PROTOCOL.md; examined with version 1 of this protocol while the rule was being developed |
| development | 21 to 30 | 545 | choice of the selection rule |
| confirmation | 11 to 20 | 601 | evaluation of the fixed rule |

No table, report or result of the confirmation block was examined before the rule and this protocol were
fixed. Each table is shortened to the range report R2 of PROTOCOL.md, section 3: MIC50 and MIC90 under
ceiling ranks and the lowest and highest occupied categories. No population analysis is requested.

## Tasks

One task is a cohort and one category whose count the report leaves open (smallest possible count below
largest possible count). The question is the number of isolates in that category, declared as a target
without a criterion. All such categories of all cohorts of a block are tasks.

## The selection rule

For every cumulative count that the report leaves open, and every value that the count can take, the
bounds of the question are computed again. The program names the count that is first in this order:

1. the smallest width that the count leaves in its least favourable value (the largest guaranteed
   reduction);
2. the smallest width averaged over the possible values of the count, each value with equal weight;
3. the fewest category boundaries between the count and the nearer edge of the question range;
4. the fewest category boundaries between the count and the median, where a boundary lies above the median
   when at least half of the isolates are certainly at or below it, below the median when fewer than half
   can be, and otherwise at the median;
5. the lower count.

Steps 1 and 2 are exact for every report. Steps 3 and 4 separate counts that are equal on both measures:
the count next to a category carries the most information about it, and MIC distributions hold most of
their isolates near the median.

## Choice of the rule (development block)

`next_count_rules.py` compares five rules with the independent calculation described below; the program
is not run. All rules begin with step 1. They differ in the steps that follow: the widest open count when
no count guarantees a reduction (the rule examined with version 1 of this protocol); step 2 only; steps 2
and 3 with the lower count on ties; steps 2 and 3 with the higher count on ties; and steps 2 to 4. The
rule with the largest median relative reduction over all tasks of the development block is selected. The
comparison is written to `results/next_count/rule_comparison.json` together with the result of the best
single count, which can be known only afterwards.

## Procedure (every block)

1. The program analyses the report with the question and names its suggested cumulative count
   (`interpretation.suggested_count`), the number of isolates at or below one category.
2. The complete table supplies the value of that count, which is added to the report as an additional
   count, and the program bounds the category again.
3. For comparison, every other cumulative count that the report leaves open is added in the same way,
   one at a time.

## Measures

For each task: the width of the count bound before (W0), after the suggested count (Ws) and after each
alternative count. Reported over all tasks of a block:

- the median, quartiles and mean of the relative reduction 1 − Ws/W0;
- the share of tasks in which the suggested count fixes the category exactly (Ws = 0);
- the share of tasks in which no alternative count gives a narrower bound than the suggested one;
- the median, over tasks, of the mean relative reduction given by the alternative counts;
- the median and quartiles of the relative reduction given by the best single count of each task.

The measures are also given separately for tasks in which some count guarantees a reduction (step 1
decides) and tasks in which none does (steps 2 to 4 decide), and with cohorts given equal weight (mean
over the tasks of a cohort, then median over cohorts).

The result of the paper is the confirmation block. The development and benchmark blocks are reported in
full beside it.

## Independent check

A separate calculation in `next_count.py`, which uses no program code, writes the report as difference
constraints on cumulative counts and closes them by the Floyd–Warshall algorithm. It recomputes every bound
before and after every added count, and compares them with the program. For every task and every candidate
count it also computes, over all possible values of the count, the largest and the average width that can
remain, and from them the count that the selection rule names. It checks that the count named by the
program is that count in every task, that it has the smallest largest width whenever some count guarantees
a reduction, and that the width obtained with the true value is never larger than the guaranteed one.

## Reporting

All tasks are kept. The results are reported as obtained.
