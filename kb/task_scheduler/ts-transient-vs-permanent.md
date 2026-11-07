---
id: ts-transient-vs-permanent
fact: exception_handler
where:
  - exc_types ~ (?i)transient|timeout|retry|connection
priority: 80
dimension: debugging_failure_handling
---
# Which failures are retried

## Question
At {file}:{line} in `{function}` you catch `{exc_types}`. Which failures does your scheduler retry, and which does it not?

## Follow-up
What should happen to an error that retrying can never fix, such as invalid job data?

## Good answer mentions
- only transient errors are worth retrying
- permanent errors should fail fast
- a dedicated exception type separates the two
- what happens to unexpected exceptions
