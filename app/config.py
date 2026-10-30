"""Environment settings. Every tunable that may differ between laptops lives here."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    sarvam_api_key: str = ""
    sarvam_chat_model: str = "sarvam-105b"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker_hi: str = ""
    sarvam_tts_speaker_kn: str = ""

    llm_mode: str = "auto"  # auto | live | replay | record | template
    llm_timeout_s: float = 8.0
    fallback_llm_base_url: str = ""
    fallback_llm_api_key: str = ""
    fallback_llm_model: str = ""

    db_path: str = "bharosa.db"
    seed: int = 42

    # Every world-changing event advances the sim clock by this many seconds, so that
    # time windows (10-minute confirm expiry, 24 h integrity rules) behave realistically
    # while staying deterministic.
    event_tick_s: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
