"""Logins and roles (v2 spec §6).

- Phone + OTP (always DEMO_OTP; nothing is sent). Login QR = one-time magic link (10 minutes).
- One cookie per app (bh_merchant, bh_customer) so one browser can be both at once.
- Admin uses the X-Admin-Key header. The Soundbox has no login and is fixed to store S1.
"""
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Cookie, Header, HTTPException, Response
from sqlmodel import Session, select

from app import db
from app.config import get_settings, now
from app.models import Customer, MagicLink, SessionRow, Store, User

COOKIES = {"merchant": "bh_merchant", "customer": "bh_customer"}
SESSION_TTL = timedelta(hours=12)
MAGIC_TTL = timedelta(minutes=10)
SOUNDBOX_STORE = "S1"


@dataclass
class Principal:
    role: str
    user_id: int
    store_id: str | None = None
    customer_id: str | None = None
    name: str = ""


def _user_for(s: Session, phone: str, app: str) -> User:
    u = s.exec(select(User).where(User.phone == phone.strip(), User.role == app)).first()
    if u is None:
        raise HTTPException(404, "This number is not registered for this app")
    return u


def start_otp(s: Session, phone: str, app: str) -> None:
    _user_for(s, phone, app)  # validates the number; no SMS in the demo


def new_session(s: Session, user: User, app: str, response: Response) -> Principal:
    token = secrets.token_urlsafe(24)
    s.add(SessionRow(token=token, user_id=user.id, app=app, expires_at=now() + SESSION_TTL))
    response.set_cookie(COOKIES[app], token, httponly=True, samesite="lax", max_age=int(SESSION_TTL.total_seconds()),
                        secure=get_settings().public_base_url.startswith("https"))
    return principal(s, user)


def verify_otp(s: Session, phone: str, otp: str, app: str, response: Response) -> Principal:
    u = _user_for(s, phone, app)
    if otp.strip() != get_settings().demo_otp:
        raise HTTPException(401, "Wrong OTP")
    return new_session(s, u, app, response)


def principal(s: Session, u: User) -> Principal:
    name = s.get(Store, u.store_id).name if u.store_id else s.get(Customer, u.customer_id).name
    return Principal(role=u.role, user_id=u.id, store_id=u.store_id, customer_id=u.customer_id, name=name)


def _from_cookie(token: str | None, app: str) -> Principal:
    if not token:
        raise HTTPException(401, "Please log in")
    with db.session() as s:
        row = s.get(SessionRow, token)
        if row is None or row.app != app or row.expires_at < now():
            raise HTTPException(401, "Please log in")
        return principal(s, s.get(User, row.user_id))


def merchant(bh_merchant: str | None = Cookie(default=None)) -> Principal:
    return _from_cookie(bh_merchant, "merchant")


def customer(bh_customer: str | None = Cookie(default=None)) -> Principal:
    return _from_cookie(bh_customer, "customer")


def admin(x_admin_key: str | None = Header(default=None)) -> None:
    if not x_admin_key or not secrets.compare_digest(x_admin_key, get_settings().admin_key):
        raise HTTPException(401, "Admin key required")


def logout(s: Session, token: str | None, app: str, response: Response) -> None:
    if token:
        row = s.get(SessionRow, token)
        if row:
            s.delete(row)
    response.delete_cookie(COOKIES[app])


def new_magic(s: Session, customer_id: str) -> str:
    c = s.get(Customer, customer_id)
    if c is None or not c.loginable:
        raise HTTPException(404, "Unknown customer")
    code = secrets.token_urlsafe(16)
    s.add(MagicLink(code=code, customer_id=customer_id, expires_at=now() + MAGIC_TTL))
    return f"{get_settings().public_base_url.rstrip('/')}/api/auth/magic/{code}"


def use_magic(s: Session, code: str, response: Response) -> Principal:
    m = s.get(MagicLink, code)
    if m is None or m.used or m.expires_at < now():
        raise HTTPException(410, "This login link has expired. Ask for a new one.")
    m.used = True
    s.add(m)
    u = s.exec(select(User).where(User.customer_id == m.customer_id)).first()
    return new_session(s, u, "customer", response)
