---
id: ts-input-crash-fix
fact: fix_commit
where:
  - commit_message ~ (?i)crash|missing|key|input|malformed
priority: 85
dimension: debugging_failure_handling
---
# Crash on malformed input fixed

## Question
Your commit "{commit_message}" ({commit_short}) fixed a crash. What input caused it, and how did you decide what to do with such input?

## Follow-up
Is silently skipping a bad job always the right policy?

## Good answer mentions
- the concrete malformed input (missing key, wrong type)
- choice between default values, skipping, and failing loudly
- logging or reporting what was skipped
