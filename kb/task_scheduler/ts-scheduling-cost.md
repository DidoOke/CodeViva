---
id: ts-scheduling-cost
fact: loop_nesting
where:
  - function ~ (?i)sched|run|main
  - depth >= 2
priority: 60
dimension: code_understanding
---
# Cost of the scheduling loop

## Question
`{function}` has a loop nested {depth} deep starting at {file}:{line}. Roughly how does its running time grow with the number of jobs?

## Follow-up
Which part would become the bottleneck with 100,000 jobs?

## Good answer mentions
- the outer loop runs once per job and the inner loop over attempts or dependents
- total work is about jobs times attempts plus edges
- identifying the real bottleneck (sleeping, sorting, I/O)
