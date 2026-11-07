from __future__ import annotations

import ast
import difflib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PIPELINE_ROOT = (
    Path("/app/pipeline_root")
    if Path("/app/pipeline_root").exists()
    else Path(__file__).resolve().parents[3]
)
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

import grade  # noqa: E402
import llm  # noqa: E402


NON_ANSWERS = {
    "dont know",
    "don't know",
    "i dont know",
    "i don't know",
    "idk",
    "no idea",
    "pass",
    "skip",
    "next",
    "n/a",
    "none",
    "not sure",
    "unsure",
}

# Domain concept clusters so natural developer phrasing (e.g. "hashmap", "o(n)", "better speed") is recognized
CONCEPT_CLUSTERS: Dict[str, List[str]] = {
    "complexity_performance": [
        r"\bo\s*\(\s*n\s*\)",
        r"\bo\s*\(\s*1\s*\)",
        r"\bo\s*\(\s*n\s*\^\s*2\s*\)",
        r"\bo\s*\(\s*n\s*log\s*n\s*\)",
        r"\bo\s*\(\s*log\s*n\s*\)",
        r"\blinear\b",
        r"\bconstant\b",
        r"\bquadratic\b",
        r"\blogarithmic\b",
        r"\bspeed\b",
        r"\bfast(?:er)?\b",
        r"\bslow(?:er)?\b",
        r"\btime\s+complexity\b",
        r"\bspace\s+complexity\b",
        r"\bmemory\b",
        r"\befficien(?:t|cy)\b",
        r"\bperformance\b",
        r"\bsingle\s+pass\b",
        r"\bnested\s+loop\b",
        r"\bbrute\s+force\b",
    ],
    "data_structures": [
        r"\bhash\s*map\b",
        r"\bhash\s*table\b",
        r"\bdict(?:ionary)?\b",
        r"\bmap\b",
        r"\bseen\b",
        r"\blookup\b",
        r"\bset\b",
        r"\blist\b",
        r"\barray\b",
        r"\bindex\b",
        r"\bindices\b",
        r"\bkey\b",
        r"\bvalue\b",
        r"\bpair\b",
        r"\bheap(?:q)?\b",
        r"\bqueue\b",
        r"\bstack\b",
        r"\bdeck\b",
        r"\bhand(?:s)?\b",
        r"\bcard(?:s)?\b",
    ],
    "control_flow_mechanics": [
        r"\bloop(?:s|ing)?\b",
        r"\biterate(?:s|d|ing)?\b",
        r"\benumerate\b",
        r"\bfor\b",
        r"\bwhile\b",
        r"\bcheck(?:s|ing)?\b",
        r"\bcomplement\b",
        r"\btarget\b",
        r"\bsubtract\b",
        r"\bdiff(?:erence)?\b",
        r"\bstore(?:s|d)?\b",
        r"\breturn(?:s|ing)?\b",
        r"\bpop(?:s|ping)?\b",
        r"\bshuffle(?:s|d)?\b",
        r"\bsort(?:s|ed|ing)?\b",
        r"\bfilter(?:s|ed|ing)?\b",
        r"\bchunk(?:s|ing)?\b",
    ],
    "validation_debugging": [
        r"\bvalidat(?:e|ion|ing)\b",
        r"\bisinstance\b",
        r"\btype(?:s|error)?\b",
        r"\bint(?:eger)?\b",
        r"\bnone\b",
        r"\bnull\b",
        r"\bempty\b",
        r"\btry\b",
        r"\bexcept(?:ion)?\b",
        r"\braise\b",
        r"\bvalueerror\b",
        r"\bbound(?:s|ary)?\b",
        r"\bedge\s+case\b",
        r"\bnegative\b",
        r"\binvalid\b",
        r"\bguard\b",
        r"\berror\b",
        r"\bbug\b",
        r"\bfail(?:ure|s)?\b",
    ],
    "architecture_consistency": [
        r"\bcall(?:s|ed|er|ing)?\b",
        r"\bfunction(?:s)?\b",
        r"\breturn(?:s|ed)?\b",
        r"\bbool(?:ean)?\b",
        r"\btrue\b",
        r"\bfalse\b",
        r"\blen(?:gth)?\b",
        r"\binvariant\b",
        r"\bcontract\b",
        r"\bdepend(?:s|ency)?\b",
        r"\bschema\b",
        r"\binterface\b",
        r"\bconsisten(?:t|cy)\b",
        r"\bmodule(?:s)?\b",
        r"\bstate\b",
    ],
}


def _is_non_answer(text: str) -> bool:
    cleaned = re.sub(r"[^a-z0-9\s']", "", text.lower()).strip()
    if not cleaned:
        return True
    if cleaned in NON_ANSWERS:
        return True
    # Also catch e.g. "i really dont know" or "pass this question"
    if len(cleaned.split()) <= 5 and any(na in cleaned for na in ("dont know", "don't know", "no idea", "idk")):
        return True
    return False


def _count_cluster_hits(text: str, cluster_name: str) -> List[str]:
    lower = text.lower()
    hits = []
    for pattern in CONCEPT_CLUSTERS.get(cluster_name, []):
        m = re.search(pattern, lower)
        if m:
            hits.append(m.group(0))
    return hits


def _analyze_live_code_diff(mod_item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze a student's live code modification for meaningful structural improvements."""
    if not mod_item or not mod_item.get("was_modified"):
        return {"modified": False, "valid_syntax": True, "added_lines": 0, "features": []}

    starter = (mod_item.get("starter_code") or "").strip()
    modified = (mod_item.get("modified_code") or "").strip()

    diff = list(difflib.unified_diff(starter.splitlines(), modified.splitlines(), lineterm=""))
    added = [line[1:].strip() for line in diff if line.startswith("+") and not line.startswith("+++") and line[1:].strip()]

    valid_syntax = True
    try:
        ast.parse(modified)
    except SyntaxError:
        valid_syntax = False

    added_joined = "\n".join(added).lower()
    features: List[str] = []
    if any(k in added_joined for k in ("if ", "elif ", "isinstance", "not ", "<", ">", "==")):
        features.append("conditional validation guard")
    if any(k in added_joined for k in ("try:", "except", "raise ", "valueerror", "typeerror")):
        features.append("explicit exception handling")
    if "return " in added_joined:
        features.append("updated return contract")
    if "def " in added_joined:
        features.append("updated function signature")
    if not features and added:
        features.append(f"{len(added)} modified code line(s)")

    return {
        "modified": True,
        "valid_syntax": valid_syntax,
        "added_lines": len(added),
        "features": features,
    }


def _score_dimension_analytically(
    dim: str,
    transcript: Dict[str, Any],
    plan: Dict[str, Any],
    live_modifications: List[Dict[str, Any]],
    pass_no: int,
) -> Optional[Dict[str, Any]]:
    """Score a single rubric dimension using semantic concept matching, codebase identifier overlap, and AST diff analysis."""
    qs = [q for q in plan.get("questions", []) if q.get("dimension") == dim]
    q_ids = {q["id"] for q in qs}

    # Collect student turns for this dimension
    if dim == "communication_under_follow_up":
        # Include both Q5 answers AND all follow-up answers across the interview!
        relevant_turns = [
            t
            for t in grade.student_turns(transcript)
            if t.get("question_id") in q_ids or t.get("kind") == "follow_up_answer"
        ]
    else:
        relevant_turns = [
            t for t in grade.student_turns(transcript) if t.get("question_id") in q_ids
        ]

    raw_texts = [t["text"].strip() for t in relevant_turns if t.get("text", "").strip()]
    substantive_texts = [txt for txt in raw_texts if not _is_non_answer(txt)]

    # Check if there is a live code modification associated with this dimension's question
    mod_by_qid = {m["question_id"]: m for m in live_modifications}
    dim_mod = next((mod_by_qid[qid] for qid in q_ids if qid in mod_by_qid), None)
    diff_info = _analyze_live_code_diff(dim_mod)

    # If the student only said "dont know" (or nothing) and didn't modify the code:
    if not substantive_texts and not diff_info["modified"]:
        if not raw_texts:
            return None
        q_prompt = qs[0]["text"] if qs else dim
        return {
            "dimension": dim,
            "score": 0,
            "quotes": raw_texts[:1],
            "confidence": "high",
            "justification": (
                f"Candidate responded '{raw_texts[0]}' without explaining the mechanism or trade-offs asked in: \"{q_prompt[:90]}...\""
            ),
        }

    joined = " ".join(substantive_texts)
    total_words = grade.word_count(joined)

    # Extract identifiers & keywords from planned question + grader notes
    q_context = " ".join(
        [q.get("text", "") + " " + " ".join(q.get("good_answer_mentions", [])) for q in qs]
    ).lower()
    code_identifiers = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", " ".join(q.get("text", "") for q in qs)))

    comp_hits = _count_cluster_hits(joined, "complexity_performance")
    ds_hits = _count_cluster_hits(joined, "data_structures")
    flow_hits = _count_cluster_hits(joined, "control_flow_mechanics")
    val_hits = _count_cluster_hits(joined, "validation_debugging")
    arch_hits = _count_cluster_hits(joined, "architecture_consistency")

    all_concept_hits = list(dict.fromkeys(comp_hits + ds_hits + flow_hits + val_hits + arch_hits))
    id_hits = [ident for ident in code_identifiers if ident.lower() in joined.lower()]

    # Keyword overlap with good_answer_mentions
    kws = grade._keywords([m for q in qs for m in q.get("good_answer_mentions", [])])
    joined_tokens = set(re.findall(r"[a-z0-9_]{3,}", joined.lower()))
    note_hits = sum(1 for k in kws if k and len(k & joined_tokens) >= 1)

    # Calculate score (0 to 4) tailored per dimension
    raw_score = 1.0  # Base credit for a substantive non-empty technical response

    if dim == "code_understanding":
        if flow_hits or ds_hits:
            raw_score += 1.5
        if comp_hits:
            raw_score += 1.0
        if id_hits or note_hits >= 1 or total_words >= 18:
            raw_score += 0.5
    elif dim == "decision_rationale":
        if comp_hits or ds_hits:
            raw_score += 1.5
        if any(w in joined.lower() for w in ("better", "faster", "instead", "because", "trade", "avoid", "lookup", "speed", "memory")):
            raw_score += 0.7
        if total_words >= 15 or note_hits >= 1:
            raw_score += 0.8
    elif dim == "debugging_failure_handling":
        if diff_info["modified"] and diff_info["valid_syntax"]:
            raw_score += 2.0
        if val_hits:
            raw_score += 1.2
        if note_hits >= 1 or total_words >= 15:
            raw_score += 0.8
    elif dim == "consistency_across_rounds":
        if arch_hits or id_hits:
            raw_score += 1.5
        if flow_hits or ds_hits:
            raw_score += 1.0
        if note_hits >= 1 or total_words >= 15:
            raw_score += 0.5
    elif dim == "communication_under_follow_up":
        if comp_hits or ds_hits or flow_hits or val_hits:
            raw_score += 1.5
        if diff_info["modified"] and diff_info["valid_syntax"]:
            raw_score += 1.5
        if len(substantive_texts) >= 1 and (total_words >= 8 or comp_hits):
            raw_score += 0.8

    # Slight pass variation check if borderline, capped cleanly at [1, 4]
    if pass_no == 2 and total_words < 6 and not diff_info["modified"] and raw_score >= 3.0:
        raw_score -= 0.5

    final_score = max(1, min(4, int(round(raw_score))))

    # Build a rich, specific educator justification
    evidence_parts: List[str] = []
    if all_concept_hits:
        evidence_parts.append(f"referenced key technical concepts ({', '.join(all_concept_hits[:5])})")
    if id_hits:
        evidence_parts.append(f"anchored to codebase symbols ({', '.join(id_hits[:3])})")
    if diff_info["modified"]:
        feat_str = ", ".join(diff_info["features"])
        evidence_parts.append(f"submitted a live code modification ({feat_str})")

    if evidence_parts:
        detail_str = "; ".join(evidence_parts)
        if final_score >= 3:
            justification = f"Strong technical evidence ({final_score}/4): Candidate {detail_str}."
        else:
            justification = (
                f"Partial technical evidence ({final_score}/4): Candidate {detail_str}, "
                f"but could expand further on edge-case invariants and line-level mechanics."
            )
    else:
        justification = (
            f"Candidate provided a brief response ({total_words} words) touching on the prompt, "
            f"earning partial credit ({final_score}/4)."
        )

    quotes = substantive_texts[:2] if substantive_texts else raw_texts[:1]
    confidence = "high" if (total_words >= 12 or len(all_concept_hits) >= 2 or diff_info["modified"]) else "medium"

    return {
        "dimension": dim,
        "score": final_score,
        "quotes": quotes,
        "confidence": confidence,
        "justification": justification,
    }


def _try_llm_grade_with_fallback_models(
    transcript: Dict[str, Any],
    plan: Dict[str, Any],
    pass_no: int,
) -> Optional[Dict[str, Any]]:
    """Try LLM grading pass across primary model and fallback Gemini models if rate-limited (HTTP 429)."""
    env_path = PIPELINE_ROOT / ".env"
    if env_path.is_file():
        llm.load_env_file(env_path)

    candidate_models = [
        os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
    ]
    seen_models: set[str] = set()

    for m_name in candidate_models:
        if not m_name or m_name in seen_models:
            continue
        seen_models.add(m_name)
        try:
            model = llm.GeminiJSONModel(model=m_name)
            return grade.model_pass(model, transcript, plan, pass_no)
        except Exception:
            continue
    return None


def run_final_grading_engine(
    transcript: Dict[str, Any],
    plan: Dict[str, Any],
    live_modifications: Optional[List[Dict[str, Any]]] = None,
    use_llm: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Execute the Two-Pass Quote-Verified Final Grading Engine combining LLM + Semantic & AST Codebase Analysis."""
    mods = live_modifications or []

    # Ensure any live code modifications where the student didn't type a separate text answer still have a verbatim student turn
    existing_qids_with_student_turn = {
        t.get("question_id") for t in grade.student_turns(transcript) if t.get("text", "").strip()
    }
    for mod in mods:
        qid = mod.get("question_id")
        if mod.get("was_modified") and qid and qid not in existing_qids_with_student_turn:
            summary_turn = f"Modified {mod.get('target_lines', 'code')} live in editor: {mod.get('modified_code', '')[:120]}"
            transcript["turns"].append(
                {
                    "speaker": "student",
                    "text": summary_turn,
                    "kind": "follow_up_answer" if qid == "Q5" else "answer",
                    "question_id": qid,
                }
            )

    analytical_p1_scores = []
    analytical_p2_scores = []
    for dim in grade.DIMENSIONS:
        s1 = _score_dimension_analytically(dim, transcript, plan, mods, pass_no=1)
        s2 = _score_dimension_analytically(dim, transcript, plan, mods, pass_no=2)
        if s1:
            analytical_p1_scores.append(s1)
        if s2:
            analytical_p2_scores.append(s2)

    analytical_p1 = {
        "grader": "codeviva-semantic-ast-engine (pass 1)",
        "scores": analytical_p1_scores,
    }
    analytical_p2 = {
        "grader": "codeviva-semantic-ast-engine (pass 2)",
        "scores": analytical_p2_scores,
    }

    llm_p1 = _try_llm_grade_with_fallback_models(transcript, plan, pass_no=1) if use_llm else None
    llm_p2 = _try_llm_grade_with_fallback_models(transcript, plan, pass_no=2) if use_llm else None

    # Blend LLM & Analytical passes so valid concise technical answers and live code edits are never lost to 429s or overly rigid prompts
    def _merge_pass(llm_raw: Optional[Dict[str, Any]], ana_raw: Dict[str, Any], pass_idx: int) -> Dict[str, Any]:
        if not llm_raw or not llm_raw.get("scores"):
            return ana_raw
        llm_by_dim = {s.get("dimension"): s for s in llm_raw.get("scores", [])}
        ana_by_dim = {s.get("dimension"): s for s in ana_raw.get("scores", [])}
        merged_scores = []
        for dim in grade.DIMENSIONS:
            ls = llm_by_dim.get(dim)
            ans = ana_by_dim.get(dim)
            if ls and grade.verify_pass({"scores": [ls]}, transcript)["scores"]:
                # If LLM gave 0 on a dimension where analytical engine found clear technical concepts or a valid live code edit, blend them
                if ls["score"] == 0 and ans and ans["score"] >= 2:
                    merged_scores.append(
                        {
                            **ans,
                            "score": max(ls["score"], ans["score"] - 1),
                        }
                    )
                else:
                    merged_scores.append(ls)
            elif ans:
                merged_scores.append(ans)
        return {
            "grader": f"{llm_raw.get('grader', 'gemini')} + AST/Semantic Verifier (Pass {pass_idx})",
            "scores": merged_scores,
        }

    raw1 = _merge_pass(llm_p1, analytical_p1, 1)
    raw2 = _merge_pass(llm_p2, analytical_p2, 2)

    p1 = grade.verify_pass(raw1, transcript)
    p2 = grade.verify_pass(raw2, transcript)
    synth = grade.synthesise(p1, p2)

    report = {
        "status": "DRAFT: AI-drafted, pending review by a named academic",
        "reviewer": None,
        "disclaimer": grade.DISCLAIMER,
        "conversation_id": transcript.get("conversation_id"),
        "round": plan.get("round", 1),
        "grader": p1["grader"],
        "grader_note": "",
        **synth,
        "dropped_scores": {"pass1": p1["dropped"], "pass2": p2["dropped"]},
        "stacked_question_turns": grade.stacked_turns(transcript),
        "student_words": sum(grade.word_count(t["text"]) for t in grade.student_turns(transcript)),
        "live_modifications": mods,
    }
    return {"raw": raw1, "verified": p1}, {"raw": raw2, "verified": p2}, report
