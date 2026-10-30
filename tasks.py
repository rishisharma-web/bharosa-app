"""Cross-platform task runner (Windows has no `make`).

    python tasks.py seed       rebuild bharosa.db from the seed
    python tasks.py run        start the server on http://localhost:8000
    python tasks.py test       run the test suite
    python tasks.py snapshot   write fixtures/snapshots/beat_0.json (sample data for the UI)
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def seed():
    from app.sim.seed import seed as do_seed

    print(do_seed())


def run():
    subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000", "--reload"], cwd=ROOT)


def test():
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))


def snapshot():
    """Sample snapshots for frontend work, captured after running real events."""
    import asyncio

    from app import clock, db
    from app.events import handlers  # noqa: F401  (registers handlers)
    from app.events.router import fire
    from app.realtime.snapshot import build_snapshot
    from app.sim.seed import seed as do_seed

    out_dir = ROOT / "fixtures" / "snapshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    def dump(name: str) -> dict:
        with db.session() as s:
            snap = build_snapshot(s)
        (out_dir / f"{name}.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote fixtures/snapshots/{name}.json")
        return snap

    async def steps():
        do_seed()
        with db.session() as s:
            clock.load(s)
        dump("beat_0")
        await fire("udhaar_spoken", {"store_id": "S1", "customer_id": "C_PRIYA", "amount": 340})
        await fire("udhaar_spoken", {"store_id": "S1", "customer_id": "C_RAMESH", "amount": 340})
        snap = dump("beat_1_guardrail_amber")
        front = snap["soundbox"]["front"]
        await fire("upi_payment", {"store_id": "S1", "payer_vpa": "ramesh.k@ptyes", "payer_name": "Ramesh Kumar",
                                   "amount": 140, "ref": front["sale_ref"]})
        await fire("customer_confirm", {"token": front["token"], "device_id": "dev-ramesh"})
        dump("beat_2_confirmed")
        await fire("mandate_created", {"customer_id": "C_RAMESH", "store_id": "S1", "cap": 3000,
                                       "window_start_day": 1, "window_end_day": 5})
        dump("beat_3_mandate")
        await fire("offer_advance", {"store_id": "S1", "bill_id": "B1"})
        snap = dump("beat_4_offer")
        await fire("advance_accept", {"advance_id": snap["merchant"]["advance"]["id"]})
        dump("beat_4_advance_repaying")
        await fire("advance_day", {"days": 6})
        dump("beat_5_salary_day")
        await fire("inject_fraud_ring", {"store_id": "S2"})
        dump("beat_6_fraud_ring")

        do_seed()
        with db.session() as s:
            clock.load(s)
        await fire("upi_payment", {"store_id": "S1", "payer_vpa": "9876500000@ptyes", "payer_name": "Kamala Kumar",
                                   "amount": 500, "remark": "Ramesh ka udhaar"})
        dump("sample_pending_match")

    asyncio.run(steps())


if __name__ == "__main__":
    tasks = {"seed": seed, "run": run, "test": test, "snapshot": snapshot}
    if len(sys.argv) != 2 or sys.argv[1] not in tasks:
        print(__doc__)
        sys.exit(1)
    tasks[sys.argv[1]]()
