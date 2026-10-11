# Describe the MIC distribution at a requested precision

MIC-50-90 1.0.0 distinguishes missing information about the tested isolates from
uncertainty about a population. A 95% confidence level is not 95% accuracy of an
individual MIC result.

In the Windows form, enter the sample size and the actual MIC categories, then
copy the available summaries or counts. A count can refer to results above a
concentration or to adjacent categories: choose **Inside a group of adjacent MIC
categories**, then select the first and last included category. Both endpoints
are included. Do not supply a new denominator for an existing sample.

If independent, identically distributed sampling is appropriate, acknowledge
that assumption in **Extend the result to a population**. Select the confidence
level and largest acceptable interval width; 10 means 10 percentage points,
such as 20–30%. The result shows a confirmed grouping, its population intervals
and the possible maximum number of groups. An unresolved maximum reflects
unfinished numerical evidence. One group covering the whole panel gives no
information about the distribution inside the panel.

To ask for missing information, select **Plan which counts to request from these
same isolates**. By default the goal retains every supplied category. The next
question names the categories and denominator. This requests existing records;
it does not request new susceptibility tests. Add the answer using **Add a
count**, retaining earlier inputs. The full tree and cost bounds are in JSON.

Command-line equivalent:

```text
mic-50-90 distribution input.json --population-precision-pp 10 --population-count-plan --output-dir output
```

The population target is independent of `--precision-pp` (sample grouping) and
`--population-tolerance-pp` (numerical endpoint tolerance). JSON may declare
`required_population_cuts`, a list of category cut indices strictly between 0
and K. `population_count_queries` lists permitted objects with `start_index`,
exclusive `stop_index`, and positive `cost`; omission permits all proper
contiguous ranges at unit cost, while an empty list permits no queries.

Additional-count CSV rows use `cohort_id,unit,n,start_category,end_category,count`.
Use the exact panel labels, not indices, for the inclusive endpoints. Instead
of `count`, supply `count_min,count_max`, or
`percentage,decimal_places,rounding_rule`. Old threshold rows remain valid.
Do not fill a threshold or relation in a category-range row.

The planner distinguishes a completed sufficient plan, a verified minimum,
a failure to guarantee success for all answers, and unfinished computation.
A single complete-histogram failure witness proves only that universal success
is impossible under the selected method. It does not imply every compatible
histogram would fail. Cost is the declared cost of retrieving existing counts,
not measured laboratory work time.

The planning time limit is cooperative. An individual mandatory population
baseline calculation is allowed to finish before the next deadline check;
the recorded elapsed time can therefore exceed the requested search time.
