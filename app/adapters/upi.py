"""UPI adapter (spec 7.12). Simulated: generates UPI deep-link strings for QR codes.

Production equivalent: Paytm UPI / Payment Gateway dynamic QR.
"""
from urllib.parse import quote

from app.models import Store


def collect_qr(store: Store, amount: int, ref: str) -> str:
    """UPI intent for 'pay ₹X now'. `tr=SALE-…` marks it as payment for the current purchase."""
    return f"upi://pay?pa={store.vpa}&pn={quote(store.name)}&am={amount}&cu=INR&tr={ref}"


def confirm_payload(token: str) -> str:
    return f"bharosa://confirm/{token}"
