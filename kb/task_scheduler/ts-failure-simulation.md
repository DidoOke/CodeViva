---
id: ts-failure-simulation
fact: numeric_comparison
where:
  - expr ~ random
priority: 50
dimension: code_understanding
---
# Simulated failures

## Question
At {file}:{line} you simulate failures with `{expr}`. How did you use this to check that your retry policy behaves correctly?

## Follow-up
How would you make a test of the retry path repeatable?

## Good answer mentions
- seeding or injecting the random generator
- forcing failures in tests (stub or monkeypatch)
- the failure rate shapes how often retries are exercised
