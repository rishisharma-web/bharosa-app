"""Simulated money adapters (spec 7.12) with production-shaped interfaces.

MandateAdapter     → UPI AutoPay (later NPCI agent mandates, proposed)
LenderAdapter      → Paytm lending partners (fictional "Partner NBFC")
DistributorAdapter → distributor B2B payments

Every call succeeds instantly unless a business rule is broken, and writes a trace line.
"""
from app.core.money import inr
from app.errors import EventError
from app.models import Advance, Bill, Mandate
from app.realtime.trace import trace

LENDER_NAME = "Partner NBFC"


class MandateAdapter:
    @staticmethod
    def create(mandate: Mandate) -> None:
        trace("mandate", f"AutoPay mandate registered: up to {inr(mandate.cap)}, "
                         f"days {mandate.window_start_day}–{mandate.window_end_day}")

    @staticmethod
    def execute(mandate: Mandate, amount: int) -> None:
        if amount > mandate.cap:
            raise EventError(f"debit {inr(amount)} exceeds the mandate cap {inr(mandate.cap)}", 409)
        trace("mandate", f"AutoPay debit {inr(amount)} executed", {"mandate_id": mandate.id, "amount": amount})


class LenderAdapter:
    @staticmethod
    def offer(store_id: str, amount: int) -> None:
        trace("lender", f"{LENDER_NAME} offer {inr(amount)} to {store_id}")

    @staticmethod
    def disburse(advance: Advance, to: str, amount: int) -> None:
        trace("lender", f"{LENDER_NAME} paid {inr(amount)} to {to} ✓", {"advance_id": advance.id})

    @staticmethod
    def repay(advance: Advance, amount: int) -> None:
        trace("lender", f"{inr(amount)} routed to {LENDER_NAME}", {"advance_id": advance.id, "repaid": advance.repaid})


class DistributorAdapter:
    @staticmethod
    def mark_paid(bill: Bill, by: str, amount: int) -> None:
        trace("distributor", f"{bill.distributor}: {inr(amount)} received from {by}", {"bill_id": bill.id})
