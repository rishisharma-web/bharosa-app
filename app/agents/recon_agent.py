"""Reconciliation Agent (spec 7.9.3): who sent an unclear UPI payment?

Only used after the deterministic rules fail (core/reconcile.py, rule 3). The validator keeps
the answer inside the candidate list and clamps confidence; the handler auto-applies at ≥ 0.85
and otherwise asks the merchant. Fallback: best name ratio × 0.8 (usually routes to a human).
"""
from typing import Optional

from pydantic import BaseModel

from app.agents.base import call_llm, prompt
from app.core import reconcile
from app.realtime.trace import trace


class ReconOut(BaseModel):
    customer_id: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""


async def match(payment: dict, candidates: list[dict]) -> dict:
    payload = {"payment": {k: payment.get(k) for k in ("amount", "payer_vpa", "payer_name", "remark")},
               "candidates": [{k: c[k] for k in ("id", "name", "outstanding", "open_entries")} for c in candidates]}
    out, source, ms = await call_llm("recon", "recon_agent", prompt("recon"), payload, ReconOut)
    if out is None:
        res = reconcile.fallback_match(payment, candidates)
        res["ms"] = ms
        return res
    ids = {c["id"] for c in candidates}
    if out.customer_id not in ids:
        if out.customer_id is not None:
            trace("validator", f"Recon picked {out.customer_id}, not a candidate → no match")
        out.customer_id, out.confidence = None, 0.0
    return {"customer_id": out.customer_id, "confidence": round(max(0.0, min(1.0, out.confidence)), 3),
            "reason": out.reason[:200], "source": source, "ms": ms}
