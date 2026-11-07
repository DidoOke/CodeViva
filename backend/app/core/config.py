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

    # Speech (TTS / STT) — ElevenLabs
    elevenlabs_api_key: str = ""
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # "Rachel": calm, neutral premade voice
    elevenlabs_tts_model_id: str = "eleven_flash_v2_5"  # low latency for turn-taking
    elevenlabs_tts_output_format: str = "mp3_44100_128"
    elevenlabs_voice_stability: float = 0.6  # higher = steadier, calmer delivery
    elevenlabs_voice_similarity_boost: float = 0.75
    elevenlabs_stt_model_id: str = "scribe_v1"
    speech_timeout_seconds: float = 60.0
    max_tts_chars: int = 2_500
    max_stt_audio_bytes: int = 25_000_000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
