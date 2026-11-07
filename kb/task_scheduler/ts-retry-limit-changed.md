---
id: ts-retry-limit-changed
fact: constant_changed
where:
  - name ~ (?i)retr|attempt
priority: 95
dimension: decision_rationale
---
# Retry limit changed between commits

## Question
In commit {commit_short} ("{commit_message}") you changed `{name}` from {old} to {new}. What made you change it, and what did you give up?

## Follow-up
What would you expect to happen to total run time if a dependency was down for a minute?

## Good answer mentions
- retries cost time and can hammer a failing dependency
- too few retries turns transient failures into permanent ones
- the interaction with backoff: total wait across attempts
- a concrete trigger such as a slow test run or observed behaviour
