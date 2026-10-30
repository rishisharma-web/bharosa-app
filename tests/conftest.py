import os
import sys
import tempfile
from pathlib import Path

import pytest

# A throwaway database and fixed settings, before anything imports the app.
_TMP = Path(tempfile.mkdtemp(prefix="bharosa-test-"))
os.environ.update({"DB_PATH": str(_TMP / "test.db"), "ADMIN_KEY": "test-admin", "SARVAM_ENABLED": "false",
                   "SARVAM_API_KEY": "", "PUBLIC_BASE_URL": "http://testserver"})
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ADMIN = {"X-Admin-Key": "test-admin"}
PHONES = {"merchant": "9000000001", "C_PRIYA": "9000000011", "C_RAMESH": "9000000012",
          "C_VIKRAM": "9000000013", "C_ANITA": "9000000014"}


def ok(r):
    assert r.status_code < 400, (r.status_code, r.text)
    return r.json()


@pytest.fixture
def world():
    """A fresh seed plus one logged-in client per role (each with its own cookie jar)."""
    from fastapi.testclient import TestClient

    from app.main import app

    clients = {}
    with TestClient(app) as sb:
        ok(sb.post("/api/admin/reset", headers=ADMIN))
        for who, phone in PHONES.items():
            c = TestClient(app)
            appname = "merchant" if who == "merchant" else "customer"
            ok(c.post("/api/auth/otp/verify", json={"phone": phone, "otp": "123456", "app": appname}))
            clients[who] = c
        clients["soundbox"] = sb
        yield clients


def counter(w, customer_id, amount, accept=True, override=False):
    sb = w["soundbox"]
    top = ok(sb.post("/api/soundbox/udhaar", json={"customer_id": customer_id, "amount": amount}))
    out = ok(sb.post("/api/soundbox/accept", json={"override": override})) if accept else None
    return top, out
