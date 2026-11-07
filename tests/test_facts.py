from facts import ast_facts, extract_facts
from make_sample_repo import submission_1, submission_2


def by_kind(result, kind):
    return [f for f in result["facts"] if f["kind"] == kind]


def test_constant_change_tied_to_commit():
    r = extract_facts(submission_1())
    (change,) = by_kind(r, "constant_changed")
    assert (change["name"], change["old"], change["new"]) == ("MAX_RETRIES", 5, 3)
    assert change["commit_message"].startswith("reduce MAX_RETRIES")
    assert change["file"] == "scheduler.py" and change["in_final"]
    lines = submission_1()["files"]["scheduler.py"].splitlines()
    assert lines[change["line"] - 1].startswith("MAX_RETRIES = 3")


def test_fix_commits_and_introducing_commit():
    r = extract_facts(submission_1())
    assert len(by_kind(r, "fix_commit")) == 2
    heap = [f for f in by_kind(r, "data_structure") if f["structure"] == "heapq"][0]
    assert heap["commit_message"].startswith("use a heap")


def test_every_fact_has_id_file_and_valid_line():
    for sub in (submission_1(), submission_2()):
        r = extract_facts(sub)
        ids = [f["id"] for f in r["facts"]]
        assert len(ids) == len(set(ids))
        for f in r["facts"]:
            if f["line"] is not None:
                assert 0 < f["line"] <= len(sub["files"][f["file"]].splitlines())


def test_submission_2_signals():
    r = extract_facts(submission_2())
    (handler,) = by_kind(r, "exception_handler")
    assert handler["broad"] and handler["body_kind"] == "pass"
    structures = {f["structure"] for f in by_kind(r, "data_structure")}
    assert {"sort_in_loop", "list_pop_front"} <= structures
    assert not by_kind(r, "constant_changed") and not by_kind(r, "fix_commit")


def test_syntax_error_is_reported_not_raised():
    sub = {"files": {"bad.py": "def f(:\n", "ok.py": "X = 1\n"}, "commits": []}
    r = extract_facts(sub)
    assert r["parse_errors"][0]["file"] == "bad.py"
    assert [f["name"] for f in r["facts"]] == ["X"]


def test_code_is_never_executed(tmp_path):
    marker = tmp_path / "pwned"
    evil = f"import os\nos.system('touch {marker}')\nOPEN = open('{marker}', 'w')\n"
    ast_facts("evil.py", evil)
    assert not marker.exists()
