"""Eval harness: run the pipeline per submission x student persona and score examiner + grader behaviour.

    python evalharness.py --db demo.db --submission 1 --submission 2 [--use-llm] [--json out.json]

Personas answer every examiner turn: strong (demo_answers/), vague (generic filler), wrong (confident but off),
silent ("I don't know"). Checks (exit 1 if any fails):
  examiner: <=1 question per turn, no evaluative words, no grading-note leakage, follow-ups reference
            the student's answer or the code (specificity), no more turns than planned.
  grader:   score(strong) > score(vague) >= score(silent); quotes verbatim; strong not flagged below vague.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from artifacts import round_dir
from examiner import EVALUATIVE_RE, ScriptedTransport, count_questions
from interview import read_answers
from pipeline import RunContext, run_pipeline
from stages import DEFAULT_KB, build_stages, make_context_options

VAGUE = ["I just thought it seemed fine and it works well enough for what we needed.",
         "It is basically how it is normally done, and it does the job.",
         "I guess it makes the code cleaner and more efficient overall."]
WRONG = ["I picked it because the language requires that value and it can't be changed at all.",
         "That has no effect on performance, the computer handles it instantly regardless of size.",
         "It was in the tutorial so I copied it, and the tests never touch it."]
SILENT = ["I don't know"]
STOP = set("the a an and or of to in is it that this was what how why you your do did would for with on be as at "
           "if are not but so can i my me we they them from have has had will which there then than".split())


def words(t: str) -> set:
    return {w for w in re.findall(r"[a-z_][a-z_0-9]{2,}", t.lower()) if w not in STOP}


def persona_answers(name: str, demo_file: Optional[Path], n: int = 12) -> List[str]:
    if name == "strong":
        if not (demo_file and demo_file.exists()) or "vague" in demo_file.read_text().splitlines()[0].lower():
            return []  # the demo file is itself a weak sample
        return read_answers(demo_file)
    pool = {"vague": VAGUE, "wrong": WRONG, "silent": SILENT}[name]
    return [pool[i % len(pool)] for i in range(n)]


def run_persona(db, sub, persona, demo_file, kb, model_on, scratch) -> Dict[str, Any]:
    answers = persona_answers(persona, demo_file)
    if not answers:
        return {"persona": persona, "skipped": "no demo answers"}
    transport = ScriptedTransport(answers)
    opts = make_context_options(db=db, kb_dirs=kb, use_openai=model_on, transport=transport)
    ctx = RunContext(submission_id=sub, round_no=1, run_dir=round_dir(scratch / persona, sub, 1),
                     runs_root=scratch / persona, seed=str(sub), options=opts)
    arts = run_pipeline(build_stages(), ctx, stop_after="7")
    plan, tr, rep = arts["5"]["data"], arts["6"]["data"], arts["7"]["data"]
    return {"persona": persona, "plan": plan, "turns": tr["turns"], "stats": tr["stats"], "report": rep,
            "total": sum(d["score"] or 0 for d in rep["dimensions"]), "model": opts["model"] is not None}


def check_examiner(r: Dict[str, Any]) -> List[str]:
    fails, plan = [], r["plan"]
    notes = [m.lower() for q in plan["questions"] for m in q.get("good_answer_mentions", [])]
    turns, last_answer = r["turns"], ""
    spec_hits = follow_ups = 0
    for t in turns:
        if t["speaker"] == "student":
            last_answer = t["text"]
            continue
        txt = t["text"]
        if count_questions(txt) > 1:
            fails.append(f"multi-question turn: {txt[:60]}")
        planned = {q["text"] for q in plan["questions"]} | {q.get("follow_up", "") for q in plan["questions"]}
        if EVALUATIVE_RE.search(txt) and t["kind"] not in ("no_feedback", "closing") \
                and not any(x and x in txt for x in planned):
            fails.append(f"evaluative: {txt[:60]}")
        if any(n and n in txt.lower() for n in notes):
            fails.append(f"grading note leaked: {txt[:60]}")
        if t["kind"] == "follow_up":
            follow_ups += 1
            q = next(q for q in plan["questions"] if q["id"] == t["question_id"])
            anchor = words(last_answer) | words(q["text"])
            spec_hits += bool(words(txt) & anchor)
    r["follow_ups"], r["specific_follow_ups"] = follow_ups, spec_hits
    return fails


def check_grader(results: Dict[str, Dict[str, Any]]) -> List[str]:
    fails = []
    for p, r in results.items():
        if "report" not in r:
            continue
        verb = " ".join(t["text"] for t in r["turns"] if t["speaker"] == "student")
        for d in r["report"]["dimensions"]:
            for q in d.get("quotes", []):
                if " ".join(q.split()).lower() not in " ".join(verb.split()).lower():
                    fails.append(f"{p}: non-verbatim quote in {d['dimension']}")
    s, v, si = (results.get(k, {}).get("total") for k in ("strong", "vague", "silent"))
    if s is not None and v is not None and not s > v:
        fails.append(f"grader does not separate strong ({s}) from vague ({v})")
    if v is not None and si is not None and not v >= si:
        fails.append(f"vague ({v}) scored below silent ({si})")
    return fails


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--submission", action="append", required=True)
    ap.add_argument("--kb", action="append")
    ap.add_argument("--use-llm", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    kb = a.kb or DEFAULT_KB
    out, bad = [], 0
    for sub in a.submission:
        scratch = Path(tempfile.mkdtemp(prefix="cveval"))
        demo = Path("demo_answers") / f"submission{sub}.txt"
        res = {p: run_persona(a.db, sub, p, demo, kb, a.use_llm, scratch) for p in ("strong", "vague", "wrong", "silent")}
        fails = []
        for p, r in res.items():
            if "plan" in r:
                fails += [f"{p}: {f}" for f in check_examiner(r)]
        fails += check_grader(res)
        print(f"\n== submission {sub}  (model: {'on' if a.use_llm else 'off'}) ==")
        print(f"{'persona':8} {'score':>6} {'turns':>5} {'follow-ups specific':>20} {'review flag':>12}")
        for p, r in res.items():
            if "report" not in r:
                print(f"{p:8} skipped ({r.get('skipped')})"); continue
            print(f"{p:8} {r['total']:>6} {len(r['turns']):>5} {r['specific_follow_ups']:>10}/{r['follow_ups']:<9} "
                  f"{str(r['report']['needs_human_review']):>12}")
        print("FAIL: " + "; ".join(fails) if fails else "all checks passed")
        bad += len(fails)
        out.append({"submission": sub, "fails": fails, "personas": {p: {k: v for k, v in r.items() if k in
                    ("total", "stats", "follow_ups", "specific_follow_ups")} for p, r in res.items()}})
        shutil.rmtree(scratch, ignore_errors=True)
    if a.json:
        a.json.write_text(json.dumps(out, indent=2))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
