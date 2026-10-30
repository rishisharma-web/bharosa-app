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
    """Press Next through the whole demo (presenter steps are done by "Do it for me")."""
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
    ok(s["merchant"]["briefing"] is not None and s["merchant"]["udhaar"]["outstanding"] == 18_000,
       "briefing ready; outstanding ₹18,000")
    ok(s["merchant"]["due_soon"][0]["gap"] == 5_000, "Sharma Traders ₹15,000 · ₹5,000 short")
    ok(s["demo"]["next"]["label"] == "Play Munim's morning briefing", "first step: Munim's briefing")
    ok(nxt()["last"]["kind"] == "ai", "briefing played (code numbers, Munim wording)")

    say("Beat 1 · Guardrail")
    ok(nxt()["last"] is None, "enter beat: caption only, nothing runs")
    nxt()
    ok(snap()["soundbox"]["top"]["band"] == "green", "Priya ₹500 → green")
    nxt()
    ok(snap()["soundbox"]["top"]["band"] == "red", "Vikram ₹500 → red")
    nxt()
    top = snap()["soundbox"]["top"]
    ok((top["customer_id"], top["band"], top["credit_now"], top["collect_now"]) == ("C_RAMESH", "amber", 400, 100),
       "Ramesh ₹500 → amber: ₹400 credit, ₹100 now")
    ok(snap()["customer"]["pending_confirms"] and "notify" not in str(snap()["soundbox"]),
       "nothing pushed to Ramesh before he scans")

    say("Beat 2 · Confirm")
    nxt()
    r = nxt()
    ok(r["last"]["label"].startswith("Ramesh pays the ₹100"), "₹100 paid by UPI, recorded as a sale")
    ok(r["next"]["presenter"], "waits for the presenter: scan + Confirm")
    nxt()
    s = snap()
    ok(s["customer"]["dues"][0]["amount"] == 1_900 and s["customer"]["pending_confirms"] == [],
       "confirmed: Ramesh owes ₹1,900 (the ₹100 was a sale)")

    say("Beat 3 · Recovery")
    nxt()
    ok(any(c["kind"] == "reminders" for c in snap()["merchant"]["suggestions"]), "Munim suggests 3 reminders")
    nxt()
    ok(len(snap()["merchant"]["drafts"]) == 3, "3 reminders drafted")
    nxt()
    ok(snap()["merchant"]["drafts"] == [], "merchant approved them")
    nxt()
    t = next(x for x in snap()["merchant"]["threads"] if x["customer_id"] == "C_RAMESH")
    ok(t["promise"] and (t["promise"]["amount"], t["promise"]["date"]) == (1_900, "2026-11-01"),
       "Hinglish reply → promise ₹1,900 on 1 Nov")
    nxt()
    s = snap()
    ok(s["customer"]["mandates"][0]["status"] == "active" and s["customer"]["score"] == 665, "auto-pay on, score 665")

    say("Beat 4 · Supplier Advance")
    nxt()
    ok(any(c["kind"] == "bill" for c in snap()["merchant"]["suggestions"]), "Munim suggests: Sharma Traders, ₹5,000 short")
    nxt()
    ok("₹5,000" in snap()["merchant"]["munim_last"]["answer"], "Munim: ₹5,000 short, advance offered")
    nxt()
    a = snap()["merchant"]["advance"]
    ok((a["state"], a["amount"], a["fee"], a["total_due"]) == ("offered", 5_000, 75, 5_075), "offer ₹5,000 + ₹75 fee")
    nxt()
    ok(snap()["merchant"]["advance"]["state"] == "repaying", "accepted: Partner NBFC paid Sharma Traders ₹5,000")

    say("Beat 5 · Salary day")
    nxt()
    nxt()
    s = snap()
    ok(s["now"].startswith("2026-11-01"), "Sun 1 Nov")
    ok(s["customer"]["dues"] == [] and s["customer"]["score"] == 672, "Ramesh auto-paid, score 660 → 672")
    ok(s["merchant"]["advance"]["repaid"] == 2_000, "₹2,000 (20% of ₹10,000) repaid to the lender")

    say("Beat 6 · Fraud ring")
    nxt()
    r = nxt()
    [al] = snap()["risk_console"]["alerts"]
    ok((al["store"], al["rules"], al["risk"], al["advance_blocked"]) == ("Sai Kirana", ["R1", "R3", "R4", "R5"], 1.0, True),
       "Sai Kirana flagged R1 R3 R4 R5, advance blocked")
    ok(r["done"] is True, "script complete")

    say("Rehearsal · goto 4")
    r = post("/api/demo/goto/4")
    ok(r["beat"] == 3 and r["step"] == r["steps"] and r["next"]["beat"] == 4, "goto(4): the next press enters beat 4")
    ok(snap()["customer"]["score"] == 665, "beats 0–3 replayed")
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
