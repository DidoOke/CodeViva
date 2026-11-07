from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.core.config import settings
from app.schemas.speech import SpeechStatusResponse, SynthesizeRequest, TranscriptResponse
from app.services.speech import SpeechError, SpeechProvider, get_speech_provider

router = APIRouter(prefix="/speech", tags=["speech"])


def _provider() -> SpeechProvider:
    try:
        return get_speech_provider()
    except SpeechError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/status", response_model=SpeechStatusResponse)
def speech_status():
    """Lets clients decide whether to use the server or fall back to browser speech."""
    configured = bool(settings.elevenlabs_api_key)
    return SpeechStatusResponse(
        tts=configured,
        stt=configured,
        provider="elevenlabs" if configured else None,
    )


@router.post(
    "/tts",
    response_class=Response,
    responses={200: {"content": {"audio/mpeg": {}}, "description": "Synthesized speech audio"}},
)
def text_to_speech(payload: SynthesizeRequest, provider: SpeechProvider = Depends(_provider)):
    if len(payload.text) > settings.max_tts_chars:
        raise HTTPException(status_code=413, detail=f"Text exceeds {settings.max_tts_chars} characters.")
    try:
        result = provider.synthesize(payload.text, voice_id=payload.voice_id)
    except SpeechError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=result.audio, media_type=result.media_type)


@router.post("/stt", response_model=TranscriptResponse)
def speech_to_text(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    provider: SpeechProvider = Depends(_provider),
):
    audio = file.file.read(settings.max_stt_audio_bytes + 1)
    if len(audio) > settings.max_stt_audio_bytes:
        raise HTTPException(status_code=413, detail="Audio file is too large.")
    try:
        transcript = provider.transcribe(
            audio,
            filename=file.filename or "audio.webm",
            content_type=file.content_type or "application/octet-stream",
            language_code=language_code,
        )
    except SpeechError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return transcript
