"""Speech module: provider wire format (mocked HTTP) and API routes (fake provider)."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.speech import _provider
from app.main import app
from app.services.speech import (
    ElevenLabsSpeechProvider,
    SpeechError,
    SpeechNotConfiguredError,
    SynthesizedAudio,
    Transcript,
    TranscriptWord,
)


def make_provider(handler):
    return ElevenLabsSpeechProvider(
        "test-key",
        voice_id="defaultVoice",
        tts_model_id="eleven_flash_v2_5",
        tts_output_format="mp3_44100_128",
        voice_stability=0.6,
        voice_similarity_boost=0.75,
        stt_model_id="scribe_v1",
        transport=httpx.MockTransport(handler),
    )


def test_synthesize_sends_expected_request():
    seen = {}

    def handler(request: httpx.Request):
        seen["request"] = request
        return httpx.Response(200, content=b"MP3DATA")

    result = make_provider(handler).synthesize("  Explain your hash map.  ")

    req = seen["request"]
    assert req.url.path == "/v1/text-to-speech/defaultVoice"
    assert req.url.params["output_format"] == "mp3_44100_128"
    assert req.headers["xi-api-key"] == "test-key"
    body = json.loads(req.content)
    assert body["text"] == "Explain your hash map."
    assert body["model_id"] == "eleven_flash_v2_5"
    assert body["voice_settings"] == {"stability": 0.6, "similarity_boost": 0.75}
    assert result == SynthesizedAudio(audio=b"MP3DATA", media_type="audio/mpeg")


def test_synthesize_voice_override():
    paths = []
    provider = make_provider(lambda r: paths.append(r.url.path) or httpx.Response(200, content=b"x"))
    provider.synthesize("hi", voice_id="otherVoice")
    assert paths == ["/v1/text-to-speech/otherVoice"]


def test_transcribe_parses_response():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "text": " I used a dictionary. ",
                "language_code": "eng",
                "language_probability": 0.98,
                "words": [{"text": "I", "start": 0.1, "end": 0.2, "type": "word", "speaker_id": "speaker_0"}],
            },
        )

    t = make_provider(handler).transcribe(b"AUDIO", filename="a.webm", content_type="audio/webm", language_code="en")

    assert b'name="model_id"' in seen["body"] and b"scribe_v1" in seen["body"]
    assert b'name="language_code"' in seen["body"]
    assert b'filename="a.webm"' in seen["body"] and b"AUDIO" in seen["body"]
    assert t.text == "I used a dictionary."
    assert t.language_code == "eng"
    assert t.words == [TranscriptWord(text="I", start=0.1, end=0.2, type="word", speaker_id="speaker_0")]


@pytest.mark.parametrize("upstream,expected", [(401, 502), (500, 502), (422, 422)])
def test_upstream_errors_are_mapped(upstream, expected):
    provider = make_provider(lambda r: httpx.Response(upstream, text="nope"))
    with pytest.raises(SpeechError) as exc:
        provider.synthesize("hi")
    assert exc.value.status_code == expected


def test_network_error_is_wrapped():
    def handler(request):
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(SpeechError) as exc:
        make_provider(handler).transcribe(b"x")
    assert exc.value.status_code == 502


def test_empty_inputs_rejected_without_calling_upstream():
    provider = make_provider(lambda r: pytest.fail("should not call upstream"))
    with pytest.raises(SpeechError):
        provider.synthesize("   ")
    with pytest.raises(SpeechError):
        provider.transcribe(b"")


def test_missing_api_key():
    with pytest.raises(SpeechNotConfiguredError):
        ElevenLabsSpeechProvider(
            "",
            voice_id="v",
            tts_model_id="m",
            tts_output_format="mp3_44100_128",
            voice_stability=0.5,
            voice_similarity_boost=0.5,
            stt_model_id="scribe_v1",
        )


class FakeProvider:
    def synthesize(self, text, *, voice_id=None):
        return SynthesizedAudio(audio=f"{voice_id}:{text}".encode(), media_type="audio/mpeg")

    def transcribe(self, audio, *, filename="audio.webm", content_type="application/octet-stream", language_code=None):
        return Transcript(text=f"{len(audio)} bytes", language_code=language_code, words=[TranscriptWord("hi", 0.0, 0.5)])


@pytest.fixture
def client():
    app.dependency_overrides[_provider] = lambda: FakeProvider()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_tts_route(client):
    r = client.post("/api/speech/tts", json={"text": "hello", "voice_id": "abc123"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"abc123:hello"


def test_tts_route_validates(client):
    assert client.post("/api/speech/tts", json={"text": ""}).status_code == 422
    assert client.post("/api/speech/tts", json={"text": "x", "voice_id": "../evil"}).status_code == 422
    assert client.post("/api/speech/tts", json={"text": "x" * 10_000}).status_code == 413


def test_stt_route(client):
    r = client.post(
        "/api/speech/stt",
        files={"file": ("answer.webm", b"12345", "audio/webm")},
        data={"language_code": "en"},
    )
    assert r.status_code == 200
    assert r.json() == {
        "text": "5 bytes",
        "language_code": "en",
        "language_probability": None,
        "words": [{"text": "hi", "start": 0.0, "end": 0.5, "type": "word", "speaker_id": None}],
    }


def test_routes_return_503_when_unconfigured(monkeypatch):
    import app.services.speech as speech

    monkeypatch.setattr(speech, "_provider", None)
    monkeypatch.setattr(speech.settings, "elevenlabs_api_key", "")
    r = TestClient(app).post("/api/speech/tts", json={"text": "hello"})
    assert r.status_code == 503


def test_status_reports_configuration(monkeypatch):
    import app.services.speech as speech

    monkeypatch.setattr(speech.settings, "elevenlabs_api_key", "")
    assert TestClient(app).get("/api/speech/status").json() == {"tts": False, "stt": False, "provider": None}
    monkeypatch.setattr(speech.settings, "elevenlabs_api_key", "k")
    assert TestClient(app).get("/api/speech/status").json() == {"tts": True, "stt": True, "provider": "elevenlabs"}
