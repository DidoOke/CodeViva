"""Thin model client: structured JSON output, timeout, one retry. Injectable for tests.

Every caller depends only on the JSONModel protocol (`.model` and `.complete_json`), so tests
pass a fake and the OpenAI SDK is imported only when a real client is built. The API key is
read by the SDK from OPENAI_API_KEY; it is never logged, printed or stored in artifacts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Tuple


class ModelError(RuntimeError):
    pass


class JSONModel(Protocol):
    model: str

    def complete_json(self, *, system: str, user: str, schema: Dict[str, Any], name: str) -> Dict[str, Any]:
        ...


class OpenAIJSONModel:
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


def load_env_file(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE lines from the repo's git-ignored .env into os.environ.

    Variables already set in the environment win. Values are never printed or logged.
    """
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


def get_model(use_openai: bool, client: Any = None) -> Tuple[Optional[JSONModel], str]:
    """Return (model or None, human-readable reason when None)."""
    load_env_file()
    if not use_openai:
        return None, "OpenAI not requested"
    try:
        return OpenAIJSONModel(client=client), ""
    except ModelError as exc:
        return None, f"OpenAI unavailable: {exc}"


def strict_object(properties: Dict[str, Any]) -> Dict[str, Any]:
    """JSON schema object in the shape OpenAI strict mode requires."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
