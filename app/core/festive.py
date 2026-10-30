"""Diwali stock plan (v2 spec §4.6), from last year's weekly sales by category.

    categories with uplift ≥ 1.3 → extra sales = baseline × (uplift − 1)
    order = round to ₹100 of extra sales × (1 − 18 % margin) × 0.8 safety factor
"""
from datetime import date
from fractions import Fraction

from sqlmodel import Session

from app.core.money import round_half_up
from app.models import FestiveProfile

MIN_UPLIFT = Fraction(13, 10)
MARGIN = Fraction(18, 100)
SAFETY = Fraction(8, 10)
LABELS = {"sweets_dryfruits": "sweets & dry fruits", "oil_ghee": "oil & ghee", "snacks": "snacks",
          "puja_items": "puja items", "staples": "staples"}


def round_to_100(x) -> int:
    return round_half_up(Fraction(x) / 100) * 100


def plan(profile: dict) -> dict:
    base, fest = profile["weekly_baseline"], profile["festive_week"]
    cats = []
    for c in base:
        uplift = Fraction(fest[c], base[c])
        if uplift >= MIN_UPLIFT:
            cats.append({"category": c, "label": LABELS.get(c, c), "uplift": float(uplift),
                         "extra_sales": int(base[c] * (uplift - 1))})
    expected_extra = sum(c["extra_sales"] for c in cats)
    order_total = round_to_100(expected_extra * (1 - MARGIN) * SAFETY)
    overall = Fraction(sum(fest.values()), sum(base.values()))
    return {
        "festival": profile["festival"], "date": profile["date"], "supplier": profile["supplier"],
        "bill_due": profile["bill_due"], "categories": cats, "expected_extra": expected_extra,
        "order_total": order_total, "overall_uplift": round(float(overall), 1),
    }


def for_store(s: Session, store_id: str) -> dict:
    return plan(s.get(FestiveProfile, store_id).profile)


def bill_due(p: dict) -> date:
    return date.fromisoformat(p["bill_due"])
