"""LLM gateway (spec 7.10): one door for every agent call, with a cache for deterministic demos.

LLM_MODE
  auto      cache hit → replay; else live (timeout); any failure → no content (caller falls back)
  live      always call the provider
  record    call live and save the response to fixtures/llm_cache/<key>.json
  replay    cache only; a miss → no content
  template  never call anything (agents use their deterministic fallbacks)

Cache key = sha256(agent + PROMPT_VERSION + canonical_json(input)).

Providers share one OpenAI-compatible chat interface. The optional fallback provider is
configured by FALLBACK_LLM_*; the Sarvam provider is registered in `providers()` once the
Sarvam integration lands. With no provider configured, `auto` behaves like `replay`.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from app.config import get_settings

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "llm_cache"


class Provider(Protocol):
    name: str

    async def chat(self, messages: list[dict], response_format: dict | None, timeout: float) -> str: ...


class OpenAICompatibleProvider:
    """POST {base_url}/chat/completions; returns choices[0].message.content."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str, auth_header: str = "Authorization",
                 auth_prefix: str = "Bearer "):
        self.name, self.base_url, self.model = name, base_url.rstrip("/"), model
        self.headers = {auth_header: f"{auth_prefix}{api_key}", "Content-Type": "application/json"}

    async def chat(self, messages: list[dict], response_format: dict | None, timeout: float) -> str:
        body = {"model": self.model, "messages": messages, "temperature": 0}
        if response_format:
            body["response_format"] = response_format
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{self.base_url}/chat/completions", headers=self.headers, json=body)
            if r.status_code == 400 and response_format and response_format.get("type") == "json_schema":
                body["response_format"] = {"type": "json_object"}  # provider without json_schema support
                r = await client.post(f"{self.base_url}/chat/completions", headers=self.headers, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


def providers() -> list[Provider]:
    st = get_settings()
    out: list[Provider] = []
    if st.fallback_llm_base_url and st.fallback_llm_api_key and st.fallback_llm_model:
        out.append(OpenAICompatibleProvider("fallback", st.fallback_llm_base_url, st.fallback_llm_api_key,
                                            st.fallback_llm_model))
    return out


@dataclass
class GatewayResult:
    content: str | None
    source: str  # live | replay | template
    ms: float
    key: str
    error: str | None = None


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def cache_key(agent: str, prompt_version: str, key_input) -> str:
    return hashlib.sha256(f"{agent}|{prompt_version}|{canonical(key_input)}".encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> str | None:
    p = _cache_path(key)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))["content"]
    return None


def _write_cache(key: str, agent: str, content: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(json.dumps({"agent": agent, "content": content}, ensure_ascii=False, indent=1),
                                encoding="utf-8")


async def _live(messages: list[dict], response_format: dict | None) -> tuple[str | None, str | None]:
    errors = []
    for p in providers():
        try:
            return await p.chat(messages, response_format, get_settings().llm_timeout_s), None
        except Exception as e:  # timeout, HTTP error, bad payload: try the next provider
            errors.append(f"{p.name}: {type(e).__name__}: {e}")
    return None, "; ".join(errors) or "no LLM provider configured"


async def complete(agent: str, prompt_version: str, key_input, messages: list[dict],
                   response_format: dict | None = None, mode: str | None = None) -> GatewayResult:
    mode = mode or get_settings().llm_mode
    key = cache_key(agent, prompt_version, key_input)
    t0 = time.perf_counter()

    def done(content, source, error=None):
        return GatewayResult(content, source, round((time.perf_counter() - t0) * 1000, 1), key, error)

    if mode == "template":
        return done(None, "template")
    if mode in ("auto", "replay"):
        cached = _read_cache(key)
        if cached is not None:
            return done(cached, "replay")
        if mode == "replay":
            return done(None, "template", "cache miss")
    content, err = await _live(messages, response_format)
    if content is not None and mode == "record":
        _write_cache(key, agent, content)
    return done(content, "live" if content is not None else "template", err)


async def live_repair(messages: list[dict], response_format: dict | None) -> str | None:
    """One extra live call used by the agents' repair retry (never cached)."""
    content, _ = await _live(messages, response_format)
    return content
