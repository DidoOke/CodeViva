import pytest

from examiner import (NO_FEEDBACK, Examiner, ScriptedTransport, TextTransport, VoiceTransport,
                      plan_to_dynamic_variables)
from llm import ModelError
from tests.fakes import FakeModel

PLAN = {"questions": [
    {"id": "Q1", "text": "Why is MAX_RETRIES 3?", "follow_up": "What if it were 30?",
     "good_answer_mentions": ["SECRET-NOTE latency trade-off"], "dimension": "decision_rationale"},
    {"id": "Q2", "text": "What does skip_dependents do?", "follow_up": "",
     "good_answer_mentions": ["SECRET-NOTE transitive"], "dimension": "code_understanding"},
]}


def run(answers, phraser=None):
    t = ScriptedTransport(answers)
    transcript = Examiner(PLAN, t, phraser=phraser, conversation_id="c1").run()
    return t, transcript


def examiner_texts(transcript):
    return [x["text"] for x in transcript["turns"] if x["speaker"] == "examiner"]


def test_shape_and_order_controlled_by_code():
    t, tr = run(["a1", "f1", "a2", "f2"])
    assert tr["conversation_id"] == "c1"
    assert all(set(x) >= {"speaker", "text"} and x["speaker"] in ("examiner", "student") for x in tr["turns"])
    texts = examiner_texts(tr)
    assert "Why is MAX_RETRIES 3?" in texts[1] and "What if it were 30?" in texts[2]
    assert "What does skip_dependents do?" in texts[3]
    assert tr["stats"]["ended_early"] is False


def test_every_examiner_turn_has_at_most_one_question():
    _, tr = run(["a1", "f1", "a2", "f2"])
    assert all(x.count("?") <= 1 for x in examiner_texts(tr))


def test_repeat_is_verbatim_and_notes_never_leak():
    t, tr = run(["repeat", "a1", "was that right?", "f1", "a2", "f2"])
    texts = examiner_texts(tr)
    assert texts[2] == "Why is MAX_RETRIES 3?"
    assert any(NO_FEEDBACK in x for x in texts)
    assert not any("SECRET-NOTE" in x for x in t.sent)


def test_pass_skips_follow_up():
    _, tr = run(["pass", "a2", "f2"])
    texts = examiner_texts(tr)
    assert "we'll move on" in texts[2] and "What does skip_dependents do?" in texts[2]
    assert tr["stats"]["passes"] == 1


def test_stacked_model_follow_up_is_rejected_and_re_asked():
    phraser = FakeModel([{"text": "Why 3? And why not 4?"}, {"text": "What would change with a slower dependency?"},
                         {"text": "How is it called?"}])
    _, tr = run(["a1", "f1", "a2", "f2"], phraser)
    texts = examiner_texts(tr)
    assert "What would change with a slower dependency?" in texts[2]
    assert tr["stats"]["multi_question_rejections"] == 1
    assert "SECRET-NOTE" not in "".join(c["user"] for c in phraser.calls)  # notes never sent to phraser


def test_persistent_bad_follow_ups_fall_back_to_kb_text():
    phraser = FakeModel(lambda **_: {"text": "Great answer, correct! Why? How?"})
    _, tr = run(["a1", "f1", "a2", "f2"], phraser)
    texts = examiner_texts(tr)
    assert texts[2].endswith("What if it were 30?")
    assert tr["stats"]["follow_up_fallbacks"] == 2


def test_model_outage_falls_back():
    _, tr = run(["a1", "f1", "a2", "f2"], FakeModel(lambda **_: ModelError("down")))
    assert examiner_texts(tr)[2].endswith("What if it were 30?")


def test_session_ending_early():
    _, tr = run(["a1"])
    assert tr["stats"]["ended_early"] is True


def test_validate_turn_guard():
    with pytest.raises(ValueError):
        Examiner.validate_turn("Why? How?")


def test_text_transport_and_voice_stub():
    out = []
    t = TextTransport(input_fn=lambda _: (_ for _ in ()).throw(EOFError()), output_fn=out.append)
    t.send("hello")
    assert t.receive() is None and "hello" in out[0]
    with pytest.raises(NotImplementedError):
        VoiceTransport()
    dv = plan_to_dynamic_variables(PLAN)
    assert dv["q1_text"] == "Why is MAX_RETRIES 3?" and "SECRET" not in str(dv)
