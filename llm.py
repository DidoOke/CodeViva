"""Thin model client: structured JSON output, timeout, one retry. Injectable for tests.

Every caller depends only on the JSONModel protocol (`.provider`, `.model`, `.complete_json`),
so tests pass a fake. Two providers:

    gemini   Google Gemini REST API (standard library only). GEMINI_API_KEY (or GOOGLE_API_KEY)
             and GEMINI_MODEL. The key travels in the x-goog-api-key header, never in the URL.
    openai   OpenAI SDK. OPENAI_API_KEY and OPENAI_MODEL.

LLM_PROVIDER picks one explicitly; otherwise Gemini is used when a Gemini key is present.
Model names come from the environment only. Keys are never logged, printed or stored.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol, Tuple

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_SCHEMA_KEYS = {"type", "properties", "required", "items", "enum", "description", "minimum",
                      "maximum", "nullable", "format", "minItems", "maxItems"}


class ModelError(RuntimeError):
    pass


class JSONModel(Protocol):
    provider: str
    model: str

    def complete_json(self, *, system: str, user: str, schema: Dict[str, Any], name: str) -> Dict[str, Any]:
        ...


# --------------------------------------------------------------------------- OpenAI

class OpenAIJSONModel:
    provider = "openai"

    def __init__(self, model: Optional[str] = None, timeout: float = 60.0, client: Any = None):
        self.model = model or os.environ.get("OPENAI_MODEL", "")
        if not self.model:
            raise ModelError("OPENAI_MODEL is not set (the model name is never hard-coded)")
        self.timeout = timeout
        if client is None:
            if not os.environ.get("OPENAI_API_KEY"):
                raise ModelError("OPENAI_API_KEY is not set")
            try:
                from openai import OpenAI  # type: ignore
            except ImportError:
                raise ModelError("the 'openai' package is not installed (pip install openai)") from None
            client = OpenAI(timeout=timeout, max_retries=0)  # we do our own single retry
        self._client = client

    def complete_json(self, *, system: str, user: str, schema: Dict[str, Any], name: str) -> Dict[str, Any]:
        last: Optional[BaseException] = None
        for _attempt in range(2):  # one try + one retry
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_schema",
                                     "json_schema": {"name": name, "schema": schema, "strict": True}},
                    timeout=self.timeout,
                )
                msg = resp.choices[0].message
                if getattr(msg, "refusal", None):
                    raise ModelError("model refused the request")
                return json.loads(msg.content)
            except Exception as exc:  # network, timeout, bad JSON, refusal
                last = exc
        # type name only: exception text can echo request details
        raise ModelError(f"model call failed after 2 attempts ({type(last).__name__})")


# --------------------------------------------------------------------------- Gemini

class ProviderHTTPError(RuntimeError):
    """HTTP failure with only safe details: status code and the provider's error status."""

    def __init__(self, code: int, status: str):
        super().__init__(f"HTTP {code} {status}".strip())
        self.code, self.status = code, status


PostFn = Callable[[str, Dict[str, Any], Dict[str, str], float], Dict[str, Any]]


def http_post_json(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            status = json.loads(exc.read() or b"{}").get("error", {}).get("status", "")
        except ValueError:
            status = ""
        raise ProviderHTTPError(exc.code, status) from None


def to_gemini_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """JSON Schema (OpenAI strict style) -> Gemini responseSchema (OpenAPI subset)."""
    out: Dict[str, Any] = {}
    for key, value in schema.items():
        if key not in GEMINI_SCHEMA_KEYS:
            continue  # e.g. additionalProperties is not supported
        if key == "type":
            out["type"] = str(value).upper()
        elif key == "properties":
            out["properties"] = {k: to_gemini_schema(v) for k, v in value.items()}
            out["propertyOrdering"] = list(value)
        elif key == "items":
            out["items"] = to_gemini_schema(value)
        else:
            out[key] = value
    return out


class GeminiJSONModel:
    provider = "gemini"

    def __init__(self, model: Optional[str] = None, timeout: float = 60.0, post: Optional[PostFn] = None):
        self.model = model or os.environ.get("GEMINI_MODEL", "")
        if not self.model:
            raise ModelError("GEMINI_MODEL is not set (the model name is never hard-coded)")
        self._key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
        if not self._key and post is None:
            raise ModelError("GEMINI_API_KEY is not set")
        self.timeout = timeout
        self._post = post or http_post_json

    def complete_json(self, *, system: str, user: str, schema: Dict[str, Any], name: str) -> Dict[str, Any]:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "responseSchema": to_gemini_schema(schema)},
        }
        url = GEMINI_ENDPOINT.format(model=self.model)
        last: Optional[BaseException] = None
        for _attempt in range(2):  # one try + one retry
            try:
                data = self._post(url, body, {"x-goog-api-key": self._key}, self.timeout)
                candidates = data.get("candidates") or []
                if not candidates:
                    reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
                    raise ModelError(f"model returned no answer ({reason})")
                parts = (candidates[0].get("content") or {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts)
                if not text:
                    raise ModelError(f"empty answer (finishReason {candidates[0].get('finishReason')})")
                return json.loads(text)
            except Exception as exc:  # network, timeout, HTTP error, bad JSON, block
                last = exc
        detail = str(last) if isinstance(last, (ProviderHTTPError, ModelError)) else type(last).__name__
        raise ModelError(f"model call failed after 2 attempts ({detail})")


# --------------------------------------------------------------------------- selection

def load_env_file(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE lines from the repo's git-ignored .env into os.environ.

    Variables already set in the environment win. Values are never printed or logged.
    Set CODEVIVA_NO_DOTENV=1 to skip (the test suite does).
    """
    if os.environ.get("CODEVIVA_NO_DOTENV") == "1":
        return
    path = path or Path(__file__).resolve().parent / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def selected_provider() -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    return "gemini" if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) else "openai"


def get_model(use_llm: bool, client: Any = None) -> Tuple[Optional[JSONModel], str]:
    """Return (model or None, human-readable reason when None)."""
    load_env_file()
    if not use_llm:
        return None, "model layer not requested"
    provider = selected_provider()
    try:
        if provider == "gemini":
            return GeminiJSONModel(post=client), ""
        if provider == "openai":
            return OpenAIJSONModel(client=client), ""
        return None, f"unknown LLM_PROVIDER {provider!r} (use 'gemini' or 'openai')"
    except ModelError as exc:
        return None, f"{provider} unavailable: {exc}"


def strict_object(properties: Dict[str, Any]) -> Dict[str, Any]:
    """JSON schema object in the strict shape (all fields required, no extras)."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
