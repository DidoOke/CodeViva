import hashlib
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.repository import AnalysisJob, AnalysisJobStatus, CodeChunk, Repository, RepositoryFile, RepositoryStatus
from app.services.storage import storage_service

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".next",
    "venv",
    ".venv",
    "__pycache__",
}

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".md": "markdown",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".css": "css",
}

ENTRYPOINT_CANDIDATES = {"main.py", "app.py", "manage.py", "package.json", "index.js", "server.js"}


class RepositoryAnalyzer:
    def create_github_repository(self, db: Session, github_url: str) -> tuple[Repository, AnalysisJob]:
        name = Path(urlparse(github_url).path.rstrip("/")).name or "repository"
        repository = Repository(
            source_type="github",
            github_url=github_url,
            display_name=name,
            status=RepositoryStatus.PENDING,
        )
        db.add(repository)
        db.commit()
        db.refresh(repository)

        job = AnalysisJob(repository_id=repository.id, status=AnalysisJobStatus.PENDING, stage="queued")
        db.add(job)
        db.commit()
        db.refresh(job)

        self._analyse_github(db, repository, job)
        return repository, job

    def create_uploaded_repository(self, db: Session, uploaded_filename: str, temp_zip_path: Path) -> tuple[Repository, AnalysisJob]:
        repository = Repository(
            source_type="upload",
            original_filename=uploaded_filename,
            display_name=Path(uploaded_filename).stem,
            status=RepositoryStatus.PENDING,
        )
        db.add(repository)
        db.commit()
        db.refresh(repository)

        job = AnalysisJob(repository_id=repository.id, status=AnalysisJobStatus.PENDING, stage="queued")
        db.add(job)
        db.commit()
        db.refresh(job)

        self._analyse_upload(db, repository, job, temp_zip_path)
        return repository, job

    def _analyse_github(self, db: Session, repository: Repository, job: AnalysisJob) -> None:
        repo_path = storage_service.repository_path(repository.id)
        self._start_job(db, repository, job, "cloning")
        if repo_path.exists():
            shutil.rmtree(repo_path)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                repository.github_url or "",
                str(repo_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._run_file_analysis(db, repository, job, repo_path)

    def _analyse_upload(self, db: Session, repository: Repository, job: AnalysisJob, temp_zip_path: Path) -> None:
        repo_path = storage_service.repository_path(repository.id)
        self._start_job(db, repository, job, "extracting")
        if repo_path.exists():
            shutil.rmtree(repo_path)
        repo_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temp_zip_path, "r") as archive:
            archive.extractall(repo_path)
        root = self._normalize_root(repo_path)
        self._run_file_analysis(db, repository, job, root)

    def _run_file_analysis(self, db: Session, repository: Repository, job: AnalysisJob, repo_path: Path) -> None:
        self._set_stage(db, job, repository, "indexing")
        files = self._discover_files(repo_path)

        language_counter: Counter[str] = Counter()
        top_level_dirs = Counter()
        tests_count = 0
        code_files = 0
        entrypoints: list[str] = []

        for item in files:
            db_file = RepositoryFile(
                repository_id=repository.id,
                relative_path=item["relative_path"],
                file_type=item["file_type"],
                language=item["language"],
                size_bytes=item["size_bytes"],
                sha256=item["sha256"],
                is_text=item["is_text"],
                line_count=item["line_count"],
                metadata_json=item["metadata_json"],
            )
            db.add(db_file)
            db.flush()

            if item["language"]:
                language_counter[item["language"]] += 1
            if item["file_type"] == "test":
                tests_count += 1
            if item["file_type"] == "source":
                code_files += 1
            parts = Path(item["relative_path"]).parts
            if parts:
                top_level_dirs[parts[0]] += 1
            if Path(item["relative_path"]).name in ENTRYPOINT_CANDIDATES:
                entrypoints.append(item["relative_path"])

            for chunk in self._chunk_file(item):
                db.add(
                    CodeChunk(
                        repository_id=repository.id,
                        repository_file_id=db_file.id,
                        chunk_index=chunk["chunk_index"],
                        chunk_type=chunk["chunk_type"],
                        start_line=chunk["start_line"],
                        end_line=chunk["end_line"],
                        content=chunk["content"],
                        metadata_json=chunk["metadata_json"],
                    )
                )

        repository.root_path = str(repo_path)
        repository.detected_languages = [name for name, _ in language_counter.most_common(5)]
        repository.summary_json = {
            "file_count": len(files),
            "code_file_count": code_files,
            "test_file_count": tests_count,
            "top_level_directories": [name for name, _ in top_level_dirs.most_common(8)],
            "entrypoints": entrypoints,
            "dominant_languages": [name for name, _ in language_counter.most_common(3)],
        }
        repository.status = RepositoryStatus.COMPLETED
        job.status = AnalysisJobStatus.COMPLETED
        job.stage = "completed"
        db.add(repository)
        db.add(job)
        db.commit()
        db.refresh(repository)
        db.refresh(job)

    def _discover_files(self, repo_path: Path) -> list[dict]:
        discovered: list[dict] = []
        for path in repo_path.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORED_DIRECTORIES for part in path.parts):
                continue
            size = path.stat().st_size
            if size > settings.max_file_size_bytes:
                continue
            relative_path = path.relative_to(repo_path).as_posix()
            is_text, content = self._read_text_file(path)
            if not is_text:
                continue
            suffix = path.suffix.lower()
            language = LANGUAGE_MAP.get(suffix)
            line_count = len(content.splitlines())
            file_type = self._detect_file_type(path, relative_path)
            discovered.append(
                {
                    "relative_path": relative_path,
                    "file_type": file_type,
                    "language": language,
                    "size_bytes": size,
                    "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "is_text": True,
                    "line_count": line_count,
                    "content": content,
                    "metadata_json": {
                        "suffix": suffix,
                        "name": path.name,
                    },
                }
            )
        return discovered

    def _chunk_file(self, file_item: dict) -> list[dict]:
        lines = file_item["content"].splitlines()
        if not lines:
            return []
        chunks: list[dict] = []
        start = 0
        chunk_index = 0
        step = max(1, settings.chunk_size_lines - settings.chunk_overlap_lines)
        chunk_type = file_item["file_type"] if file_item["file_type"] in {"test", "config", "docs"} else "code"
        while start < len(lines):
            end = min(start + settings.chunk_size_lines, len(lines))
            content = "\n".join(lines[start:end]).strip()
            if content:
                chunks.append(
                    {
                        "chunk_index": chunk_index,
                        "chunk_type": chunk_type,
                        "start_line": start + 1,
                        "end_line": end,
                        "content": content,
                        "metadata_json": {
                            "path": file_item["relative_path"],
                            "language": file_item["language"],
                        },
                    }
                )
                chunk_index += 1
            start += step
        return chunks

    def _detect_file_type(self, path: Path, relative_path: str) -> str:
        lower = relative_path.lower()
        if path.name.startswith("test_") or "/tests/" in lower or lower.endswith(".test.js") or lower.endswith("_test.py"):
            return "test"
        if path.name.lower() in {"readme.md", "readme"} or path.suffix.lower() == ".md":
            return "docs"
        if path.name.lower() in {"package.json", "pyproject.toml", "requirements.txt", "dockerfile", "docker-compose.yml", "docker-compose.yaml"}:
            return "config"
        return "source"

    def _normalize_root(self, repo_path: Path) -> Path:
        children = [child for child in repo_path.iterdir()]
        if len(children) == 1 and children[0].is_dir():
            return children[0]
        return repo_path

    def _read_text_file(self, path: Path) -> tuple[bool, str]:
        try:
            content = path.read_text(encoding="utf-8")
            return True, content
        except UnicodeDecodeError:
            return False, ""

    def _start_job(self, db: Session, repository: Repository, job: AnalysisJob, stage: str) -> None:
        repository.status = RepositoryStatus.PROCESSING
        job.status = AnalysisJobStatus.PROCESSING
        job.stage = stage
        db.add(repository)
        db.add(job)
        db.commit()

    def _set_stage(self, db: Session, job: AnalysisJob, repository: Repository, stage: str) -> None:
        job.stage = stage
        repository.status = RepositoryStatus.PROCESSING
        db.add(job)
        db.add(repository)
        db.commit()


repository_analyzer = RepositoryAnalyzer()
