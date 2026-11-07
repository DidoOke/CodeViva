---
id: r-function-rewritten
fact: function_changed
where:
  - churn >= 0.5
priority: 75
dimension: code_understanding
---
# Function largely rewritten since last round

## Question
`{function}` in {file} was largely rewritten since last round ({lines_before} to {lines_after} lines). What about the old version did not work for this round's requirements?

## Follow-up
What did you deliberately keep from the old version?

## Good answer mentions
- names the requirement or behaviour that forced the change
- can walk through the new control flow
- knows which old behaviour must still hold (and ideally how it is tested)
