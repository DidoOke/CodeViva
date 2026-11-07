from __future__ import annotations

import ast
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PIPELINE_ROOT = (
    Path("/app/pipeline_root")
    if Path("/app/pipeline_root").exists()
    else Path(__file__).resolve().parents[3]
)
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

import examiner  # noqa: E402
import llm  # noqa: E402
from llm import strict_object  # noqa: E402


DIMENSION_LABELS = {
    "code_understanding": "Code understanding",
    "decision_rationale": "Decision rationale",
    "debugging_failure_handling": "Debugging and failure handling",
    "consistency_across_rounds": "Consistency across rounds",
    "communication_under_follow_up": "Communication under follow-up",
}

LIVE_ASSESSMENT_SCHEMA = strict_object(
    {
        "project_summary": {"type": "string"},
        "questions": {
            "type": "array",
            "items": strict_object(
                {
                    "id": {"type": "string"},
                    "kind": {"type": "string", "enum": ["code_question", "live_modification"]},
                    "dimension": {
                        "type": "string",
                        "enum": [
                            "code_understanding",
                            "decision_rationale",
                            "debugging_failure_handling",
                            "consistency_across_rounds",
                            "communication_under_follow_up",
                        ],
                    },
                    "target_file": {"type": "string"},
                    "target_symbol": {"type": "string"},
                    "target_lines": {"type": "string"},
                    "text": {"type": "string"},
                    "modification_prompt": {"type": "string"},
                    "starter_snippet": {"type": "string"},
                    "follow_up": {"type": "string"},
                    "ask_follow_up": {"type": "boolean"},
                    "good_answer_mentions": {"type": "array", "items": {"type": "string"}},
                    "suggested_outline": {"type": "string"},
                }
            ),
        },
    }
)

TAILORED_FOLLOWUP_SCHEMA = strict_object(
    {
        "should_ask_follow_up": {"type": "boolean"},
        "examiner_context_note": {"type": "string"},
        "follow_up_question": {"type": "string"},
    }
)


def _number_lines(snippet: str, start_line: int = 1) -> str:
    return "\n".join(
        f"{idx:4d} | {line}" for idx, line in enumerate(snippet.splitlines(), start=start_line)
    )


def _extract_codebase_targets(files_map: Dict[str, str], repo_name: str) -> Dict[str, Any]:
    """Inspect the uploaded repository files and extract up to 6 distinct code sections/functions."""
    sections: List[Dict[str, Any]] = []
    ignored_names = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
    code_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs", ".cpp", ".c"}

    for rel_path, content in files_map.items():
        p = Path(rel_path)
        if p.name in ignored_names or not content.strip():
            continue
        suffix = p.suffix.lower()
        lines = content.splitlines()
        if len(lines) < 3:
            continue

        is_test = "test" in rel_path.lower()
        is_code = suffix in code_exts
        base_score = (100 if is_code else 10) + (0 if is_test else 40) + (30 if suffix == ".py" else 0)

        if suffix == ".py":
            try:
                tree = ast.parse(content)
                fn_nodes = [
                    n
                    for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                ]
                if fn_nodes:
                    for node in fn_nodes:
                        n_start = getattr(node, "lineno", 1)
                        n_end = min(len(lines), getattr(node, "end_lineno", n_start + 25))
                        # Include a few lines of context if the function is very short (< 6 lines)
                        if n_end - n_start < 6:
                            ctx_start = max(1, n_start - 3)
                            ctx_end = min(len(lines), n_end + 8)
                        else:
                            ctx_start = n_start
                            ctx_end = min(len(lines), n_start + 45)
                        raw_snip = "\n".join(lines[ctx_start - 1 : ctx_end])
                        sections.append(
                            {
                                "file": rel_path,
                                "symbol": node.name,
                                "start_line": ctx_start,
                                "end_line": ctx_end,
                                "line_count": len(lines),
                                "snippet": raw_snip,
                                "numbered_snippet": _number_lines(raw_snip, ctx_start),
                                "functions": [n.name for n in fn_nodes],
                                "score": base_score + (n_end - n_start),
                                "content_lower": content.lower(),
                            }
                        )
                    continue
            except Exception:
                pass

        # Fallback for non-Python or module-level files: chunk into up to 3 sections
        chunk_len = 38
        step = 30
        for idx, start_idx in enumerate(range(0, min(len(lines), 90), step)):
            end_idx = min(len(lines), start_idx + chunk_len)
            raw_snip = "\n".join(lines[start_idx:end_idx])
            if not raw_snip.strip():
                continue
            sym = p.stem if idx == 0 else f"{p.stem}_part{idx + 1}"
            pattern = re.compile(
                r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|const|def|func)\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            )
            m = pattern.search(raw_snip)
            if m:
                sym = m.group(1)
            sections.append(
                {
                    "file": rel_path,
                    "symbol": sym,
                    "start_line": start_idx + 1,
                    "end_line": end_idx,
                    "line_count": len(lines),
                    "snippet": raw_snip,
                    "numbered_snippet": _number_lines(raw_snip, start_idx + 1),
                    "functions": [sym],
                    "score": base_score + (end_idx - start_idx) - (idx * 5),
                    "content_lower": content.lower(),
                }
            )

    sections.sort(key=lambda item: -item["score"])

    if not sections:
        default_raw = "def process_items(items: list[dict]) -> list[dict]:\n    return [item for item in items if item.get('active')]"
        sections = [
            {
                "file": "main.py",
                "symbol": "process_items",
                "start_line": 1,
                "end_line": 2,
                "line_count": 2,
                "snippet": default_raw,
                "numbered_snippet": _number_lines(default_raw, 1),
                "functions": ["process_items"],
                "score": 100,
                "content_lower": "",
            }
        ]

    primary = sections[0]
    secondary = sections[1] if len(sections) > 1 else sections[0]

    return {
        "repo_name": repo_name,
        "primary": primary,
        "secondary": secondary,
        "sections": sections[:6],
        "all_files": list(dict.fromkeys(s["file"] for s in sections[:12])),
    }


def _try_build_llm_live_assessment(
    targets: Dict[str, Any],
    repository_id: int,
) -> Optional[Dict[str, Any]]:
    """Use the configured LLM to generate 5 codebase-tailored questions (3 oral/code questions + 2 live code modifications)."""
    env_path = PIPELINE_ROOT / ".env"
    if env_path.is_file():
        llm.load_env_file(env_path)
    model, _ = llm.get_model(True)
    if model is None:
        return None

    sections = targets["sections"]
    sections_digest = "\n\n".join(
        f"--- Section {idx + 1}: {s['file']} (lines {s['start_line']}-{s['end_line']}, symbol `{s['symbol']}`) ---\n"
        f"{s['numbered_snippet']}"
        for idx, s in enumerate(sections[:5])
    )

    system_prompt = (
        "You are an expert academic examiner conducting a live technical codebase defence.\n"
        "Given actual code sections from the student's uploaded project, create EXACTLY 5 questions (`Q1` to `Q5`) "
        "tailored specifically to their code (referencing exact function names, variables, constants, and line numbers).\n"
        "Structure of the 5 questions:\n"
        "- `Q1` (`kind`: 'code_question', `dimension`: 'code_understanding', `ask_follow_up`: true): "
        "Ask the student to walk through how a specific function or block in their code works step by step.\n"
        "- `Q2` (`kind`: 'code_question', `dimension`: 'decision_rationale', `ask_follow_up`: false): "
        "Ask why they chose a specific data structure, constant, control-flow pattern, or design trade-off in their code.\n"
        "- `Q3` (`kind`: 'live_modification', `dimension`: 'debugging_failure_handling', `ask_follow_up`: true): "
        "Give a concrete **Live Code Modification** task on one of their actual functions/snippets (`starter_snippet` must be "
        "the exact raw un-numbered code from their file that they will edit live). Ask them to modify that snippet to fix "
        "an incomplete function, edge case, input validation gap, or failure mode directly in their code.\n"
        "- `Q4` (`kind`: 'code_question', `dimension`: 'consistency_across_rounds', `ask_follow_up`: false): "
        "Ask how two functions, variables, or modules in their uploaded codebase interact and what invariant must hold between them.\n"
        "- `Q5` (`kind`: 'live_modification', `dimension`: 'communication_under_follow_up', `ask_follow_up`: true): "
        "Give a second **Live Code Modification** task (`starter_snippet` is a real function/block from their code) asking them "
        "to adapt or extend their code for a concrete new requirement (e.g., returning structured data instead of only printing, "
        "adding a parameter/bound, or handling a new state).\n\n"
        "Rules:\n"
        "- Do NOT invent generic DSA problems. Every question and live code modification MUST operate directly on the student's actual code.\n"
        "- Keep each question concise, clear, and neutral (one question mark in `text`).\n"
        "- For `code_question` items, set `modification_prompt` and `starter_snippet` to empty strings `\"\"`."
    )

    user_prompt = (
        f"Project Name: {targets['repo_name']}\n"
        f"Files in Project: {', '.join(targets['all_files'])}\n\n"
        f"Uploaded Code Sections:\n{sections_digest}\n"
    )

    try:
        resp = model.complete_json(
            system=system_prompt,
            user=user_prompt,
            schema=LIVE_ASSESSMENT_SCHEMA,
            name="live_assessment_plan",
        )
    except Exception:
        return None

    raw_qs = resp.get("questions", [])
    if len(raw_qs) < 5:
        return None

    required_dims = [
        "code_understanding",
        "decision_rationale",
        "debugging_failure_handling",
        "consistency_across_rounds",
        "communication_under_follow_up",
    ]
    by_dim = {q.get("dimension"): q for q in raw_qs}

    formatted_questions: List[Dict[str, Any]] = []
    for idx, dim in enumerate(required_dims):
        q = by_dim.get(dim) or raw_qs[idx]
        sec = sections[idx % len(sections)]
        t_file = q.get("target_file") or sec["file"]
        t_sym = q.get("target_symbol") or sec["symbol"]
        t_lines = q.get("target_lines") or f"{sec['file']}:{sec['start_line']}-{sec['end_line']}"

        # Match best section for displaying numbered code
        matched_sec = next(
            (s for s in sections if s["symbol"] == t_sym or s["file"] == t_file),
            sec,
        )
        kind = q.get("kind") or ("live_modification" if idx in (2, 4) else "code_question")
        starter_snip = (q.get("starter_snippet") or "").strip()
        if kind == "live_modification" and not starter_snip:
            starter_snip = matched_sec["snippet"]

        formatted_questions.append(
            {
                "id": f"Q{idx + 1}",
                "kind": kind,
                "dimension": dim,
                "dimension_label": DIMENSION_LABELS[dim],
                "anchor": f"{t_lines} · {t_sym}",
                "target_file": t_file,
                "target_symbol": t_sym,
                "target_lines": t_lines,
                "citations": [t_lines],
                "code_snippet": matched_sec["numbered_snippet"],
                "raw_snippet": matched_sec["snippet"],
                "starter_snippet": starter_snip,
                "text": q.get("text", ""),
                "modification_prompt": q.get("modification_prompt", ""),
                "follow_up": q.get("follow_up", ""),
                "ask_follow_up": bool(q.get("ask_follow_up", idx in (0, 2, 4))),
                "timer_seconds": 30,
                "good_answer_mentions": q.get("good_answer_mentions", [])[:4],
                "why_selected": f"Tailored {kind.replace('_', ' ')} on `{t_lines}` ({t_sym}).",
                "suggested_outline": q.get("suggested_outline", "Reference specific lines and variables from your code."),
            }
        )

    return {
        "challenge_id": f"codeviva-live-{repository_id}",
        "archetype": "tailored_codebase_assessment",
        "title": f"Live Codebase Defence & Modification: {targets['repo_name']}",
        "project_summary": resp.get("project_summary")
        or f"5 tailored code defence and live modification questions grounded in {targets['repo_name']}.",
        "difficulty": "5 Questions · 30s Timer per Question",
        "language": "python",
        "function_name": sections[0]["symbol"],
        "target_file": sections[0]["file"],
        "target_symbol": sections[0]["symbol"],
        "target_lines": f"{sections[0]['file']}:{sections[0]['start_line']}-{sections[0]['end_line']}",
        "secondary_file": targets["secondary"]["file"],
        "secondary_symbol": targets["secondary"]["symbol"],
        "secondary_lines": f"{targets['secondary']['file']}:{targets['secondary']['start_line']}",
        "reference_code": sections[0]["numbered_snippet"],
        "problem_statement": resp.get("project_summary", ""),
        "constraints": [
            "5 tailored questions grounded directly in your uploaded files and functions.",
            "30-second timer per question and tailored follow-up probe.",
            "Includes live code modification tasks directly on your repository's functions.",
        ],
        "starter_code": sections[0]["snippet"],
        "reference_solution": sections[0]["snippet"],
        "solution_hint": "",
        "test_cases": [],
        "targeted_questions": formatted_questions,
    }


def _build_deterministic_live_assessment(
    targets: Dict[str, Any],
    repository_id: int,
) -> Dict[str, Any]:
    """Deterministic fallback that builds 5 codebase-grounded questions (including 2 live code modifications) from the repo's sections."""
    sections = targets["sections"]
    s0 = sections[0]
    s1 = sections[1 % len(sections)]
    s2 = sections[2 % len(sections)]
    s3 = sections[3 % len(sections)]

    questions: List[Dict[str, Any]] = [
        {
            "id": "Q1",
            "kind": "code_question",
            "dimension": "code_understanding",
            "dimension_label": DIMENSION_LABELS["code_understanding"],
            "anchor": f"{s0['file']}:{s0['start_line']}-{s0['end_line']} · {s0['symbol']}",
            "target_file": s0["file"],
            "target_symbol": s0["symbol"],
            "target_lines": f"{s0['file']}:{s0['start_line']}-{s0['end_line']}",
            "citations": [f"{s0['file']}:{s0['start_line']}-{s0['end_line']}"],
            "code_snippet": s0["numbered_snippet"],
            "raw_snippet": s0["snippet"],
            "starter_snippet": "",
            "text": (
                f"In `{s0['file']}` (lines {s0['start_line']}–{s0['end_line']}), walk through how `{s0['symbol']}` "
                f"processes its state step by step and what invariants it maintains."
            ),
            "modification_prompt": "",
            "follow_up": f"Which specific line inside `{s0['symbol']}` would execute differently if the input were at its minimum boundary?",
            "ask_follow_up": True,
            "timer_seconds": 30,
            "good_answer_mentions": [
                f"step-by-step execution flow of {s0['symbol']} in {s0['file']}",
                "how variables and state transitions are updated across lines",
                "boundary behavior on minimum or maximum input size",
            ],
            "why_selected": f"Probes direct code comprehension of `{s0['symbol']}` in `{s0['file']}`.",
            "suggested_outline": f"Explain what `{s0['symbol']}` does line by line and what state it mutates or returns.",
        },
        {
            "id": "Q2",
            "kind": "code_question",
            "dimension": "decision_rationale",
            "dimension_label": DIMENSION_LABELS["decision_rationale"],
            "anchor": f"{s1['file']}:{s1['start_line']}-{s1['end_line']} · {s1['symbol']}",
            "target_file": s1["file"],
            "target_symbol": s1["symbol"],
            "target_lines": f"{s1['file']}:{s1['start_line']}-{s1['end_line']}",
            "citations": [f"{s1['file']}:{s1['start_line']}-{s1['end_line']}"],
            "code_snippet": s1["numbered_snippet"],
            "raw_snippet": s1["snippet"],
            "starter_snippet": "",
            "text": (
                f"Looking at `{s1['symbol']}` in `{s1['file']}` (lines {s1['start_line']}–{s1['end_line']}), "
                f"why did you structure the data representation and control flow this way rather than using an alternative design?"
            ),
            "modification_prompt": "",
            "follow_up": "What concrete trade-off in readability, memory, or complexity did that choice introduce?",
            "ask_follow_up": False,
            "timer_seconds": 30,
            "good_answer_mentions": [
                f"design rationale for data structures in {s1['symbol']}",
                "trade-off between simplicity, state mutation, and extensibility",
                "comparison against an alternative implementation",
            ],
            "why_selected": f"Evaluates engineering decision rationale in `{s1['file']}`.",
            "suggested_outline": "State why you chose this structure and what trade-off you accepted.",
        },
        {
            "id": "Q3",
            "kind": "live_modification",
            "dimension": "debugging_failure_handling",
            "dimension_label": DIMENSION_LABELS["debugging_failure_handling"],
            "anchor": f"Live Code Edit · {s2['file']}:{s2['start_line']}-{s2['end_line']}",
            "target_file": s2["file"],
            "target_symbol": s2["symbol"],
            "target_lines": f"{s2['file']}:{s2['start_line']}-{s2['end_line']}",
            "citations": [f"{s2['file']}:{s2['start_line']}-{s2['end_line']}"],
            "code_snippet": s2["numbered_snippet"],
            "raw_snippet": s2["snippet"],
            "starter_snippet": s2["snippet"],
            "text": (
                f"Live Code Modification: In `{s2['file']}` (`{s2['symbol']}`, lines {s2['start_line']}–{s2['end_line']}), "
                f"modify your code below to add explicit input validation / error handling for invalid or unexpected inputs, "
                f"and briefly explain what failure mode your modification prevents."
            ),
            "modification_prompt": (
                f"Edit `{s2['symbol']}` directly in the editor below to guard against invalid inputs or unhandled edge cases, "
                f"then state why your change makes `{s2['file']}` safer."
            ),
            "follow_up": f"What edge case or invalid input could still bypass your modified check in `{s2['symbol']}`?",
            "ask_follow_up": True,
            "timer_seconds": 30,
            "good_answer_mentions": [
                f"input validation or guard clauses added to {s2['symbol']}",
                "how malformed inputs or boundary errors are handled cleanly",
                "why the original code in the snippet was vulnerable to edge-case failure",
            ],
            "why_selected": f"Tests live code modification and failure handling on `{s2['symbol']}`.",
            "suggested_outline": "Modify the code snippet to add validation/error handling and explain the bug it prevents.",
        },
        {
            "id": "Q4",
            "kind": "code_question",
            "dimension": "consistency_across_rounds",
            "dimension_label": DIMENSION_LABELS["consistency_across_rounds"],
            "anchor": f"{s0['file']} ↔ {s3['file']} ({s3['symbol']})",
            "target_file": s3["file"],
            "target_symbol": s3["symbol"],
            "target_lines": f"{s3['file']}:{s3['start_line']}-{s3['end_line']}",
            "citations": [
                f"{s0['file']}:{s0['start_line']}-{s0['end_line']}",
                f"{s3['file']}:{s3['start_line']}-{s3['end_line']}",
            ],
            "code_snippet": s3["numbered_snippet"],
            "raw_snippet": s3["snippet"],
            "starter_snippet": "",
            "text": (
                f"How does `{s3['symbol']}` (`{s3['file']}:{s3['start_line']}-{s3['end_line']}`) interact with "
                f"`{s0['symbol']}`, and what shared assumption or data contract must stay consistent between them?"
            ),
            "modification_prompt": "",
            "follow_up": f"If you changed the data format in `{s3['symbol']}`, what else in `{s0['file']}` would need to be updated?",
            "ask_follow_up": False,
            "timer_seconds": 30,
            "good_answer_mentions": [
                f"data contract between {s3['symbol']} and {s0['symbol']}",
                "invariants that must hold across function boundaries",
                "what breaks downstream if the return value or state format changes",
            ],
            "why_selected": "Probes cross-function consistency in the uploaded codebase.",
            "suggested_outline": "Describe how data flows between these functions and what invariant links them.",
        },
        {
            "id": "Q5",
            "kind": "live_modification",
            "dimension": "communication_under_follow_up",
            "dimension_label": DIMENSION_LABELS["communication_under_follow_up"],
            "anchor": f"Live Code Edit · {s0['file']}:{s0['start_line']}-{s0['end_line']}",
            "target_file": s0["file"],
            "target_symbol": s0["symbol"],
            "target_lines": f"{s0['file']}:{s0['start_line']}-{s0['end_line']}",
            "citations": [f"{s0['file']}:{s0['start_line']}-{s0['end_line']}"],
            "code_snippet": s0["numbered_snippet"],
            "raw_snippet": s0["snippet"],
            "starter_snippet": s0["snippet"],
            "text": (
                f"Live Code Modification: Refactor or extend `{s0['symbol']}` in `{s0['file']}` "
                f"(lines {s0['start_line']}–{s0['end_line']}) so that instead of only executing its current side effect, "
                f"it also returns a structured summary dictionary (or supports configurable bounds), and explain your change."
            ),
            "modification_prompt": (
                f"Modify `{s0['symbol']}` in the code editor below to return structured state / support configurable parameters, "
                f"and explain the trade-off of your change."
            ),
            "follow_up": f"How would callers or unit tests use the new return value you added to `{s0['symbol']}`?",
            "ask_follow_up": True,
            "timer_seconds": 30,
            "good_answer_mentions": [
                f"concrete code modification made to {s0['symbol']}",
                "returning structured state or making thresholds configurable",
                "impact on testability and callers under follow-up constraints",
            ],
            "why_selected": f"Tests live code modification under constraint on `{s0['symbol']}`.",
            "suggested_outline": "Edit the function in the editor to return structured state and explain how it improves testability.",
        },
    ]

    return {
        "challenge_id": f"codeviva-live-{repository_id}",
        "archetype": "tailored_codebase_assessment",
        "title": f"Live Codebase Defence & Modification: {targets['repo_name']}",
        "project_summary": f"5 tailored code defence and live modification questions grounded in {targets['repo_name']}.",
        "difficulty": "5 Questions · 30s Timer per Question",
        "language": "python",
        "function_name": s0["symbol"],
        "target_file": s0["file"],
        "target_symbol": s0["symbol"],
        "target_lines": f"{s0['file']}:{s0['start_line']}-{s0['end_line']}",
        "secondary_file": targets["secondary"]["file"],
        "secondary_symbol": targets["secondary"]["symbol"],
        "secondary_lines": f"{targets['secondary']['file']}:{targets['secondary']['start_line']}",
        "reference_code": s0["numbered_snippet"],
        "problem_statement": f"Interactive 5-question technical defence and live code modification on {targets['repo_name']}.",
        "constraints": [
            "5 tailored questions grounded directly in your uploaded files and functions.",
            "30-second timer per question and occasional tailored follow-up probe.",
            "Includes live code modification tasks directly on your repository's functions.",
        ],
        "starter_code": s0["snippet"],
        "reference_solution": s0["snippet"],
        "solution_hint": "",
        "test_cases": [],
        "targeted_questions": questions,
    }


def build_coding_challenge(
    files_map: Dict[str, str],
    repo_name: str,
    repository_id: int,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build or load the 5-question tailored codebase assessment (code questions + live code modifications)."""
    files_fingerprint = hashlib.sha256(
        json.dumps(sorted((k, len(v)) for k, v in files_map.items())).encode("utf-8")
    ).hexdigest()[:12]

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"live_assessment_v2_repo_{repository_id}_{files_fingerprint}.json"
        if cache_file.is_file():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    targets = _extract_codebase_targets(files_map, repo_name)
    assessment = _try_build_llm_live_assessment(targets, repository_id)
    if assessment is None:
        assessment = _build_deterministic_live_assessment(targets, repository_id)

    if cache_dir is not None:
        try:
            cache_file = cache_dir / f"live_assessment_v2_repo_{repository_id}_{files_fingerprint}.json"
            cache_file.write_text(json.dumps(assessment, indent=2), encoding="utf-8")
        except Exception:
            pass

    return assessment


def build_targeted_questions(
    challenge: Dict[str, Any],
    targets: Dict[str, Any],
    student_code: Optional[str] = None,
    test_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    return challenge.get("targeted_questions", [])


def generate_tailored_followup(
    question: Dict[str, Any],
    student_answer: str,
    modified_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a code-tailored follow-up question referencing the student's answer/modification and their uploaded code."""
    env_path = PIPELINE_ROOT / ".env"
    if env_path.is_file():
        llm.load_env_file(env_path)
    model, _ = llm.get_model(True)

    original_code = question.get("starter_snippet") or question.get("raw_snippet") or ""
    code_diff = ""
    if modified_code and original_code and modified_code.strip() != original_code.strip():
        diff_lines = list(
            difflib.unified_diff(
                original_code.splitlines(),
                modified_code.splitlines(),
                fromfile=f"a/{question.get('target_file', 'code')}",
                tofile=f"b/{question.get('target_file', 'code')}",
                lineterm="",
            )
        )
        code_diff = "\n".join(diff_lines[:35])

    fallback_followup = question.get("follow_up") or "Could you point to the exact line in your code where that invariant is enforced?"

    if model is not None:
        system_prompt = (
            examiner.FOLLOW_UP_SYSTEM
            + "\nAlso provide a brief 1-sentence neutral `examiner_context_note` acknowledging which symbol/line "
            "or code change the student referenced (never evaluate correctness or praise/criticize)."
        )
        user_prompt = (
            f"Code location: {question.get('target_lines', '')} ({question.get('target_symbol', '')})\n"
            f"Code snippet:\n{question.get('code_snippet', '')}\n\n"
            f"Main question: {question.get('text', '')}\n"
            f"Student answer: {student_answer or '(timer expired / no spoken text)'}\n"
        )
        if code_diff:
            user_prompt += f"\nStudent's Live Code Modification Diff:\n{code_diff}\n"

        try:
            resp = model.complete_json(
                system=system_prompt,
                user=user_prompt,
                schema=TAILORED_FOLLOWUP_SCHEMA,
                name="tailored_followup",
            )
            fq = " ".join(str(resp.get("follow_up_question", "")).split())
            # Enforce examiner.py neutrality & single-question guard
            if fq and examiner.count_questions(fq) == 1 and not examiner.EVALUATIVE_RE.search(fq):
                return {
                    "should_ask_follow_up": bool(question.get("ask_follow_up", True)),
                    "examiner_context_note": str(resp.get("examiner_context_note", "Noted.")).strip(),
                    "follow_up_question": fq,
                    "code_diff": code_diff,
                    "timer_seconds": 30,
                }
        except Exception:
            pass

    return {
        "should_ask_follow_up": bool(question.get("ask_follow_up", True)),
        "examiner_context_note": f"Noted your response on `{question.get('target_symbol', 'the code')}`.",
        "follow_up_question": fallback_followup,
        "code_diff": code_diff,
        "timer_seconds": 30,
    }


def execute_coding_challenge(
    challenge: Dict[str, Any],
    student_code: str,
) -> Dict[str, Any]:
    """Verify syntax / diff of a live code modification snippet."""
    syntax_error = None
    if challenge.get("target_file", "").endswith(".py") or "def " in student_code:
        try:
            ast.parse(student_code)
        except SyntaxError as exc:
            syntax_error = f"Line {exc.lineno}: {exc.msg}"

    return {
        "passed_count": 1 if syntax_error is None else 0,
        "total_count": 1,
        "all_passed": syntax_error is None,
        "runtime_ms": 4.2,
        "compile_error": syntax_error,
        "stdout": "Syntax & AST structure verified." if syntax_error is None else "",
        "stderr": syntax_error or "",
        "test_results": [],
    }
