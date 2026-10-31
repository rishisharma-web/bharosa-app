"""Merchant app endpoints (v2 spec §7 Merchant). Scoped to the merchant's own store.

Privacy (spec §6.2): nothing here returns entries from other stores, other stores' names, or a
customer's per-store amounts elsewhere. Network facts reach the merchant only as a score band, a
limit and the tag "New · Paytm network".
"""
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import auth, bus, db
from app.agents import growth_agent
from app.ai import sarvam
from app.config import start_of_day, today
from app.core import activity, advance, basket, festive, growth, mandates, payments, requests as req, risk
from app.core import score as score_mod
from app.core.money import inr
from app.errors import EventError
from app.models import (
    Advance, BasketOffer, Bill, Customer, Entry, Message, Payment, PromiseRow, Store, StoreCustomer,
)

router = APIRouter(prefix="/api/merchant")
Me = auth.Principal
INDICATOR = 340  # the Udhaar Book shows each customer's band for a typical ₹340 request


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=300)


def _scopes(t: bus.Tx, store_id: str, *customers: str) -> None:
    t.touch(f"merchant:{store_id}", f"soundbox:{store_id}", *(f"customer:{c}" for c in customers))


# ---------------------------------------------------------------- read models

def _open_here(s: Session, store_id: str) -> list[Entry]:
    return list(s.exec(select(Entry).where(Entry.store_id == store_id,
                                           Entry.state.in_(("verified", "partly_paid")))).all())


def _tags(s: Session, store_id: str, customer_id: str) -> list[str]:
    first = s.exec(select(Entry).where(Entry.store_id == store_id, Entry.customer_id == customer_id,
                                       Entry.source == "counter").order_by(Entry.id)).first()
    return list(first.tags or []) if first else []


def summary(s: Session, store_id: str) -> dict:
    store = s.get(Store, store_id)
    opens = _open_here(s, store_id)
    lo = start_of_day(today())
    upi_today = sum(p.amount for p in s.exec(select(Payment).where(
        Payment.store_id == store_id, Payment.created_at >= lo, Payment.method.in_(("upi", "credit_line")))).all())
    week_end = today() + timedelta(days=7)
    won = {e.customer_id for e in s.exec(select(Entry).where(
        Entry.store_id == store_id, Entry.source == "counter", Entry.created_at >= lo,
        Entry.state.in_(("verified", "partly_paid", "settled")))).all()
        if "New · Paytm network" in (e.tags or [])}
    outstanding = sum(e.amount - e.paid for e in opens)
    overdue = sum(e.amount - e.paid for e in opens if score_mod.overdue_days(e))
    return {
        "store": store.name, "area": store.area,
        "upi_sales_today": store.upi_sales_today + upi_today,
        "outstanding": outstanding, "overdue": overdue,
        # Money that should come in this week: everything already overdue plus what falls due in 7 days.
        "due_this_week": sum(e.amount - e.paid for e in opens if e.due_date <= week_end),
        "new_customers_won": len(won),
        "outstanding_text": inr(outstanding), "overdue_text": inr(overdue),
    }


def _stock(s: Session, store_id: str) -> dict:
    p = festive.for_store(s, store_id)
    bill, adv = s.get(Bill, "B1"), s.get(Advance, "A1")
    out = {"plan": p, "bill": None, "advance": None}
    if bill:
        z = advance.sizing(s, store_id, bill) if bill.status != "paid" else None
        out["bill"] = {"id": bill.id, "distributor": bill.distributor, "amount": bill.amount,
                       "due": bill.due_date.isoformat(), "status": bill.status,
                       "gap": z["gap"] if z else 0, "paid_by_lender": bill.paid_by_lender,
                       "paid_by_store": bill.paid_by_store}
    if adv:
        out["advance"] = {"id": adv.id, "state": adv.state, "lender": adv.lender, "amount": adv.amount, "fee": adv.fee,
                          "total_due": adv.total_due, "repaid": adv.repaid, "split_rate": adv.split_rate,
                          "backstop": adv.backstop_date.isoformat() if adv.backstop_date else
                          (today() + timedelta(days=advance.BACKSTOP_DAYS)).isoformat(),
                          "paid_to": bill.distributor if bill else None}
    return out


def _counter_feed(s: Session, store_id: str) -> list[dict]:
    feed = req.sb_get(s, store_id).get("feed", [])
    out = []
    for f in feed:
        item = dict(f)
        if f.get("entry_id"):
            e = s.get(Entry, f["entry_id"])
            item["state"] = e.state.replace("_", " ").title() if e else "—"
        out.append(item)
    return out


def _get_paid(s: Session, store_id: str) -> dict:
    sm = summary(s, store_id)
    opens = _open_here(s, store_id)
    return {"outstanding": sm["outstanding"], "overdue": sm["overdue"],
            "verified": sum(e.amount - e.paid for e in opens),
            "promises": len(s.exec(select(PromiseRow).where(PromiseRow.store_id == store_id)).all()),
            "replies": len(s.exec(select(Message).where(Message.store_id == store_id, Message.direction == "in")).all()),
            "autopay": sum(len(mandates.active(s, link.customer_id, store_id)) for link in
                           s.exec(select(StoreCustomer).where(StoreCustomer.store_id == store_id)).all())}


def home_view(s: Session, store_id: str) -> dict:
    req.expire_stale(s)
    plan = growth.view(s, store_id)
    return {"summary": summary(s, store_id),
            "growth_plan": {"summary": "Three things to do this week, in order of impact.", "actions": plan},
            "counter_feed": _counter_feed(s, store_id), "stock": _stock(s, store_id), "get_paid": _get_paid(s, store_id),
            "ai_enabled": sarvam.enabled()}


def udhaar_book(s: Session, store_id: str) -> list[dict]:
    rows = []
    for link in s.exec(select(StoreCustomer).where(StoreCustomer.store_id == store_id)).all():
        c = s.get(Customer, link.customer_id)
        opens = payments.open_entries(s, store_id, c.id)
        g = risk.evaluate(s, store_id, c.id, INDICATOR)
        sc = score_mod.for_customer(s, c.id)
        disputed = s.exec(select(Entry.id).where(Entry.store_id == store_id, Entry.customer_id == c.id,
                                                 Entry.state == "disputed")).first()
        rows.append({"id": c.id, "name": c.name, "outstanding": sum(e.amount - e.paid for e in opens),
                     "overdue_days": max((score_mod.overdue_days(e) for e in opens), default=0),
                     "band": g.band, "safe_limit": g.safe_limit, "score_band": sc.band,
                     "tags": _tags(s, store_id, c.id) + (["Disputed"] if disputed else [])})
    return sorted(rows, key=lambda r: (-r["overdue_days"], -r["outstanding"], r["name"]))


def customer_detail(s: Session, store_id: str, customer_id: str) -> dict:
    if s.get(StoreCustomer, (store_id, customer_id)) is None:
        raise EventError("Not a customer of this shop", 404)
    c = s.get(Customer, customer_id)
    g = risk.evaluate(s, store_id, customer_id, INDICATOR)
    sc = score_mod.for_customer(s, customer_id)
    entries = s.exec(select(Entry).where(Entry.store_id == store_id, Entry.customer_id == customer_id)
                     .order_by(Entry.created_at.desc())).all()
    msgs = s.exec(select(Message).where(Message.store_id == store_id, Message.customer_id == customer_id)
                  .order_by(Message.id)).all()
    return {"id": c.id, "name": c.name, "score_band": sc.band, "safe_limit": g.safe_limit, "band": g.band,
            "reasons": g.reasons, "tags": _tags(s, store_id, customer_id),
            "entries": [{"id": e.id, "amount": e.amount, "paid": e.paid, "state": e.state, "source": e.source,
                         "created_at": e.created_at.isoformat(), "due_date": e.due_date.isoformat(),
                         "overdue_days": score_mod.overdue_days(e), "dispute_reason": e.dispute_reason,
                         "items": e.items, "integrity_flag": e.integrity_flag} for e in entries],
            "messages": [{"direction": m.direction, "text": m.text, "ts": m.created_at.isoformat(), "source": m.source}
                         for m in msgs]}


def collect_view(s: Session, store_id: str) -> dict:
    threads: dict[str, dict] = {}
    for m in s.exec(select(Message).where(Message.store_id == store_id).order_by(Message.id)).all():
        th = threads.setdefault(m.customer_id, {"customer_id": m.customer_id,
                                                "customer": s.get(Customer, m.customer_id).name, "messages": []})
        th["messages"].append({"direction": m.direction, "text": m.text, "ts": m.created_at.isoformat(),
                               "source": m.source, "intent": (m.meta or {}).get("intent"),
                               "escalate": (m.meta or {}).get("escalate", False)})
    promises = [{"customer": s.get(Customer, p.customer_id).name, "amount": p.amount, "date": p.date.isoformat()}
                for p in s.exec(select(PromiseRow).where(PromiseRow.store_id == store_id)).all()]
    schedules = []
    for link in s.exec(select(StoreCustomer).where(StoreCustomer.store_id == store_id)).all():
        for m in mandates.active(s, link.customer_id, store_id):
            schedules.append({**mandates.schedule(s, m), "customer": s.get(Customer, link.customer_id).name})
    return {"threads": list(threads.values()), "promises": promises, "schedules": schedules}


def orders_view(s: Session, store_id: str) -> list[dict]:
    return [{"id": b.id, "customer": s.get(Customer, b.customer_id).name, "value": b.value, "items": b.items,
             "state": b.state} for b in s.exec(select(BasketOffer).where(BasketOffer.store_id == store_id)
                                                .order_by(BasketOffer.id.desc())).all()]


# ---------------------------------------------------------------- routes

@router.get("/home")
async def home(me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        return home_view(t.s, me.store_id)


@router.get("/udhaar-book")
async def get_book(me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        return udhaar_book(t.s, me.store_id)


@router.get("/customers/{customer_id}")
async def get_customer(customer_id: str, me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        return customer_detail(t.s, me.store_id, customer_id)


@router.get("/collect")
async def get_collect(me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        return collect_view(t.s, me.store_id)


@router.get("/orders")
async def get_orders(me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        return orders_view(t.s, me.store_id)


@router.post("/growth/{action_id}/approve")
async def approve(action_id: str, me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        a = await growth.approve(t.s, me.store_id, action_id)
        customers = [x["customer_id"] for x in a.facts.get("customers", [])] + \
            ([a.facts["customer_id"]] if a.facts.get("customer_id") else [])
        _scopes(t, me.store_id, *customers)
    return {"ok": True}


@router.post("/advance/{advance_id}/accept")
async def advance_accept(advance_id: str, me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        advance.accept(t.s, me.store_id, advance_id)
        _scopes(t, me.store_id)
    return {"ok": True}


@router.post("/advance/{advance_id}/decline")
async def advance_decline(advance_id: str, me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        advance.decline(t.s, me.store_id, advance_id)
        _scopes(t, me.store_id)
    return {"ok": True}


@router.post("/entries/{entry_id}/cancel")
async def cancel_entry(entry_id: int, me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        req.cancel_entry(t.s, me.store_id, entry_id)
        _scopes(t, me.store_id, t.s.get(Entry, entry_id).customer_id)
    return {"ok": True}


@router.post("/baskets/{basket_id}/delivered")
async def basket_delivered(basket_id: int, me: Me = Depends(auth.merchant)):
    async with bus.tx() as t:
        b = basket.delivered(t.s, me.store_id, basket_id)
        _scopes(t, me.store_id, b.customer_id)
    return {"ok": True}


@router.post("/ask")
async def ask(body: AskIn, me: Me = Depends(auth.merchant)):
    if not sarvam.enabled():
        return {"answer": "Ask Munim is available when AI is enabled.", "steps": [], "source": "template",
                "enabled": False}
    # Read-only tools on their own session: the AI loop can take several seconds, and holding the
    # write lock (bus.tx) that long would freeze the Soundbox and every other write meanwhile.
    with db.session() as s:
        tools = {
            "get_summary": lambda: summary(s, me.store_id),
            "get_growth_plan": lambda: [{k: a[k] for k in ("title", "impact", "state", "outcome")}
                                        for a in growth.view(s, me.store_id)],
            "get_stock": lambda: _stock(s, me.store_id),
            "list_overdue": lambda: [r for r in udhaar_book(s, me.store_id) if r["overdue_days"]],
            "list_customers": lambda: [{k: r[k] for k in ("name", "outstanding", "overdue_days", "safe_limit", "score_band")}
                                       for r in udhaar_book(s, me.store_id)],
        }
        out = await growth_agent.ask(body.question, tools)
    async with bus.tx() as t:
        activity.log(t.s, me.store_id, "ai", f"Munim answered: {body.question[:60]}", out["source"])
        t.touch(f"merchant:{me.store_id}")
    return {**out, "enabled": True}
