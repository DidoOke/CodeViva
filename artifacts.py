"""Stage artifacts: one JSON file per stage, each wrapped in a metadata envelope.

Envelope shape (every artifact):
    {
      "meta": {
        "stage": "facts",            # stage name
        "stage_id": "1",             # stage id (ordering key, e.g. "1", "1d", "2")
        "round": 1,
        "submission_id": "1",
        "input_hash": "sha256...",   # hash of the upstream artifacts' data
        "output_hash": "sha256...",  # hash of this artifact's data
        "created_at": "2026-...Z",
        "model": null | "model-name",
        "count_in": 12,
        "count_out": 42,
        "summary": "42 facts"        # one line, used in stages.md
      },
      "data": { ... stage-specific ... }
    }
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_json(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def round_dir(runs_root: Path, submission_id: str, round_no: int) -> Path:
    """runs/<submission_id>/round<N>/ — every artifact path is keyed by round."""
    if round_no < 1:
        raise ValueError(f"round must be >= 1, got {round_no}")
    safe_id = str(submission_id)
    if not safe_id or "/" in safe_id or "\\" in safe_id or safe_id in {".", ".."}:
        raise ValueError(f"invalid submission id: {submission_id!r}")
    return Path(runs_root) / safe_id / f"round{round_no}"


def write_artifact(
    path: Path,
    *,
    stage: str,
    stage_id: str,
    round_no: int,
    submission_id: str,
    input_hash: str,
    data: Any,
    count_in: int,
    count_out: int,
    summary: str,
    model: Optional[str] = None,
    flat: bool = False,
) -> dict:
    """flat=True writes {**data, "meta": ...} so files with a prescribed shape keep it."""
    envelope = {
        "meta": {
            "stage": stage,
            "stage_id": stage_id,
            "round": round_no,
            "submission_id": str(submission_id),
            "input_hash": input_hash,
            "output_hash": hash_json(data),
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model": model,
            "count_in": count_in,
            "count_out": count_out,
            "summary": summary,
        },
        "data": data,
    }
    on_disk = {**data, "meta": envelope["meta"]} if flat else envelope
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(on_disk, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)  # atomic: a crashed stage never leaves a half-written artifact
    return envelope


def read_artifact(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"artifact not found: {path}")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(envelope, dict) or "meta" not in envelope:
        raise ValueError(f"not a stage artifact (missing meta): {path}")
    if "data" not in envelope:  # flat artifact
        return {"meta": envelope["meta"], "data": {k: v for k, v in envelope.items() if k != "meta"}}
    return envelope
