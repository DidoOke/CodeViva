# Knowledge base rules

Each `*.md` file in a kb directory is one rule written by the course team. Rules match
**facts** (stage 1, see `facts.py`) and turn them into questions that use the student's own
names, numbers and commit messages. `README.md` and `spec.md` are not rules.

```markdown
---
id: ts-retry-limit-changed          # unique across all kb dirs
fact: constant_changed              # fact kind, or "always" (asked whatever the code)
where:                              # all conditions must hold (optional)
  - name ~ (?i)retr|attempt         # regex search
  - depth >= 2                      # numeric: > >= < <=
  - structure in heapq, deque       # one of a list
  - broad = true                    # equality (case-insensitive); also !=
priority: 95                        # higher is preferred when the plan is built
dimension: decision_rationale       # one of the five rubric dimensions
---
# Human-readable title

## Question
Exactly one question mark. {placeholders} are fact fields, e.g. {name} {old} {new}
{file} {line} {function} {commit_short} {commit_message}.

## Follow-up
Optional; exactly one question mark.

## Good answer mentions
- notes for graders, never shown to the student
```

Dimensions: `decision_rationale`, `code_understanding`, `debugging_failure_handling`,
`consistency_across_rounds`, `communication_under_follow_up`.

If several facts match, one is chosen in code with a seeded RNG (seed = submission id), never by
the model. A rule that matches nothing is reported **not triggered**, which often means the
student did not implement that part. That is useful to know, not an error.

Fact kinds and their fields are listed at the top of `facts.py`.
`tests/test_kb_rules.py` checks that every rule parses and fires on a fixture.
