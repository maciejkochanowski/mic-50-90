# Count requests: a constructed teaching case

Ten isolates have MIC50 = 1 and MIC90 = 2 mg/L under ceiling ranks. The questions ask whether fewer than 5% of the
isolates exceed 2, 4 and 8 mg/L; with ten isolates each question asks whether the corresponding count is zero. The
inputs are constructed for teaching; they are not patient data or measured laboratory work.

| File | Content |
|---|---|
| summaries.csv | n, ranks, MIC50 and MIC90 |
| panels.csv | The declared MIC categories |
| targets.csv | The three questions |
| completed.csv | The teaching reply: one isolate above 2 mg/L and none above 4 or 8 mg/L |

The commands are in COUNT REQUESTS and LINKED CSV TABLES of ../../COMMANDS.txt. With no cost per request round the
planner asks for the count above 4 mg/L first and needs at most two counts; with a cost of two per round it asks for
all three counts at once. Appendix C.7 explains the result.
