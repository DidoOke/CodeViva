---
id: u-module-constant
fact: constant
priority: 48
dimension: decision_rationale
---
# Module configuration constant

## Question
At {file}:{line} you define `{name} = {value}`. Why did you choose `{value}` for `{name}`, and what trade-offs would changing it introduce?

## Follow-up
What happens in your program if `{name}` is set to an extreme value or overridden by a caller?

## Good answer mentions
- the role of the constant in controlling program behaviour or thresholds
- trade-offs of a larger versus smaller value
- how configuration or boundary values are validated in the module
