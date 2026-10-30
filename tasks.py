"""Cross-platform task runner (Windows has no `make`).

    python tasks.py seed       rebuild bharosa.db from the seed
    python tasks.py run        start the server on http://localhost:8000
    python tasks.py test       run the test suite
    python tasks.py snapshot   write fixtures/snapshots/*.json (sample data for the UI)
    python tasks.py smoke      run demo beats 0–6 headless and check the contract numbers
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
    """Sample snapshots for frontend work: one per demo beat, produced by the real demo script."""
    import asyncio
    import shutil

    from app import db
    from app.events import handlers  # noqa: F401  (registers handlers)
    from app.events.router import fire
    from app.realtime.snapshot import build_snapshot
    from app.sim import demo_script

    out_dir = ROOT / "fixtures" / "snapshots"
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)

    def dump(name: str) -> None:
        with db.session() as s:
            snap = build_snapshot(s)
        (out_dir / f"{name}.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote fixtures/snapshots/{name}.json")

    async def steps():
        await demo_script.reset()
        dump("beat_0_morning")
        for beat in demo_script.BEATS[1:]:
            await demo_script.run_beat(fast=True)
            dump(f"beat_{beat.n}_{beat.title.split()[0].lower()}")
        await demo_script.reset()
        await fire("upi_payment", {"store_id": "S1", "payer_vpa": "9876500000@ptyes", "payer_name": "Kamala Kumar",
                                   "amount": 500, "remark": "Ramesh ka udhaar"})
        dump("sample_pending_match")

    asyncio.run(steps())


def smoke():
    sys.exit(subprocess.call([sys.executable, "scripts/smoke_demo.py", *sys.argv[2:]], cwd=ROOT))


if __name__ == "__main__":
    tasks = {"seed": seed, "run": run, "test": test, "snapshot": snapshot, "smoke": smoke}
    if len(sys.argv) < 2 or sys.argv[1] not in tasks:
        print(__doc__)
        sys.exit(1)
    tasks[sys.argv[1]]()
