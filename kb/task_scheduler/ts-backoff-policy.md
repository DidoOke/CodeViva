---
id: ts-backoff-policy
fact: constant
where:
  - name ~ (?i)backoff|delay|wait|sleep
priority: 75
dimension: decision_rationale
---
# Backoff parameters

## Question
Your scheduler waits between attempts using `{name}` = {value} ({file}:{line}). Why wait at all, and why this value?

## Follow-up
What is the longest a single job could wait across all its retries?

## Good answer mentions
- waiting gives transient faults time to clear
- exponential growth with a cap avoids unbounded waits
- computing the worst-case total delay
- jitter or load on a shared dependency
