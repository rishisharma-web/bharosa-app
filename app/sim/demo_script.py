"""Demo Mode (spec 13), step by step: every press of Next runs ONE step and explains it.

Each step has an explanation in three parts, written by us (not by an LLM, so it never lags or
fails on stage):
    what — what just happened on screen
    who  — who decided: code (formula/rule), AI (which agent, and what checked it),
           the customer, or the merchant
    why  — why it matters

Presenter steps are things a person does on screen (scan a QR, tap a button). The bar shows
"Your turn: …"; if the presenter does it, the step completes by itself and its explanation
appears; if they press Next instead, the step is done for them. A step whose effect already
happened on screen is never run twice, so no money step can be repeated.

State (sim_state): demo_beat, demo_step (index of the next step in that beat),
demo_last (explanation of the step just completed), demo_caption.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from sqlmodel import Session, select

from app import clock, db, state
from app.adapters import soundbox
from app.agents import munim
from app.events.effects import caption as caption_effect
from app.events.router import before_commit, fire, unit_of_work
from app.models import Advance, Entry, Mandate, Message, Sale
from app.sim.seed import seed

RAMESH_REPLY = "Salary 1 tareekh ko aati hai, tab pura de dunga"
MUNIM_QUESTION = "Friday ko Sharma ko 15,000 kaise dunga?"


@dataclass
class Step:
    label: str
    run: Callable[[], Awaitable[None]]
    what: str
    who: str
    why: str
    kind: str = "code"  # code | ai | customer | merchant: who decided
    presenter: bool = False
    done: Callable[[Session], bool] | None = None
    ui: dict = field(default_factory=dict)  # screens to show while this step is next: merchant / customer / view
    pause_after: float = 0.0


@dataclass
class Beat:
    n: int
    title: str
    caption: str
    steps: list[Step]


# ---------------------------------------------------------------- helpers

def _read(fn):
    with db.session() as s:
        return fn(s)


def _ramesh_proposed(s: Session) -> Entry | None:
    return s.exec(select(Entry).where(Entry.customer_id == "C_RAMESH", Entry.state == "proposed")
                  .order_by(Entry.id.desc())).first()


def _ramesh_sale_ref(s: Session) -> str | None:
    """The unpaid 'pay ₹100 now' reference for Ramesh's split sale today, if any."""
    e = s.exec(select(Entry).where(Entry.customer_id == "C_RAMESH", Entry.requested_amount > Entry.amount)
               .order_by(Entry.id.desc())).first()
    if e is None or e.created_at.date() != clock.today():
        return None
    ref = f"SALE-{e.id}"
    return None if s.exec(select(Sale.id).where(Sale.ref == ref)).first() else ref


def _drafts(s: Session) -> list[int]:
    return [m.id for m in s.exec(select(Message).where(Message.store_id == "S1", Message.status == "draft")).all()]


def _ramesh_messages(s: Session, direction: str, status: str) -> bool:
    return s.exec(select(Message.id).where(Message.customer_id == "C_RAMESH", Message.direction == direction,
                                           Message.status == status)).first() is not None


def _advance(s: Session) -> Advance | None:
    return s.exec(select(Advance).where(Advance.store_id == "S1", Advance.state != "declined")
                  .order_by(Advance.created_at.desc())).first()


def _event(type_: str, payload: dict | Callable[[Session], dict]):
    async def run():
        await fire(type_, _read(payload) if callable(payload) else payload)
    return run


async def _speak_briefing():
    async with unit_of_work() as uow:
        b = state.get(uow.s, "briefing")
        uow.effects.append(soundbox.play("S1", b["text"], b["lang"], kind="briefing"))


async def _ask_munim():
    async with unit_of_work() as uow:
        await munim.ask(uow.s, "S1", MUNIM_QUESTION, state.get(uow.s, "lang"))


def _udhaar(cid: str):
    return _event("udhaar_spoken", {"store_id": "S1", "customer_id": cid, "amount": 500})


# ---------------------------------------------------------------- the script

BEATS = [
    Beat(0, "Morning", "Morning: Munim briefs Lakshmi Stores in Hindi.", [
        Step("Play Munim's morning briefing", _speak_briefing,
             what="The Soundbox reads the morning briefing: yesterday's sales, udhaar to collect, and Sharma "
                  "Traders' ₹15,000 bill on Friday, ₹5,000 short.",
             who="Code computes every number (sales, dues, the cash forecast). Munim (AI) only phrases them in "
                 "Hindi; a validator rejects any rewording that changes a number.",
             why="The shopkeeper knows today's money situation before the first customer walks in.",
             kind="ai", ui={"merchant": "home", "customer": "home"}),
    ]),
    Beat(1, "Guardrail", "Same ₹500, three answers. A formula decides each in milliseconds; no AI.", [
        Step("Priya asks for ₹500 on credit", _udhaar("C_PRIYA"),
             what="Green: safe. Priya can take ₹500 on credit.",
             who="Code · risk formula. Score 780 and nothing owed → safe limit ₹4,100. No AI.",
             why="Good customers get credit instantly, with no awkward questions."),
        Step("Vikram asks for ₹500 on credit", _udhaar("C_VIKRAM"),
             what="Red: limit ₹0. The Soundbox suggests collecting the full ₹500 now.",
             who="Code · ₹2,500 has been overdue for 45 days → limit ×0.",
             why="The shopkeeper hears the risk before handing over goods, not after."),
        Step("Ramesh asks for ₹500 on credit", _udhaar("C_RAMESH"),
             what="Amber: give ₹400 on credit and collect ₹100 now. The customer-facing screen shows two QRs.",
             who="Code · ₹1,500 has been overdue for 20 days → limit ×0.6 → ₹400.",
             why="Credit still flows, but the risk is capped. Tap “Why?” on the Soundbox for the reasons."),
    ]),
    Beat(2, "Confirm", "Ramesh confirms in his own Paytm app. A diary entry becomes a verified receivable.", [
        Step("Ramesh pays the ₹100 by scanning the pay QR",
             _event("upi_payment", lambda s: {"store_id": "S1", "payer_vpa": "ramesh.k@ptyes",
                                              "payer_name": "Ramesh Kumar", "amount": 100,
                                              "ref": _ramesh_sale_ref(s)}),
             what="₹100 received from Ramesh, recorded as today's sale.",
             who="Code · the payment carries the QR's sale reference (SALE-…), so it never touches his old ₹1,500.",
             why="Without this rule a ₹100 sale would silently pay down old dues and corrupt the books.",
             done=lambda s: _ramesh_sale_ref(s) is None, pause_after=1.0),
        Step("Click the ₹400 QR on the Soundbox, then tap Confirm on Ramesh's phone",
             _event("customer_confirm", lambda s: {"token": _ramesh_proposed(s).confirm_token, "device_id": "dev-ramesh"}),
             what="Ramesh confirmed ₹400 in his own Paytm app. He now owes ₹1,900, all verified.",
             who="The customer decides. Code marks it verified, records consent and runs the fraud check.",
             why="A notebook entry is a claim; a confirmed entry is a receivable a lender can trust.",
             kind="customer", presenter=True, done=lambda s: _ramesh_proposed(s) is None,
             ui={"customer": "home"}),
    ]),
    Beat(3, "Recovery (AI)", "Munim spots overdue udhaar. The Recovery Agent turns a Hinglish reply into a "
                             "promise, then auto-pay.", [
        Step("Tap “Send 3 reminders” on Munim's suggestion",
             _event("nudges_requested", {"store_id": "S1"}),
             what="Munim noticed 3 customers overdue more than a week. A reminder is drafted for each.",
             who="Code picks who (overdue ≥ 7 days, not reminded in 3 days). AI · Recovery Agent writes each "
                 "message; a validator checks it states the exact dues and invents no other amount.",
             why="Reminders without the shopkeeper having to chase neighbours.",
             kind="ai", presenter=True, done=lambda s: bool(_drafts(s)) or _ramesh_messages(s, "out", "sent"),
             ui={"merchant": "home"}),
        Step("Approve the reminders",
             _event("nudges_approved", lambda s: {"message_ids": _drafts(s)}),
             what="The reminders arrive in each customer's Paytm app, from “Lakshmi Stores via Paytm”.",
             who="The merchant decides. Nothing reaches a customer without this tap.",
             why="AI drafts; people stay in charge of what is sent.",
             kind="merchant", presenter=True, done=lambda s: not _drafts(s) and _ramesh_messages(s, "out", "sent"),
             ui={"merchant": "home", "customer": "messages"}),
        Step(f"Ramesh replies: “{RAMESH_REPLY}”",
             _event("customer_reply", {"customer_id": "C_RAMESH", "store_id": "S1", "text": RAMESH_REPLY}),
             what="The reply is read as a promise: ₹1,900 on 1 Nov. Ramesh is offered salary-day auto-pay.",
             who="AI · Recovery Agent classifies the Hinglish reply. Code checks the promise against policy "
                 "(within 30 days, not more than he owes) before saving it.",
             why="A vague reply becomes a dated promise that the cash forecast can rely on.",
             kind="ai", done=lambda s: _ramesh_messages(s, "in", "received"),
             ui={"customer": "messages"}, pause_after=1.0),
        Step("On Ramesh's phone, tap “Set up auto-pay”, then Activate",
             _event("mandate_created", {"customer_id": "C_RAMESH", "store_id": "S1", "cap": 3000,
                                        "window_start_day": 1, "window_end_day": 5}),
             what="Salary-day auto-pay is on: up to ₹3,000, on the 1st–5th of the month. Score 660 → 665.",
             who="The customer decides (a UPI AutoPay mandate). Code adds +5 to his Bharosa Score.",
             why="Dues will clear themselves on payday. No reminders needed next month.",
             kind="customer", presenter=True,
             done=lambda s: s.exec(select(Mandate.id).where(Mandate.customer_id == "C_RAMESH",
                                                            Mandate.status == "active")).first() is not None,
             ui={"customer": "messages"}),
    ]),
    Beat(4, "Supplier Advance (AI)", "Munim checks the forecast, dues and eligibility. The lender pays the "
                                     "distributor directly.", [
        Step("Tap “Ask Munim” on the Sharma Traders suggestion", _ask_munim,
             what=f"The shopkeeper asks: “{MUNIM_QUESTION}” Munim answers with two options and buttons.",
             who="AI · Munim calls three read-only tools: cash forecast, dues expected back, advance eligibility. "
                 "Every rupee figure in its answer must appear in a tool result, or the answer is rebuilt by code.",
             why="A plain-language answer to a real money problem, grounded in the shop's own numbers.",
             kind="ai", presenter=True,
             done=lambda s: (state.get(s, "munim_last") or {}).get("question", "").lower().startswith("friday"),
             ui={"merchant": "home"}),
        Step("Tap “Get Supplier Advance” in Munim's answer",
             _event("offer_advance", {"store_id": "S1", "bill_id": "B1"}),
             what="Partner NBFC offers ₹5,000 for a ₹75 fee (₹5,075 in total), repaid from 20% of incoming udhaar.",
             who="Code sizes it: the ₹5,000 gap, capped at 40% of verified udhaar from good customers (₹5,800).",
             why="Working capital against verified receivables, not against guesswork.",
             presenter=True, done=lambda s: _advance(s) is not None, ui={"merchant": "munim"}),
        Step("Tap Accept",
             _event("advance_accept", lambda s: {"advance_id": _advance(s).id}),
             what="Partner NBFC pays ₹5,000 straight to Sharma Traders. The shop pays the other ₹10,000 on Friday.",
             who="The merchant decides. Code moves the advance to “repaying” and switches on the 20% split.",
             why="The money goes to the supplier, so it cannot be diverted.",
             kind="merchant", presenter=True,
             done=lambda s: (a := _advance(s)) is not None and a.state != "offered",
             ui={"merchant": "advance"}),
    ]),
    Beat(5, "Salary day", "Salary lands, dues clear themselves, and 20% of each repayment goes to the lender.", [
        Step("Six days pass, to Sunday 1 November", _event("advance_day", {"days": 6}),
             what="Salary day: auto-pay collects ₹10,000 from 4 customers, including Ramesh's ₹1,900. "
                  "Ramesh's score 665 → 672; he owes nothing.",
             who="Code · mandate executor and split router: ₹2,000 (20%) goes to Partner NBFC automatically.",
             why="Dues clear themselves, and the advance repays itself.",
             ui={"merchant": "home", "customer": "home"}),
    ]),
    Beat(6, "Fraud ring", "Fake udhaar to farm loans? Blocked by graph rules before any money moves.", [
        Step("Sai Kirana records four fake customers", _event("inject_fraud_ring", {"store_id": "S2"}),
             what="Another shop invents 4 customers, confirms ₹2,000 for each from one phone within seconds, "
                  "and cycles money back to fake on-time repayments.",
             who="Code · graph rules: shared device, round amounts, instant confirms, money cycle → risk 1.0. "
                 "The entries are excluded and the shop's advance is blocked.",
             why="Lenders can trust verified udhaar because fakes are caught. See the Overview risk console.",
             ui={"merchant": "home"}),
    ]),
]
TOTAL = len(BEATS)


# ---------------------------------------------------------------- state

def _explain(beat: Beat, i: int) -> dict:
    st = beat.steps[i]
    return {"beat": beat.n, "step": i, "label": st.label, "what": st.what, "who": st.who, "why": st.why,
            "kind": st.kind}


def _position(s: Session) -> tuple[int, int]:
    return state.get(s, "demo_beat"), state.get(s, "demo_step")


@before_commit
def _complete_steps_done_on_screen(uow) -> None:
    """After any event: if the presenter just did the next step themselves, mark it complete and
    show its explanation, so the panel always explains what just happened."""
    s = uow.s
    beat_n, step = _position(s)
    steps = BEATS[beat_n].steps
    while step < len(steps) and steps[step].done is not None and steps[step].done(s):
        state.put(s, "demo_last", _explain(BEATS[beat_n], step))
        step += 1
    if step != state.get(s, "demo_step"):
        state.put(s, "demo_step", step)


def status(s: Session) -> dict:
    beat_n, step = _position(s)
    beat = BEATS[beat_n]
    if step >= len(beat.steps):  # beat finished: the next press starts the next beat
        nb = BEATS[beat_n + 1] if beat_n + 1 < TOTAL else None
        nxt = ({"beat": nb.n, "title": nb.title, "label": nb.steps[0].label, "presenter": nb.steps[0].presenter,
                "ui": nb.steps[0].ui} if nb else None)
    else:
        st = beat.steps[step]
        nxt = {"beat": beat.n, "title": beat.title, "label": st.label, "presenter": st.presenter, "ui": st.ui}
    return {"beat": beat.n, "total": TOTAL, "title": beat.title, "caption": state.get(s, "demo_caption"),
            "step": step, "steps": len(beat.steps), "next": nxt, "last": state.get(s, "demo_last"),
            "done": nxt is None}


# ---------------------------------------------------------------- runner

async def _set(**kv) -> None:
    async with unit_of_work() as uow:
        for k, v in kv.items():
            state.put(uow.s, "demo_" + k, v)
        if "caption" in kv:
            uow.effects.append(caption_effect(kv["caption"]))


async def reset() -> dict:
    """Rebuild the world and compose the morning briefing through Munim (beat 0 is ready, not played)."""
    async with unit_of_work() as uow:
        stats = seed()  # rebuilds tables in its own transaction and resets the clock
        await munim.compose_briefing(uow.s, "S1")
        for k, v in {"beat": 0, "step": 0, "last": None, "caption": BEATS[0].caption}.items():
            state.put(uow.s, "demo_" + k, v)
        uow.effects.append(caption_effect(BEATS[0].caption))
    return stats


async def next_step(fast: bool = False) -> dict:
    """One press of Next. At the end of a beat it only enters the next beat (caption and what comes
    next, nothing runs), so the presenter can introduce it. Otherwise it runs exactly one step."""
    with db.session() as s:
        beat_n, step = _position(s)
    beat = BEATS[beat_n]
    if step >= len(beat.steps):
        if beat_n + 1 < TOTAL:
            nb = BEATS[beat_n + 1]
            await _set(beat=nb.n, step=0, caption=nb.caption, last=None)
        with db.session() as s:
            return status(s)
    st = beat.steps[step]
    if not (st.done and _read(st.done)):  # never repeat something already done on screen
        await st.run()
        if st.pause_after and not fast:
            await asyncio.sleep(st.pause_after)
    with db.session() as s:
        moved = _position(s) != (beat_n, step)  # the before_commit hook may already have advanced it
    if not moved:
        await _set(step=step + 1, last=_explain(beat, step))
    with db.session() as s:
        return status(s)


async def run_beat(fast: bool = False) -> dict:
    """Run the rest of the current beat, or enter and run the whole next one, without stopping."""
    with db.session() as s:
        out = status(s)
    if out["step"] >= out["steps"]:
        if out["done"]:
            return out
        out = await next_step(fast)
    while out["step"] < out["steps"]:
        out = await next_step(fast)
    return out


async def goto(n: int) -> dict:
    """Reset, then play beats 0..n-1 completely: the next press of Next enters beat n."""
    n = max(0, min(n, TOTAL - 1))
    await reset()
    with db.session() as s:
        out = status(s)
    for _ in range(n):
        out = await run_beat(fast=True)
    return out


def script() -> list[dict]:
    return [{"beat": b.n, "title": b.title, "caption": b.caption,
             "steps": [{"label": st.label, "presenter": st.presenter, "kind": st.kind, "what": st.what,
                        "who": st.who, "why": st.why} for st in b.steps]} for b in BEATS]
