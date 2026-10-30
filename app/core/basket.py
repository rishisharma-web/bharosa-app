"""Monthly basket (v2 spec §4.8): items a customer buys in the first week of most months.

    cycles = purchases on days 1–7 of each of the last 3 calendar months
    items  = SKUs present in ≥ 2 cycles, quantity = median
"""
import statistics
from datetime import date, timedelta

from sqlmodel import Session, select

from app.config import now, today
from app.core import activity, risk
from app.core.money import inr
from app.errors import EventError
from app.models import BasketOffer, CatalogueItem, Customer, Entry, Store

CYCLES = 3
MIN_CYCLES = 2


def cycle_months() -> list[tuple[int, int]]:
    """The last 3 calendar months whose first week has passed (Aug, Sep, Oct on 31 Oct)."""
    t = today()
    y, m = t.year, t.month
    if t.day <= 7:  # this month's first week is still running: start from last month
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    out = []
    for _ in range(CYCLES):
        out.insert(0, (y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def predict(s: Session, store_id: str, customer_id: str) -> dict | None:
    months = cycle_months()
    cycles: list[dict[str, int]] = []
    for y, m in months:
        lo, hi = date(y, m, 1), date(y, m, 7)
        qty: dict[str, int] = {}
        for e in s.exec(select(Entry).where(Entry.store_id == store_id, Entry.customer_id == customer_id)).all():
            if e.items and lo <= e.created_at.date() <= hi:
                for it in e.items:
                    qty[it["sku"]] = qty.get(it["sku"], 0) + it["qty"]
        cycles.append(qty)
    skus = {sku for c in cycles for sku in c}
    items = []
    for sku in sorted(skus):
        present = [c[sku] for c in cycles if sku in c]
        if len(present) >= MIN_CYCLES:
            item = s.get(CatalogueItem, sku)
            q = int(statistics.median(present))
            items.append({"sku": sku, "name": item.name, "qty": q, "price": item.price})
    if not items:
        return None
    return {"items": items, "value": sum(i["qty"] * i["price"] for i in items), "cycles": len(cycles)}


def offer(s: Session, store_id: str, customer_id: str) -> BasketOffer | None:
    p = predict(s, store_id, customer_id)
    if p is None:
        return None
    limit = risk.evaluate(s, store_id, customer_id, p["value"]).safe_limit
    if p["value"] > limit:
        return None
    b = BasketOffer(customer_id=customer_id, store_id=store_id, items=p["items"], value=p["value"], created_at=now())
    s.add(b)
    s.flush()
    name = s.get(Customer, customer_id).name
    activity.log(s, store_id, "growth", f"Monthly basket offered to {name}: {len(p['items'])} items, {inr(p['value'])}")
    return b


def _get(s: Session, offer_id: int) -> BasketOffer:
    b = s.get(BasketOffer, offer_id)
    if b is None:
        raise EventError("basket offer not found", 404)
    return b


def accept(s: Session, offer_id: int, customer_id: str) -> BasketOffer:
    b = _get(s, offer_id)
    if b.customer_id != customer_id:
        raise EventError("This offer is for another customer.", 403)
    if b.state != "offered":
        raise EventError(f"This offer is already {b.state}", 409)
    store = s.get(Store, b.store_id)
    t = now()
    e = Entry(store_id=b.store_id, customer_id=customer_id, amount=b.value, state="verified", source="basket",
              created_at=t, due_date=t.date() + timedelta(days=store.due_days), items=b.items, band="green")
    s.add(e)
    s.flush()
    b.state, b.entry_id = "accepted", e.id
    s.add(b)
    activity.log(s, b.store_id, "growth", f"{s.get(Customer, customer_id).name} accepted the monthly basket "
                                          f"({inr(b.value)} on credit)")
    return b


def decline(s: Session, offer_id: int, customer_id: str) -> BasketOffer:
    b = _get(s, offer_id)
    if b.customer_id != customer_id or b.state != "offered":
        raise EventError("This offer is not open.", 409)
    b.state = "declined"
    s.add(b)
    return b


def delivered(s: Session, store_id: str, offer_id: int) -> BasketOffer:
    b = _get(s, offer_id)
    if b.store_id != store_id or b.state != "accepted":
        raise EventError("Only accepted baskets can be delivered", 409)
    b.state = "delivered"
    s.add(b)
    activity.log(s, store_id, "growth", f"Basket delivered to {s.get(Customer, b.customer_id).name}")
    return b
