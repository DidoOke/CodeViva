---
id: u-module-import
fact: import
priority: 30
dimension: code_understanding
---
# Dependency and module boundary

## Question
At {file}:{line} you import `{names}` from `{module}`. How is `{names}` used in `{file}`, and why did you structure that dependency this way?

## Follow-up
If you needed to swap or mock `{module}` during unit testing, how would `{file}` be affected?

## Good answer mentions
- the specific responsibility delegated to the imported module or symbol
- how data flows across the module boundary
- how coupling or testability is managed in that file
