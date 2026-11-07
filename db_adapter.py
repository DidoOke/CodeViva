"""Read one submission (files + commit history) from the database.

Connection comes from --db or the DATABASE_URL environment variable:
    sqlite:///demo.db        relative SQLite file
    sqlite:////abs/demo.db   absolute SQLite file
    demo.db                  bare path, treated as SQLite
    postgresql://...         Postgres (needs psycopg installed); "+psycopg" suffix accepted

Return shape (stable contract used by every later stage):
    {
      "submission_id": "1",
      "assignment": "log_monitor",
      "files":   {"monitor.py": "<final content>", ...},
      "commits": [ {"sha", "message", "authored_at", "files": {path: content | None}}, ... ]
    }
commits are oldest first; a commit's "files" holds the full content of each file it touched
(None = deleted). Database content is untrusted: every path is checked for traversal, and
every query is parameterised.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY,
    assignment TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS submission_files (
    submission_id INTEGER NOT NULL REFERENCES submissions(id),
    path TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (submission_id, path)
);
CREATE TABLE IF NOT EXISTS commits (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES submissions(id),
    seq INTEGER NOT NULL,
    sha TEXT NOT NULL,
    message TEXT NOT NULL,
    authored_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS commit_files (
    commit_id INTEGER NOT NULL REFERENCES commits(id),
    path TEXT NOT NULL,
    content TEXT,
    PRIMARY KEY (commit_id, path)
);
"""


class SubmissionNotFound(LookupError):
    pass


class UnsafePath(ValueError):
    pass


def safe_relpath(path: str) -> str:
    """Normalise a repo-relative path from the DB; reject anything that could escape the repo."""
    if not isinstance(path, str) or not path or "\x00" in path or "\\" in path:
        raise UnsafePath(f"unsafe path in database: {path!r}")
    p = PurePosixPath(path)
    if p.is_absolute() or any(part in ("..", "") for part in path.split("/")) or path.startswith("~"):
        raise UnsafePath(f"unsafe path in database: {path!r}")
    norm = str(p)
    if norm in (".", ""):
        raise UnsafePath(f"unsafe path in database: {path!r}")
    return norm


def resolve_url(db: Optional[str] = None) -> str:
    url = db or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("no database given: pass --db or set DATABASE_URL")
    return url


@contextmanager
def connect(db: Optional[str] = None) -> Iterator[Tuple[Any, str]]:
    """Yield (connection, paramstyle placeholder)."""
    url = resolve_url(db)
    if url.startswith(("postgresql://", "postgresql+psycopg://", "postgres://")):
        try:
            import psycopg  # type: ignore
        except ImportError:
            raise RuntimeError("Postgres URL given but psycopg is not installed (pip install psycopg[binary])") from None
        conn = psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1))
        ph = "%s"
    else:
        path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else url
        if url.startswith("sqlite://") and not url.startswith("sqlite:///"):
            raise ValueError(f"unsupported sqlite URL: {url}")
        conn = sqlite3.connect(path)
        ph = "?"
    try:
        yield conn, ph
    finally:
        conn.close()


def _rows(conn: Any, sql: str, params: tuple) -> List[tuple]:
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def load_submission(submission_id: Any, db: Optional[str] = None) -> Dict[str, Any]:
    sid = int(submission_id)
    with connect(db) as (conn, ph):
        sub = _rows(conn, f"SELECT id, assignment FROM submissions WHERE id = {ph}", (sid,))
        if not sub:
            raise SubmissionNotFound(f"submission {sid} not found")
        files: Dict[str, str] = {}
        for path, content in _rows(
            conn, f"SELECT path, content FROM submission_files WHERE submission_id = {ph} ORDER BY path", (sid,)
        ):
            files[safe_relpath(path)] = content

        commits: List[Dict[str, Any]] = []
        commit_rows = _rows(
            conn,
            f"SELECT id, sha, message, authored_at FROM commits WHERE submission_id = {ph} ORDER BY seq, id",
            (sid,),
        )
        for cid, sha, message, authored_at in commit_rows:
            cfiles: Dict[str, Optional[str]] = {}
            for path, content in _rows(
                conn, f"SELECT path, content FROM commit_files WHERE commit_id = {ph} ORDER BY path", (cid,)
            ):
                cfiles[safe_relpath(path)] = content
            commits.append({"sha": sha, "message": message, "authored_at": authored_at, "files": cfiles})

    return {"submission_id": str(sid), "assignment": sub[0][1], "files": files, "commits": commits}


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def insert_submission(conn: sqlite3.Connection, submission: Dict[str, Any]) -> int:
    """Insert a submission in the load_submission() shape (SQLite; used for demo data and tests)."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO submissions (id, assignment, label, created_at) VALUES (?, ?, ?, ?)",
        (int(submission["submission_id"]), submission["assignment"], submission.get("label", ""),
         submission.get("created_at", "")),
    )
    sid = int(submission["submission_id"])
    for path, content in submission["files"].items():
        cur.execute("INSERT INTO submission_files (submission_id, path, content) VALUES (?, ?, ?)",
                    (sid, path, content))
    for seq, commit in enumerate(submission["commits"]):
        cur.execute(
            "INSERT INTO commits (submission_id, seq, sha, message, authored_at) VALUES (?, ?, ?, ?, ?)",
            (sid, seq, commit["sha"], commit["message"], commit.get("authored_at", "")),
        )
        cid = cur.lastrowid
        for path, content in commit["files"].items():
            cur.execute("INSERT INTO commit_files (commit_id, path, content) VALUES (?, ?, ?)", (cid, path, content))
    conn.commit()
    return sid


def list_submissions(db: Optional[str] = None) -> List[Dict[str, Any]]:
    with connect(db) as (conn, _ph):
        rows = _rows(conn, "SELECT id, assignment, label FROM submissions ORDER BY id", ())
    return [{"id": str(r[0]), "assignment": r[1], "label": r[2]} for r in rows]
