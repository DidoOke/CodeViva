"""Text-to-speech and speech-to-text for the voice examiner.

The rest of the app talks to `SpeechProvider`, never to a vendor directly, so the
provider can be swapped (or faked in tests) without touching callers.

The default provider is ElevenLabs, matching the project proposal:
- TTS: POST /v1/text-to-speech/{voice_id}  -> audio bytes
- STT: POST /v1/speech-to-text (Scribe)    -> transcript with word timings
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

import httpx

from app.core.config import settings


class SpeechError(RuntimeError):
    """Raised when the speech provider fails or is misconfigured."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class SpeechNotConfiguredError(SpeechError):
    def __init__(self, message: str = "Speech provider is not configured (set ELEVENLABS_API_KEY).") -> None:
        super().__init__(message, status_code=503)


@dataclass
class SynthesizedAudio:
    audio: bytes
    media_type: str  # e.g. "audio/mpeg"


@dataclass
class TranscriptWord:
    text: str
    start: Optional[float]  # seconds
    end: Optional[float]
    type: str = "word"  # "word" | "spacing" | "audio_event"
    speaker_id: Optional[str] = None


@dataclass
class Transcript:
    text: str
    language_code: Optional[str] = None
    language_probability: Optional[float] = None
    words: list[TranscriptWord] = field(default_factory=list)


class SpeechProvider(Protocol):
    def synthesize(self, text: str, *, voice_id: Optional[str] = None) -> SynthesizedAudio: ...

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.webm",
        content_type: str = "application/octet-stream",
        language_code: Optional[str] = None,
    ) -> Transcript: ...


_OUTPUT_FORMAT_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "pcm": "audio/pcm",
    "ulaw": "audio/basic",
    "opus": "audio/ogg",
}


def _media_type_for(output_format: str) -> str:
    return _OUTPUT_FORMAT_MEDIA_TYPES.get(output_format.split("_", 1)[0], "application/octet-stream")


class ElevenLabsSpeechProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.elevenlabs.io",
        voice_id: str,
        tts_model_id: str,
        tts_output_format: str,
        voice_stability: float,
        voice_similarity_boost: float,
        stt_model_id: str,
        timeout_seconds: float = 60.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        if not api_key:
            raise SpeechNotConfiguredError()
        self.voice_id = voice_id
        self.tts_model_id = tts_model_id
        self.tts_output_format = tts_output_format
        self.voice_stability = voice_stability
        self.voice_similarity_boost = voice_similarity_boost
        self.stt_model_id = stt_model_id
        self._client = httpx.Client(
            base_url=base_url,
            headers={"xi-api-key": api_key},
            timeout=timeout_seconds,
            transport=transport,
        )

    def synthesize(self, text: str, *, voice_id: Optional[str] = None) -> SynthesizedAudio:
        text = text.strip()
        if not text:
            raise SpeechError("Text to synthesize is empty.", status_code=400)

        response = self._request(
            "POST",
            f"/v1/text-to-speech/{voice_id or self.voice_id}",
            params={"output_format": self.tts_output_format},
            json={
                "text": text,
                "model_id": self.tts_model_id,
                "voice_settings": {
                    "stability": self.voice_stability,
                    "similarity_boost": self.voice_similarity_boost,
                },
            },
        )
        return SynthesizedAudio(audio=response.content, media_type=_media_type_for(self.tts_output_format))

    def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "audio.webm",
        content_type: str = "application/octet-stream",
        language_code: Optional[str] = None,
    ) -> Transcript:
        if not audio:
            raise SpeechError("Audio to transcribe is empty.", status_code=400)

        data = {"model_id": self.stt_model_id, "tag_audio_events": "false"}
        if language_code:
            data["language_code"] = language_code

        response = self._request(
            "POST",
            "/v1/speech-to-text",
            data=data,
            files={"file": (filename, audio, content_type)},
        )
        body = response.json()
        return Transcript(
            text=(body.get("text") or "").strip(),
            language_code=body.get("language_code"),
            language_probability=body.get("language_probability"),
            words=[
                TranscriptWord(
                    text=w.get("text", ""),
                    start=w.get("start"),
                    end=w.get("end"),
                    type=w.get("type", "word"),
                    speaker_id=w.get("speaker_id"),
                )
                for w in body.get("words") or []
            ],
        )

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise SpeechError(f"Speech provider request failed: {exc}") from exc
        if response.status_code >= 400:
            # Pass client errors (bad voice id, unsupported audio) through; map auth and
            # server failures to 502 so callers don't mistake them for their own mistakes.
            status = response.status_code if response.status_code in (400, 404, 413, 415, 422) else 502
            raise SpeechError(
                f"Speech provider returned {response.status_code}: {response.text[:500]}",
                status_code=status,
            )
        return response


_provider: Optional[SpeechProvider] = None


def get_speech_provider() -> SpeechProvider:
    """Lazily build the configured provider. Use as a FastAPI dependency."""
    global _provider
    if _provider is None:
        _provider = ElevenLabsSpeechProvider(
            settings.elevenlabs_api_key,
            base_url=settings.elevenlabs_base_url,
            voice_id=settings.elevenlabs_voice_id,
            tts_model_id=settings.elevenlabs_tts_model_id,
            tts_output_format=settings.elevenlabs_tts_output_format,
            voice_stability=settings.elevenlabs_voice_stability,
            voice_similarity_boost=settings.elevenlabs_voice_similarity_boost,
            stt_model_id=settings.elevenlabs_stt_model_id,
            timeout_seconds=settings.speech_timeout_seconds,
        )
    return _provider
