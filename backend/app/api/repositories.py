import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.repository import CodeChunk, Repository, RepositoryFile
from app.schemas.repository import (
    AnalysisJobResponse,
    CodeChunkResponse,
    GithubRepositoryCreate,
    RepositoryFileResponse,
    RepositorySummaryResponse,
)
from app.services.analyzer import repository_analyzer
from app.services.storage import storage_service

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post("/github", response_model=dict)
def create_github_repository(payload: GithubRepositoryCreate, db: Session = Depends(get_db)):
    repository, job = repository_analyzer.create_github_repository(db, payload.github_url)
    return {
        "repository": RepositorySummaryResponse.model_validate(repository),
        "job": AnalysisJobResponse.model_validate(job),
    }


@router.post("/upload", response_model=dict)
def create_uploaded_repository(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Please upload a ZIP archive.")

    storage_service.ensure_dirs()
    temp_name = f"{uuid.uuid4()}-{file.filename}"
    temp_path = storage_service.upload_path(temp_name)
    with temp_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    repository, job = repository_analyzer.create_uploaded_repository(db, file.filename, temp_path)
    return {
        "repository": RepositorySummaryResponse.model_validate(repository),
        "job": AnalysisJobResponse.model_validate(job),
    }


@router.get("/{repository_id}", response_model=RepositorySummaryResponse)
def get_repository(repository_id: int, db: Session = Depends(get_db)):
    repository = db.get(Repository, repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


@router.get("/{repository_id}/status", response_model=AnalysisJobResponse)
def get_repository_status(repository_id: int, db: Session = Depends(get_db)):
    repository = db.get(Repository, repository_id)
    if not repository or not repository.jobs:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return repository.jobs[-1]


@router.get("/{repository_id}/files", response_model=list[RepositoryFileResponse])
def list_repository_files(repository_id: int, db: Session = Depends(get_db)):
    files = db.query(RepositoryFile).filter(RepositoryFile.repository_id == repository_id).all()
    return files


@router.get("/{repository_id}/chunks", response_model=list[CodeChunkResponse])
def list_repository_chunks(repository_id: int, db: Session = Depends(get_db)):
    chunks = db.query(CodeChunk).filter(CodeChunk.repository_id == repository_id).limit(200).all()
    return chunks
