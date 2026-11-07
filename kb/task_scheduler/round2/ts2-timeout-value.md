---
id: ts2-timeout-value
fact: constant
where:
  - name ~ (?i)timeout
priority: 86
dimension: decision_rationale
---
# Timeout value

## Question
You set `{name} = {value}`. How did you choose that value, and what happens to a job that is still running when it expires?

## Follow-up
How would your scheduler treat a slow but healthy job differently from a stuck one?

## Good answer mentions
- relates the value to expected job duration or retries and backoff
- knows whether a running thread can actually be stopped (in Python it usually cannot be killed)
- what the summary reports for timed-out jobs and their dependents
