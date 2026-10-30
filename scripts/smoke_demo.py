"""Run Demo Mode beats 0–6 headless and assert the contract numbers (spec 13, M7).

    python scripts/smoke_demo.py                       # in-process, throwaway database
    python scripts/smoke_demo.py --url http://localhost:8000   # against a running server (resets it!)

Exit code 0 = demo is safe to present.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check_beats(get: Callable[[str], dict], post: Callable[[str], dict], say=print) -> None:
    def snap():
        return get("/api/snapshot")

    def nxt():
        return post("/api/demo/next?fast=true")

    def ok(cond: bool, what: str):
        if not cond:
            raise AssertionError(what)
        say(f"  ✓ {what}")

    say("Beat 0 · Morning")
    post("/api/demo/reset")
    s = snap()
    ok(s["merchant"]["briefing"] is not None, "briefing ready")
    ok(s["merchant"]["due_soon"][0]["gap"] == 9_200, "Sharma Traders ₹18,000 · ₹9,200 short")
    ok(s["merchant"]["udhaar"]["outstanding"] == 45_000, "outstanding ₹45,000")

    say("Beat 1 · Guardrail")
    r = nxt()
    top = snap()["soundbox"]["top"]
    ok(r["beat"] == 1 and r["awaiting"] is None, "beat 1 ran")
    ok((top["customer_id"], top["band"], top["credit_now"], top["collect_now"]) == ("C_RAMESH", "amber", 200, 140),
       "Ramesh amber: ₹200 credit, ₹140 now")

    say("Beat 2 · Confirm")
    r = nxt()
    ok(r["awaiting"] is not None and snap()["demo"]["awaiting"] == r["awaiting"], "waits for the presenter's scan")
    nxt()
    s = snap()
    ok(s["customer"]["pending_confirms"] == [], "entry confirmed")
    ok(s["customer"]["dues"][0]["amount"] == 2_000, "Ramesh owes ₹2,000 (the ₹140 was a sale)")

    say("Beat 3 · Recovery")
    r = nxt()
    ok(r["awaiting"] is not None, "waits for Ramesh to tap auto-pay")
    t = snap()["merchant"]["threads"][0]
    ok(t["promise"] and (t["promise"]["amount"], t["promise"]["date"]) == (2_000, "2026-11-01"),
       "reply → promise ₹2,000 on 1 Nov")
    nxt()
    s = snap()
    ok(s["customer"]["mandates"][0]["status"] == "active" and s["customer"]["score"] == 685, "auto-pay active, score 685")

    say("Beat 4 · Supplier Advance")
    r = nxt()
    ok("₹9,200" in snap()["merchant"]["munim_last"]["answer"], "Munim: ₹9,200 short, advance offered")
    nxt()
    a = snap()["merchant"]["advance"]
    ok((a["state"], a["amount"], a["fee"], a["total_due"]) == ("repaying", 9_200, 138, 9_338),
       "Partner NBFC paid ₹9,200 to Sharma Traders; repaying ₹9,338")

    say("Beat 5 · Salary day")
    nxt()
    s = snap()
    ok(s["now"].startswith("2026-11-01"), "Sun 1 Nov")
    ok(s["customer"]["dues"] == [] and s["customer"]["score"] == 692, "Ramesh auto-paid, score 680 → 692")
    ok(s["merchant"]["advance"]["repaid"] == 2_200, "₹2,200 repaid to the lender via 20% splits")

    say("Beat 6 · Fraud ring")
    nxt()
    [al] = snap()["risk_console"]["alerts"]
    ok((al["store"], al["rules"], al["risk"], al["advance_blocked"]) == ("Sai Kirana", ["R1", "R3", "R4", "R5"], 1.0, True),
       "Sai Kirana flagged R1 R3 R4 R5, advance blocked")
    ok(nxt().get("done") is True, "script complete")

    say("Rehearsal · goto 4")
    r = post("/api/demo/goto/4")
    ok(r["beat"] == 4 and snap()["merchant"]["advance"]["state"] == "repaying", "goto(4) lands after the advance")
    post("/api/demo/reset")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="base URL of a running server (it will be reset)")
    args = ap.parse_args()
    try:
        if args.url:
            import httpx
            c = httpx.Client(base_url=args.url, timeout=60)
            check_beats(lambda p: _ok(c.get(p)), lambda p: _ok(c.post(p)))
        else:
            os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp(prefix="bharosa-smoke-")) / "smoke.db")
            os.environ.setdefault("LLM_MODE", "replay")
            from fastapi.testclient import TestClient

            from app.main import app
            with TestClient(app) as c:
                check_beats(lambda p: _ok(c.get(p)), lambda p: _ok(c.post(p)))
    except AssertionError as e:
        print(f"  ✗ {e}\nSMOKE FAILED")
        return 1
    print("SMOKE OK: demo beats 0–6 produce the contract numbers")
    return 0


def _ok(r) -> dict:
    if r.status_code >= 400:
        raise AssertionError(f"{r.request.method} {r.request.url.path} → {r.status_code}: {r.text[:200]}")
    return r.json()


if __name__ == "__main__":
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
