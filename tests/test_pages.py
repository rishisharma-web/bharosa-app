"""Home page, presentation and app routes (spec §10.7–10.9, §14)."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_home_has_three_sections():
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    tabs = re.findall(r'class="tab" role="tab" data-pane="(\w+)"', r.text)
    assert tabs == ["demo", "overview", "presentation"]
    for pane in tabs:
        assert f'<iframe data-pane="{pane}"' in r.text


def test_every_app_url_serves():
    with TestClient(app) as c:
        for path in ("/merchant", "/customer", "/soundbox", "/demo", "/overview", "/presentation"):
            assert c.get(path).status_code == 200, path


def test_presentation_slides_and_notes():
    with TestClient(app) as c:
        html = c.get("/presentation").text
    slides = re.findall(r'<section class="slide[^"]*" data-act="(\w*)">(.*?)</section>', html, re.S)
    assert len(slides) == 18
    assert all('<aside class="notes">' in body for _, body in slides), "every slide needs speaker notes"
    acts = [a for a, _ in slides if a]
    # The pitch flows Problem → Challenge → Solution → Architecture → Risks (Solution returns once for "who benefits").
    assert acts.index("Problem") < acts.index("Challenge") < acts.index("Solution") < acts.index("Architecture") < acts.index("Risks")
    text = re.sub(r"<[^>]+>", " ", html)
    for must in ("AI layer: the agents", "Validation: the firewall", "Counter Agent", "Recovery Agent", "Growth Agent (Munim)",
                 "Why not more agents?", "Why not zero agents?", "Where each agent works along the journey", "Risks &amp; answers"):
        assert must in text, must


def test_presentation_pdfs_exist():
    for name in ("bharosa-pitch.pdf", "bharosa-pitch-notes.pdf"):
        data = (STATIC / "presentation" / name).read_bytes()
        assert data.startswith(b"%PDF") and len(re.findall(rb"/Type\s*/Page[^s]", data)) == 18, name
