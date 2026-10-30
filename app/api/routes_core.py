"""Core API: events, snapshot, SSE stream, trace, customer pickers (spec 10)."""
import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from app import clock, db
from app.config import get_settings
from app.core import advance, forecast, ledger, risk, score as sc
from app.events.router import EventError, fire
from app.models import Advance, Bill, Consent, Customer, Entry, Repayment, ScoreEvent, Store, StoreCustomer
from app.realtime import broadcaster, trace as tr
from app.realtime.snapshot import INDICATOR_AMOUNT, build_snapshot

router = APIRouter(prefix="/api")


class EventIn(BaseModel):
    type: str
    payload: dict[str, Any] = {}


@router.post("/events")
async def post_event(body: EventIn):
    try:
        return await fire(body.type, body.payload)
    except EventError as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.get("/snapshot")
def get_snapshot():
    with db.session() as s:
        return build_snapshot(s)


@router.get("/stream")
async def stream(request: Request):
    q = broadcaster.subscribe()

    async def gen():
        try:
            with db.session() as s:
                first = [{"type": "snapshot", "data": build_snapshot(s)}]
                first += [{"type": "trace", "data": ln} for ln in tr.recent(s, 30)]
            for msg in first:
                yield {"data": json.dumps(msg, ensure_ascii=False)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=10)
                except asyncio.TimeoutError:
                    continue
                yield {"data": json.dumps(msg, ensure_ascii=False)}
        finally:
            broadcaster.unsubscribe(q)

    return EventSourceResponse(gen(), ping=15)


@router.get("/trace")
def get_trace(limit: int = 100):
    with db.session() as s:
        return tr.recent(s, min(max(limit, 1), 500))


@router.get("/customers")
def list_customers(store_id: str = "S1"):
    """Udhaar Book list: everyone at this store with balance, score band and the ₹340 risk dot."""
    today = clock.today()
    with db.session() as s:
        rows = s.exec(select(Customer).join(StoreCustomer, StoreCustomer.customer_id == Customer.id)
                      .where(StoreCustomer.store_id == store_id).order_by(Customer.name)).all()
        per = ledger.totals_by_customer(ledger.open_entries(s, store_id), today)
        feats = risk.load_features_bulk(s, store_id, [c.id for c in rows])
        last_paid = dict(s.exec(select(Repayment.customer_id, func.max(Repayment.created_at))
                                .where(Repayment.store_id == store_id).group_by(Repayment.customer_id)).all())
        out = []
        for c in rows:
            t = per.get(c.id)
            r = risk.compute(feats[c.id], INDICATOR_AMOUNT)
            out.append({
                "id": c.id, "name": c.name, "score": c.score, "score_band": sc.band(c.score),
                "outstanding": t.outstanding if t else 0, "verified": t.verified if t else 0,
                "overdue_days": t.oldest_overdue_days if t else 0,
                "band": r.band, "safe_limit": r.safe_limit, "last_paid": clock.iso(last_paid.get(c.id)),
            })
        return out


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: str, store_id: str = "S1", amount: int = INDICATOR_AMOUNT):
    """Merchant's view of one customer: this store's entries only, risk reasons, score history."""
    with db.session() as s:
        c = s.get(Customer, customer_id)
        if c is None or s.get(StoreCustomer, (store_id, customer_id)) is None:
            raise HTTPException(404, f"{customer_id} is not a customer of {store_id}")
        today = clock.today()
        entries = s.exec(select(Entry).where(Entry.store_id == store_id, Entry.customer_id == customer_id)
                         .order_by(Entry.created_at.desc())).all()
        reps = s.exec(select(Repayment).where(Repayment.store_id == store_id, Repayment.customer_id == customer_id)
                      .order_by(Repayment.created_at.desc())).all()
        hist = s.exec(select(ScoreEvent).where(ScoreEvent.customer_id == customer_id)
                      .order_by(ScoreEvent.created_at.desc()).limit(20)).all()
        t = ledger.totals([e for e in entries if e.state in ledger.OPEN_STATES], today)
        r = risk.evaluate(s, store_id, customer_id, max(1, amount))
        return {
            "id": c.id, "name": c.name, "mobile": c.mobile, "score": c.score, "score_band": sc.band(c.score),
            "outstanding": t.outstanding, "verified": t.verified, "overdue": t.overdue,
            "oldest_overdue_days": t.oldest_overdue_days,
            "risk": {"amount": r.amount, "band": r.band, "safe_limit": r.safe_limit, "credit_now": r.credit_now,
                     "collect_now": r.collect_now, "reasons": r.reasons, "ms": r.ms},
            "entries": [
                {"id": e.id, "amount": e.amount, "paid": e.paid_amount, "remaining": ledger.remaining(e),
                 "state": e.state, "verified": e.verified_at is not None, "override": e.override,
                 "created_at": clock.iso(e.created_at), "due_date": e.due_date.isoformat(),
                 "overdue_days": ledger.overdue_days(e, today)}
                for e in entries
            ],
            "repayments": [
                {"id": rp.id, "amount": rp.amount, "source": rp.source, "matched_by": rp.matched_by,
                 "created_at": clock.iso(rp.created_at)}
                for rp in reps
            ],
            "score_history": [
                {"delta": h.delta, "score_after": h.score_after, "reason": h.reason, "ts": clock.iso(h.created_at)}
                for h in hist
            ],
        }


@router.get("/confirm/{token}")
def confirm_sheet(token: str):
    """Data for the customer's Confirm sheet after scanning the Soundbox QR."""
    with db.session() as s:
        e = s.exec(select(Entry).where(Entry.confirm_token == token)).first()
        if e is None:
            raise HTTPException(404, "unknown confirmation code")
        store, c = s.get(Store, e.store_id), s.get(Customer, e.customer_id)
        first_time = s.exec(select(Consent.id).where(
            Consent.customer_id == c.id, Consent.type == "data_share", Consent.revoked_at == None)).first() is None  # noqa: E711
        return {
            "token": token, "entry_id": e.id, "state": e.state, "store": store.name, "store_id": store.id,
            "customer_id": c.id, "customer": c.name, "amount": e.amount, "label": "Groceries",
            "date": clock.iso(e.created_at), "due_date": e.due_date.isoformat(),
            "expires_at": clock.iso(e.token_expires_at), "first_time": first_time,
            "disputed_before": e.disputed_from_amount is not None,
        }


@router.get("/health")
def health():
    ok_db = True
    try:
        with db.session() as s:
            s.exec(select(Customer.id).limit(1)).all()
    except Exception:
        ok_db = False
    settings = get_settings()
    return {
        "ok": ok_db,
        "llm_mode": settings.llm_mode,
        "sarvam_configured": bool(settings.sarvam_api_key),
        "sarvam_reachable": None,  # probed once the LLM gateway lands
        "db": settings.db_path if ok_db else "unavailable",
        "sim_now": clock.iso(clock.now()),
    }


@router.get("/forecast")
def get_forecast(store_id: str = "S1"):
    with db.session() as s:
        return forecast.forecast(s, store_id)


@router.get("/advances/eligibility")
def advance_eligibility(store_id: str = "S1", bill_id: str = "B1"):
    try:
        with db.session() as s:
            return advance.eligibility(s, store_id, bill_id)
    except EventError as e:
        raise HTTPException(e.status, e.message)


@router.get("/advances/{advance_id}")
def advance_detail(advance_id: str):
    """Supplier Advance detail: terms, state and the split repayment ledger."""
    with db.session() as s:
        a = s.get(Advance, advance_id)
        if a is None:
            raise HTTPException(404, f"unknown advance {advance_id}")
        bill = s.get(Bill, a.bill_id)
        return {
            "id": a.id, "state": a.state, "lender": a.lender, "amount": a.amount, "fee": a.fee,
            "total_due": a.total_due, "repaid": a.repaid, "split_rate": a.split_rate,
            "backstop": a.backstop_date.isoformat() if a.backstop_date else None,
            "paid_to": bill.distributor, "bill_id": bill.id, "bill_amount": bill.amount,
            "bill_due": bill.due_date.isoformat(), "created_at": clock.iso(a.created_at),
            "accepted_at": clock.iso(a.accepted_at),
            "splits": advance.splits(s, a.id) if a.accepted_at else [],
        }
