"""One handler per event type. Handlers mutate state through core services and return Effects.

Handlers for later milestones are registered as they are built; until then the router
answers 501 for those event types.
"""
from sqlmodel import Session, select

from app import clock, state
from app.adapters import soundbox, upi
from app.core import (
    advance, collector, forecast, integrity, ledger, mandates, messages, reconcile, risk, score,
)
from app.core.money import inr
from app.events import schemas as sc
from app.agents import counter, recon_agent, recovery
from app.events.effects import notify, toast
from app.events.router import EventError, UnitOfWork, before_each, handles
from app.models import (
    Bill, Consent, Customer, Entry, Message, PendingMatch, Promise, Sale, Store, StoreCustomer,
)
from app.realtime.snapshot import window_label
from app.sim import daily, fraud
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

async def _spoken_text(uow: UnitOfWork, store: Store, text: str, lang: str):
    """Free text from the Soundbox: the Counter Agent proposes, each valid action becomes its own event."""
    s = uow.s
    res = await counter.parse(s, store.id, text, lang)
    effects = []
    for a in res.data.actions:
        if a.type == "udhaar" and a.customer_id:
            await uow.emit("udhaar_spoken", {"store_id": store.id, "customer_id": a.customer_id, "amount": a.amount,
                                             "text": text, "lang": lang})
        elif a.type == "cash_repayment" and a.customer_id:
            await uow.emit("cash_reported", {"store_id": store.id, "customer_id": a.customer_id, "amount": a.amount,
                                             "text": text})
        elif len(a.candidate_ids) > 1:
            names = _names_for(s, a.candidate_ids)
            soundbox.display(s, store.id, top={
                "band": "clarify", "text": res.data.clarify_question or f"Which {a.name_heard}?",
                "intent": a.type, "amount": a.amount,
                "candidates": [{"id": cid, "name": names[cid]} for cid in a.candidate_ids]})
        elif a.type == "udhaar" and a.name_heard and a.amount:
            # Nobody by that name here: first-ever credit, ask the customer for a mobile number.
            soundbox.display(s, store.id, front={"mode": "new_customer", "name": a.name_heard, "amount": a.amount})
        else:
            effects.append(toast(f"Didn't catch that: “{text}”", "warn"))
    return effects


def _names_for(s: Session, ids: list[str]) -> dict[str, str]:
    return {c.id: c.name for c in s.exec(select(Customer).where(Customer.id.in_(ids))).all()}


@handles("udhaar_spoken")
async def on_udhaar_spoken(uow: UnitOfWork, p: sc.UdhaarSpoken):
    s = uow.s
    store = _store(s, p.store_id)
    if p.customer_id is None or p.amount is None:
        return await _spoken_text(uow, store, p.text, _lang(s, p.lang))
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

    integrity.check(s, store.id, f"confirm entry #{e.id}")

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


# ---------------------------------------------------------------- repayments (flow B)



def _payment_received(s: Session, store: Store, amount: int, customer: Customer | None, *,
                      cash: bool = False, sale_ref: str | None = None) -> list:
    """Soundbox alert + front-screen flash + customer notification for money that arrived."""
    lang = _lang(s)
    msg = messages.received(amount, customer.name if customer else None, lang, cash=cash)
    front = soundbox.current(s).get("front") or {}
    if sale_ref and front.get("sale_ref") == sale_ref and front.get("mode") == "confirm_qr":
        # Split sale: the ₹140 is paid, the ₹200 confirm QR is still waiting for a scan.
        new_front = {**front, "pay_qr": None, "pay_paid": True}
    elif front.get("mode") == "confirm_qr":
        new_front = None  # don't hide a pending confirmation behind a payment flash
    else:
        new_front = {"mode": "amount", "amount": amount, "text": f"{inr(amount)} received ✓"}
    soundbox.display(s, store.id, front=new_front, last_alert=msg["display"])
    effects = [soundbox.play(store.id, msg["spoken"], lang)]
    if customer is not None and not cash:
        effects.append(notify(f"customer:{customer.id}", "Payment successful", f"{inr(amount)} paid to {store.name}"))
    return effects


def _record_sale(s: Session, store: Store, amount: int, customer_id: str | None, payer_vpa: str | None,
                 ref: str | None, note: str) -> Sale:
    sale = Sale(store_id=store.id, customer_id=customer_id, amount=amount, payer_vpa=payer_vpa, ref=ref,
                note=note, created_at=clock.now())
    s.add(sale)
    trace("ledger", f"₹{amount} recorded as a sale (not udhaar)", {"ref": ref, "customer_id": customer_id})
    return sale


@handles("upi_payment")
async def on_upi_payment(uow: UnitOfWork, p: sc.UpiPayment):
    s = uow.s
    store = _store(s, p.store_id)
    trace("upi", f"{inr(p.amount)} from {p.payer_vpa}", {"payer_name": p.payer_name, "remark": p.remark, "ref": p.ref})
    d = reconcile.decide(s, store.id, p.payer_vpa, p.amount, p.payer_name, p.remark, p.ref)
    trace("reconcile", f"{d.rule}: {d.reason}", {"customer_id": d.customer_id, "kind": d.kind})

    if d.kind == "pending":
        payment = p.model_dump(mode="json")
        m = await recon_agent.match(payment, d.candidates)
        trace("recon_agent", f"Best guess {m['customer_id']} ({m['confidence']:.2f})", m, ms=m.get("ms"),
              source=m.get("source"))
        ids = {c["id"] for c in d.candidates}
        if m["customer_id"] in ids and m["confidence"] >= reconcile.AUTO_APPLY_CONFIDENCE:
            d = reconcile.Decision("repayment", "rule3", customer_id=m["customer_id"], matched_by="agent",
                                   confidence=m["confidence"], reason=m.get("reason", ""))
        else:
            pm = PendingMatch(store_id=store.id, payment=payment, candidates=d.candidates, agent_output=m,
                              created_at=clock.now())
            s.add(pm)
            s.flush()
            trace("validator", f"Confidence {m['confidence']:.2f} < {reconcile.AUTO_APPLY_CONFIDENCE}: ask merchant",
                  {"pending_id": pm.id})
            return _payment_received(s, store, p.amount, None) + [
                notify(f"merchant:{store.id}", f"Who paid {inr(p.amount)}?", p.payer_name or p.payer_vpa,
                       {"label": "Choose", "pending_id": pm.id})]

    customer = s.get(Customer, d.customer_id) if d.customer_id else None
    if d.kind == "sale":
        _record_sale(s, store, p.amount, d.customer_id, p.payer_vpa, p.ref, d.reason)
        return _payment_received(s, store, p.amount, customer, sale_ref=p.ref if d.rule == "rule0" else None)

    if d.link_vpa:
        customer.vpa = p.payer_vpa
        s.add(customer)
        trace("reconcile", f"Linked {p.payer_vpa} to {customer.name}", {"customer_id": customer.id})
    ledger.apply_repayment(s, store.id, customer.id, p.amount, "upi", matched_by=d.matched_by,
                           confidence=d.confidence, payer_vpa=p.payer_vpa, payer_name=p.payer_name,
                           remark=p.remark, ref=p.ref)
    return _payment_received(s, store, p.amount, customer)


@handles("cash_reported")
async def on_cash_reported(uow: UnitOfWork, p: sc.CashReported):
    s = uow.s
    store = _store(s, p.store_id)
    if p.customer_id is None or p.amount is None:
        return await _spoken_text(uow, store, p.text, _lang(s))
    c = _store_customer(s, store.id, p.customer_id)
    trace("soundbox", f"Heard: {messages.first_name(c.name)} {p.amount} cash diye", {"text": p.text})
    ledger.apply_repayment(s, store.id, c.id, p.amount, "cash", matched_by="merchant", remark=p.text)
    return _payment_received(s, store, p.amount, c, cash=True)


@handles("match_resolved")
def on_match_resolved(uow: UnitOfWork, p: sc.MatchResolved):
    s = uow.s
    pm = s.get(PendingMatch, p.pending_id)
    if pm is None:
        raise EventError(f"unknown pending match {p.pending_id}", 404)
    if pm.resolved:
        raise EventError("this payment was already matched", 409)
    store = s.get(Store, pm.store_id)
    pay = pm.payment
    if p.customer_id is None:
        _record_sale(s, store, pay["amount"], None, pay["payer_vpa"], pay.get("ref"), "merchant: not a repayment")
    else:
        c = _store_customer(s, store.id, p.customer_id)
        # The payer's VPA is not linked: it may be a relative's account (spec 4.2).
        ledger.apply_repayment(s, store.id, c.id, pay["amount"], "upi", matched_by="human",
                               payer_vpa=pay["payer_vpa"], payer_name=pay.get("payer_name"),
                               remark=pay.get("remark"), ref=pay.get("ref"))
        trace("merchant_app", f"Merchant matched {inr(pay['amount'])} to {c.name}", {"pending_id": pm.id})
    pm.resolved, pm.resolved_customer_id = True, p.customer_id
    s.add(pm)


# ---------------------------------------------------------------- auto-pay, bills, Supplier Advance (flows B4, D)

@handles("mandate_created")
def on_mandate_created(uow: UnitOfWork, p: sc.MandateCreated):
    s = uow.s
    c = _store_customer(s, p.store_id, p.customer_id)
    store = s.get(Store, p.store_id)
    trace("customer_app", f"{messages.first_name(c.name)} activated auto-pay", {"store_id": store.id})
    m = mandates.create(s, c.id, store.id, p.cap, p.window_start_day, p.window_end_day)
    return [notify(f"customer:{c.id}", "Auto-pay active",
                   f"Up to {inr(m.cap)} to {store.name} on salary day "
                   f"({window_label(m.window_start_day, m.window_end_day)})")]


@handles("salary_credited")
def on_salary_credited(uow: UnitOfWork, p: sc.SalaryCredited):
    s = uow.s
    c = s.get(Customer, p.customer_id)
    if c is None:
        raise EventError(f"unknown customer {p.customer_id}", 404)
    trace("upi", f"Salary credited to {messages.first_name(c.name)}")
    effects = []
    for m in mandates.active(s, c.id):
        rep = mandates.execute(s, m)
        if rep is None:
            continue
        store = s.get(Store, m.store_id)
        msg = messages.received(rep.amount, c.name, _lang(s))
        soundbox.display(s, store.id, last_alert=msg["display"])
        effects += [soundbox.play(store.id, msg["spoken"], _lang(s)),
                    notify(f"customer:{c.id}", "Auto-pay", f"{inr(rep.amount)} auto-paid to {store.name} ✓")]
    return effects


@handles("bill_added")
def on_bill_added(uow: UnitOfWork, p: sc.BillAdded):
    s = uow.s
    store = _store(s, p.store_id)
    n = len(s.exec(select(Bill.id)).all()) + 1
    b = Bill(id=f"B{n}", store_id=store.id, distributor=p.distributor, amount=p.amount, due_date=p.due_date)
    s.add(b)
    s.flush()
    g = forecast.gap_for_bill(forecast.forecast(s, store.id), b.id)
    trace("forecast", f"Bill {b.id} {p.distributor} {inr(p.amount)}: " + (f"{inr(g['gap'])} short" if g else "covered"),
          {"bill_id": b.id, "gap": g})


@handles("offer_advance")
def on_offer_advance(uow: UnitOfWork, p: sc.OfferAdvance):
    a = advance.offer(uow.s, p.store_id, p.bill_id)
    return [notify(f"merchant:{p.store_id}", "Supplier Advance offer",
                   f"{inr(a.amount)} from {a.lender} · fee {inr(a.fee)}", {"label": "View", "advance_id": a.id})]


@handles("advance_accept")
def on_advance_accept(uow: UnitOfWork, p: sc.AdvanceId):
    a = advance.accept(uow.s, p.advance_id)
    bill = uow.s.get(Bill, a.bill_id)
    trace("merchant_app", f"Merchant accepted {a.id}")
    return [notify(f"merchant:{a.store_id}", "Supplier Advance", f"{a.lender} paid {inr(a.amount)} to {bill.distributor} ✓")]


@handles("advance_decline")
def on_advance_decline(uow: UnitOfWork, p: sc.AdvanceId):
    advance.decline(uow.s, p.advance_id)


@handles("advance_day")
async def on_advance_day(uow: UnitOfWork, p: sc.AdvanceDay):
    effects = []
    for _ in range(p.days):
        effects = await daily.run_day(uow)  # only the last morning's briefing is spoken
    return effects


# ---------------------------------------------------------------- integrity (flow E)

@handles("inject_fraud_ring")
def on_inject_fraud_ring(uow: UnitOfWork, p: sc.InjectFraudRing):
    s = uow.s
    fraud.inject(s, p.store_id)
    alert = integrity.check(s, p.store_id, "fraud ring injected")
    if alert is None:
        return []
    store = s.get(Store, p.store_id)
    return [notify("overview", f"{store.name}: {integrity.summary(alert.rules)}",
                   f"Risk {alert.risk:.1f} · Supplier Advance blocked")]


# ---------------------------------------------------------------- recovery (flow C)

def _pay_action(store: Store, amount: int) -> dict:
    return {"type": "pay", "label": f"Pay {inr(amount)} now", "amount": amount, "store_id": store.id}


@handles("nudges_requested")
async def on_nudges_requested(uow: UnitOfWork, p: sc.NudgesRequested):
    s = uow.s
    store = _store(s, p.store_id)
    picked = collector.pick(s, store.id, p.customer_ids)
    trace("router", f"Collector policy picked {len(picked)} customer(s)", {"ids": [c.id for c, _ in picked]})
    if not picked:
        return [toast("No one is due for a reminder right now", "info")]
    for c, t in picked:
        res = await recovery.draft_nudge(c.name, c.lang, t.outstanding, t.oldest_overdue_days, c.persona, store.name)
        s.add(Message(store_id=store.id, customer_id=c.id, direction="out", text=res.data.message, lang=res.data.lang,
                      status="draft", created_at=clock.now(),
                      agent_output={"agent": "recovery_draft", "source": res.source, "dues": t.outstanding,
                                    "ui_actions": [_pay_action(store, t.outstanding)]}))
    return [notify(f"merchant:{store.id}", "Reminders ready", f"Approve {len(picked)} reminder(s)",
                   {"label": "Review"})]


@handles("nudges_approved")
def on_nudges_approved(uow: UnitOfWork, p: sc.NudgesApproved):
    s = uow.s
    msgs = s.exec(select(Message).where(Message.id.in_(p.message_ids))).all()
    if len(msgs) != len(set(p.message_ids)):
        raise EventError("unknown message id", 404)
    effects = []
    for m in msgs:
        if m.status != "draft":
            raise EventError(f"message {m.id} is already {m.status}", 409)
        m.status = "sent"
        link = s.get(StoreCustomer, (m.store_id, m.customer_id))
        link.last_nudge_at = clock.now()
        s.add_all([m, link])
        store = s.get(Store, m.store_id)
        effects.append(notify(f"customer:{m.customer_id}", f"{store.name} via Paytm", m.text,
                              {"label": "Open", "message_id": m.id}))
    trace("merchant_app", f"Merchant approved {len(msgs)} reminder(s)")
    return effects


@handles("customer_reply")
async def on_customer_reply(uow: UnitOfWork, p: sc.CustomerReply):
    s = uow.s
    c = _store_customer(s, p.store_id, p.customer_id)
    store = s.get(Store, p.store_id)
    today = clock.today()
    s.add(Message(store_id=store.id, customer_id=c.id, direction="in", text=p.text, lang=c.lang, status="received",
                  created_at=clock.now()))
    s.flush()
    dues = sum(ledger.remaining(e) for e in ledger.open_entries(s, store.id, c.id))
    has_mandate = bool(mandates.active(s, c.id, store.id))
    res = await recovery.interpret_reply(p.text, c.name, dues, today, has_mandate, store.name, c.lang)
    out = res.data

    if out.promise:
        for old in s.exec(select(Promise).where(Promise.customer_id == c.id, Promise.store_id == store.id,
                                                Promise.status == "open")).all():
            old.status = "replaced"
            s.add(old)
        s.add(Promise(customer_id=c.id, store_id=store.id, amount=out.promise.amount, date=out.promise.date,
                      created_at=clock.now()))
        trace("validator", f"Promise accepted: {inr(out.promise.amount)} by {out.promise.date:%d %b}")

    actions = []
    if out.suggest_mandate:
        actions.append({"type": "setup_autopay", "label": "Set up auto-pay", "store_id": store.id,
                        "cap": 3000, "window_start_day": 1, "window_end_day": 5})
    if dues > 0 and out.intent not in ("dispute",):
        actions.append(_pay_action(store, dues))
    clock.tick(5)  # the reply lands a moment after the customer's message
    s.add(Message(store_id=store.id, customer_id=c.id, direction="out", text=out.reply_message, lang=c.lang,
                  status="sent", created_at=clock.now(),
                  agent_output={"agent": "recovery_reply", "source": res.source, **out.model_dump(mode="json"),
                                "ui_actions": actions}))
    effects = [notify(f"customer:{c.id}", f"{store.name} via Paytm", out.reply_message)]
    if out.escalate:
        effects.append(notify(f"merchant:{store.id}", f"{messages.first_name(c.name)} needs your attention",
                              f"“{p.text}” ({out.intent})", {"label": "Open", "customer_id": c.id}))
    return effects
