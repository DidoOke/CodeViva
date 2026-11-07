"""Stage 5: build the final question plan from rule matches and verified model proposals.

Selection is done entirely in code:
  1. the best rule question for each dimension (highest priority, seeded tie-break)
  2. up to MAX_MODEL_QUESTIONS accepted model proposals
  3. remaining slots by rule priority
  4. the "always" rule (plan for next iteration) last, so round 2 can check it
Two questions are never anchored on the same fact (or the same commit). Every question
records why it was selected; every rule not used records why not.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from kb_match import DIMENSIONS

DEFAULT_MAX_QUESTIONS = 5
MAX_MODEL_QUESTIONS = 2
QUESTION_ORDER = ["decision_rationale", "code_understanding", "debugging_failure_handling",
                  "communication_under_follow_up", "consistency_across_rounds"]


def _anchor(fact: Optional[Dict[str, Any]]) -> Optional[Tuple[Any, ...]]:
    if not fact:
        return None
    if fact.get("line") is None:
        return ("commit", fact.get("commit"))
    return ("line", fact.get("file"), fact.get("line"))


def _citation(fact: Dict[str, Any]) -> Dict[str, Any]:
    return {"file": fact.get("file"), "line": fact.get("line"), "commit": fact.get("commit"),
            "commit_message": fact.get("commit_message"), "fact_id": fact["id"]}


def build_plan(rule_matches: List[Dict[str, Any]], verified: Dict[str, Any], facts: List[Dict[str, Any]],
               seed: str, round_no: int = 1, max_questions: int = DEFAULT_MAX_QUESTIONS) -> Dict[str, Any]:
    fact_by_id = {f["id"]: f for f in facts}
    triggered = [m for m in rule_matches if m["triggered"]]
    always = [m for m in triggered if m["chosen_fact_id"] is None]
    fact_rules = [m for m in triggered if m["chosen_fact_id"] is not None]

    def rank(m: Dict[str, Any]) -> Tuple[int, str]:
        # priority first; ties broken by a seeded hash, never by the model
        return (-m["priority"], hashlib.sha256(f"{seed}:{m['rule_id']}".encode()).hexdigest())

    fact_rules.sort(key=rank)
    slots = max_questions - (1 if always else 0)
    picked: List[Dict[str, Any]] = []
    used_anchors: set = set()
    reasons_not: Dict[str, str] = {}

    def try_pick(item: Dict[str, Any], why: str) -> bool:
        if len(picked) >= slots:
            return False
        anchors = item["anchors"]
        clash = [a for a in anchors if a and a in used_anchors]
        if clash:
            reasons_not[item["key"]] = f"same code location or commit as an already selected question ({clash[0]})"
            return False
        used_anchors.update(a for a in anchors if a)
        item["why_selected"] = why
        picked.append(item)
        return True

    def rule_item(m: Dict[str, Any]) -> Dict[str, Any]:
        fact = fact_by_id[m["chosen_fact_id"]]
        return {"key": m["rule_id"], "text": m["question"], "follow_up": m["follow_up"],
                "good_answer_mentions": m["good_answer_mentions"], "dimension": m["dimension"],
                "source": {"type": "rule", "rule_id": m["rule_id"], "fact_id": fact["id"],
                           "instances": len(m["instances"])},
                "citations": [_citation(fact)], "anchors": [_anchor(fact)]}

    # 1. best rule per dimension
    for dim in QUESTION_ORDER:
        for m in fact_rules:
            if m["dimension"] == dim and m["rule_id"] not in {p["key"] for p in picked}:
                if try_pick(rule_item(m), f"highest-priority triggered rule for {dim} (priority {m['priority']})"):
                    break

    # 2. verified model proposals
    model_items = 0
    for r in verified.get("results", []):
        if not r["accepted"]:
            continue
        p = r["proposal"]
        if model_items >= MAX_MODEL_QUESTIONS:
            reasons_not[r["proposal_id"]] = f"model question cap ({MAX_MODEL_QUESTIONS}) reached"
            continue
        cites = [{"file": p["file"], "line": p["line"], "commit": r["commit"],
                  "commit_message": r["commit_message"], "fact_id": None}]
        cites += [_citation(fact_by_id[f]) for f in r["fact_ids"]]
        item = {"key": r["proposal_id"], "text": p["question"], "follow_up": p.get("follow_up", ""),
                "good_answer_mentions": p.get("good_answer_mentions", []), "dimension": p["dimension"],
                "source": {"type": "model", "proposal_id": r["proposal_id"], "proposal_index": r["index"],
                           "fact_ids": r["fact_ids"]},
                "citations": cites,
                "anchors": [("line", p["file"], p["line"])] + [_anchor(fact_by_id[f]) for f in r["fact_ids"]]}
        if try_pick(item, f"verified model proposal ({p.get('confidence')} confidence): {p.get('why_it_matters', '')}"):
            model_items += 1

    # 3. fill: prefer less-covered dimensions, then priority
    remaining = [m for m in fact_rules if m["rule_id"] not in {p["key"] for p in picked}]
    while remaining:
        covered = {d: sum(1 for p in picked if p["dimension"] == d) for d in DIMENSIONS}
        remaining.sort(key=lambda m: (covered.get(m["dimension"], 0), rank(m)))
        m = remaining.pop(0)
        if not try_pick(rule_item(m), f"next triggered rule, favouring less-covered dimensions "
                                      f"(priority {m['priority']})") and m["rule_id"] not in reasons_not:
            reasons_not[m["rule_id"]] = "question limit reached"

    # 4. the always-asked closing question
    for i, m in enumerate(always):
        item = {"key": m["rule_id"], "text": m["question"], "follow_up": m["follow_up"],
                "good_answer_mentions": m["good_answer_mentions"], "dimension": m["dimension"],
                "source": {"type": "rule", "rule_id": m["rule_id"], "fact_id": None, "instances": 0},
                "citations": [], "anchors": [],
                "why_selected": "always asked: the student's stated plan is checked in the next round"}
        if i == 0:
            picked.append(item)
        else:
            reasons_not[m["rule_id"]] = "only one always-asked question per round"

    order = {d: i for i, d in enumerate(QUESTION_ORDER)}
    picked.sort(key=lambda q: (q["source"].get("fact_id") is None and q["source"]["type"] == "rule",
                               order.get(q["dimension"], 9)))
    questions = []
    for i, q in enumerate(picked, 1):
        q = {k: v for k, v in q.items() if k not in ("key", "anchors")}
        questions.append({"id": f"Q{i}", **q})

    not_selected = [{"id": k, "reason": v} for k, v in reasons_not.items()
                    if k not in {q["source"].get("rule_id") or q["source"].get("proposal_id") for q in questions}]
    not_triggered = [{"rule_id": m["rule_id"], "reason": m.get("note", "")} for m in rule_matches if not m["triggered"]]
    mode = "rules + model" if verified.get("status") == "ok" else f"rules-only ({verified.get('reason') or verified.get('status')})"
    return {"round": round_no, "seed": seed, "max_questions": max_questions, "mode": mode,
            "questions": questions, "not_selected": not_selected, "not_triggered": not_triggered,
            "dimensions": list(DIMENSIONS)}
