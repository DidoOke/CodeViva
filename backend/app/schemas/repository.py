from datetime import datetime

from pydantic import BaseModel, Field

from app.models.repository import AnalysisJobStatus, RepositorySource, RepositoryStatus


class GithubRepositoryCreate(BaseModel):
    github_url: str = Field(..., examples=["https://github.com/octocat/Hello-World"])


class RepositorySummaryResponse(BaseModel):
    id: int
    source_type: RepositorySource
    display_name: str
    status: RepositoryStatus
    github_url: str | None = None
    original_filename: str | None = None
    detected_languages: list[str] = Field(default_factory=list)
    summary_json: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnalysisJobResponse(BaseModel):
    id: int
    repository_id: int
    status: AnalysisJobStatus
    stage: str
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class RepositoryFileResponse(BaseModel):
    id: int
    relative_path: str
    file_type: str
    language: str | None = None
    size_bytes: int
    sha256: str
    is_text: bool
    line_count: int
    metadata_json: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True


class CodeChunkResponse(BaseModel):
    id: int
    repository_file_id: int
    chunk_index: int
    chunk_type: str
    start_line: int
    end_line: int
    content: str
    metadata_json: dict = Field(default_factory=dict)

    class Config:
        from_attributes = True
