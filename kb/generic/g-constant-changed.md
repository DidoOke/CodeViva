---
id: g-constant-changed
fact: constant_changed
priority: 40
dimension: decision_rationale
---
# A tuned constant changed between commits

## Question
In commit {commit_short} ("{commit_message}") `{name}` changed from {old} to {new}. What did you observe that made you change it?

## Follow-up
How would you check whether {new} is a better value than {old}?

## Good answer mentions
- a concrete observation (test result, bug, behaviour) that prompted the change
- what the old value got wrong
- a way to evaluate the new value rather than guessing
