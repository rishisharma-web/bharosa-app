"""Growth plan (v2 spec §4.7): three actions computed by code, ranked by expected impact.
The Growth Agent may only reword titles and reasons; facts, impact and order stay code-defined.

    1 A_DIWALI  festive stock         +expected extra sales      → order (bill B1) → Stock Advance offer
    2 A_REMIND  collect overdue       overdue amount             → reminder messages
    3 A_BASKET  monthly basket        basket value               → basket offer to the customer
"""
from sqlmodel import Session, select

from app.agents import recovery
from app.config import now
from app.core import activity, advance, basket, festive, payments, score as score_mod
from app.core.money import inr
from app.errors import EventError
from app.models import Advance, BasketOffer, Customer, GrowthAction, Message, PromiseRow, StoreCustomer


def _overdue_customers(s: Session, store_id: str) -> list[dict]:
    out = []
    ids = [l.customer_id for l in s.exec(select(StoreCustomer).where(StoreCustomer.store_id == store_id)).all()]
    for cid in ids:
        opens = payments.open_entries(s, store_id, cid)
        days = max((score_mod.overdue_days(e) for e in opens), default=0)
        if days:
            c = s.get(Customer, cid)
            out.append({"customer_id": cid, "name": c.name, "dues": sum(e.amount - e.paid for e in opens),
                        "overdue": sum(e.amount - e.paid for e in opens if score_mod.overdue_days(e)), "days": days})
    return sorted(out, key=lambda x: x["days"])


def _basket_candidate(s: Session, store_id: str) -> dict | None:
    best = None
    for c in s.exec(select(Customer).where(Customer.loginable == True)).all():  # noqa: E712
        p = basket.predict(s, store_id, c.id)
        if p and (best is None or p["value"] > best["value"]):
            best = {**p, "customer_id": c.id, "name": c.name}
    return best


def compute(s: Session, store_id: str) -> list[dict]:
    fp = festive.for_store(s, store_id)
    od = _overdue_customers(s, store_id)
    bk = _basket_candidate(s, store_id)
    cats = ", ".join(c["label"] for c in fp["categories"])
    actions = [
        {"action_id": "A_DIWALI", "type": "festive_stock", "impact": fp["expected_extra"],
         "facts": {"festival": fp["festival"], "date": fp["date"], "uplift": fp["overall_uplift"],
                   "order_total": fp["order_total"], "expected_extra": fp["expected_extra"],
                   "supplier": fp["supplier"], "categories": cats},
         "title": f"Stock up for {fp['festival']}",
         "why": (f"Last year your {fp['festival']}-week sales were about {fp['overall_uplift']:g}× normal. "
                 f"A {inr(fp['order_total'])} order could bring about {inr(fp['expected_extra'])} in extra sales.")},
        {"action_id": "A_REMIND", "type": "collect_overdue", "impact": sum(x["overdue"] for x in od),
         "facts": {"customers": od, "overdue_total": sum(x["overdue"] for x in od)},
         "title": f"Remind {len(od)} overdue customer{'s' if len(od) != 1 else ''}",
         "why": f"{inr(sum(x['overdue'] for x in od))} is overdue: " +
                " and ".join(f"{x['name'].split()[0]} ({x['days']} days)" for x in od) + "."},
    ]
    if bk:
        actions.append(
            {"action_id": "A_BASKET", "type": "monthly_basket", "impact": bk["value"],
             "facts": {"customer_id": bk["customer_id"], "name": bk["name"], "value": bk["value"],
                       "items": len(bk["items"])},
             "title": f"Offer {bk['name'].split()[0]} her monthly basket",
             "why": (f"{bk['name'].split()[0]} buys the same {len(bk['items'])} items every month. "
                     f"{inr(bk['value'])}, within her limit.")})
    for i, a in enumerate(actions, start=1):
        a["rank"] = i
    return actions


def generate(s: Session, store_id: str) -> None:
    for old in s.exec(select(GrowthAction).where(GrowthAction.store_id == store_id)).all():
        s.delete(old)
    for a in compute(s, store_id):
        s.add(GrowthAction(store_id=store_id, action_id=a["action_id"], type=a["type"], facts=a["facts"],
                           impact=a["impact"], rank=a["rank"], title=a["title"], why=a["why"], updated_at=now()))
    activity.log(s, store_id, "growth", "This week's growth plan is ready: 3 actions")


def apply_wording(s: Session, store_id: str, wording: dict) -> None:
    """Store validated AI wording (titles / reasons only)."""
    for a in s.exec(select(GrowthAction).where(GrowthAction.store_id == store_id)).all():
        w = wording.get(a.action_id)
        if w:
            a.title, a.why, a.source = w["title"], w["why"], "ai"
            s.add(a)


async def approve(s: Session, store_id: str, action_id: str) -> GrowthAction:
    a = s.exec(select(GrowthAction).where(GrowthAction.store_id == store_id, GrowthAction.action_id == action_id)).first()
    if a is None:
        raise EventError("Unknown action", 404)
    if a.state != "proposed":
        raise EventError("Already approved", 409)
    if action_id == "A_DIWALI":
        advance.create_bill_and_offer(s, store_id)
    elif action_id == "A_REMIND":
        for x in a.facts["customers"]:
            c = s.get(Customer, x["customer_id"])
            opens = payments.open_entries(s, store_id, c.id)  # live dues: they may have bought more since
            dues = sum(e.amount - e.paid for e in opens)
            days = max((score_mod.overdue_days(e) for e in opens), default=0)
            if not dues:
                continue
            text, source = await recovery.draft(c.name, dues, days, c.lang)
            s.add(Message(store_id=store_id, customer_id=c.id, direction="out", text=text, lang=c.lang,
                          source=source, created_at=now(), meta={"kind": "reminder", "dues": dues}))
            activity.log(s, store_id, "message", f"Reminder sent to {c.name} ({inr(dues)})", source)
    elif action_id == "A_BASKET":
        if basket.offer(s, store_id, a.facts["customer_id"]) is None:
            raise EventError("The basket is no longer within this customer's limit", 409)
    a.state, a.updated_at = "approved", now()
    s.add(a)
    activity.log(s, store_id, "growth", f"Approved: {a.title}")
    return a


def view(s: Session, store_id: str) -> list[dict]:
    """The plan with live outcomes; an action is done once its follow-up has finished."""
    out = []
    for a in s.exec(select(GrowthAction).where(GrowthAction.store_id == store_id).order_by(GrowthAction.rank)).all():
        state, outcome = a.state, None
        if a.state != "proposed":
            if a.action_id == "A_DIWALI":
                adv = s.get(Advance, "A1")
                if adv is None:
                    outcome = "Order placed: no cash gap"
                elif adv.state == "offered":
                    outcome = f"Stock Advance offered: {inr(adv.amount)}"
                elif adv.state == "declined":
                    state, outcome = "done", "Advance declined"
                else:
                    state, outcome = "done", f"{adv.lender} paid {a.facts['supplier']} {inr(adv.amount)} ✓"
            elif a.action_id == "A_REMIND":
                ids = [x["customer_id"] for x in a.facts["customers"]]
                replies = len({m.customer_id for m in s.exec(select(Message).where(
                    Message.store_id == store_id, Message.direction == "in", Message.customer_id.in_(ids))).all()})
                promises = len(s.exec(select(PromiseRow).where(PromiseRow.store_id == store_id,
                                                               PromiseRow.customer_id.in_(ids))).all())
                outcome = f"Sent to {len(ids)} · {replies} replied · {promises} promise{'s' if promises != 1 else ''}"
                if replies == len(ids):
                    state = "done"
            elif a.action_id == "A_BASKET":
                b = s.exec(select(BasketOffer).where(BasketOffer.store_id == store_id)
                           .order_by(BasketOffer.id.desc())).first()
                if b is not None:
                    outcome = {"offered": f"Offer sent to {a.facts['name'].split()[0]}",
                               "accepted": f"{a.facts['name'].split()[0]} accepted ✓ · deliver from Orders",
                               "delivered": "Delivered ✓", "declined": "Declined"}[b.state]
                    if b.state != "offered":
                        state = "done"
        out.append({"action_id": a.action_id, "type": a.type, "rank": a.rank, "title": a.title, "why": a.why,
                    "impact": a.impact, "facts": a.facts, "state": state, "outcome": outcome, "source": a.source})
    return out
