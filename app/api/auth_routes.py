"""Auth endpoints (v2 spec §7 Auth)."""
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app import auth, db

router = APIRouter(prefix="/api")


class OtpStart(BaseModel):
    phone: str
    app: Literal["merchant", "customer"]


class OtpVerify(OtpStart):
    otp: str


@router.post("/auth/otp/start")
def otp_start(body: OtpStart):
    with db.session() as s:
        auth.start_otp(s, body.phone, body.app)
    return {"ok": True}


@router.post("/auth/otp/verify")
def otp_verify(body: OtpVerify, response: Response):
    with db.session() as s:
        p = auth.verify_otp(s, body.phone, body.otp, body.app, response)
        s.commit()
    return {"role": p.role, "name": p.name}


@router.get("/auth/magic/{code}")
def magic(code: str):
    response = RedirectResponse("/customer", status_code=303)
    with db.session() as s:
        auth.use_magic(s, code, response)
        s.commit()
    return response


@router.post("/auth/logout")
def logout(app: Literal["merchant", "customer"], response: Response,
           bh_merchant: str | None = Cookie(default=None), bh_customer: str | None = Cookie(default=None)):
    with db.session() as s:
        auth.logout(s, bh_merchant if app == "merchant" else bh_customer, app, response)
        s.commit()
    return {"ok": True}


@router.get("/me/merchant")
def me_merchant(p: auth.Principal = Depends(auth.merchant)):
    return {"role": p.role, "name": p.name, "store_id": p.store_id}


@router.get("/me/customer")
def me_customer(p: auth.Principal = Depends(auth.customer)):
    return {"role": p.role, "name": p.name, "customer_id": p.customer_id}
