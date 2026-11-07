import ast
import sqlite3

import pytest

from db_adapter import SubmissionNotFound, UnsafePath, create_schema, load_submission, safe_relpath
from make_demo_db import build
from make_sample_repo import all_submissions


@pytest.fixture
def demo_db(tmp_path):
    return str(build(tmp_path / "demo.db"))


def test_round_trip_shape(demo_db):
    sub = load_submission(1, f"sqlite:///{demo_db}")
    assert sub["submission_id"] == "1" and sub["assignment"] == "task_scheduler"
    assert set(sub["files"]) == {"scheduler.py", "README.md", "jobs.json", "tests/test_scheduler.py"}
    msgs = [c["message"] for c in sub["commits"]]
    assert msgs[0].startswith("initial") and msgs[-1].startswith("add tests")  # oldest first
    assert all(set(c) == {"sha", "message", "authored_at", "files"} for c in sub["commits"])


def test_bare_path_and_env_var(demo_db, monkeypatch):
    assert load_submission(2, demo_db)["files"]
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{demo_db}")
    assert load_submission("2")["submission_id"] == "2"


def test_missing_submission_and_missing_url(demo_db, monkeypatch):
    with pytest.raises(SubmissionNotFound):
        load_submission(99, demo_db)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        load_submission(1)


def test_sample_code_parses_and_history_is_consistent():
    for sub in all_submissions():
        for path, content in sub["files"].items():
            if path.endswith(".py"):
                ast.parse(content)
        for c in sub["commits"]:
            for path, content in c["files"].items():
                if path.endswith(".py") and content:
                    ast.parse(content)


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs.py", "a/../../b.py", "a\\b.py", "", "x\x00.py", "a//b.py"])
def test_path_traversal_rejected(bad):
    with pytest.raises(UnsafePath):
        safe_relpath(bad)


def test_unsafe_path_in_db_is_refused(tmp_path):
    db = tmp_path / "evil.db"
    conn = sqlite3.connect(db)
    create_schema(conn)
    conn.execute("INSERT INTO submissions (id, assignment) VALUES (5, 'x')")
    conn.execute("INSERT INTO submission_files VALUES (5, '../../secret.py', 'x = 1')")
    conn.commit()
    conn.close()
    with pytest.raises(UnsafePath):
        load_submission(5, str(db))


def test_injection_attempt_is_just_a_bad_id(demo_db):
    with pytest.raises(ValueError):
        load_submission("1 OR 1=1", demo_db)
