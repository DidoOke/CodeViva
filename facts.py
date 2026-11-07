"""Stage 1: deterministic facts from code and git history. No model, no execution.

Student code is only ever parsed with `ast.parse`; constant values are read with
`ast.literal_eval`, which evaluates literals only. Nothing from the submission is imported
or run.

Every fact has an id, a kind, a file and (where meaningful) a line, plus the commit that
introduced it when the history shows one. Fact kinds and their fields:

    constant            name, value
    constant_changed    name, old, new, commit*, line_at_commit, in_final
    fix_commit          commit*, files            (line is null: commit-level fact)
    exception_handler   function, exc_types, handler, broad, body_kind
    import              module, names
    loop_nesting        function, depth
    numeric_comparison  function, expr, op, operand
    data_structure      function, structure, usage (heapq, deque, defaultdict, Counter,
                                                   sort_in_loop, list_pop_front)
    test_function       name

    commit* = commit, commit_short, commit_message
"""
from __future__ import annotations

import ast
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

CONSTANT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
FIX_MESSAGE = re.compile(
    r"(?i)\b(fix(es|ed)?|bug|crash(es|ed)?|error|handle[sd]?|broken|oops|typo|wrong|never)\b"
)
BROAD_TYPES = {"Exception", "BaseException"}
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical"}
KIND_ORDER = [
    "constant_changed", "fix_commit", "constant", "exception_handler", "data_structure",
    "numeric_comparison", "loop_nesting", "import", "test_function",
]
STRUCTURE_USAGE = {"sort_in_loop": "`.sort()` on every iteration", "list_pop_front": "`.pop(0)`"}
OPS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
       ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in"}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return repr(value)


def _short(sha: str) -> str:
    return sha[:7]


# --------------------------------------------------------------------------- AST facts

def module_constants(tree: ast.Module) -> Dict[str, Tuple[Any, int]]:
    """Top-level UPPER_CASE = <literal> assignments: name -> (value, line)."""
    out: Dict[str, Tuple[Any, int]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            name = node.target.id
        else:
            continue
        if not CONSTANT_NAME.match(name):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError, TypeError):
            continue
        out[name] = (_json_safe(value), node.lineno)
    return out


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else ""
        return f"{base}.{f.attr}" if base else f".{f.attr}"
    return ""


def _handler_body_kind(handler: ast.ExceptHandler) -> str:
    first = handler.body[0] if handler.body else None
    if isinstance(first, ast.Pass):
        return "pass"
    if isinstance(first, ast.Continue):
        return "continue"
    if isinstance(first, ast.Return):
        return "return"
    if isinstance(first, ast.Raise):
        return "raise"
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Call):
        name = _call_name(first.value)
        if name == "print" or name.split(".")[-1] in LOG_METHODS:
            return "log"
    return "other"


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, constants: Dict[str, Tuple[Any, int]]):
        self.path = path
        self.constants = constants
        self.facts: List[Dict[str, Any]] = []
        self.func_stack: List[str] = []
        self.loop_depth = 0
        self.seen_structures: set = set()

    @property
    def func(self) -> str:
        return self.func_stack[-1] if self.func_stack else "<module>"

    def add(self, kind: str, line: Optional[int], **fields: Any) -> None:
        self.facts.append({"kind": kind, "file": self.path, "line": line, **fields})

    # functions -------------------------------------------------------------
    def _visit_func(self, node: Any) -> None:
        is_test_file = self.path.split("/")[-1].startswith("test_") or self.path.startswith("tests/")
        if is_test_file and node.name.startswith("test_") and not self.func_stack:
            self.add("test_function", node.lineno, name=node.name)
        self.func_stack.append(node.name)
        saved, self.loop_depth = self.loop_depth, 0
        self.generic_visit(node)
        self.loop_depth = saved
        self.func_stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    # loops -----------------------------------------------------------------
    def _visit_loop(self, node: Any) -> None:
        if self.loop_depth == 0:
            depth = _max_loop_depth(node)
            if depth >= 2:
                self.add("loop_nesting", node.lineno, function=self.func, depth=depth)
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    visit_For = _visit_loop
    visit_While = _visit_loop
    visit_AsyncFor = _visit_loop

    # imports ---------------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.add("import", node.lineno, module=alias.name, names=alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.add("import", node.lineno, module=node.module or "", names=", ".join(a.name for a in node.names))

    # exception handlers ----------------------------------------------------
    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            exc_types, broad = "bare except", True
        else:
            exc_types = ast.unparse(node.type)
            names = {n.id for n in ast.walk(node.type) if isinstance(n, ast.Name)}
            broad = bool(names & BROAD_TYPES)
        handler = "except:" if node.type is None else f"except {exc_types}:"
        self.add("exception_handler", node.lineno, function=self.func, exc_types=exc_types,
                 handler=handler, broad=broad, body_kind=_handler_body_kind(node))
        self.generic_visit(node)

    # comparisons -----------------------------------------------------------
    def visit_Compare(self, node: ast.Compare) -> None:
        if self.func_stack:
            for operand in [node.left, *node.comparators]:
                label = None
                if isinstance(operand, ast.Constant) and isinstance(operand.value, (int, float)) \
                        and not isinstance(operand.value, bool):
                    label = repr(operand.value)
                elif isinstance(operand, ast.Name) and operand.id in self.constants:
                    label = operand.id
                if label is not None:
                    self.add("numeric_comparison", node.lineno, function=self.func, expr=ast.unparse(node),
                             op=OPS.get(type(node.ops[0]), "?"), operand=label)
                    break
        self.generic_visit(node)

    # data structures -------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        structure = None
        if name.startswith("heapq.") or name in {"heappush", "heappop", "heapify"}:
            structure = "heapq"
        elif name.split(".")[-1] in {"deque", "defaultdict", "Counter", "OrderedDict"} and not name.startswith("."):
            structure = name.split(".")[-1]
        elif self.loop_depth > 0 and name.endswith(".sort"):  # in-place re-sort every iteration
            structure = "sort_in_loop"
        elif name.endswith(".pop") and len(node.args) == 1 and isinstance(node.args[0], ast.Constant) \
                and node.args[0].value == 0:
            structure = "list_pop_front"
        if structure and (structure, self.func) not in self.seen_structures:
            self.seen_structures.add((structure, self.func))
            self.add("data_structure", node.lineno, function=self.func, structure=structure,
                     usage=STRUCTURE_USAGE.get(structure, structure))
        self.generic_visit(node)


def _max_loop_depth(node: ast.AST) -> int:
    best = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        best = max(best, _max_loop_depth(child))
    return best + (1 if isinstance(node, (ast.For, ast.While, ast.AsyncFor)) else 0)


def ast_facts(path: str, source: str) -> List[Dict[str, Any]]:
    tree = ast.parse(source, filename=path)  # parse only, never execute
    constants = module_constants(tree)
    facts = [{"kind": "constant", "file": path, "line": line, "name": name, "value": value}
             for name, (value, line) in constants.items()]
    v = _Visitor(path, constants)
    v.visit(tree)
    return facts + v.facts


# --------------------------------------------------------------------------- history facts

def snapshots(commits: List[Dict[str, Any]]) -> Iterable[Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]]:
    """Yield (commit, files_before, files_after) for each commit, oldest first."""
    state: Dict[str, str] = {}
    for commit in commits:
        before = dict(state)
        for path, content in commit["files"].items():
            if content is None:
                state.pop(path, None)
            else:
                state[path] = content
        yield commit, before, dict(state)


def _safe_constants(source: str) -> Optional[Dict[str, Tuple[Any, int]]]:
    try:
        return module_constants(ast.parse(source))
    except SyntaxError:
        return None


def history_facts(commits: List[Dict[str, Any]], final_files: Dict[str, str]) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    final_consts = {p: _safe_constants(src) or {} for p, src in final_files.items() if p.endswith(".py")}
    for commit, before, after in snapshots(commits):
        ref = {"commit": commit["sha"], "commit_short": _short(commit["sha"]), "commit_message": commit["message"]}
        py_touched = [p for p in commit["files"] if p.endswith(".py")]
        if FIX_MESSAGE.search(commit["message"]):
            facts.append({"kind": "fix_commit", "file": py_touched[0] if py_touched else None, "line": None,
                          "files": sorted(commit["files"]), **ref})
        for path in py_touched:
            if path not in before or path not in after:
                continue
            old, new = _safe_constants(before[path]), _safe_constants(after[path])
            if old is None or new is None:
                continue
            for name in sorted(set(old) & set(new)):
                if old[name][0] != new[name][0]:
                    final = final_consts.get(path, {}).get(name)
                    facts.append({
                        "kind": "constant_changed", "file": path,
                        "line": final[1] if final else new[name][1],
                        "name": name, "old": old[name][0], "new": new[name][0],
                        "line_at_commit": new[name][1], "in_final": final is not None, **ref,
                    })
    return facts


def attach_introducing_commit(facts: List[Dict[str, Any]], commits: List[Dict[str, Any]],
                              final_files: Dict[str, str]) -> None:
    """For AST facts, record the first commit whose snapshot contains the fact's source line."""
    snaps = list(snapshots(commits))
    for fact in facts:
        if "commit" in fact or not fact.get("file") or not fact.get("line"):
            continue
        lines = final_files.get(fact["file"], "").splitlines()
        if not 0 < fact["line"] <= len(lines):
            continue
        text = lines[fact["line"] - 1].strip()
        if not text:
            continue
        for commit, _, after in snaps:
            content = after.get(fact["file"])
            if content and any(l.strip() == text for l in content.splitlines()):
                fact.update(commit=commit["sha"], commit_short=_short(commit["sha"]),
                            commit_message=commit["message"])
                break


def extract_facts(submission: Dict[str, Any]) -> Dict[str, Any]:
    """submission: load_submission() shape. Returns {"facts", "parse_errors", "python_files"}."""
    files: Dict[str, str] = submission["files"]
    commits: List[Dict[str, Any]] = submission.get("commits", [])
    facts: List[Dict[str, Any]] = []
    parse_errors: List[Dict[str, Any]] = []
    py_files = sorted(p for p in files if p.endswith(".py"))
    for path in py_files:
        try:
            facts.extend(ast_facts(path, files[path]))
        except SyntaxError as exc:
            parse_errors.append({"file": path, "line": exc.lineno, "error": exc.msg})
    facts.extend(history_facts(commits, files))
    attach_introducing_commit(facts, commits, files)

    order = {k: i for i, k in enumerate(KIND_ORDER)}
    facts.sort(key=lambda f: (order.get(f["kind"], 99), f.get("file") or "", f.get("line") or 0,
                              str(f.get("name", "")), f.get("commit", "")))
    for i, fact in enumerate(facts, 1):
        fact["id"] = f"F{i:03d}"
    return {"facts": facts, "parse_errors": parse_errors, "python_files": len(py_files)}
