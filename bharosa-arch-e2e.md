# Bharosa: End-to-End Architecture & Build Specification

**Team MerchantMavericks** (Sujay Mohanty · Sukruth N · Rishi Sharma)
Paytm Build for India AI Hackathon, Bengaluru · Track 1: Merchant Growth AI · Finals: 31 Oct 2026
Document version 1.0. **This file is the single source of truth for the build.**

---

## 0. How to use this document

This spec is written so that a human or an AI coding agent can build the full prototype from it without other context.

- **Build in the order of Section 17.** Each milestone has acceptance checks; do not start the next milestone until the current one passes.
- **Numbers in this file are contracts.** The seed data, formulas and demo script are tuned so the demo always produces the same values (for example, Ramesh's safe limit is exactly ₹200). Tests assert these values.
- **Where something is an assumption** (for example, the Soundbox event format, or a Sarvam language code), it is marked `ASSUMPTION` or `VERIFY`.
- **Golden rule for every module:** *the LLM proposes, code decides.* No LLM output ever changes money, limits or ledger state without passing a deterministic validator.

---

## 1. Product in one page

### 1.1 The problem
Every kirana gives udhaar (informal credit). In doing so it acts as an unlicensed lender with no underwriting (credit is given on gut feel), no collections (chasing neighbours damages relationships) and no funding (udhaar is paid for out of stock money, while distributors want payment in 7–14 days).

### 1.2 The solution
Bharosa is an AI-assisted credit layer that sits **on top of** Paytm's existing rails:
- **Merchant side:** the Paytm AI Soundbox (voice in, top display, speaker, customer-facing front screen with QR) and the Paytm for Business app.
- **Customer side:** the Paytm consumer app (identity, UPI, AutoPay mandates, credit line on UPI).
- **Lender side:** Paytm's lending partners.

### 1.3 The five moments of a credit sale
| # | Moment | Feature | Decided by |
|---|---|---|---|
| 1 | Before credit is given | **Udhaar Guardrail**: safe limit and suggested split, in under 300 ms | Deterministic risk formula |
| 2 | At the sale | **Scan-to-Confirm**: the customer scans a QR on the Soundbox front screen and confirms in the Paytm app, so the entry becomes a *verified receivable* | Customer |
| 3 | After the sale | **Salary-day Auto-pay**: a UPI AutoPay mandate clears verified dues when salary arrives; the **Recovery Agent** handles conversations | Customer mandate, plus deterministic policy |
| 4 | When cash runs short | **Supplier Advance**: a lender pays the distributor directly, and the advance is repaid from 20% of incoming udhaar repayments | Merchant approves; deterministic sizing |
| 5 | Always | **Bharosa Score**: on-time repayment builds the customer's credit identity across all Paytm merchants | Deterministic scoring |

Plus: the **Munim Agent** (shopkeeper copilot) and the **Integrity check** (fraud rings that fake udhaar to farm loans).

### 1.4 One-liners for the pitch
- "Khata apps record udhaar. Bharosa makes it safe, verified and self-collecting."
- "The merchant uses the Soundbox. The customer uses the Paytm app. Bharosa connects them."
- "AI where the world is messy (language, conversations, unclear payments). Code where money moves."
- "Swap the adapters and this runs on Paytm."

---

## 2. Scope

### 2.1 Real in the prototype (actual working code)
- Event-driven backend: ledger, entry state machine, risk engine, reconciliation, mandate executor, forecaster, supplier advance with split settlement, integrity (fraud) rules, Bharosa Score.
- Four LLM agents (Counter, Recovery, Reconciliation, Munim) using the Sarvam LLM, with validators and fallbacks.
- Sarvam text-to-speech for Soundbox voice in Hindi and Kannada.
- One web UI with five views: Live Demo, Soundbox, Merchant app, Customer app, Overview. All are live-synced through server-sent events.
- Simulation engine: seeded world, simulated clock, guided Demo Mode, and the "notebook vs Bharosa" comparison.

### 2.2 Simulated (behind adapters with production-shaped interfaces)
- Soundbox device input (Paytm's speech recognition is assumed; we receive text or structured intents).
- UPI payments, salary credits, UPI AutoPay mandate execution.
- Lender (a fictional "Partner NBFC") and distributor ("Sharma Traders") APIs.
- The Paytm consumer app and Paytm for Business app (rendered as mock screens in Paytm style).

### 2.3 Non-goals
- No speech-to-text. Paytm's Soundbox already does this.
- No real money movement, no real KYC, no real lender integration.
- No build-step frontend framework (no React, no npm).
- No authentication. A demo "viewing as" switcher replaces login.

### 2.4 Optional stretch goals (only after all milestones pass)
- UPI adapter creates real payment links via the Paytm Payment Gateway sandbox or Paytm's MCP connector.
- Open the Customer view on a real phone over LAN.
- An MCP server exposing the Bharosa ledger to AI assistants.

---

## 3. Glossary

| Term | Meaning |
|---|---|
| Udhaar | Goods given on credit by a shop to a customer |
| Entry | One udhaar record (customer, amount, date, state) |
| Verified receivable | An entry the customer has confirmed in the Paytm app |
| Safe limit | Maximum new credit the risk engine recommends for a customer at this store today |
| Band | Guardrail colour: `green` (within limit), `amber` (partially within), `red` (limit is zero) |
| Bharosa Score | Network-wide customer score, 300–900, starting at 600 |
| Mandate | Customer's standing UPI AutoPay permission to clear verified dues at a store, up to a cap, in a salary window |
| Supplier Advance | A lender pays a distributor bill directly; repaid by splitting a share of incoming udhaar repayments |
| Split rate | Share of each eligible repayment routed to the lender (default 20%) |
| Backstop | If an advance is not fully repaid by its backstop date, the remainder becomes a normal instalment |
| Trace | A log line recording each system step (component, decision, latency), shown live in the UI |
| Sim clock | The simulated "today" used by every module; advanced by demo controls |

---

## 4. The seeded world (cast and numbers)

All names are fictional. No real lender or distributor names.

### 4.1 Stores
| ID | Name | Area | Role in demo |
|---|---|---|---|
| `S1` | **Lakshmi Stores** | Jayanagar, Bengaluru | Main demo store |
| `S2` | **Sai Kirana** | Banashankari, Bengaluru | Used only for the fraud-ring beat |

**Lakshmi Stores settings:**
- Owner display name: "Lakshmi Stores" (owner name not needed)
- Average daily UPI sales: ₹10,000
- `starter_limit` for new customers: ₹500 (presets: 200 / 500 / 1,000)
- `due_days` (default credit period): 30
- `cash_on_hand` at demo start: ₹3,200
- `daily_net_cash` (cash left after daily expenses): ₹1,200
- Default language: Hindi (`hi-IN`); Kannada toggle (`kn-IN`, VERIFY code in Sarvam docs)

### 4.2 Named customers (all at S1)
| ID | Name | Persona | Score | Verified outstanding | Oldest overdue | Mandate | Role in demo |
|---|---|---|---|---|---|---|---|
| `C_RAMESH` | Ramesh Kumar | `salary_day` | **680** | **₹1,800** | **19 days** | none at start | Hero customer: amber guardrail, confirm, recovery chat, sets auto-pay |
| `C_PRIYA` | Priya Nair | `punctual` | 780 | ₹0 | 0 | none | Green guardrail |
| `C_VIKRAM` | Vikram Rao | `chronic_defaulter` | 420 | ₹2,600 | 41 days | none | Red guardrail |
| `C_SURESH` | Suresh Gowda | `cash_only` | 610 | ₹900 | 0 | none | Cash repayment example |
| `C_ANITA` | Anita Desai | new (no history) | 600 | ₹0 | 0 | none | Starter-limit example |

Exact seeded entries for the named customers (so overdue days and score changes are predictable):
- **Ramesh:** a **single** verified entry of ₹1,800 created Mon 7 Sep 2026 (due 7 Oct, so 19 days overdue on 26 Oct). VPA `ramesh.k@ptyes`. Also linked to the VPA `9876500000@ptyes` (his mother's account, used in the unclear-payment example) **only via the agent**, not on file.
- **Vikram:** one verified entry of ₹2,600 created Sun 16 Aug 2026 (due 15 Sep, 41 days overdue).
- **Suresh:** one verified entry of ₹900 created 20 Oct 2026 (not yet due).

Plus **55 generated customers** at S1 with this persona mix: `punctual` 25%, `salary_day` 30%, `late_payer` 25%, `chronic_defaulter` 10%, `cash_only` 10%. **Eight** of the `salary_day` customers have active mandates, with total verified dues of about ₹9,000 due to sweep on 1 Nov.

**Store-level totals at demo start (tests assert these, ±₹500 where noted):**
- Total outstanding udhaar: ≈ ₹45,000 (±₹500)
- Verified outstanding: ≈ ₹38,000 (±₹500)
- Verified outstanding from customers with score ≥ 550 (`V_eligible`): ≥ ₹23,000 (so the advance cap ≥ ₹9,200)

### 4.3 Distributor bill
| ID | Distributor | Amount | Due |
|---|---|---|---|
| `B1` | Sharma Traders | ₹18,000 | Fri 30 Oct 2026 |

### 4.4 Lender
`L1` **Partner NBFC (simulated)**. Fee 1.5% flat, split rate 20%, backstop 30 days.

### 4.5 Sim clock
- Demo start: **Mon 26 Oct 2026, 09:00 IST**
- Salary day for `salary_day` customers: the 1st of each month (Sun 1 Nov 2026)

### 4.6 Persona behaviour (used by the generator and the comparison sim)
| Persona | Takes udhaar | Repays |
|---|---|---|
| `punctual` | 2–4 times/month, ₹150–600 | UPI within 3–10 days |
| `salary_day` | 3–6 times/month, ₹200–700 | UPI on the 1st–3rd |
| `late_payer` | 2–5 times/month, ₹200–800 | UPI 25–50 days later, sometimes partial |
| `chronic_defaulter` | 3–6 times/month, ₹300–900 | Rarely; 40% never |
| `cash_only` | 2–4 times/month, ₹150–500 | Cash, 5–15 days later |

The generator uses a fixed random seed (`SEED=42`) and then **overrides** the five named customers with the exact values in 4.2.

---

## 5. End-to-end flows

### 5.1 Flow A: a credit sale (the core lifecycle)

```
Shopkeeper presses Paytm button and speaks
        │  (Paytm speech recognition, assumed)
        ▼
Soundbox adapter → event udhaar_spoken {store, text | structured intent}
        │
        ▼
Counter Agent (only if free text) → proposal {customer, amount}
        │  Validator: customer exists at store, 1 ≤ amount ≤ 50,000
        ▼
Risk engine → safe_limit, band, split (credit_now, collect_now)
        │
        ▼
Ledger creates Entry(state=proposed, amount=credit_now) + confirm token
        │
        ├─► Soundbox TOP display: band colour + message (+ spoken audio)
        ├─► Soundbox FRONT screen: "Scan to confirm ₹200 udhaar" QR (+ UPI QR for ₹140 if split)
        └─► Merchant app: pending entry
        │
Customer scans QR → Paytm app Confirm sheet → customer_confirm {token}
        │
        ▼
Ledger: proposed → verified; consents recorded (first time)
Integrity rules run on the new verified entry
Score service updates the customer's history
Broadcast to all screens; trace lights up the architecture diagram
```

**Variants**
- **Customer taps Dispute:** entry → `disputed`; the merchant sees "Ramesh disputes: says ₹240". Merchant corrects (`entry_corrected`), and the entry goes back to `proposed` with the new amount and a new QR.
- **No scan within 10 minutes (sim time):** entry → `unverified`. It counts in the merchant's books but not in `V_eligible` or advance sizing.
- **Shopkeeper overrides the guardrail** (gives the full ₹340): allowed via an "Override" button; the entry is flagged `override=true` and logged.
- **Customer has no smartphone:** same as no scan → `unverified`.
- **First-ever credit for a customer:** the front screen asks for a mobile number (simulated input), a customer is created with `starter_limit`, and the Confirm sheet includes the two consent checkboxes.

### 5.2 Flow B: repayments

**B1. UPI payment from a known customer**
`upi_payment {payer_vpa, amount, remark?}` → reconciliation rules match the VPA to a customer → allocate FIFO (oldest verified entry first) → excess becomes `customer_credit_balance` → split if an advance is repaying → score update → Soundbox speaks "₹500 received from Ramesh".

**B2. UPI payment, unclear payer**
Rules find no VPA match → **Reconciliation Agent** proposes `{customer_id, confidence}` from the top 5 candidates. If confidence ≥ 0.85, apply automatically (trace shows "agent match 0.91"). Otherwise the merchant app shows a "Who paid ₹500?" card with the candidates, and the merchant taps one.

**B3. Cash repayment**
Shopkeeper says "Suresh ne 300 cash diye" → Counter Agent → `cash_reported` → FIFO allocation, `source=cash`, `attested_by=merchant`. Score impact is half that of UPI. Cash is never split to a lender.

**B4. Salary-day auto-pay**
`salary_credited {customer_id}` → mandate executor checks the active mandate for each store → debits `min(verified_dues, mandate_cap)` → creates a repayment with `source=mandate` → FIFO allocation → split if an advance is repaying → score update → customer app notification "₹2,000 auto-paid to Lakshmi Stores".

### 5.3 Flow C: Recovery Agent conversation
1. Trigger: the merchant taps "Send reminders" (or the Munim suggestion), or the demo beat fires. Collector policy picks customers whose oldest entry is overdue ≥ 7 days, with no nudge in the last 3 days.
2. The Recovery Agent drafts a nudge in the customer's language. The merchant approves (one tap, or "approve all").
3. The customer app shows the message in **Messages** (from "Lakshmi Stores via Paytm"), with "Pay now" and a reply box.
4. The customer replies in free text, e.g. "Salary 1 tareekh ko aati hai, tab pura de dunga" (my salary comes on the 1st, I'll pay it all then).
5. The Recovery Agent classifies it as `promise {amount: 2000, date: 2026-11-01}`. The validator checks it against policy (date within 30 days, amount ≤ dues). It replies and suggests: "Set up salary-day auto-pay so you never miss it?" with a button.
6. The customer taps the button → Auto-pay setup sheet → `mandate_created`.
7. If the reply indicates a dispute or hardship, `escalate=true` → the merchant gets a card.

### 5.4 Flow D: Forecast and Supplier Advance
1. The forecaster runs daily (and on `bill_added`, and when Munim asks). It projects cash for 14 days.
2. For bill B1, the projected cash before the due date is ₹8,800, so the gap is **₹9,200** (Section 7.6). The merchant home shows a "Due soon: Sharma Traders ₹18,000 · ₹9,200 short on Fri" warning.
3. The merchant asks Munim, "Friday ko Sharma ko 18,000 kaise dunga?" (How will I pay Sharma ₹18,000 on Friday?). Munim calls tools: forecast, collectable dues, advance eligibility. It answers with two options plus an **"Get Supplier Advance"** action button.
4. The merchant opens the advance offer: amount ₹9,200, fee ₹138, total ₹9,338, split 20%, backstop 29 Nov. They tap **Accept**.
5. States animate: `offered → accepted → disbursed` ("Partner NBFC paid ₹9,200 to Sharma Traders ✓") `→ repaying`.
6. Every subsequent UPI or mandate repayment at S1 is split 80/20 until ₹9,338 is repaid → `closed`. A progress bar on the merchant home and the Overview shows the lender share.
7. If the remainder is outstanding on the backstop date → `backstop_due` (shown, not demoed).

### 5.5 Flow E: Integrity (fraud ring)
`inject_fraud_ring {store: S2}` creates 4 fake customers at Sai Kirana. All confirm from the same simulated device ID within seconds, with round ₹2,000 entries, and the store sends P2P money back to them within 48 hours. Integrity rules flag the ring, the entries are excluded from `V_eligible`, Sai Kirana's advance eligibility is blocked, and the Overview "Risk console" card shows the alert with the reasons.

### 5.6 Flow F: Morning briefing
At demo start (`reset`) and on each `advance_day`, Munim composes a briefing from a **deterministic summary** (yesterday's sales, dues collectable this week, overdue count, bills due, gaps). The LLM only phrases it. It is spoken on the Soundbox (Hindi or Kannada audio) and shown as a card on the merchant home.

---

## 6. System architecture

### 6.1 Diagram
```
┌──────────────────────────────── BROWSER (one page, 5 views) ────────────────────────────────┐
│  Live Demo │ Soundbox │ Merchant (Paytm for Business style) │ Customer (Paytm app style) │ Overview │
│      state = latest snapshot from server; every view re-renders from it                         │
└──────────────▲───────────────────────────────────────────────┬──────────────────────────────────┘
               │ SSE /api/stream (snapshot, trace, audio,       │ REST /api/events, /api/agents/*,
               │ notify, caption)                                │ /api/demo/*
┌──────────────┴──────────────────────────── FastAPI ─────────────▼─────────────────────────────────┐
│  EVENT ROUTER  validate (Pydantic) → persist event → dispatch handler → broadcast                  │
│                                                                                                     │
│  AGENTS (LLM, propose only)          VALIDATORS            CORE SERVICES (deterministic)            │
│  • Counter Agent       ───────────►  schema + policy ───►  • Ledger + entry state machine           │
│  • Recovery Agent                    checks                • Risk engine (safe limit, band)         │
│  • Reconciliation Agent                                    • Reconciliation rules (FIFO)           │
│  • Munim Agent (tool loop) ◄── read-only tools ───────────  • Mandate executor                       │
│                                                            • Forecaster                             │
│                                                            • Supplier Advance + split router       │
│                                                            • Integrity rules (NetworkX)            │
│                                                            • Score service                         │
│                                                                                                     │
│  ADAPTERS:  LLM gateway (Sarvam → fallback → replay → template) · TTS (Sarvam + cache)            │
│             UPI · Mandate · Lender · Distributor · Soundbox      (simulated, production-shaped)    │
│                                                                                                     │
│  SIM ENGINE: seed · sim clock · demo script · comparison sim       TRACE + BROADCASTER (SSE)       │
└──────────────────────────────────────────────┬──────────────────────────────────────────────────────┘
                                               ▼
                                   SQLite (bharosa.db) via SQLModel
```

### 6.2 Design principles
1. **Single source of truth.** All state lives in the backend database. The frontend never computes balances; it renders snapshots.
2. **Everything is an event.** Every user action and simulated occurrence is a `POST /api/events`. Each event is persisted (event log) and replayable.
3. **The LLM proposes, code decides.** Agents return structured proposals; validators accept, reject or route them to a human. Agents' tools are read-only; any write goes through the event router.
4. **Adapters at every boundary.** Each external system has an interface plus a simulated implementation. Production swaps implementations, not logic.
5. **Every step is traced.** Each module writes a trace line (`node`, `label`, `detail`, `ms`). The UI uses node IDs to light up the architecture diagram.
6. **Deterministic demo.** Fixed seed, sim clock, cached LLM and TTS outputs. The same demo produces the same numbers every time.
7. **Privacy by design.** The merchant sees only their own ledger plus each customer's band, safe limit and score band, never other stores' records.

### 6.3 Tech stack
| Layer | Prototype choice | Notes |
|---|---|---|
| Language | Python 3.11 | |
| API | FastAPI + Uvicorn | Async, also serves the static frontend |
| Validation | Pydantic v2 | Event payloads, agent outputs |
| DB | SQLite via SQLModel | Single file `bharosa.db`; `reset` rebuilds it |
| Realtime | SSE via `sse-starlette` | One stream, typed messages |
| Graph | NetworkX | Integrity rules |
| Data gen | `random` + Faker (`en_IN`) | Fixed seed |
| LLM | Sarvam Chat Completions (`sarvam-105b`), `https://api.sarvam.ai/v1/chat/completions` | Supports `tools` and `response_format` (`json_schema` / `json_object`). Model names via env |
| TTS | Sarvam Text-to-Speech, `POST https://api.sarvam.ai/text-to-speech`, model `bulbul:v3` | `language_code` `hi-IN`, `kn-IN` (VERIFY); returns base64 WAV in `audios[]` |
| SDK | `sarvamai` (Python) | Or raw `httpx` calls; header `api-subscription-key` |
| Frontend | HTML + CSS + vanilla JS + **Alpine.js** | No build step; vendored files |
| Charts | Chart.js (vendored UMD) | Overview comparison chart |
| QR | `qrcode` JS library (vendored) | Confirm QR and UPI QR |
| Diagram | Hand-authored SVG with node IDs | Lit by trace events |
| Tests | pytest | Core formulas and demo flow |

---

## 7. Backend modules (behaviour and exact rules)

All modules read time **only** from `clock.now()`.

### 7.1 Event router (`app/events/router.py`)
- `POST /api/events` with body `{type, payload}`.
- Steps: validate payload against the schema for `type` → assign `event_id`, `ts=clock.now()` → persist to `events` → call the handler → handlers return a list of `Effect`s (state changed, audio, notify, caption) → the broadcaster sends a fresh snapshot plus effects.
- Handlers run sequentially (one asyncio lock) to avoid race conditions in the demo.
- Unknown type → 400. Validation error → 422 with message. Handler exception → 500, plus trace node `router` with an error, and the UI shows a toast.

### 7.2 Ledger and entry state machine (`app/core/ledger.py`)

**Entry states**
```
proposed ──confirm──► verified ──partial payment──► partly_paid ──full──► settled
   │  ├──dispute──► disputed ──correct──► proposed
   │  └──timeout(10 sim-min)──► unverified ──(still collectable; not lendable)
verified/partly_paid ──60 days overdue──► defaulted (score penalty; still collectable)
```

| From | Event | To | Side effects |
|---|---|---|---|
| — | `udhaar_spoken` (after guardrail) | `proposed` | Confirm token (UUID4), expiry = now + 10 sim-minutes |
| `proposed` | `customer_confirm` | `verified` | `verified_at`; consents if first time; integrity check |
| `proposed` | `customer_dispute` | `disputed` | Reason and claimed amount stored; merchant card |
| `disputed` | `entry_corrected` | `proposed` | New amount, new token |
| `proposed` | expiry | `unverified` | — |
| `verified`/`partly_paid`/`unverified` | allocation | `partly_paid`/`settled` | `paid_amount` updated |
| `verified`/`partly_paid` | daily job, overdue > 60 days | `defaulted` | Score −40 (once) |

- `due_date = created_at + store.due_days`.
- `overdue_days(entry) = max(0, today − due_date)` while unpaid.
- **Allocation (FIFO):** repayments are applied to the customer's open entries at that store, ordered by `created_at` ascending, `verified` and `partly_paid` first, then `unverified`. Any excess goes to `customer.credit_balance[store]`.

### 7.3 Risk engine (`app/core/risk.py`)
Pure function, no I/O except reading a cached feature row. **Target p95 < 50 ms in-process** (the UI shows the measured ms; the pitch says under 300 ms end to end).

**Inputs (per customer, per store):**
- `S` = Bharosa Score (network-wide, 300–900)
- `O` = verified + partly_paid + unverified outstanding at this store (₹)
- `D` = max overdue days across open entries at this store
- `is_new` = no entries at any store

**Formula:**
```
if is_new:
    safe_limit = store.starter_limit
else:
    base = 500 + (S - 300) / 600 * 4500          # S=300 → ₹500, S=900 → ₹5,000
    m = 1.0 if D == 0 else 0.75 if D <= 14 else 0.6 if D <= 30 else 0.0
    safe_limit = max(0, floor50(base * m - O))    # floor50 = round down to a multiple of 50
    safe_limit = min(safe_limit, 5000)

band = "green" if amount <= safe_limit
       else "red" if safe_limit == 0
       else "amber"
credit_now  = min(amount, safe_limit)
collect_now = amount - credit_now
```

**Contract values (tests assert these):**
| Customer | S | O | D | safe_limit | For ₹340 |
|---|---|---|---|---|---|
| Ramesh | 680 | 1,800 | 19 | **200** | amber: credit 200, collect 140 |
| Priya | 780 | 0 | 0 | **4,100** | green: credit 340 |
| Vikram | 420 | 2,600 | 41 | **0** | red: credit 0, collect 340 |
| Anita (new) | 600 | 0 | 0 | **500** (starter) | green |

**Explainability:** the risk engine returns `reasons[]`, for example `["₹1,800 overdue for 19 days → limit ×0.6", "Score 680 → base ₹3,350", "Already owes ₹1,800"]`. The UI's "Why?" button shows these.

**Merchant-facing message** (template, optionally rephrased by the LLM; cached):
- green: "Safe. Ramesh can take ₹340 on credit."
- amber: "Caution: ₹1,800 overdue for 19 days. Safe limit today ₹200. Give ₹200 on credit, collect ₹140 now (UPI or cash)."
- red: "High risk: ₹2,600 overdue for 41 days. Suggest collecting full payment."

### 7.4 Score service (`app/core/score.py`)
Range 300–900, start 600. Updated on these triggers (deltas are clamped to the range):
| Trigger | Δ |
|---|---|
| Verified entry settled by its due date | +8 |
| Settled 1–15 days late | +2 |
| Settled > 15 days late | −4 |
| Mandate created | +5 (once per store) |
| Mandate payment executed | +3 |
| Cash settlement (merchant-attested) | half of the UPI delta, rounded down |
| Dispute resolved against the customer (entry confirmed after correction at the original amount) | −15 |
| Entry `defaulted` | −40 |

**Demo contract:** Ramesh 680 → +5 (mandate created) → on salary day +3 (mandate payment) +8 (the ₹200 entry settled on time) −4 (the ₹1,800 entry settled > 15 days late) = **692**.

Score bands for display: 300–549 "Building", 550–699 "Good", 700–799 "Strong", 800–900 "Excellent".
**Rewards (displayed only):** ≥ 700 unlocks "Higher limits at all Paytm stores"; ≥ 750 unlocks "Partner offer: [x]% cashback on groceries (ASSUMPTION: partner-funded)".

### 7.5 Reconciliation rules (`app/core/reconcile.py`)
For each `upi_payment {store_id, payer_vpa, payer_name?, amount, remark?, ref?}`:
0. **Rule 0 (sale payment):** if `ref` starts with `SALE-` (the "pay ₹140 now" QR from a guardrail split carries `ref=SALE-<entry_id>`), record it as a **sale**, not a repayment. It must **not** be allocated to old dues.
1. **Rule 1 (VPA match):** a customer at this store with this `vpa` → allocate. `matched_by=rule`.
2. **Rule 2 (single exact amount):** exactly one customer at the store has an open entry with `amount_remaining == amount` and no VPA on file → allocate, and link the VPA. `matched_by=rule_amount`.
3. **Otherwise:** call the **Reconciliation Agent** (7.9.3) with the top 5 candidates (ranked by name similarity to `payer_name` and `remark`, then by closeness of outstanding amount). If `confidence ≥ 0.85` and the chosen ID is among the candidates, allocate (`matched_by=agent`). Otherwise create a `pending_match` card for the merchant (`matched_by=human` when resolved).
4. If no customer matches at all (plain sale) → record as a sale, not a repayment.

### 7.6 Forecaster (`app/core/forecast.py`)
Deterministic 14-day projection, day by day from today:
```
cash[d] = cash_on_hand
        + Σ_{t=today..d} daily_net_cash
        + Σ_{t=today..d} expected_collections[t]
        - Σ bills due on or before d (counted on the due day, before that day's inflows)
```
- **Expected collections:**
  - Mandate customers: verified dues on the next salary day (the 1st), probability 1.0.
  - Others: `remaining × on_time_rate` placed on the predicted pay day = `last_entry_date + median_days_to_pay` (persona history); defaulters contribute 0.
- **Gap for a bill** = `bill.amount − cash available on the due date before paying it`. If > 0, flag.
- **Contract values:** for B1 (₹18,000, due Fri 30 Oct), cash available = 3,200 + 4 × 1,200 (Mon–Thu) + ₹800 expected collections (Mon–Thu, tuned in seed) = **₹8,800**, gap = **₹9,200**, flagged on Thu 29 Oct.
- Output: `{days:[{date, cash, inflow, outflow}], gaps:[{bill_id, due, gap, flagged_on}]}`.

### 7.7 Supplier Advance and split router (`app/core/advance.py`)
**Eligibility and sizing**
```
V_eligible = Σ remaining on verified/partly_paid entries at the store
             from customers with score ≥ 550 and not integrity-flagged
cap        = 0.4 × V_eligible
eligible   = store not integrity-blocked and no other advance repaying
amount     = min(gap, cap, bill.amount, 50,000)
fee        = round(amount × 0.015)           # ₹138 for ₹9,200
total_due  = amount + fee                    # ₹9,338
split_rate = 0.20
backstop   = accepted_at + 30 days
```
**States:** `offered → accepted → disbursed → repaying → closed`, or `backstop_due`, or `declined`.
- `offer_advance {bill_id}` creates an `offered` advance (via Munim's action button or the "Due soon" card).
- `advance_accept` → `accepted` → lender adapter `disburse(to=distributor, amount)` → `disbursed` (bill marked paid: ₹9,200 by lender + remainder by store) → `repaying`.

**Split router** (called on every allocation):
```
if store has advance in "repaying" and repayment.source in {upi, mandate}:
    lender_share   = min(round(amount × split_rate), advance.total_due − advance.repaid)
    merchant_share = amount − lender_share
    advance.repaid += lender_share
    if advance.repaid >= advance.total_due: state = "closed"
```
Cash repayments are never split. The split is recorded on the repayment row (`lender_share`, `merchant_share`).

### 7.8 Integrity rules (`app/core/integrity.py`)
Run on each `customer_confirm` and nightly. Build a NetworkX `DiGraph` per store: merchant → customer edges for verified entries, and money edges for repayments and P2P transfers (P2P from the simulated UPI adapter).

| Rule | Condition | Weight |
|---|---|---|
| R1 shared device | ≥ 3 customers confirmed from the same `device_id` within 24 h | 0.4 |
| R2 burst | New verified credit in 24 h > 3× the store's 30-day daily average | 0.2 |
| R3 round amounts | ≥ 80% of the last 10 new entries are multiples of ₹500 | 0.1 |
| R4 instant confirms | Median creation-to-confirm time < 15 s for new customers with no UPI history | 0.1 |
| R5 money cycle | `nx.simple_cycles` finds merchant → customer → merchant money flow within 48 h | 0.4 |

`risk = min(1, Σ weights)`. If `risk ≥ 0.6` → flag the entries (`integrity_flag=true`), set `store.advance_blocked=true`, and create a risk alert with the rule reasons. **Contract:** the injected ring at S2 triggers R1, R3, R4 and R5 (risk 1.0).

### 7.9 Agents (`app/agents/`)
All agents share `agents/base.py`:
- `call_llm(agent, messages, schema) -> dict`: goes through the LLM gateway (7.10), requests `response_format={"type":"json_schema", ...}` (falls back to `json_object`), parses with Pydantic, and makes **one repair retry** on a parse error. On a second failure it uses the agent's **deterministic fallback**.
- Every call writes a trace line: `node=<agent>`, `label`, `ms`, `source=live|replay|template`.
- System prompts live in `agents/prompts/*.md` with a `PROMPT_VERSION` constant (part of the cache key).

#### 7.9.1 Counter Agent
**Purpose:** turn shopkeeper speech text (Hindi, Kannada, English, code-mixed) into actions.
**When called:** `udhaar_spoken` or `cash_reported` with `text` and no structured intent. Demo presets send structured intents and skip the LLM.
**Input:** `{text, lang, store_customers:[{id, name, aliases}], today}`
**Output schema:**
```json
{
  "actions": [
    {"type": "udhaar | cash_repayment | unknown",
     "customer_id": "C_RAMESH | null",
     "name_heard": "Ramesh",
     "candidate_ids": ["C_RAMESH"],
     "amount": 340}
  ],
  "clarify_question": "null | 'Which Ramesh: Ramesh Kumar or Ramesh B?'"
}
```
**Validator:** `amount` integer 1–50,000; `customer_id` in the store list or null; if `candidate_ids` has more than 1, show a disambiguation picker on the Soundbox top display. Each valid action becomes its own event.
**Fallback:** regex for `<name> <amount> (udhaar|udhar|credit|khata)` and `<name> (ne)? <amount> (cash|diye)`, with fuzzy name matching (`difflib`).
**System prompt (summary):** "You convert a kirana shopkeeper's short spoken sentence into JSON actions. Use only customer IDs from the list. Never invent amounts. If unsure about the person, return the candidates and a short clarify question in the shopkeeper's language. Output JSON only."

#### 7.9.2 Recovery Agent
**Two modes.**

**(a) `draft_nudge`.** Input: `{customer_name, lang, dues_total, oldest_overdue_days, persona_hint, store_name, policy}`. Output: `{"message": "...", "lang": "hi-IN"}`. Validator: length ≤ 320 characters, must contain the exact dues figure from the input and no other ₹ figure. Fallback: a template per language.

**(b) `interpret_reply`.** Input: `{reply_text, dues_total, today, policy:{max_days:30, max_installments:3, min_first_pct:25}, has_mandate}`. Output:
```json
{
  "intent": "promise | pay_now | plan_request | dispute | hardship | other",
  "promise": {"amount": 2000, "date": "2026-11-01"},
  "proposed_plan": [{"amount": 1000, "date": "2026-11-01"}, {"amount": 1000, "date": "2026-11-15"}],
  "suggest_mandate": true,
  "reply_message": "Dhanyavaad Ramesh ji ...",
  "escalate": false
}
```
**Validator:** promise date within `today .. today + 30`; amount ≤ dues; a plan must satisfy the policy (≤ 3 instalments, first ≥ 25%, sum = dues), otherwise drop the plan and set `escalate=true`; `suggest_mandate` only if `has_mandate=false`; `dispute` or `hardship` → `escalate=true`. Valid promises are stored in `promises`, and the forecaster uses them.
**Fallback:** keyword rules (`salary|tankhwa|1 tareekh` → promise on the next 1st; `nahi|galat|wrong` → dispute) and template replies.
**Contract (demo):** reply "Salary 1 tareekh ko aati hai, tab pura de dunga" → `intent=promise`, `promise={2000, 2026-11-01}`, `suggest_mandate=true`.

#### 7.9.3 Reconciliation Agent
**Input:** `{payment:{amount, payer_vpa, payer_name, remark}, candidates:[{id, name, outstanding, open_entries:[amounts]}]}`
**Output:** `{"customer_id": "C_x | null", "confidence": 0.0-1.0, "reason": "..."}`
**Validator:** `customer_id` must be among the candidates; confidence clamped to 0–1. Auto-apply if ≥ 0.85.
**Fallback:** best candidate by `difflib` name ratio; confidence = ratio × 0.8 (so it usually routes to the human).
**Demo contract:** payment ₹500 from `9876500000@ptyes`, payer_name "Kamala Kumar", remark "Ramesh ka udhaar" (Ramesh's udhaar) → `C_RAMESH`, confidence ≥ 0.85.

#### 7.9.4 Munim Agent (tool-using copilot)
**Purpose:** answer the shopkeeper's open questions and produce the morning briefing.
**Protocol:** a JSON action loop (portable across providers). Native Sarvam `tools` support can be swapped in later.
```
Each step the model returns either:
  {"tool": "<name>", "args": {...}}
or
  {"final": {"answer": "...", "actions": [{"type": "offer_advance", "params": {"bill_id": "B1"}}]}}
Max 4 tool steps, then a forced final.
```
**Read-only tools:**
| Tool | Returns |
|---|---|
| `get_store_summary()` | Sales today and yesterday, outstanding, verified, overdue count |
| `get_forecast(days=14)` | Forecast output (7.6) |
| `list_collectable_dues(until_date)` | Customers with expected collections before the date (amount, probability) |
| `list_overdue(top_n=5)` | Top overdue customers |
| `check_advance_eligibility(bill_id)` | `{eligible, amount, fee, cap, reasons}` |
| `get_customer(name)` | Customer summary (this store only) |

**Allowed final actions** (rendered as buttons; a merchant tap fires the event): `send_nudges {customer_ids}`, `offer_advance {bill_id}`, `open_customer {customer_id}`.
**Validator:** every ₹ figure in `answer` must appear in a tool result from this conversation (regex check); otherwise the answer is replaced with a deterministic template built from the tool results.
**Morning briefing:** not a tool loop. The deterministic summary is passed and the LLM phrases it (≤ 60 words); template fallback.
**Demo contract:** "Friday ko Sharma ko 18,000 kaise dunga?" → calls `get_forecast`, `list_collectable_dues`, `check_advance_eligibility(B1)` → answer mentions ₹9,200 short, about ₹800 collectable, and the advance of ₹9,200 → actions include `offer_advance {B1}` and `send_nudges`.

### 7.10 LLM gateway (`app/adapters/llm.py`)
- `LLM_MODE` env: `auto` (default) | `live` | `replay` | `record` | `template`.
  - `live`: call Sarvam; timeout 8 s.
  - `record`: call live and save the response to `fixtures/llm_cache/<key>.json`.
  - `replay`: read only from the cache; a miss → template fallback.
  - `auto`: if the key is in the cache → replay; else live (timeout 8 s); on error → template.
- Cache key = `sha256(agent + PROMPT_VERSION + canonical_json(input))`.
- **Demo Mode beats use cached outputs** (pre-recorded with `scripts/record_llm.py`). The two **live showcase moments** (Recovery reply typed by a judge, Munim free question) use `auto`.
- Providers: `SarvamProvider` (primary) and an optional `FallbackProvider` (any OpenAI-compatible endpoint via env). Both go through the same interface.

### 7.11 TTS adapter (`app/adapters/tts.py`)
- `speak(text, lang) -> url`. Cache key = `sha256(text + lang + speaker + model)`, file `static/audio/<key>.wav`.
- On a cache miss: call Sarvam TTS (`model=bulbul:v3`, `language_code`, `speaker` from env, default `anushka`-style voice per language; VERIFY speaker names for the chosen model), base64-decode `audios[0]`, write the WAV.
- On failure: return null; the UI shows text only.
- `scripts/prebuild_audio.py` generates all Demo Mode lines in `hi-IN` and `kn-IN`.

### 7.12 Simulated external adapters (`app/adapters/`)
| Adapter | Interface | Prototype behaviour | Production equivalent |
|---|---|---|---|
| `SoundboxAdapter` | `to_event(raw) -> Event`; `display(store, top, front)`; `play(store, audio_url)` | Browser simulator via SSE | Paytm device platform (ASSUMPTION) |
| `UPIAdapter` | `create_collect_qr(amount, payee)`; `incoming_payment()` | Generates UPI-style QR strings; payments fired from controls | Paytm UPI / Payment Gateway (sandbox stretch goal) |
| `MandateAdapter` | `create(customer, store, cap, window)`; `execute(mandate, amount)` | Always succeeds unless `cap` exceeded | UPI AutoPay; later NPCI agent mandates (UAP, proposed) |
| `LenderAdapter` | `offer(store, amount)`; `disburse(to, amount)`; `repay(advance, amount)` | Instant success, logs | Paytm lending partners |
| `DistributorAdapter` | `mark_paid(bill, by, amount)` | Updates the bill | Distributor B2B payments |

Each adapter writes trace lines with `node=<adapter>`.

### 7.13 Trace and broadcaster (`app/realtime/`)
- `trace(node, label, detail=None, ms=None, source=None)` → inserted in the `trace` table and queued for SSE.
- `broadcast(effects)`: after each event, send `snapshot` plus any `audio`, `notify` and `caption` messages.
- One SSE endpoint, `/api/stream`. Clients reconnect automatically (EventSource). On connect, the server immediately sends the current snapshot and the last 30 trace lines.

### 7.14 Simulation engine (`app/sim/`)
- `seed.py`: rebuild the DB from scratch with `SEED=42`, generate 90 days of history (5 Aug–25 Oct 2026), then apply the overrides in Section 4. Must finish in under 5 s.
- `clock.py`: `now()`, `set()`, `advance_days(n)`, `advance_to(datetime)`. Stored in the `sim_state` table.
- `advance_day` handler: advance 1 day → run daily jobs in order: entry expiry → overdue/default check → mandate sweeps (if the 1st) → forecaster → integrity nightly → morning briefing.
- `demo_script.py`: the beats in Section 13.
- `compare.py`: "notebook vs Bharosa" comparison (Section 11.5), cached as JSON after the first run.

---

## 8. Data model (SQLModel tables)

```text
stores(id PK, name, area, lang, starter_limit, due_days, cash_on_hand, daily_net_cash,
       avg_daily_upi_sales, advance_blocked BOOL)

customers(id PK, name, aliases JSON, mobile, vpa, device_id, persona, score INT,
          is_new BOOL, created_at)

store_customers(store_id FK, customer_id FK, credit_balance INT, last_nudge_at,
                PRIMARY KEY(store_id, customer_id))

entries(id PK, store_id FK, customer_id FK, amount INT, paid_amount INT, state TEXT,
        created_at, due_date, verified_at, confirm_token, token_expires_at,
        override BOOL, integrity_flag BOOL, dispute_reason, dispute_amount,
        source_text)

repayments(id PK, store_id FK, customer_id FK NULL, amount INT, source TEXT
           -- upi | cash | mandate
           , payer_vpa, payer_name, remark, matched_by TEXT, match_confidence REAL,
           lender_share INT, merchant_share INT, created_at)

allocations(id PK, repayment_id FK, entry_id FK, amount INT)

pending_matches(id PK, repayment_id FK, candidates JSON, created_at, resolved BOOL)

consents(id PK, customer_id FK, store_id FK NULL, type TEXT
         -- data_share | payment_mandate
         , granted_at, revoked_at)

mandates(id PK, customer_id FK, store_id FK, cap INT, window_start_day INT,
         window_end_day INT, status TEXT, created_at)

promises(id PK, customer_id FK, store_id FK, amount INT, date, status TEXT, created_at)

messages(id PK, store_id FK, customer_id FK, direction TEXT  -- out | in
         , text, lang, status TEXT  -- draft | approved | sent | received
         , agent_output JSON, created_at)

bills(id PK, store_id FK, distributor, amount INT, due_date, status TEXT,
      paid_by_lender INT, paid_by_store INT)

advances(id PK, store_id FK, bill_id FK, lender TEXT, amount INT, fee INT,
         total_due INT, repaid INT, split_rate REAL, state TEXT, backstop_date,
         created_at, accepted_at)

risk_alerts(id PK, store_id FK, rules JSON, risk REAL, entry_ids JSON, created_at)

events(id PK, ts, type, payload JSON)

trace(id PK, ts, node, label, detail JSON, ms REAL, source TEXT)

sim_state(key PK, value)      -- sim_now, demo_beat, lang, focus_customer
```

All money is in **integer rupees**. All timestamps are ISO strings in IST from the sim clock.

---

## 9. Event catalogue

| Event `type` | Payload | Producer | Handler effects |
|---|---|---|---|
| `udhaar_spoken` | `{store_id, text?, customer_id?, amount?, lang?}` | Soundbox panel | Counter Agent if `text` → risk → proposed entry → Soundbox top/front + audio |
| `guardrail_override` | `{entry_id}` | Soundbox / merchant | Entry amount raised to the requested amount, `override=true` |
| `customer_confirm` | `{token, device_id, consents?:{data_share:bool}}` | Customer app | proposed → verified; consents; integrity; score |
| `customer_dispute` | `{token, reason, claimed_amount?}` | Customer app | → disputed; merchant card |
| `entry_corrected` | `{entry_id, amount}` | Merchant app | → proposed, new token |
| `new_customer` | `{store_id, name, mobile}` | Soundbox front screen | Customer with starter limit |
| `upi_payment` | `{store_id, payer_vpa, payer_name?, amount, remark?, ref?}` (`ref=SALE-…` = payment for the current purchase) | Controls / customer "Pay now" | Reconcile → allocate → split → score → audio "₹X received" |
| `cash_reported` | `{store_id, text?, customer_id?, amount?}` | Soundbox panel | Counter Agent if text → allocate (`source=cash`) |
| `match_resolved` | `{pending_id, customer_id}` | Merchant app | Allocate (`matched_by=human`) |
| `nudges_requested` | `{store_id, customer_ids?}` | Merchant / Munim / demo | Collector picks customers → Recovery drafts (status `draft`) |
| `nudges_approved` | `{message_ids}` | Merchant app | status `sent` → customer notify |
| `customer_reply` | `{customer_id, store_id, text}` | Customer app Messages | Recovery `interpret_reply` → promise/escalate → reply message |
| `mandate_created` | `{customer_id, store_id, cap, window_start_day, window_end_day}` | Customer app | Mandate + consent + score +5 |
| `salary_credited` | `{customer_id}` | Controls / `advance_day` on the 1st | Mandate executor for each store |
| `bill_added` | `{store_id, distributor, amount, due_date}` | Controls | Forecaster |
| `offer_advance` | `{store_id, bill_id}` | Munim action / merchant card | Advance `offered` |
| `advance_accept` / `advance_decline` | `{advance_id}` | Merchant app | Disburse to distributor → repaying / declined |
| `advance_day` | `{days: 1}` | Controls / demo | Daily jobs (7.14) |
| `inject_fraud_ring` | `{store_id: "S2"}` | Controls / demo | Fake customers, entries, P2P; integrity → alert |
| `set_language` | `{lang: "hi-IN" or "kn-IN"}` | Top bar | `sim_state.lang`; re-render; audio language |
| `set_focus_customer` | `{customer_id}` | Customer view switcher | `sim_state.focus_customer` |

Demo and admin endpoints (Section 10) also exist for reset and stepping.

---

## 10. API contract

All JSON. Base path `/api`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/events` | Fire any event (Section 9). Returns `{ok, event_id, effects_summary}` |
| GET | `/api/snapshot` | Full current snapshot (shape below) |
| GET | `/api/stream` | SSE stream |
| GET | `/api/customers?store_id=S1` | List for pickers |
| GET | `/api/customers/{id}?store_id=S1` | Detail: entries timeline, risk reasons, score history |
| GET | `/api/confirm/{token}` | Data for the Confirm sheet (store, amount, date, first_time) |
| POST | `/api/agents/munim/ask` | `{store_id, question, lang}` → `{answer, actions[], steps[]}` (steps feed the trace) |
| GET | `/api/forecast?store_id=S1` | Forecast output |
| GET | `/api/trace?limit=100` | Recent trace lines |
| GET | `/api/overview/compare` | Comparison series (11.5) |
| POST | `/api/demo/reset` | Rebuild the DB from the seed, reset the clock, keep the LLM/TTS caches |
| GET | `/api/demo/script` | List of beats with captions |
| POST | `/api/demo/next` | Run the next beat's events; returns the caption |
| POST | `/api/demo/goto/{beat}` | Reset, then run beats up to N (for rehearsal) |
| GET | `/api/health` | `{ok, llm_mode, sarvam_reachable, db}` |

### 10.1 SSE message types
```json
{"type": "snapshot", "data": { ...snapshot... }}
{"type": "trace", "data": {"ts": "...", "node": "risk", "label": "Safe limit ₹200 (amber)", "ms": 3.2, "source": null}}
{"type": "audio", "data": {"target": "soundbox:S1", "url": "/static/audio/ab12.wav", "text": "..."}}
{"type": "notify", "data": {"target": "customer:C_RAMESH | merchant:S1", "title": "...", "body": "...", "action": {"label": "Confirm", "token": "..."}}}
{"type": "caption", "data": {"text": "Guardrail checked Ramesh's history in 3 ms"}}
```

### 10.2 Snapshot shape (abridged; the builder may add fields but must not rename these)
```json
{
  "now": "2026-10-26T09:00:00+05:30",
  "lang": "hi-IN",
  "demo": {"beat": 2, "total": 7, "caption": "..."},
  "soundbox": {
    "store_id": "S1",
    "top": {"band": "amber", "text": "Safe limit ₹200 ...", "ms": 3},
    "front": {"mode": "idle | confirm_qr | pay_qr | new_customer | amount",
              "amount": 200, "qr_payload": "bharosa://confirm/<token>", "pay_qr": "upi://pay?pa=lakshmistores@ptyes&am=140&tr=SALE-<entry_id>"},
    "last_alert": "₹500 received from Ramesh"
  },
  "merchant": {
    "store": {"id": "S1", "name": "Lakshmi Stores"},
    "today_collection": 10240,
    "udhaar": {"outstanding": 45000, "verified": 38000, "overdue": 6400, "pending_confirm": 1},
    "briefing": {"text": "...", "audio_url": "..."},
    "due_soon": [{"bill_id": "B1", "distributor": "Sharma Traders", "amount": 18000, "due": "2026-10-30", "gap": 9200}],
    "advance": {"id": "A1", "state": "repaying", "amount": 9200, "fee": 138, "total_due": 9338, "repaid": 2200, "split_rate": 0.2, "lender": "Partner NBFC", "backstop": "2026-11-29"},
    "pending_matches": [],
    "disputes": [],
    "drafts": [{"message_id": 12, "customer": "Ramesh Kumar", "text": "..."}],
    "customers_top": [{"id": "C_RAMESH", "name": "Ramesh Kumar", "outstanding": 2000, "band": "amber", "score_band": "Good", "overdue_days": 19}]
  },
  "customer": {
    "id": "C_RAMESH", "name": "Ramesh Kumar",
    "score": 680, "score_band": "Good", "score_delta_7d": 8,
    "dues": [{"store": "Lakshmi Stores", "store_id": "S1", "amount": 2000, "verified": 2000, "oldest_overdue_days": 19}],
    "pending_confirms": [{"token": "...", "store": "Lakshmi Stores", "amount": 200, "date": "..."}],
    "mandates": [{"store": "Lakshmi Stores", "cap": 3000, "window": "1st–5th", "status": "active"}],
    "messages": [{"direction": "in", "text": "...", "ts": "..."}],
    "history": [{"type": "entry | repayment", "amount": 200, "state": "verified", "ts": "..."}],
    "rewards": ["Higher limits at all Paytm stores"]
  },
  "risk_console": {"alerts": [{"store": "Sai Kirana", "risk": 1.0, "rules": ["R1", "R3", "R4", "R5"]}]},
  "trace_tail": []
}
```
Privacy rule: `merchant.*` never includes other stores' entries; `customer.dues` lists all stores (it's the customer's own data).

---

## 11. Frontend specification

### 11.1 Tech and structure
- One page: `static/index.html`, served at `/`.
- **Alpine.js** global store `Alpine.store('app')` holds `snapshot`, `trace[]`, `view`, `toast`. An `EventSource('/api/stream')` updates it. Every component renders from the store.
- Hash routing: `#/live` (default), `#/soundbox`, `#/merchant`, `#/customer`, `#/overview`.
- Plain CSS with design tokens. **No framework CSS.** Vendored: `alpine.min.js`, `chart.umd.min.js`, `qrcode.min.js` in `static/vendor/`. **Must work fully offline** (no CDN at runtime).
- Target resolution: 1920×1080 (primary), usable at 1440×900.
- Audio: one `<audio>` element; play on `audio` messages whose target matches. A global "🔊 sound on" toggle in the top bar (browsers need a first click to allow audio; the "Start demo" button provides it).

### 11.2 Design tokens (`static/css/tokens.css`)
```css
:root {
  --navy: #042E6F;        /* Paytm Prussian blue: icon circles, primary buttons */
  --navy-deep: #172B75;   /* hover / gradients */
  --cyan: #00BAF2;        /* accents, QR frames, links on dark */
  --link: #0F6FDE;        /* "View All →" style links */
  --bg: #F5F5F7;          /* app background */
  --card: #FFFFFF;
  --ink: #111418;         /* headings */
  --ink-2: #4A5568;       /* body */
  --muted: #8A94A6;
  --line: #E6E8EC;
  --green: #1E9E5A;  --green-bg: #E6F6EE;
  --amber: #E08A00;  --amber-bg: #FFF4E0;
  --red:   #D93025;  --red-bg:   #FDECEA;
  --radius-card: 24px; --radius-pill: 999px; --radius-sm: 12px;
  --shadow: 0 2px 12px rgba(4,46,111,.08);
  --font: "Inter", "Roboto", system-ui, -apple-system, "Noto Sans", sans-serif;
}
```
Fonts: vendor Inter (woff2) locally, or rely on system Roboto. Add Noto Sans Devanagari and Noto Sans Kannada (vendored) for Hindi and Kannada text.

**Patterns taken from the real Paytm apps (copy the feel, not exact screens):**
- Light grey page; white rounded cards with no borders; bold near-black section titles.
- 4-column grids of **solid navy circular icon buttons** with two-line labels underneath.
- Pill buttons: navy filled (primary) and light navy-tint filled (secondary).
- "View All →" text links in blue.
- A floating navy gradient pill at the bottom (Paytm's "Scan QR" style), used for the main action on each app screen.
- Status text: green for received/settled, red for failed/overdue, amber for warnings.
- Wordmark: plain text "**Pay**tm" styled in navy and cyan (not the official logo file). Footer label on every view: "Concept prototype · Team MerchantMavericks".

### 11.3 Global top bar (all views)
Left: "Bharosa" wordmark + "on Paytm" chip. Centre: view tabs (Live Demo · Soundbox · Merchant · Customer · Overview). Right: **sim date/time** (e.g., "Mon 26 Oct · 09:00"), "+1 day" button, language toggle (हिं / ಕನ್ನ), 🔊 toggle, **Reset**.

### 11.4 View 1: Live Demo (`#/live`), the main screen
Layout (1920×1080):
```
┌ top bar ─────────────────────────────────────────────────────────────────────┐
├──────────────────┬───────────────────────────┬───────────────────────────────┤
│  SOUNDBOX        │  MERCHANT PHONE (frame)   │  CUSTOMER PHONE (frame)       │
│  device render   │  Merchant Home (compact)  │  Customer app (focus: Ramesh) │
│  + Paytm button  │                           │                               │
│  panel           │                           │                               │
├──────────────────┴───────────────────────────┴───────────────────────────────┤
│ DEMO BAR: [◀ Beat 2/7 ▶ Next]  caption text ...      | TRACE (last 8 lines, live) │
│ CONTROLS (collapsible): UPI payment · Salary credited · +1 day · Inject fraud ring │
└───────────────────────────────────────────────────────────────────────────────┘
```
- Phone frames: 390×780 CSS-px rounded device outlines, each scrollable inside.
- Any device has an "⤢" button that switches to its full view.
- **Interaction: clicking the confirm QR on the Soundbox front screen = "customer scans".** It opens the Confirm sheet on the customer phone (fires nothing until the customer taps Confirm).
- Notifications slide in at the top of the relevant phone frame (from `notify` messages).
- Every state change animates briefly (status pill colour fade, number count-up).

### 11.5 View 2: Overview (`#/overview`), the pitch page
Scrollable sections:
1. **Hero:** "Every kirana is secretly a lender." Three facts with sources: 1.57 crore Paytm device merchant subscriptions (Paytm Q1 FY27); distributors want payment in 7–14 days (IIM Bangalore study); MYbank lends to small merchants at about 1% NPL (SMU case study).
2. **Lifecycle:** the five moments (1.3) as a horizontal stepper with icons.
3. **Live architecture:** the SVG diagram (11.9). Nodes glow for 1.2 s when a trace line with their node ID arrives. A side panel lists the trace lines with ms and source (`live` / `replay` / `template` badge).
4. **Notebook vs Bharosa:** Chart.js line charts from `/api/overview/compare`, two series over 30 simulated days: (a) money stuck in udhaar, (b) cumulative bad debt; plus KPI tiles: days to collect (median), bad udhaar prevented, working capital freed, supplier paid on time (Yes/No). Labelled "**Simulation on synthetic data**".
   - Comparison sim: the same personas and random draws, 30 days. *Notebook policy:* credit always given in full, no reminders, no mandates, no advance. *Bharosa policy:* guardrail splits, nudges for overdue ≥ 7 days (late payers shift −10 days with 60% probability, ASSUMPTION), salary-day mandates for 50% of `salary_day` personas, advance used when a gap appears.
5. **Risk console:** integrity alerts (the fraud beat lands here), with rule names spelled out.
6. **AI vs code:** a two-column table, "AI does (language, conversations, unclear payments, planning)" vs "Code does (limits, balances, debits, splits, scores)", plus the five safety rules (6.2).
7. **Tech stack and prototype → production table** (Section 16).
8. **Team:** Sujay Mohanty · Sukruth N · Rishi Sharma.

### 11.6 View 3: Soundbox (`#/soundbox`, also embedded in Live Demo)
**Device render (CSS):** a cyan/white body like the real AI Soundbox, with:
- **Top display** (merchant-facing, a strip about 340×90): band LED bar (green/amber/red), one line of text, a small "3 ms" latency tag, and a "Why?" link (opens reasons).
- **Front screen** (customer-facing, about 300×300): modes:
  - `idle`: Paytm-style payment QR with the store name.
  - `confirm_qr`: "Scan to confirm ₹200 udhaar · Lakshmi Stores" + QR (`bharosa://confirm/<token>`) + 10-minute countdown.
  - `pay_qr`: "Pay ₹140 now" UPI QR (shown alongside confirm when split).
  - `new_customer`: a mobile number input (simulated keypad).
  - `amount`: "₹500 received ✓" flash.
- **Speaker icon** with a pulse animation while audio plays.
- **Paytm Button:** opens the **Speak panel** below the device:
  - Preset chips (structured intents, no LLM): "Priya 340 udhaar", "Ramesh 340 udhaar", "Vikram 340 udhaar", "Anita 300 udhaar (new)", "Suresh 300 cash diye".
  - A free text box: "Type what the shopkeeper says…" (sent as `text`, so the Counter Agent runs live).
  - A note: "Paytm's Soundbox already converts speech to text; we receive the text."
- Under the device, when amber/red: buttons **"Use suggestion"** (default) and **"Override: give ₹340"**.

### 11.7 View 4: Merchant app (`#/merchant`), Paytm for Business style
**Home**
1. Header: "Lakshmi Stores" + "Jayanagar" + bell + "SM"-style avatar circle.
2. **Today's Collection** card: big number, "via UPI" subtitle, small sparkline.
3. **Morning briefing** card (Munim): text + ▶ play.
4. **Udhaar** card: Outstanding · Verified · Overdue (three numbers), "Pending confirmations: 1", "View Udhaar Book →".
5. **Due soon** card: Sharma Traders ₹18,000 · Fri 30 Oct · red pill "₹9,200 short" · button "Get Supplier Advance".
6. **Supplier Advance** card (when any advance exists): "Partner NBFC · paid Sharma Traders ₹9,200 ✓", a progress bar `repaid / total_due`, "20% of udhaar repayments", backstop date, state pill.
7. **Action grid** (navy circles): Udhaar Book · Collect · Supplier Advance · Ask Munim.
8. Cards for **"Who paid ₹500?"** (pending matches), **disputes**, **draft reminders** ("Approve 3 reminders").
9. Floating pill: "🎙 Ask Munim".

**Sub-screens**
- **Udhaar Book:** list (search box): name, outstanding, risk dot (band for ₹340 as an indicator), score band, overdue days, last paid. Tap → **Customer detail:** entries timeline with status pills, risk reasons ("Why?"), "Send reminder".
- **Collect:** recovery threads per customer, with draft approval and the agent's interpreted promise ("Promised ₹2,000 on 1 Nov").
- **Supplier Advance detail:** offer terms (amount, fee, total, split rate, backstop, paid-to), **Accept / Decline**, then the state timeline (offered → accepted → disbursed → repaying → closed) and repayment ledger (each split).
- **Ask Munim:** chat UI; shows "thinking…" while live; answers with action buttons; a collapsible "How I worked this out" list of tool steps.

### 11.8 View 5: Customer app (`#/customer`), Paytm consumer app style
Top-right "Viewing as: Ramesh ▾" switcher (demo affordance).

**Home**
1. Header: avatar circle "RK" + bell (badge on new notifications).
2. **Pending confirmation banner** (if any): "Lakshmi Stores: ₹200 on credit · Confirm" (opens the sheet).
3. **Bharosa Score card:** semicircle gauge 300–900, number, band, "+8 this week", "What affects my score →".
4. **My Dues** card: per store, amount, verified tick, oldest overdue, **Pay** button (fires `upi_payment` with the customer's VPA).
5. **Salary-day Auto-pay** card: active (cap, window, stores) or "Set up auto-pay" CTA.
6. **Action grid:** Pay Dues · Auto-pay · My Score · Messages.
7. Floating pill: "Scan QR" (in Live Demo, scanning = clicking the Soundbox QR).

**Sheets and sub-screens**
- **Confirm sheet:** store, amount, date, "Groceries" label; first time: two checkboxes, "Share my repayment record to build my Bharosa Score (data consent)" and a note that auto-pay is set up separately; **Confirm** (navy) / **Dispute** (outline). Dispute → reason chips + "Actual amount" input.
- **Auto-pay setup:** store, cap (default ₹3,000), window (1st–5th), summary in the style of Paytm AutoPay screens (mandate amount, frequency, validity), mock "Enter UPI PIN ●●●●" → **Activate**.
- **Messages:** chat with "Lakshmi Stores via Paytm"; incoming nudge, a text box for the judge to reply, and agent replies with action chips ("Set up auto-pay", "Pay ₹2,000 now").
- **History:** entries and repayments with status pills (Verified, Settled, Auto-paid, Disputed).
- **Score details:** factors (on-time rate, overdue, mandates), recent changes with reasons, rewards unlocked.

### 11.9 Architecture SVG (`static/img/architecture.svg`)
A hand-authored SVG matching 6.1. **Every box has an `id` equal to a trace node name** so JS can toggle a `.lit` class:

`soundbox`, `merchant_app`, `customer_app`, `router`, `counter_agent`, `recovery_agent`, `recon_agent`, `munim_agent`, `validator`, `ledger`, `risk`, `reconcile`, `mandate`, `forecast`, `advance`, `integrity`, `score`, `llm`, `tts`, `upi`, `lender`, `distributor`, `db`, `broadcaster`.

Group labels: "Paytm surfaces", "Agents (propose)", "Core (decides)", "Adapters", "Data". Colours: agents in cyan outline, core in navy fill, adapters in grey. Lit state: cyan glow plus a thicker stroke.

---

## 12. LLM and voice usage map

| Moment | Agent / service | Demo Mode | Free / live use |
|---|---|---|---|
| Preset Soundbox sentence | none (structured intent) | — | — |
| Free-typed Soundbox sentence | Counter Agent | — | **live** (`auto`) |
| Guardrail message | Template (optional LLM rephrase) | cached | cached |
| Soundbox spoken lines | Sarvam TTS | **pre-built audio** | live with cache |
| Morning briefing | Munim (phrase only) | cached | `auto` |
| Draft nudges | Recovery `draft_nudge` | cached | `auto` |
| Customer reply | Recovery `interpret_reply` | cached for the scripted reply | **live** ⭐ when a judge types |
| Unclear payment | Reconciliation Agent | cached | `auto` |
| Shopkeeper question | Munim tool loop | cached for the scripted question | **live** ⭐ when a judge asks |

Every trace line from an agent shows a badge: `LIVE`, `CACHED` or `FALLBACK`. Show this honestly; judges appreciate it.

---

## 13. Demo script (Demo Mode beats)

`POST /api/demo/next` runs one beat. Each beat: events → expected UI → caption. **Total ≈ 5 minutes.** Start with `reset`.

| Beat | Events fired | Expected UI | Caption |
|---|---|---|---|
| **0 · Morning** | `reset` (clock Mon 26 Oct 09:00) | Merchant home shows the briefing; the Soundbox speaks it; Due soon shows ₹9,200 short | "Morning: Bharosa briefs Lakshmi Stores in Hindi." |
| **1 · Guardrail** | `udhaar_spoken` Priya 340 → (pause 1.5 s) → `udhaar_spoken` Ramesh 340 | Priya: green "Safe"; Ramesh: **amber**, "Safe limit ₹200 · collect ₹140", spoken; front screen shows confirm QR ₹200 + pay QR ₹140 | "Same ₹340, two answers. The risk check took 3 ms; no AI decided the limit." |
| **2 · Confirm** | `upi_payment` Ramesh ₹140 with `ref=SALE-<entry_id>` (recorded as a sale) → (presenter clicks QR) → `customer_confirm` | Customer phone shows the Confirm sheet; on Confirm, the entry pill turns **Verified**; the merchant ledger updates; the diagram lights ledger → integrity → score | "Ramesh confirms in his own Paytm app. A diary entry becomes a verified receivable." |
| **3 · Recovery (AI)** | `nudges_requested {C_RAMESH}` → `nudges_approved` → `customer_reply` "Salary 1 tareekh ko aati hai, tab pura de dunga" → (Ramesh taps "Set up auto-pay") `mandate_created` cap 3,000, 1st–5th | Message arrives on the customer phone; the agent reads the reply → "Promise: ₹2,000 on 1 Nov"; suggests auto-pay; mandate card turns active; score +5 | "The AI understood a Hinglish reply and turned it into a promise, then a mandate. No chasing." |
| **4 · Supplier Advance (AI)** | `POST /agents/munim/ask` "Friday ko Sharma ko 18,000 kaise dunga?" → merchant taps action `offer_advance B1` → `advance_accept` | Munim answer with tool steps; the offer card (₹9,200, fee ₹138, split 20%); accept → "Partner NBFC paid ₹9,200 to Sharma Traders ✓", state **repaying** | "Munim checked the forecast, the dues and eligibility. The lender pays the distributor directly." |
| **5 · Salary day** | `advance_day` × 6 (to Sun 1 Nov) → daily jobs → mandate sweeps for Ramesh + 8 others | Ramesh: "₹2,000 auto-paid ✓", dues 0, score **680 → 692**; the merchant advance progress bar jumps (≈ ₹2,200 repaid via 20% splits); the Soundbox announces receipts | "Salary lands, dues clear themselves, and 20% of each repayment goes to the lender." |
| **6 · Fraud ring** | `inject_fraud_ring {S2}` | The Risk console shows "Sai Kirana: possible fake-udhaar ring (shared device, round amounts, instant confirms, money cycle)", advance blocked | "Fake udhaar to farm loans? Blocked by graph rules before any money moves." |

**Optional beat (sandbox, for judges):** 3-customer comparison (Priya / Ramesh / Vikram presets), an unclear-payment match (Kamala Kumar ₹500 → Ramesh), Kannada toggle, dispute flow.

**Reset between judges:** the top bar **Reset** returns to beat 0 in under 5 s.

---

## 14. Repository layout

```
bharosa/
├── README.md                    # how to run, demo controls, troubleshooting
├── .env.example
├── requirements.txt
├── Makefile                     # make seed | run | test | audio | record
├── app/
│   ├── main.py                  # FastAPI app, static mount, routers, startup seed-if-missing
│   ├── config.py                # env settings (pydantic-settings)
│   ├── db.py                    # engine, session, init
│   ├── models.py                # SQLModel tables (Section 8)
│   ├── clock.py                 # sim clock
│   ├── events/
│   │   ├── schemas.py           # Pydantic payloads per event type
│   │   ├── router.py            # POST /api/events, dispatch, lock
│   │   └── handlers.py          # one function per event type
│   ├── core/
│   │   ├── ledger.py  risk.py  score.py  reconcile.py  mandates.py
│   │   ├── forecast.py  advance.py  integrity.py  policy.py  collector.py
│   ├── agents/
│   │   ├── base.py              # call_llm, repair retry, trace
│   │   ├── counter.py  recovery.py  recon_agent.py  munim.py
│   │   ├── validators.py  fallbacks.py
│   │   └── prompts/             # counter.md recovery_draft.md recovery_reply.md recon.md munim.md briefing.md
│   ├── adapters/
│   │   ├── llm.py  tts.py  upi.py  mandate.py  lender.py  distributor.py  soundbox.py
│   ├── realtime/
│   │   ├── broadcaster.py  trace.py  snapshot.py
│   ├── api/
│   │   ├── routes_core.py  routes_agents.py  routes_demo.py  routes_overview.py
│   └── sim/
│       ├── seed.py  personas.py  demo_script.py  compare.py
├── static/
│   ├── index.html
│   ├── css/  tokens.css base.css devices.css soundbox.css merchant.css customer.css overview.css
│   ├── js/   store.js api.js router.js live.js soundbox.js merchant.js customer.js overview.js trace.js demo.js
│   ├── vendor/ alpine.min.js chart.umd.min.js qrcode.min.js fonts/
│   ├── img/  architecture.svg
│   └── audio/                   # generated by scripts/prebuild_audio.py
├── fixtures/llm_cache/          # recorded LLM outputs (committed)
├── scripts/
│   ├── prebuild_audio.py  record_llm.py  smoke_demo.py
└── tests/
    ├── test_risk.py  test_ledger.py  test_reconcile.py  test_forecast.py
    ├── test_advance.py  test_integrity.py  test_agents_validators.py  test_demo_flow.py
```

### 14.1 Environment (`.env.example`)
```
SARVAM_API_KEY=
SARVAM_CHAT_MODEL=sarvam-105b
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER_HI=          # VERIFY a valid speaker for the model
SARVAM_TTS_SPEAKER_KN=
LLM_MODE=auto                   # auto | live | replay | record | template
LLM_TIMEOUT_S=8
FALLBACK_LLM_BASE_URL=          # optional OpenAI-compatible
FALLBACK_LLM_API_KEY=
FALLBACK_LLM_MODEL=
DB_PATH=bharosa.db
SEED=42
```

### 14.2 Dependencies (`requirements.txt`)
`fastapi`, `uvicorn[standard]`, `sqlmodel`, `pydantic>=2`, `pydantic-settings`, `sse-starlette`, `httpx`, `sarvamai`, `networkx`, `faker`, `python-dotenv`, `pytest`.

### 14.3 Run
```
pip install -r requirements.txt
cp .env.example .env            # add SARVAM_API_KEY
make seed                       # builds bharosa.db
make audio                      # prebuild voice clips (needs key; optional)
make record                     # record LLM outputs for demo beats (needs key; optional)
make run                        # uvicorn app.main:app --port 8000 → open http://localhost:8000
make test
```
Without a key, everything runs on `template` and `replay` mode (text only, no audio unless pre-built).

---

## 15. Non-functional requirements

| Requirement | Target |
|---|---|
| Guardrail compute | p95 < 50 ms in-process; shown in the UI |
| Event → all screens updated | < 500 ms (no LLM) |
| Live LLM calls | ≤ 8 s timeout, then fallback; "thinking…" indicator |
| Reset | < 5 s |
| Offline | Full demo runs with no internet (`LLM_MODE=replay`, pre-built audio, vendored JS) |
| Determinism | Same seed + same beats → identical numbers (tests) |
| Accessibility | Body text ≥ 14 px in phone frames, ≥ 16 px elsewhere; status shown by text as well as colour |
| Audit | Every event, agent call and money movement is in `events` + `trace` |

---

## 16. Prototype → production mapping

| Concern | Prototype | Production |
|---|---|---|
| Core logic (risk, ledger, reconcile, mandates, forecast, advance, integrity, score) | **Same code** | **Same code** |
| Agents and validators | Same | Same, plus evaluation sets and monitoring |
| Event flow | In-process, single lock | Kafka / managed queue, idempotent consumers |
| Database | SQLite | Postgres (ledger), partitioned event store |
| Risk feature cache | In-process | Redis |
| Soundbox | Browser simulator | Paytm device platform (ASSUMPTION: event contract proposed by us) |
| Customer surface | Mock Paytm app screens | Paytm app module + push notifications |
| UPI / AutoPay | Simulated | Paytm UPI, AutoPay mandates; NPCI agent mandates (UAP) when live |
| Lender | Simulated Partner NBFC | Paytm lending partners via partner APIs |
| Consent | Table rows | Consent manager aligned with the DPDP Act; account aggregator where relevant |
| Fraud | Rule graph | Rule graph + ML; signal sharing with RBI's DPIP when available |
| Clock | Simulated | Real time, scheduled jobs |
| Observability | Trace table + SSE | OpenTelemetry, dashboards, alerting |

**Line for judges:** "Swap the adapters and this runs on Paytm."

---

## 17. Build plan and acceptance checks

Owners are suggestions: **Sujay** (backend core and agents), **Sukruth** (frontend), **Rishi** (sim, data, overview, demo).

### M1. Skeleton and seed (Sujay + Rishi)
- FastAPI app, models, `seed.py`, clock, `/api/health`, `/api/snapshot`, SSE stream with an initial snapshot, static `index.html` loads.
- ✅ `make seed && make run` works; `/api/snapshot` returns Lakshmi Stores with outstanding ≈ ₹45,000; the 5 named customers have the exact values in 4.2.

### M2. Credit sale end to end (Sujay + Sukruth)
- Events `udhaar_spoken` (structured), `customer_confirm`, `customer_dispute`, `entry_corrected`, `guardrail_override`; risk engine; ledger; trace; Soundbox view (top/front/speak panel); Customer Confirm sheet; Live Demo layout.
- ✅ Ramesh ₹340 → amber, limit **₹200**, collect **₹140**; Priya green; Vikram red; Anita starter ₹500. Clicking the QR opens the Confirm sheet; Confirm → **Verified** on both phones within 500 ms. `test_risk.py` passes.

### M3. Repayments and score (Sujay)
- `upi_payment` (rules 1–2), FIFO allocation, `cash_reported`, score service, payment alert audio hook.
- ✅ Ramesh pays ₹500 → oldest entries cleared FIFO; excess handled; score changes per 7.4. `test_ledger.py`, `test_reconcile.py` pass.

### M4. Merchant and Customer apps (Sukruth)
- Merchant home + Udhaar Book + customer detail; Customer home + Score + Dues + History; Paytm styling per 11.2.
- ✅ Visual check against the screenshots' feel; all values come from the snapshot (no hard-coded numbers in JS).

### M5. Forecast, Supplier Advance, mandates (Sujay + Rishi)
- Forecaster, `advance_day` daily jobs, mandates + `salary_credited`, advance offer/accept/split, Due soon + Advance cards, Auto-pay sheet.
- ✅ The B1 gap is exactly **₹9,200**; advance ₹9,200, fee ₹138, total ₹9,338; after the salary-day sweep, `advance.repaid` ≈ ₹2,200 and every split row has `lender_share = 20%` (capped). `test_forecast.py`, `test_advance.py` pass.

### M6. Agents (Sujay)
- LLM gateway (modes, cache), Counter, Recovery (both modes), Reconciliation, Munim (tool loop), validators, fallbacks, prompt files; Messages and Ask Munim UIs.
- ✅ With `LLM_MODE=template` the whole demo still runs. With a key: the scripted reply → promise {2000, 1 Nov}, suggest_mandate=true; the Munim scripted question → answer mentions ₹9,200 and offers `offer_advance B1`; the Kamala Kumar payment → C_RAMESH ≥ 0.85. Validator tests reject invented ₹ figures and out-of-policy plans.

### M7. Integrity, Overview, voice, Demo Mode (Rishi + Sukruth)
- Integrity rules + `inject_fraud_ring`; Overview page with the live SVG, compare charts, risk console; TTS adapter + prebuild; `demo_script.py` + demo bar + captions; Kannada toggle.
- ✅ The fraud beat flags S2 with R1, R3, R4, R5 and blocks the advance; diagram nodes light up on trace; `smoke_demo.py` runs beats 0–6 headless and asserts the key numbers; `make record` + `LLM_MODE=replay` makes the demo fully offline.

### M8. Polish and rehearsal (all)
- Animations, the "Why?" reasons, empty states, toasts, error handling, README.
- ✅ Full demo three times in a row with Reset between runs; the offline run passes with Wi-Fi off; a 2-minute demo video is recorded.

**Cut order if time is short:** Kannada → compare charts → dispute flow → reconciliation agent (keep the rules) → Munim tool loop (keep the scripted answer via replay). **Never cut:** guardrail, scan-to-confirm, Recovery reply (live), salary-day sweep, Supplier Advance with split, trace + lit diagram, Reset.

---

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Venue Wi-Fi fails | `LLM_MODE=replay`, pre-built audio, vendored assets; the live moments fall back automatically |
| LLM returns bad JSON or invented numbers | Pydantic + repair retry + validators + deterministic fallbacks |
| Browser blocks audio | "Start demo" click unlocks audio; text is always shown |
| Demo state drifts | One-click Reset; deterministic seed; `smoke_demo.py` before presenting |
| Judge asks "what's real?" | Trace badges (LIVE/CACHED/FALLBACK) + the Overview "Prototype vs production" table |
| Soundbox API unknown | Stated as our proposed event contract (ASSUMPTION) |
| Sarvam specifics change | Model, speaker and language codes come from env; VERIFY at build time |

---

## 19. Assumptions and items to verify

- `ASSUMPTION` The Soundbox front screen faces the customer (based on the product image showing the payment QR on it) and can show a dynamic QR.
- `ASSUMPTION` Paytm's Soundbox voice layer can deliver transcribed text or structured intents to a partner service.
- `ASSUMPTION` A lender would accept split-settlement repayment from udhaar repayments routed through Paytm (a standard merchant cash advance pattern).
- `ASSUMPTION` Nudge effect sizes in the comparison sim (labelled as simulation).
- `VERIFY` Sarvam: `sarvam-105b` availability on the hackathon credits; `json_schema` response format behaviour; the Kannada `language_code` (`kn-IN`); valid speaker names for `bulbul:v3`.
- `VERIFY` Whether organisers provide Paytm sandbox or MCP access on the day (stretch goal only).
- NPCI's Unified Agent Protocol is **proposed, not live**. Present mandates as UPI AutoPay today, "UAP-ready" tomorrow.
- RBI's DPIP is being built with banks. Present it as "ready to share signals", not as an integration.

---

## 20. Pitch Q&A cheat sheet

| Question | Answer |
|---|---|
| Isn't this Khatabook? | Khatabook records. We check risk before credit, get customer verification, collect automatically and fund the shop. |
| Why would a customer confirm their own debt? | One scan; it builds their Bharosa Score, which raises limits at every Paytm store. |
| Is the AI deciding credit? | No. A transparent formula decides; the AI handles language, conversations and unclear payments, and the merchant has the final say. |
| Why agents at all? | Only where the input is messy human language or ambiguous data. Four agents, and every proposal is validated by code. |
| What's real? | All logic and agents are real code; Paytm rails are simulated behind adapters with production-shaped interfaces. |
| Who takes the risk? | Udhaar risk stays with the merchant, as today, but is caught earlier. Advances come from regulated lenders against verified receivables. |
| Privacy? | Merchants see a limit and a band, never other stores' data. Data sharing and auto-pay are separate consents. |
| How does Paytm make money? | Lending distribution fees (advances, merchant loans), bank-paid credit line acquisition, collections services, optional Bharosa Pro. |
| How does it scale? | The same code on Kafka, Postgres and Redis; agents are stateless; the Soundbox and app already reach 1.57 crore merchant subscriptions. |
