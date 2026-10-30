"""Thin Sarvam AI client (v2 spec §9.3). Disabled unless SARVAM_ENABLED=true.
Never logs or prints the API key. Every function returns None on any failure, so callers
fall back to their rule/template result."""
import base64
import json
import re

import httpx

from app.config import get_settings

BASE_URL = "https://api.sarvam.ai"


def enabled() -> bool:
    st = get_settings()
    return bool(st.sarvam_enabled and st.sarvam_api_key.strip())


def _headers() -> dict:
    return {"api-subscription-key": get_settings().sarvam_api_key.strip()}


def _timeout() -> float:
    return float(get_settings().sarvam_timeout_s)


def _extract_json(text: str) -> dict:
    """Accept raw JSON or JSON wrapped in ```json fences."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


async def chat_json(system: str, user: str) -> dict | None:
    if not enabled():
        return None
    payload = {
        "model": get_settings().sarvam_chat_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{BASE_URL}/v1/chat/completions", headers=_headers(), json=payload)
            r.raise_for_status()
            return _extract_json(r.json()["choices"][0]["message"]["content"])
    except Exception:
        return None


async def text_to_speech(text: str, language_code: str = "kn-IN") -> bytes | None:
    """WAV bytes, or None."""
    if not enabled():
        return None
    st = get_settings()
    payload = {"text": text[:2500], "language_code": language_code, "model": st.sarvam_tts_model,
               "speaker": st.sarvam_tts_speaker}
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{BASE_URL}/text-to-speech", headers=_headers(), json=payload)
            r.raise_for_status()
            return base64.b64decode(r.json()["audios"][0])
    except Exception:
        return None


async def speech_to_text(audio: bytes, filename: str, mime: str, language_code: str = "unknown") -> dict | None:
    """{"transcript", "language_code"} or None. "unknown" = auto-detect (code-mixed speech is fine).
    VERIFY against Sarvam's current docs: the STT model name and these two response fields."""
    if not enabled():
        return None
    data = {"model": get_settings().sarvam_stt_model, "language_code": language_code}
    files = {"file": (filename, audio, mime)}
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{BASE_URL}/speech-to-text", headers=_headers(), data=data, files=files)
            r.raise_for_status()
            body = r.json()
            return {"transcript": body.get("transcript", ""), "language_code": body.get("language_code")}
    except Exception:
        return None
