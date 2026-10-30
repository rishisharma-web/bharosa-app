"""Deterministic merchant/Soundbox message templates (spec 7.3).

`display` is the English line on the Soundbox top display and merchant app.
`spoken` is the line sent to TTS in the store language. The LLM may later rephrase
these (cached); the numbers always come from here.
VERIFY: Kannada phrasing with a native speaker before the finals.
"""
from app.core.money import inr
from app.core.risk import RiskResult


def first_name(full: str) -> str:
    return full.split()[0]


def guardrail(r: RiskResult, customer_name: str, lang: str) -> dict:
    name = first_name(customer_name)
    f = r.features
    od, d, owed = f["overdue_amount"], f["max_overdue_days"], f["owed"]
    if r.band == "green":
        display = f"Safe. {name} can take {inr(r.amount)} on credit."
        spoken = {
            "hi-IN": f"सुरक्षित। {name} को {inr(r.amount)} उधार दे सकते हैं।",
            "kn-IN": f"ಸುರಕ್ಷಿತ. {name} ಅವರಿಗೆ {inr(r.amount)} ಸಾಲ ಕೊಡಬಹುದು.",
        }
    elif r.band == "amber":
        why_en = f"{inr(od)} overdue for {d} days" if d else f"already owes {inr(owed)}"
        why_hi = f"{inr(od)} {d} दिन से बाकी है" if d else f"पहले से {inr(owed)} बाकी है"
        why_kn = f"{inr(od)} {d} ದಿನಗಳಿಂದ ಬಾಕಿ ಇದೆ" if d else f"ಈಗಾಗಲೇ {inr(owed)} ಬಾಕಿ ಇದೆ"
        display = (f"Caution: {why_en}. Safe limit today {inr(r.safe_limit)}. "
                   f"Give {inr(r.credit_now)} on credit, collect {inr(r.collect_now)} now (UPI or cash).")
        spoken = {
            "hi-IN": (f"सावधान। {why_hi}। आज की सुरक्षित सीमा {inr(r.safe_limit)}। "
                      f"{inr(r.credit_now)} उधार दें, {inr(r.collect_now)} अभी लें।"),
            "kn-IN": (f"ಎಚ್ಚರಿಕೆ. {why_kn}. ಇಂದಿನ ಸುರಕ್ಷಿತ ಮಿತಿ {inr(r.safe_limit)}. "
                      f"{inr(r.credit_now)} ಸಾಲ ಕೊಡಿ, {inr(r.collect_now)} ಈಗ ಪಡೆಯಿರಿ."),
        }
    else:
        why_en = f"{inr(od)} overdue for {d} days" if d else f"already owes {inr(owed)}"
        why_hi = f"{inr(od)} {d} दिन से बाकी है" if d else f"पहले से {inr(owed)} बाकी है"
        why_kn = f"{inr(od)} {d} ದಿನಗಳಿಂದ ಬಾಕಿ ಇದೆ" if d else f"ಈಗಾಗಲೇ {inr(owed)} ಬಾಕಿ ಇದೆ"
        display = f"High risk: {why_en}. Suggest collecting full payment."
        spoken = {
            "hi-IN": f"जोखिम ज़्यादा है। {why_hi}। पूरा पेमेंट अभी लेने की सलाह है।",
            "kn-IN": f"ಹೆಚ್ಚಿನ ಅಪಾಯ. {why_kn}. ಪೂರ್ಣ ಹಣ ಈಗ ಪಡೆಯಿರಿ.",
        }
    return {"display": display, "spoken": spoken.get(lang, spoken["hi-IN"])}


def confirmed(customer_name: str, amount: int) -> str:
    return f"{first_name(customer_name)} confirmed {inr(amount)} udhaar ✓"


def received(amount: int, customer_name: str | None, lang: str, cash: bool = False) -> dict:
    """Payment alert: Soundbox line + spoken text."""

    who = first_name(customer_name) if customer_name else None
    kind = " cash" if cash else ""
    display = f"{inr(amount)}{kind} received" + (f" from {who}" if who else "")
    spoken = {
        "hi-IN": (f"{who} से " if who else "") + f"{inr(amount)}" + (" नकद" if cash else "") + " प्राप्त हुए।",
        "kn-IN": (f"{who} ಅವರಿಂದ " if who else "") + f"{inr(amount)}" + (" ನಗದು" if cash else "") + " ಸ್ವೀಕರಿಸಲಾಗಿದೆ.",
    }
    return {"display": display, "spoken": spoken.get(lang, spoken["hi-IN"])}
