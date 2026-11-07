"""Stage 1d (round 2+): what changed since the previous round, and did the stated plan happen?

Inputs: this round's snapshot and facts (stages 0, 1) and the previous round's saved artifacts
(stage0_submission.json, stage1_facts.json, stage5_plan.json, transcript.json).

Output, used by stages 2-5 in place of the stage-1 facts:
  facts        facts NEW since the previous round (so round-1 questions are not asked again)
               + delta facts (ids D001...):
    round_constant_changed  name, old, new                   value differs from last round
    import_added            module, names
    structure_added         structure, usage, label, function
    structure_removed       structure, usage, label, function, prev_line
    function_added          function, lines
    function_changed        function, churn (0-1), lines_before, lines_after
    function_removed        function, prev_line
    round_fix_commit        commit*, files                   fix-like commit made this round
    plan_item               claim, quote, status (found | no_evidence), keywords, evidence_where
  Each has file, line and the commit (made this round) that introduced it, where one applies.

The stated plan is the student's answer to last round's plan question. Splitting it into claims
may use the model, but every claim must quote the student verbatim (checked in code); matching
claims to evidence is done in code only. "no_evidence" means code could not find the change, not
that the student did not make it: the round-2 question asks where to look.
"""
from __future__ import annotations

import ast
import difflib
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from facts import FIX_MESSAGE, _safe_constants, snapshots
from llm import JSONModel, ModelError, strict_object

PLAN_RULE_IDS = {"g-next-iteration-plan"}
MIN_CHURN = 0.3
MAX_CLAIMS = 5
MAX_EVIDENCE = 3
COMMIT_LEVEL = {"fix_commit"}  # facts identified by their commit, not their line
VOLATILE = {"id", "line", "commit", "commit_short", "commit_message", "line_at_commit", "in_final"}
STOPWORDS = set("""
a about after again all also an and any are as at be because been before but by can could did do
does each first for from get had has have how i if in into is it its just like make maybe me more
most my need new no not now of on one only or other our out over probably really right run so some
than that the their them then there these they thing things this to too up use used very want was
way we well were what when where which while will with would you your yes add adding change
changing better instead also first sure try see code project week time
""".split())
SUFFIXES = ("ing", "ion", "ed", "er", "es", "s", "e")

REPEAT_OR_META = re.compile(r"^\s*(repeat|again|pass|skip|next|pardon|sorry|what\??|i don'?t know|no idea|"
                            r"was (that|i|it) (right|correct|wrong|ok)\??|how did i do\??)[\s.!?]*$", re.I)


# --------------------------------------------------------------------------- small helpers

def stem(word: str) -> str:
    w = word.lower()
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def stems_of(text: str) -> List[str]:
    """Words and identifier parts (snake_case and camelCase split), stemmed, stopwords removed."""
    words = []
    for token in re.findall(r"[A-Za-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")):
        t = token.lower()
        if len(t) >= 3 and t not in STOPWORDS:
            words.append(stem(t))
    return words


def fact_key(f: Dict[str, Any]) -> Tuple:
    """Identity of a fact across rounds, ignoring where it moved to (line) and its id."""
    keep = {k: v for k, v in f.items() if k not in VOLATILE}
    if f.get("kind") in COMMIT_LEVEL:
        keep["commit"] = f.get("commit")
    return tuple(sorted((k, repr(v)) for k, v in keep.items()))


def _ref(commit: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not commit:
        return {}
    return {"commit": commit["sha"], "commit_short": commit["sha"][:7], "commit_message": commit["message"]}


def function_spans(source: str) -> Dict[str, Tuple[int, str]]:
    """Top-level functions and class methods: qualified name -> (def line, source text)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    lines = source.splitlines()
    out: Dict[str, Tuple[int, str]] = {}

    def add(node: ast.AST, name: str) -> None:
        end = getattr(node, "end_lineno", node.lineno)
        out[name] = (node.lineno, "\n".join(lines[node.lineno - 1:end]))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(sub, f"{node.name}.{sub.name}")
    return out


def churn(old: str, new: str) -> float:
    return round(1 - difflib.SequenceMatcher(None, old.splitlines(), new.splitlines()).ratio(), 2)


def added_lines(prev_files: Dict[str, str], cur_files: Dict[str, str]) -> List[Tuple[str, int, str]]:
    """(file, line in current version, text) for every line added or rewritten since last round."""
    out = []
    for path in sorted(cur_files):
        new = cur_files[path].splitlines()
        old = prev_files.get(path, "").splitlines()
        for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag in ("insert", "replace"):
                out.extend((path, j + 1, new[j]) for j in range(j1, j2) if new[j].strip())
    return out


class History:
    """This round's commits, with snapshots, to attribute a change to the commit that made it."""

    def __init__(self, commits: List[Dict[str, Any]], prev_shas: Set[str]):
        self.snaps = list(snapshots(commits))
        self.new = [c for c in commits if c["sha"] not in prev_shas]
        new_shas = {c["sha"] for c in self.new}
        self.new_snaps = [s for s in self.snaps if s[0]["sha"] in new_shas]

    def first(self, path: str, pred) -> Optional[Dict[str, Any]]:
        for commit, _before, after in self.new_snaps:
            if path in commit["files"] and after.get(path) is not None and pred(after[path]):
                return commit
        return None

    def introducing_line(self, path: str, text: str) -> Optional[Dict[str, Any]]:
        text = text.strip()
        return self.first(path, lambda src: any(l.strip() == text for l in src.splitlines())) if text else None


# --------------------------------------------------------------------------- code delta

def code_delta(prev_files: Dict[str, str], cur_files: Dict[str, str], prev_facts: List[Dict[str, Any]],
               cur_facts: List[Dict[str, Any]], history: History) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    py = sorted(p for p in cur_files if p.endswith(".py"))

    # constants whose value differs from last round
    for path in py:
        old = _safe_constants(prev_files.get(path, "")) or {}
        new = _safe_constants(cur_files[path]) or {}
        for name in sorted(set(old) & set(new)):
            if old[name][0] != new[name][0]:
                target = new[name][0]
                commit = history.first(path, lambda src, n=name, t=target: (_safe_constants(src) or {}).get(n, (None,))[0] == t)
                out.append({"kind": "round_constant_changed", "file": path, "line": new[name][1], "name": name,
                            "old": old[name][0], "new": target, **_ref(commit)})

    # imports and data structures that appeared or disappeared
    prev_keys = {fact_key(f): f for f in prev_facts}
    cur_keys = {fact_key(f): f for f in cur_facts}
    cur_lines = {p: cur_files[p].splitlines() for p in py}
    spans_now = {p: function_spans(cur_files[p]) for p in py}

    def line_text(f: Dict[str, Any]) -> str:
        lines = cur_lines.get(f.get("file"), [])
        return lines[f["line"] - 1] if f.get("line") and 0 < f["line"] <= len(lines) else ""

    for key, f in cur_keys.items():
        if key in prev_keys:
            continue
        if f["kind"] == "import":
            out.append({"kind": "import_added", "file": f["file"], "line": f["line"], "module": f["module"],
                        "names": f.get("names"), **_ref(history.introducing_line(f["file"], line_text(f)))})
        elif f["kind"] == "data_structure":
            out.append({"kind": "structure_added", "file": f["file"], "line": f["line"],
                        "structure": f["structure"], "usage": f.get("usage"), "function": f.get("function"),
                        "label": f.get("usage") or f["structure"],
                        **_ref(history.introducing_line(f["file"], line_text(f)))})
    for key, f in prev_keys.items():
        if key in cur_keys or f["kind"] != "data_structure":
            continue
        span = spans_now.get(f["file"], {}).get(f.get("function") or "")
        commit = history.first(f["file"], lambda src, k=key: k not in {fact_key(g) for g in _structure_facts(f["file"], src)})
        out.append({"kind": "structure_removed", "file": f["file"], "line": span[0] if span else None,
                    "structure": f["structure"], "usage": f.get("usage"), "function": f.get("function"),
                    "label": f.get("usage") or f["structure"], "prev_line": f.get("line"),
                    **_ref(commit)})

    # functions added, rewritten or removed
    for path in py:
        before = function_spans(prev_files.get(path, ""))
        now = spans_now[path]
        for name, (line, src) in now.items():
            if name not in before:
                commit = history.first(path, lambda s, n=name: n in function_spans(s))
                out.append({"kind": "function_added", "file": path, "line": line, "function": name,
                            "lines": len(src.splitlines()), **_ref(commit)})
                continue
            c = churn(before[name][1], src)
            if c >= MIN_CHURN:
                old_src = before[name][1]
                commit = history.first(path, lambda s, n=name, o=old_src: n in function_spans(s)
                                       and churn(o, function_spans(s)[n][1]) >= MIN_CHURN)
                out.append({"kind": "function_changed", "file": path, "line": line, "function": name, "churn": c,
                            "lines_before": len(before[name][1].splitlines()), "lines_after": len(src.splitlines()),
                            **_ref(commit)})
        for name, (line, _src) in before.items():
            if name not in now:
                out.append({"kind": "function_removed", "file": path, "line": None, "function": name,
                            "prev_line": line})

    # fix-like commits made this round
    for commit in history.new:
        if FIX_MESSAGE.search(commit["message"]):
            touched = sorted(commit["files"])
            pys = [p for p in touched if p.endswith(".py")]
            out.append({"kind": "round_fix_commit", "file": pys[0] if pys else None, "line": None,
                        "files": touched, **_ref(commit)})
    return out


def _structure_facts(path: str, source: str) -> List[Dict[str, Any]]:
    from facts import ast_facts
    try:
        return [f for f in ast_facts(path, source) if f["kind"] == "data_structure"]
    except SyntaxError:
        return []


# --------------------------------------------------------------------------- stated plan

def stated_plan(prev_plan: Optional[Dict[str, Any]], prev_transcript: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The student's answer(s) to last round's plan question, verbatim."""
    if not prev_plan or not prev_transcript:
        return {"status": "missing", "reason": "previous round has no plan or no transcript", "answers": []}
    q = next((q for q in prev_plan.get("questions", []) if q.get("source", {}).get("rule_id") in PLAN_RULE_IDS), None)
    if q is None:
        return {"status": "missing", "reason": "previous round did not ask the plan question", "answers": []}
    answers = [t["text"] for t in prev_transcript.get("turns", [])
               if t.get("speaker") == "student" and t.get("question_id") == q["id"]
               and not REPEAT_OR_META.match(t.get("text", ""))]
    status = "ok" if answers else "passed"
    return {"status": status, "question_id": q["id"], "question": q["text"], "answers": answers,
            "reason": "" if answers else "the student did not answer the plan question"}


CLAIM_SCHEMA = strict_object({"claims": {"type": "array", "items": strict_object({
    "quote": {"type": "string", "description": "verbatim span of the student's words"},
    "keywords": {"type": "array", "items": {"type": "string"}},
})}})
CLAIM_SYSTEM = """A student was asked what they would change next in their programming project.
Split their answer into at most {n} separate intended changes. For each, give "quote": the exact
words the student used for that change, copied verbatim (no paraphrase), and "keywords": words
or code identifiers that would likely appear in code or commit messages if the change were made.
Do not judge the plan, and do not add changes the student did not state."""


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _trim_reason(quote: str) -> str:
    return re.split(r",?\s+because\b|,?\s+so that\b|,?\s+since\b", quote, maxsplit=1)[0].strip(" ,.;")


def split_claims(answers: List[str], model: Optional[JSONModel] = None) -> Dict[str, Any]:
    """Claims from the plan answers. Model output is kept only where its quote is verbatim."""
    text = " ".join(answers)
    dropped: List[str] = []
    if model is not None:
        try:
            resp = model.complete_json(system=CLAIM_SYSTEM.format(n=MAX_CLAIMS), user=text,
                                       schema=CLAIM_SCHEMA, name="plan_claims")
            claims = []
            for c in resp.get("claims", [])[:MAX_CLAIMS]:
                if c.get("quote") and _norm(c["quote"]) in _norm(text):
                    claims.append({"quote": c["quote"].strip(), "keywords": c.get("keywords", [])})
                else:
                    dropped.append(c.get("quote", ""))
            if claims:
                return {"mode": f"model ({model.model})", "claims": claims, "dropped_not_verbatim": dropped}
            reason = "model quotes were not verbatim"
        except ModelError as exc:
            reason = str(exc)
        mode = f"sentences (model fallback: {reason})"
    else:
        mode = "sentences (no model)"
    claims = []
    for sentence in re.split(r"(?<=[.!?;])\s+", text):
        if stems_of(_trim_reason(sentence)):
            claims.append({"quote": sentence.strip(), "keywords": []})
    return {"mode": mode, "claims": claims[:MAX_CLAIMS], "dropped_not_verbatim": dropped}


def check_claims(claims: List[Dict[str, Any]], delta_facts: List[Dict[str, Any]], prev_vocab: Set[str],
                 added: List[Tuple[str, int, str]], new_commits: List[Dict[str, Any]],
                 history: History) -> List[Dict[str, Any]]:
    """Code-only matching of each claim to evidence made this round."""
    by_name: Dict[str, Dict[str, Any]] = {}
    for f in delta_facts:
        for field in ("name", "function", "module", "structure"):
            for s in stems_of(str(f.get(field) or "")):
                by_name.setdefault(s, f)
    commit_stems = [(c, set(stems_of(c["message"]))) for c in new_commits]
    line_stems = [(path, line, text, set(stems_of(text))) for path, line, text in added]

    items = []
    for c in claims:
        core = _trim_reason(c["quote"])
        keys = list(dict.fromkeys(stems_of(core) + [s for k in c.get("keywords", []) for s in stems_of(k)]))
        evidence: List[Dict[str, Any]] = []
        matched: List[str] = []
        for k in keys:
            if len(evidence) >= MAX_EVIDENCE:
                break
            if k in by_name:
                f = by_name[k]
                ev = {"via": f["kind"], "keyword": k, "file": f.get("file"), "line": f.get("line"),
                      **{x: f[x] for x in ("commit", "commit_short", "commit_message") if f.get(x)}}
            elif k in prev_vocab:
                continue  # word already common in last round's code: not evidence of a change
            else:
                hit_c = next((cm for cm, st in commit_stems if k in st), None)
                hit_l = next(((p, ln, t) for p, ln, t, st in line_stems if k in st), None)
                if hit_c is None and hit_l is None:
                    continue
                ev = {"via": "commit_message" if hit_c else "added_line", "keyword": k}
                if hit_l:
                    ev.update(file=hit_l[0], line=hit_l[1], text=hit_l[2].strip())
                commit = hit_c or (history.introducing_line(hit_l[0], hit_l[2]) if hit_l else None)
                ev.update(_ref(commit))
            matched.append(k)
            loc = (ev.get("file"), ev.get("line"), ev.get("commit"))
            if loc not in {(e.get("file"), e.get("line"), e.get("commit")) for e in evidence}:
                evidence.append(ev)
        items.append({"quote": c["quote"], "claim": core.replace("?", ""), "keywords": keys, "matched": matched,
                      "status": "found" if evidence else "no_evidence", "evidence": evidence})
    return items


def plan_item_fact(item: Dict[str, Any]) -> Dict[str, Any]:
    first = item["evidence"][0] if item["evidence"] else {}
    if first.get("file") and first.get("line"):
        where = f"{first['file']}:{first['line']}"
    elif first.get("commit_short"):
        where = f"commit {first['commit_short']} (\"{first['commit_message']}\")"
    else:
        where = ""
    fact = {"kind": "plan_item", "file": first.get("file"), "line": first.get("line"),
            "claim": item["claim"], "quote": item["quote"], "status": item["status"],
            "keywords": ", ".join(item["matched"] or item["keywords"]), "evidence_where": where or None}
    fact.update({x: first[x] for x in ("commit", "commit_short", "commit_message") if first.get(x)})
    return fact


# --------------------------------------------------------------------------- assembly

def compute_delta(prev_sub: Dict[str, Any], cur_sub: Dict[str, Any], prev_facts: List[Dict[str, Any]],
                  cur_facts: List[Dict[str, Any]], prev_plan: Optional[Dict[str, Any]] = None,
                  prev_transcript: Optional[Dict[str, Any]] = None,
                  model: Optional[JSONModel] = None) -> Dict[str, Any]:
    """prev_sub / cur_sub: {"files": {path: content}, "commits": [...]} (load_submission shape)."""
    prev_files, cur_files = prev_sub["files"], cur_sub["files"]
    prev_shas = {c["sha"] for c in prev_sub.get("commits", [])}
    cur_shas = {c["sha"] for c in cur_sub.get("commits", [])}
    boundary = prev_sub["commits"][-1]["sha"] if prev_sub.get("commits") else None
    history = History(cur_sub.get("commits", []), prev_shas)

    delta_facts = code_delta(prev_files, cur_files, prev_facts, cur_facts, history)

    plan = stated_plan(prev_plan, prev_transcript)
    claims = split_claims(plan["answers"], model) if plan["status"] == "ok" else {"mode": "none", "claims": [],
                                                                                    "dropped_not_verbatim": []}
    prev_vocab = set(stems_of(" ".join(prev_files.values())))
    prev_vocab |= set(stems_of(" ".join(c["message"] for c in prev_sub.get("commits", []))))
    items = check_claims(claims["claims"], delta_facts, prev_vocab, added_lines(prev_files, cur_files),
                         history.new, history)
    delta_facts += [plan_item_fact(i) for i in items]
    for i, f in enumerate(delta_facts, 1):
        f["id"] = f"D{i:03d}"

    prev_keys = {fact_key(f) for f in prev_facts}
    new_facts = [f for f in cur_facts if fact_key(f) not in prev_keys]
    return {
        "boundary_commit": boundary,
        "history_rewritten": bool(boundary) and boundary not in cur_shas,
        "new_commits": [{"sha": c["sha"], "short": c["sha"][:7], "message": c["message"]} for c in history.new],
        "files_added": sorted(set(cur_files) - set(prev_files)),
        "files_removed": sorted(set(prev_files) - set(cur_files)),
        "files_changed": sorted(p for p in set(cur_files) & set(prev_files) if cur_files[p] != prev_files[p]),
        "carried_fact_count": len(cur_facts) - len(new_facts),
        "new_fact_ids": [f["id"] for f in new_facts],
        "delta_facts": delta_facts,
        "stated_plan": {**plan, "claim_mode": claims["mode"],
                        "dropped_not_verbatim": claims["dropped_not_verbatim"]},
        "plan_items": items,
        "facts": new_facts + delta_facts,
    }


def summarise(d: Dict[str, Any]) -> str:
    found = sum(i["status"] == "found" for i in d["plan_items"])
    plan = (f"plan: {found}/{len(d['plan_items'])} claims with evidence" if d["plan_items"]
            else f"plan: {d['stated_plan']['status']}")
    warn = "; HISTORY REWRITTEN since last round" if d["history_rewritten"] else ""
    return (f"{len(d['new_commits'])} new commits, {len(d['new_fact_ids'])} new facts, "
            f"{len(d['delta_facts'])} delta facts; {plan}{warn}")


def s1d_delta(ctx: Any, inputs: Dict[str, Any]) -> Any:
    """Pipeline stage wrapper. Reads the previous round's artifacts from ctx.previous_round_dir."""
    from artifacts import read_artifact
    from pipeline import StageResult

    prev_dir = ctx.previous_round_dir
    try:
        prev0 = read_artifact(prev_dir / "stage0_submission.json")
        prev1 = read_artifact(prev_dir / "stage1_facts.json")
    except FileNotFoundError:
        raise RuntimeError(f"round {ctx.round_no} needs round {ctx.round_no - 1} artifacts in {prev_dir}; "
                           f"run round {ctx.round_no - 1} first") from None
    optional = {}
    for name in ("stage5_plan.json", "transcript.json"):
        try:
            optional[name] = read_artifact(prev_dir / name)
        except FileNotFoundError:
            optional[name] = None

    def as_sub(s0: Dict[str, Any]) -> Dict[str, Any]:
        return {"files": {f["path"]: f["content"] for f in s0["files"]}, "commits": s0["commits"]}

    model = ctx.options.get("model")
    d = compute_delta(as_sub(prev0["data"]), as_sub(inputs["0"]), prev1["data"]["facts"], inputs["1"]["facts"],
                      prev_plan=optional["stage5_plan.json"] and optional["stage5_plan.json"]["data"],
                      prev_transcript=optional["transcript.json"] and optional["transcript.json"]["data"],
                      model=model)
    # previous-round hashes make this artifact (and everything downstream) change when last round does
    d["previous_round"] = {"dir": str(prev_dir), **{n: (e["meta"]["output_hash"] if e else None) for n, e in
                           (("stage0", prev0), ("stage1", prev1), ("plan", optional["stage5_plan.json"]),
                            ("transcript", optional["transcript.json"]))}}
    used_model = model.model if model and d["stated_plan"]["claim_mode"].startswith("model") else None
    return StageResult(d, count_in=len(inputs["1"]["facts"]), count_out=len(d["facts"]), summary=summarise(d),
                       model=used_model)
