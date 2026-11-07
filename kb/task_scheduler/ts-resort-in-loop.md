---
id: ts-resort-in-loop
fact: data_structure
where:
  - structure in sort_in_loop, list_pop_front
priority: 80
dimension: code_understanding
---
# Queue re-sorted or popped from the front inside the loop

## Question
In `{function}` ({file}:{line}) the job list is handled with {usage} inside the main loop. What does that cost as the number of jobs grows?

## Follow-up
Which data structure would remove that cost?

## Good answer mentions
- sorting each iteration is O(n log n) per step, so roughly O(n^2 log n) overall
- list.pop(0) is O(n) because elements shift
- a heap (heapq) or deque as the alternative
