"""Replies, promises and the auto-pay suggestion (v2 spec §4.11)."""
from datetime import date

from sqlmodel import Session

from app.agents import recovery
from app.config import now
from app.core import activity, mandates
from app.core.money import inr
from app.errors import EventError
from app.models import Customer, Message, PromiseRow, StoreCustomer


async def reply(s: Session, customer_id: str, store_id: str, text: str) -> dict:
    if s.get(StoreCustomer, (store_id, customer_id)) is None:
        raise EventError("You have no conversation with this shop", 404)
    c = s.get(Customer, customer_id)
    s.add(Message(store_id=store_id, customer_id=customer_id, direction="in", text=text[:500], lang=c.lang,
                  source="customer", created_at=now(), read=False))
    dues = mandates.verified_dues(s, store_id, customer_id)
    has_mandate = bool(mandates.active(s, customer_id, store_id))
    res = await recovery.interpret(text, c.name, dues, has_mandate, c.lang)
    actions = []
    if res["promise"]:
        p = res["promise"]
        s.add(PromiseRow(store_id=store_id, customer_id=customer_id, amount=p["amount"],
                         date=date.fromisoformat(p["date"]), created_at=now()))
        activity.log(s, store_id, "message", f"{c.name} promised {inr(p['amount'])} on "
                                             f"{date.fromisoformat(p['date']):%d %b}", res["source"])
    else:
        activity.log(s, store_id, "message", f"{c.name} replied ({res['intent']})", res["source"])
    if res["suggest_mandate"]:
        actions.append({"type": "setup_autopay", "label": "Set up salary-week auto-pay", "store_id": store_id})
    if dues and res["intent"] not in ("dispute",):
        actions.append({"type": "pay", "label": "Pay now", "store_id": store_id, "amount": dues})
    s.add(Message(store_id=store_id, customer_id=customer_id, direction="out", text=res["reply_message"], lang=c.lang,
                  source=res["source"] if res["source"] == "ai" else "template", created_at=now(),
                  meta={"kind": "reply", "intent": res["intent"], "promise": res["promise"],
                        "escalate": res["escalate"], "actions": actions}))
    if res["escalate"]:
        activity.log(s, store_id, "message", f"{c.name} needs your attention ({res['intent']})", res["source"])
    return res
