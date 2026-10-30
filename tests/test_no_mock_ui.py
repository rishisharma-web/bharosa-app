"""No hard-coded names, amounts or statuses in frontend code (spec §10.1, §14). Same check as
test_no_mock_ui.sh, in Python so it runs on Windows too: only static/overview/ may match."""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
PATTERN = re.compile(r"₹ ?[0-9]|Ramesh|Priya|Vikram|Anita|Lakshmi|Sharma")


def test_frontend_has_no_mock_data():
    hits = []
    for f in list(STATIC.rglob("*.js")) + list(STATIC.rglob("*.html")):
        if PATTERN.search(f.read_text(encoding="utf-8", errors="ignore")):
            hits.append(f.relative_to(STATIC).as_posix())
    assert all(h.startswith("overview/") for h in hits), hits


def test_no_mock_files():
    assert not [f for f in STATIC.rglob("*") if re.match(r"(mock|fake|sample|dummy)", f.name, re.I)]
