"""Pydantic payloads for every event type (spec section 9).

Payloads forbid unknown fields so a typo in the UI or demo script fails loudly (422)
instead of being silently ignored.
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Amount = Field(ge=1, le=50_000)
Lang = Literal["hi-IN", "kn-IN", "en-IN"]


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UdhaarSpoken(_P):
    store_id: str
    text: Optional[str] = None
    customer_id: Optional[str] = None
    amount: Optional[int] = Amount
    lang: Optional[Lang] = None

    @model_validator(mode="after")
    def _text_or_intent(self):
        if not self.text and not (self.customer_id and self.amount):
            raise ValueError("provide either text, or customer_id and amount")
        return self


class GuardrailOverride(_P):
    entry_id: int


class CustomerConfirm(_P):
    token: str
    device_id: str
    consents: Optional[dict[str, bool]] = None


class CustomerDispute(_P):
    token: str
    reason: str
    claimed_amount: Optional[int] = Field(default=None, ge=0, le=50_000)


class EntryCorrected(_P):
    entry_id: int
    amount: int = Amount


class NewCustomer(_P):
    store_id: str
    name: str = Field(min_length=1, max_length=60)
    mobile: str = Field(pattern=r"^[6-9]\d{9}$")
    amount: Optional[int] = Amount  # optional pending udhaar to raise right after creation


class UpiPayment(_P):
    store_id: str
    payer_vpa: str
    payer_name: Optional[str] = None
    amount: int = Amount
    remark: Optional[str] = None
    ref: Optional[str] = None


class CashReported(_P):
    store_id: str
    text: Optional[str] = None
    customer_id: Optional[str] = None
    amount: Optional[int] = Amount

    @model_validator(mode="after")
    def _text_or_intent(self):
        if not self.text and not (self.customer_id and self.amount):
            raise ValueError("provide either text, or customer_id and amount")
        return self


class MatchResolved(_P):
    pending_id: int
    customer_id: Optional[str] = None  # None = "not a repayment, record as sale"


class NudgesRequested(_P):
    store_id: str
    customer_ids: Optional[list[str]] = None


class NudgesApproved(_P):
    message_ids: list[int] = Field(min_length=1)


class CustomerReply(_P):
    customer_id: str
    store_id: str
    text: str = Field(min_length=1, max_length=500)


class MandateCreated(_P):
    customer_id: str
    store_id: str
    cap: int = Field(ge=100, le=50_000)
    window_start_day: int = Field(ge=1, le=28)
    window_end_day: int = Field(ge=1, le=28)

    @model_validator(mode="after")
    def _window(self):
        if self.window_end_day < self.window_start_day:
            raise ValueError("window_end_day must be >= window_start_day")
        return self


class SalaryCredited(_P):
    customer_id: str


class BillAdded(_P):
    store_id: str
    distributor: str
    amount: int = Field(ge=1, le=1_000_000)
    due_date: date


class OfferAdvance(_P):
    store_id: str
    bill_id: str


class AdvanceId(_P):
    advance_id: str


class AdvanceDay(_P):
    days: int = Field(default=1, ge=1, le=31)


class InjectFraudRing(_P):
    store_id: str = "S2"


class SetLanguage(_P):
    lang: Literal["hi-IN", "kn-IN"]


class SetFocusCustomer(_P):
    customer_id: str


SCHEMAS: dict[str, type[BaseModel]] = {
    "udhaar_spoken": UdhaarSpoken,
    "guardrail_override": GuardrailOverride,
    "customer_confirm": CustomerConfirm,
    "customer_dispute": CustomerDispute,
    "entry_corrected": EntryCorrected,
    "new_customer": NewCustomer,
    "upi_payment": UpiPayment,
    "cash_reported": CashReported,
    "match_resolved": MatchResolved,
    "nudges_requested": NudgesRequested,
    "nudges_approved": NudgesApproved,
    "customer_reply": CustomerReply,
    "mandate_created": MandateCreated,
    "salary_credited": SalaryCredited,
    "bill_added": BillAdded,
    "offer_advance": OfferAdvance,
    "advance_accept": AdvanceId,
    "advance_decline": AdvanceId,
    "advance_day": AdvanceDay,
    "inject_fraud_ring": InjectFraudRing,
    "set_language": SetLanguage,
    "set_focus_customer": SetFocusCustomer,
}

# UI-only events: they do not move the sim clock, so presenter clicks never change timings.
NO_TICK = {"set_language", "set_focus_customer", "advance_day"}
