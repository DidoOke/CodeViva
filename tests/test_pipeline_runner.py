"""Runner mechanics with toy stages (no student code, no model)."""
import json

import pytest

from artifacts import hash_json, read_artifact, round_dir
from pipeline import RunContext, Stage, StageError, StageResult, run_pipeline


def make_stages(calls):
    def s0(ctx, inputs):
        calls.append("0")
        return StageResult(data={"files": ["a.py", "b.py"]}, count_in=0, count_out=2, summary="2 files")

    def s1(ctx, inputs):
        calls.append("1")
        n = len(inputs["0"]["files"]) * 3
        return StageResult(data={"facts": list(range(n))}, count_in=2, count_out=n, summary=f"{n} facts")

    def s1d(ctx, inputs):
        calls.append("1d")
        return StageResult(data={"prev": str(ctx.previous_round_dir)}, count_in=0, count_out=0, summary="delta")

    def s2(ctx, inputs):
        calls.append("2")
        return StageResult(data={"seed": ctx.seed}, count_in=len(inputs["1"]["facts"]), count_out=1,
                           summary="1 of 1 rules triggered", model=None)

    return [
        Stage("0", "ingest", "stage0_submission.json", s0),
        Stage("1", "facts", "stage1_facts.json", s1, requires=["0"]),
        Stage("1d", "delta", "stage1d_delta.json", s1d, requires=["1"], min_round=2),
        Stage("2", "rule_match", "stage2_rule_matches.json", s2, requires=["1"]),
    ]


def ctx_for(tmp_path, round_no=1):
    return RunContext(submission_id="7", round_no=round_no,
                      run_dir=round_dir(tmp_path, "7", round_no), runs_root=tmp_path, seed="7")


def test_full_run_writes_round_keyed_artifacts_with_meta(tmp_path):
    calls = []
    ctx = ctx_for(tmp_path)
    run_pipeline(make_stages(calls), ctx)
    assert calls == ["0", "1", "2"]  # delta stage skipped in round 1
    assert ctx.run_dir == tmp_path / "7" / "round1"
    env = read_artifact(ctx.run_dir / "stage1_facts.json")
    meta = env["meta"]
    assert meta["stage"] == "facts" and meta["round"] == 1 and meta["submission_id"] == "7"
    assert meta["count_in"] == 2 and meta["count_out"] == 6
    assert meta["model"] is None and meta["created_at"].endswith("Z")
    stage0 = read_artifact(ctx.run_dir / "stage0_submission.json")
    assert meta["input_hash"] == hash_json({"0": stage0["meta"]["output_hash"]})
    assert meta["output_hash"] == hash_json(env["data"])


def test_stop_after_and_from_stage(tmp_path):
    calls = []
    ctx = ctx_for(tmp_path)
    run_pipeline(make_stages(calls), ctx, stop_after="1")
    assert calls == ["0", "1"]
    assert not (ctx.run_dir / "stage2_rule_matches.json").exists()

    calls.clear()
    run_pipeline(make_stages(calls), ctx, from_stage="2")
    assert calls == ["2"]  # 0 and 1 loaded from disk, not recomputed


def test_from_stage_with_missing_upstream_is_a_clear_error(tmp_path):
    with pytest.raises(StageError, match="stage0_submission.json is missing"):
        run_pipeline(make_stages([]), ctx_for(tmp_path), from_stage="1")


def test_unknown_stage_id_is_rejected(tmp_path):
    with pytest.raises(StageError, match="known: 0, 1, 2"):
        run_pipeline(make_stages([]), ctx_for(tmp_path), stop_after="9")


def test_round2_includes_delta_stage_and_sees_previous_round(tmp_path):
    calls = []
    run_pipeline(make_stages(calls), ctx_for(tmp_path, round_no=2))
    assert calls == ["0", "1", "1d", "2"]
    delta = read_artifact(tmp_path / "7" / "round2" / "stage1d_delta.json")
    assert delta["data"]["prev"] == str(tmp_path / "7" / "round1")


def test_stages_md_summarises_and_flags_stale(tmp_path):
    ctx = ctx_for(tmp_path)
    run_pipeline(make_stages([]), ctx)
    md = (ctx.run_dir / "stages.md").read_text()
    assert "6 facts" in md and "1 of 1 rules triggered" in md and "STALE" not in md

    # Upstream changes after downstream was written -> downstream flagged stale.
    path = ctx.run_dir / "stage0_submission.json"
    env = json.loads(path.read_text())
    env["meta"]["output_hash"] = "changed"
    path.write_text(json.dumps(env))
    from pipeline import write_stages_md
    md = write_stages_md(make_stages([])[:2] + make_stages([])[3:], ctx).read_text()
    assert "STALE" in md


def test_round_dir_rejects_traversal(tmp_path):
    for bad in ["../x", "a/b", "..", ""]:
        with pytest.raises(ValueError):
            round_dir(tmp_path, bad, 1)
