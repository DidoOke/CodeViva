---
id: ts-retry-off-by-one
fact: numeric_comparison
where:
  - operand ~ (?i)retr|attempt
priority: 75
dimension: code_understanding
---
# How many attempts really happen

## Question
At {file}:{line} you check `{expr}`. With your current settings, how many times does a failing job actually run before it is marked failed?

## Follow-up
Where in the code would you change it so the limit counts total attempts instead?

## Good answer mentions
- range(MAX_RETRIES + 1) means one initial attempt plus MAX_RETRIES retries
- the comparison fires on the final attempt
- distinguishing retries from attempts
