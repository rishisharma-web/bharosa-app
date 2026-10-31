# Bharosa on Paytm

**Team MerchantMavericks** · Sujay Mohanty · Sukruth N · Rishi Sharma
Paytm Build for India AI Hackathon, Bengaluru · Track 1: Merchant Growth AI

Bharosa turns udhaar (informal shop credit) from a cost into a growth engine for Paytm merchants:
**sell more, safely** (a safe credit limit; customers carry their Bharosa Score to a new shop with consent;
a predicted monthly basket), **get paid without chasing** (customers confirm credit by scanning a QR in their
own app; reminders that understand replies; compliant salary-week auto-pay) and **stock up without cash**
(a Diwali stock plan funded by a Stock Advance paid straight to the distributor, repaid from 20% of repayments).

> *AI proposes, code decides.* No AI output changes money, limits or scores without a validator.
> With AI switched off (the default) everything works on rules and templates.

The full specification is [`bharosa-arch-v2.md`](bharosa-arch-v2.md). The complete explanation (problem, production architecture,
where the agents sit and why, the pitch, tough questions) is [`bharosa-explained.md`](bharosa-explained.md). How the code
works (architecture, design choices, every engine, the AI layer, live updates, each flow end to end) is
[`bharosa-technical-deep-dive.md`](bharosa-technical-deep-dive.md).

**The pitch deck as PDF:** [`static/presentation/bharosa-pitch.pdf`](static/presentation/bharosa-pitch.pdf) (18 slides) and
[`bharosa-pitch-notes.pdf`](static/presentation/bharosa-pitch-notes.pdf) (each slide with its speaker notes, for rehearsal).

---

## 1. Run it from scratch

Needs **Python 3.11+** and Chrome or Edge. No Node, no database server.

**Windows (PowerShell)**
```powershell
cd bharosa-app
py -3.11 -m venv .venv          # any Python 3.11 or newer works, e.g. py -3.12
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # then set ADMIN_KEY in .env
.venv\Scripts\python tasks.py run
```

**macOS / Linux**
```bash
cd bharosa-app
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env            # then set ADMIN_KEY in .env
.venv/bin/python tasks.py run
```

Open **http://localhost:8000**. The database is created and seeded on first start. Exact tested versions
are in `requirements.lock.txt` if you ever need them.

`.venv` can't be copied between machines: it points at the Python install that created it. On a new machine,
delete it and run the `venv` step again.

### Secrets and `.env`

All settings, including every credential, live in **`.env`**, which you create from `.env.example`. `.env` is
git-ignored and must never be committed. `.env.example` is committed and holds only placeholders.

| Secret | Where it goes | Notes |
|---|---|---|
| `SARVAM_API_KEY` | `.env` only | Get it from the Sarvam dashboard. The code reads it in `app/config.py` and never logs it |
| `ADMIN_KEY` | `.env` only | Presenter key for Reset and login QRs. Change the default `change-me` before showing the app on a shared network |
| `PUBLIC_BASE_URL` | `.env` only | Not secret, but it's your current tunnel address, so it stays local |

`.gitignore` also keeps out the local database (`bharosa.db*`, which holds sessions and test activity), any other
`.env.*` file, certificate and key files (`*.pem`, `*.key`), cloudflared credentials, and the smoke-test audio file.

Before pushing to GitHub, check that nothing secret is staged:

```powershell
git status                      # .env and bharosa.db* must not appear
git check-ignore -v .env        # prints the .gitignore rule that excludes it
```

If a key is ever committed or shared, rotate it in the Sarvam dashboard. Deleting the file in a later commit leaves it in
the git history.

| Command | What it does |
|---|---|
| `python tasks.py run` | Start the server on port 8000 (all interfaces) |
| `python tasks.py seed` | Rebuild the database from the seed |
| `python tasks.py test` | Run the tests (51, about 15 s) |
| `python tasks.py smoke` | One real Sarvam call (only when AI is on) |
| `python tasks.py pdf` | Print the presentation to both PDFs (needs Chrome or Edge; no server needed) |

`make run|seed|test|smoke|pdf` does the same on macOS/Linux.

---

## 2. The home page and the five apps

**http://localhost:8000/** is one page with three sections (tabs at the top; `/#demo`, `/#overview`, `/#presentation`):

1. **Live Demo**: the presenter screen below. Switching tabs never resets it.
2. **Overview**: the one-page summary.
3. **Presentation**: the pitch as 18 slides: Problem → Challenge → Solution → Architecture & flow (where the agents sit
   and why) → Risks & answers. Keys: ← → / Space, **F** fullscreen, **N** speaker notes. The header has **Fullscreen**,
   **PDF** and **PDF with notes**.

| App | URL | Who | Login |
|---|---|---|---|
| Presenter screen | `/demo` | The team on stage | Admin key (asked once, kept in the browser) |
| AI Soundbox simulator | `/soundbox` | The counter (laptop) | None, fixed to Lakshmi Stores |
| Merchant app | `/merchant` | Lakshmi Stores owner | Phone `9000000001` + OTP |
| Customer app | `/customer` | Priya `…11`, Ramesh `…12`, Vikram `…13`, Anita `…14` (`90000000xx`) | Phone + OTP, or a login QR |
| Overview (one-page summary) | `/overview` | Anyone | None |
| Presentation (slides) | `/presentation` | Anyone | None |

**The OTP is always `123456`** (set by `DEMO_OTP`; no SMS is sent). The presenter screen shows one login QR per
customer; each works once and they refresh every 9 minutes. The merchant and customer apps use separate
cookies, so one browser can be logged in as both. To switch customers on one phone, tap **Log out** in the
customer app's header.

**Reset:** the **Reset** button on the presenter screen rebuilds everything in under a second.

---

## 3. The demo world (31 Oct 2026, a fixed date; no clock moves)

| Customer | Bharosa Score | At Lakshmi Stores | Asking ₹340 → |
|---|---|---|---|
| Priya | 780 Strong | nothing owed | **Green**, limit ₹4,100 |
| Ramesh | 662 Good | ₹1,700, 19 days overdue | **Amber**: ₹200 credit + ₹140 now |
| Vikram | 438 Building | ₹2,600, 41 days overdue | **Red**: collect in full |
| Anita (asks ₹2,000) | 770 Strong, from other Paytm shops | new here | ₹500 starter limit, or **₹1,500 + ₹500** if she shares her score |

Six read-only regulars owe ₹21,500, so the shop has **₹25,800** outstanding and **₹4,300** overdue.
Diwali is Sun 8 Nov: last year's Diwali week was 1.6× normal, so the plan is an **₹18,000** order from
Sharma Traders (+₹27,400 expected sales). The shop will have ₹8,800, so **₹9,200 short** → Stock Advance
**₹9,200 + ₹138 fee**, repaid from 20% of repayments.

---

## 4. Presenting (about 5 minutes of demo; the app does not enforce an order)

Open `/` full screen. Start in **Presentation** (slides 1–6: problem, challenge, solution), switch to **Live Demo** for
the steps below, then go back to **Presentation** for the architecture, the agents and the risks (slides 7–18).
Rehearse from `bharosa-pitch-notes.pdf`.

1. **Merchant** logs in → Home shows the growth plan (3 actions).
2. **Soundbox**: tap **Priya 340** (green), then **Ramesh 340** (amber) → **Use suggestion** → a QR appears.
   On Ramesh's phone: **Scan QR** → Confirm sheet → **Pay ₹140 & confirm** → the laptop updates within a second.
3. A judge scans **Anita's login QR** → Soundbox **Anita 2000** → the judge scans → **Share** → ₹1,500 credit →
   pays ₹500 by **Credit line on UPI** → confirm → merchant sees **"New · Paytm network"**.
4. Merchant approves **Stock up for Diwali** → **Accept** the Stock Advance → "Partner NBFC paid Sharma Traders ₹9,200 ✓".
5. Merchant approves **Remind 2 overdue customers** → Ramesh replies *"Salary 1 tareekh ko aati hai, tab de dunga"* →
   "Promised ₹1,900 on 1 Nov" → he taps **Set up salary-week auto-pay** → then **Pay** ₹500 → split **₹400 shop / ₹100 lender**.
6. Merchant approves the **monthly basket** → Priya accepts → merchant **Orders** → **Mark delivered**.
7. (AI on) one spoken Kannada line, and one live reply understood by the Recovery Agent.

No phone? The presenter screen's right-hand phone frame is the customer app: log it in, and clicking the
Soundbox QR opens the same request.

---

## 5. Real phones (HTTPS tunnel)

Phone cameras only work on HTTPS. Expose the laptop with a Cloudflare quick tunnel:

```powershell
winget install --id Cloudflare.cloudflared      # once (macOS: brew install cloudflared); then open a NEW terminal
cloudflared tunnel --protocol http2 --url http://127.0.0.1:8000
```

Copy the `https://….trycloudflare.com` address into `PUBLIC_BASE_URL` in `.env`, **restart the server**, and open
the presenter screen through that address. QR codes then point at the tunnel. The laptop needs internet (venue
Wi-Fi or a hotspot); phones can use mobile data. On the phone: scan the login QR (or log in by phone + OTP),
then use the app's **Scan QR** button, or the phone's own camera app.

* **`--protocol http2`**: many networks block the UDP traffic cloudflared uses by default, and the tunnel then never
  connects. HTTP/2 runs over normal HTTPS.
* **`127.0.0.1` rather than `localhost`**: `localhost` tries IPv6 first, but the server listens on IPv4.
* **The address changes every time `cloudflared` restarts.** Each time, update `PUBLIC_BASE_URL`, restart the server, and
  log in again on every device. Restarting only the server keeps the address.
* **Use the tunnel address on the laptop too.** With an `https` `PUBLIC_BASE_URL`, login cookies are HTTPS-only, so logins
  on `http://localhost:8000` won't stick.
* **Live updates through the tunnel:** a quick tunnel buffers Server-Sent Events, so pages that hear nothing on
  `/api/stream` within 4 s switch to long-polling `/api/changes`. That's why the server log shows a steady stream of
  `GET /api/changes` lines.

---

## 6. AI (Sarvam), off by default

In `.env` set `SARVAM_ENABLED=true` and `SARVAM_API_KEY=…` (never commit the key; `.env` is git-ignored), restart,
and run `python tasks.py smoke` once.

Keep `SARVAM_REASONING_EFFORT=none`. `sarvam-105b` otherwise "thinks" before answering: one Ask Munim step took 6–11 s
(once 90 s) with reasoning on and about 1.5 s with it off. Calls over 8 s fall back to templates, so with reasoning on
most AI answers show as TEMPLATE. Every AI output is validated by code either way. With AI on:

| Feature | AI off | AI on |
|---|---|---|
| Shopkeeper text | Rule parser ("Ramesh 340") | Counter Agent when the rules can't parse it |
| Mic on the Soundbox | Hidden | Sarvam speech-to-text |
| Spoken line on the Soundbox | Off | One short Kannada line per event |
| Reminders / reply reading | Templates / keyword rules | Recovery Agent (validated) |
| Growth plan wording | Templates | Growth Agent (validated; order stays code) |
| Ask Munim | "Available when AI is enabled" | Answers from read-only tools (shop summary, growth plan, stock, overdue list, every customer's dues and limit) |
| Score, limits, payments, split, advance | Code | **Code (never AI)** |

Every AI call times out after 8 s and falls back to the rule/template result; the activity log shows the source.
`VERIFY` before relying on it: the Sarvam STT model name and response fields, and a Kannada voice for `bulbul:v3`.

---

## 7. How it is built

```
app/
  main.py             FastAPI: /api/*, the five apps, /c/r/{token} (a QR request)
  config.py           .env settings (DEMO_DATE, PUBLIC_BASE_URL, DEMO_OTP, ADMIN_KEY, SARVAM_*)
  models.py  seed.py  db.py  auth.py  bus.py (one write lock + "changed" pings)  voice.py
  core/               score · risk · requests (counter + QR bridge) · payments (split) · advance · festive
                      growth · basket · mandates · messages · activity · money
  ai/sarvam.py        thin Sarvam client (chat, speech-to-text, text-to-speech)
  agents/             counter · recovery · growth_agent (rules first, AI second, validators always)
  api/                auth · soundbox · customer · merchant · voice · admin (stream, activity, reset, health)
static/
  shared/             tokens.css · base.css · api.js (fetch + SSE pings) · format.js
  merchant/ customer/ soundbox/ demo/ overview/    one Alpine.js page each
  home/               the three-section home page (/)
  presentation/       the slides (plain JS) and the two committed PDFs
  vendor/             Alpine 3.14.1 · qrcode-generator 1.4.4 · html5-qrcode 2.3.8
tests/                spec §14 contracts (score, risk, requests, split, Diwali, growth, basket, recovery, privacy, AI off, no mock UI, pages)
scripts/sarvam_smoke.py   scripts/build_pdf.py (slides → PDF with headless Chrome/Edge)
```

* **Real-time:** after every change the server sends `{"type": "changed", "scopes": ["merchant:S1", "customer:C_RAMESH", …]}`
  on `/api/stream`. No data travels in the ping; each app refetches its own view.
* **Privacy:** the merchant API never returns other shops' names, entries or amounts; a customer can only open
  their own requests; Portable Trust needs the customer's consent and can be revoked.
* **No mock data:** frontend code contains no names or amounts (`tests/test_no_mock_ui.py`).

API docs: **http://localhost:8000/docs**.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| Presenter screen asks for an admin key | Enter the `ADMIN_KEY` from `.env` (default `change-me`) |
| "This request is for another customer" | The phone is logged in as someone else: scan that customer's login QR |
| "This request has expired" | Requests last 15 minutes: tap the preset again on the Soundbox |
| Phone camera won't open | It needs HTTPS: use the tunnel (section 5), or the phone's camera app |
| QR opens `localhost` on the phone | Set `PUBLIC_BASE_URL` to the tunnel address and restart |
| Port 8000 busy | `.venv\Scripts\python -m uvicorn app.main:app --port 8001` |
| Numbers look wrong | **Reset** on the presenter screen, or `python tasks.py seed` |
| Slides changed but the PDF didn't | `python tasks.py pdf`. If Chrome/Edge isn't found, set `BROWSER_PATH` to its executable |
| A page looks stale after an update | Hard-refresh (Ctrl+Shift+R) |
| Mic button missing | It only appears with AI on |
| `cloudflared` is "not recognized" right after installing | Open a new terminal so it picks up the updated PATH |
| Tunnel log: `failed to dial a quic connection` | Start the tunnel with `--protocol http2` |
| Tunnel log: `connectex: … actively refused it` | The server isn't running: start it |
| Tunnel log: `context canceled` | Harmless: a browser closed or reloaded a page while a request was open |
| Phone says "site can't be reached" | The tunnel was restarted and has a new address: use the current one |
| Login doesn't stick on the laptop | Open the tunnel address, not `localhost`, once `PUBLIC_BASE_URL` is `https` |
| Ask Munim answers show TEMPLATE | Check `SARVAM_REASONING_EFFORT=none` and run `python tasks.py smoke` |
| Screens don't update without a refresh | Hard-refresh once so the page loads the current `api.js` |

---

## 9. Sharing as a zip

```bash
git archive --format=zip -o bharosa-app.zip HEAD
```
`git archive` only includes committed files, so `.env` and the database are left out automatically. Or zip the folder
**without** `.venv/`, `.env`, `*.db*`, `__pycache__/`, `.pytest_cache/`. The recipient follows section 1 and creates their
own `.env`.

*Concept prototype · Team MerchantMavericks. All names, shops, the lender and the distributor are fictional.*
