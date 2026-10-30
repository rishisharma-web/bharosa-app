"""SQLModel tables (v2 spec §12). Money is integer rupees; datetimes are naive IST."""
from datetime import date
from typing import Any, Optional

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _json(default=None):
    return Field(default_factory=default or (lambda: None), sa_column=Column(JSON))


class Store(SQLModel, table=True):
    __tablename__ = "stores"
    id: str = Field(primary_key=True)
    name: str
    area: str = ""
    voice_lang: str = "kn-IN"
    starter_limit: int = 500
    due_days: int = 30
    upi_sales_today: int = 0
    cash_available_by_bill_due: int = 0
    vpa: str = ""
    is_network: bool = False  # the pseudo-store "Other Paytm shops"


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    id: str = Field(primary_key=True)
    name: str
    phone: Optional[str] = None
    vpa: Optional[str] = None
    lang: str = "en-IN"
    loginable: bool = False


class StoreCustomer(SQLModel, table=True):
    __tablename__ = "store_customers"
    store_id: str = Field(foreign_key="stores.id", primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", primary_key=True)
    credit_balance: int = 0


class Entry(SQLModel, table=True):
    __tablename__ = "entries"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    amount: int
    paid: int = 0
    state: str = Field(index=True)  # proposed|verified|partly_paid|settled|disputed|cancelled|expired|written_off
    source: str = "counter"  # counter | basket | seed
    created_at: NaiveDatetime
    due_date: date
    settled_at: Optional[NaiveDatetime] = None
    items: Optional[list] = _json()
    override: bool = False
    integrity_flag: bool = False
    dispute_reason: Optional[str] = None
    device_id: Optional[str] = None
    band: Optional[str] = None  # guardrail band at the counter (for the merchant's counter feed)
    tags: list = _json(list)  # e.g. ["New · Paytm network"]


class Payment(SQLModel, table=True):
    __tablename__ = "payments"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    amount: int
    method: str  # upi | credit_line | cash | autopay
    purpose: str  # sale | repayment
    lender_share: int = 0
    merchant_share: int = 0
    created_at: NaiveDatetime


class Allocation(SQLModel, table=True):
    __tablename__ = "allocations"
    id: Optional[int] = Field(default=None, primary_key=True)
    payment_id: int = Field(foreign_key="payments.id", index=True)
    entry_id: int = Field(foreign_key="entries.id", index=True)
    amount: int


class PendingRequest(SQLModel, table=True):
    __tablename__ = "pending_requests"
    token: str = Field(primary_key=True)
    kind: str  # confirm | share
    store_id: str = Field(foreign_key="stores.id")
    customer_id: str = Field(foreign_key="customers.id", index=True)
    amount_requested: int
    credit_now: int = 0
    collect_now: int = 0
    entry_id: Optional[int] = None
    status: str = "open"  # open | completed | declined | expired
    created_at: NaiveDatetime
    expires_at: NaiveDatetime
    next_token: Optional[str] = None  # share → the confirm request created right after


class ScoreShare(SQLModel, table=True):
    __tablename__ = "score_shares"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    store_id: str = Field(foreign_key="stores.id")
    granted_at: NaiveDatetime
    revoked_at: Optional[NaiveDatetime] = None


class Mandate(SQLModel, table=True):
    __tablename__ = "mandates"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    store_id: str = Field(foreign_key="stores.id")
    cap: int
    collection_day: int
    status: str = "active"
    created_at: NaiveDatetime


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id", index=True)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    direction: str  # out (shop → customer) | in (customer → shop)
    text: str
    lang: str = "en-IN"
    source: str = "template"  # template | ai | customer
    created_at: NaiveDatetime
    read: bool = False
    meta: Optional[dict] = _json()  # interpreted intent, buttons offered


class PromiseRow(SQLModel, table=True):
    __tablename__ = "promises"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    customer_id: str = Field(foreign_key="customers.id")
    amount: int
    date: date
    created_at: NaiveDatetime


class CatalogueItem(SQLModel, table=True):
    __tablename__ = "catalogue"
    sku: str = Field(primary_key=True)
    name: str
    category: str
    price: int


class FestiveProfile(SQLModel, table=True):
    __tablename__ = "festive_profiles"
    store_id: str = Field(foreign_key="stores.id", primary_key=True)
    profile: dict = _json(dict)


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
    state: str  # offered | repaying | closed | declined
    backstop_date: Optional[date] = None
    created_at: NaiveDatetime


class GrowthAction(SQLModel, table=True):
    __tablename__ = "growth_actions"
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="stores.id")
    action_id: str
    type: str
    facts: dict = _json(dict)
    impact: int
    rank: int
    title: str
    why: str
    state: str = "proposed"  # proposed | approved | done
    source: str = "template"
    updated_at: NaiveDatetime


class BasketOffer(SQLModel, table=True):
    __tablename__ = "basket_offers"
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: str = Field(foreign_key="customers.id")
    store_id: str = Field(foreign_key="stores.id")
    items: list = _json(list)
    value: int
    state: str = "offered"  # offered | accepted | delivered | declined
    entry_id: Optional[int] = None
    created_at: NaiveDatetime


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str  # merchant | customer
    phone: str = Field(index=True)
    store_id: Optional[str] = None
    customer_id: Optional[str] = None


class SessionRow(SQLModel, table=True):
    __tablename__ = "sessions"
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    app: str  # merchant | customer
    expires_at: NaiveDatetime


class MagicLink(SQLModel, table=True):
    __tablename__ = "magic_links"
    code: str = Field(primary_key=True)
    customer_id: str = Field(foreign_key="customers.id")
    expires_at: NaiveDatetime
    used: bool = False


class Activity(SQLModel, table=True):
    __tablename__ = "activity"
    id: Optional[int] = Field(default=None, primary_key=True)
    ts: NaiveDatetime
    store_id: Optional[str] = None
    kind: str  # guardrail | confirm | payment | advance | growth | ai | integrity | message
    text: str
    source: str = "rule"  # rule | ai | template


class SoundboxState(SQLModel, table=True):
    __tablename__ = "soundbox_state"
    store_id: str = Field(primary_key=True)
    state: Any = _json(dict)
