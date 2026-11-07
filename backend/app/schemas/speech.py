from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voice_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9]+$")


class TranscriptWordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    type: str = "word"
    speaker_id: Optional[str] = None


class TranscriptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    text: str
    language_code: Optional[str] = None
    language_probability: Optional[float] = None
    words: list[TranscriptWordResponse] = []


class SpeechStatusResponse(BaseModel):
    tts: bool
    stt: bool
    provider: Optional[str] = None
