---
id: ts2-worker-count
fact: constant
where:
  - name ~ (?i)worker|pool|thread
priority: 70
dimension: decision_rationale
---
# Number of workers

## Question
You set `{name} = {value}`. What limits how many workers are actually useful for this scheduler?

## Follow-up
What would you measure to choose a better number?

## Good answer mentions
- I/O-bound vs CPU-bound work; the GIL for CPU-bound Python threads
- dependency structure limits parallelism (a chain cannot run in parallel)
- a measurement: run time vs worker count on a realistic job file
