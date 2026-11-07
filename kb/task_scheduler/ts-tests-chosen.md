---
id: ts-tests-chosen
fact: test_function
priority: 65
dimension: debugging_failure_handling
---
# Why this test exists

## Question
You wrote `{name}` in {file}. What bug or behaviour were you worried about when you wrote it?

## Follow-up
What important behaviour is still not covered by any test?

## Good answer mentions
- a specific risk or past bug the test guards
- how the test isolates randomness or sleeping
- an honest gap, such as dependency cycles or malformed input
