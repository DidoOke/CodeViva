---
id: u-exception-handling
fact: exception_handler
priority: 50
dimension: debugging_failure_handling
---
# Exception recovery path

## Question
At {file}:{line} in `{function}` you use `{handler}`. Which failure conditions are expected to enter this block, and why is `{body_kind}` the right recovery action?

## Follow-up
How does the caller of `{function}` know whether this error path was triggered?

## Good answer mentions
- the specific failure condition that triggers the exception
- why the chosen handler action (`pass`, `return`, `raise`, `log`) is safe
- how errors are surfaced or logged for debugging
