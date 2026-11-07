---
id: ts-silent-failure
fact: exception_handler
where:
  - body_kind in pass, continue
priority: 90
dimension: debugging_failure_handling
---
# A failure swallowed silently

## Question
At {file}:{line} in `{function}` the handler `{handler}` just does `{body_kind}`. What happens to a job whose every attempt fails there?

## Follow-up
How would someone running your scheduler find out that a job had failed?

## Good answer mentions
- the failure is lost: no record, no message
- the job may be silently dropped from results
- recording the failure and reporting it
- catching a narrower exception type
