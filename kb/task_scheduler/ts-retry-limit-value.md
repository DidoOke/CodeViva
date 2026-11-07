---
id: ts-retry-limit-value
fact: constant
where:
  - name ~ (?i)retr|attempt
priority: 70
dimension: decision_rationale
---
# Choice of retry limit

## Question
`{name}` is {value} at {file}:{line}. How did you choose that number?

## Follow-up
What kind of failure would that limit be wrong for?

## Good answer mentions
- the expected failure rate or nature of transient failures
- trade-off between latency and success rate
- that the number is a policy choice, ideally configurable
