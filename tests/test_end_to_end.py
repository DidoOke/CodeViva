"""Full pipeline on the synthetic demo DB, with and without a (fake) model."""
import json

import pytest

import explain
from artifacts import read_artifact, round_dir
from examiner import ScriptedTransport
from interview import read_answers
from make_demo_db import build
from pipeline import RunContext, run_pipeline
from stages import build_stages, make_context_options
from tests.fakes import FakeModel


@pytest.fixture
def db(tmp_path):
    return str(build(tmp_path / "demo.db"))


def ctx_for(tmp_path, db, sid="1", **opts):
    runs = tmp_path / "runs"
    return RunContext(submission_id=sid, round_no=1, run_dir=round_dir(runs, sid, 1), runs_root=runs, seed=sid,
                      options={**make_context_options(db=db), **opts})


def test_rules_only_full_run(tmp_path, db):
    answers = read_answers(__import__("pathlib").Path("demo_answers/submission1.txt"))
    ctx = ctx_for(tmp_path, db, transport=ScriptedTransport(answers))
    run_pipeline(build_stages(), ctx)
    for name in ["stage0_submission.json", "stage1_facts.json", "stage2_rule_matches.json", "stage3_model_raw.json",
                 "stage4_verified.json", "stage5_plan.json", "transcript.json", "stage7_grades_pass1.json",
                 "stage7_grades_pass2.json", "report.json", "report.md", "stages.md"]:
        assert (ctx.run_dir / name).exists(), name
    t = json.loads((ctx.run_dir / "transcript.json").read_text())
    assert set(t) >= {"conversation_id", "turns", "meta"}
    plan = read_artifact(ctx.run_dir / "stage5_plan.json")["data"]
    assert all(q["citations"] or q["source"]["fact_id"] is None for q in plan["questions"])
    stages_md = (ctx.run_dir / "stages.md").read_text()
    assert "rules triggered" in stages_md and "STALE" not in stages_md


def test_model_run_with_verification_and_explain(tmp_path, db, capsys):
    proposals = {"proposals": [
        {"title": "Heap tie-breaker", "question": "Why does each heap entry carry a sequence number?",
         "why_it_matters": "stable order", "file": "scheduler.py", "line": 87, "commit": "", "fact_ids": [],
         "dimension": "code_understanding", "confidence": "high", "follow_up": "", "good_answer_mentions": ["x"]},
        {"title": "Invented", "question": "Why use Redis?", "why_it_matters": "", "file": "redis_queue.py",
         "line": 3, "commit": "", "fact_ids": [], "dimension": "decision_rationale", "confidence": "high",
         "follow_up": "", "good_answer_mentions": ["x"]},
    ]}
    model = FakeModel(lambda name, **_: proposals if name == "decision_proposals" else {"text": "Why that way?"})
    ctx = ctx_for(tmp_path, db)
    ctx.options.update(model=model, model_reason="")
    run_pipeline(build_stages(), ctx, stop_after="5")
    raw = read_artifact(ctx.run_dir / "stage3_model_raw.json")
    assert raw["meta"]["model"] == "fake-model" and raw["data"]["response"] == proposals
    v = read_artifact(ctx.run_dir / "stage4_verified.json")["data"]
    assert v["accepted"] == 1 and v["results"][1]["reasons"][0].startswith("bad file")
    plan = read_artifact(ctx.run_dir / "stage5_plan.json")["data"]
    mq = [q for q in plan["questions"] if q["source"]["type"] == "model"]
    assert len(mq) == 1 and plan["mode"] == "rules + model"
    assert explain.main([str(ctx.run_dir), mq[0]["id"]]) == 0
    out = capsys.readouterr().out
    assert "stage 3 model" in out and "stage 4 verify accepted as M1" in out and "scheduler.py:87" in out


def test_explain_rule_chain(tmp_path, db, capsys):
    ctx = ctx_for(tmp_path, db)
    run_pipeline(build_stages(), ctx, stop_after="5")
    assert explain.main([str(ctx.run_dir), "Q1"]) == 0
    out = capsys.readouterr().out
    assert "stage 2 rule" in out and "stage 1 fact" in out and "code:" in out and "commit:" in out
    assert explain.main([str(ctx.run_dir), "Q99"]) == 2


def test_same_seed_same_plan_different_db_runs(tmp_path, db):
    a = ctx_for(tmp_path / "a", db)
    b = ctx_for(tmp_path / "b", db)
    run_pipeline(build_stages(), a, stop_after="5")
    run_pipeline(build_stages(), b, stop_after="5")
    qa = read_artifact(a.run_dir / "stage5_plan.json")["data"]["questions"]
    qb = read_artifact(b.run_dir / "stage5_plan.json")["data"]["questions"]
    assert [q["text"] for q in qa] == [q["text"] for q in qb]
