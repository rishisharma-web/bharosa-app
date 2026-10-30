"""SQLModel tables (spec section 8).

Conventions
- Money is integer rupees.
- Datetimes are naive and mean IST wall-clock time from the sim clock; the API
  serialises them as ISO strings with +05:30.
- An entry is a *verified receivable* iff `verified_at` is set. `state` tracks
  payment progress, so a partly paid entry that was never confirmed keeps
  `verified_at = None` and must never count as verified.
"""
from datetime import date
from typing import Any, Optional

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _json(default: Any = None):
    return Field(default_factory=(lambda: None) if default is None else default, sa_column=Column(JSON))


class Store(SQLModel, table=True):
    __tablename__ = "stores"
    id: str = Field(primary_key=True)
    name: str
    area: str
    vpa: str
    lang: str = "hi-IN"
    starter_limit: int = 500
    due_days: int = 30
    cash_on_hand: int = 0
    daily_net_cash: int = 0
    avg_daily_upi_sales: int = 0
    advance_blocked: bool = False


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    id: str = Field(primary_key=True)
    name: str
    aliases: list = _json(list)
    mobile: Optional[str] = None
    vpa: Optional[str] = Field(default=None, index=True)
    device_id: Optional[str] = None
    persona: Optional[str] = None
    score: int = 600
    is_new: bool = False
    lang: str = "hi-IN"
    created_at: NaiveDatetime


class StoreCustomer(SQLModel, table=True):
    __tablename__ = "store_customers"
    store_id: str = Field(foreign_key="stores.id", primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", primary_key=True)
    credit_balance: int = 0
    last_nudge_at: Optional[NaiveDatetime] = None


class Entry(SQLModel, table=True):
    __tablename__ = "entries"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    amount: int
    requested_amount: Optional[int] = None  # what the shopkeeper asked for before the guardrail split
    paid_amount: int = 0
    state: str = Field(index=True)  # proposed|verified|partly_paid|settled|disputed|unverified|defaulted
    created_at: NaiveDatetime
    due_date: date
    verified_at: Optional[NaiveDatetime] = None
    confirm_device_id: Optional[str] = None
    confirm_token: Optional[str] = Field(default=None, index=True)
    token_expires_at: Optional[NaiveDatetime] = None
    settled_at: Optional[NaiveDatetime] = None
    override: bool = False
    integrity_flag: bool = False
    dispute_reason: Optional[str] = None
    dispute_amount: Optional[int] = None
    disputed_from_amount: Optional[int] = None  # amount at the time of the (last) dispute
    source_text: Optional[str] = None


class Repayment(SQLModel, table=True):
    __tablename__ = "repayments"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: Optional[str] = Field(default=None, foreign_key="customers.id", index=True)
    amount: int
    source: str  # upi | cash | mandate
    payer_vpa: Optional[str] = None
    payer_name: Optional[str] = None
    remark: Optional[str] = None
    ref: Optional[str] = None
    matched_by: Optional[str] = None  # rule | rule_amount | agent | human | mandate | merchant
    match_confidence: Optional[float] = None
    allocated: int = 0  # part applied to entries; the rest went to credit balance
    lender_share: int = 0
    merchant_share: int = 0
    created_at: NaiveDatetime


class Allocation(SQLModel, table=True):
    __tablename__ = "allocations"
    id: Optional[int] = Field(default=None, primary_key=True)
    repayment_id: int = Field(foreign_key="repayments.id", index=True)
    entry_id: int = Field(foreign_key="entries.id", index=True)
    amount: int


class Sale(SQLModel, table=True):
    """Money received that is NOT an udhaar repayment (walk-in UPI, the 'pay ₹140 now' QR)."""

    __tablename__ = "sales"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: Optional[str] = Field(default=None, foreign_key="customers.id")
    amount: int
    source: str = "upi"  # upi | cash
    payer_vpa: Optional[str] = None
    ref: Optional[str] = None
    note: Optional[str] = None
    created_at: NaiveDatetime


class PendingMatch(SQLModel, table=True):
    __tablename__ = "pending_matches"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    payment: dict = _json(dict)  # the original upi_payment payload; no repayment row exists until resolved
    candidates: list = _json(list)
    agent_output: Optional[dict] = _json()
    created_at: NaiveDatetime
    resolved: bool = False
    resolved_customer_id: Optional[str] = None


class Consent(SQLModel, table=True):
    __tablename__ = "consents"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    store_id: Optional[str] = Field(default=None, foreign_key="stores.id")
    type: str  # data_share | payment_mandate
    granted_at: NaiveDatetime
    revoked_at: Optional[NaiveDatetime] = None


class Mandate(SQLModel, table=True):
    __tablename__ = "mandates"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    cap: int
    window_start_day: int = 1
    window_end_day: int = 5
    status: str = "active"  # active | paused | revoked
    created_at: NaiveDatetime


class Promise(SQLModel, table=True):
    __tablename__ = "promises"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id")
    store_id: str = Field(foreign_key="stores.id")
    amount: int
    date: date
    status: str = "open"  # open | kept | broken
    created_at: NaiveDatetime


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    direction: str  # out | in
    text: str
    lang: str = "hi-IN"
    status: str  # draft | approved | sent | received
    agent_output: Optional[dict] = _json()
    created_at: NaiveDatetime


class Bill(SQLModel, table=True):
    __tablename__ = "bills"
    id: str = Field(primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    distributor: str
    amount: int
    due_date: date
    status: str = "due"  # due | paid
    paid_by_lender: int = 0
    paid_by_store: int = 0


class Advance(SQLModel, table=True):
    __tablename__ = "advances"
    id: str = Field(primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    bill_id: str = Field(foreign_key="bills.id")
    lender: str
    amount: int
    fee: int
    total_due: int
    repaid: int = 0
    split_rate: float
    state: str  # offered | accepted | disbursed | repaying | closed | backstop_due | declined
    backstop_date: Optional[date] = None
    created_at: NaiveDatetime
    accepted_at: Optional[NaiveDatetime] = None


class P2PTransfer(SQLModel, table=True):
    """Peer-to-peer UPI transfers seen by the (simulated) UPI adapter; input to integrity rules."""

    __tablename__ = "p2p_transfers"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    from_id: str  # store id or customer id
    to_id: str
    amount: int
    created_at: NaiveDatetime


class RiskAlert(SQLModel, table=True):
    __tablename__ = "risk_alerts"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    rules: list = _json(list)
    risk: float
    entry_ids: list = _json(list)
    created_at: NaiveDatetime


class ScoreEvent(SQLModel, table=True):
    """Audit trail of Bharosa Score changes (feeds 'recent changes' and score_delta_7d)."""

    __tablename__ = "score_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    store_id: Optional[str] = None
    delta: int
    score_after: int
    reason: str
    ref: Optional[str] = None  # e.g. "entry:12" — used to make one-off deltas idempotent
    created_at: NaiveDatetime


class Event(SQLModel, table=True):
    __tablename__ = "events"
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: NaiveDatetime
    type: str
    payload: dict = _json(dict)
    parent_id: Optional[int] = None


class Trace(SQLModel, table=True):
    __tablename__ = "trace"
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: NaiveDatetime
    node: str
    label: str
    detail: Optional[Any] = _json()
    ms: Optional[float] = None
    source: Optional[str] = None


class SimState(SQLModel, table=True):
    __tablename__ = "sim_state"
    key: str = Field(primary_key=True)
    value: Any = _json()
