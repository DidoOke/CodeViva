---
id: r-plan-no-evidence
fact: plan_item
where:
  - status = no_evidence
priority: 96
dimension: consistency_across_rounds
---
# Stated plan with no matching change found

## Question
Last round you said: "{claim}". I could not find that change in this round's code or commits. What happened to that part of your plan?

## Follow-up
If you made the change in a different way, where in the code should I look?

## Good answer mentions
- an honest account: dropped, postponed, or done differently, with a reason
- reprioritising because of new requirements is a legitimate decision and is not penalised
- if done differently, points to real code (the matcher is keyword-based and can miss reworded changes)
- for graders: "no evidence" is a prompt to ask, not a finding against the student
