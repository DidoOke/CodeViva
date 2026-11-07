import json

import grade
from grade import DISCLAIMER, MIN_EVIDENCE_WORDS
from kb_match import DIMENSIONS
from llm import ModelError
from tests.fakes import FakeModel

LONG = ("I lowered the retry limit because five attempts without waiting made the test run slow and kept "
        "hammering the failing job, so three attempts with backoff is the trade-off I chose.")
TRANSCRIPT = {"conversation_id": "c", "turns": [
    {"speaker": "examiner", "text": "Why did you lower MAX_RETRIES?", "question_id": "Q1", "kind": "question"},
    {"speaker": "student", "text": LONG, "question_id": "Q1", "kind": "answer"},
    {"speaker": "examiner", "text": "What happens with a long outage?", "question_id": "Q1", "kind": "follow_up"},
    {"speaker": "student", "text": "Jobs fail.", "question_id": "Q1", "kind": "follow_up_answer"},
]}
PLAN = {"round": 1, "questions": [{"id": "Q1", "text": "Why?", "dimension": "decision_rationale",
                                   "good_answer_mentions": ["retry trade-off", "backoff"], "follow_up": ""}]}


def scores(**over):
    base = {d: {"dimension": d, "score": 3, "quotes": [LONG], "justification": "j", "confidence": "high"}
            for d in DIMENSIONS}
    for d, v in over.items():
        base[d] = {**base[d], **v}
    return {"scores": list(base.values())}


def test_clean_model_grading_has_no_flags():
    p1, p2, report = grade.grade(TRANSCRIPT, PLAN, FakeModel([scores(), scores()]))
    assert report["needs_human_review"] is False
    assert report["total"] == 15.0 and report["grader"] == "openai:fake-model"
    assert "Why did you" not in json.dumps(report["dimensions"])  # examiner text never quoted


def test_fabricated_quote_is_dropped_and_flagged():
    fake = {"quotes": ["I wrote a full test suite for every edge case."]}
    _, _, report = grade.grade(TRANSCRIPT, PLAN, FakeModel([scores(code_understanding=fake), scores()]))
    dim = next(d for d in report["dimensions"] if d["dimension"] == "code_understanding")
    assert dim["needs_human_review"] and "missing or unsupported" in dim["review_reasons"][0]
    assert report["dropped_scores"]["pass1"][0]["dimension"] == "code_understanding"


def test_examiner_words_do_not_count_as_student_quotes():
    q = {"quotes": ["Why did you lower MAX_RETRIES?"]}
    _, _, report = grade.grade(TRANSCRIPT, PLAN, FakeModel([scores(decision_rationale=q), scores(decision_rationale=q)]))
    dim = next(d for d in report["dimensions"] if d["dimension"] == "decision_rationale")
    assert dim["score"] is None and dim["needs_human_review"]


def test_thin_evidence_low_confidence_and_disagreement_flags():
    thin = {"quotes": ["Jobs fail."]}
    _, _, report = grade.grade(TRANSCRIPT, PLAN, FakeModel([
        scores(communication_under_follow_up=thin, debugging_failure_handling={"confidence": "low"},
               code_understanding={"score": 4}),
        scores(communication_under_follow_up=thin, code_understanding={"score": 1}),
    ]))
    by = {d["dimension"]: d for d in report["dimensions"]}
    assert any(f"fewer than {MIN_EVIDENCE_WORDS}" in r for r in by["communication_under_follow_up"]["review_reasons"])
    assert any("low confidence" in r for r in by["debugging_failure_handling"]["review_reasons"])
    assert any("disagree by 3" in r for r in by["code_understanding"]["review_reasons"])
    assert report["needs_human_review"]


def test_whitespace_differences_still_verify():
    assert grade.quote_is_verbatim("  three attempts   with backoff ", TRANSCRIPT)


def test_model_failure_uses_heuristic_and_says_so(tmp_path):
    p1, p2, report = grade.grade(TRANSCRIPT, PLAN, FakeModel(lambda **_: ModelError("down")))
    assert report["grader"].startswith("heuristic") and "failed" in report["grader_note"]
    paths = grade.write_outputs(tmp_path, TRANSCRIPT, PLAN, (p1, p2, report), submission_id="9")
    md = paths["report.md"].read_text()
    assert "Draft, pending review" in md and DISCLAIMER in md
    env = json.loads(paths["report.json"].read_text())
    assert env["meta"]["stage"] == "grade" and env["data"]["status"].startswith("DRAFT")
    assert (tmp_path / "stage7_grades_pass1.json").exists() and (tmp_path / "stage7_grades_pass2.json").exists()


def test_cli_with_plain_files(tmp_path, capsys):
    (tmp_path / "t.json").write_text(json.dumps(TRANSCRIPT))
    (tmp_path / "p.json").write_text(json.dumps(PLAN))
    assert grade.main([str(tmp_path / "t.json"), str(tmp_path / "p.json")]) == 0
    assert "needs_human_review" in capsys.readouterr().out
    assert (tmp_path / "report.md").exists()
