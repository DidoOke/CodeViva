import json

import pytest

from llm import GeminiJSONModel, ModelError, ProviderHTTPError, get_model, strict_object, to_gemini_schema

SCHEMA = strict_object({"text": {"type": "string"}, "n": {"type": "integer", "minimum": 0},
                        "tags": {"type": "array", "items": {"type": "string", "enum": ["a", "b"]}}})


def ok(payload):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}, "finishReason": "STOP"}]}


class Post:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def test_schema_conversion_drops_unsupported_keys():
    g = to_gemini_schema(SCHEMA)
    assert g["type"] == "OBJECT" and "additionalProperties" not in g
    assert g["propertyOrdering"] == ["text", "n", "tags"]
    assert g["properties"]["tags"]["items"] == {"type": "STRING", "enum": ["a", "b"]}
    assert g["properties"]["n"]["minimum"] == 0


def test_request_shape_key_in_header_not_url(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gem-test")
    monkeypatch.setenv("GEMINI_API_KEY", "secret-123")
    post = Post([ok({"text": "hi", "n": 1, "tags": []})])
    m = GeminiJSONModel(post=post)
    m._key = "secret-123"
    assert m.complete_json(system="sys", user="usr", schema=SCHEMA, name="x") == {"text": "hi", "n": 1, "tags": []}
    call = post.calls[0]
    assert "gem-test:generateContent" in call["url"] and "secret" not in call["url"]
    assert call["headers"] == {"x-goog-api-key": "secret-123"}
    assert call["body"]["systemInstruction"]["parts"][0]["text"] == "sys"
    assert call["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_one_retry_then_clear_error(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "g")
    m = GeminiJSONModel(post=Post([TimeoutError(), ok({"text": "x", "n": 0, "tags": []})]))
    assert m.complete_json(system="s", user="u", schema=SCHEMA, name="x")["text"] == "x"
    m = GeminiJSONModel(post=Post([ProviderHTTPError(403, "PERMISSION_DENIED")] * 2))
    with pytest.raises(ModelError, match="HTTP 403 PERMISSION_DENIED"):
        m.complete_json(system="s", user="u", schema=SCHEMA, name="x")
    m = GeminiJSONModel(post=Post([{"promptFeedback": {"blockReason": "SAFETY"}}] * 2))
    with pytest.raises(ModelError, match="SAFETY"):
        m.complete_json(system="s", user="u", schema=SCHEMA, name="x")


def test_provider_selection(monkeypatch):
    assert get_model(False)[1] == "model layer not requested"
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    model, why = get_model(True)
    assert model is None and "gemini unavailable: GEMINI_MODEL" in why
    monkeypatch.setenv("GEMINI_MODEL", "g")
    model, _ = get_model(True)
    assert model.provider == "gemini" and model.model == "g"
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert "openai unavailable" in get_model(True)[1]
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    assert "unknown LLM_PROVIDER" in get_model(True)[1]
