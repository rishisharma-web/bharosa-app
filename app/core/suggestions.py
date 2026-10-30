"""Munim's proactive suggestion cards on the merchant home (decision: code triggers, AI may word).

Code decides *when* a card appears, from the same rules the rest of the system uses:
- reminders: customers the collector policy would pick (≥ 7 days overdue, not reminded in 3 days)
  and no reminder drafts already waiting for approval;
- bill: a distributor bill with a forecast cash gap and no Supplier Advance yet.
The wording is a template today; with Sarvam it can be phrased by Munim (cached, validated).
"""
from datetime import date

from sqlmodel import Session, select

from app.core import collector
from app.core.money import inr
from app.models import Advance, Message

WEEKDAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def for_store(s: Session, store_id: str, gaps: list[dict]) -> list[dict]:
    cards = []
    drafts_waiting = s.exec(select(Message.id).where(Message.store_id == store_id, Message.status == "draft")).first()
    if not drafts_waiting:
        picked = collector.pick(s, store_id)
        if picked:
            who = ", ".join(f"{c.name.split()[0]} {inr(t.outstanding)} ({t.oldest_overdue_days} days)" for c, t in picked)
            cards.append({
                "id": "reminders", "kind": "reminders",
                "title": f"{len(picked)} customer{'s' if len(picked) > 1 else ''} overdue more than a week",
                "body": who,
                "action": {"type": "send_nudges", "label": f"Send {len(picked)} reminder{'s' if len(picked) > 1 else ''}",
                           "customer_ids": [c.id for c, _ in picked]},
                "source": "template",
            })
    has_advance = s.exec(select(Advance.id).where(Advance.store_id == store_id, Advance.state != "declined")).first()
    for g in gaps:
        if has_advance:
            break
        day = WEEKDAY_EN[date.fromisoformat(g["due"]).weekday()]
        cards.append({
            "id": f"bill:{g['bill_id']}", "kind": "bill",
            "title": f"{g['distributor']} {inr(g['amount'])} due {day}",
            "body": f"You will be {inr(g['gap'])} short. Want options?",
            "action": {"type": "ask_munim", "label": "Ask Munim",
                       "question": f"{day} ko {g['distributor'].split()[0]} ko {g['amount']:,} kaise dunga?"},
            "source": "template",
        })
    return cards
