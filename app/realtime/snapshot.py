"""Snapshot builder (spec 10.2). The UI renders only from this; it never computes balances.

Fields may be added but the spec's names must not be renamed. Privacy (spec 6.2.7):
`merchant.*` only ever reads the merchant's own store; `customer.*` is the focus
customer's own data across stores.
"""
from datetime import date, timedelta

from sqlmodel import Session, select

from app import clock, state
from app.core import ledger, score as sc
from app.models import (
    Advance, Bill, Customer, Entry, Mandate, Message, PendingMatch, Repayment, RiskAlert, Sale, ScoreEvent, Store,
)
from app.realtime import trace as tr

MERCHANT_STORE = "S1"
DEMO_TOTAL_BEATS = 7


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def window_label(start: int, end: int) -> str:
    return f"{_ordinal(start)}–{_ordinal(end)}"


def build_snapshot(s: Session) -> dict:
    stores = {st.id: st for st in s.exec(select(Store)).all()}
    if not stores:
        return {"now": clock.iso(clock.now()), "seeded": False}
    return {
        "now": clock.iso(clock.now()),
        "lang": state.get(s, "lang"),
        "demo": {
            "beat": state.get(s, "demo_beat"),
            "total": DEMO_TOTAL_BEATS,
            "caption": state.get(s, "demo_caption"),
        },
        "soundbox": state.get(s, "soundbox"),
        "merchant": _merchant(s, stores[MERCHANT_STORE]),
        "customer": _customer(s, stores, state.get(s, "focus_customer")),
        "risk_console": _risk_console(s, stores),
        "trace_tail": tr.recent(s, 8),
    }


# ---------------------------------------------------------------- merchant

def _collections_by_day(s: Session, store_id: str, start: date, end: date) -> dict[date, int]:
    """UPI money received (sales + UPI/mandate repayments). Cash is not 'collection via UPI'."""
    lo = clock.datetime_floor(start)
    hi = clock.datetime_floor(end + timedelta(days=1))
    out = {start + timedelta(days=i): 0 for i in range((end - start).days + 1)}
    for amt, at in s.exec(select(Sale.amount, Sale.created_at).where(
            Sale.store_id == store_id, Sale.source == "upi", Sale.created_at >= lo, Sale.created_at < hi)).all():
        out[at.date()] += amt
    for amt, at in s.exec(select(Repayment.amount, Repayment.created_at).where(
            Repayment.store_id == store_id, Repayment.source != "cash",
            Repayment.created_at >= lo, Repayment.created_at < hi)).all():
        out[at.date()] += amt
    return out


def _merchant(s: Session, store: Store) -> dict:
    today = clock.today()
    entries = ledger.open_entries(s, store.id)
    tot = ledger.totals(entries, today)
    per_cust = ledger.totals_by_customer(entries, today)
    customers = {c.id: c for c in s.exec(select(Customer).where(Customer.id.in_(list(per_cust) or [""]))).all()}

    week = _collections_by_day(s, store.id, today - timedelta(days=6), today)

    top = sorted(per_cust.items(), key=lambda kv: (-kv[1].outstanding, -kv[1].oldest_overdue_days))[:8]
    customers_top = [
        {
            "id": cid, "name": customers[cid].name, "outstanding": t.outstanding, "verified": t.verified,
            "band": None,  # guardrail band for a ₹340 sale; filled once the risk engine lands
            "score": customers[cid].score, "score_band": sc.band(customers[cid].score),
            "overdue_days": t.oldest_overdue_days,
        }
        for cid, t in top
    ]

    proposed = s.exec(select(Entry).where(Entry.store_id == store.id, Entry.state == "proposed")
                      .order_by(Entry.created_at)).all()
    disputed = s.exec(select(Entry).where(Entry.store_id == store.id, Entry.state == "disputed")).all()
    names = _names(s, {e.customer_id for e in [*proposed, *disputed]})

    bills = s.exec(select(Bill).where(Bill.store_id == store.id, Bill.status == "due",
                                      Bill.due_date <= today + timedelta(days=7)).order_by(Bill.due_date)).all()
    advance = s.exec(select(Advance).where(Advance.store_id == store.id, Advance.state != "declined")
                     .order_by(Advance.created_at.desc())).first()
    pms = s.exec(select(PendingMatch).where(PendingMatch.store_id == store.id, PendingMatch.resolved == False)  # noqa: E712
                 .order_by(PendingMatch.created_at)).all()
    drafts = s.exec(select(Message).where(Message.store_id == store.id, Message.status == "draft")
                    .order_by(Message.created_at)).all()
    draft_names = _names(s, {m.customer_id for m in drafts})

    return {
        "store": {"id": store.id, "name": store.name, "area": store.area, "vpa": store.vpa,
                  "advance_blocked": store.advance_blocked},
        "today_collection": week[today],
        "collection_7d": [{"date": d.isoformat(), "amount": v} for d, v in week.items()],
        "udhaar": {
            "outstanding": tot.outstanding, "verified": tot.verified, "unverified": tot.unverified,
            "overdue": tot.overdue, "pending_confirm": len(proposed), "customers_owing": len(per_cust),
        },
        "briefing": state.get(s, "briefing"),
        "due_soon": [
            {"bill_id": b.id, "distributor": b.distributor, "amount": b.amount, "due": b.due_date.isoformat(),
             "gap": None}  # filled by the forecaster milestone
            for b in bills
        ],
        "advance": _advance(advance),
        "pending_entries": [
            {"entry_id": e.id, "customer_id": e.customer_id, "customer": names.get(e.customer_id), "amount": e.amount,
             "requested_amount": e.requested_amount, "token": e.confirm_token,
             "expires_at": clock.iso(e.token_expires_at)}
            for e in proposed
        ],
        "pending_matches": [
            {"pending_id": pm.id, "amount": pm.payment.get("amount"), "payer_name": pm.payment.get("payer_name"),
             "payer_vpa": pm.payment.get("payer_vpa"), "remark": pm.payment.get("remark"),
             "candidates": pm.candidates, "agent": pm.agent_output}
            for pm in pms
        ],
        "disputes": [
            {"entry_id": e.id, "customer_id": e.customer_id, "customer": names.get(e.customer_id),
             "amount": e.amount, "claimed_amount": e.dispute_amount, "reason": e.dispute_reason}
            for e in disputed
        ],
        "drafts": [
            {"message_id": m.id, "customer_id": m.customer_id, "customer": draft_names.get(m.customer_id),
             "text": m.text, "lang": m.lang}
            for m in drafts
        ],
        "customers_top": customers_top,
    }


def _advance(a: Advance | None) -> dict | None:
    if a is None:
        return None
    return {
        "id": a.id, "state": a.state, "bill_id": a.bill_id, "amount": a.amount, "fee": a.fee,
        "total_due": a.total_due, "repaid": a.repaid, "split_rate": a.split_rate, "lender": a.lender,
        "backstop": a.backstop_date.isoformat() if a.backstop_date else None,
    }


def _names(s: Session, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    return {c.id: c.name for c in s.exec(select(Customer).where(Customer.id.in_(list(ids)))).all()}


# ---------------------------------------------------------------- customer

def _customer(s: Session, stores: dict[str, Store], customer_id: str | None) -> dict | None:
    c = s.get(Customer, customer_id) if customer_id else None
    if c is None:
        return None
    today = clock.today()
    now = clock.now()

    entries = ledger.open_entries(s, customer_id=c.id)
    by_store: dict[str, list[Entry]] = {}
    for e in entries:
        by_store.setdefault(e.store_id, []).append(e)
    dues = []
    for sid, es in sorted(by_store.items()):
        t = ledger.totals(es, today)
        dues.append({"store": stores[sid].name, "store_id": sid, "amount": t.outstanding, "verified": t.verified,
                     "oldest_overdue_days": t.oldest_overdue_days})

    proposed = s.exec(select(Entry).where(Entry.customer_id == c.id, Entry.state == "proposed")
                      .order_by(Entry.created_at)).all()
    mandates = s.exec(select(Mandate).where(Mandate.customer_id == c.id).order_by(Mandate.created_at)).all()
    msgs = s.exec(select(Message).where(Message.customer_id == c.id, Message.status.in_(("sent", "received")))
                  .order_by(Message.created_at.desc(), Message.id.desc()).limit(30)).all()

    delta_7d = sum(s.exec(select(ScoreEvent.delta).where(
        ScoreEvent.customer_id == c.id, ScoreEvent.created_at >= now - timedelta(days=7))).all())

    return {
        "id": c.id, "name": c.name, "mobile": c.mobile, "vpa": c.vpa, "lang": c.lang,
        "score": c.score, "score_band": sc.band(c.score), "score_delta_7d": delta_7d,
        "dues": dues,
        "pending_confirms": [
            {"token": e.confirm_token, "entry_id": e.id, "store": stores[e.store_id].name, "store_id": e.store_id,
             "amount": e.amount, "date": clock.iso(e.created_at), "expires_at": clock.iso(e.token_expires_at)}
            for e in proposed
        ],
        "mandates": [
            {"id": m.id, "store": stores[m.store_id].name, "store_id": m.store_id, "cap": m.cap,
             "window": window_label(m.window_start_day, m.window_end_day), "status": m.status}
            for m in mandates
        ],
        "messages": [
            {"id": m.id, "store": stores[m.store_id].name, "store_id": m.store_id, "direction": m.direction,
             "text": m.text, "ts": clock.iso(m.created_at),
             "actions": (m.agent_output or {}).get("ui_actions", [])}
            for m in reversed(msgs)
        ],
        "history": _history(s, stores, c.id),
        "rewards": sc.rewards(c.score),
    }


def _history(s: Session, stores: dict[str, Store], customer_id: str, limit: int = 25) -> list[dict]:
    es = s.exec(select(Entry).where(Entry.customer_id == customer_id, Entry.state != "proposed")
                .order_by(Entry.created_at.desc()).limit(limit)).all()
    rs = s.exec(select(Repayment).where(Repayment.customer_id == customer_id)
                .order_by(Repayment.created_at.desc()).limit(limit)).all()
    items = [
        {"type": "entry", "id": e.id, "store": stores[e.store_id].name, "amount": e.amount,
         "paid": e.paid_amount, "state": e.state, "verified": e.verified_at is not None,
         "ts": clock.iso(e.created_at), "due": e.due_date.isoformat()}
        for e in es
    ] + [
        {"type": "repayment", "id": r.id, "store": stores[r.store_id].name, "amount": r.amount,
         "source": r.source, "state": "auto_paid" if r.source == "mandate" else "paid", "ts": clock.iso(r.created_at)}
        for r in rs
    ]
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:limit]


# ---------------------------------------------------------------- risk console

def _risk_console(s: Session, stores: dict[str, Store]) -> dict:
    alerts = s.exec(select(RiskAlert).order_by(RiskAlert.created_at.desc())).all()
    return {"alerts": [
        {"id": a.id, "store": stores[a.store_id].name, "store_id": a.store_id, "risk": a.risk, "rules": a.rules,
         "entry_count": len(a.entry_ids or []), "ts": clock.iso(a.created_at)}
        for a in alerts
    ]}
