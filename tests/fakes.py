"""Fake model clients for tests: no network, no API key."""
from typing import Any, Callable, Dict, List, Union

from llm import ModelError

Reply = Union[Dict[str, Any], Exception]


class FakeModel:
    """JSONModel stand-in. `replies` is a list (consumed in order) or a callable(system, user, name)."""

    def __init__(self, replies: Union[List[Reply], Callable[..., Reply]], model: str = "fake-model"):
        self.model = model
        self.replies = replies
        self.calls: List[Dict[str, Any]] = []

    def complete_json(self, *, system: str, user: str, schema: Dict[str, Any], name: str) -> Dict[str, Any]:
        self.calls.append({"system": system, "user": user, "name": name, "schema": schema})
        reply = self.replies(system=system, user=user, name=name) if callable(self.replies) else self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeOpenAIClient:
    """Mimics openai.OpenAI().chat.completions.create for OpenAIJSONModel."""

    def __init__(self, contents: List[Union[str, Exception]]):
        self.contents = list(contents)
        self.calls: List[Dict[str, Any]] = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.contents.pop(0)
        if isinstance(item, Exception):
            raise item

        class Msg:
            content = item
            refusal = None

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]

        return Resp()


def failing_model() -> FakeModel:
    return FakeModel(lambda **_: ModelError("down"))
