---
id: u-numeric-check
fact: numeric_comparison
priority: 46
dimension: debugging_failure_handling
---
# Boundary condition and numeric comparison

## Question
At {file}:{line} inside `{function}` you check `{expr}`. What boundary case does `{operand}` guard against, and what would happen if `{op}` were off by one?

## Follow-up
How did you test or verify that `{expr}` handles edge inputs accurately?

## Good answer mentions
- the exact boundary condition or invariant protected by the comparison
- the symptom of an off-by-one or boundary error at that line
- a concrete input case that exercises the boundary
