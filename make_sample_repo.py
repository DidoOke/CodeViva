"""Synthetic student submissions for the task_scheduler assignment (no real student data).

Submission 1: a reasonable project with a realistic history (heap added, crash fixed, retry
limit lowered with backoff, dependency bug fixed, tests added).
Submission 2: a thin project with two commits, a broad `except: pass` and a list re-sorted
every loop, so different rules trigger and some report "not triggered".

    python make_sample_repo.py --git out/   # also write real git repos for inspection
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

ASSIGNMENT = "task_scheduler"


def render_scheduler(*, heap: bool, safe_load: bool, backoff: bool, max_retries: int, skip: bool) -> str:
    """One student's scheduler.py at different points in their history."""
    imports = ["import json", "import logging", "import random", "import time"]
    if heap:
        imports.insert(0, "import heapq")
    imports.append("from collections import defaultdict")

    consts = [f"MAX_RETRIES = {max_retries}"]
    if backoff:
        consts += ["BACKOFF_BASE = 0.5", "BACKOFF_CAP = 8.0"]
    consts.append("FAILURE_RATE = 0.2")

    if safe_load:
        load_body = '''    jobs = {}
    for item in raw:
        try:
            job_id = item["id"]
        except KeyError:
            log.warning("skipping job without id: %r", item)
            continue
        jobs[job_id] = {
            "id": job_id,
            "priority": int(item.get("priority", 5)),
            "deps": list(item.get("deps", [])),
        }
    return jobs'''
    else:
        load_body = '''    jobs = {}
    for item in raw:
        jobs[item["id"]] = {"id": item["id"], "priority": item["priority"], "deps": item["deps"]}
    return jobs'''

    backoff_fn = ""
    if backoff:
        backoff_fn = '''


def backoff_delay(attempt):
    return min(BACKOFF_CAP, BACKOFF_BASE * (2 ** attempt))'''

    if heap:
        push_ready = "heapq.heappush(ready, (jobs[{v}][\"priority\"], seq, {v}))\n{i}seq += 1"
        pop_ready = "_, _, job_id = heapq.heappop(ready)"
    else:
        push_ready = "ready.append({v})\n{i}ready.sort(key=lambda j: jobs[j][\"priority\"])"
        pop_ready = "job_id = ready.pop(0)"

    retry_failed = (
        "                if attempt == MAX_RETRIES:\n"
        "                    results[job_id] = \"failed\"\n"
        + ("                else:\n                    sleep(backoff_delay(attempt))\n" if backoff else "")
    )
    on_fail = (
        "        if results[job_id] == \"failed\":\n"
        + ("            skip_dependents(job_id, dependents, results)\n" if skip else "")
        + "            continue\n"
    )
    skip_fn = ""
    if skip:
        skip_fn = '''


def skip_dependents(job_id, dependents, results):
    stack = list(dependents[job_id])
    while stack:
        child = stack.pop()
        if child in results:
            continue
        results[child] = "skipped"
        stack.extend(dependents[child])'''

    seq_init = "    seq = 0\n" if heap else ""
    return f'''"""Batch job scheduler with priorities, dependencies and retries."""
{chr(10).join(imports)}

{chr(10).join(consts)}

log = logging.getLogger("scheduler")


class TransientJobError(Exception):
    """A failure worth retrying (timeout, flaky dependency)."""


def load_jobs(path):
    with open(path) as fh:
        raw = json.load(fh)
{load_body}


def run_job(job, rng):
    if rng.random() < FAILURE_RATE:
        raise TransientJobError(f"job {{job['id']}} timed out")
    return f"ok:{{job['id']}}"{backoff_fn}


def schedule(jobs, rng=None, sleep=time.sleep):
    rng = rng or random.Random(0)
    dependents = defaultdict(list)
    waiting = {{}}
    for job in jobs.values():
        waiting[job["id"]] = len(job["deps"])
        for dep in job["deps"]:
            dependents[dep].append(job["id"])

    ready = []
{seq_init}    for job_id, count in waiting.items():
        if count == 0:
            {push_ready.format(v="job_id", i="            ")}

    results = {{}}
    while ready:
        {pop_ready}
        job = jobs[job_id]
        for attempt in range(MAX_RETRIES + 1):
            try:
                results[job_id] = run_job(job, rng)
                break
            except TransientJobError as exc:
                log.info("attempt %d failed: %s", attempt + 1, exc)
{retry_failed}{on_fail}        for child in dependents[job_id]:
            if child in results:
                continue
            waiting[child] -= 1
            if waiting[child] == 0:
                {push_ready.format(v="child", i="                ")}
    return results{skip_fn}


def main(path):
    results = schedule(load_jobs(path))
    for status in ("ok", "failed", "skipped"):
        names = sorted(j for j, r in results.items() if r.split(":")[0] == status)
        print(f"{{status}}: {{len(names)}} {{names}}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1])
'''


README_1 = """# Job scheduler

Runs jobs from a JSON file with priorities, dependencies and retries.

    python scheduler.py jobs.json
"""

JOBS_JSON = """[
  {"id": "fetch", "priority": 1},
  {"id": "parse", "priority": 2, "deps": ["fetch"]},
  {"id": "report", "priority": 3, "deps": ["parse"]},
  {"id": "cleanup", "priority": 9}
]
"""

TESTS_1 = '''import random

from scheduler import TransientJobError, schedule
import scheduler


def test_gives_up_after_max_retries(monkeypatch):
    calls = []

    def always_fail(job, rng):
        calls.append(job["id"])
        raise TransientJobError("boom")

    monkeypatch.setattr(scheduler, "run_job", always_fail)
    jobs = {"a": {"id": "a", "priority": 1, "deps": []}}
    results = schedule(jobs, rng=random.Random(1), sleep=lambda s: None)
    assert results["a"] == "failed"
    assert len(calls) == scheduler.MAX_RETRIES + 1


def test_dependents_of_failed_job_are_skipped(monkeypatch):
    def fail_a(job, rng):
        if job["id"] == "a":
            raise TransientJobError("boom")
        return "ok"

    monkeypatch.setattr(scheduler, "run_job", fail_a)
    jobs = {
        "a": {"id": "a", "priority": 1, "deps": []},
        "b": {"id": "b", "priority": 1, "deps": ["a"]},
    }
    results = schedule(jobs, rng=random.Random(1), sleep=lambda s: None)
    assert results["b"] == "skipped"
'''

SCHEDULER_2_V1 = '''import random

MAX_RETRIES = 10


def load(path):
    import json
    return json.load(open(path))


def run(job):
    if random.random() < 0.3:
        raise RuntimeError("failed")
    return "ok"


def main(path):
    jobs = load(path)
    done = {}
    todo = list(jobs)
    while todo:
        todo.sort(key=lambda j: j.get("priority", 5))
        job = todo.pop(0)
        for i in range(MAX_RETRIES):
            try:
                done[job["id"]] = run(job)
                break
            except:
                pass
    print(done)
'''

SCHEDULER_2_V2 = SCHEDULER_2_V1.replace('    print(done)\n', '''    print("done:", len(done))
    print(done)
''')


def _sha(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8")).hexdigest()


def _history(submission_id: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Turn [{message, files}] into the load_submission() shape with deterministic fake SHAs."""
    files: Dict[str, Optional[str]] = {}
    commits = []
    parent = ""
    for i, step in enumerate(steps):
        files.update(step["files"])
        sha = _sha(submission_id, parent, step["message"], *sorted(f"{k}={v}" for k, v in step["files"].items()))
        commits.append({
            "sha": sha,
            "message": step["message"],
            "authored_at": f"2026-10-{1 + i * 2:02d}T14:00:00Z",
            "files": dict(step["files"]),
        })
        parent = sha
    final = {k: v for k, v in files.items() if v is not None}
    return {"submission_id": submission_id, "assignment": ASSIGNMENT, "label": f"synthetic-{submission_id}",
            "files": final, "commits": commits}


def submission_1() -> Dict[str, Any]:
    v = dict(heap=False, safe_load=False, backoff=False, max_retries=5, skip=False)
    steps = [
        {"message": "initial scheduler: run jobs by priority with retries",
         "files": {"scheduler.py": render_scheduler(**v), "README.md": README_1, "jobs.json": JOBS_JSON}},
    ]
    v["heap"] = True
    steps.append({"message": "use a heap for the ready queue instead of re-sorting a list",
                  "files": {"scheduler.py": render_scheduler(**v)}})
    v["safe_load"] = True
    steps.append({"message": "fix crash when a job has no 'deps' or 'priority' key",
                  "files": {"scheduler.py": render_scheduler(**v)}})
    v.update(max_retries=3, backoff=True)
    steps.append({"message": "reduce MAX_RETRIES from 5 to 3 and add capped exponential backoff",
                  "files": {"scheduler.py": render_scheduler(**v)}})
    v["skip"] = True
    steps.append({"message": "fix: dependents of a permanently failed job were never resolved",
                  "files": {"scheduler.py": render_scheduler(**v)}})
    steps.append({"message": "add tests for retry limit and skipped dependents",
                  "files": {"tests/test_scheduler.py": TESTS_1}})
    return _history("1", steps)


def submission_2() -> Dict[str, Any]:
    return _history("2", [
        {"message": "initial commit", "files": {"scheduler.py": SCHEDULER_2_V1}},
        {"message": "final version", "files": {"scheduler.py": SCHEDULER_2_V2}},
    ])


def all_submissions() -> List[Dict[str, Any]]:
    return [submission_1(), submission_2()]


def write_git_repo(submission: Dict[str, Any], dest: Path) -> None:
    """Materialise a submission as a real git repo (for humans to inspect; never executed)."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    for c in submission["commits"]:
        for path, content in c["files"].items():
            target = dest / path
            if content is None:
                target.unlink(missing_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        env = {"GIT_AUTHOR_NAME": "Student", "GIT_AUTHOR_EMAIL": "student@example.invalid",
               "GIT_COMMITTER_NAME": "Student", "GIT_COMMITTER_EMAIL": "student@example.invalid",
               "GIT_AUTHOR_DATE": c["authored_at"], "GIT_COMMITTER_DATE": c["authored_at"], "PATH": "/usr/bin:/bin"}
        subprocess.run(["git", "-C", str(dest), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(dest), "commit", "-q", "-m", c["message"]], check=True, env=env)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--git", type=Path, help="write each submission as a git repo under this dir")
    args = ap.parse_args()
    for sub in all_submissions():
        print(f"submission {sub['submission_id']}: {len(sub['files'])} files, {len(sub['commits'])} commits")
        if args.git:
            write_git_repo(sub, args.git / f"submission{sub['submission_id']}")
