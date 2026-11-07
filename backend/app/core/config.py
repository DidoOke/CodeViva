from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CodeViva API"
    api_prefix: str = "/api"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://codeviva:codeviva@db:5432/codeviva"
    storage_root: Path = Path("/app/storage")
    max_file_size_bytes: int = 512_000
    chunk_size_lines: int = 80
    chunk_overlap_lines: int = 20
    upload_dir_name: str = "uploads"
    repository_dir_name: str = "repositories"
    temp_dir_name: str = "tmp"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
