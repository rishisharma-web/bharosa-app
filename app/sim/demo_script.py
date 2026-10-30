"""Demo Mode (spec 13): seven beats, each a list of steps with a caption.

Automatic steps run when the presenter presses Next. Presenter steps (scan the QR and
Confirm, tap "Set up auto-pay", tap the Munim action, Accept the advance) are left for the
presenter to do on screen; the beat pauses there. Pressing Next again performs any
presenter step that has not happened yet, so the demo can never get stuck.

State: sim_state.demo_beat (last beat started), demo_resume (index of the first presenter
step still to check in that beat, or None), demo_caption.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlmodel import Session, select

from app import db, state
from app.adapters import soundbox
from app.agents import munim
from app.events.effects import caption as caption_effect
from app.events.router import fire, unit_of_work
from app.models import Advance, Entry, Mandate, Message
from app.sim.seed import seed

RAMESH_REPLY = "Salary 1 tareekh ko aati hai, tab pura de dunga"
MUNIM_QUESTION = "Friday ko Sharma ko 18,000 kaise dunga?"


@dataclass
class Step:
    label: str
    run: Callable[[], Awaitable[None]]
    presenter: bool = False  # left for the presenter; Next performs it if still undone
    done: Callable[[Session], bool] | None = None
    pause_after: float = 0.0


@dataclass
class Beat:
    n: int
    title: str
    caption: str
    steps: list[Step] = field(default_factory=list)


# ---------------------------------------------------------------- step helpers

def _read(fn):
    with db.session() as s:
        return fn(s)


def _ramesh_proposed(s: Session) -> Entry | None:
    return s.exec(select(Entry).where(Entry.customer_id == "C_RAMESH", Entry.state == "proposed")
                  .order_by(Entry.id.desc())).first()


def _event(type_: str, payload: dict | Callable[[Session], dict]):
    async def run():
        await fire(type_, _read(payload) if callable(payload) else payload)
    return run


async def _ask_munim():
    async with unit_of_work() as uow:
        await munim.ask(uow.s, "S1", MUNIM_QUESTION, state.get(uow.s, "lang"))


def _live_advance(s: Session) -> Advance | None:
    return s.exec(select(Advance).where(Advance.store_id == "S1", Advance.state != "declined")
                  .order_by(Advance.created_at.desc())).first()


BEATS = [
    Beat(0, "Morning", "Morning: Bharosa briefs Lakshmi Stores in Hindi."),
    Beat(1, "Guardrail", "Same ₹340, two answers. The risk check took 3 ms; no AI decided the limit.", [
        Step("Priya asks for ₹340 on credit", _event("udhaar_spoken", {"store_id": "S1", "customer_id": "C_PRIYA",
                                                                      "amount": 340}), pause_after=1.5),
        Step("Ramesh asks for ₹340 on credit", _event("udhaar_spoken", {"store_id": "S1", "customer_id": "C_RAMESH",
                                                                       "amount": 340})),
    ]),
    Beat(2, "Confirm", "Ramesh confirms in his own Paytm app. A diary entry becomes a verified receivable.", [
        Step("Ramesh pays ₹140 now by UPI", _event("upi_payment", lambda s: {
            "store_id": "S1", "payer_vpa": "ramesh.k@ptyes", "payer_name": "Ramesh Kumar", "amount": 140,
            "ref": soundbox.current(s)["front"].get("sale_ref")}), pause_after=1.0),
        Step("Scan the QR on the Soundbox, then Confirm on Ramesh's phone",
             _event("customer_confirm", lambda s: {"token": _ramesh_proposed(s).confirm_token,
                                                   "device_id": "dev-ramesh"}),
             presenter=True, done=lambda s: _ramesh_proposed(s) is None),
    ]),
    Beat(3, "Recovery (AI)", "The AI understood a Hinglish reply and turned it into a promise, then a mandate. "
                             "No chasing.", [
        Step("Draft a reminder for Ramesh", _event("nudges_requested", {"store_id": "S1",
                                                                        "customer_ids": ["C_RAMESH"]}), pause_after=1.0),
        Step("Merchant approves the reminder", _event("nudges_approved", lambda s: {"message_ids": [
            m.id for m in s.exec(select(Message).where(Message.customer_id == "C_RAMESH",
                                                       Message.status == "draft")).all()]}), pause_after=1.5),
        Step("Ramesh replies", _event("customer_reply", {"customer_id": "C_RAMESH", "store_id": "S1",
                                                         "text": RAMESH_REPLY}), pause_after=1.0),
        Step("Ramesh taps “Set up auto-pay” and activates it",
             _event("mandate_created", {"customer_id": "C_RAMESH", "store_id": "S1", "cap": 3000,
                                        "window_start_day": 1, "window_end_day": 5}),
             presenter=True, done=lambda s: s.exec(select(Mandate).where(
                 Mandate.customer_id == "C_RAMESH", Mandate.status == "active")).first() is not None),
    ]),
    Beat(4, "Supplier Advance (AI)", "Munim checked the forecast, the dues and eligibility. "
                                     "The lender pays the distributor directly.", [
        Step(f"Shopkeeper asks Munim: “{MUNIM_QUESTION}”", _ask_munim, pause_after=1.0),
        Step("Tap “Get Supplier Advance” in Munim's answer",
             _event("offer_advance", {"store_id": "S1", "bill_id": "B1"}),
             presenter=True, done=lambda s: _live_advance(s) is not None),
        Step("Accept the offer", _event("advance_accept", lambda s: {"advance_id": _live_advance(s).id}),
             presenter=True, done=lambda s: (a := _live_advance(s)) is not None and a.state != "offered"),
    ]),
    Beat(5, "Salary day", "Salary lands, dues clear themselves, and 20% of each repayment goes to the lender.", [
        Step(f"Day {i + 1} of 6", _event("advance_day", {"days": 1}), pause_after=0.6) for i in range(6)
    ]),
    Beat(6, "Fraud ring", "Fake udhaar to farm loans? Blocked by graph rules before any money moves.", [
        Step("Sai Kirana records four fake customers", _event("inject_fraud_ring", {"store_id": "S2"})),
    ]),
]
TOTAL = len(BEATS)


# ---------------------------------------------------------------- runner

async def _set(beat: int, resume: int | None, caption: str | None = None) -> None:
    async with unit_of_work() as uow:
        state.put(uow.s, "demo_beat", beat)
        state.put(uow.s, "demo_resume", resume)
        state.put(uow.s, "demo_awaiting", BEATS[beat].steps[resume].label if resume is not None else None)
        if caption is not None:
            state.put(uow.s, "demo_caption", caption)
            uow.effects.append(caption_effect(caption))


async def _run_steps(beat: Beat, start: int, fast: bool, include_presenter: bool) -> tuple[list[str], int | None]:
    ran = []
    for i in range(start, len(beat.steps)):
        st = beat.steps[i]
        if st.presenter:
            if st.done and _read(st.done):
                continue
            if not include_presenter:
                return ran, i
        await st.run()
        ran.append(st.label)
        if st.pause_after and not fast:
            await asyncio.sleep(st.pause_after)
    return ran, None


def _status(beat: Beat, resume: int | None, ran: list[str]) -> dict:
    return {"beat": beat.n, "total": TOTAL, "title": beat.title, "caption": beat.caption, "ran": ran,
            "awaiting": beat.steps[resume].label if resume is not None else None}


async def reset() -> dict:
    async with unit_of_work() as uow:
        stats = seed()  # rebuilds tables in its own transaction, resets the clock, writes the briefing
        b = state.get(uow.s, "briefing")
        state.put(uow.s, "demo_beat", 0)
        state.put(uow.s, "demo_resume", None)
        state.put(uow.s, "demo_awaiting", None)
        state.put(uow.s, "demo_caption", BEATS[0].caption)
        uow.effects += [caption_effect(BEATS[0].caption), soundbox.play("S1", b["text"], b["lang"])]
    return stats


async def next_beat(fast: bool = False) -> dict:
    with db.session() as s:
        current, resume = state.get(s, "demo_beat"), state.get(s, "demo_resume")
    if resume is not None:  # finish the current beat: do whatever the presenter has not done yet
        beat = BEATS[current]
        ran, _ = await _run_steps(beat, resume, fast, include_presenter=True)
        await _set(current, None)
        return _status(beat, None, ran)
    if current + 1 >= TOTAL:
        return {"beat": current, "total": TOTAL, "done": True, "caption": BEATS[current].caption, "ran": [],
                "awaiting": None}
    beat = BEATS[current + 1]
    await _set(beat.n, None, beat.caption)
    ran, resume = await _run_steps(beat, 0, fast, include_presenter=False)
    if resume is not None:
        await _set(beat.n, resume)
    return _status(beat, resume, ran)


async def goto(n: int) -> dict:
    """Reset, then run beats 1..n completely (presenter steps included) without pauses."""
    n = max(0, min(n, TOTAL - 1))
    await reset()
    out = {"beat": 0, "total": TOTAL, "caption": BEATS[0].caption, "ran": [], "awaiting": None}
    for _ in range(n):
        out = await next_beat(fast=True)
        if out.get("awaiting"):
            out = await next_beat(fast=True)
    return out


def script() -> list[dict]:
    return [{"beat": b.n, "title": b.title, "caption": b.caption,
             "steps": [{"label": st.label, "presenter": st.presenter} for st in b.steps]} for b in BEATS]
