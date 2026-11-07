"""Every rule parses, and each fires (and fills its template) on at least one fixture repo."""
from pathlib import Path

import pytest

from facts import extract_facts
from kb_match import RuleError, load_rules, match_rules, parse_rule, seeded_choice
from make_sample_repo import submission_1, submission_2

KB_DIRS = ["kb/generic", "kb/task_scheduler"]
RULE_FILES = sorted(p for d in KB_DIRS for p in Path(d).glob("*.md") if p.name not in ("README.md", "spec.md"))


@pytest.fixture(scope="module")
def fixture_facts():
    return {sid: extract_facts(sub)["facts"] for sid, sub in (("1", submission_1()), ("2", submission_2()))}


def test_assignment_has_10_to_15_rules():
    assert 10 <= len(list(Path("kb/task_scheduler").glob("ts-*.md"))) <= 15


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_rule_parses(path):
    rule = parse_rule(path.read_text(), str(path))
    assert rule.id == path.stem


@pytest.mark.parametrize("path", RULE_FILES, ids=lambda p: p.stem)
def test_rule_fires_on_a_fixture(path, fixture_facts):
    rule = parse_rule(path.read_text(), str(path))
    fired = []
    for sid, facts in fixture_facts.items():
        (entry,) = match_rules([rule], facts, seed=sid)
        if entry["triggered"]:
            assert "{" not in entry["question"] and entry["question"].count("?") == 1
            fired.append(sid)
    assert fired, f"{rule.id} fires on no fixture repo"


def test_not_triggered_is_reported(fixture_facts):
    rules = load_rules(KB_DIRS)
    entries = {e["rule_id"]: e for e in match_rules(rules, fixture_facts["2"], seed="2")}
    assert entries["ts-heap-ready-queue"]["triggered"] is False
    assert "not triggered" in entries["ts-heap-ready-queue"]["note"]
    assert entries["ts-silent-failure"]["triggered"] is True


def test_seeded_choice_is_deterministic_and_seed_dependent():
    options = [f"F{i:03d}" for i in range(20)]
    assert seeded_choice("1", "r", options) == seeded_choice("1", "r", list(reversed(options)))
    assert len({seeded_choice(str(s), "r", options) for s in range(30)}) > 5


@pytest.mark.parametrize("text,msg", [
    ("no frontmatter", "frontmatter"),
    ("---\nid: x\nfact: constant\ndimension: nope\n---\n", "dimension"),
    ("---\nid: x\nfact: constant\ndimension: decision_rationale\n---\n## Question\nA? B?\n", "exactly one"),
    ("---\nid: x\nfact: constant\ndimension: decision_rationale\nwhere:\n  - name ~ (\n---\n", "bad regex"),
])
def test_bad_rules_give_clear_errors(text, msg):
    with pytest.raises(RuleError, match=msg):
        parse_rule(text)
