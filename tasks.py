"""Cross-platform task runner (Windows has no `make`).

    python tasks.py seed     rebuild bharosa.db from the seed
    python tasks.py run      start the server on http://localhost:8000 (open /demo)
    python tasks.py test     run the test suite
    python tasks.py smoke    one real call to Sarvam (needs SARVAM_ENABLED=true and a key in .env)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def seed():
    from app import seed as seed_mod

    print(seed_mod.build())


def run():
    subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"], cwd=ROOT)


def test():
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))


def smoke():
    sys.exit(subprocess.call([sys.executable, "scripts/sarvam_smoke.py"], cwd=ROOT))


if __name__ == "__main__":
    tasks = {"seed": seed, "run": run, "test": test, "smoke": smoke}
    if len(sys.argv) < 2 or sys.argv[1] not in tasks:
        print(__doc__)
        sys.exit(1)
    tasks[sys.argv[1]]()
