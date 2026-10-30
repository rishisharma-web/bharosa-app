"""Customer app endpoints (v2 spec §7 Customer). Every call is scoped to the logged-in customer."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import auth, bus
from app.config import now
from app.core import activity, basket, mandates, messages, payments, requests as req, score as score_mod
from app.core.money import inr
from app.errors import EventError
from app.models import BasketOffer, Customer, Message, PendingRequest, ScoreShare, Store, StoreCustomer
from app.voice import spoken_line

router = APIRouter(prefix="/api")
Me = auth.Principal


class ShareIn(BaseModel):
    decision: Literal["share", "decline"]


class ConfirmIn(BaseModel):
    pay_method: Literal["upi", "credit_line"] | None = None
    device_id: str | None = Field(default=None, max_length=64)


class DisputeIn(BaseModel):
    reason: str = Field(min_length=1, max_length=120)


class PayIn(BaseModel):
    store_id: str
    amount: int = Field(ge=1, le=50_000)
    method: Literal["upi"] = "upi"


class ReplyIn(BaseModel):
    store_id: str
    text: str = Field(min_length=1, max_length=500)


class MandateIn(BaseModel):
    store_id: str
    cap: int = mandates.DEFAULT_CAP
    collection_day: int = mandates.DEFAULT_DAY


def _scopes(t: bus.Tx, store_id: str, customer_id: str) -> None:
    t.touch(f"merchant:{store_id}", f"customer:{customer_id}", f"soundbox:{store_id}")


# ---------------------------------------------------------------- views

def _action_needed(s: Session, cid: str) -> dict | None:
    r = s.exec(select(PendingRequest).where(PendingRequest.customer_id == cid, PendingRequest.status == "open")
               .order_by(PendingRequest.created_at.desc())).first()
    if r:
        store = s.get(Store, r.store_id)
        return {"kind": "request", "token": r.token, "request_kind": r.kind, "store": store.name,
                "title": f"{store.name} is waiting for you",
                "body": "Share your Bharosa Score to get credit" if r.kind == "share"
                else f"Confirm {inr(r.credit_now)} on credit", "button": "Open"}
    b = s.exec(select(BasketOffer).where(BasketOffer.customer_id == cid, BasketOffer.state == "offered")).first()
    if b:
        store = s.get(Store, b.store_id)
        return {"kind": "basket", "basket_id": b.id, "store": store.name,
                "title": f"Your monthly basket at {store.name}",
                "body": f"{inr(b.value)} · {len(b.items)} items · pay on credit within {store.due_days} days",
                "button": "View basket"}
    m = s.exec(select(Message).where(Message.customer_id == cid, Message.direction == "out", Message.read == False)  # noqa: E712
               .order_by(Message.id.desc())).first()
    if m:
        return {"kind": "message", "store": s.get(Store, m.store_id).name, "title": f"Message from {s.get(Store, m.store_id).name}",
                "body": m.text, "button": "Reply"}
    return None


def home_view(s: Session, cid: str) -> dict:
    req.expire_stale(s)
    c = s.get(Customer, cid)
    sc = score_mod.for_customer(s, cid)
    stores = {st.id: st for st in s.exec(select(Store)).all()}
    dues = []
    for link in s.exec(select(StoreCustomer).where(StoreCustomer.customer_id == cid)).all():
        opens = payments.open_entries(s, link.store_id, cid)
        amount = sum(e.amount - e.paid for e in opens)
        if amount or link.credit_balance:
            dues.append({"store": stores[link.store_id].name, "store_id": link.store_id, "amount": amount,
                         "overdue_days": max((score_mod.overdue_days(e) for e in opens), default=0),
                         "credit_balance": link.credit_balance, "is_network": stores[link.store_id].is_network})
    shares = [{"store": stores[x.store_id].name, "store_id": x.store_id, "granted_at": x.granted_at.isoformat()}
              for x in s.exec(select(ScoreShare).where(ScoreShare.customer_id == cid, ScoreShare.revoked_at == None)).all()]  # noqa: E711
    return {
        "customer": {"id": c.id, "name": c.name, "phone": c.phone, "lang": c.lang},
        "action_needed": _action_needed(s, cid),
        "score": sc.to_dict(),
        "dues": dues,
        "mandates": [mandates.schedule(s, m) for m in mandates.active(s, cid)],
        "shares": shares,
        "autopay_defaults": {"cap": mandates.DEFAULT_CAP, "collection_day": mandates.DEFAULT_DAY},
        "baskets": [{"id": b.id, "store": stores[b.store_id].name, "items": b.items, "value": b.value, "state": b.state}
                    for b in s.exec(select(BasketOffer).where(BasketOffer.customer_id == cid)).all()],
    }


@router.get("/customer/home")
async def home(me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        return home_view(t.s, me.customer_id)


# ---------------------------------------------------------------- requests (QR bridge)

@router.get("/requests/{token}")
async def request_details(token: str, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        r = req.get_for_customer(t.s, token, me.customer_id)
        return req.describe(t.s, r)


@router.post("/requests/{token}/share")
async def share(token: str, body: ShareIn, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        out = req.share(t.s, token, me.customer_id, body.decision)
        _scopes(t, t.s.get(PendingRequest, token).store_id, me.customer_id)
    return out


@router.post("/requests/{token}/confirm")
async def confirm(token: str, body: ConfirmIn, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        out = req.confirm(t.s, token, me.customer_id, body.pay_method, body.device_id)
        r = t.s.get(PendingRequest, token)
        _scopes(t, r.store_id, me.customer_id)
        await spoken_line(t, r.store_id, out["spoken"])
    return {"ok": True, "entry_id": out["entry_id"]}


@router.post("/requests/{token}/dispute")
async def dispute(token: str, body: DisputeIn, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        req.dispute(t.s, token, me.customer_id, body.reason)
        _scopes(t, t.s.get(PendingRequest, token).store_id, me.customer_id)
    return {"ok": True}


# ---------------------------------------------------------------- money

@router.post("/customer/pay")
async def pay(body: PayIn, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        if t.s.get(StoreCustomer, (body.store_id, me.customer_id)) is None:
            raise EventError("You have no dues at this shop", 404)
        p = payments.repay(t.s, body.store_id, me.customer_id, body.amount, body.method)
        _scopes(t, body.store_id, me.customer_id)
        await spoken_line(t, body.store_id, f"{inr(body.amount)} received from {me.name.split()[0]}.")
    return {"ok": True, "amount": p.amount, "lender_share": p.lender_share, "merchant_share": p.merchant_share}


@router.post("/customer/mandates")
async def create_mandate(body: MandateIn, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        m = mandates.create(t.s, me.customer_id, body.store_id, body.cap, body.collection_day)
        _scopes(t, body.store_id, me.customer_id)
        return mandates.schedule(t.s, m)


@router.post("/customer/shares/{store_id}/revoke")
async def revoke_share(store_id: str, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        rows = t.s.exec(select(ScoreShare).where(ScoreShare.customer_id == me.customer_id,
                                                 ScoreShare.store_id == store_id, ScoreShare.revoked_at == None)).all()  # noqa: E711
        if not rows:
            raise EventError("Nothing shared with this shop", 404)
        for r in rows:
            r.revoked_at = now()
            t.s.add(r)
        activity.log(t.s, store_id, "confirm", f"{me.name} stopped sharing their Bharosa Score")
        _scopes(t, store_id, me.customer_id)
    return {"ok": True}


@router.post("/customer/baskets/{basket_id}/accept")
async def basket_accept(basket_id: int, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        b = basket.accept(t.s, basket_id, me.customer_id)
        _scopes(t, b.store_id, me.customer_id)
    return {"ok": True}


@router.post("/customer/baskets/{basket_id}/decline")
async def basket_decline(basket_id: int, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        b = basket.decline(t.s, basket_id, me.customer_id)
        _scopes(t, b.store_id, me.customer_id)
    return {"ok": True}


# ---------------------------------------------------------------- messages

@router.get("/customer/messages")
async def get_messages(me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        rows = t.s.exec(select(Message).where(Message.customer_id == me.customer_id).order_by(Message.id)).all()
        threads: dict[str, dict] = {}
        changed = False
        for m in rows:
            th = threads.setdefault(m.store_id, {"store_id": m.store_id, "store": t.s.get(Store, m.store_id).name,
                                                 "messages": []})
            th["messages"].append({"id": m.id, "direction": m.direction, "text": m.text, "ts": m.created_at.isoformat(),
                                   "actions": (m.meta or {}).get("actions", [])})
            if m.direction == "out" and not m.read:
                m.read, changed = True, True
                t.s.add(m)
        if changed:
            t.touch(f"customer:{me.customer_id}")
        return list(threads.values())


@router.post("/customer/messages/reply")
async def reply(body: ReplyIn, me: Me = Depends(auth.customer)):
    async with bus.tx() as t:
        res = await messages.reply(t.s, me.customer_id, body.store_id, body.text)
        _scopes(t, body.store_id, me.customer_id)
    return {"intent": res["intent"], "promise": res["promise"]}
