import json

import pytest

import analyse
from facts import extract_facts
from kb_match import load_rules, match_rules
from llm import ModelError, OpenAIJSONModel, get_model
from make_sample_repo import submission_1
from tests.fakes import FakeModel, FakeOpenAIClient


@pytest.fixture(scope="module")
def ctx():
    sub = submission_1()
    facts = extract_facts(sub)["facts"]
    matches = match_rules(load_rules(["kb/generic", "kb/task_scheduler"]), facts, seed="1")
    return sub, facts, matches


def proposal(**over):
    p = {"title": "Tie-breaker in heap entries", "question": "Why does each heap entry include a sequence number?",
         "why_it_matters": "avoids comparing dicts", "file": "scheduler.py", "line": 87, "commit": "",
         "fact_ids": [], "dimension": "code_understanding", "confidence": "high",
         "follow_up": "", "good_answer_mentions": ["stable order"]}
    p.update(over)
    return p


def test_model_name_comes_from_env(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ModelError, match="OPENAI_MODEL"):
        OpenAIJSONModel(client=FakeOpenAIClient([]))
    monkeypatch.setenv("OPENAI_MODEL", "some-model")
    m = OpenAIJSONModel(client=FakeOpenAIClient(['{"ok": 1}']))
    assert m.complete_json(system="s", user="u", schema={}, name="n") == {"ok": 1}
    call = m._client.calls[0]
    assert call["model"] == "some-model" and call["response_format"]["json_schema"]["strict"] is True
    assert "timeout" in call


def test_one_retry_then_success_and_then_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "m")
    m = OpenAIJSONModel(client=FakeOpenAIClient([TimeoutError("slow"), '{"a": 2}']))
    assert m.complete_json(system="s", user="u", schema={}, name="n") == {"a": 2}
    m = OpenAIJSONModel(client=FakeOpenAIClient([TimeoutError("x"), "not json"]))
    with pytest.raises(ModelError, match="after 2 attempts"):
        m.complete_json(system="s", user="u", schema={}, name="n")


def test_missing_key_falls_back(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    model, reason = get_model(True)
    assert model is None and "OPENAI_API_KEY" in reason


def test_raw_response_saved_untouched_and_prompt_has_no_identity(ctx):
    sub, facts, matches = ctx
    response = {"proposals": [proposal()]}
    model = FakeModel([response])
    raw = analyse.propose(model, "", sub["files"], sub["commits"], facts, matches, "spec")
    assert raw == {"status": "ok", "reason": "", "model": "fake-model", "response": response}
    prompt = model.calls[0]["user"]
    assert "   1  \"\"\"Batch job scheduler" in prompt  # line-numbered code
    assert "synthetic" not in prompt and "label" not in prompt  # no submission label/id sent


def test_model_failure_falls_back_to_rules_only(ctx):
    sub, facts, matches = ctx
    raw = analyse.propose(FakeModel([ModelError("boom")]), "", sub["files"], sub["commits"], facts, matches, "")
    assert raw["status"] == "failed" and raw["response"] is None
    v = analyse.verify(raw, sub["files"], sub["commits"], facts, matches)
    assert v["accepted"] == 0 and v["results"] == []


def test_verification_accepts_and_rejects_with_reasons(ctx):
    sub, facts, matches = ctx
    heap_line = next(f["line"] for f in facts if f.get("structure") == "heapq")
    proposals = [
        proposal(),                                                     # ok
        proposal(file="../etc/passwd"),                                 # bad file
        proposal(line=9999),                                            # bad line
        proposal(commit="deadbeefcafe"),                                # unknown commit
        proposal(confidence="low", line=40),                            # low confidence
        proposal(question="Why a heap? And why seq?", line=40),         # stacked question
        proposal(line=heap_line, question="Why did you use a heap to pick the next job instead of a sorted list?"),
        proposal(line=90, commit=sub["commits"][1]["sha"][:7], fact_ids=["F999"]),  # ok, drops unknown fact id
    ]
    raw = {"status": "ok", "reason": "", "model": "fake", "response": {"proposals": proposals}}
    v = analyse.verify(raw, sub["files"], sub["commits"], facts, matches)
    reasons = [r["reasons"][0].split(":")[0] if r["reasons"] else "accepted" for r in v["results"]]
    assert reasons[0] == "accepted" and reasons[7] == "accepted"
    assert reasons[1] == "bad file" and reasons[2] == "bad line" and reasons[3] == "unknown commit"
    assert reasons[4] == "low confidence reported by the model"
    assert reasons[5] == "question must contain exactly one '?'"
    assert reasons[6].startswith("duplicates rule question")
    assert v["results"][7]["dropped_fact_ids"] == ["F999"] and v["results"][7]["commit"] == sub["commits"][1]["sha"]
    assert [r.get("proposal_id") for r in v["results"] if r["accepted"]] == ["M1", "M2"]
