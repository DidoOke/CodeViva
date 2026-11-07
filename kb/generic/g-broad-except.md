---
id: g-broad-except
fact: exception_handler
where:
  - broad = true
priority: 45
dimension: debugging_failure_handling
---
# A broad exception handler

## Question
At {file}:{line} in `{function}` the handler `{handler}` is used. What failures can reach that handler, and what happens to them?

## Follow-up
If a genuine bug in your own code raised an error there, how would you find out?

## Good answer mentions
- which concrete exceptions can occur there
- that broad handlers can hide programming errors
- narrowing the exception type or logging/re-raising
