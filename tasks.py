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
    from app import clock, db
    from app.realtime.snapshot import build_snapshot
    from app.sim.seed import seed as do_seed

    do_seed()
    with db.session() as s:
        clock.load(s)
        snap = build_snapshot(s)
    out = ROOT / "fixtures" / "snapshots" / "beat_0.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    tasks = {"seed": seed, "run": run, "test": test, "snapshot": snapshot}
    if len(sys.argv) != 2 or sys.argv[1] not in tasks:
        print(__doc__)
        sys.exit(1)
    tasks[sys.argv[1]]()
