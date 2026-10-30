# Bharosa on Paytm

**Team MerchantMavericks** · Paytm Build for India AI Hackathon · Track 1: Merchant Growth AI

Every kirana gives udhaar (goods on credit) with no checks, no collections and no funding. Bharosa is a
credit layer on top of Paytm's existing rails: the **Soundbox** at the counter, the **Paytm for Business**
app for the shopkeeper and the **Paytm app** for the customer.

> *AI where the world is messy (language, conversations, unclear payments). Code where money moves.*

This repository is a complete working prototype: a Python backend (FastAPI) and a single-page browser UI.
Paytm's rails (UPI, AutoPay, the lender, the distributor, the Soundbox device) are simulated behind adapters
with production-shaped interfaces. The full design is in [`bharosa-arch-e2e.md`](bharosa-arch-e2e.md).

---

## 1. Run it from scratch

You need **Python 3.11 or newer** and a modern browser (Chrome or Edge recommended). No Node, no database
server, no internet connection (all browser libraries are bundled in `static/vendor/`).

### Windows (PowerShell)

```powershell
cd bharosa-app
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python tasks.py run
```

### macOS / Linux

```bash
cd bharosa-app
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tasks.py run
```

Then open **http://localhost:8000**.

On first start the server creates `bharosa.db` (SQLite) and seeds the demo world automatically. Nothing
else to configure: without an API key every AI agent runs on its deterministic fallback (labelled
**FALLBACK** in the UI), so the whole demo works offline.

> Exact versions that were tested are pinned in `requirements.lock.txt`
> (`pip install -r requirements.lock.txt`) if you ever hit a dependency problem.
> Calling `.venv\Scripts\python` directly avoids PowerShell's script-activation policy.

### Other commands

| Command (`python tasks.py …`) | What it does |
|---|---|
| `run` | Start the server on port 8000 (auto-reloads on code changes) |
| `seed` | Rebuild `bharosa.db` from scratch |
| `test` | Run the test suite (121 tests, about 20 s) |
| `smoke` | Play the whole demo headless and check every number. Add `--url http://localhost:8000` to check a running server (**it resets it**) |
| `snapshot` | Write one sample UI snapshot per demo beat to `fixtures/snapshots/` |

On macOS/Linux `make run`, `make test`, etc. do the same.

---

## 2. The demo world

One shop, round numbers. Everything is defined in [`app/sim/seed.py`](app/sim/seed.py).

**Lakshmi Stores, Jayanagar** · Monday 26 Oct 2026, 09:00

| Customer | Role | Score | Owes | Overdue |
|---|---|---|---|---|
| **Priya** | always pays on time | 780 | ₹0 | – |
| **Ramesh** | the hero | 660 | ₹1,500 | 20 days |
| **Vikram** | chronic defaulter | 420 | ₹2,500 | 45 days |
| Meena, Arjun, Kavya | background, salary-day auto-pay | | ₹8,100 together | – |
| Deepak, Sunita, Imran | background | | ₹5,900 together | Deepak 10 days |

Shop totals: **₹18,000** owed, **₹17,000** verified, **₹7,000** overdue.
**Sharma Traders**' ₹15,000 bill is due **Friday**; the shop will have ₹10,000 → **₹5,000 short**.

---

## 3. Presenting the demo (Live Demo tab)

Three devices side by side: the **Soundbox** (the counter), the **merchant's phone** and the
**customer's phone** (Ramesh). Under them, the demo bar.

* **Next ▶** runs *one step* and explains it in the panel on the right: **what happened**, **who decided**
  (code, an AI agent, the customer or the merchant) and **why it matters**. Pause as long as you like.
* When the bar says **👉 Your turn**, do the step yourself on screen (scan a QR, tap a button). It completes
  by itself and its explanation appears. Or press **Do it for me ▶**.
* **Run beat ⏭** plays the rest of a beat without stopping. **◀** restarts the beat.
* **Reset** (top bar) goes back to Monday 09:00 in about a second.
* **🔊** turns voice on/off, **⏹ Stop speech** silences it immediately. Until Sarvam text-to-speech is
  added, the browser's own voice is used (if it has Hindi/Kannada) and the line is always shown as text.
* **हिं / ಕನ್ನ** switches the Soundbox and briefing language.

### The script

| Beat | Step | Who decides | What you see |
|---|---|---|---|
| **0 Morning** | Munim's briefing | Code computes, **Munim (AI)** phrases | Hindi briefing: Sharma Traders ₹15,000 Friday, ₹5,000 short |
| **1 Guardrail** | Priya asks ₹500 | Code (risk formula) | Green, safe limit ₹4,100 |
| | Vikram asks ₹500 | Code | Red, limit ₹0, collect full payment |
| | Ramesh asks ₹500 | Code | Amber: **₹400 on credit + ₹100 now**, two QRs on the front screen, "3 ms" |
| **2 Confirm** | Ramesh pays ₹100 (pay QR) | Code (sale reference) | Recorded as a sale, never touches his old ₹1,500 |
| | 👉 Click the ₹400 QR, then **Confirm** on Ramesh's phone | **Customer** | Verified receivable; Ramesh owes ₹1,900 |
| **3 Recovery** | 👉 Tap **Send 3 reminders** on Munim's suggestion | Code picks who, **Recovery Agent (AI)** writes | 3 drafts (Vikram, Ramesh, Deepak) |
| | 👉 Approve the reminders | **Merchant** | Reminders arrive in the customers' Paytm apps |
| | Ramesh replies *"Salary 1 tareekh ko aati hai, tab pura de dunga"* | **Recovery Agent (AI)**, checked by code | Promise ₹1,900 on 1 Nov; auto-pay offered |
| | 👉 On Ramesh's phone: **Set up auto-pay → Activate** | **Customer** | Auto-pay up to ₹3,000, 1st–5th; score 660 → 665 |
| **4 Advance** | 👉 Tap **Ask Munim** on the Sharma Traders suggestion | **Munim (AI)** with 3 read-only tools | Two options + buttons |
| | 👉 Tap **Get Supplier Advance** | Code sizes it | ₹5,000 + ₹75 fee = ₹5,075, repaid from 20% of udhaar |
| | 👉 Tap **Accept** | **Merchant** | Partner NBFC pays Sharma Traders ₹5,000 directly |
| **5 Salary day** | Six days pass | Code | Auto-pay collects ₹10,000 from 4 customers; ₹2,000 to the lender; Ramesh 665 → 672, owes ₹0 |
| **6 Fraud ring** | Sai Kirana fakes 4 customers | Code (graph rules) | Risk 1.0: shared device, round amounts, instant confirms, money cycle; advance blocked (see **Overview**) |

### Where AI is used, and where it is not

| Agent | Used in | What it does | What checks it |
|---|---|---|---|
| **Munim** | Beat 0, Beat 4, Ask Munim | Words the briefing; answers questions using read-only tools | Every ₹ figure must come from a tool result; only 3 action types allowed |
| **Recovery Agent** | Beat 3 | Writes reminders; reads replies (promise / dispute / plan …) | Exact dues only, no invented amounts; promises and plans must fit policy |
| **Counter Agent** | Typing free text on the Soundbox ("Ramesh 500 udhaar") | Turns shopkeeper speech into actions | Only this shop's customers; ₹1–50,000; ambiguity → picker |
| **Reconciliation Agent** | Controls → UPI payment from "Kamala Kumar" | Guesses who sent an unclear payment | Must be one of the candidates; auto-applies only at ≥ 85% |

Limits, balances, debits, the advance and the 20% split, scores and fraud rules are **always plain code**.
Munim's suggestion cards are shown by code rules; their wording is a template today.

### More to show judges (Controls panel under the demo bar)

* **UPI payment** prefilled as "Kamala Kumar ₹500, remark *Ramesh ka udhaar*": an unclear payer → "Who paid ₹500?" card.
* **Salary credited**, **+1 day**, **Add bill**, **Inject fraud ring**.
* Free text on the Soundbox, e.g. `Ramesh ne 300 cash diye` or an unknown name, which opens the new-customer keypad.
* A dispute: on the Confirm sheet tap **Dispute**, then correct it from the merchant phone.

**Before presenting**, start the server and run `python tasks.py smoke --url http://localhost:8000`.
It plays every beat and checks every number above (then resets).

---

## 4. Optional: connect an LLM

Copy `.env.example` to `.env`. The gateway supports any OpenAI-compatible endpoint through
`FALLBACK_LLM_BASE_URL`, `FALLBACK_LLM_API_KEY`, `FALLBACK_LLM_MODEL`. **The Sarvam provider and Sarvam
text-to-speech are the planned next step and are not wired yet**; `SARVAM_*` settings are reserved for them.

`LLM_MODE`: `auto` (default: cache, then live, then fallback) · `live` · `record` (save answers to
`fixtures/llm_cache/` for offline demos) · `replay` (cache only) · `template` (never call an LLM).

---

## 5. How it is built

```
Browser (one page: Live Demo · Soundbox · Merchant · Customer · Overview)
   ▲ SSE /api/stream (snapshot, audio, notifications)      │ POST /api/events, /api/demo/*, /api/agents/munim/ask
FastAPI ── event router (validate → persist → handle → commit → broadcast, one lock)
           ├─ agents (propose only):  Counter · Recovery · Reconciliation · Munim  → validators
           ├─ core (decides):         ledger · risk · reconcile · mandates · forecast · advance · integrity · score
           ├─ adapters (simulated):   LLM gateway · UPI · AutoPay · lender · distributor · Soundbox
           └─ sim:                    seed · daily jobs · demo script · comparison
SQLite (bharosa.db) via SQLModel
```

* The UI never computes money. It renders the latest **snapshot** pushed by the server.
* Every action is an **event** (`POST /api/events`), stored in the `events` table.
* Every step writes a **trace** line (component, label, timing, LIVE/CACHED/FALLBACK). The trace is the
  audit trail; the **Overview** tab shows it and lights up the architecture diagram.

```
app/
  main.py            FastAPI app, static files, seed-if-missing
  events/            schemas (payloads) · router (lock, transaction) · handlers (one per event type)
  core/              ledger, risk, score, reconcile, mandates, forecast, advance, integrity,
                     collector, briefing, suggestions, messages, money
  agents/            base (LLM call + repair + trace) · counter · recovery · recon_agent · munim · prompts/
  adapters/          llm gateway · soundbox · upi · payments (mandate, lender, distributor)
  realtime/          snapshot builder · SSE broadcaster · trace
  sim/               seed (the demo world) · daily jobs · demo_script (beats + explanations) · fraud · compare
static/              index.html, css/, js/ (Alpine.js), vendor/ (Alpine, Chart.js, QR), img/architecture.svg
tests/               pytest: contract numbers, flows, agents/validators, demo end to end
scripts/smoke_demo.py
```

API quick reference: `GET /api/snapshot`, `GET /api/stream`, `POST /api/events`,
`POST /api/demo/reset|next|run_beat|goto/{beat}`, `GET /api/demo/script`, `POST /api/agents/munim/ask`,
`GET /api/customers`, `GET /api/forecast`, `GET /api/overview/compare`, `GET /api/health`.
Interactive docs at **http://localhost:8000/docs**.

---

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found / wrong version | Install Python 3.11+ from python.org; on Windows use `py -3.11` |
| Port 8000 is busy | `.venv\Scripts\python -m uvicorn app.main:app --port 8001` and open that port |
| Page loads but stays empty / "Reconnecting" dot | The server stopped; restart `tasks.py run` and refresh |
| Numbers look wrong after experimenting | Press **Reset**, or stop the server and run `python tasks.py seed` |
| `database is locked` | Only one server per `bharosa.db`; close other copies, or delete `bharosa.db` (it is rebuilt on start) |
| No voice | Click **🔊** (browsers need a click before audio). The browser may have no Hindi/Kannada voice; the text is always shown on screen. Sarvam TTS will replace this |
| Layout too big | Designed for 1920×1080; use browser zoom (Ctrl −) on smaller screens |

---

## 7. Sharing this project as a zip

Leave out the generated folders:

```bash
git archive --format=zip -o bharosa-app.zip HEAD
```

Or zip the folder manually **without** `.venv/`, `bharosa.db*`, `__pycache__/` and `.pytest_cache/`.
The recipient follows section 1.

---

*Concept prototype · Team MerchantMavericks (Sujay Mohanty · Sukruth N · Rishi Sharma). All names, shops,
the lender and the distributor are fictional.*
