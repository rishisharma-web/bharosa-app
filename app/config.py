"""Environment settings (v2 spec §13.1). The Sarvam key is read here and nowhere else is it printed."""
from datetime import date, datetime, time
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_date: date = date(2026, 10, 31)
    public_base_url: str = "http://localhost:8000"
    demo_otp: str = "123456"
    admin_key: str = "change-me"
    db_path: str = "bharosa.db"

    sarvam_enabled: bool = False
    sarvam_api_key: str = ""
    sarvam_chat_model: str = "sarvam-105b"
    sarvam_stt_model: str = "saaras:v3"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "shubh"
    sarvam_timeout_s: float = 8.0
    # sarvam-105b "thinks" before answering unless told not to: 6–90 s per call with reasoning on,
    # about 1.5 s with it off. Every AI output is validated by code, so the default is "none".
    sarvam_reasoning_effort: str = "none"  # none | low | medium | high


@lru_cache
def get_settings() -> Settings:
    return Settings()


def today() -> date:
    """The fixed demo date. There is no clock that moves (spec §3.1)."""
    return get_settings().demo_date


def now() -> datetime:
    """Demo date with the real time of day, so 15-minute expiries work in real time."""
    return datetime.combine(today(), datetime.now().time().replace(microsecond=0))


def iso(dt: datetime | date | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def start_of_day(d: date) -> datetime:
    return datetime.combine(d, time(0, 0))
