"""Run stages 0-6 for one submission and hold the interview.

    python interview.py --db demo.db --submission 1 --kb kb/generic --kb kb/task_scheduler --use-llm --text
    python interview.py --db demo.db --submission 1 --answers demo_answers/submission1.txt   # scripted demo

Artifacts go to runs/<submission>/round<N>/. plan.json and transcript.json are also copied to
--out (default: current directory) so `python grade.py transcript.json plan.json` works.
With --grade, stage 7 runs straight after the interview.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from artifacts import round_dir
from examiner import ScriptedTransport, TextTransport
from pipeline import RunContext, StageError, run_pipeline
from stages import DEFAULT_KB, build_stages, make_context_options


def read_answers(path: Path) -> List[str]:
    """One answer per paragraph (blank-line separated); lines starting with # are comments."""
    text = "\n".join(l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("#"))
    return [" ".join(p.split()) for p in text.split("\n\n") if p.strip()]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Plan and run a code-grounded oral interview.")
    ap.add_argument("--db", help="database URL or SQLite path (default: $DATABASE_URL)")
    ap.add_argument("--submission", required=True)
    ap.add_argument("--kb", action="append", help="knowledge base dir (repeatable)")
    ap.add_argument("--round", type=int, default=1, dest="round_no")
    ap.add_argument("--runs", default="runs")
    ap.add_argument("--use-llm", "--use-openai", dest="use_openai", action="store_true",
                    help="use the model layer (provider from LLM_PROVIDER / .env)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--text", action="store_true", help="interactive text interview in the terminal")
    mode.add_argument("--answers", type=Path, help="scripted answers file (demo / testing)")
    mode.add_argument("--voice", action="store_true", help="voice interview (not available yet)")
    ap.add_argument("--from-stage", help="re-run from this stage (earlier artifacts load from disk)")
    ap.add_argument("--max-questions", type=int, default=5)
    ap.add_argument("--grade", action="store_true", help="also run stage 7 (grading) afterwards")
    ap.add_argument("--out", type=Path, default=Path("."), help="where to copy plan.json and transcript.json")
    args = ap.parse_args(argv)

    if args.voice:
        print("error: voice transport is not built yet (ElevenLabs seam in examiner.VoiceTransport); use --text",
              file=sys.stderr)
        return 2
    if args.answers:
        transport = ScriptedTransport(read_answers(args.answers), echo=print)
    else:
        transport = TextTransport()

    options = make_context_options(db=args.db, kb_dirs=args.kb or DEFAULT_KB, use_openai=args.use_openai,
                                   transport=transport, max_questions=args.max_questions)
    if args.use_openai and options["model"] is None:
        print(f"note: {options['model_reason']}", file=sys.stderr)
    runs_root = Path(args.runs)
    ctx = RunContext(submission_id=args.submission, round_no=args.round_no,
                     run_dir=round_dir(runs_root, args.submission, args.round_no),
                     runs_root=runs_root, seed=str(args.submission), options=options)
    try:
        artifacts = run_pipeline(build_stages(), ctx, from_stage=args.from_stage,
                                 stop_after="7" if args.grade else "6")
    except (StageError, ValueError, LookupError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    for name, sid in (("plan.json", "5"), ("transcript.json", "6")):
        env = artifacts[sid]
        body = {**env["data"], "meta": env["meta"]} if sid == "6" else env
        (args.out / name).write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n" + (ctx.run_dir / "stages.md").read_text(encoding="utf-8"))
    print(f"artifacts: {ctx.run_dir}")
    print(f"wrote {args.out / 'plan.json'} and {args.out / 'transcript.json'}")
    if args.grade:
        print(f"report: {ctx.run_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
