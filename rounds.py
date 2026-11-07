"""Multi-round assessment: run round 2+ for a student, comparing with their previous round.

    # round 1 as usual (plan, interview, grade):
    python interview.py --db demo.db --submission 1 --answers demo_answers/submission1.txt --grade
    # round 2 against the student's extended code (DB row 11), plan only:
    python rounds.py --db demo.db --submission 1 --round 2 --code-from 11
    # ... and the interview + grading:
    python rounds.py --db demo.db --submission 1 --round 2 --code-from 11 --answers demo_answers/submission1_round2.txt --grade

Artifacts go to runs/<submission>/round<N>/ next to round 1, keyed by the round-1 submission id
(which stays the random seed). In round 2+ this module adapts the standard stages without
changing them:
  - stage 0 loads the code from --code-from (the student's latest upload)
  - stage 1d (delta.py) runs after stage 1 and compares with runs/<submission>/round<N-1>/
  - stages 2-5 see stage 1d's facts (new since last round + delta facts) instead of all facts,
    so last round's questions are not asked again
  - the knowledge base adds kb/rounds and the assignment's round<N>/ directory
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from artifacts import round_dir
from delta import s1d_delta
from pipeline import RunContext, Stage, StageError, StageResult, run_pipeline

ROUNDS_KB = "kb/rounds"
USES_FACTS = {"2", "3", "4", "5"}


def kb_for_round(base_kb: List[str], round_no: int) -> List[str]:
    """Round 1: base_kb. Round N: base_kb + kb/rounds + each assignment dir's round<N>/ if present."""
    if round_no <= 1:
        return list(base_kb)
    extra = [ROUNDS_KB] + [str(Path(d) / f"round{round_no}") for d in base_kb
                           if (Path(d) / f"round{round_no}").is_dir()]
    return list(base_kb) + [d for d in extra if d not in base_kb]


def _with_round_facts(fn):
    def wrapped(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
        inputs = dict(inputs)
        inputs["1"] = {**inputs["1"], "facts": inputs.pop("1d")["facts"]}
        return fn(ctx, inputs)
    return wrapped


def _ingest_from(fn, code_from: str):
    def wrapped(ctx: RunContext, inputs: Dict[str, Any]) -> StageResult:
        result = fn(dataclasses.replace(ctx, submission_id=code_from), inputs)
        result.data = {**result.data, "code_from": code_from}
        result.summary += f" (code from submission {code_from})"
        return result
    return wrapped


def round_stages(base: List[Stage], round_no: int, code_from: Optional[str] = None) -> List[Stage]:
    """The standard stage list adapted for round_no. Round 1 (and no code_from) is unchanged."""
    if round_no <= 1:
        return list(base)
    out: List[Stage] = []
    for s in base:
        if s.id == "0" and code_from:
            s = dataclasses.replace(s, fn=_ingest_from(s.fn, code_from))
        if s.id in USES_FACTS:
            s = dataclasses.replace(s, fn=_with_round_facts(s.fn), requires=list(s.requires) + ["1d"])
        out.append(s)
        if s.id == "1":
            out.append(Stage("1d", "delta", "stage1d_delta.json", s1d_delta, requires=["0", "1"], min_round=2))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    from examiner import ScriptedTransport, TextTransport
    from interview import read_answers
    from stages import DEFAULT_KB, build_stages, make_context_options

    ap = argparse.ArgumentParser(description="Run round 2+ of a multi-round assessment.")
    ap.add_argument("--db", help="database URL or SQLite path (default: $DATABASE_URL)")
    ap.add_argument("--submission", required=True, help="the student's round-1 submission id (run key and seed)")
    ap.add_argument("--round", type=int, required=True, dest="round_no")
    ap.add_argument("--code-from", help="DB submission id holding this round's code (default: --submission)")
    ap.add_argument("--kb", action="append", help="base knowledge base dir (repeatable; round dirs are added)")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--use-llm", "--use-openai", dest="use_llm", action="store_true")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="interactive text interview")
    mode.add_argument("--answers", type=Path, help="scripted answers file")
    ap.add_argument("--grade", action="store_true", help="also grade (needs --text or --answers)")
    ap.add_argument("--from-stage")
    ap.add_argument("--max-questions", type=int, default=5)
    args = ap.parse_args(argv)
    if args.round_no < 2:
        print("error: use pipeline.py / interview.py for round 1", file=sys.stderr)
        return 2

    transport = None
    if args.answers:
        transport = ScriptedTransport(read_answers(args.answers), echo=print)
    elif args.text:
        transport = TextTransport()
    stop = "7" if (transport and args.grade) else "6" if transport else "5"

    kb = kb_for_round(args.kb or DEFAULT_KB, args.round_no)
    options = make_context_options(db=args.db, kb_dirs=kb, use_openai=args.use_llm, transport=transport,
                                   max_questions=args.max_questions)
    runs_root = Path(args.runs)
    ctx = RunContext(submission_id=args.submission, round_no=args.round_no,
                     run_dir=round_dir(runs_root, args.submission, args.round_no), runs_root=runs_root,
                     seed=str(args.submission), options=options)
    try:
        arts = run_pipeline(round_stages(build_stages(), args.round_no, args.code_from), ctx,
                            from_stage=args.from_stage, stop_after=stop)
    except (StageError, ValueError, LookupError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print("\n" + (ctx.run_dir / "stages.md").read_text(encoding="utf-8"))
    d = arts["1d"]["data"]
    print(f"stated plan ({d['stated_plan']['status']}, claims by {d['stated_plan']['claim_mode']}):")
    for item in d["plan_items"]:
        where = ", ".join(f"{e.get('file') or ''}{':' + str(e['line']) if e.get('line') else ''} "
                          f"{e.get('commit_short', '')}".strip() for e in item["evidence"])
        print(f"  [{item['status']}] \"{item['claim']}\"" + (f"  <- {where}" if where else ""))
    print("\nround plan:")
    for q in arts["5"]["data"]["questions"]:
        print(f"  {q['id']} [{q['dimension']}] {q['text']}")
    print(f"\nartifacts: {ctx.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
