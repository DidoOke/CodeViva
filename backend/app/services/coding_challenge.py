from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PIPELINE_ROOT = (
    Path("/app/pipeline_root")
    if Path("/app/pipeline_root").exists()
    else Path(__file__).resolve().parents[3]
)
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

import llm  # noqa: E402
from llm import strict_object  # noqa: E402


LLM_CHALLENGE_SCHEMA = strict_object(
    {
        "title": {"type": "string"},
        "function_name": {"type": "string"},
        "problem_statement": {"type": "string"},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "starter_code": {"type": "string"},
        "reference_solution": {"type": "string"},
        "solution_hint": {"type": "string"},
        "test_cases": {
            "type": "array",
            "items": strict_object(
                {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "args_json": {"type": "string"},
                    "is_hidden": {"type": "boolean"},
                }
            ),
        },
        "targeted_questions": {
            "type": "array",
            "items": strict_object(
                {
                    "id": {"type": "string"},
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
                    "anchor": {"type": "string"},
                    "text": {"type": "string"},
                    "follow_up": {"type": "string"},
                    "good_answer_mentions": {"type": "array", "items": {"type": "string"}},
                    "suggested_outline": {"type": "string"},
                }
            ),
        },
    }
)

DIMENSION_LABELS = {
    "code_understanding": "Code understanding",
    "decision_rationale": "Decision rationale",
    "debugging_failure_handling": "Debugging and failure handling",
    "consistency_across_rounds": "Consistency across rounds",
    "communication_under_follow_up": "Communication under follow-up",
}


def _extract_codebase_targets(files_map: Dict[str, str], repo_name: str) -> Dict[str, Any]:
    """Inspect the uploaded repository files and extract primary & secondary code targets."""
    source_candidates: List[Dict[str, Any]] = []

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

        symbol_name = p.stem
        start_line = 1
        end_line = min(len(lines), 65)
        snippet = "\n".join(lines[:end_line])
        functions_found: List[str] = []

        if suffix == ".py":
            try:
                tree = ast.parse(content)
                best_node: Optional[ast.AST] = None
                best_len = 0
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        functions_found.append(node.name)
                        node_start = getattr(node, "lineno", 1)
                        node_end = getattr(node, "end_lineno", min(len(lines), node_start + 35))
                        span = node_end - node_start
                        if span > best_len and not node.name.startswith("__"):
                            best_len = span
                            best_node = node
                if best_node is not None:
                    symbol_name = getattr(best_node, "name", p.stem)
                    # Include top-level constants/helpers if file is short (< 90 lines)
                    if len(lines) <= 90:
                        start_line = 1
                        end_line = len(lines)
                    else:
                        start_line = getattr(best_node, "lineno", 1)
                        end_line = min(len(lines), getattr(best_node, "end_lineno", start_line + 40), start_line + 50)
                    snippet = "\n".join(lines[start_line - 1 : end_line])
            except Exception:
                pass
        elif suffix in {".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs"}:
            pattern = re.compile(
                r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|const|def|func)\s+([A-Za-z_][A-Za-z0-9_]*)",
                re.MULTILINE,
            )
            for match in pattern.finditer(content):
                fn_name = match.group(1)
                functions_found.append(fn_name)
                line_no = content[: match.start()].count("\n") + 1
                if start_line == 1:
                    symbol_name = fn_name
                    start_line = line_no
                    end_line = min(len(lines), start_line + 42)
                    snippet = "\n".join(lines[start_line - 1 : end_line])

        score = (100 if is_code else 10) + (0 if is_test else 40) + min(len(lines), 200)
        if suffix == ".py":
            score += 30

        numbered_snippet = "\n".join(
            f"{idx:4d} | {line}" for idx, line in enumerate(snippet.splitlines(), start=start_line)
        )

        source_candidates.append(
            {
                "file": rel_path,
                "symbol": symbol_name,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": len(lines),
                "snippet": snippet,
                "numbered_snippet": numbered_snippet,
                "functions": functions_found[:10],
                "score": score,
                "content_lower": content.lower(),
            }
        )

    source_candidates.sort(key=lambda item: -item["score"])

    if not source_candidates:
        default_snippet = "   1 | def process_items(items: list[dict]) -> list[dict]:\n   2 |     return [item for item in items if item.get('active')]"
        primary = {
            "file": "main.py",
            "symbol": "process_items",
            "start_line": 1,
            "end_line": 2,
            "line_count": 2,
            "snippet": default_snippet,
            "numbered_snippet": default_snippet,
            "functions": ["process_items"],
            "content_lower": "",
        }
        secondary = primary
    else:
        primary = source_candidates[0]
        secondary = source_candidates[1] if len(source_candidates) > 1 else source_candidates[0]

    return {
        "repo_name": repo_name,
        "primary": primary,
        "secondary": secondary,
        "all_files": [c["file"] for c in source_candidates[:12]],
    }


def _select_archetype(targets: Dict[str, Any]) -> str:
    combined = " ".join(
        [
            targets["primary"]["file"].lower(),
            targets["primary"]["symbol"].lower(),
            targets["primary"]["content_lower"][:4000],
            targets["secondary"]["file"].lower(),
        ]
    )
    if any(k in combined for k in ("holdem", "poker", "suits", "ranks", "create_deck", "flop", "river")):
        return "holdem_dealer"
    if any(k in combined for k in ("heapq", "schedule", "backoff", "retry", "task", "queue", "worker")):
        return "scheduler_backoff"
    if any(k in combined for k in ("quote", "verbatim", "transcript", "rubric", "grade", "examiner", "verify")):
        return "quote_verifier"
    return "sliding_chunker"


def _try_build_llm_challenge(
    targets: Dict[str, Any],
    repository_id: int,
) -> Optional[Dict[str, Any]]:
    """Attempt to synthesize a custom codebase-specific coding challenge via LLM and verify it in the sandbox."""
    env_path = PIPELINE_ROOT / ".env"
    if env_path.is_file():
        llm.load_env_file(env_path)
    model, _ = llm.get_model(True)
    if model is None:
        return None

    primary = targets["primary"]
    secondary = targets["secondary"]
    p_file = primary["file"]
    p_sym = primary["symbol"]
    p_start = primary["start_line"]
    p_end = primary["end_line"]
    s_file = secondary["file"]
    s_sym = secondary["symbol"]
    s_start = secondary["start_line"]

    system_prompt = (
        "You are an expert computer science examiner designing a HackerRank-style Python coding exercise "
        "and 5 targeted oral/written defence questions directly based on a student's uploaded codebase.\n"
        "Rules:\n"
        "1. Design a self-contained, deterministic Python function (`function_name`) that directly extends, completes, "
        "or tests a core algorithm/feature from the student's code snippet (for example, if the code is a card game, "
        "implement deterministic dealing/burn-card state or hand/bet evaluation; if it is a scheduler, implement task dispatch; "
        "if it is a web/API service, implement payload validation or windowing).\n"
        "2. The function MUST be 100% pure and deterministic (no `input()`, no `random.shuffle()`, no network/disk I/O, "
        "only standard library types: lists, dicts, ints, strings, booleans).\n"
        "3. `starter_code` must include the function signature, helpful setup lines, and a `# TODO:` where the student "
        "writes the core logic (returning a placeholder or partial result initially).\n"
        "4. `reference_solution` must be a complete, syntactically valid, working Python implementation of `function_name`.\n"
        "5. Provide exactly 5 `test_cases` (`TC1` to `TC5`). For each test case, `args_json` MUST be a valid JSON array "
        "representing the positional arguments passed to `function_name(*json.loads(args_json))`.\n"
        "6. Provide exactly 5 `targeted_questions` (`Q1` to `Q5`), one for each of the 5 dimensions: "
        "`code_understanding`, `decision_rationale`, `debugging_failure_handling`, `consistency_across_rounds`, "
        "and `communication_under_follow_up`. Every question MUST reference specific function names, variables, or line numbers "
        f"from `{p_file}` (`{p_sym}`) AND the coding exercise function."
    )

    user_prompt = (
        f"Repository: {targets['repo_name']}\n"
        f"Primary File: {p_file} (lines {p_start}-{p_end}, symbol `{p_sym}`, functions: {primary['functions']})\n"
        f"Secondary File: {s_file} (line {s_start}, symbol `{s_sym}`)\n\n"
        f"Code from `{p_file}`:\n```python\n{primary['numbered_snippet']}\n```\n"
    )

    try:
        resp = model.complete_json(
            system=system_prompt,
            user=user_prompt,
            schema=LLM_CHALLENGE_SCHEMA,
            name="coding_challenge",
        )
    except Exception:
        return None

    fn_name = str(resp.get("function_name", "")).strip()
    ref_code = str(resp.get("reference_solution", "")).strip()
    starter_code = str(resp.get("starter_code", "")).strip()
    raw_tcs = resp.get("test_cases", [])
    raw_qs = resp.get("targeted_questions", [])

    if not fn_name or not ref_code or not starter_code or len(raw_tcs) < 3 or len(raw_qs) < 5:
        return None

    # Parse args_json and compute/verify expected outputs by running reference_solution in our sandbox!
    parsed_tcs: List[Dict[str, Any]] = []
    for idx, tc in enumerate(raw_tcs[:5]):
        try:
            args_val = json.loads(tc["args_json"])
            if not isinstance(args_val, list):
                args_val = [args_val]
        except Exception:
            return None
        parsed_tcs.append(
            {
                "id": f"TC{idx + 1}",
                "name": tc.get("name") or f"Test Case {idx + 1}",
                "category": tc.get("category") or ("Base Case" if idx == 0 else "Edge Case"),
                "args": args_val,
                "expected": None,
                "is_hidden": bool(tc.get("is_hidden", idx >= 3)),
            }
        )

    # Execute reference_solution on parsed_tcs to populate exact expected outputs and verify it runs cleanly
    compute_script = """
import json, sys
ref_code = sys.argv[1]
fn_name = sys.argv[2]
tcs = json.loads(sys.argv[3])
ns = {}
exec(compile(ref_code, "<ref>", "exec"), ns)
fn = ns.get(fn_name)
if not callable(fn):
    sys.exit(1)
out = []
for tc in tcs:
    args_copy = json.loads(json.dumps(tc["args"]))
    res = fn(*args_copy)
    out.append(res)
print(json.dumps({"ok": True, "expected_list": out}))
"""
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", compute_script, ref_code, fn_name, json.dumps(parsed_tcs)],
            capture_output=True,
            text=True,
            timeout=3.5,
        )
        if proc.returncode != 0:
            return None
        verified_out = json.loads(proc.stdout.strip())
        expected_list = verified_out["expected_list"]
        for tc, exp in zip(parsed_tcs, expected_list):
            tc["expected"] = exp
    except Exception:
        return None

    formatted_questions: List[Dict[str, Any]] = []
    required_dims = [
        "code_understanding",
        "decision_rationale",
        "debugging_failure_handling",
        "consistency_across_rounds",
        "communication_under_follow_up",
    ]
    by_dim = {q.get("dimension"): q for q in raw_qs}

    for idx, dim in enumerate(required_dims):
        q = by_dim.get(dim) or raw_qs[min(idx, len(raw_qs) - 1)]
        formatted_questions.append(
            {
                "id": f"Q{idx + 1}",
                "dimension": dim,
                "dimension_label": DIMENSION_LABELS[dim],
                "anchor": q.get("anchor") or f"{p_file}:{p_start}-{p_end} · {fn_name}()",
                "citations": [f"{p_file}:{p_start}-{p_end}", f"{fn_name}()"],
                "text": q.get("text", ""),
                "follow_up": q.get("follow_up", ""),
                "good_answer_mentions": q.get("good_answer_mentions", [])[:4],
                "why_selected": f"Directly probes {DIMENSION_LABELS[dim].lower()} on `{p_file}` and `{fn_name}()`.",
                "suggested_outline": q.get("suggested_outline", "Explain your implementation choices and edge cases."),
            }
        )

    return {
        "challenge_id": f"codeviva-hr-{repository_id}-llm",
        "archetype": "llm_custom_codebase",
        "title": resp.get("title") or f"Codebase Challenge: {p_sym} ({p_file})",
        "difficulty": "Medium · Codebase Defence",
        "language": "python",
        "function_name": fn_name,
        "target_file": p_file,
        "target_symbol": p_sym,
        "target_lines": f"{p_file}:{p_start}-{p_end}",
        "secondary_file": s_file,
        "secondary_symbol": s_sym,
        "secondary_lines": f"{s_file}:{s_start}",
        "reference_code": primary["numbered_snippet"],
        "problem_statement": resp.get("problem_statement", ""),
        "constraints": resp.get("constraints", []),
        "starter_code": starter_code,
        "reference_solution": ref_code,
        "solution_hint": resp.get("solution_hint", ""),
        "test_cases": parsed_tcs,
        "targeted_questions": formatted_questions,
    }


def build_coding_challenge(
    files_map: Dict[str, str],
    repo_name: str,
    repository_id: int,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build or load cached HackerRank-style coding exercise grounded in the uploaded codebase."""
    files_fingerprint = hashlib.sha256(
        json.dumps(sorted((k, len(v)) for k, v in files_map.items())).encode("utf-8")
    ).hexdigest()[:12]

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"challenge_repo_{repository_id}_{files_fingerprint}.json"
        if cache_file.is_file():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    targets = _extract_codebase_targets(files_map, repo_name)

    # First try LLM-synthesized custom codebase challenge (verified in Python sandbox)
    llm_challenge = _try_build_llm_challenge(targets, repository_id)
    if llm_challenge is not None:
        if cache_dir is not None:
            try:
                cache_file = cache_dir / f"challenge_repo_{repository_id}_{files_fingerprint}.json"
                cache_file.write_text(json.dumps(llm_challenge, indent=2), encoding="utf-8")
            except Exception:
                pass
        return llm_challenge

    # Deterministic codebase-matched archetypes (including Texas Hold'em, Scheduler, Verifier, Chunker)
    primary = targets["primary"]
    secondary = targets["secondary"]
    archetype = _select_archetype(targets)

    p_file = primary["file"]
    p_sym = primary["symbol"]
    p_start = primary["start_line"]
    p_end = primary["end_line"]
    s_file = secondary["file"]
    s_sym = secondary["symbol"]
    s_start = secondary["start_line"]

    if archetype == "holdem_dealer":
        ref_sol = (
            f"# Grounded in {p_file}:{p_start}-{p_end} ({p_sym})\n"
            "from typing import Any\n\n"
            "def deal_holdem_round(deck: list[str], num_players: int) -> dict[str, Any]:\n"
            '    """Deal Texas Hold\'em hole cards and community board with burn cards."""\n'
            "    if num_players < 2 or num_players > 9:\n"
            "        return {'error': 'invalid_player_count', 'players': {}, 'community': [], 'remaining': len(deck)}\n"
            "    required_cards = (2 * num_players) + 8\n"
            "    if len(deck) < required_cards:\n"
            "        return {'error': 'insufficient_deck', 'players': {}, 'community': [], 'remaining': len(deck)}\n\n"
            "    working = list(deck)\n"
            "    players: dict[str, list[str]] = {}\n"
            "    for i in range(1, num_players + 1):\n"
            "        c1 = working.pop()\n"
            "        c2 = working.pop()\n"
            "        players[f'Player {i}'] = [c1, c2]\n\n"
            "    # Burn 1, deal Flop (3)\n"
            "    working.pop()\n"
            "    flop = [working.pop(), working.pop(), working.pop()]\n"
            "    # Burn 1, deal Turn (1)\n"
            "    working.pop()\n"
            "    turn = working.pop()\n"
            "    # Burn 1, deal River (1)\n"
            "    working.pop()\n"
            "    river = working.pop()\n\n"
            "    return {\n"
            "        'error': None,\n"
            "        'players': players,\n"
            "        'community': flop + [turn, river],\n"
            "        'remaining': len(working),\n"
            "    }\n"
        )
        starter = (
            f"# Grounded in {p_file}:{p_start}-{p_end} ({p_sym})\n"
            "from typing import Any\n\n"
            "def deal_holdem_round(deck: list[str], num_players: int) -> dict[str, Any]:\n"
            '    """Deal Texas Hold\'em hole cards and community board with burn cards."""\n'
            "    # 1. Validate player count (2 <= num_players <= 9)\n"
            "    if num_players < 2 or num_players > 9:\n"
            "        return {'error': 'invalid_player_count', 'players': {}, 'community': [], 'remaining': len(deck)}\n\n"
            "    # 2. Check that deck has at least (2 * num_players) + 8 cards (5 community + 3 burn cards)\n"
            "    required_cards = (2 * num_players) + 8\n"
            "    if len(deck) < required_cards:\n"
            "        return {'error': 'insufficient_deck', 'players': {}, 'community': [], 'remaining': len(deck)}\n\n"
            "    working = list(deck)\n"
            "    players: dict[str, list[str]] = {}\n"
            "    for i in range(1, num_players + 1):\n"
            "        players[f'Player {i}'] = [working.pop(), working.pop()]\n\n"
            "    # TODO: Burn 1 card before Flop (3 cards), burn 1 before Turn (1 card), burn 1 before River (1 card)\n"
            "    working.pop()\n"
            "    flop = [working.pop(), working.pop(), working.pop()]\n"
            "    working.pop()\n"
            "    turn = working.pop()\n"
            "    working.pop()\n"
            "    river = working.pop()\n\n"
            "    return {\n"
            "        'error': None,\n"
            "        'players': players,\n"
            "        'community': flop + [turn, river],\n"
            "        'remaining': len(working),\n"
            "    }\n"
        )
        sample_deck_12 = [f"C{i}" for i in range(1, 13)]
        challenge = {
            "challenge_id": f"codeviva-hr-{repository_id}-holdem",
            "archetype": "holdem_dealer",
            "title": f"Texas Hold'em Deal & Burn-Card State Machine ({p_sym})",
            "difficulty": "Medium · Codebase Defence",
            "language": "python",
            "function_name": "deal_holdem_round",
            "target_file": p_file,
            "target_symbol": p_sym,
            "target_lines": f"{p_file}:{p_start}-{p_end}",
            "secondary_file": s_file,
            "secondary_symbol": s_sym,
            "secondary_lines": f"{s_file}:{s_start}",
            "reference_code": primary["numbered_snippet"],
            "problem_statement": (
                f"In your uploaded repository (`{p_file}`, lines {p_start}–{p_end} in `{p_sym}`), "
                f"hole cards and community cards are dealt by popping from `deck` with burn cards before the Flop, Turn, and River.\n\n"
                f"Write a deterministic function `deal_holdem_round(deck, num_players)` that returns the structured state of a deal:\n"
                "1. **Player Count Guard**: If `num_players < 2` or `num_players > 9`, return `{'error': 'invalid_player_count', 'players': {}, 'community': [], 'remaining': len(deck)}`.\n"
                "2. **Deck Exhaustion Guard**: Dealing requires `2 * num_players` hole cards + `3` burn cards + `5` community cards (`2 * num_players + 8`). If `len(deck) < 2 * num_players + 8`, return `{'error': 'insufficient_deck', 'players': {}, 'community': [], 'remaining': len(deck)}`.\n"
                "3. **Deal Sequence (Popping from End)**: Copy `deck` so the caller's list is not mutated. For `Player 1` .. `Player N`, pop 2 hole cards each. Then pop 1 burn card and 3 Flop cards, pop 1 burn card and 1 Turn card, and pop 1 burn card and 1 River card.\n"
                "4. **Output Format**: Return `{'error': None, 'players': players, 'community': flop + [turn, river], 'remaining': len(working)}`."
            ),
            "constraints": [
                "2 <= num_players <= 9 (mirroring line 19 of texasholdem.py).",
                "Must burn 1 card before Flop (3), 1 before Turn (1), and 1 before River (1).",
                "Must not mutate the input deck list passed by the caller.",
            ],
            "starter_code": starter,
            "reference_solution": ref_sol,
            "solution_hint": (
                "Check `num_players < 2 or num_players > 9` first, then check `len(deck) < 2 * num_players + 8`, "
                "and pop hole cards followed by burn+flop(3), burn+turn(1), burn+river(1)."
            ),
            "test_cases": [
                {
                    "id": "TC1",
                    "name": "2-Player Deal & Burn Sequence",
                    "category": "Base Case",
                    "args": [sample_deck_12, 2],
                    "expected": {
                        "error": None,
                        "players": {"Player 1": ["C12", "C11"], "Player 2": ["C10", "C9"]},
                        "community": ["C7", "C6", "C5", "C3", "C1"],
                        "remaining": 0,
                    },
                    "is_hidden": False,
                },
                {
                    "id": "TC2",
                    "name": "Reject < 2 Players (num_players = 1)",
                    "category": "Boundary",
                    "args": [sample_deck_12, 1],
                    "expected": {
                        "error": "invalid_player_count",
                        "players": {},
                        "community": [],
                        "remaining": 12,
                    },
                    "is_hidden": False,
                },
                {
                    "id": "TC3",
                    "name": "Reject > 9 Players (num_players = 10)",
                    "category": "Boundary",
                    "args": [[f"C{i}" for i in range(52)], 10],
                    "expected": {
                        "error": "invalid_player_count",
                        "players": {},
                        "community": [],
                        "remaining": 52,
                    },
                    "is_hidden": False,
                },
                {
                    "id": "TC4",
                    "name": "Insufficient Deck Guard",
                    "category": "Edge Case",
                    "args": [["A", "K", "Q", "J", "10"], 2],
                    "expected": {
                        "error": "insufficient_deck",
                        "players": {},
                        "community": [],
                        "remaining": 5,
                    },
                    "is_hidden": True,
                },
                {
                    "id": "TC5",
                    "name": "Full 52-Card Deck with 4 Players",
                    "category": "Invariant",
                    "args": [[f"Card-{i}" for i in range(1, 53)], 4],
                    "expected": {
                        "error": None,
                        "players": {
                            "Player 1": ["Card-52", "Card-51"],
                            "Player 2": ["Card-50", "Card-49"],
                            "Player 3": ["Card-48", "Card-47"],
                            "Player 4": ["Card-46", "Card-45"],
                        },
                        "community": ["Card-43", "Card-42", "Card-41", "Card-39", "Card-37"],
                        "remaining": 36,
                    },
                    "is_hidden": True,
                },
            ],
        }
    elif archetype == "scheduler_backoff":
        ref_sol = (
            f"# Grounded in {p_file}:{p_start}-{p_end} ({p_sym})\n"
            "from typing import Any\n\n"
            "def dispatch_ready_tasks(\n"
            "    tasks: list[dict[str, Any]],\n"
            "    max_retries: int = 3,\n"
            "    base_delay: int = 2,\n"
            ") -> list[dict[str, Any]]:\n"
            '    """Filter eligible tasks, compute exponential backoff, and order by (priority, seq)."""\n'
            "    eligible: list[tuple[int, int, dict[str, Any]]] = []\n"
            "    for idx, task in enumerate(tasks):\n"
            "        name = str(task.get('name', '')).strip()\n"
            "        retries = int(task.get('retries', 0))\n"
            "        if not name or retries > max_retries:\n"
            "            continue\n"
            "        priority = int(task.get('priority', 0))\n"
            "        seq = int(task.get('seq', idx))\n"
            "        backoff_seconds = base_delay * (2 ** retries)\n"
            "        eligible.append((priority, seq, {\n"
            "            'name': name,\n"
            "            'priority': priority,\n"
            "            'backoff_seconds': backoff_seconds,\n"
            "        }))\n\n"
            "    eligible.sort(key=lambda item: (item[0], item[1]))\n"
            "    return [item[2] for item in eligible]\n"
        )
        challenge = {
            "challenge_id": f"codeviva-hr-{repository_id}-scheduler",
            "archetype": "scheduler_backoff",
            "title": f"Priority Task Dispatch & Exponential Backoff ({p_sym})",
            "difficulty": "Medium · Codebase Defence",
            "language": "python",
            "function_name": "dispatch_ready_tasks",
            "target_file": p_file,
            "target_symbol": p_sym,
            "target_lines": f"{p_file}:{p_start}-{p_end}",
            "secondary_file": s_file,
            "secondary_symbol": s_sym,
            "secondary_lines": f"{s_file}:{s_start}",
            "reference_code": primary["numbered_snippet"],
            "problem_statement": (
                f"In your uploaded repository (`{p_file}`, lines {p_start}–{p_end} around `{p_sym}`), "
                f"task ordering and failure recovery govern how work items are dispatched.\n\n"
                f"Write a function `dispatch_ready_tasks(tasks, max_retries, base_delay)` that takes a list of task "
                f"dictionaries and returns the ordered dispatch plan for all eligible tasks:\n"
                f"1. **Filter Exhausted or Invalid Tasks**: Ignore any task whose `'retries'` strictly exceeds `max_retries`, "
                f"or whose `'name'` is empty/whitespace.\n"
                f"2. **Compute Exponential Backoff**: For each eligible task, compute `backoff_seconds = base_delay * (2 ** retries)` "
                f"(where `retries` defaults to `0` if omitted).\n"
                "3. **Deterministic Priority Ordering**: Sort eligible tasks by ascending `'priority'` (lower integer = higher urgency). "
                "Break ties by ascending `'seq'` (arrival sequence number).\n"
                "4. **Output Format**: Return a list of dictionaries `[{'name': str, 'priority': int, 'backoff_seconds': int}]` in dispatch order."
            ),
            "constraints": [
                "0 <= len(tasks) <= 10^4 — target O(N log N) time complexity.",
                "Tasks with retries > max_retries or blank/whitespace names must be excluded.",
                "Ties in priority must preserve deterministic FIFO order via the 'seq' field.",
            ],
            "starter_code": ref_sol,
            "reference_solution": ref_sol,
            "solution_hint": (
                "Filter out tasks where `not name` or `retries > max_retries`, calculate `base_delay * (2 ** retries)`, "
                "and sort by `(priority, seq)` so equal-priority tasks never starve."
            ),
            "test_cases": [
                {
                    "id": "TC1",
                    "name": "Base Priority & Backoff Ordering",
                    "category": "Base Case",
                    "args": [
                        [
                            {"name": "sync-db", "priority": 5, "retries": 1, "seq": 1},
                            {"name": "send-alert", "priority": 1, "retries": 0, "seq": 2},
                            {"name": "reindex", "priority": 3, "retries": 2, "seq": 3},
                        ],
                        3,
                        2,
                    ],
                    "expected": [
                        {"name": "send-alert", "priority": 1, "backoff_seconds": 2},
                        {"name": "reindex", "priority": 3, "backoff_seconds": 8},
                        {"name": "sync-db", "priority": 5, "backoff_seconds": 4},
                    ],
                    "is_hidden": False,
                },
                {
                    "id": "TC2",
                    "name": "Retry Limit Cutoff (retries > max_retries)",
                    "category": "Boundary",
                    "args": [
                        [
                            {"name": "poison-job", "priority": 0, "retries": 4, "seq": 1},
                            {"name": "borderline-job", "priority": 2, "retries": 3, "seq": 2},
                        ],
                        3,
                        2,
                    ],
                    "expected": [
                        {"name": "borderline-job", "priority": 2, "backoff_seconds": 16},
                    ],
                    "is_hidden": False,
                },
                {
                    "id": "TC3",
                    "name": "FIFO Tie-Breaking on Equal Priority",
                    "category": "Invariant",
                    "args": [
                        [
                            {"name": "worker-b", "priority": 2, "retries": 0, "seq": 10},
                            {"name": "worker-a", "priority": 2, "retries": 0, "seq": 4},
                            {"name": "worker-c", "priority": 2, "retries": 1, "seq": 7},
                        ],
                        3,
                        3,
                    ],
                    "expected": [
                        {"name": "worker-a", "priority": 2, "backoff_seconds": 3},
                        {"name": "worker-c", "priority": 2, "backoff_seconds": 6},
                        {"name": "worker-b", "priority": 2, "backoff_seconds": 3},
                    ],
                    "is_hidden": False,
                },
                {
                    "id": "TC4",
                    "name": "Blank Names & Empty Input Resilience",
                    "category": "Edge Case",
                    "args": [
                        [
                            {"name": "   ", "priority": 1, "retries": 0, "seq": 1},
                            {"name": "", "priority": 0, "retries": 0, "seq": 2},
                        ],
                        3,
                        2,
                    ],
                    "expected": [],
                    "is_hidden": True,
                },
                {
                    "id": "TC5",
                    "name": "Negative Priorities & Custom Base Delay",
                    "category": "Stress / Edge",
                    "args": [
                        [
                            {"name": "normal", "priority": 0, "retries": 2, "seq": 2},
                            {"name": "urgent-interrupt", "priority": -5, "retries": 1, "seq": 5},
                        ],
                        5,
                        5,
                    ],
                    "expected": [
                        {"name": "urgent-interrupt", "priority": -5, "backoff_seconds": 10},
                        {"name": "normal", "priority": 0, "backoff_seconds": 20},
                    ],
                    "is_hidden": True,
                },
            ],
        }
    else:
        ref_sol = (
            f"# Grounded in {p_file}:{p_start}-{p_end} ({p_sym})\n"
            "from typing import Any\n\n"
            "def build_code_chunks(\n"
            "    source_text: str,\n"
            "    chunk_size: int = 4,\n"
            "    overlap: int = 1,\n"
            ") -> list[dict[str, Any]]:\n"
            '    """Segment source_text into 1-based overlapping line chunks."""\n'
            "    lines = source_text.splitlines()\n"
            "    if not lines:\n"
            "        return []\n\n"
            "    step = max(1, chunk_size - overlap)\n"
            "    chunks: list[dict[str, Any]] = []\n"
            "    start = 0\n"
            "    chunk_index = 0\n\n"
            "    while start < len(lines):\n"
            "        end = min(start + chunk_size, len(lines))\n"
            "        content = '\\n'.join(lines[start:end]).strip()\n"
            "        if content:\n"
            "            chunks.append({\n"
            "                'chunk_index': chunk_index,\n"
            "                'start_line': start + 1,\n"
            "                'end_line': end,\n"
            "                'content': content,\n"
            "            })\n"
            "            chunk_index += 1\n"
            "        start += step\n\n"
            "    return chunks\n"
        )
        challenge = {
            "challenge_id": f"codeviva-hr-{repository_id}-chunker",
            "archetype": "sliding_chunker",
            "title": f"Sliding-Window Source Chunker & Line Anchor Indexer ({p_sym})",
            "difficulty": "Medium · Codebase Defence",
            "language": "python",
            "function_name": "build_code_chunks",
            "target_file": p_file,
            "target_symbol": p_sym,
            "target_lines": f"{p_file}:{p_start}-{p_end}",
            "secondary_file": s_file,
            "secondary_symbol": s_sym,
            "secondary_lines": f"{s_file}:{s_start}",
            "reference_code": primary["numbered_snippet"],
            "problem_statement": (
                f"In your uploaded repository (`{p_file}`, lines {p_start}–{p_end} around `{p_sym}`), "
                f"source files are segmented into line-anchored chunks so downstream analysis can cite exact line ranges.\n\n"
                f"Write a function `build_code_chunks(source_text, chunk_size, overlap)` that splits `source_text` into "
                f"overlapping line windows with 1-based line numbers:\n"
                f"1. **Step Size**: Advance the window start by `step = max(1, chunk_size - overlap)` lines on each iteration.\n"
                f"2. **1-Based Line Anchors**: For a window covering slice `lines[start:end]`, set `'start_line': start + 1` and `'end_line': end`.\n"
                "3. **Skip Blank Windows**: Strip leading/trailing whitespace from the joined window (`content = '\\n'.join(lines[start:end]).strip()`). "
                "If `content` is empty, do not emit a chunk (and only increment `'chunk_index'` for emitted chunks).\n"
                "4. **Output Format**: Return a list of dictionaries `[{'chunk_index': int, 'start_line': int, 'end_line': int, 'content': str}]`."
            ),
            "constraints": [
                "If overlap >= chunk_size, step must be clamped to at least 1 (`max(1, chunk_size - overlap)`) to prevent infinite loops.",
                "Empty or whitespace-only windows must be skipped without incrementing chunk_index.",
                "start_line and end_line are 1-based inclusive line numbers.",
            ],
            "starter_code": ref_sol,
            "reference_solution": ref_sol,
            "solution_hint": (
                "Compute `step = max(1, chunk_size - overlap)`, slice `lines[start:end]` where `end = min(start + chunk_size, len(lines))`, "
                "and only append when `'\\n'.join(lines[start:end]).strip()` is non-empty."
            ),
            "test_cases": [
                {
                    "id": "TC1",
                    "name": "Standard Sliding Window with Overlap",
                    "category": "Base Case",
                    "args": ["line1\nline2\nline3\nline4\nline5", 3, 1],
                    "expected": [
                        {"chunk_index": 0, "start_line": 1, "end_line": 3, "content": "line1\nline2\nline3"},
                        {"chunk_index": 1, "start_line": 3, "end_line": 5, "content": "line3\nline4\nline5"},
                        {"chunk_index": 2, "start_line": 5, "end_line": 5, "content": "line5"},
                    ],
                    "is_hidden": False,
                },
                {
                    "id": "TC2",
                    "name": "Overlap >= Chunk Size Guard (Step Clamping)",
                    "category": "Boundary",
                    "args": ["a\nb\nc", 2, 5],
                    "expected": [
                        {"chunk_index": 0, "start_line": 1, "end_line": 2, "content": "a\nb"},
                        {"chunk_index": 1, "start_line": 2, "end_line": 3, "content": "b\nc"},
                        {"chunk_index": 2, "start_line": 3, "end_line": 3, "content": "c"},
                    ],
                    "is_hidden": False,
                },
                {
                    "id": "TC3",
                    "name": "Skip Whitespace-Only Windows Cleanly",
                    "category": "Invariant",
                    "args": ["   \n  \ndef alpha():\n    return 1", 2, 0],
                    "expected": [
                        {"chunk_index": 0, "start_line": 3, "end_line": 4, "content": "def alpha():\n    return 1"},
                    ],
                    "is_hidden": False,
                },
                {
                    "id": "TC4",
                    "name": "Empty File Handling",
                    "category": "Edge Case",
                    "args": ["", 4, 1],
                    "expected": [],
                    "is_hidden": True,
                },
                {
                    "id": "TC5",
                    "name": "Single-Line Repository File",
                    "category": "Stress / Edge",
                    "args": ["export const VERSION = '1.0.0'", 10, 2],
                    "expected": [
                        {
                            "chunk_index": 0,
                            "start_line": 1,
                            "end_line": 1,
                            "content": "export const VERSION = '1.0.0'",
                        }
                    ],
                    "is_hidden": True,
                },
            ],
        }

    challenge["targeted_questions"] = build_targeted_questions(challenge, targets)

    if cache_dir is not None:
        try:
            cache_file = cache_dir / f"challenge_repo_{repository_id}_{files_fingerprint}.json"
            cache_file.write_text(json.dumps(challenge, indent=2), encoding="utf-8")
        except Exception:
            pass

    return challenge


def build_targeted_questions(
    challenge: Dict[str, Any],
    targets: Dict[str, Any],
    student_code: Optional[str] = None,
    test_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return the challenge's targeted questions (preserving custom LLM questions if present)."""
    existing = challenge.get("targeted_questions")
    if existing and len(existing) == 5 and challenge.get("archetype") == "llm_custom_codebase":
        return existing

    p_file = challenge["target_file"]
    p_sym = challenge["target_symbol"]
    p_lines = challenge["target_lines"]
    s_file = challenge["secondary_file"]
    s_sym = challenge["secondary_symbol"]
    s_lines = challenge["secondary_lines"]
    fn_name = challenge["function_name"]

    pass_badge = ""
    if test_summary is not None:
        p_cnt = test_summary.get("passed_count", 0)
        t_cnt = test_summary.get("total_count", 5)
        pass_badge = f" (your submission passed {p_cnt}/{t_cnt} test cases)"

    return [
        {
            "id": "Q1",
            "dimension": "code_understanding",
            "dimension_label": "Code understanding",
            "anchor": f"{p_lines} · {fn_name}()",
            "citations": [p_lines, f"{fn_name}()"],
            "text": (
                f"Walk through how your `{fn_name}` implementation{pass_badge} processes its inputs step by step, "
                f"and explain how this logic connects to `{p_sym}` in `{p_lines}` of your uploaded repository."
            ),
            "follow_up": (
                f"What is the time and space complexity of your `{fn_name}` implementation as the input size grows?"
            ),
            "good_answer_mentions": [
                f"step-by-step control flow in {fn_name} and {p_sym}",
                "time and space complexity bounds on large inputs",
                "how state or output records are constructed and returned",
            ],
            "why_selected": f"Directly verifies understanding of submitted `{fn_name}` solution and `{p_lines}`.",
            "suggested_outline": (
                f"Explain the iteration/filtering steps in `{fn_name}`, how `{p_sym}` in `{p_file}` uses similar invariants, "
                f"and state the Big-O time/space complexity."
            ),
        },
        {
            "id": "Q2",
            "dimension": "decision_rationale",
            "dimension_label": "Decision rationale",
            "anchor": f"{p_lines} · Trade-offs",
            "citations": [p_lines],
            "text": (
                f"In `{p_lines}` (`{p_sym}`) and in your `{fn_name}` solution, why did you choose this specific data structure "
                f"and boundary logic over alternative designs, and what trade-offs did you accept?"
            ),
            "follow_up": (
                "If memory were strictly bounded or inputs arrived as an unbounded stream, what would you trade off differently?"
            ),
            "good_answer_mentions": [
                "rationale for choosing the data structure or sorting/window strategy",
                "trade-off between simplicity, memory overhead, and runtime latency",
                "streaming or bounded-memory alternative design",
            ],
            "why_selected": f"Probes engineering trade-offs in `{p_lines}` and the live coding exercise.",
            "suggested_outline": (
                "Discuss why your chosen data structure fits the access pattern, what edge-case complexity it avoids, "
                "and how you would adapt it for streaming inputs."
            ),
        },
        {
            "id": "Q3",
            "dimension": "debugging_failure_handling",
            "dimension_label": "Debugging and failure handling",
            "anchor": f"Test Cases TC2–TC4 · {p_file}",
            "citations": [p_lines, "Test Suite TC2-TC4"],
            "text": (
                f"Look at the boundary and edge-case tests (`TC2`, `TC3`, and `TC4`) in the coding exercise and the error paths in `{p_file}`. "
                f"What subtle bug or failure mode occurs if those boundary guards are omitted, and how would you diagnose and fix it in production?"
            ),
            "follow_up": (
                f"Where in `{p_file}` could malformed input or an unhandled exception still cause silent data corruption or cascading failure?"
            ),
            "good_answer_mentions": [
                "boundary guard behavior in TC2, TC3, and TC4",
                "how malformed inputs, empty values, or invalid bounds are isolated",
                "concrete debugging signal, logging, or regression test strategy",
            ],
            "why_selected": f"Tests debugging and failure-mode reasoning on `{p_file}` and edge-case test cases.",
            "suggested_outline": (
                "Describe what breaks without the boundary check (e.g., infinite loop, starvation, or bad state), "
                "and explain how you validate inputs and catch regressions."
            ),
        },
        {
            "id": "Q4",
            "dimension": "consistency_across_rounds",
            "dimension_label": "Consistency across rounds",
            "anchor": f"{p_lines} ↔ {s_lines}",
            "citations": [p_lines, s_lines],
            "text": (
                f"How does the contract of `{p_sym}` in `{p_lines}` stay consistent with `{s_sym}` in `{s_lines}` across your repository, "
                f"and what invariant must remain true across both modules when code is refactored?"
            ),
            "follow_up": (
                f"If you changed the return schema of `{fn_name}` or `{p_sym}`, which callers in `{s_file}` would break first?"
            ),
            "good_answer_mentions": [
                f"interface contract between {p_file} and {s_file}",
                "schema and state invariants preserved across modules",
                "impact of refactoring or changing return types on downstream callers",
            ],
            "why_selected": f"Checks cross-file consistency between `{p_lines}` and `{s_lines}`.",
            "suggested_outline": (
                f"Explain how data flows between `{p_file}` and `{s_file}`, the shared schema assumptions, "
                f"and what integration test guarantees consistency."
            ),
        },
        {
            "id": "Q5",
            "dimension": "communication_under_follow_up",
            "dimension_label": "Communication under follow-up",
            "anchor": f"Live Follow-Up Probe · {fn_name}()",
            "citations": [p_lines, s_lines],
            "text": (
                f"Follow-Up Probe: Suppose traffic or repository size increases 100× and `{fn_name}` (alongside `{p_sym}` in `{p_file}`) "
                f"must run concurrently across multiple workers. Where is the bottleneck or race condition in your current code, and how would you redesign it?"
            ),
            "follow_up": (
                "Be specific about what state would need locking, partitioning, or idempotency keys, and what remains uncertain."
            ),
            "good_answer_mentions": [
                "concurrency bottleneck or shared-state contention under 100x load",
                "partitioning, locking, batching, or idempotency redesign",
                "honest identification of edge cases or operational trade-offs",
            ],
            "why_selected": "Evaluates technical communication and adaptability under an examiner follow-up constraint.",
            "suggested_outline": (
                "Identify the primary bottleneck under 100x concurrent load, propose a concrete partitioning or async batching strategy, "
                "and note any trade-offs."
            ),
        },
    ]


def execute_coding_challenge(
    challenge: Dict[str, Any],
    student_code: str,
) -> Dict[str, Any]:
    """Execute the student's Python solution against the challenge's test suite in an isolated subprocess."""
    fn_name = challenge["function_name"]
    test_cases = challenge["test_cases"]

    harness_payload = {
        "function_name": fn_name,
        "test_cases": [
            {
                "id": tc["id"],
                "name": tc["name"],
                "category": tc["category"],
                "args": tc["args"],
                "expected": tc["expected"],
            }
            for tc in test_cases
        ],
    }

    runner_script = """
import io
import json
import sys
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr

payload = json.loads(sys.argv[1])
student_code = sys.argv[2]
fn_name = payload["function_name"]
test_cases = payload["test_cases"]

namespace = {}
compile_stdout = io.StringIO()
compile_stderr = io.StringIO()

try:
    with redirect_stdout(compile_stdout), redirect_stderr(compile_stderr):
        exec(compile(student_code, "<student_solution>", "exec"), namespace)
except Exception:
    print(json.dumps({
        "compile_error": traceback.format_exc(),
        "stdout": compile_stdout.getvalue(),
        "stderr": compile_stderr.getvalue(),
        "results": [],
    }))
    sys.exit(0)

target_fn = namespace.get(fn_name)
if not callable(target_fn):
    print(json.dumps({
        "compile_error": f"Function '{fn_name}' was not found or is not callable in your submission.",
        "stdout": compile_stdout.getvalue(),
        "stderr": compile_stderr.getvalue(),
        "results": [],
    }))
    sys.exit(0)

results = []
all_stdout = [compile_stdout.getvalue()] if compile_stdout.getvalue() else []
all_stderr = [compile_stderr.getvalue()] if compile_stderr.getvalue() else []

for tc in test_cases:
    tc_out = io.StringIO()
    tc_err = io.StringIO()
    t0 = time.perf_counter()
    passed = False
    actual = None
    err_msg = None
    try:
        args_copy = json.loads(json.dumps(tc["args"]))
        with redirect_stdout(tc_out), redirect_stderr(tc_err):
            actual = target_fn(*args_copy)
        passed = (actual == tc["expected"])
    except Exception:
        err_msg = traceback.format_exc()
        passed = False
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    if tc_out.getvalue():
        all_stdout.append(f"[{tc['id']}] {tc_out.getvalue().strip()}")
    if tc_err.getvalue():
        all_stderr.append(f"[{tc['id']}] {tc_err.getvalue().strip()}")
    results.append({
        "id": tc["id"],
        "name": tc["name"],
        "category": tc["category"],
        "input_display": json.dumps(tc["args"], ensure_ascii=False),
        "expected_display": json.dumps(tc["expected"], ensure_ascii=False),
        "actual_display": json.dumps(actual, ensure_ascii=False) if err_msg is None else " raised exception ",
        "passed": passed,
        "runtime_ms": elapsed_ms,
        "error": err_msg,
    })

print(json.dumps({
    "compile_error": None,
    "stdout": "\\n".join(all_stdout),
    "stderr": "\\n".join(all_stderr),
    "results": results,
}))
"""

    t_start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", runner_script, json.dumps(harness_payload), student_code],
            capture_output=True,
            text=True,
            timeout=3.5,
        )
    except subprocess.TimeoutExpired:
        return {
            "passed_count": 0,
            "total_count": len(test_cases),
            "all_passed": False,
            "runtime_ms": 3500.0,
            "compile_error": "Time Limit Exceeded (3.5s): Your code took too long to finish (check for an infinite loop).",
            "stdout": "",
            "stderr": "TimeoutExpired",
            "test_results": [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "category": tc["category"],
                    "input_display": json.dumps(tc["args"], ensure_ascii=False),
                    "expected_display": json.dumps(tc["expected"], ensure_ascii=False),
                    "actual_display": "Timed out (> 3500 ms)",
                    "passed": False,
                    "runtime_ms": 3500.0,
                    "error": "Execution timed out.",
                }
                for tc in test_cases
            ],
        }

    total_ms = round((time.perf_counter() - t_start) * 1000, 2)
    try:
        parsed = json.loads(proc.stdout.strip() or "{}")
    except Exception:
        parsed = {
            "compile_error": proc.stderr or "Failed to parse test runner output.",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "results": [],
        }

    compile_error = parsed.get("compile_error")
    results = parsed.get("results", [])

    if compile_error and not results:
        results = [
            {
                "id": tc["id"],
                "name": tc["name"],
                "category": tc["category"],
                "input_display": json.dumps(tc["args"], ensure_ascii=False),
                "expected_display": json.dumps(tc["expected"], ensure_ascii=False),
                "actual_display": "Compilation / Syntax Error",
                "passed": False,
                "runtime_ms": 0.0,
                "error": compile_error,
            }
            for tc in test_cases
        ]

    passed_count = sum(1 for r in results if r.get("passed"))
    return {
        "passed_count": passed_count,
        "total_count": len(test_cases),
        "all_passed": passed_count == len(test_cases) and len(test_cases) > 0,
        "runtime_ms": total_ms,
        "compile_error": compile_error,
        "stdout": parsed.get("stdout", ""),
        "stderr": parsed.get("stderr", ""),
        "test_results": results,
    }
