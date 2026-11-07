"""Round 2: delta facts, stated-plan check, round-2 rules and the round-aware stage list."""
from pathlib import Path

import pytest

from delta import compute_delta, split_claims, stated_plan, stems_of
from facts import extract_facts
from kb_match import load_rules, match_rules, parse_rule
from llm import ModelError
from make_round2_samples import ROUND1_PLAN_ANSWERS, round2_submission_1, round2_submission_2
from make_sample_repo import submission_1, submission_2
from rounds import kb_for_round, round_stages
from tests.fakes import FakeModel

ROUND2_KB = ["kb/rounds", "kb/task_scheduler/round2"]
ROUND2_RULES = sorted(p for d in ROUND2_KB for p in Path(d).glob("*.md") if p.name not in ("README.md", "spec.md"))
PLAN_Q = {"questions": [{"id": "Q5", "text": "next?", "source": {"type": "rule", "rule_id": "g-next-iteration-plan"}}]}


def transcript(*answers, qid="Q5"):
    return {"turns": [{"speaker": "examiner", "text": "next?", "question_id": qid}]
            + [{"speaker": "student", "text": a, "question_id": qid} for a in answers]}


def delta_for(r1, r2, answers=None, model=None, plan=PLAN_Q):
    tr = transcript(*answers) if answers is not None else None
    return compute_delta(r1, r2, extract_facts(r1)["facts"], extract_facts(r2)["facts"], plan, tr, model)


@pytest.fixture(scope="module")
def d1():
    return delta_for(submission_1(), round2_submission_1(), list(ROUND1_PLAN_ANSWERS["1"]))


@pytest.fixture(scope="module")
def d2():
    return delta_for(submission_2(), round2_submission_2(), list(ROUND1_PLAN_ANSWERS["2"]))


def structure_swap_pair():
    """Round 1 pops the front of a list; round 2 uses a deque."""
    old = "def take(q):\n    item = q.pop(0)\n    return item\n"
    new = "from collections import deque\n\n\ndef take(q):\n    item = q.popleft()\n    return item\n"
    r1 = {"files": {"a.py": old}, "commits": [{"sha": "a" * 40, "message": "first", "files": {"a.py": old}}]}
    r2 = {"files": {"a.py": new}, "commits": r1["commits"] + [{"sha": "b" * 40, "message": "use a deque",
                                                                "files": {"a.py": new}}]}
    return r1, r2


# --------------------------------------------------------------------------- code delta

def by_kind(d, kind):
    return [f for f in d["delta_facts"] if f["kind"] == kind]


def test_round2_history_continues_round1():
    r1, r2 = submission_1(), round2_submission_1()
    assert [c["sha"] for c in r2["commits"][:len(r1["commits"])]] == [c["sha"] for c in r1["commits"]]


def test_constant_change_attributed_to_the_commit_that_made_it(d1):
    (c,) = by_kind(d1, "round_constant_changed")
    assert (c["name"], c["old"], c["new"]) == ("MAX_RETRIES", 3, 4)
    assert "raise MAX_RETRIES" in c["commit_message"]


def test_imports_functions_and_fix_commit(d1):
    assert {f["module"] for f in by_kind(d1, "import_added")} == {"threading", "concurrent.futures"}
    assert "find_blocked" in {f["function"] for f in by_kind(d1, "function_added")}
    (sched,) = [f for f in by_kind(d1, "function_changed") if f["function"] == "schedule"]
    assert sched["churn"] >= 0.5 and "thread pool" in sched["commit_message"]
    (fix,) = by_kind(d1, "round_fix_commit")
    assert fix["commit_message"].startswith("fix: two workers")
    assert d1["history_rewritten"] is False and len(d1["new_commits"]) == 5


def test_round1_facts_are_not_carried_into_round2(d1):
    kinds = {(f["kind"], f.get("structure")) for f in d1["facts"]}
    assert ("data_structure", "heapq") not in kinds  # asked about in round 1, unchanged
    assert d1["carried_fact_count"] > 0
    assert all(f["id"].startswith(("F", "D")) for f in d1["facts"])


def test_structure_removed():
    r1, r2 = structure_swap_pair()
    d = compute_delta(r1, r2, extract_facts(r1)["facts"], extract_facts(r2)["facts"])
    (f,) = by_kind(d, "structure_removed")
    assert f["structure"] == "list_pop_front" and f["label"] == "`.pop(0)`" and f["function"] == "take" and f["commit_message"] == "use a deque"


def test_rewritten_history_is_flagged():
    r1, r2 = structure_swap_pair()
    r2 = {**r2, "commits": r2["commits"][1:]}
    assert compute_delta(r1, r2, [], [])["history_rewritten"] is True


# --------------------------------------------------------------------------- stated plan

def test_plan_followed_is_found_with_evidence(d1):
    items = d1["plan_items"]
    assert len(items) == 3 and all(i["status"] == "found" for i in items)
    assert items[0]["claim"] == "I would detect dependency cycles"  # reason clause trimmed
    assert any(e.get("file") == "tests/test_scheduler.py" for e in items[2]["evidence"])
    for i in items:
        locs = [(e.get("file"), e.get("line"), e.get("commit")) for e in i["evidence"]]
        assert len(locs) == len(set(locs))


def test_vague_plan_not_followed_has_no_evidence(d2):
    assert [i["status"] for i in d2["plan_items"]] == ["no_evidence", "no_evidence"]
    assert [f["claim"] for f in by_kind(d2, "plan_item")] == ["Make it faster", "Probably test it"]


def test_stated_plan_ignores_repeat_and_pass_turns():
    p = stated_plan(PLAN_Q, transcript("repeat", "I would add a cache.", "was that right?"))
    assert p["answers"] == ["I would add a cache."]
    assert stated_plan(PLAN_Q, transcript("pass"))["status"] == "passed"
    assert stated_plan(PLAN_Q, None)["status"] == "missing"
    assert stated_plan({"questions": []}, transcript("x"))["status"] == "missing"


def test_missing_previous_transcript_gives_no_plan_items():
    d = delta_for(submission_1(), round2_submission_1(), answers=None)
    assert d["plan_items"] == [] and d["stated_plan"]["status"] == "missing"


def test_model_claims_must_be_verbatim():
    answer = "I would add a cache for results. Then I would write a benchmark."
    fake = FakeModel([{"claims": [{"quote": "add a cache for results", "keywords": ["cache"]},
                                  {"quote": "improve performance generally", "keywords": []}]}])
    out = split_claims([answer], fake)
    assert [c["quote"] for c in out["claims"]] == ["add a cache for results"]
    assert out["dropped_not_verbatim"] == ["improve performance generally"]
    assert out["mode"].startswith("model")


def test_model_failure_falls_back_to_sentences():
    out = split_claims(["I would add a cache. Then a benchmark."], FakeModel([ModelError("down")]))
    assert out["mode"].startswith("sentences (model fallback") and len(out["claims"]) == 2


def test_claim_text_never_adds_a_question_mark():
    d = delta_for(submission_2(), round2_submission_2(), ["Should I add retries? Maybe."])
    assert all("?" not in f["claim"] for f in by_kind(d, "plan_item"))


def test_stems_split_identifiers():
    assert {"find", "block"} <= set(stems_of("find_blocked"))
    assert stems_of("cycles") == stems_of("cycle")


# --------------------------------------------------------------------------- rules

@pytest.fixture(scope="module")
def round2_facts(d1, d2):
    r1, r2 = structure_swap_pair()
    swap = compute_delta(r1, r2, extract_facts(r1)["facts"], extract_facts(r2)["facts"])
    return {"1": d1["facts"], "2": d2["facts"], "swap": swap["facts"]}


@pytest.mark.parametrize("path", ROUND2_RULES, ids=lambda p: p.stem)
def test_round2_rule_parses_and_fires(path, round2_facts):
    rule = parse_rule(path.read_text(), str(path))
    assert rule.id == path.stem
    fired = []
    for sid, facts in round2_facts.items():
        (entry,) = match_rules([rule], facts, seed=sid)
        if entry["triggered"]:
            assert "{" not in entry["question"] and entry["question"].count("?") == 1
            fired.append(sid)
    assert fired, f"{rule.id} fires on no round-2 fixture"


def test_kb_for_round():
    base = ["kb/generic", "kb/task_scheduler"]
    assert kb_for_round(base, 1) == base
    assert kb_for_round(base, 2) == base + ["kb/rounds", "kb/task_scheduler/round2"]
    assert kb_for_round(base, 3) == base + ["kb/rounds"]  # no round3 dir yet
    ids = [r.id for r in load_rules(kb_for_round(base, 2))]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- stage list and end to end

def test_round_stages_round1_unchanged_round2_inserts_delta():
    from stages import build_stages
    base = build_stages()
    assert round_stages(base, 1) == base
    r2 = round_stages(base, 2, code_from="11")
    ids = [s.id for s in r2]
    assert ids.index("1d") == ids.index("1") + 1
    for s in r2:
        if s.id in {"2", "3", "4", "5"}:
            assert "1d" in s.requires
    assert [s.requires for s in base if s.id == "2"] == [["1"]]  # base list not mutated


def test_round1_then_round2_end_to_end(tmp_path):
    from artifacts import read_artifact, round_dir
    from examiner import ScriptedTransport
    from interview import read_answers
    from make_demo_db import build
    from make_round2_samples import add_to_db
    from pipeline import RunContext, run_pipeline
    from stages import DEFAULT_KB, build_stages, make_context_options

    db = build(tmp_path / "demo.db")
    assert add_to_db(db) == ["11", "12"] and add_to_db(db) == []
    runs = tmp_path / "runs"

    def ctx(round_no, **opts):
        return RunContext(submission_id="1", round_no=round_no, run_dir=round_dir(runs, "1", round_no),
                          runs_root=runs, seed="1",
                          options=make_context_options(db=str(db), kb_dirs=kb_for_round(DEFAULT_KB, round_no), **opts))

    answers = read_answers(Path("demo_answers/submission1.txt"))
    run_pipeline(build_stages(), ctx(1, transport=ScriptedTransport(answers)), stop_after="6")
    c2 = ctx(2)
    run_pipeline(round_stages(build_stages(), 2, code_from="11"), c2, stop_after="5")

    delta = read_artifact(c2.run_dir / "stage1d_delta.json")["data"]
    assert delta["stated_plan"]["status"] == "ok"
    assert any(i["status"] == "found" and "cycle" in i["claim"] for i in delta["plan_items"])
    plan = read_artifact(c2.run_dir / "stage5_plan.json")["data"]
    assert plan["round"] == 2
    rule_ids = {q["source"].get("rule_id") for q in plan["questions"]}
    assert rule_ids & {"r-plan-found", "r-plan-no-evidence"}
    assert "ts2-shared-state" in rule_ids
    assert "ts-heap-ready-queue" not in rule_ids  # round-1 question not repeated
    assert "STALE" not in (c2.run_dir / "stages.md").read_text()
