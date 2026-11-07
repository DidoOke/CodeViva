from __future__ import annotations

import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.repository import Repository, RepositoryFile
from app.services.coding_challenge import (
    _extract_codebase_targets,
    build_coding_challenge,
    build_targeted_questions,
    execute_coding_challenge,
    generate_tailored_followup,
)
from app.services.grading_engine import run_final_grading_engine
from app.services.storage import storage_service

# Ensure root pipeline modules are importable both in Docker (/app/pipeline_root) and locally
PIPELINE_ROOT = (
    Path("/app/pipeline_root")
    if Path("/app/pipeline_root").exists()
    else Path(__file__).resolve().parents[3]
)
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

import explain  # noqa: E402
import grade  # noqa: E402
import llm  # noqa: E402
from artifacts import hash_json, read_artifact, round_dir, write_artifact  # noqa: E402
from db_adapter import create_schema, insert_submission  # noqa: E402
from examiner import InterviewTransport, ScriptedTransport  # noqa: E402
from make_sample_repo import all_submissions  # noqa: E402
from pipeline import RunContext, Stage, run_pipeline  # noqa: E402
from rounds import kb_for_round, round_stages  # noqa: E402
from stages import build_stages, make_context_options  # noqa: E402

router = APIRouter(prefix="/assessment", tags=["assessment"])

ASSESSMENT_DB_PATH = settings.storage_root / "assessment.db"
RUNS_ROOT = settings.storage_root / "runs"

DEFAULT_KB_DIRS = [
    str(PIPELINE_ROOT / "kb" / "generic"),
    str(PIPELINE_ROOT / "kb" / "task_scheduler"),
]


class QueueTransport(InterviewTransport):
    """Bridges the blocking Stage 6 Examiner loop to non-blocking HTTP polling."""

    def __init__(self, submission_id: str, round_no: int, repo_id: int) -> None:
        self.submission_id = submission_id
        self.round_no = round_no
        self.repo_id = repo_id
        self.outbox: List[Dict[str, Any]] = []
        self.inbox: "queue.Queue[Optional[str]]" = queue.Queue()
        self.done = False
        self.error = ""

    def send(self, text: str) -> None:
        self.outbox.append({"speaker": "examiner", "text": text})

    def receive(self) -> Optional[str]:
        try:
            answer = self.inbox.get(timeout=3600)
        except queue.Empty:
            return None
        if answer is not None:
            self.outbox.append({"speaker": "student", "text": answer})
        return answer


ACTIVE_SESSIONS: Dict[str, QueueTransport] = {}


def _reload_env() -> None:
    env_path = PIPELINE_ROOT / ".env"
    if env_path.is_file():
        llm.load_env_file(env_path)
    else:
        llm.load_env_file()


def _ensure_demo_db() -> str:
    """Ensure the SQLite assessment DB exists and contains the synthetic demo submissions."""
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ASSESSMENT_DB_PATH)
    try:
        create_schema(conn)
        cur = conn.cursor()
        cur.execute("SELECT id FROM submissions WHERE id IN (1, 2)")
        existing = {row[0] for row in cur.fetchall()}
        for sub in all_submissions():
            sid = int(sub["submission_id"])
            if sid not in existing:
                insert_submission(conn, sub)
        try:
            from make_round2_samples import all_round2_submissions  # type: ignore

            cur.execute("SELECT id FROM submissions WHERE id IN (11, 12)")
            existing_r2 = {row[0] for row in cur.fetchall()}
            for sub in all_round2_submissions():
                sid = int(sub["submission_id"])
                if sid not in existing_r2:
                    insert_submission(conn, sub)
        except Exception:
            pass
    finally:
        conn.close()
    return f"sqlite:///{ASSESSMENT_DB_PATH}"


def _extract_git_commits(repo_path: Path, final_files: Dict[str, str]) -> List[Dict[str, Any]]:
    """Extract git commit snapshots if .git is present; otherwise synthesize a commit snapshot."""
    git_dir = repo_path / ".git"
    commits: List[Dict[str, Any]] = []
    if git_dir.exists():
        try:
            log_out = subprocess.check_output(
                ["git", "-C", str(repo_path), "log", "--reverse", "--max-count=12", "--format=%H|%aI|%s"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            for line in log_out.splitlines():
                parts = line.split("|", 2)
                if len(parts) != 3:
                    continue
                sha, authored_at, message = parts
                changed = subprocess.check_output(
                    ["git", "-C", str(repo_path), "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                cfiles: Dict[str, Optional[str]] = {}
                for rel in changed.splitlines():
                    rel = rel.strip()
                    if not rel or "/" in rel and any(p in {".git", "node_modules", "__pycache__"} for p in rel.split("/")):
                        continue
                    try:
                        blob = subprocess.check_output(
                            ["git", "-C", str(repo_path), "show", f"{sha}:{rel}"],
                            text=True,
                            stderr=subprocess.DEVNULL,
                        )
                        cfiles[rel] = blob
                    except Exception:
                        cfiles[rel] = final_files.get(rel)
                if cfiles:
                    commits.append(
                        {
                            "sha": sha,
                            "message": message,
                            "authored_at": authored_at,
                            "files": cfiles,
                        }
                    )
        except Exception:
            commits = []

    if not commits:
        commits = [
            {
                "sha": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
                "message": "Initial repository implementation snapshot",
                "authored_at": "2026-11-07T15:00:00Z",
                "files": dict(final_files),
            }
        ]
    return commits


def _resolve_submission_id(
    repository_id: int,
    db: Session,
    demo_submission_id: Optional[str] = None,
) -> str:
    """Resolve or sync the target repository into the assessment SQLite database."""
    _ensure_demo_db()

    if demo_submission_id and demo_submission_id in {"1", "2", "11", "12"}:
        return demo_submission_id

    # Sample repository mode (id 101 in frontend) maps to synthetic submission 1
    if repository_id == 101:
        return "1"

    repository = db.get(Repository, repository_id)
    if not repository:
        if str(repository_id) in {"1", "2"}:
            return str(repository_id)
        raise HTTPException(status_code=404, detail=f"Repository {repository_id} not found")

    mapped_sid = 1000 + repository_id
    repo_path = Path(repository.root_path) if repository.root_path else storage_service.repository_path(repository_id)
    db_files = db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository_id).all()

    files_map: Dict[str, str] = {}
    for f in db_files:
        if not f.is_text:
            continue
        candidate = repo_path / f.relative_path
        if candidate.is_file():
            try:
                files_map[f.relative_path] = candidate.read_text(encoding="utf-8")
            except Exception:
                continue

    if not files_map and repo_path.is_dir():
        for p in repo_path.rglob("*.py"):
            try:
                rel = p.relative_to(repo_path).as_posix()
                files_map[rel] = p.read_text(encoding="utf-8")
            except Exception:
                continue

    if not files_map:
        # Fallback to demo submission 1 if repository has no readable text files
        return "1"

    commits = _extract_git_commits(repo_path, files_map)

    conn = sqlite3.connect(ASSESSMENT_DB_PATH)
    try:
        create_schema(conn)
        cur = conn.cursor()
        cur.execute("DELETE FROM commit_files WHERE commit_id IN (SELECT id FROM commits WHERE submission_id = ?)", (mapped_sid,))
        cur.execute("DELETE FROM commits WHERE submission_id = ?", (mapped_sid,))
        cur.execute("DELETE FROM submission_files WHERE submission_id = ?", (mapped_sid,))
        cur.execute("DELETE FROM submissions WHERE id = ?", (mapped_sid,))
        conn.commit()

        insert_submission(
            conn,
            {
                "submission_id": str(mapped_sid),
                "assignment": repository.display_name or "coursework",
                "label": repository.display_name,
                "created_at": repository.created_at.isoformat() if repository.created_at else "",
                "files": files_map,
                "commits": commits,
            },
        )
    finally:
        conn.close()

    return str(mapped_sid)


def _stages_for(round_no: int, code_from: Optional[str] = None) -> List[Stage]:
    base = build_stages()
    if round_no >= 2:
        # Ensure kb/rounds path is resolved relative to PIPELINE_ROOT
        return round_stages(base, round_no, code_from)
    return base


def _kb_dirs_for(round_no: int, submission_id: str = "1") -> List[str]:
    dirs = list(DEFAULT_KB_DIRS)
    uploaded_kb = PIPELINE_ROOT / "kb" / "uploaded"
    if submission_id.isdigit() and int(submission_id) >= 1000 and uploaded_kb.is_dir():
        dirs.append(str(uploaded_kb))
    if round_no <= 1:
        return dirs
    extra = [str(PIPELINE_ROOT / "kb" / "rounds")]
    r2_dir = PIPELINE_ROOT / "kb" / "task_scheduler" / f"round{round_no}"
    if r2_dir.is_dir():
        extra.append(str(r2_dir))
    return dirs + extra


def _stage_rows(run_dir: Path, round_no: int = 1) -> List[Dict[str, Any]]:
    rows = []
    for stage in _stages_for(round_no):
        path = run_dir / stage.filename
        if path.exists():
            try:
                meta = read_artifact(path)["meta"]
                rows.append(
                    {
                        "id": stage.id,
                        "name": stage.name,
                        "summary": meta["summary"],
                        "model": meta["model"],
                        "count_in": meta["count_in"],
                        "count_out": meta["count_out"],
                        "status": "completed",
                    }
                )
            except Exception:
                rows.append(
                    {
                        "id": stage.id,
                        "name": stage.name,
                        "summary": "error reading artifact",
                        "model": None,
                        "count_in": 0,
                        "count_out": 0,
                        "status": "error",
                    }
                )
        else:
            rows.append(
                {
                    "id": stage.id,
                    "name": stage.name,
                    "summary": "not run",
                    "model": None,
                    "count_in": None,
                    "count_out": None,
                    "status": "pending",
                }
            )
    return rows


def _make_ctx(
    submission_id: str,
    round_no: int = 1,
    use_llm: bool = True,
    max_questions: int = 5,
    transport: Any = None,
) -> RunContext:
    _reload_env()
    db_url = _ensure_demo_db()
    kb_dirs = _kb_dirs_for(round_no, submission_id)
    options = make_context_options(
        db=db_url,
        kb_dirs=kb_dirs,
        use_openai=use_llm,
        transport=transport,
        max_questions=max_questions,
    )
    return RunContext(
        submission_id=submission_id,
        round_no=round_no,
        run_dir=round_dir(RUNS_ROOT, submission_id, round_no),
        runs_root=RUNS_ROOT,
        seed=str(submission_id),
        options=options,
    )


class PlanRequest(BaseModel):
    use_llm: bool = True
    round_no: int = 1
    max_questions: int = 5
    demo_submission_id: Optional[str] = None
    code_from: Optional[str] = None


class StartInterviewRequest(BaseModel):
    use_llm: bool = True
    round_no: int = 1
    demo_submission_id: Optional[str] = None


class AnswerRequest(BaseModel):
    text: str


@router.get("/status")
def get_assessment_status() -> Dict[str, Any]:
    _reload_env()
    model, reason = llm.get_model(True)
    eleven_key = bool(settings.elevenlabs_api_key or os.environ.get("ELEVENLABS_API_KEY"))
    return {
        "llm_configured": model is not None,
        "llm_provider": getattr(model, "provider", llm.selected_provider()),
        "llm_model": getattr(model, "model", os.environ.get("GEMINI_MODEL") or os.environ.get("OPENAI_MODEL") or ""),
        "llm_reason": reason,
        "speech_server_configured": eleven_key,
        "demo_submissions": [
            {
                "id": "1",
                "assignment": "task_scheduler",
                "label": "Submission 1 · Full project (heapq, backoff, crash fix, unit tests)",
            },
            {
                "id": "2",
                "assignment": "task_scheduler",
                "label": "Submission 2 · Thin history (broad except: pass, list.sort in loop)",
            },
        ],
    }


@router.post("/repositories/{repository_id}/plan")
def build_repository_plan(
    repository_id: int,
    payload: PlanRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sid = _resolve_submission_id(repository_id, db, payload.demo_submission_id)
    round_no = max(1, payload.round_no)
    code_from = payload.code_from or ("11" if sid == "1" and round_no == 2 else None)

    # If round 2 is requested and round 1 hasn't been run yet, ensure round 1 plan & scripted transcript exist
    if round_no >= 2:
        r1_dir = round_dir(RUNS_ROOT, sid, 1)
        if not (r1_dir / "transcript.json").exists():
            r1_answers_path = PIPELINE_ROOT / "demo_answers" / "submission1.txt"
            ans_lines = (
                [l.strip() for l in r1_answers_path.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
                if r1_answers_path.exists()
                else ["We used heapq for O(log n) priority scheduling and added exponential backoff."] * 10
            )
            r1_ctx = _make_ctx(sid, round_no=1, use_llm=payload.use_llm, transport=ScriptedTransport(ans_lines))
            run_pipeline(build_stages(), r1_ctx, stop_after="7")

    ctx = _make_ctx(
        sid,
        round_no=round_no,
        use_llm=payload.use_llm,
        max_questions=payload.max_questions,
    )
    try:
        stages = _stages_for(round_no, code_from=code_from)
        run_pipeline(stages, ctx, stop_after="5")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run = explain.load_run(ctx.run_dir)
    plan_data = run["5"]["data"]
    facts_data = run["1"]["data"]
    matches_data = run["2"]["data"]
    verified_data = run["4"]["data"]

    questions_out = []
    for q in plan_data["questions"]:
        citations = []
        for c in q.get("citations", []):
            if c.get("file") and c.get("line"):
                citations.append(f"{c['file']}:{c['line']}")
            elif c.get("file"):
                citations.append(str(c["file"]))
            elif c.get("commit"):
                citations.append(f"commit {str(c['commit'])[:7]}")
        try:
            explanation = explain.explain(run, q["id"])
        except Exception as exc:
            explanation = f"Selected: {q.get('why_selected', '')} ({exc})"

        questions_out.append(
            {
                "id": q["id"],
                "dimension": q["dimension"],
                "dimension_label": grade.DIMENSION_LABELS.get(q["dimension"], q["dimension"]),
                "text": q["text"],
                "follow_up": q.get("follow_up", ""),
                "good_answer_mentions": q.get("good_answer_mentions", []),
                "why_selected": q.get("why_selected", ""),
                "source": q.get("source", {}),
                "citations": citations,
                "explain": explanation,
            }
        )

    delta_info = None
    delta_path = ctx.run_dir / "stage1d_delta.json"
    if delta_path.exists():
        try:
            delta_info = read_artifact(delta_path)["data"]
        except Exception:
            delta_info = None

    return {
        "submission_id": sid,
        "round_no": round_no,
        "mode": plan_data["mode"],
        "stages": _stage_rows(ctx.run_dir, round_no),
        "facts_summary": {
            "total": len(facts_data.get("facts", [])),
            "python_files": facts_data.get("python_files", 0),
            "counts_by_kind": facts_data.get("counts_by_kind", {}),
            "facts": facts_data.get("facts", [])[:30],
        },
        "rule_matches_summary": {
            "triggered_count": sum(1 for m in matches_data.get("matches", []) if m.get("triggered")),
            "total_rules": len(matches_data.get("matches", [])),
        },
        "verified_proposals_summary": {
            "status": verified_data.get("status"),
            "accepted": verified_data.get("accepted", 0),
            "rejected": verified_data.get("rejected", 0),
        },
        "questions": questions_out,
        "not_triggered": plan_data.get("not_triggered", []),
        "not_selected": plan_data.get("not_selected", []),
        "delta": delta_info,
    }


@router.post("/repositories/{repository_id}/interview/start")
def start_repository_interview(
    repository_id: int,
    payload: StartInterviewRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sid = _resolve_submission_id(repository_id, db, payload.demo_submission_id)
    round_no = max(1, payload.round_no)
    r_dir = round_dir(RUNS_ROOT, sid, round_no)

    if not (r_dir / "stage5_plan.json").exists():
        # Auto-build plan if not built yet
        build_repository_plan(
            repository_id,
            PlanRequest(
                use_llm=payload.use_llm,
                round_no=round_no,
                demo_submission_id=payload.demo_submission_id,
            ),
            db,
        )

    transport = QueueTransport(submission_id=sid, round_no=round_no, repo_id=repository_id)
    session_id = uuid.uuid4().hex[:12]
    ACTIVE_SESSIONS[session_id] = transport

    def worker() -> None:
        try:
            ctx = _make_ctx(sid, round_no=round_no, use_llm=payload.use_llm, transport=transport)
            stages = _stages_for(round_no)
            run_pipeline(stages, ctx, from_stage="6", stop_after="7")
        except Exception as exc:
            transport.error = str(exc)
        finally:
            transport.done = True

    threading.Thread(target=worker, daemon=True).start()

    # Wait briefly for Examiner intro + Q1 to populate transport.outbox
    for _ in range(25):
        if len(transport.outbox) >= 2 or transport.done:
            break
        time.sleep(0.02)

    return {
        "session_id": session_id,
        "submission_id": sid,
        "round_no": round_no,
        "messages": list(transport.outbox),
        "done": transport.done,
        "error": transport.error,
    }


@router.get("/interview/{session_id}")
def poll_interview(session_id: str, after: int = Query(0, ge=0)) -> Dict[str, Any]:
    transport = ACTIVE_SESSIONS.get(session_id)
    if transport is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return {
        "session_id": session_id,
        "submission_id": transport.submission_id,
        "round_no": transport.round_no,
        "messages": transport.outbox[after:],
        "total_messages": len(transport.outbox),
        "done": transport.done,
        "error": transport.error,
    }


@router.post("/interview/{session_id}/answer")
def submit_interview_answer(session_id: str, body: AnswerRequest) -> Dict[str, Any]:
    transport = ACTIVE_SESSIONS.get(session_id)
    if transport is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if transport.done:
        return {
            "ok": False,
            "messages": list(transport.outbox),
            "done": True,
            "error": transport.error,
        }

    prev_len = len(transport.outbox)
    transport.inbox.put(body.text.strip()[:5000])

    # Wait briefly for the examiner's follow-up / next question or completion
    for _ in range(40):
        if len(transport.outbox) >= prev_len + 2 or transport.done:
            break
        time.sleep(0.03)

    return {
        "ok": True,
        "messages": list(transport.outbox),
        "done": transport.done,
        "error": transport.error,
    }


@router.post("/repositories/{repository_id}/auto-grade")
def run_auto_demo_interview_and_grade(
    repository_id: int,
    payload: StartInterviewRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Replays realistic student answers through Stage 6 and Stage 7 for fast end-to-end grading verification."""
    sid = _resolve_submission_id(repository_id, db, payload.demo_submission_id)
    round_no = max(1, payload.round_no)
    r_dir = round_dir(RUNS_ROOT, sid, round_no)

    if not (r_dir / "stage5_plan.json").exists():
        build_repository_plan(
            repository_id,
            PlanRequest(
                use_llm=payload.use_llm,
                round_no=round_no,
                demo_submission_id=payload.demo_submission_id,
            ),
            db,
        )

    plan_data = read_artifact(r_dir / "stage5_plan.json")["data"]

    # Choose best matching demo answers file or construct rich answers from good_answer_mentions
    demo_file = (
        PIPELINE_ROOT / "demo_answers" / "submission1_round2.txt"
        if round_no >= 2
        else PIPELINE_ROOT / "demo_answers" / ("submission2.txt" if sid == "2" else "submission1.txt")
    )

    scripted_answers: List[str] = []
    if sid in {"1", "2"} and demo_file.is_file():
        scripted_answers = [
            line.strip()
            for line in demo_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    else:
        for q in plan_data.get("questions", []):
            mentions = q.get("good_answer_mentions", [])
            cite = q.get("citations", [{}])[0] if q.get("citations") else {}
            loc = f"in {cite.get('file', 'the module')}" if cite.get("file") else "in our implementation"
            main_ans = (
                f"When building this {loc}, we focused on {', '.join(mentions[:2]) if mentions else 'clean state transitions and bounded complexity'}. "
                f"Specifically, we traded off extra bookkeeping so that edge cases and failure paths remain deterministic."
            )
            follow_ans = (
                f"Under the hood, {mentions[-1] if mentions else 'the caller validates inputs before mutating state'}, "
                f"and if an unexpected input arrives we log the context and prevent cascading failures in downstream tasks."
            )
            scripted_answers.extend([main_ans, follow_ans])

    transport = ScriptedTransport(scripted_answers)
    ctx = _make_ctx(sid, round_no=round_no, use_llm=payload.use_llm, transport=transport)
    stages = _stages_for(round_no)
    try:
        run_pipeline(stages, ctx, from_stage="6", stop_after="7")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return get_repository_report(repository_id, round_no=round_no, demo_submission_id=sid, db=db)


@router.get("/repositories/{repository_id}/report")
def get_repository_report(
    repository_id: int,
    round_no: int = Query(1, ge=1),
    demo_submission_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    sid = _resolve_submission_id(repository_id, db, demo_submission_id)
    r_dir = round_dir(RUNS_ROOT, sid, round_no)
    report_path = r_dir / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Grading report not generated yet. Complete the interview first.")

    report_data = read_artifact(report_path)["data"]
    transcript_data = read_artifact(r_dir / "transcript.json")["data"] if (r_dir / "transcript.json").exists() else {}
    markdown_text = (r_dir / "report.md").read_text(encoding="utf-8") if (r_dir / "report.md").exists() else ""

    return {
        "submission_id": sid,
        "round_no": round_no,
        "report": report_data,
        "transcript": transcript_data,
        "stages": _stage_rows(r_dir, round_no),
        "markdown": markdown_text,
    }


# ---------------------------------------------------------------------------
# HackerRank-Style Coding Exercise & Targeted Codebase Questions
# ---------------------------------------------------------------------------


class RunCodingChallengeRequest(BaseModel):
    code: str


class TargetedQuestionAnswer(BaseModel):
    question_id: str
    answer: str
    follow_up_question: Optional[str] = ""
    follow_up_answer: Optional[str] = ""
    modified_code: Optional[str] = ""


class GenerateFollowUpRequest(BaseModel):
    question_id: str
    answer: str
    modified_code: Optional[str] = ""


class SubmitCodingDefenceRequest(BaseModel):
    code: Optional[str] = ""
    answers: List[TargetedQuestionAnswer]
    use_llm: bool = True
    round_no: int = 1


def _load_repo_files_and_name(repository_id: int, db: Session) -> tuple[Dict[str, str], str]:
    repository = db.get(Repository, repository_id)
    if repository:
        repo_name = repository.display_name or f"repository-{repository_id}"
        repo_path = (
            Path(repository.root_path)
            if repository.root_path
            else storage_service.repository_path(repository_id)
        )
        db_files = (
            db.query(RepositoryFile)
            .filter(RepositoryFile.repository_id == repository_id)
            .all()
        )
        files_map: Dict[str, str] = {}
        for f in db_files:
            if not f.is_text:
                continue
            candidate = repo_path / f.relative_path
            if candidate.is_file():
                try:
                    files_map[f.relative_path] = candidate.read_text(encoding="utf-8")
                except Exception:
                    continue
        if not files_map and repo_path.is_dir():
            for p in repo_path.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".go"}:
                    try:
                        rel = p.relative_to(repo_path).as_posix()
                        files_map[rel] = p.read_text(encoding="utf-8")
                    except Exception:
                        continue
        if files_map:
            return files_map, repo_name

    # Fallback to synthetic submission 1 files if repository has no files
    subs = {str(s["submission_id"]): s for s in all_submissions()}
    sub1 = subs.get("1", all_submissions()[0])
    return dict(sub1["files"]), str(sub1.get("label", "task_scheduler"))


def _format_challenge_for_client(challenge: Dict[str, Any]) -> Dict[str, Any]:
    import json as _json

    formatted_tcs = []
    for tc in challenge["test_cases"]:
        formatted_tcs.append(
            {
                "id": tc["id"],
                "name": tc["name"],
                "category": tc["category"],
                "input_display": _json.dumps(tc["args"], ensure_ascii=False),
                "expected_display": _json.dumps(tc["expected"], ensure_ascii=False),
                "is_hidden": bool(tc.get("is_hidden", False)),
            }
        )
    return {
        "challenge_id": challenge["challenge_id"],
        "archetype": challenge["archetype"],
        "title": challenge["title"],
        "difficulty": challenge["difficulty"],
        "language": challenge["language"],
        "function_name": challenge["function_name"],
        "target_file": challenge["target_file"],
        "target_symbol": challenge["target_symbol"],
        "target_lines": challenge["target_lines"],
        "secondary_file": challenge["secondary_file"],
        "secondary_symbol": challenge["secondary_symbol"],
        "secondary_lines": challenge["secondary_lines"],
        "reference_code": challenge["reference_code"],
        "problem_statement": challenge["problem_statement"],
        "constraints": challenge["constraints"],
        "starter_code": challenge["starter_code"],
        "reference_solution": challenge.get("reference_solution", challenge["starter_code"]),
        "solution_hint": challenge["solution_hint"],
        "test_cases": formatted_tcs,
        "targeted_questions": challenge["targeted_questions"],
    }


@router.get("/repositories/{repository_id}/coding-challenge")
def get_repository_coding_challenge(
    repository_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    files_map, repo_name = _load_repo_files_and_name(repository_id, db)
    challenge = build_coding_challenge(files_map, repo_name, repository_id, cache_dir=RUNS_ROOT)
    return _format_challenge_for_client(challenge)


@router.post("/repositories/{repository_id}/coding-challenge/run")
def run_repository_coding_challenge(
    repository_id: int,
    payload: RunCodingChallengeRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    files_map, repo_name = _load_repo_files_and_name(repository_id, db)
    challenge = build_coding_challenge(files_map, repo_name, repository_id, cache_dir=RUNS_ROOT)
    exec_result = execute_coding_challenge(challenge, payload.code)

    targets = _extract_codebase_targets(files_map, repo_name)
    updated_questions = build_targeted_questions(
        challenge,
        targets,
        student_code=payload.code,
        test_summary=exec_result,
    )
    return {
        **exec_result,
        "targeted_questions": updated_questions,
    }


@router.post("/repositories/{repository_id}/coding-challenge/follow-up")
def generate_repository_question_followup(
    repository_id: int,
    payload: GenerateFollowUpRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    files_map, repo_name = _load_repo_files_and_name(repository_id, db)
    challenge = build_coding_challenge(files_map, repo_name, repository_id, cache_dir=RUNS_ROOT)
    question = next(
        (q for q in challenge.get("targeted_questions", []) if q["id"] == payload.question_id),
        challenge["targeted_questions"][0] if challenge.get("targeted_questions") else {},
    )
    return generate_tailored_followup(
        question=question,
        student_answer=payload.answer,
        modified_code=payload.modified_code,
    )


@router.post("/repositories/{repository_id}/coding-challenge/submit-defence")
def submit_coding_challenge_and_defence(
    repository_id: int,
    payload: SubmitCodingDefenceRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _reload_env()
    sid = _resolve_submission_id(repository_id, db)
    round_no = max(1, payload.round_no)
    r_dir = round_dir(RUNS_ROOT, sid, round_no)
    r_dir.mkdir(parents=True, exist_ok=True)

    files_map, repo_name = _load_repo_files_and_name(repository_id, db)
    challenge = build_coding_challenge(files_map, repo_name, repository_id, cache_dir=RUNS_ROOT)
    targets = _extract_codebase_targets(files_map, repo_name)
    targeted_questions = build_targeted_questions(challenge, targets)

    plan_questions = []
    for q in targeted_questions:
        plan_questions.append(
            {
                "id": q["id"],
                "dimension": q["dimension"],
                "text": q["text"],
                "follow_up": q["follow_up"],
                "good_answer_mentions": q["good_answer_mentions"],
                "why_selected": q["why_selected"],
                "source": {"rule_id": f"tailored-{q['id'].lower()}", "origin": q.get("kind", "code_question")},
                "citations": [{"file": q.get("target_file", challenge["target_file"]), "line": targets["primary"]["start_line"]}],
            }
        )

    plan_data = {
        "round": round_no,
        "mode": "tailored-codebase-assessment",
        "max_questions": len(plan_questions),
        "questions": plan_questions,
        "not_triggered": [],
        "not_selected": [],
    }
    write_artifact(
        r_dir / "stage5_plan.json",
        stage="plan",
        stage_id="5",
        round_no=round_no,
        submission_id=sid,
        input_hash=hash_json(plan_data),
        data=plan_data,
        count_in=len(plan_questions),
        count_out=len(plan_questions),
        summary=f"{len(plan_questions)} tailored questions & live modifications on {repo_name}",
        model=None,
    )

    ans_by_id: Dict[str, TargetedQuestionAnswer] = {a.question_id: a for a in payload.answers}
    live_modifications: List[Dict[str, Any]] = []

    turns: List[Dict[str, Any]] = [
        {
            "speaker": "examiner",
            "text": f"Live Codebase Assessment started on {repo_name} (5 tailored questions, 30s timer per turn).",
            "kind": "intro",
            "question_id": None,
        }
    ]

    for q in targeted_questions:
        qid = q["id"]
        ans_item = ans_by_id.get(qid)
        main_text = (ans_item.answer.strip() if ans_item and ans_item.answer else "")
        follow_q_text = (
            ans_item.follow_up_question.strip()
            if ans_item and ans_item.follow_up_question
            else q.get("follow_up", "")
        )
        follow_text = (ans_item.follow_up_answer.strip() if ans_item and ans_item.follow_up_answer else "")
        mod_code = (ans_item.modified_code.strip() if ans_item and ans_item.modified_code else "")

        if q.get("kind") == "live_modification":
            starter = (q.get("starter_snippet") or q.get("raw_snippet") or "").strip()
            changed = bool(mod_code and mod_code != starter)
            live_modifications.append(
                {
                    "question_id": qid,
                    "target_file": q.get("target_file", challenge["target_file"]),
                    "target_lines": q.get("target_lines", challenge["target_lines"]),
                    "prompt": q.get("modification_prompt") or q["text"],
                    "starter_code": starter,
                    "modified_code": mod_code or starter,
                    "was_modified": changed,
                    "explanation": main_text,
                }
            )

        turns.append(
            {
                "speaker": "examiner",
                "text": q["text"],
                "kind": "question",
                "question_id": qid,
            }
        )
        if main_text:
            turn_kind = "follow_up_answer" if q["dimension"] == "communication_under_follow_up" else "answer"
            turns.append(
                {
                    "speaker": "student",
                    "text": main_text,
                    "kind": turn_kind,
                    "question_id": qid,
                }
            )
        if follow_text:
            turns.append(
                {
                    "speaker": "examiner",
                    "text": follow_q_text,
                    "kind": "follow_up",
                    "question_id": qid,
                }
            )
            turns.append(
                {
                    "speaker": "student",
                    "text": follow_text,
                    "kind": "follow_up_answer",
                    "question_id": qid,
                }
            )

    transcript_data = {
        "conversation_id": f"conv-{sid}-r{round_no}",
        "submission_id": sid,
        "round": round_no,
        "turns": turns,
        "stats": {
            "examiner_turns": sum(1 for t in turns if t["speaker"] == "examiner"),
            "multi_question_rejections": 0,
            "follow_up_fallbacks": 0,
            "model_follow_ups": sum(1 for t in turns if t.get("kind") == "follow_up"),
            "repeats": 0,
            "passes": 0,
            "feedback_requests": 0,
        },
    }
    write_artifact(
        r_dir / "transcript.json",
        stage="interview",
        stage_id="6",
        round_no=round_no,
        submission_id=sid,
        input_hash=hash_json(plan_data),
        data=transcript_data,
        count_in=len(plan_questions),
        count_out=len([t for t in turns if t["speaker"] == "student"]),
        summary=f"{len(turns)} turns recorded across 5 tailored codebase questions",
        model=None,
    )

    p1, p2, report_obj = run_final_grading_engine(
        transcript_data,
        plan_data,
        live_modifications=live_modifications,
        use_llm=payload.use_llm,
    )

    grade.write_outputs(
        r_dir,
        transcript_data,
        plan_data,
        (p1, p2, report_obj),
        submission_id=sid,
        round_no=round_no,
    )

    return get_repository_report(repository_id, round_no=round_no, demo_submission_id=sid, db=db)

