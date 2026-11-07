from pathlib import Path

from app.core.config import settings


class StorageService:
    def __init__(self) -> None:
        self.root = settings.storage_root
        self.uploads = self.root / settings.upload_dir_name
        self.repositories = self.root / settings.repository_dir_name
        self.temp = self.root / settings.temp_dir_name

    def ensure_dirs(self) -> None:
        for path in (self.root, self.uploads, self.repositories, self.temp):
            path.mkdir(parents=True, exist_ok=True)

    def repository_path(self, repository_id: int) -> Path:
        return self.repositories / str(repository_id)

    def upload_path(self, filename: str) -> Path:
        return self.uploads / filename


storage_service = StorageService()
