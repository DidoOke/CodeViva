"""Round-2 versions of the synthetic submissions (no real student data).

Round 2 of the task_scheduler assignment (kb/task_scheduler/round2/spec.md) adds a worker pool
and per-job timeouts. Each round-2 submission continues the student's round-1 git history.

Submission 1 -> 11: follows the plan stated in round 1 (detect dependency cycles, test it), then
  adds a thread pool, raises MAX_RETRIES 3 -> 4 and fixes a race found along the way.
Submission 2 -> 12: said "make it faster" / "probably test it"; adds threads, replaces
  `.pop(0)` but keeps re-sorting every loop and `except: pass`, lowers MAX_RETRIES, no tests.

    python make_round2_samples.py --db demo.db     # add submissions 11 and 12 to the demo DB

Run round 2 for a student against their new code:
    python pipeline.py --db demo.db --submission 1 --round 2 --code-from 11
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from db_adapter import insert_submission
from make_sample_repo import _sha, submission_1, submission_2

ROUND2_ID = {"1": "11", "2": "12"}  # round-1 submission id -> DB row holding its round-2 code

# What each student said in round 1 when asked for their plan (main answer, follow-up answer).
# Submission 1 matches demo_answers/submission1.txt; used by tests and the demo.
ROUND1_PLAN_ANSWERS = {
    "1": ("I would detect dependency cycles, because right now two jobs that depend on each other are never "
          "run and never reported. I would add a check before scheduling that finds any job that never "
          "becomes ready.",
          "I would add a test with a cycle and check that both jobs come back as skipped or as an explicit error."),
    "2": ("Make it faster.", "Probably test it."),
}


# --------------------------------------------------------------------------- submission 1 -> 11

CYCLE_FN = '''

def find_blocked(jobs, dependents):
    """Jobs that can never become ready: part of a dependency cycle, or waiting on one."""
    indegree = {j: len(jobs[j]["deps"]) for j in jobs}
    queue = [j for j, n in indegree.items() if n == 0]
    seen = set()
    while queue:
        job_id = queue.pop()
        seen.add(job_id)
        for child in dependents[job_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return sorted(set(jobs) - seen)
'''

CYCLE_TEST = '''

def test_dependency_cycle_is_reported_as_blocked():
    jobs = {
        "a": {"id": "a", "priority": 1, "deps": ["b"]},
        "b": {"id": "b", "priority": 1, "deps": ["a"]},
        "c": {"id": "c", "priority": 1, "deps": []},
    }
    results = schedule(jobs, rng=random.Random(1), sleep=lambda s: None)
    assert results["a"] == results["b"] == "blocked"
    assert results["c"].startswith("ok")
'''

POOL_SCHEDULE = '''def schedule(jobs, rng=None, sleep=time.sleep, workers=WORKERS):
    rng = rng or random.Random(0)
    dependents = defaultdict(list)
    waiting = {}
    for job in jobs.values():
        waiting[job["id"]] = len(job["deps"])
        for dep in job["deps"]:
            dependents[dep].append(job["id"])

    results = {}
    for job_id in find_blocked(jobs, dependents):
        results[job_id] = "blocked"

    lock = threading.Lock()
    ready = []
    seq = 0
    for job_id, count in waiting.items():
        if count == 0:
            heapq.heappush(ready, (jobs[job_id]["priority"], seq, job_id))
            seq += 1

    def attempt_job(job_id):
        job = jobs[job_id]
        for attempt in range(MAX_RETRIES + 1):
            try:
                return run_job(job, rng)
            except TransientJobError as exc:
                log.info("attempt %d failed: %s", attempt + 1, exc)
                if attempt < MAX_RETRIES:
                    sleep(backoff_delay(attempt))
        return "failed"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        running = {}
        while ready or running:
            while ready and len(running) < workers:
                _, _, job_id = heapq.heappop(ready)
                running[pool.submit(attempt_job, job_id)] = job_id
            done, _ = wait(running, timeout=JOB_TIMEOUT, return_when=FIRST_COMPLETED)
            if not done:
                for future, job_id in running.items():
                    future.cancel()
                    results[job_id] = "timed_out"
                break
            for future in done:
                job_id = running.pop(future)
                with lock:
                    results[job_id] = future.result()
                    if results[job_id] == "failed":
                        skip_dependents(job_id, dependents, results)
                        continue
                    for child in dependents[job_id]:
                        if child in results:
                            continue
                        waiting[child] -= 1
                        if waiting[child] == 0:
                            heapq.heappush(ready, (jobs[child]["priority"], seq, child))
                            seq += 1
    return results
'''


def _scheduler_1_steps(r1: str) -> List[Dict[str, Any]]:
    """Round-2 commits for submission 1, each with the full content of the files it touched."""
    v_cycle = r1.replace("\n\ndef skip_dependents", CYCLE_FN + "\n\ndef skip_dependents")
    v_cycle = v_cycle.replace(
        "    ready = []\n",
        "    results = {}\n    for job_id in find_blocked(jobs, dependents):\n"
        "        results[job_id] = \"blocked\"  # never becomes ready: cycle\n\n    ready = []\n", 1)
    v_cycle = v_cycle.replace("    results = {}\n    while ready:", "    while ready:")
    v_cycle = v_cycle.replace('for status in ("ok", "failed", "skipped")', 'for status in ("ok", "failed", "skipped", "blocked")')

    start = v_cycle.index("def schedule(")
    end = v_cycle.index("\n\ndef find_blocked")
    v_pool_racy = v_cycle[:start] + POOL_SCHEDULE.replace(
        "                with lock:\n                    results", "                if True:\n                    results") \
        + "\n\n" + v_cycle[end:].lstrip("\n")
    v_pool_racy = v_pool_racy.replace("import random\n", "import random\nimport threading\n")
    v_pool_racy = v_pool_racy.replace("import time\n", "import time\nfrom concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait\n")
    v_pool_racy = v_pool_racy.replace("FAILURE_RATE = 0.2\n", "FAILURE_RATE = 0.2\nWORKERS = 4\nJOB_TIMEOUT = 30.0\n")
    v_retry = v_pool_racy.replace("MAX_RETRIES = 3\n", "MAX_RETRIES = 4\n")
    v_fixed = v_retry.replace("                if True:\n                    results", "                with lock:\n                    results")

    tests = submission_1()["files"]["tests/test_scheduler.py"]
    readme = submission_1()["files"]["README.md"] + (
        "\nRound 2: jobs run on a pool of `WORKERS` threads; a run stops if no job finishes within "
        "`JOB_TIMEOUT` seconds.\n")
    return [
        {"message": "detect dependency cycles before scheduling and report blocked jobs",
         "files": {"scheduler.py": v_cycle}},
        {"message": "test that a dependency cycle is reported as blocked",
         "files": {"tests/test_scheduler.py": tests + CYCLE_TEST}},
        {"message": "run jobs on a thread pool with a per-run timeout (round 2 spec)",
         "files": {"scheduler.py": v_pool_racy, "README.md": readme}},
        {"message": "raise MAX_RETRIES from 3 to 4: backoff no longer blocks the whole run",
         "files": {"scheduler.py": v_retry}},
        {"message": "fix: two workers finishing together could release a dependent twice",
         "files": {"scheduler.py": v_fixed}},
    ]


# --------------------------------------------------------------------------- submission 2 -> 12

SCHEDULER_2_R2 = '''import random
import threading

MAX_RETRIES = 5
MAX_WORKERS = 8


def load(path):
    import json
    return json.load(open(path))


def run(job):
    if random.random() < 0.3:
        raise RuntimeError("failed")
    return "ok"


def run_with_retries(job, done):
    for i in range(MAX_RETRIES):
        try:
            done[job["id"]] = run(job)
            break
        except:
            pass


def main(path):
    jobs = load(path)
    done = {}
    todo = list(jobs)
    threads = []
    while todo:
        todo.sort(key=lambda j: j.get("priority", 5), reverse=True)
        job = todo.pop()
        t = threading.Thread(target=run_with_retries, args=(job, done))
        t.start()
        threads.append(t)
        if len(threads) >= MAX_WORKERS:
            threads.pop(0).join()
    for t in threads:
        t.join()
    print("done:", len(done))
    print(done)
'''


def _scheduler_2_steps() -> List[Dict[str, Any]]:
    return [{"message": "threads", "files": {"scheduler.py": SCHEDULER_2_R2.replace("MAX_RETRIES = 5", "MAX_RETRIES = 10")}},
            {"message": "tweak", "files": {"scheduler.py": SCHEDULER_2_R2}}]


# --------------------------------------------------------------------------- assembly

def extend_history(round1: Dict[str, Any], new_id: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Continue round1's commit history with `steps`; same SHA scheme as make_sample_repo."""
    files = dict(round1["files"])
    commits = [dict(c) for c in round1["commits"]]
    parent = commits[-1]["sha"] if commits else ""
    for i, step in enumerate(steps):
        files.update(step["files"])
        sha = _sha(round1["submission_id"], parent, step["message"],
                   *sorted(f"{k}={v}" for k, v in step["files"].items()))
        commits.append({"sha": sha, "message": step["message"], "authored_at": f"2026-11-{1 + i * 2:02d}T14:00:00Z",
                        "files": dict(step["files"])})
        parent = sha
    return {"submission_id": new_id, "assignment": round1["assignment"],
            "label": f"round 2 of submission {round1['submission_id']}",
            "files": {k: v for k, v in files.items() if v is not None}, "commits": commits}


def round2_submission_1() -> Dict[str, Any]:
    r1 = submission_1()
    return extend_history(r1, ROUND2_ID["1"], _scheduler_1_steps(r1["files"]["scheduler.py"]))


def round2_submission_2() -> Dict[str, Any]:
    return extend_history(submission_2(), ROUND2_ID["2"], _scheduler_2_steps())


def round2_submissions() -> List[Dict[str, Any]]:
    return [round2_submission_1(), round2_submission_2()]


def add_to_db(db: Path) -> List[str]:
    """Insert the round-2 rows into an existing demo DB; rows already present are left alone."""
    conn = sqlite3.connect(db)
    added = []
    try:
        for sub in round2_submissions():
            if conn.execute("SELECT 1 FROM submissions WHERE id = ?", (int(sub["submission_id"]),)).fetchone():
                continue
            insert_submission(conn, sub)
            added.append(sub["submission_id"])
    finally:
        conn.close()
    return added


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Add round-2 synthetic submissions to the demo database.")
    ap.add_argument("--db", type=Path, default=Path("demo.db"))
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"error: {args.db} not found; run make_demo_db.py first")
    added = add_to_db(args.db)
    print(f"added submissions {', '.join(added)} to {args.db}" if added else f"round-2 rows already in {args.db}")
