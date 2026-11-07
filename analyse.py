"""Stage 3 (model proposals) and stage 4 (verification in code).

Stage 3 asks the model for decision points the rules did not anticipate, given the facts, the
line-numbered code, the commit list and the assignment spec. The raw response is saved
untouched. Only code excerpts, facts and commit messages are sent: no names, no submission id.

Stage 4 checks every proposal against the real repository and either accepts it or rejects
it with a reason. The model adds flexibility; this code keeps it accountable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from kb_match import DIMENSIONS
from llm import JSONModel, ModelError, strict_object

MAX_CODE_CHARS = 60_000
MAX_PROPOSALS = 6
LINE_TOLERANCE = 2  # a proposal within 2 lines of a rule question's fact counts as a duplicate

PROPOSAL_SCHEMA = strict_object({
    "proposals": {
        "type": "array",
        "items": strict_object({
            "title": {"type": "string"},
            "question": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "file": {"type": "string"},
            "line": {"type": "integer"},
            "commit": {"type": "string", "description": "short or full sha, or empty string"},
            "fact_ids": {"type": "array", "items": {"type": "string"}},
            "dimension": {"type": "string", "enum": list(DIMENSIONS)},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "follow_up": {"type": "string"},
            "good_answer_mentions": {"type": "array", "items": {"type": "string"}},
        }),
    }
})

SYSTEM_PROMPT = """You help plan an oral examination about a student's programming coursework.
You receive deterministic facts extracted from the code, the line-numbered source, the commit
history and the assignment spec. Propose up to {n} additional design decisions worth asking
about that the existing rule questions do NOT already cover: trade-offs, thresholds, data
structures, failure handling, bugs visible in the history, or fragile behaviour.

Requirements for every proposal:
- cite a real file and line number from the numbered source; cite a commit only if it appears
  in the commit list, otherwise use an empty string
- list the ids of supporting facts if any apply
- "question" is ONE short question with exactly one question mark, neutral and calm in tone,
  answerable from the student's own experience of building the code
- "follow_up" is one optional probing question (exactly one question mark) or empty
- "good_answer_mentions" are notes for human graders
- set confidence to "low" if you are unsure the decision is real
Do not invent code, lines or commits."""


def number_lines(files: Dict[str, str]) -> str:
    out, total = [], 0
    for path in sorted(p for p in files if p.endswith(".py")):
        block = f"### {path}\n" + "\n".join(f"{i:4d}  {line}" for i, line in enumerate(files[path].splitlines(), 1))
        if total + len(block) > MAX_CODE_CHARS:
            out.append(f"### {path}\n(omitted: code budget reached)")
            continue
        out.append(block)
        total += len(block)
    return "\n\n".join(out)


def _compact_fact(f: Dict[str, Any]) -> str:
    skip = {"id", "kind", "file", "line", "commit", "commit_message"}
    extra = ", ".join(f"{k}={v}" for k, v in f.items() if k not in skip)
    loc = f"{f.get('file')}:{f.get('line')}" if f.get("line") else str(f.get("file"))
    return f"{f['id']} {f['kind']} {loc} {extra}"


def build_prompt(files: Dict[str, str], commits: List[Dict[str, Any]], facts: List[Dict[str, Any]],
                 rule_questions: List[Dict[str, Any]], spec: str) -> str:
    commit_lines = "\n".join(f"{c['sha'][:7]} {c['message']}" for c in commits) or "(no history)"
    rq = "\n".join(f"- [{q['rule_id']}] {q['question']}" for q in rule_questions) or "(none)"
    return (
        f"## Assignment spec\n{spec or '(not provided)'}\n\n"
        f"## Commit history (oldest first)\n{commit_lines}\n\n"
        f"## Facts\n" + "\n".join(_compact_fact(f) for f in facts) + "\n\n"
        f"## Questions already covered by rules (do not duplicate)\n{rq}\n\n"
        f"## Source (line-numbered)\n{number_lines(files)}\n"
    )


def propose(model: Optional[JSONModel], unavailable_reason: str, files: Dict[str, str],
            commits: List[Dict[str, Any]], facts: List[Dict[str, Any]],
            rule_questions: List[Dict[str, Any]], spec: str) -> Dict[str, Any]:
    """Stage 3. Returns data for stage3_model_raw.json; never raises on model failure."""
    if model is None:
        return {"status": "skipped", "reason": unavailable_reason, "model": None, "response": None}
    try:
        response = model.complete_json(
            system=SYSTEM_PROMPT.format(n=MAX_PROPOSALS),
            user=build_prompt(files, commits, facts, rule_questions, spec),
            schema=PROPOSAL_SCHEMA, name="decision_proposals",
        )
    except ModelError as exc:
        return {"status": "failed", "reason": str(exc), "model": model.model,
                "response": None}
    return {"status": "ok", "reason": "", "model": model.model, "response": response}


# --------------------------------------------------------------------------- stage 4

def _words(text: str) -> set:
    return set(re.findall(r"[a-z_]{3,}", text.lower()))


def _resolve_commit(ref: str, commits: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ref = (ref or "").strip().lower()
    if len(ref) < 7 or not re.fullmatch(r"[0-9a-f]+", ref):
        return None
    hits = [c for c in commits if c["sha"].lower().startswith(ref)]
    return hits[0] if len(hits) == 1 else None


def verify(raw: Dict[str, Any], files: Dict[str, str], commits: List[Dict[str, Any]],
           facts: List[Dict[str, Any]], rule_matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Stage 4: accept or reject every proposal with a reason."""
    proposals = (raw.get("response") or {}).get("proposals", []) if raw.get("status") == "ok" else []
    fact_by_id = {f["id"]: f for f in facts}
    rule_anchors = []
    for m in rule_matches:
        if m["triggered"] and m["chosen_fact_id"]:
            f = fact_by_id.get(m["chosen_fact_id"], {})
            rule_anchors.append((m["rule_id"], f.get("file"), f.get("line"), _words(m["question"] or "")))

    results, accepted_n = [], 0
    for index, p in enumerate(proposals[:MAX_PROPOSALS * 2]):
        entry: Dict[str, Any] = {"index": index, "proposal": p, "accepted": False, "reasons": []}
        file, line = p.get("file", ""), p.get("line")
        lines = files.get(file, "").splitlines() if file in files else None

        if lines is None:
            entry["reasons"].append(f"bad file: {file!r} is not in the submission")
        elif not isinstance(line, int) or not 1 <= line <= len(lines):
            entry["reasons"].append(f"bad line: {file} has {len(lines)} lines, proposal cites {line}")
        commit = None
        if p.get("commit"):
            commit = _resolve_commit(p["commit"], commits)
            if commit is None:
                entry["reasons"].append(f"unknown commit: {p['commit']!r}")
        if p.get("confidence") == "low":
            entry["reasons"].append("low confidence reported by the model")
        if p.get("question", "").count("?") != 1:
            entry["reasons"].append("question must contain exactly one '?'")
        if p.get("follow_up") and p["follow_up"].count("?") != 1:
            entry["reasons"].append("follow-up must contain exactly one '?'")
        if p.get("dimension") not in DIMENSIONS:
            entry["reasons"].append(f"unknown dimension {p.get('dimension')!r}")
        qwords = _words(p.get("question", ""))
        for rule_id, rfile, rline, rwords in rule_anchors:
            near = rfile == file and rline and isinstance(line, int) and abs(rline - line) <= LINE_TOLERANCE
            overlap = len(qwords & rwords) / max(1, len(qwords | rwords))
            if near or overlap > 0.6:
                entry["reasons"].append(f"duplicates rule question {rule_id}")
                break

        cited = [fid for fid in p.get("fact_ids", []) if fid in fact_by_id]
        unknown = [fid for fid in p.get("fact_ids", []) if fid not in fact_by_id]
        nearby = [f["id"] for f in facts if f.get("file") == file and f.get("line") and isinstance(line, int)
                  and abs(f["line"] - line) <= 1]
        entry["fact_ids"] = sorted(set(cited) | set(nearby))
        if unknown:
            entry["dropped_fact_ids"] = unknown
        entry["commit"] = commit["sha"] if commit else None
        entry["commit_message"] = commit["message"] if commit else None

        if not entry["reasons"]:
            accepted_n += 1
            entry["accepted"] = True
            entry["proposal_id"] = f"M{accepted_n}"
        results.append(entry)

    return {
        "status": raw.get("status"),
        "reason": raw.get("reason", ""),
        "results": results,
        "accepted": accepted_n,
        "rejected": len(results) - accepted_n,
    }
