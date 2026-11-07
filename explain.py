"""Print the evidence trail for one question: plan -> rule or model proposal -> facts -> code.

    python explain.py runs/1/round1 Q2
    python explain.py runs/1/round1 --all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from artifacts import read_artifact


def load_run(run_dir: Path) -> Dict[str, Dict[str, Any]]:
    names = {"0": "stage0_submission.json", "1": "stage1_facts.json", "2": "stage2_rule_matches.json",
             "3": "stage3_model_raw.json", "4": "stage4_verified.json", "5": "stage5_plan.json"}
    out = {}
    for sid, name in names.items():
        path = run_dir / name
        if not path.exists():
            raise FileNotFoundError(f"{path} missing; run the pipeline up to stage 5 first")
        out[sid] = read_artifact(path)
    return out


def code_line(stage0: Dict[str, Any], file: Optional[str], line: Optional[int]) -> str:
    if not file or not line:
        return ""
    for f in stage0["data"]["files"]:
        if f["path"] == file:
            lines = f["content"].splitlines()
            if 0 < line <= len(lines):
                return lines[line - 1].strip()
    return "(line not found)"


def describe_fact(fact: Dict[str, Any], stage0: Dict[str, Any], indent: str) -> List[str]:
    skip = {"id", "kind", "file", "line", "commit", "commit_short", "commit_message"}
    details = ", ".join(f"{k}={v}" for k, v in fact.items() if k not in skip)
    loc = f"{fact.get('file')}:{fact['line']}" if fact.get("line") else f"{fact.get('file')} (commit-level)"
    out = [f"{indent}{fact['id']} {fact['kind']} @ {loc}  {details}"]
    src = code_line(stage0, fact.get("file"), fact.get("line"))
    if src:
        out.append(f"{indent}    code:   {src}")
    if fact.get("commit"):
        out.append(f"{indent}    commit: {fact['commit'][:7]} \"{fact.get('commit_message', '')}\"")
    return out


def explain(run: Dict[str, Dict[str, Any]], qid: str) -> str:
    plan = run["5"]["data"]
    q = next((x for x in plan["questions"] if x["id"] == qid), None)
    if q is None:
        known = ", ".join(x["id"] for x in plan["questions"])
        raise KeyError(f"{qid} is not in the plan (questions: {known})")
    facts = {f["id"]: f for f in run["1"]["data"]["facts"]}
    s0 = run["0"]
    lines = [f"{q['id']} [{q['dimension']}]", f"  \"{q['text']}\"", "",
             f"stage 5 plan   why selected: {q['why_selected']}  (seed {plan['seed']}, mode: {plan['mode']})"]
    src = q["source"]
    if src["type"] == "rule":
        m = next(x for x in run["2"]["data"]["matches"] if x["rule_id"] == src["rule_id"])
        lines.append(f"stage 2 rule   {m['rule_id']}: {m['title']}  ({m['source_file']}, priority {m['priority']})")
        if m["chosen_fact_id"] is None:
            lines.append("               always-asked rule: not tied to a fact")
        else:
            lines.append(f"               matched {len(m['instances'])} fact(s): {', '.join(m['instances'])}; "
                         f"chosen in code with seed {plan['seed']}: {m['chosen_fact_id']}")
            lines.append("stage 1 fact")
            lines += describe_fact(facts[m["chosen_fact_id"]], s0, "               ")
    else:
        v = next(r for r in run["4"]["data"]["results"] if r.get("proposal_id") == src["proposal_id"])
        p = v["proposal"]
        raw = run["3"]
        lines.append(f"stage 3 model  proposal #{v['index']} from {raw['meta']['model']}: {p['title']}")
        lines.append(f"               why it matters: {p['why_it_matters']}  (confidence {p['confidence']})")
        lines.append(f"stage 4 verify accepted as {v['proposal_id']}: {p['file']}:{p['line']} exists"
                     + (f", commit {v['commit'][:7]} exists" if v["commit"] else ""))
        lines.append(f"               cited line: {code_line(s0, p['file'], p['line'])}")
        if v.get("dropped_fact_ids"):
            lines.append(f"               dropped unknown fact ids: {', '.join(v['dropped_fact_ids'])}")
        if v["fact_ids"]:
            lines.append("stage 1 facts")
            for fid in v["fact_ids"]:
                lines += describe_fact(facts[fid], s0, "               ")
    lines.append(f"stage 0 input  submission {s0['data']['submission_id']}, "
                 f"{len(s0['data']['files'])} files, {len(s0['data']['commits'])} commits")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Show why a question was asked.")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("question_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)
    try:
        run = load_run(args.run_dir)
        ids = [q["id"] for q in run["5"]["data"]["questions"]] if args.all else [args.question_id]
        if not ids or ids == [None]:
            ap.error("give a question id or --all")
        print("\n\n".join(explain(run, qid) for qid in ids))
    except (FileNotFoundError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
