"""Morning briefing (spec 5.6). The numbers come from a deterministic summary; the Munim
Agent may only rephrase them (added with the agents milestone). This template is the fallback.
VERIFY: Kannada phrasing with a native speaker.
"""
from datetime import date, timedelta

from sqlmodel import Session, select

from app import clock, state
from app.core import forecast, ledger
from app.core.money import inr
from app.models import Bill, Sale, Store
from app.realtime.trace import trace

WEEKDAY = {
    "en-IN": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "hi-IN": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "kn-IN": ["ಸೋಮವಾರ", "ಮಂಗಳವಾರ", "ಬುಧವಾರ", "ಗುರುವಾರ", "ಶುಕ್ರವಾರ", "ಶನಿವಾರ", "ಭಾನುವಾರ"],
}


def summary(s: Session, store_id: str) -> dict:
    today = clock.today()
    y0, y1 = clock.datetime_floor(today - timedelta(days=1)), clock.datetime_floor(today)
    yesterday_sales = sum(s.exec(select(Sale.amount).where(Sale.store_id == store_id, Sale.created_at >= y0,
                                                           Sale.created_at < y1)).all())
    fc = forecast.forecast(s, store_id)
    week_end = today + timedelta(days=6)
    collectable = sum(c["amount"] for c in fc["collections"] if date.fromisoformat(c["date"]) <= week_end)
    per = ledger.totals_by_customer(ledger.open_entries(s, store_id), today)
    overdue = [t for t in per.values() if t.overdue > 0]
    bills = s.exec(select(Bill).where(Bill.store_id == store_id, Bill.status != "paid",
                                      Bill.due_date <= week_end).order_by(Bill.due_date)).all()
    gaps = {g["bill_id"]: g["gap"] for g in fc["gaps"]}
    return {
        "date": today.isoformat(),
        "yesterday_sales": yesterday_sales,
        "collectable_this_week": collectable,
        "overdue_customers": len(overdue),
        "overdue_amount": sum(t.overdue for t in overdue),
        "bills_due": [{"bill_id": b.id, "distributor": b.distributor, "amount": b.amount - b.paid_by_lender - b.paid_by_store,
                       "due": b.due_date.isoformat(), "gap": gaps.get(b.id, 0)} for b in bills],
    }


def template(store_name: str, sm: dict, lang: str) -> str:
    def day(iso: str) -> str:
        return WEEKDAY[lang if lang in WEEKDAY else "en-IN"][date.fromisoformat(iso).weekday()]

    bill_lines = []
    for b in sm["bills_due"]:
        if lang == "hi-IN":
            line = f"{day(b['due'])} को {b['distributor']} को {inr(b['amount'])} देने हैं"
            bill_lines.append(line + (f", {inr(b['gap'])} कम पड़ेंगे।" if b["gap"] else "।"))
        elif lang == "kn-IN":
            line = f"{day(b['due'])} {b['distributor']} ಗೆ {inr(b['amount'])} ಕೊಡಬೇಕು"
            bill_lines.append(line + (f", {inr(b['gap'])} ಕೊರತೆ." if b["gap"] else "."))
        else:
            line = f"{b['distributor']} {inr(b['amount'])} due {day(b['due'])}"
            bill_lines.append(line + (f": {inr(b['gap'])} short." if b["gap"] else "."))
    if lang == "hi-IN":
        head = (f"सुप्रभात, {store_name}। कल की UPI बिक्री {inr(sm['yesterday_sales'])}। "
                f"इस हफ्ते {inr(sm['collectable_this_week'])} उधार वापस आने की उम्मीद। "
                f"{sm['overdue_customers']} ग्राहकों का {inr(sm['overdue_amount'])} बकाया।")
    elif lang == "kn-IN":
        head = (f"ಶುಭೋದಯ, {store_name}. ನಿನ್ನೆಯ UPI ಮಾರಾಟ {inr(sm['yesterday_sales'])}. "
                f"ಈ ವಾರ {inr(sm['collectable_this_week'])} ಸಾಲ ವಸೂಲಿ ನಿರೀಕ್ಷೆ. "
                f"{sm['overdue_customers']} ಗ್ರಾಹಕರ {inr(sm['overdue_amount'])} ಬಾಕಿ.")
    else:
        head = (f"Good morning, {store_name}. Yesterday's UPI sales {inr(sm['yesterday_sales'])}. "
                f"Udhaar collectable this week {inr(sm['collectable_this_week'])}. "
                f"{sm['overdue_customers']} customers overdue ({inr(sm['overdue_amount'])}).")
    return " ".join([head, *bill_lines])


def refresh(s: Session, store_id: str = "S1") -> dict:
    """Compute and store today's briefing (sim_state.briefing). Returns it."""
    store = s.get(Store, store_id)
    lang = state.get(s, "lang")
    sm = summary(s, store_id)
    b = {"date": sm["date"], "lang": lang, "text": template(store.name, sm, lang),
         "text_en": template(store.name, sm, "en-IN"), "summary": sm, "audio_url": None, "source": "template"}
    state.put(s, "briefing", b)
    trace("munim_agent", "Morning briefing composed", {"summary": sm}, source="template")
    return b
