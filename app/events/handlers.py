"""One handler per event type. Handlers mutate state through core services and return Effects.

Handlers for later milestones are registered as they are built; until then the router
answers 501 for those event types.
"""
from sqlmodel import Session, select

from app import clock, state
from app.adapters import soundbox, upi
from app.core import ledger, messages, risk, score
from app.core.money import inr
from app.events import schemas as sc
from app.events.effects import notify
from app.events.router import EventError, UnitOfWork, before_each, handles
from app.models import Consent, Customer, Entry, Sale, Store, StoreCustomer
from app.realtime.trace import trace


# ---------------------------------------------------------------- helpers

def _store(s: Session, store_id: str) -> Store:
    st = s.get(Store, store_id)
    if st is None:
        raise EventError(f"unknown store {store_id}", 404)
    return st


def _store_customer(s: Session, store_id: str, customer_id: str) -> Customer:
    c = s.get(Customer, customer_id)
    if c is None or s.get(StoreCustomer, (store_id, customer_id)) is None:
        raise EventError(f"{customer_id} is not a customer of {store_id}", 404)
    return c


def _entry(s: Session, entry_id: int) -> Entry:
    e = s.get(Entry, entry_id)
    if e is None:
        raise EventError(f"unknown entry {entry_id}", 404)
    return e


def _lang(s: Session, explicit: str | None = None) -> str:
    return explicit or state.get(s, "lang")


def _confirm_front(store: Store, e: Entry, collect_now: int = 0, sale_ref: str | None = None) -> dict:
    return {
        "mode": "confirm_qr",
        "entry_id": e.id,
        "customer_id": e.customer_id,
        "amount": e.amount,
        "qr_payload": upi.confirm_payload(e.confirm_token),
        "token": e.confirm_token,
        "expires_at": clock.iso(e.token_expires_at),
        "pay_amount": collect_now or None,
        "pay_qr": upi.collect_qr(store, collect_now, sale_ref) if collect_now else None,
        "sale_ref": sale_ref if collect_now else None,
    }


def _confirm_notify(store: Store, e: Entry):
    return notify(f"customer:{e.customer_id}", store.name, f"{inr(e.amount)} on credit · Confirm",
                  {"label": "Confirm", "token": e.confirm_token})


@before_each
def _expire_confirmations(uow: UnitOfWork) -> None:
    for e in ledger.expire_stale(uow.s):
        soundbox.clear_front_if_showing(uow.s, e.id)


# ---------------------------------------------------------------- UI state

@handles("set_language")
def on_set_language(uow: UnitOfWork, p: sc.SetLanguage):
    state.put(uow.s, "lang", p.lang)
    trace("router", f"Language → {p.lang}")


@handles("set_focus_customer")
def on_set_focus_customer(uow: UnitOfWork, p: sc.SetFocusCustomer):
    if uow.s.get(Customer, p.customer_id) is None:
        raise EventError(f"unknown customer {p.customer_id}", 404)
    state.put(uow.s, "focus_customer", p.customer_id)


# ---------------------------------------------------------------- credit sale (flow A)

@handles("udhaar_spoken")
def on_udhaar_spoken(uow: UnitOfWork, p: sc.UdhaarSpoken):
    s = uow.s
    store = _store(s, p.store_id)
    if p.customer_id is None or p.amount is None:
        raise EventError("free-text sentences need the Counter Agent (not built yet); "
                         "send customer_id and amount", 501)
    c = _store_customer(s, store.id, p.customer_id)
    lang = _lang(s, p.lang)
    trace("soundbox", f"Heard: {messages.first_name(c.name)} {p.amount} udhaar", {"text": p.text})

    r = risk.evaluate(s, store.id, c.id, p.amount)
    trace("risk", f"Safe limit {inr(r.safe_limit)} ({r.band})",
          {"customer_id": c.id, "amount": p.amount, "reasons": r.reasons}, ms=r.ms)
    msg = messages.guardrail(r, c.name, lang)

    entry = ledger.propose(s, store, c.id, r.credit_now, p.amount, source_text=p.text) if r.credit_now else None
    sale_ref = f"SALE-{entry.id}" if entry else f"SALE-E{uow.event_id}"
    top = {
        "band": r.band, "text": msg["display"], "ms": r.ms, "reasons": r.reasons,
        "customer_id": c.id, "customer": c.name, "requested": p.amount, "safe_limit": r.safe_limit,
        "credit_now": r.credit_now, "collect_now": r.collect_now,
        "entry_id": entry.id if entry else None, "override": False,
    }
    if entry:
        front = _confirm_front(store, entry, r.collect_now, sale_ref)
    else:
        front = {"mode": "pay_qr", "entry_id": None, "customer_id": c.id, "amount": 0,
                 "pay_amount": r.collect_now, "pay_qr": upi.collect_qr(store, r.collect_now, sale_ref),
                 "sale_ref": sale_ref}
    soundbox.display(s, store.id, top=top, front=front)

    effects = [soundbox.play(store.id, msg["spoken"], lang)]
    if entry:
        effects.append(_confirm_notify(store, entry))
    return effects


@handles("guardrail_override")
def on_guardrail_override(uow: UnitOfWork, p: sc.GuardrailOverride):
    s = uow.s
    if p.entry_id is not None:
        e = _entry(s, p.entry_id)
        if s.exec(select(Sale.id).where(Sale.ref == f"SALE-{e.id}")).first():
            raise EventError("the split amount was already collected; record a new udhaar instead", 409)
        ledger.override_amount(s, e)
        store = s.get(Store, e.store_id)
    else:
        store = _store(s, p.store_id)
        _store_customer(s, store.id, p.customer_id)
        e = ledger.propose(s, store, p.customer_id, p.amount, p.amount, override=True)

    c = s.get(Customer, e.customer_id)
    trace("risk", f"Guardrail overridden by shopkeeper: {inr(e.amount)}", {"entry_id": e.id})
    top = dict(soundbox.current(s).get("top") or {})
    top.update({"entry_id": e.id, "credit_now": e.amount, "collect_now": 0, "override": True,
                "text": f"Override: giving {messages.first_name(c.name)} {inr(e.amount)} on credit."})
    soundbox.display(s, store.id, top=top, front=_confirm_front(store, e))
    return [_confirm_notify(store, e)]


@handles("customer_confirm")
def on_customer_confirm(uow: UnitOfWork, p: sc.CustomerConfirm):
    s = uow.s
    e = ledger.by_token(s, p.token)
    c = s.get(Customer, e.customer_id)
    store = s.get(Store, e.store_id)
    trace("customer_app", f"{messages.first_name(c.name)} tapped Confirm", {"entry_id": e.id})
    ledger.confirm(s, e, p.device_id)

    has_consent = s.exec(select(Consent.id).where(
        Consent.customer_id == c.id, Consent.type == "data_share", Consent.revoked_at == None)).first()  # noqa: E711
    if not has_consent and (p.consents or {}).get("data_share"):
        s.add(Consent(customer_id=c.id, type="data_share", granted_at=clock.now()))
        trace("ledger", "Data-share consent recorded", {"customer_id": c.id})

    # The customer disputed, the shop stood by its amount, and the customer then confirmed it.
    if e.disputed_from_amount is not None and e.amount >= e.disputed_from_amount:
        score.apply_delta(s, c.id, -15, "dispute resolved against customer", ref=f"entry:{e.id}", store_id=store.id)

    front = soundbox.current(s).get("front") or {}
    if front.get("entry_id") == e.id:
        sale_paid = front.get("sale_ref") and s.exec(select(Sale.id).where(Sale.ref == front["sale_ref"])).first()
        if front.get("pay_qr") and not sale_paid:
            front = {**front, "mode": "pay_qr", "qr_payload": None, "token": None}
        else:
            front = soundbox.IDLE_FRONT
    else:
        front = None
    alert = messages.confirmed(c.name, e.amount)
    soundbox.display(s, store.id, front=front, last_alert=alert)
    return [notify(f"merchant:{store.id}", "Udhaar confirmed", alert)]


@handles("customer_dispute")
def on_customer_dispute(uow: UnitOfWork, p: sc.CustomerDispute):
    s = uow.s
    e = ledger.by_token(s, p.token)
    c = s.get(Customer, e.customer_id)
    ledger.dispute(s, e, p.reason, p.claimed_amount)
    soundbox.clear_front_if_showing(s, e.id)
    says = f": says {inr(p.claimed_amount)}" if p.claimed_amount is not None else ""
    text = f"{messages.first_name(c.name)} disputes{says}"
    soundbox.display(s, e.store_id, last_alert=text)
    return [notify(f"merchant:{e.store_id}", text, p.reason, {"label": "Correct", "entry_id": e.id})]


@handles("entry_corrected")
def on_entry_corrected(uow: UnitOfWork, p: sc.EntryCorrected):
    s = uow.s
    e = _entry(s, p.entry_id)
    ledger.correct(s, e, p.amount)
    store = s.get(Store, e.store_id)
    soundbox.display(s, store.id, front=_confirm_front(store, e))
    return [_confirm_notify(store, e)]


@handles("new_customer")
async def on_new_customer(uow: UnitOfWork, p: sc.NewCustomer):
    """First-ever credit: the front screen collects a mobile number. A mobile already known on
    the network links the existing identity (and score) to this store instead of duplicating it."""
    s = uow.s
    store = _store(s, p.store_id)
    c = s.exec(select(Customer).where(Customer.mobile == p.mobile)).first()
    if c is None:
        n = len(s.exec(select(Customer.id).where(Customer.id.like("C_N%"))).all()) + 1
        c = Customer(id=f"C_N{n:03d}", name=p.name.strip(), aliases=[p.name.split()[0]], mobile=p.mobile,
                     vpa=f"{p.mobile}@ptyes", device_id=None, persona=None, score=score.START_SCORE,
                     is_new=True, lang=store.lang, created_at=clock.now())
        s.add(c)
        s.flush()
        trace("ledger", f"New customer {c.name} ({c.id})", {"customer_id": c.id})
    if s.get(StoreCustomer, (store.id, c.id)) is None:
        s.add(StoreCustomer(store_id=store.id, customer_id=c.id))
        s.flush()
    if p.amount:
        await uow.emit("udhaar_spoken", sc.UdhaarSpoken(store_id=store.id, customer_id=c.id, amount=p.amount))
