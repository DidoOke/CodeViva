"""Stage runner.

Each stage reads the saved artifacts of the stages it requires, returns a StageResult, and
the runner writes it to runs/<submission_id>/round<N>/<filename>. Stages before --from-stage
are loaded from disk, never recomputed; stages after --stop-after are not run.

Stages are plain functions, so each one can be tested and re-run on its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from artifacts import hash_json, read_artifact, round_dir, write_artifact


@dataclass
class StageResult:
    data: Any
    count_in: int
    count_out: int
    summary: str
    model: Optional[str] = None


@dataclass
class RunContext:
    submission_id: str
    round_no: int
    run_dir: Path
    runs_root: Path
    seed: str  # randomisation seed (the submission id) — never let the model randomise
    options: Dict[str, Any] = field(default_factory=dict)

    @property
    def previous_round_dir(self) -> Optional[Path]:
        """Round N-1's directory, for delta stages. None in round 1."""
        if self.round_no <= 1:
            return None
        return round_dir(self.runs_root, self.submission_id, self.round_no - 1)


# fn(ctx, inputs) where inputs maps required stage id -> that stage's artifact data
StageFn = Callable[[RunContext, Dict[str, Any]], StageResult]


@dataclass
class Stage:
    id: str  # ordering key shown to users: "0", "1", "1d", "2", ...
    name: str
    filename: str
    fn: StageFn
    requires: List[str] = field(default_factory=list)
    min_round: int = 1  # e.g. the delta stage only exists from round 2
    flat: bool = False  # write {**data, meta} instead of {meta, data}


class StageError(RuntimeError):
    pass


def stages_for_round(stages: List[Stage], round_no: int) -> List[Stage]:
    return [s for s in stages if round_no >= s.min_round]


def _index_of(stages: List[Stage], stage_id: Optional[str], flag: str) -> Optional[int]:
    if stage_id is None:
        return None
    for i, s in enumerate(stages):
        if s.id == str(stage_id):
            return i
    known = ", ".join(s.id for s in stages)
    raise StageError(f"{flag} {stage_id!r} is not a stage in this round (known: {known})")


def input_hash_for(stage: Stage, artifacts: Dict[str, dict]) -> str:
    return hash_json({sid: artifacts[sid]["meta"]["output_hash"] for sid in stage.requires})


def run_pipeline(
    all_stages: List[Stage],
    ctx: RunContext,
    from_stage: Optional[str] = None,
    stop_after: Optional[str] = None,
) -> Dict[str, dict]:
    """Run stages [from_stage, stop_after]; load earlier ones from disk. Returns envelopes by id."""
    stages = stages_for_round(all_stages, ctx.round_no)
    start = _index_of(stages, from_stage, "--from-stage") or 0
    end = _index_of(stages, stop_after, "--stop-after")
    if end is None:
        end = len(stages) - 1
    if start > end:
        raise StageError(f"--from-stage {stages[start].id} comes after --stop-after {stages[end].id}")

    by_id = {s.id: s for s in stages}
    artifacts: Dict[str, dict] = {}

    for i, stage in enumerate(stages[: end + 1]):
        path = ctx.run_dir / stage.filename
        if i < start:
            try:
                artifacts[stage.id] = read_artifact(path)
            except FileNotFoundError:
                raise StageError(
                    f"--from-stage {stages[start].id} needs stage {stage.id} ({stage.name}) "
                    f"already on disk, but {path} is missing; run from an earlier stage"
                ) from None
            continue

        for req in stage.requires:
            if req not in by_id:
                raise StageError(f"stage {stage.id} requires unknown stage {req!r}")
            if req not in artifacts:
                raise StageError(f"stage {stage.id} requires stage {req}, which runs later")
        inputs = {req: artifacts[req]["data"] for req in stage.requires}

        result = stage.fn(ctx, inputs)
        if not isinstance(result, StageResult):
            raise StageError(f"stage {stage.id} ({stage.name}) must return a StageResult")
        artifacts[stage.id] = write_artifact(
            path,
            stage=stage.name,
            stage_id=stage.id,
            round_no=ctx.round_no,
            submission_id=ctx.submission_id,
            input_hash=input_hash_for(stage, artifacts),
            data=result.data,
            count_in=result.count_in,
            count_out=result.count_out,
            summary=result.summary,
            model=result.model,
            flat=stage.flat,
        )

    write_stages_md(stages, ctx)
    return artifacts


def write_stages_md(stages: List[Stage], ctx: RunContext) -> Path:
    """Human-readable summary of every artifact present in the run dir, with staleness."""
    lines = [
        f"# Submission {ctx.submission_id}, round {ctx.round_no}",
        "",
        "| Stage | Name | Summary | Model | In → Out | Status |",
        "|---|---|---|---|---|---|",
    ]
    loaded: Dict[str, dict] = {}
    for stage in stages:
        path = ctx.run_dir / stage.filename
        if not path.exists():
            lines.append(f"| {stage.id} | {stage.name} | not run | | | — |")
            continue
        env = read_artifact(path)
        loaded[stage.id] = env
        meta = env["meta"]
        status = "ok"
        if all(r in loaded for r in stage.requires):
            if input_hash_for(stage, loaded) != meta["input_hash"]:
                status = "STALE (upstream changed; re-run from here)"
        else:
            status = "STALE (upstream missing)"
        lines.append(
            f"| {stage.id} | {stage.name} | {meta['summary']} | {meta['model'] or ''} "
            f"| {meta['count_in']} → {meta['count_out']} | {status} |"
        )
    out = ctx.run_dir / "stages.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import sys

    # Import via the module name so `python pipeline.py` and `stages` share one set of classes.
    from pipeline import RunContext, StageError, run_pipeline
    from stages import DEFAULT_KB, build_stages, make_context_options

    p = argparse.ArgumentParser(description="Run the staged analysis pipeline for one submission.")
    p.add_argument("--submission", required=True, help="submission id (also the random seed)")
    p.add_argument("--db", help="database URL or SQLite path (default: $DATABASE_URL)")
    p.add_argument("--kb", action="append", help="knowledge base dir (repeatable)")
    p.add_argument("--round", type=int, default=1, dest="round_no")
    p.add_argument("--runs", default="runs", help="root directory for run artifacts")
    p.add_argument("--use-openai", action="store_true", help="enable the model layer (stages 3, 6, 7)")
    p.add_argument("--from-stage", help="re-run from this stage; earlier stages load from disk")
    p.add_argument("--stop-after", default="5", help="stop after this stage (default 5: the plan; "
                   "use interview.py for the interview)")
    args = p.parse_args(argv)

    runs_root = Path(args.runs)
    ctx = RunContext(
        submission_id=args.submission,
        round_no=args.round_no,
        run_dir=round_dir(runs_root, args.submission, args.round_no),
        runs_root=runs_root,
        seed=str(args.submission),
        options=make_context_options(db=args.db, kb_dirs=args.kb or DEFAULT_KB, use_openai=args.use_openai),
    )
    try:
        run_pipeline(build_stages(), ctx, from_stage=args.from_stage, stop_after=args.stop_after)
    except (StageError, ValueError, LookupError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print((ctx.run_dir / "stages.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
