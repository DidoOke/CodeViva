"""Stage 2: match lecturer-written markdown rules (kb/) against stage-1 facts. No model.

Rule file format: see kb/README.md. A rule matching no facts is reported "not triggered".
When a rule matches several facts, ONE instance is chosen in code with a seeded RNG
(seed = submission id + rule id), never by a model.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DIMENSIONS = (
    "decision_rationale",
    "code_understanding",
    "debugging_failure_handling",
    "consistency_across_rounds",
    "communication_under_follow_up",
)
CONDITION = re.compile(r"^\s*(\w+)\s*(~|!=|>=|<=|=|>|<|\bin\b)\s*(.+?)\s*$")
PLACEHOLDER = re.compile(r"\{(\w+)\}")
SECTIONS = {"question": "question", "follow-up": "follow_up", "good answer mentions": "good_answer_mentions"}


class RuleError(ValueError):
    pass


@dataclass
class Condition:
    field: str
    op: str
    value: str

    def test(self, fact: Dict[str, Any]) -> bool:
        if self.field not in fact or fact[self.field] is None:
            return False
        actual = fact[self.field]
        if self.op == "~":
            return re.search(self.value, str(actual)) is not None
        if self.op == "in":
            return str(actual) in [v.strip() for v in self.value.split(",")]
        if self.op in ("=", "!="):
            equal = str(actual).lower() == self.value.lower()
            return equal if self.op == "=" else not equal
        try:
            a, b = float(actual), float(self.value)
        except (TypeError, ValueError):
            return False
        return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[self.op]


@dataclass
class Rule:
    id: str
    title: str
    fact: str  # fact kind, or "always"
    question: str
    follow_up: str
    good_answer_mentions: List[str]
    dimension: str
    priority: int = 50
    where: List[Condition] = field(default_factory=list)
    source_file: str = ""

    def matches(self, fact: Dict[str, Any]) -> bool:
        return fact["kind"] == self.fact and all(c.test(fact) for c in self.where)


def _parse_frontmatter(text: str, path: str) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    current_list: Optional[str] = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        if raw.lstrip().startswith("- ") and current_list:
            meta[current_list].append(raw.lstrip()[2:].strip())
            continue
        if ":" not in raw:
            raise RuleError(f"{path}: cannot parse frontmatter line {raw!r}")
        key, value = raw.split(":", 1)
        key, value = key.strip(), value.strip()
        if value == "":
            meta[key] = []
            current_list = key
        else:
            meta[key] = value
            current_list = None
    return meta


def parse_rule(text: str, path: str = "<string>") -> Rule:
    if not text.startswith("---"):
        raise RuleError(f"{path}: rule must start with a '---' frontmatter block")
    try:
        _, front, body = text.split("---", 2)
    except ValueError:
        raise RuleError(f"{path}: frontmatter block is not closed with '---'") from None
    meta = _parse_frontmatter(front, path)
    for key in ("id", "fact", "dimension"):
        if not meta.get(key):
            raise RuleError(f"{path}: missing '{key}' in frontmatter")
    if meta["dimension"] not in DIMENSIONS:
        raise RuleError(f"{path}: dimension {meta['dimension']!r} not one of {', '.join(DIMENSIONS)}")

    where = []
    for cond in meta.get("where", []) or []:
        m = CONDITION.match(cond)
        if not m:
            raise RuleError(f"{path}: cannot parse condition {cond!r} (use 'field ~ regex', 'field >= 2', ...)")
        if m.group(2) == "~":
            try:
                re.compile(m.group(3))
            except re.error as exc:
                raise RuleError(f"{path}: bad regex in {cond!r}: {exc}") from None
        where.append(Condition(m.group(1), m.group(2), m.group(3)))

    title, sections, current = "", {}, None
    for line in body.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            current = SECTIONS.get(line[3:].strip().lower())
            if current is None:
                raise RuleError(f"{path}: unknown section {line.strip()!r}")
            sections[current] = []
        elif current:
            sections[current].append(line)

    question = "\n".join(sections.get("question", [])).strip()
    if not question:
        raise RuleError(f"{path}: missing '## Question' section")
    if question.count("?") != 1:
        raise RuleError(f"{path}: question must contain exactly one '?' (one question per turn)")
    follow_up = "\n".join(sections.get("follow_up", [])).strip()
    if follow_up and follow_up.count("?") != 1:
        raise RuleError(f"{path}: follow-up must contain exactly one '?'")
    mentions = [l.strip()[2:].strip() for l in sections.get("good_answer_mentions", []) if l.strip().startswith("- ")]
    if not mentions:
        raise RuleError(f"{path}: '## Good answer mentions' needs at least one '- ' bullet")

    try:
        priority = int(meta.get("priority", 50))
    except ValueError:
        raise RuleError(f"{path}: priority must be an integer") from None
    return Rule(id=meta["id"], title=title or meta["id"], fact=meta["fact"], question=question,
                follow_up=follow_up, good_answer_mentions=mentions, dimension=meta["dimension"],
                priority=priority, where=where, source_file=path)


def load_rules(kb_dirs: List[str]) -> List[Rule]:
    rules: List[Rule] = []
    seen: Dict[str, str] = {}
    for d in kb_dirs:
        base = Path(d)
        if not base.is_dir():
            raise RuleError(f"knowledge base directory not found: {d}")
        for path in sorted(base.glob("*.md")):
            if path.name.lower() in ("readme.md", "spec.md"):
                continue
            rule = parse_rule(path.read_text(encoding="utf-8"), str(path))
            if rule.id in seen:
                raise RuleError(f"duplicate rule id {rule.id!r} in {path} and {seen[rule.id]}")
            seen[rule.id] = str(path)
            rules.append(rule)
    return rules


def kb_hash(kb_dirs: List[str]) -> str:
    h = hashlib.sha256()
    for d in kb_dirs:
        for path in sorted(Path(d).glob("*.md")):
            h.update(str(path).encode())
            h.update(path.read_bytes())
    return h.hexdigest()


def fill(template: str, fact: Dict[str, Any], rule_id: str) -> str:
    def sub(m: "re.Match[str]") -> str:
        key = m.group(1)
        if key not in fact or fact[key] is None:
            raise RuleError(f"rule {rule_id}: placeholder {{{key}}} has no value in fact {fact.get('id')}")
        return str(fact[key])
    return PLACEHOLDER.sub(sub, template)


def seeded_choice(seed: str, rule_id: str, options: List[str]) -> str:
    """Deterministic per (seed, rule): same student, same choice; different students vary."""
    digest = hashlib.sha256(f"{seed}:{rule_id}".encode()).hexdigest()
    return random.Random(int(digest, 16)).choice(sorted(options))


def match_rules(rules: List[Rule], facts: List[Dict[str, Any]], seed: str) -> List[Dict[str, Any]]:
    out = []
    for rule in rules:
        entry: Dict[str, Any] = {
            "rule_id": rule.id, "title": rule.title, "source_file": rule.source_file, "fact_kind": rule.fact,
            "dimension": rule.dimension, "priority": rule.priority,
            "good_answer_mentions": rule.good_answer_mentions,
        }
        if rule.fact == "always":
            entry.update(triggered=True, instances=[], chosen_fact_id=None,
                         question=rule.question, follow_up=rule.follow_up)
            out.append(entry)
            continue
        instances = [f for f in facts if rule.matches(f)]
        if not instances:
            entry.update(triggered=False, instances=[], chosen_fact_id=None, question=None, follow_up=None,
                         note="not triggered: no matching facts (the student may not have implemented this part)")
            out.append(entry)
            continue
        chosen_id = seeded_choice(seed, rule.id, [f["id"] for f in instances])
        chosen = next(f for f in instances if f["id"] == chosen_id)
        entry.update(triggered=True, instances=[f["id"] for f in instances], chosen_fact_id=chosen_id,
                     question=fill(rule.question, chosen, rule.id),
                     follow_up=fill(rule.follow_up, chosen, rule.id) if rule.follow_up else "")
        out.append(entry)
    return out
