"""Shared agent plumbing (spec 7.9): the LLM proposes, code decides.

`call_llm` asks the gateway for JSON matching a Pydantic schema, makes one repair retry on
a parse error (live calls only), and otherwise returns None so the agent uses its
deterministic fallback. Every call writes a trace line with source live | replay | template
(shown in the UI as LIVE / CACHED / FALLBACK).
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.adapters import llm
from app.realtime.trace import trace

PROMPT_VERSION = "v1"
PROMPTS = Path(__file__).resolve().parent / "prompts"

T = TypeVar("T", bound=BaseModel)


@dataclass
class AgentResult(Generic[T]):
    data: T
    source: str  # live | replay | template
    ms: float = 0.0
    note: str | None = None


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def _parse(content: str, schema: type[T]) -> T:
    text = content.strip()
    m = re.search(r"\{.*\}", text, re.S)  # tolerate prose or ``` fences around the JSON
    return schema.model_validate(json.loads(m.group(0) if m else text))


def response_format(schema: type[BaseModel]) -> dict:
    return {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()}}


async def call_llm(agent: str, node: str, system: str, payload: dict, schema: type[T],
                   key_extra: dict | None = None) -> tuple[T | None, str, float]:
    """Returns (parsed or None, source, ms). None means: use the deterministic fallback."""
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]
    fmt = response_format(schema)
    res = await llm.complete(agent, PROMPT_VERSION, {"payload": payload, **(key_extra or {})}, messages, fmt)
    if res.content is None:
        return None, "template", res.ms
    try:
        return _parse(res.content, schema), res.source, res.ms
    except (ValueError, ValidationError) as e:
        if res.source != "live":
            trace(node, "Cached output invalid → fallback", {"error": str(e)[:200]}, source=res.source)
            return None, "template", res.ms
        repair = messages + [{"role": "assistant", "content": res.content},
                             {"role": "user", "content": f"That was not valid: {str(e)[:300]}. "
                                                         "Reply with JSON only, matching the schema."}]
        content = await llm.live_repair(repair, fmt)
        if content:
            try:
                return _parse(content, schema), "live", res.ms
            except (ValueError, ValidationError):
                pass
        trace(node, "Invalid JSON twice → fallback", {"error": str(e)[:200]}, source="live")
        return None, "template", res.ms


def rupee_figures(text: str) -> set[int]:
    """Every ₹/Rs amount in a text, as integers (₹2,000 / Rs. 2000 / 2000 rupaye)."""
    pats = [r"(?:₹|rs\.?\s*|inr\s*)\s*([\d,]+)", r"([\d,]+)\s*(?:rupaye|rupees|rupay|रुपये|रुपए)"]
    out = set()
    for p in pats:
        for m in re.finditer(p, text, re.I):
            digits = m.group(1).replace(",", "")
            if digits.isdigit():
                out.add(int(digits))
    return out
