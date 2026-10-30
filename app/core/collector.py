"""Collector policy (spec 5.3): who gets a reminder. Deterministic; the Recovery Agent only writes it."""
from datetime import timedelta

from sqlmodel import Session, select

from app import clock
from app.core import ledger
from app.models import Customer, StoreCustomer

MIN_OVERDUE_DAYS = 7
COOLDOWN = timedelta(days=3)
MAX_PER_RUN = 10


def pick(s: Session, store_id: str, customer_ids: list[str] | None = None) -> list[tuple[Customer, ledger.Totals]]:
    """Customers whose oldest entry is ≥ 7 days overdue and who were not nudged in the last 3 days.
    An explicit list (merchant tapped specific people) still skips anyone who owes nothing or was just nudged."""
    today, now = clock.today(), clock.now()
    per = ledger.totals_by_customer(ledger.open_entries(s, store_id), today)
    ids = customer_ids if customer_ids is not None else [
        cid for cid, t in per.items() if t.oldest_overdue_days >= MIN_OVERDUE_DAYS]
    out = []
    for cid in ids:
        t = per.get(cid)
        link = s.get(StoreCustomer, (store_id, cid))
        if t is None or t.outstanding <= 0 or link is None:
            continue
        if link.last_nudge_at and now - link.last_nudge_at < COOLDOWN:
            continue
        out.append((s.get(Customer, cid), t))
    out.sort(key=lambda ct: (-ct[1].overdue, -ct[1].outstanding, ct[0].id))
    return out[:MAX_PER_RUN] if customer_ids is None else out
