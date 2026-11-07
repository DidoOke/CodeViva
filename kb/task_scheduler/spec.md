# Assignment: Batch job scheduler (round 1, MVP)

*Synthetic assignment for the CodeViva demo. Not a real course.*

Write a Python program that runs a batch of jobs described in a JSON file. Each job has an
`id`, an optional `priority` (lower number runs first) and an optional list of `deps`: ids of
jobs that must succeed before it may start. Running a job is simulated and can fail
transiently.

Your scheduler must:

1. Run every runnable job, respecting priorities and dependencies.
2. Retry transient failures with a policy **you choose** (how many attempts, how long to wait
   between them) and eventually give up.
3. Decide what happens to jobs whose dependencies failed permanently.
4. Cope with malformed input without crashing.
5. Print a summary: succeeded, failed, skipped.

There is no single right implementation. You will be asked to explain your choices, for
example your retry limit, the data structure you use to pick the next job, and how you
handle failures. Commit regularly: your commit history is part of the evidence.

Learning outcomes assessed:
- LO1 choose and justify a data structure for a scheduling problem
- LO2 design a failure-handling policy and explain its trade-offs
- LO3 reason about the behaviour and cost of your own code
- LO4 find, explain and fix defects
