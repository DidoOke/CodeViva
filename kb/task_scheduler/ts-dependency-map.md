---
id: ts-dependency-map
fact: data_structure
where:
  - structure in defaultdict, Counter
priority: 55
dimension: code_understanding
---
# Representation of dependencies

## Question
In `{function}` ({file}:{line}) you build a `{structure}`. What does it map from and to, and how is it used when a job finishes?

## Follow-up
What happens with this structure if two jobs depend on each other?

## Good answer mentions
- maps a job to the jobs that depend on it (reverse edges)
- decrementing a waiting count to find newly ready jobs
- a dependency cycle means jobs never become ready
