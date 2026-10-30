"""The counter and the bridge to the customer's phone (v2 spec §4.3–4.4, §4.10, §5.1–5.2).

Counter: udhaar(text or preset) → guardrail on the top display → the operator accepts the
suggestion (or overrides) → a `proposed` entry and a confirm request → QR on the front screen.
A customer new to this shop but known to the network first gets a share request instead; if
they share (or decline), the confirm request is created straight away so their phone moves on
to the Confirm sheet without a second scan.

Soundbox state (one JSON row per store):
    top:     {band, text, reasons, customer, amount, kind} | None
    front:   {mode: idle|confirm_qr|share_qr|pay_full|done, token, credit_now, collect_now, message}
    pending: {customer_id, amount, guardrail} — the decision waiting for Use suggestion / Override
    feed:    last counter decisions for the merchant app
"""
import secrets
from datetime import timedelta

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.config import get_settings, now
from app.core import activity, payments, risk
from app.core.money import inr
from app.errors import EventError
from app.models import Customer, Entry, PendingRequest, ScoreShare, SoundboxState, Store, StoreCustomer

EXPIRY = timedelta(minutes=15)
IDLE = {"mode": "idle"}
FEED_LEN = 5


# ---------------------------------------------------------------- soundbox state

def sb_get(s: Session, store_id: str) -> dict:
    row = s.get(SoundboxState, store_id)
    return dict(row.state or {}) if row else {}


def sb_put(s: Session, store_id: str, state: dict) -> None:
    row = s.get(SoundboxState, store_id) or SoundboxState(store_id=store_id)
    row.state = state
    flag_modified(row, "state")
    s.add(row)


def request_url(token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/c/r/{token}"


def _top(g: risk.Guardrail, c: Customer, store: Store) -> dict:
    return {"band": "waiting" if g.needs_share else g.band, "text": risk.verdict(g, c.name, store.starter_limit),
            "reasons": g.reasons, "customer": c.name, "customer_id": c.id, "amount": g.amount,
            "credit_now": g.credit_now, "collect_now": g.collect_now, "kind": g.kind, "ms": g.ms}


def _feed_push(state: dict, item: dict) -> None:
    feed = [f for f in state.get("feed", []) if f.get("entry_id") is None or f["entry_id"] != item.get("entry_id")]
    state["feed"] = ([item] + feed)[:FEED_LEN]


# ---------------------------------------------------------------- requests

def _token() -> str:
    return secrets.token_urlsafe(16)  # 22 URL-safe characters


def _new_request(s: Session, kind: str, store_id: str, customer_id: str, amount: int, credit: int = 0,
                 collect: int = 0, entry_id: int | None = None) -> PendingRequest:
    t = now()
    r = PendingRequest(token=_token(), kind=kind, store_id=store_id, customer_id=customer_id,
                       amount_requested=amount, credit_now=credit, collect_now=collect, entry_id=entry_id,
                       created_at=t, expires_at=t + EXPIRY)
    s.add(r)
    s.flush()
    return r


def expire_stale(s: Session) -> list[str]:
    """Lazily expire requests older than 15 minutes (no background clock). Returns affected stores."""
    stores = []
    for r in s.exec(select(PendingRequest).where(PendingRequest.status == "open",
                                                 PendingRequest.expires_at < now())).all():
        r.status = "expired"
        s.add(r)
        if r.entry_id:
            e = s.get(Entry, r.entry_id)
            if e and e.state == "proposed":
                e.state = "expired"
                s.add(e)
        state = sb_get(s, r.store_id)
        if (state.get("front") or {}).get("token") == r.token:
            state["front"] = dict(IDLE)
            sb_put(s, r.store_id, state)
        stores.append(r.store_id)
    return stores


def get_for_customer(s: Session, token: str, customer_id: str) -> PendingRequest:
    expire_stale(s)
    r = s.get(PendingRequest, token)
    if r is None:
        raise EventError("This request was not found.", 404)
    if r.customer_id != customer_id:
        raise EventError("This request is for another customer.", 403)
    return r


def describe(s: Session, r: PendingRequest) -> dict:
    store = s.get(Store, r.store_id)
    e = s.get(Entry, r.entry_id) if r.entry_id else None
    out = {"token": r.token, "kind": r.kind, "status": r.status, "store": store.name, "store_id": store.id,
           "amount_requested": r.amount_requested, "credit_now": r.credit_now, "collect_now": r.collect_now,
           "due_date": e.due_date.isoformat() if e else None, "expires_at": r.expires_at.isoformat(),
           "next_token": r.next_token}
    if r.status == "expired":
        out["message"] = "This request has expired. Ask the shop to try again."
    return out


# ---------------------------------------------------------------- counter flow

def udhaar(s: Session, store_id: str, customer_id: str, amount: int) -> dict:
    if not (1 <= amount <= 50_000):
        raise EventError("Amount must be between ₹1 and ₹50,000", 422)
    store, c = s.get(Store, store_id), s.get(Customer, customer_id)
    if c is None:
        raise EventError("Unknown customer", 404)
    expire_stale(s)
    g = risk.evaluate(s, store_id, customer_id, amount)
    state = sb_get(s, store_id)
    state["top"] = _top(g, c, store)
    state["pending"] = {"customer_id": c.id, "amount": amount}
    state["front"] = dict(IDLE)
    if g.needs_share:
        r = _new_request(s, "share", store_id, c.id, amount)
        state["front"] = {"mode": "share_qr", "token": r.token, "message": "New here? Scan to share your Bharosa Score"}
        state["pending"]["share_token"] = r.token
    sb_put(s, store_id, state)
    activity.log(s, store_id, "guardrail", f"{c.name} asks {inr(amount)}: {state['top']['text']}")
    return state["top"]


def accept(s: Session, store_id: str, override: bool) -> dict:
    """The operator taps Use suggestion (or Override). Creates the proposed entry and confirm request."""
    expire_stale(s)
    state = sb_get(s, store_id)
    pend = state.get("pending")
    if not pend:
        raise EventError("Nothing to accept: ask for an amount first", 409)
    if pend.get("share_token"):  # waiting for a share: go ahead on the starter limit instead
        r = s.get(PendingRequest, pend["share_token"])
        if r and r.status == "open":
            r.status = "declined"
            s.add(r)
    return _start_confirm(s, store_id, pend["customer_id"], pend["amount"], override)


def _start_confirm(s: Session, store_id: str, customer_id: str, amount: int, override: bool = False) -> dict:
    store, c = s.get(Store, store_id), s.get(Customer, customer_id)
    g = risk.evaluate(s, store_id, customer_id, amount)
    credit = amount if override else g.credit_now
    collect = amount - credit
    state = sb_get(s, store_id)
    state["top"] = _top(g, c, store)
    state.pop("pending", None)
    if credit == 0:
        state["front"] = {"mode": "pay_full", "amount": amount, "message": f"Please pay {inr(amount)}"}
        _feed_push(state, {"entry_id": None, "customer": c.name, "band": g.band, "credit": 0, "collect": amount,
                           "tags": [], "state": "Paid in full"})
        sb_put(s, store_id, state)
        activity.log(s, store_id, "guardrail", f"{c.name}: no credit, collect full {inr(amount)}")
        return {"mode": "pay_full", "customer_id": c.id}
    t = now()
    e = Entry(store_id=store_id, customer_id=c.id, amount=credit, state="proposed", source="counter", created_at=t,
              due_date=t.date() + timedelta(days=store.due_days), override=override, band=g.band, tags=g.tags)
    s.add(e)
    s.flush()
    r = _new_request(s, "confirm", store_id, c.id, amount, credit, collect, e.id)
    state["front"] = {"mode": "confirm_qr", "token": r.token, "credit_now": credit, "collect_now": collect,
                      "customer": c.name, "message": f"Scan to confirm {inr(credit)} udhaar · {store.name}"}
    _feed_push(state, {"entry_id": e.id, "customer": c.name, "band": g.band, "credit": credit, "collect": collect,
                       "tags": g.tags + (["Override"] if override else [])})
    sb_put(s, store_id, state)
    activity.log(s, store_id, "guardrail", f"{c.name}: {inr(credit)} on credit" +
                 (f", {inr(collect)} now" if collect else "") + (" (override)" if override else ""))
    return {"mode": "confirm_qr", "token": r.token, "customer_id": c.id}


def clear(s: Session, store_id: str) -> str | None:
    """Reset the counter. A request still on the front screen is withdrawn (its proposed entry
    expires), so the customer cannot confirm something the shop cancelled. Returns that customer."""
    state = sb_get(s, store_id)
    front = state.get("front") or {}
    customer_id = None
    if front.get("token"):
        r = s.get(PendingRequest, front["token"])
        if r and r.status == "open":
            r.status, customer_id = "declined", r.customer_id
            s.add(r)
            e = s.get(Entry, r.entry_id) if r.entry_id else None
            if e and e.state == "proposed":
                e.state = "expired"
                s.add(e)
    state.update(top=None, front=dict(IDLE))
    state.pop("pending", None)
    sb_put(s, store_id, state)
    return customer_id


# ---------------------------------------------------------------- customer actions

def share(s: Session, token: str, customer_id: str, decision: str) -> dict:
    r = get_for_customer(s, token, customer_id)
    if r.kind != "share" or r.status != "open":
        raise EventError("This request is no longer open.", 409)
    c = s.get(Customer, customer_id)
    if decision == "share":
        s.add(ScoreShare(customer_id=customer_id, store_id=r.store_id, granted_at=now()))
        s.flush()
        activity.log(s, r.store_id, "confirm", f"{c.name} shared their Bharosa Score")
    else:
        activity.log(s, r.store_id, "confirm", f"{c.name} chose not to share: starter limit applies")
    r.status = "completed" if decision == "share" else "declined"
    out = _start_confirm(s, r.store_id, customer_id, r.amount_requested)
    r.next_token = out.get("token")
    s.add(r)
    return {"next_token": r.next_token, "mode": out["mode"]}


def confirm(s: Session, token: str, customer_id: str, pay_method: str | None, device_id: str | None) -> dict:
    r = get_for_customer(s, token, customer_id)
    if r.kind != "confirm":
        raise EventError("This is not a confirmation request.", 409)
    if r.status == "expired":
        raise EventError("This request has expired. Ask the shop to try again.", 410)
    if r.status != "open":
        raise EventError("This request was already answered.", 409)
    if r.collect_now and pay_method not in ("upi", "credit_line"):
        raise EventError("Choose how to pay the amount due now.", 422)
    e = s.get(Entry, r.entry_id)
    c = s.get(Customer, customer_id)
    if r.collect_now:
        payments.record_sale(s, r.store_id, customer_id, r.collect_now, pay_method)
    e.state, e.device_id = "verified", device_id
    if s.get(StoreCustomer, (r.store_id, customer_id)) is None:
        s.add(StoreCustomer(store_id=r.store_id, customer_id=customer_id))
    r.status = "completed"
    s.add_all([e, r])
    s.flush()
    _integrity_check(s, e)
    state = sb_get(s, r.store_id)
    state.update(top=None, front={"mode": "done", "message": f"✓ Confirmed by {c.name.split()[0]}"})
    sb_put(s, r.store_id, state)
    paid = f" + {inr(r.collect_now)} paid by {'credit line' if pay_method == 'credit_line' else 'UPI'}" if r.collect_now else ""
    activity.log(s, r.store_id, "confirm", f"{c.name} confirmed {inr(e.amount)} udhaar{paid}")
    return {"entry_id": e.id, "amount": e.amount, "spoken": f"{c.name.split()[0]} confirmed {inr(e.amount)} udhaar."}


def dispute(s: Session, token: str, customer_id: str, reason: str) -> None:
    r = get_for_customer(s, token, customer_id)
    if r.kind != "confirm" or r.status != "open":
        raise EventError("This request is no longer open.", 409)
    e = s.get(Entry, r.entry_id)
    e.state, e.dispute_reason = "disputed", reason[:120]
    r.status = "declined"
    s.add_all([e, r])
    c = s.get(Customer, customer_id)
    state = sb_get(s, r.store_id)
    state.update(top=None, front={"mode": "idle", "message": f"Disputed by {c.name.split()[0]}"})
    sb_put(s, r.store_id, state)
    activity.log(s, r.store_id, "confirm", f"{c.name} disputed {inr(e.amount)}: {e.dispute_reason}")


def cancel_entry(s: Session, store_id: str, entry_id: int) -> None:
    e = s.get(Entry, entry_id)
    if e is None or e.store_id != store_id:
        raise EventError("entry not found", 404)
    if e.state != "disputed":
        raise EventError("Only disputed entries can be cancelled", 409)
    e.state = "cancelled"
    s.add(e)
    activity.log(s, store_id, "confirm", f"Disputed entry of {inr(e.amount)} cancelled")


def _integrity_check(s: Session, e: Entry) -> None:
    """Same phone confirming for a different customer at this shop within 24 h → keep the entry out
    of advance eligibility (spec §4.10)."""
    if not e.device_id:
        return
    since = now() - timedelta(hours=24)
    other = s.exec(select(Entry.id).where(Entry.store_id == e.store_id, Entry.device_id == e.device_id,
                                          Entry.customer_id != e.customer_id, Entry.id != e.id,
                                          Entry.created_at >= since)).first()
    if other:
        e.integrity_flag = True
        s.add(e)
        activity.log(s, e.store_id, "integrity", "Possible shared device: entry excluded from advance eligibility")
