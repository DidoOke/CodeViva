---
id: ts-dependency-failure-fix
fact: fix_commit
where:
  - commit_message ~ (?i)depend|skip|never|resolved|blocked
priority: 90
dimension: debugging_failure_handling
---
# Dependents of failed jobs

## Question
Your commit "{commit_message}" ({commit_short}) changed what happens after a job fails. What was the bug before that commit?

## Follow-up
Why mark a dependent job as skipped rather than failed?

## Good answer mentions
- dependents never became ready and were missing from the results
- propagating to all transitive dependents
- skipped versus failed tells the user the job never ran
