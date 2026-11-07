---
id: ts2-shared-state
fact: import_added
where:
  - module ~ ^(threading|concurrent|multiprocessing|asyncio)
priority: 94
dimension: code_understanding
---
# Concurrency added: shared state

## Question
This round you added `{module}`. Which data in your scheduler can now be read or changed by two workers at the same time, and how do you protect it?

## Follow-up
What would you expect to see in the results if that protection were missing?

## Good answer mentions
- identifies the shared structures (results, waiting counts, ready queue) and which thread touches each
- explains the protection actually used (lock, single coordinating thread, thread-safe queue)
- may correctly say a structure is only touched by one thread and so needs no lock
