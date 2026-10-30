"""Voice endpoints (v2 spec §7 Voice). They exist only when SARVAM_ENABLED is on (404 otherwise)."""
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response

from app.ai import sarvam

router = APIRouter(prefix="/api/voice")
MAX_AUDIO = 2_000_000  # ~30 s of compressed speech


def _require() -> None:
    if not sarvam.enabled():
        raise HTTPException(404, "Voice is available when AI is enabled")


@router.post("/transcribe")
async def transcribe(file: UploadFile):
    _require()
    audio = await file.read()
    if not audio or len(audio) > MAX_AUDIO:
        raise HTTPException(422, "Send up to 30 seconds of audio")
    out = await sarvam.speech_to_text(audio, file.filename or "speech.webm", file.content_type or "audio/webm")
    if not out or not out.get("transcript"):
        raise HTTPException(502, "Didn't catch that. Try again or type it.")
    return out


@router.get("/speak")
async def speak(text: str, lang: str = "kn-IN"):
    _require()
    wav = await sarvam.text_to_speech(text[:300], lang)
    if not wav:
        raise HTTPException(502, "Speech is unavailable right now")
    return Response(content=wav, media_type="audio/wav")
