"""Stage definitions 0-7: thin wrappers that adapt each module to the runner.

Each stage reads only the saved artifacts it requires, so it can be re-run on its own.
    0 ingest       stage0_submission.json
    1 facts        stage1_facts.json
    (1d delta      stage1d_delta.json, round 2+, reserved: not built in this hackathon)
    2 rule_match   stage2_rule_matches.json
    3 model        stage3_model_raw.json      (raw model response, untouched)
    4 verify       stage4_verified.json
    5 plan         stage5_plan.json
    6 interview    transcript.json            ({conversation_id, turns} + meta)
    7 grade        report.json (+ stage7_grades_pass1/2.json, report.md)
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import analyse
from db_adapter import load_submission
from examiner import Examiner
from facts import extract_facts
from grade import grade as grade_transcript, write_outputs
from kb_match import kb_hash, load_rules, match_rules
from llm import get_model
from pipeline import RunContext, Stage, StageResult
from plan import build_plan

DEFAULT_KB = ["kb/generic", "kb/task_scheduler"]


def make_context_options(db: Optional[str] = None, kb_dirs: Optional[List[str]] = None,
                         use_openai: bool = False, client: Any = None, transport: Any = None,
                         max_questions: int = 5) -> Dict[str, Any]:
    model, reason = get_model(use_openai, client=client)
    return {"db": db, "kb_dirs": kb_dirs or DEFAULT_KB, "model": model, "model_reason": reason,
            "transport": transport, "max_questions": max_questions}


def files_of(stage0: Dict[str, Any]) -> Dict[str, str]:
    return {f["path"]: f["content"] for f in stage0["files"]}


def read_spec(kb_dirs: List[str]) -> str:
    return "\n\n".join(p.read_text(encoding="utf-8") for d in kb_dirs for p in [Path(d) / "spec.md"] if p.exists())


# --------------------------------------------------------------------------- stages

def s0_ingest(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    sub = load_submission(ctx.submission_id, ctx.options.get("db"))
    files = [{"path": p, "sha256": hashlib.sha256(c.encode("utf-8")).hexdigest(),
              "lines": len(c.splitlines()), "content": c} for p, c in sorted(sub["files"].items())]
    commits = [{**c, "short": c["sha"][:7]} for c in sub["commits"]]
    data = {"submission_id": sub["submission_id"], "assignment": sub["assignment"], "files": files, "commits": commits}
    return StageResult(data, count_in=0, count_out=len(files),
                       summary=f"{len(files)} files, {len(commits)} commits")


def s1_facts(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    s0 = inputs["0"]
    result = extract_facts({"files": files_of(s0), "commits": s0["commits"]})
    kinds: Dict[str, int] = {}
    for f in result["facts"]:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    result["counts_by_kind"] = kinds
    err = f", {len(result['parse_errors'])} files failed to parse" if result["parse_errors"] else ""
    return StageResult(result, count_in=len(s0["files"]), count_out=len(result["facts"]),
                       summary=f"{len(result['facts'])} facts from {result['python_files']} Python files{err}")


def s2_rule_match(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    kb_dirs = ctx.options["kb_dirs"]
    rules = load_rules(kb_dirs)
    matches = match_rules(rules, inputs["1"]["facts"], seed=ctx.seed)
    n = sum(m["triggered"] for m in matches)
    data = {"kb_dirs": kb_dirs, "kb_hash": kb_hash(kb_dirs), "seed": ctx.seed, "matches": matches}
    return StageResult(data, count_in=len(rules), count_out=n, summary=f"{n} of {len(rules)} rules triggered")


def s3_model(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    s0, facts, matches = inputs["0"], inputs["1"]["facts"], inputs["2"]["matches"]
    rule_qs = [m for m in matches if m["triggered"]]
    raw = analyse.propose(ctx.options.get("model"), ctx.options.get("model_reason", ""), files_of(s0),
                          s0["commits"], facts, rule_qs, read_spec(ctx.options["kb_dirs"]))
    n = len((raw.get("response") or {}).get("proposals", []))
    summary = (f"{n} model proposals" if raw["status"] == "ok"
               else f"{raw['status']}: {raw['reason']}; continuing rules-only")
    return StageResult(raw, count_in=len(facts), count_out=n, summary=summary, model=raw.get("model"))


def s4_verify(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    s0 = inputs["0"]
    v = analyse.verify(inputs["3"], files_of(s0), s0["commits"], inputs["1"]["facts"], inputs["2"]["matches"])
    if v["status"] != "ok":
        summary = "nothing to verify (rules-only)"
    else:
        reasons = sorted({r["reasons"][0].split(":")[0] for r in v["results"] if not r["accepted"]})
        summary = f"{v['accepted']} accepted, {v['rejected']} rejected" + (f" ({', '.join(reasons)})" if reasons else "")
    return StageResult(v, count_in=len(v["results"]), count_out=v["accepted"], summary=summary)


def s5_plan(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    plan = build_plan(inputs["2"]["matches"], inputs["4"], inputs["1"]["facts"], seed=ctx.seed,
                      round_no=ctx.round_no, max_questions=ctx.options.get("max_questions", 5))
    src = [q["source"]["type"] for q in plan["questions"]]
    candidates = sum(m["triggered"] for m in inputs["2"]["matches"]) + inputs["4"].get("accepted", 0)
    return StageResult(plan, count_in=candidates, count_out=len(plan["questions"]),
                       summary=f"{len(plan['questions'])} questions selected ({src.count('rule')} rule, "
                               f"{src.count('model')} model); mode: {plan['mode']}")


def s6_interview(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    transport = ctx.options.get("transport")
    if transport is None:
        raise RuntimeError("stage 6 needs a transport (run interview.py --text, or pass --answers FILE)")
    model = ctx.options.get("model")
    conv = f"sub{ctx.submission_id}-round{ctx.round_no}-{hashlib.sha256(repr(inputs['5']).encode()).hexdigest()[:8]}"
    t = Examiner(inputs["5"], transport, phraser=model, conversation_id=conv).run()
    st = t["stats"]
    student = sum(1 for x in t["turns"] if x["speaker"] == "student")
    return StageResult(t, count_in=len(inputs["5"]["questions"]), count_out=len(t["turns"]),
                       summary=f"{len(t['turns'])} turns ({student} student); "
                               f"{st['multi_question_rejections']} multi-question replies rejected; "
                               f"{st['repeats']} repeats" + ("; ENDED EARLY" if st["ended_early"] else ""),
                       model=model.model if model and st["model_follow_ups"] else None)


def s7_grade(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
    plan, transcript = inputs["5"], inputs["6"]
    results = grade_transcript(transcript, plan, ctx.options.get("model"), ctx.options.get("model_reason", ""))
    write_outputs(ctx.run_dir, transcript, plan, results, submission_id=ctx.submission_id, round_no=ctx.round_no)
    report = results[2]
    flag = "NEEDS HUMAN REVIEW" if report["needs_human_review"] else "no review flags"
    scored = sum(1 for d in report["dimensions"] if d["score"] is not None)
    return StageResult(report, count_in=len(report["dimensions"]), count_out=scored,
                       summary=f"draft total {report['total']}/{report['max_total']}; {flag}",
                       model=report["grader"] if report["grader"].startswith("openai:") else None)


def build_stages() -> List[Stage]:
    return [
        Stage("0", "ingest", "stage0_submission.json", s0_ingest),
        Stage("1", "facts", "stage1_facts.json", s1_facts, requires=["0"]),
        # Round 2+: Stage("1d", "delta", "stage1d_delta.json", s1d_delta, requires=["1"], min_round=2)
        # compares with ctx.previous_round_dir (snapshot, facts, and the stated plan in transcript.json).
        Stage("2", "rule_match", "stage2_rule_matches.json", s2_rule_match, requires=["1"]),
        Stage("3", "model", "stage3_model_raw.json", s3_model, requires=["0", "1", "2"]),
        Stage("4", "verify", "stage4_verified.json", s4_verify, requires=["0", "1", "2", "3"]),
        Stage("5", "plan", "stage5_plan.json", s5_plan, requires=["1", "2", "4"]),
        Stage("6", "interview", "transcript.json", s6_interview, requires=["5"], flat=True),
        Stage("7", "grade", "report.json", s7_grade, requires=["5", "6"]),
    ]
