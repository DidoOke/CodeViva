"""Stage 6: turn-based interview where CODE controls the flow.

- Code picks every main question from the plan and asks it verbatim.
- The model (optional) only phrases one short follow-up per question and nothing else.
- Every examiner turn is checked in code: at most one question mark. A model follow-up
  with more than one question is sent back for a re-ask; after that, the lecturer's
  follow-up text is used instead.
- "repeat" repeats the current question verbatim. Grades, scores and answer notes are never
  revealed; requests for feedback get a fixed neutral reply.
- No time limits: a student may take as long as they need (fairness for slower speakers).

Transports: TextTransport (terminal), ScriptedTransport (tests, demos) and VoiceTransport,
a stub where an ElevenLabs agent plugs in later.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from llm import JSONModel, ModelError, strict_object

INTRO = (
    "Hello. This is a short conversation about the code you submitted: about {n} questions, "
    "each about something you built. There is no time limit, so take as long as you need. "
    "Type 'repeat' to see a question again, or 'pass' to skip one. "
    "I won't comment on answers during the conversation; you'll receive a written report afterwards. "
    "If you would prefer a different format, your course team can arrange one."
)
CLOSING = ("That's all the questions. Thank you for your time. Your answers will be reviewed by a member "
           "of staff, and you will receive a written report.")
NO_FEEDBACK = "I can't comment on answers during the conversation; you'll get a report afterwards."
PASS_ACK = "That's fine, we'll move on."
ACKS = ["Thank you.", "Okay, thanks.", "Thanks for explaining.", "Thank you, noted."]
GENERIC_FOLLOW_UP = "Could you say a little more about how that works in your code?"
MAX_REPEATS = 3
MAX_FOLLOW_UP_WORDS = 40

REPEAT_RE = re.compile(r"^\s*(repeat|again|say (that|it) again|can you repeat|could you repeat|pardon|sorry\??|what\??)"
                       r"[\s.!?]*(that|the question|please)?[\s.!?]*$", re.I)
PASS_RE = re.compile(r"^\s*(pass|skip|i don'?t know|no idea|next)[\s.!]*$", re.I)
FEEDBACK_RE = re.compile(r"(was (that|i|it) (right|correct|wrong|ok)|is (that|it) (right|correct)|"
                         r"how did i do|what('?s| is) the (right |correct )?answer|my (grade|score|mark)|"
                         r"what (grade|score|mark))", re.I)
EVALUATIVE_RE = re.compile(r"\b(correct|incorrect|wrong|right answer|grade|score|marks?|excellent|great answer|"
                           r"good answer|perfect|well done)\b", re.I)


def count_questions(text: str) -> int:
    return text.count("?")


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


# --------------------------------------------------------------------------- transports

class InterviewTransport(ABC):
    """How examiner turns reach the student and answers come back."""

    @abstractmethod
    def send(self, text: str) -> None:
        ...

    @abstractmethod
    def receive(self) -> Optional[str]:
        """The student's next answer, or None if the session ended."""

    def close(self) -> None:
        pass


class TextTransport(InterviewTransport):
    """Terminal chat. Also the text-only alternative for students who opt out of voice."""

    def __init__(self, input_fn: Callable[[str], str] = input, output_fn: Callable[[str], None] = print):
        self._input, self._output = input_fn, output_fn

    def send(self, text: str) -> None:
        self._output(f"\nExaminer: {text}\n")

    def receive(self) -> Optional[str]:
        try:
            return self._input("You: ")
        except (EOFError, KeyboardInterrupt):
            return None


class ScriptedTransport(InterviewTransport):
    """Replays prepared answers (tests and demos)."""

    def __init__(self, answers: List[str], echo: Optional[Callable[[str], None]] = None):
        self.answers = list(answers)
        self.sent: List[str] = []
        self._echo = echo

    def send(self, text: str) -> None:
        self.sent.append(text)
        if self._echo:
            self._echo(f"\nExaminer: {text}")

    def receive(self) -> Optional[str]:
        if not self.answers:
            return None
        answer = self.answers.pop(0)
        if self._echo:
            self._echo(f"Student: {answer}")
        return answer


class VoiceTransport(InterviewTransport):
    """>>> VOICE SEAM: ElevenLabs plugs in here (not implemented in this build). <<<

    Plan for the integration:
      - Create an ElevenLabs conversational agent whose prompt is agent_prompt.md, with a calm,
        neutral voice (never a cloned staff voice) and a silence tolerance of at least 30 s.
      - Pass the plan as dynamic variables: plan_to_dynamic_variables(plan) below.
      - Keep the one-question-per-turn rule in code: run each examiner turn through
        Examiner.validate_turn() before it is spoken (server tool or custom LLM endpoint).
      - Receive the post-call webhook and convert it with transcript_from_voice() into the
        same transcript.json shape, so grading is unchanged.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        raise NotImplementedError("voice transport is a placeholder; use --text (TextTransport) for now")

    def send(self, text: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def receive(self) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError


def plan_to_dynamic_variables(plan: Dict[str, Any]) -> Dict[str, str]:
    """Per-student variables for a voice agent. Questions only: never grading notes."""
    out = {"question_count": str(len(plan["questions"]))}
    for q in plan["questions"]:
        out[f"{q['id'].lower()}_text"] = q["text"]
        out[f"{q['id'].lower()}_follow_up"] = q.get("follow_up", "")
    return out


def transcript_from_voice(payload: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
    """Placeholder: map an ElevenLabs post-call webhook payload to transcript.json."""
    raise NotImplementedError("map the provider's transcript to {'conversation_id', 'turns': [...]}")


# --------------------------------------------------------------------------- examiner

FOLLOW_UP_SCHEMA = strict_object({"text": {"type": "string"}})
FOLLOW_UP_SYSTEM = """You are a calm, neutral oral examiner for a programming course.
Write ONE short follow-up question (at most 30 words, exactly one question mark) that probes
the student's last answer more deeply, about their own code. Do not evaluate the answer, do
not say whether it is right, do not hint at what a good answer contains, and do not ask two
things at once. Plain, simple English."""


class Examiner:
    def __init__(self, plan: Dict[str, Any], transport: InterviewTransport,
                 phraser: Optional[JSONModel] = None, conversation_id: str = "conversation"):
        self.plan = plan
        self.transport = transport
        self.phraser = phraser
        self.conversation_id = conversation_id
        self.turns: List[Dict[str, Any]] = []
        self.stats = {"examiner_turns": 0, "multi_question_rejections": 0, "follow_up_fallbacks": 0,
                      "model_follow_ups": 0, "repeats": 0, "passes": 0, "feedback_requests": 0,
                      "ended_early": False}
        self._ack_i = 0

    # -- turn plumbing ------------------------------------------------------
    @staticmethod
    def validate_turn(text: str) -> None:
        """Code-level guard: an examiner turn may contain at most one question."""
        if count_questions(text) > 1:
            raise ValueError(f"examiner turn has {count_questions(text)} questions: {text!r}")

    def _say(self, text: str, kind: str, question_id: Optional[str] = None) -> None:
        self.validate_turn(text)
        self.transport.send(text)
        self.stats["examiner_turns"] += 1
        self.turns.append({"speaker": "examiner", "text": text, "kind": kind, "question_id": question_id})

    def _hear(self, question_id: Optional[str], kind: str) -> Optional[str]:
        text = self.transport.receive()
        if text is None:
            return None
        self.turns.append({"speaker": "student", "text": text, "kind": kind, "question_id": question_id})
        return text

    def _ack(self) -> str:
        ack = ACKS[self._ack_i % len(ACKS)]  # rotation in code; no randomness from the model
        self._ack_i += 1
        return ack

    # -- follow-up phrasing --------------------------------------------------
    def _valid_follow_up(self, text: str) -> Optional[str]:
        text = " ".join(text.split())
        if count_questions(text) != 1:
            return f"it contained {count_questions(text)} question marks; write exactly one question"
        if word_count(text) > MAX_FOLLOW_UP_WORDS:
            return "it was too long; keep it under 30 words"
        if EVALUATIVE_RE.search(text):
            return "it evaluated the answer; stay neutral"
        return None

    def follow_up_for(self, question: Dict[str, Any], answer: str) -> str:
        fallback = question.get("follow_up") or GENERIC_FOLLOW_UP
        if self.phraser is None:
            return fallback
        user = (f"Main question: {question['text']}\nStudent's answer: {answer}\n"
                f"Lecturer's suggested follow-up (adapt it to the answer): {question.get('follow_up') or '(none)'}")
        for _ in range(2):  # original + one re-ask
            try:
                text = self.phraser.complete_json(system=FOLLOW_UP_SYSTEM, user=user,
                                                  schema=FOLLOW_UP_SCHEMA, name="follow_up")["text"]
            except (ModelError, KeyError, TypeError):
                break
            problem = self._valid_follow_up(text)
            if problem is None:
                self.stats["model_follow_ups"] += 1
                return " ".join(text.split())
            self.stats["multi_question_rejections"] += problem.startswith("it contained")
            user += f"\nYour previous reply was rejected because {problem}. Try again."
        self.stats["follow_up_fallbacks"] += 1
        return fallback

    # -- one exchange --------------------------------------------------------
    def _ask(self, text: str, qid: str, kind: str, prefix: str = "") -> Optional[str]:
        """Ask, handling repeat / feedback requests. Returns the answer, '' for pass, None if ended."""
        self._say(f"{prefix} {text}".strip(), kind, qid)
        repeats = 0
        while True:
            answer = self._hear(qid, "answer" if kind == "question" else "follow_up_answer")
            if answer is None:
                return None
            if REPEAT_RE.match(answer) and repeats < MAX_REPEATS:
                repeats += 1
                self.stats["repeats"] += 1
                self._say(text, "repeat", qid)  # verbatim
                continue
            if FEEDBACK_RE.search(answer) and repeats < MAX_REPEATS:
                repeats += 1
                self.stats["feedback_requests"] += 1
                self._say(f"{NO_FEEDBACK} Here is the question again: {text}", "no_feedback", qid)
                continue
            if PASS_RE.match(answer):
                self.stats["passes"] += 1
                return ""
            return answer

    def run(self) -> Dict[str, Any]:
        questions = self.plan["questions"]
        self._say(INTRO.format(n=len(questions)), "intro")
        prefix = ""
        for q in questions:
            answer = self._ask(q["text"], q["id"], "question", prefix)
            if answer is None:
                self.stats["ended_early"] = True
                break
            if answer == "":
                prefix = PASS_ACK
                continue
            follow = self.follow_up_for(q, answer)
            fa = self._ask(follow, q["id"], "follow_up", self._ack())
            if fa is None:
                self.stats["ended_early"] = True
                break
            prefix = PASS_ACK if fa == "" else self._ack()
        self._say(CLOSING if not self.stats["ended_early"] else "The session has ended. Thank you.", "closing")
        self.transport.close()
        return {"conversation_id": self.conversation_id, "turns": self.turns, "stats": self.stats}
