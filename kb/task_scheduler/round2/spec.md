# Assignment: Batch job scheduler (round 2, extension)

*Synthetic assignment for the CodeViva demo. Not a real course.*

Extend your round-1 scheduler. Keep your git history: round 2 continues it.

1. Run independent jobs in parallel on a pool of workers. **You choose** how many.
2. Give up on a job (or a whole run) that takes too long. **You choose** the timeout and what
   happens to a job that is still running when it expires.
3. Keep priorities, dependencies and your failure policy working with parallel workers.
4. Carry out, or explicitly revise, the plan you described at the end of round 1.

You will be asked how your round-1 decisions held up, what you changed and why, and how your
plan compared with what you built. Changing a decision with a good reason is fine and is not
penalised.

Learning outcomes assessed:
- LO2 design a failure-handling policy and explain its trade-offs
- LO3 reason about the behaviour and cost of your own code
- LO5 reason about shared state when work runs concurrently
- LO6 plan an iteration and evaluate the plan against the outcome
