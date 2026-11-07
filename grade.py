"""Stage 7: draft grades with verified quotes and a human-review flag set in code.

    python grade.py transcript.json plan.json [--use-llm] [--out DIR]

Two independent grading passes score five dimensions 0-4. Every score must rest on verbatim
student quotes; code checks each quote is a substring of what the STUDENT said and drops any
score left without support. needs_human_review is set by code, never by the model, when:
  - a score rests on fewer than MIN_EVIDENCE_WORDS student words
  - a pass reports low confidence
  - the two passes differ by more than 1 point on a dimension, or on the total
  - a score was dropped as unsupported, or a dimension is missing
Grades are AI-drafted and must be reviewed by a named academic. Agreement between passes is a
reliability signal; it does not show that the grades are valid.

Without a model a deterministic keyword grader produces the passes. It is a demo fallback,
labelled as such in the report.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from artifacts import hash_json, read_artifact, write_artifact
from kb_match import DIMENSIONS
from llm import JSONModel, ModelError, get_model, strict_object

MIN_EVIDENCE_WORDS = 15
MAX_PASS_DIFF = 1
DIMENSION_LABELS = {
    "decision_rationale": "Decision rationale",
    "code_understanding": "Code understanding",
    "debugging_failure_handling": "Debugging and failure handling",
    "consistency_across_rounds": "Consistency across rounds",
    "communication_under_follow_up": "Communication under follow-up",
}
RUBRIC = {
    "decision_rationale": "explains why a threshold, structure or approach was chosen and what was traded off",
    "code_understanding": "accurately describes what specific parts of their own code do and why",
    "debugging_failure_handling": "describes real bugs met, how they were found and fixed, and what remains fragile",
    "consistency_across_rounds": "claims match the commit history and code (round 1: within this submission; "
                                 "the stated plan is checked in round 2)",
    "communication_under_follow_up": "answers the question asked, adapts when probed, admits uncertainty honestly",
}
DISCLAIMER = ("These grades are an AI-drafted proposal. They are not final and have not been validated: "
              "a named member of academic staff reviews them and owns every mark. Agreement between the "
              "automated grading passes shows consistency only, not that the grades are right.")

GRADE_SCHEMA = strict_object({
    "scores": {"type": "array", "items": strict_object({
        "dimension": {"type": "string", "enum": list(DIMENSIONS)},
        "score": {"type": "integer", "minimum": 0, "maximum": 4},
        "quotes": {"type": "array", "items": {"type": "string"}},
        "justification": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    })},
})
GRADE_SYSTEM = """You are an independent grader for an oral examination about a student's own code.
Score each of the five dimensions from 0 (no evidence) to 4 (strong evidence) using the rubric.
For every score give 1-3 quotes copied EXACTLY, character for character, from the student's
turns (never from the examiner). Quote enough words to show the evidence. If the student said
too little to judge a dimension, give a low score with confidence "low". Judge understanding,
not fluency or accent: do not penalise grammar, hesitation or non-native phrasing. If the
examiner asked several questions in one turn, score only the parts the student answered."""


# --------------------------------------------------------------------------- loading

def load_json_artifact(path: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (data, meta) for an enveloped, flat-with-meta, or plain JSON file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "meta" in raw:
        env = read_artifact(Path(path))
        return env["data"], env["meta"]
    return raw, {}


def student_turns(transcript: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [t for t in transcript["turns"] if t["speaker"] == "student"]


def _norm(text: str) -> str:
    return " ".join(text.split())


def quote_is_verbatim(quote: str, transcript: Dict[str, Any]) -> bool:
    q = _norm(quote)
    return bool(q) and any(q in _norm(t["text"]) for t in student_turns(transcript))


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


# --------------------------------------------------------------------------- passes

def render_for_grader(transcript: Dict[str, Any], plan: Dict[str, Any], order: List[str]) -> str:
    qs = "\n".join(
        f"{q['id']} [{q['dimension']}] {q['text']}\n   grader notes: " + "; ".join(q.get("good_answer_mentions", []))
        for q in plan["questions"])
    rubric = "\n".join(f"- {d}: {RUBRIC[d]}" for d in order)
    convo = "\n".join(f"{t['speaker'].upper()}: {t['text']}" for t in transcript["turns"])
    return f"## Rubric (score 0-4)\n{rubric}\n\n## Planned questions\n{qs}\n\n## Transcript\n{convo}\n"


def model_pass(model: JSONModel, transcript: Dict[str, Any], plan: Dict[str, Any], pass_no: int) -> Dict[str, Any]:
    order = list(DIMENSIONS) if pass_no == 1 else list(reversed(DIMENSIONS))  # vary presentation per pass
    resp = model.complete_json(system=GRADE_SYSTEM + f"\n(Independent pass {pass_no}.)",
                               user=render_for_grader(transcript, plan, order),
                               schema=GRADE_SCHEMA, name="grades")
    return {"grader": f"{getattr(model, 'provider', 'llm')}:{model.model}", "scores": resp.get("scores", [])}


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _keywords(mentions: List[str]) -> List[set]:
    stop = {"that", "with", "from", "this", "than", "into", "such", "what", "when", "which", "their", "rather",
            "versus", "about", "because", "would", "there", "every", "each", "only", "more", "less"}
    return [{w for w in re.findall(r"[a-z0-9_]{4,}", m.lower()) if w not in stop} for m in mentions]


def heuristic_pass(transcript: Dict[str, Any], plan: Dict[str, Any], pass_no: int) -> Dict[str, Any]:
    """Deterministic demo grader: keyword overlap with grader notes. Not a substitute for a model."""
    by_q: Dict[str, List[str]] = {}
    for t in student_turns(transcript):
        by_q.setdefault(t.get("question_id") or "", []).append(t["text"])
    scores = []
    follow_ups = [t for t in student_turns(transcript) if t.get("kind") == "follow_up_answer"]
    for dim in DIMENSIONS:
        qs = [q for q in plan["questions"] if q["dimension"] == dim]
        if dim == "communication_under_follow_up":
            texts = [t["text"] for t in follow_ups]
            mentions_hit, total_mentions = sum(1 for t in texts if word_count(t) >= 12), max(1, len(texts))
            candidates = [s for t in texts for s in _sentences(t)]
        else:
            texts = [a for q in qs for a in by_q.get(q["id"], [])]
            kws = _keywords([m for q in qs for m in q.get("good_answer_mentions", [])])
            total_mentions = max(1, len(kws))
            joined = " ".join(texts).lower()
            mentions_hit = sum(1 for k in kws if k and len(k & set(re.findall(r"[a-z0-9_]{4,}", joined))) >= 1)
            all_kw = set().union(*kws) if kws else set()
            candidates = sorted((s for t in texts for s in _sentences(t)),
                                key=lambda s: -len(all_kw & set(re.findall(r"[a-z0-9_]{4,}", s.lower()))))
        if not texts:
            continue
        ratio = mentions_hit / total_mentions
        score = min(4, round(ratio * 4 + (0.5 if word_count(" ".join(texts)) > 60 else 0)))
        quotes = candidates[:2]
        conf = "medium" if mentions_hit >= 2 else "low"
        scores.append({"dimension": dim, "score": score, "quotes": quotes, "confidence": conf,
                       "justification": f"{mentions_hit} of {total_mentions} grader notes touched (keyword match)"})
    return {"grader": "heuristic-keyword (no model; demo only)", "scores": scores}


def verify_pass(raw: Dict[str, Any], transcript: Dict[str, Any]) -> Dict[str, Any]:
    """Drop quotes that are not verbatim student text; drop scores left without quotes."""
    kept, dropped = [], []
    seen = set()
    for s in raw.get("scores", []):
        dim = s.get("dimension")
        if dim not in DIMENSIONS or dim in seen or not isinstance(s.get("score"), int) or not 0 <= s["score"] <= 4:
            dropped.append({"dimension": dim, "reason": "invalid or duplicate dimension/score"})
            continue
        good = [q for q in s.get("quotes", []) if quote_is_verbatim(q, transcript)]
        bad = [q for q in s.get("quotes", []) if not quote_is_verbatim(q, transcript)]
        if not good:
            dropped.append({"dimension": dim, "reason": "no quote is verbatim student text", "rejected_quotes": bad})
            continue
        seen.add(dim)
        kept.append({**s, "quotes": good, "rejected_quotes": bad,
                     "evidence_words": sum(word_count(q) for q in good)})
    return {"grader": raw.get("grader"), "scores": kept, "dropped": dropped}


# --------------------------------------------------------------------------- synthesis

def synthesise(p1: Dict[str, Any], p2: Dict[str, Any]) -> Dict[str, Any]:
    a = {s["dimension"]: s for s in p1["scores"]}
    b = {s["dimension"]: s for s in p2["scores"]}
    dims, reasons_all = [], []
    for dim in DIMENSIONS:
        s1, s2 = a.get(dim), b.get(dim)
        reasons = []
        if not s1 or not s2:
            reasons.append("score missing or unsupported in at least one pass")
        present = [s for s in (s1, s2) if s]
        if s1 and s2 and abs(s1["score"] - s2["score"]) > MAX_PASS_DIFF:
            reasons.append(f"passes disagree by {abs(s1['score'] - s2['score'])} points")
        if any(s["confidence"] == "low" for s in present):
            reasons.append("a grading pass reported low confidence")
        if present and min(s["evidence_words"] for s in present) < MIN_EVIDENCE_WORDS:
            reasons.append(f"thin evidence (fewer than {MIN_EVIDENCE_WORDS} quoted student words)")
        score = round(sum(s["score"] for s in present) / len(present), 1) if present else None
        quotes = []
        for s in present:
            for q in s["quotes"]:
                if q not in quotes:
                    quotes.append(q)
        dims.append({"dimension": dim, "label": DIMENSION_LABELS[dim], "score": score,
                     "pass_scores": [s1["score"] if s1 else None, s2["score"] if s2 else None],
                     "quotes": quotes[:3], "justifications": [s["justification"] for s in present],
                     "needs_human_review": bool(reasons), "review_reasons": reasons})
        reasons_all += [f"{DIMENSION_LABELS[dim]}: {r}" for r in reasons]

    t1 = sum(s["score"] for s in p1["scores"])
    t2 = sum(s["score"] for s in p2["scores"])
    if abs(t1 - t2) > MAX_PASS_DIFF:
        reasons_all.append(f"pass totals differ by {abs(t1 - t2)} points ({t1} vs {t2})")
    scored = [d["score"] for d in dims if d["score"] is not None]
    return {"dimensions": dims, "total": round(sum(scored), 1) if scored else None,
            "max_total": 4 * len(DIMENSIONS), "pass_totals": [t1, t2],
            "needs_human_review": bool(reasons_all), "review_reasons": reasons_all}


def stacked_turns(transcript: Dict[str, Any]) -> int:
    return sum(1 for t in transcript["turns"] if t["speaker"] == "examiner" and t["text"].count("?") > 1)


def report_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Your oral assessment: draft feedback",
        "",
        f"> **Draft, pending review.** {DISCLAIMER}",
        "",
        f"Conversation: `{report['conversation_id']}`. Grader: {report['grader']}.",
        "",
    ]
    if report["needs_human_review"]:
        lines += ["A member of staff will look at this conversation closely before any mark is confirmed. "
                  "This is routine and does not mean anything is wrong.", ""]
    lines += ["| Area | Draft score (0-4) |", "|---|---|"]
    for d in report["dimensions"]:
        lines.append(f"| {d['label']} | {d['score'] if d['score'] is not None else 'not scored'} |")
    lines += ["", f"**Draft total:** {report['total']} / {report['max_total']}", "", "## What we based this on", ""]
    for d in report["dimensions"]:
        lines.append(f"### {d['label']}")
        if d["quotes"]:
            lines += [f"> \"{q}\"" for q in d["quotes"]]
        else:
            lines.append("We did not hear enough on this area to score it; a member of staff will review it.")
        lines.append("")
    lines += ["## If you disagree", "",
              "You can ask for a human review of any part of this feedback through your course team.", ""]
    return "\n".join(lines)


def grade(transcript: Dict[str, Any], plan: Dict[str, Any], model: Optional[JSONModel],
          model_note: str = "") -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Returns (pass1, pass2, report)."""
    raws: List[Dict[str, Any]] = []
    note = model_note
    for n in (1, 2):
        raw = None
        if model is not None:
            try:
                raw = model_pass(model, transcript, plan, n)
            except ModelError as exc:
                note = f"model grading failed ({exc}); used heuristic grader"
        raws.append(raw or heuristic_pass(transcript, plan, n))
    p1, p2 = (verify_pass(r, transcript) for r in raws)
    synth = synthesise(p1, p2)
    report = {
        "status": "DRAFT: AI-drafted, pending review by a named academic",
        "reviewer": None,
        "disclaimer": DISCLAIMER,
        "conversation_id": transcript.get("conversation_id"),
        "round": plan.get("round", 1),
        "grader": p1["grader"],
        "grader_note": note,
        **synth,
        "dropped_scores": {"pass1": p1["dropped"], "pass2": p2["dropped"]},
        "stacked_question_turns": stacked_turns(transcript),
        "student_words": sum(word_count(t["text"]) for t in student_turns(transcript)),
    }
    return {"raw": raws[0], "verified": p1}, {"raw": raws[1], "verified": p2}, report


def write_outputs(out_dir: Path, transcript: Dict[str, Any], plan: Dict[str, Any], results: Tuple,
                  submission_id: str = "", round_no: int = 1, input_hash: str = "") -> Dict[str, Path]:
    p1, p2, report = results
    input_hash = input_hash or hash_json({"transcript": hash_json(transcript), "plan": hash_json(plan)})
    model = None if report["grader"].startswith("heuristic") else report["grader"]
    paths = {}
    for name, data in (("stage7_grades_pass1.json", p1), ("stage7_grades_pass2.json", p2)):
        n = len(data["verified"]["scores"])
        write_artifact(out_dir / name, stage="grade", stage_id="7", round_no=round_no, submission_id=submission_id,
                       input_hash=input_hash, data=data, count_in=len(data["raw"].get("scores", [])), count_out=n,
                       summary=f"{n} verified scores, {len(data['verified']['dropped'])} dropped", model=model)
        paths[name] = out_dir / name
    flag = "NEEDS HUMAN REVIEW" if report["needs_human_review"] else "no review flags"
    write_artifact(out_dir / "report.json", stage="grade", stage_id="7", round_no=round_no,
                   submission_id=submission_id, input_hash=input_hash, data=report,
                   count_in=len(report["dimensions"]),
                   count_out=sum(1 for d in report["dimensions"] if d["score"] is not None),
                   summary=f"draft total {report['total']}/{report['max_total']}; {flag}", model=model)
    (out_dir / "report.md").write_text(report_markdown(report), encoding="utf-8")
    paths["report.json"] = out_dir / "report.json"
    paths["report.md"] = out_dir / "report.md"
    return paths


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Draft grades for one interview transcript.")
    ap.add_argument("transcript", type=Path)
    ap.add_argument("plan", type=Path)
    ap.add_argument("--use-llm", "--use-openai", dest="use_openai", action="store_true",
                    help="use the model layer (provider from LLM_PROVIDER / .env)")
    ap.add_argument("--out", type=Path, help="output dir (default: next to the transcript)")
    args = ap.parse_args(argv)
    try:
        transcript, tmeta = load_json_artifact(args.transcript)
        plan, _ = load_json_artifact(args.plan)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    model, note = get_model(args.use_openai)
    if note and args.use_openai:
        print(note, file=sys.stderr)
    results = grade(transcript, plan, model, note)
    out = args.out or args.transcript.parent
    paths = write_outputs(out, transcript, plan, results, submission_id=str(tmeta.get("submission_id", "")),
                          round_no=int(tmeta.get("round", plan.get("round", 1))))
    report = results[2]
    print(f"draft total {report['total']}/{report['max_total']}  grader: {report['grader']}")
    print("needs_human_review:", report["needs_human_review"])
    for r in report["review_reasons"]:
        print("  -", r)
    print("wrote", ", ".join(str(p) for p in paths.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
