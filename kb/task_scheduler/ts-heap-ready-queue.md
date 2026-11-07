---
id: ts-heap-ready-queue
fact: data_structure
where:
  - structure = heapq
priority: 85
dimension: decision_rationale
---
# Heap for the ready queue

## Question
In `{function}` ({file}:{line}) you use a heap to pick the next job. Why a heap rather than keeping a sorted list?

## Follow-up
Your heap entries include more than the priority; what problem does the extra field solve?

## Good answer mentions
- O(log n) push/pop versus re-sorting or O(n) insertion
- only the minimum is needed at each step
- tie-breaking so equal priorities keep a stable order and dicts are never compared
