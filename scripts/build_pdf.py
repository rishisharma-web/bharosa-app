"""Print the pitch deck to PDF (v2 spec §10.9) with a locally installed Chrome or Edge, headless.

    python scripts/build_pdf.py        (or: python tasks.py pdf)

Serves static/ itself on a free local port (the app server need not run) and writes:
    static/presentation/bharosa-pitch.pdf         one 16:9 slide per page, to share
    static/presentation/bharosa-pitch-notes.pdf   each slide with its speaker notes, for rehearsal
"""
import functools
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "presentation"
CANDIDATES = [
    os.environ.get("BROWSER_PATH", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge"]


def browsers() -> list[str]:
    found = [c for c in CANDIDATES if c and Path(c).is_file()] + [w for n in NAMES if (w := shutil.which(n))]
    if not found:
        sys.exit("No Chrome or Edge found. Install one, or set BROWSER_PATH to its executable.")
    return list(dict.fromkeys(found))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, int]:
    # The deck links /static/..., so serve the repository root.
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def print_pdf(url: str, out: Path) -> None:
    # Some installs (Edge under group policy, for example) exit without printing, so try each browser in turn.
    out.unlink(missing_ok=True)
    for browser in browsers():
        with tempfile.TemporaryDirectory() as profile:
            subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
                            "--no-pdf-header-footer", "--virtual-time-budget=4000", f"--print-to-pdf={out}", url],
                           capture_output=True, timeout=120)
        if out.is_file() and out.stat().st_size > 10_000:
            print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB) with {Path(browser).stem}")
            return
    sys.exit(f"Printing failed: {out.name} was not written by any of {browsers()}")


def main() -> None:
    srv, port = serve()
    base = f"http://127.0.0.1:{port}/static/presentation/index.html"
    try:
        print_pdf(base + "?print", OUT / "bharosa-pitch.pdf")
        print_pdf(base + "?print&notes", OUT / "bharosa-pitch-notes.pdf")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
