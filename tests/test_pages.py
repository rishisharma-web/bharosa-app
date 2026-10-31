"""Home page, demo guide, presentation and app routes (spec §10.7–10.9, §14)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "static"
SLIDES = 16


def test_home_has_four_sections():
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    tabs = re.findall(r'class="tab" role="tab" data-pane="(\w+)"', r.text)
    assert tabs == ["guide", "demo", "overview", "presentation"]
    for pane in tabs:
        assert f'<iframe data-pane="{pane}"' in r.text


def test_every_app_url_serves():
    with TestClient(app) as c:
        for path in ("/merchant", "/customer", "/soundbox", "/demo", "/guide", "/overview", "/presentation"):
            assert c.get(path).status_code == 200, path


def test_guide_lists_every_login_and_step():
    with TestClient(app) as c:
        html = c.get("/guide").text
    for phone in ("9000000001", "9000000011", "9000000012", "9000000013", "9000000014"):
        assert phone in html, phone
    assert "123456" in html and "Log out" in html
    for step in ("Sell more, safely", "Scan-to-Confirm", "Portable Trust", "Stock up without cash",
                 "Get paid without chasing", "The monthly basket", "If something goes wrong"):
        assert step in html, step


def test_presentation_slides_and_notes():
    with TestClient(app) as c:
        html = c.get("/presentation").text
        slides = re.findall(r'<section class="slide[^"]*"[^>]*>(.*?)</section>', html, re.S)
        assert len(slides) == SLIDES
        assert all('<aside class="notes">' in body for body in slides), "every slide needs speaker notes"
        groups = list(dict.fromkeys(re.findall(r'data-group="([^"]+)"', html)))
        assert groups == ["Problem", "Solution", "How it works", "Impact", "Risks"]
        text = re.sub(r"<[^>]+>", " ", html)
        for must in ("Trust, turned", "Every kirana in India is secretly a lender.", "Trust is invisible.",
                     "Udhaar Guardrail", "Scan-to-Confirm", "Portable Trust", "Stock Advance",
                     "AI layer: 4 agents", "Validation firewall", "Counter Agent", "Recovery Agent", "Growth Agent (Munim)",
                     "Who carries which risk", "A working product, not a mock-up.", "The questions we expect, answered by design."):
            assert must in text, must
        # every screenshot the deck uses is served
        for src in set(re.findall(r'src="(/static/presentation/img/[^"]+)"', html)):
            assert c.get(src).status_code == 200, src


def test_presentation_pdfs_exist():
    for name in ("bharosa-pitch.pdf", "bharosa-pitch-notes.pdf"):
        data = (STATIC / "presentation" / name).read_bytes()
        assert data.startswith(b"%PDF") and len(re.findall(rb"/Type\s*/Page[^s]", data)) == SLIDES, name
