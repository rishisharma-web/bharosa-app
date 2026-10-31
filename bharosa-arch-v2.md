# Bharosa Architecture v2: Final Target State

**Team MerchantMavericks** · Sujay Mohanty · Sukruth N · Rishi Sharma
Paytm Build for India AI Hackathon, Bengaluru · Track 1: Merchant Growth AI · Finals: Sat 31 Oct 2026
**Companion documents:** `bharosa-overview-v2.md` (human-readable overview) and `bharosa-explained.md` (the complete explanation: problem, production architecture, the role of AI and the agents, the pitch and tough questions). The Presentation (§10.8) is built from `bharosa-explained.md`.

---

## 0. Read this first (instructions for the coding agent)

1. **This document describes the final state of the application.** The v1 codebase (`bharosa-arch-e2e.md`) is already built. Your job is to **transform that codebase into exactly what this document describes.**
2. **Where v1 and v2 differ, v2 wins.** Anything in v1 that this document does not mention as kept (Section 2) should be removed or disabled.
3. **Simplicity is a requirement.** Do not add features, simulation, personas, clocks or controls beyond this spec. If something feels missing, it was cut on purpose (Section 2.3).
4. **Numbers are contracts.** The seed data and formulas produce exact values (Section 3–4). Tests in Section 14 assert them. Do not tune formulas to "look nicer".
5. **Golden rule:** *AI proposes, code decides.* No AI output ever changes money, limits, scores or ledger state without a deterministic validator. With `SARVAM_ENABLED=false` (the default), **the entire app must work fully** using rules and templates.
6. **Never hard-code, print, log or commit the Sarvam API key.** It is read only from the environment.
7. Build in the order of Section 15. Run the acceptance checks after each milestone.

---

## 1. The target in one page

**Bharosa turns udhaar (informal shop credit) from a cost into a growth engine** for Paytm merchants. Three pillars:
- **Sell more, safely:** a guardrail suggests a safe credit limit; customers can carry their Bharosa Score to a new shop (with consent); regulars get a predicted monthly basket.
- **Get paid without chasing:** customers confirm credit in their own phone app by scanning a QR; reminders understand replies; compliant salary-week auto-pay.
- **Stock up without cash:** a Diwali stock plan, funded by a Stock Advance that a partner lender pays directly to the distributor and that is repaid from 20% of incoming repayments.

**The prototype consists of five web apps served by one FastAPI backend, gathered on one home page (`/`, §10.7) with three sections: Live Demo, Overview and Presentation.**

| App | URL | Who uses it | Login |
|---|---|---|---|
| **Home** (three sections: Live Demo · Overview · Presentation) | `/` | Everyone; the screen on stage | None (the Live Demo section asks for the admin key) |
| Merchant app (Paytm for Business style) | `/merchant` | Lakshmi Stores owner | Phone + OTP |
| Customer app (Paytm app style, phone-first) | `/customer` | Priya, Ramesh, Vikram, Anita | Phone + OTP, or a login QR |
| AI Soundbox simulator | `/soundbox` | The counter device (on the laptop) | None (fixed to Lakshmi Stores) |
| Presenter screen | `/demo` | The team on stage | Admin key |
| Overview (one-page summary) | `/overview` | Anyone | None |
| Presentation (the pitch as slides, also a PDF) | `/presentation` | The team on stage; anyone rehearsing | None |

**The headline moment:** the Soundbox on the laptop shows a QR for a credit entry; a **real phone** running the customer app scans it; the customer confirms; the laptop's Soundbox and merchant app update within about a second.

**What the demo is NOT:** no step-by-step demo mode, no controls panel, no simulated clock or time travel, no generated crowd of customers, no background simulation. Every visible change is caused by a person using one of the apps.

---

## 2. What changes from v1

### 2.1 Keep (adapt as described later)
| v1 component | v2 treatment |
|---|---|
| FastAPI app, SQLite via SQLModel, Pydantic schemas | Keep |
| Ledger + entry state machine | Keep, with the simplified states in §4.3 |
| Risk engine | Replace the formula with §4.2 (adds network trust and exposure cap) |
| Bharosa Score service | Replace with the **computed-from-history** formula in §4.1 (no stored score deltas) |
| Supplier Advance + split router | Keep the split logic; simplify sizing and triggers (§4.6) |
| Counter Agent, Recovery Agent | Keep, rewritten against the new AI layer (§9) |
| Munim | Becomes the **Growth Agent**: weekly plan wording + optional Q&A (§9) |
| SSE broadcaster | Keep, but send **"changed" pings only** (§8) |
| Design tokens (`tokens.css`), Alpine.js, vendored assets | Keep |

### 2.2 Add
- **Logins and roles** (merchant, customer, admin), separate cookies per app (§6).
- **Pending requests** (confirm and share-score) with QR links to the customer app (§5, §11).
- **Phone scanning** via a QR scanner in the customer app, over an HTTPS tunnel (§11).
- **Portable Trust**: score sharing with consent; new-to-store limits; network exposure cap (§4.2, §5.2).
- **Network history** for Anita via a pseudo-store "Other Paytm shops" (§3.4).
- **Growth plan** with 3 actions (§4.7).
- **Diwali stock plan** (§4.6).
- **Priya's monthly basket** (§4.8).
- **Compliant salary-week auto-pay** setup with schedule display (§4.9).
- **AI toggle** `SARVAM_ENABLED` with Sarvam chat, speech-to-text and text-to-speech (§9).
- **Credit line on UPI** as a simulated payment method for the "pay now" part (§4.5).

### 2.3 Remove (delete code, routes, UI and tests)
| Remove | Why |
|---|---|
| Demo Mode (`demo_script.py`, `/api/demo/next`, `/goto`, demo bar, captions) | No step-by-step demo |
| Controls panel (UPI payment, salary credited, +1 day, add bill, inject fraud ring, customer picker list) | Every change comes from a real app interaction |
| Sim clock advancing, `advance_day`, daily jobs, salary-day sweep | Fixed demo date |
| 60 generated customers, personas, random generator, 90-day history | 4 named customers + 6 read-only regulars |
| Stores S2, S3, S4; fraud-ring injection; integrity rules R2–R6 | One store + network record; one lightweight shared-device check (§4.10) |
| Reconciliation Agent and unclear-payment matching | Every payment comes from the customer's own app |
| Dispute correction flow | Dispute only marks the entry; the merchant can cancel it |
| 14-day forecaster | One number: cash available by the bill's due date |
| Comparison simulation and charts (`compare.py`, `/api/overview/compare`) | Not needed |
| LLM record/replay cache, prompt-version cache keys, `make record` | Replaced by the simple AI toggle |
| Pre-built audio (`prebuild_audio.py`, `static/audio/`), morning briefing, read-aloud | Speech only when the AI toggle is on, and only one short line |
| Language toggle in the UI | The UI is English; spoken and customer messages use each person's language |
| Live architecture SVG lighting | Optional stretch only (§15) |
| Mock or hard-coded data in frontend JS | All data comes from APIs |

---

## 3. The fixed demo world (seed)

### 3.1 Demo date
`DEMO_DATE=2026-10-31` (Saturday). All "days overdue", "today", due dates and schedules are computed against this date. **There is no clock that moves.** `reset` restores the seed.

### 3.2 Store
| Field | Value |
|---|---|
| id | `S1` |
| name | Lakshmi Stores |
| area | Jayanagar, Bengaluru |
| owner login phone | `9000000001` |
| voice language (Soundbox speech) | `kn-IN` (Kannada) |
| starter_limit (new customers without shared score) | ₹500 |
| due_days (credit period) | 30 |
| upi_sales_today (display) | ₹10,240 |
| cash_available_by_bill_due (for the Diwali gap) | ₹8,800 |
| UPI ID shown on the shop QR | `lakshmistores@ptyes` |

Pseudo-store `NET` = **"Other Paytm shops"** (holds Anita's network history; no login; never shown by name to the merchant).

### 3.3 The four loginable customers
| id | Name | Phone (login) | VPA | Language | Profile |
|---|---|---|---|---|---|
| `C_PRIYA` | Priya Nair | 9000000011 | priya.n@ptyes | en-IN | Good credit |
| `C_RAMESH` | Ramesh Kumar | 9000000012 | ramesh.k@ptyes | hi-IN | Not so great |
| `C_VIKRAM` | Vikram Rao | 9000000013 | vikram.r@ptyes | hi-IN | Bad credit |
| `C_ANITA` | Anita Desai | 9000000014 | anita.d@ptyes | kn-IN | New to this shop, known to the network |

**Seeded history (exact; dates are illustrative but must keep these counts and open entries):**

| Customer | Store | Settled on time | Settled late | Written off (never repaid) | Open entries |
|---|---|---|---|---|---|
| Priya | S1 | 12 (Apr–Oct 2026, ₹300–1,900, paid in 3–10 days) | 0 | 0 | none |
| Ramesh | S1 | 8 | 2 (paid 20–30 days late) | 0 | **₹1,700**, created 12 Sep 2026, due 12 Oct (**19 days overdue**) |
| Vikram | S1 | 2 | 5 | 1 (₹800, written off Jul 2026) | **₹2,600**, created 21 Aug 2026, due 20 Sep (**41 days overdue**) |
| Anita | NET | 12 | 1 | 0 | **₹600**, created 20 Oct, due 19 Nov (not overdue) |

All seeded open entries are `verified`. Priya's 12 entries carry `items` (§3.6) so her basket can be predicted.

### 3.4 Six read-only regular customers (S1, no login)
They make the ledger look real and provide verified receivables for the Stock Advance. Each has 6 entries settled on time and one open verified entry, created within the last 20 days (not overdue).

| Name | Open verified dues |
|---|---|
| Suresh Gowda | ₹4,200 |
| Kavya Rao | ₹3,800 |
| Imran Sheikh | ₹3,600 |
| Meena Iyer | ₹3,500 |
| Rohit Shetty | ₹3,400 |
| Lata Kulkarni | ₹3,000 |
| **Total** | **₹21,500** |

Store totals at reset: **udhaar outstanding ₹25,800** (1,700 + 2,600 + 21,500); **overdue ₹4,300** (Ramesh + Vikram).

### 3.5 Distributor and lender
- Distributor: **Sharma Traders** (festive categories).
- Lender: **Partner NBFC (simulated)**. Fee 1.5%, split 20%, backstop 30 days.
- Credit line on UPI: **Partner Bank (simulated)**.

### 3.6 Catalogue (subset that must exist; add more items freely)
| sku | name | price |
|---|---|---|
| ATTA10 | Wheat atta 10 kg | 480 |
| RICE5 | Rice 5 kg | 450 |
| TOOR2 | Toor dal 2 kg | 320 |
| OIL1 | Sunflower oil 1 L | 150 |
| SUG2 | Sugar 2 kg | 100 |
| TEA250 | Tea 250 g | 140 |
| SALT1 | Salt 1 kg | 28 |
| DET1 | Detergent 1 kg | 32 |

**Priya's monthly basket** (appears in her purchases in the first week of Aug, Sep and Oct): ATTA10 ×1, RICE5 ×1, TOOR2 ×1, OIL1 ×2, SUG2 ×1, TEA250 ×1, SALT1 ×1, DET1 ×1 = **₹1,850**.

### 3.7 Diwali profile (S1)
Diwali: **Sun 8 Nov 2026**. Last year's weekly sales by category (baseline = average of the 4 weeks before Diwali 2025; festive = Diwali week 2025):
```json
{"festival": "Diwali", "date": "2026-11-08", "supplier": "Sharma Traders", "bill_due": "2026-11-06",
 "weekly_baseline": {"sweets_dryfruits": 4000, "oil_ghee": 9000, "snacks": 8000, "puja_items": 4500, "staples": 30000},
 "festive_week":    {"sweets_dryfruits": 9600, "oil_ghee": 16200, "snacks": 13600, "puja_items": 13500, "staples": 36000}}
```

---

## 4. Core rules (deterministic code)

### 4.1 Bharosa Score (computed live from history; never stored)
```
score(customer) = clamp(300, 900,
      600
    + 15 × count(entries settled on or before due date)      # all stores, including NET
    − 10 × count(entries settled after due date)
    −  2 × max_overdue_days(open entries, all stores)        # 0 if none overdue
    − 60 × count(entries written off) )
```
Return a **breakdown** for the UI: `[{label: "12 on-time repayments", points: +180}, …]`.

| Customer | Calculation | Score | Band |
|---|---|---|---|
| Priya | 600 + 180 | **780** | Strong |
| Ramesh | 600 + 120 − 20 − 38 | **662** | Good |
| Vikram | 600 + 30 − 50 − 82 − 60 | **438** | Building |
| Anita | 600 + 180 − 10 | **770** | Strong |
| Each regular | 600 + 90 | 690 | Good |

Bands: 300–549 Building · 550–699 Good · 700–799 Strong · 800–900 Excellent.

### 4.2 Safe limit (the Udhaar Guardrail)
```
S             = score(customer)
base          = 500 + (S − 300) / 600 × 4500              # S=300 → ₹500; S=900 → ₹5,000
net_out       = customer's open outstanding across ALL stores
exposure_room = max(0, base − net_out)
here          = customer has any entries at this store?

if not here and no entries anywhere:          safe = store.starter_limit
elif not here and no active score_share:      safe = store.starter_limit          # no consent → no network data
elif not here and score shared:               safe = min(floor50(base × 0.4), 1500, exposure_room)
else:                                                                            # existing customer here
    D     = max overdue days of open entries at THIS store
    m     = 1.0 if D == 0 else 0.75 if D <= 14 else 0.6 if D <= 30 else 0.0
    O     = open outstanding at THIS store
    safe  = min(base × m − O, exposure_room)
safe = clamp(0, 5000, floor50(safe))                      # floor50 = round down to a multiple of 50

band        = "green" if amount <= safe else ("red" if safe == 0 else "amber")
credit_now  = min(amount, safe)
collect_now = amount − credit_now
```
**Contract table (tests):**
| Customer | Request | base | safe | Band | credit / collect |
|---|---|---|---|---|---|
| Priya | ₹340 | 4,100 | **4,100** | green | 340 / 0 |
| Ramesh | ₹340 | 3,215 | **200** | amber | 200 / 140 |
| Vikram | ₹340 | 1,535 | **0** | red | 0 / 340 |
| Anita, not shared | ₹2,000 | 4,025 | **500** | amber | 500 / 1,500 |
| Anita, shared | ₹2,000 | 4,025 | **1,500** | amber | 1,500 / 500 |

**Reasons** (shown to the merchant under "Why?"), e.g. Ramesh: "Score 662 → base ₹3,215", "₹1,700 overdue for 19 days → ×0.6", "Already owes ₹1,700 here". Anita (shared): "New to this shop: 40% of network limit, max ₹1,500", "Network exposure room ₹3,425". **Never** name another store or show per-store amounts to the merchant.

**Verdict text** (merchant-facing; English template; when AI is on, also spoken in the store's language):
- green: "Safe. {name} can take up to ₹{safe}."
- amber: "Caution. Give ₹{credit_now} on credit, collect ₹{collect_now} now."
- red: "High risk. Collect full payment (₹{amount})."
- new, waiting for share: "New customer. Ask them to scan to share their Bharosa Score. Starter limit ₹{starter}."

### 4.3 Entry states
```
proposed ──confirm (customer)──► verified ──partial──► partly_paid ──full──► settled
   ├──dispute (customer)──► disputed ──cancel (merchant)──► cancelled
   └──expires (15 min, no confirm)──► expired
verified/partly_paid can be written_off (seed only in v2)
```
- `due_date = created_at + store.due_days`. Overdue days are derived: `max(0, DEMO_DATE − due_date)` while not settled.
- A `proposed` entry is created **only after** the merchant accepts the guardrail suggestion (or overrides it).
- `basket` entries are created directly as `verified` (in-app acceptance is the confirmation).

### 4.4 Pending requests (the bridge between Soundbox and phone)
Table `pending_requests(token, kind, store_id, customer_id, amount_requested, credit_now, collect_now, entry_id, status, created_at, expires_at)`.
- `kind = "confirm"` for a known customer at this store; `kind = "share"` for a customer new to this store.
- `token` = 22-char URL-safe random string; expires in 15 minutes.
- `status`: `open → completed | declined | expired`.
- The QR encodes `${PUBLIC_BASE_URL}/c/r/{token}`.
- **Identity rule:** when a logged-in customer opens the link, the server checks `session.customer_id == pending.customer_id`. If not, return "This request is for another customer" (no details).

### 4.5 Payments, allocation and split
Table `payments(id, store_id, customer_id, amount, method, purpose, lender_share, merchant_share, created_at)`.
- `method`: `upi` | `credit_line` (simulated Partner Bank) | `cash` | `autopay`.
- `purpose`: `sale` (the "collect now" part of a purchase; **never** allocated to dues) | `repayment`.
- **Allocation (repayments):** FIFO over the customer's open entries at the store, oldest `created_at` first. Any excess becomes `credit_balance` on `store_customers`.
- **Split (repayments only, method `upi` or `autopay`):** if the store has an advance in state `repaying`:
  `lender_share = min(round(amount × 0.20), total_due − repaid)`, `merchant_share = amount − lender_share`; `advance.repaid += lender_share`; close the advance when fully repaid.
- **Contract:** after the advance is accepted, Ramesh pays ₹500 → lender ₹100, merchant ₹400; his ₹1,700 entry becomes `partly_paid` with ₹1,200 remaining.

### 4.6 Diwali stock plan and Stock Advance
**Festive plan** (computed from §3.7):
```
for each category c with uplift_c = festive_c / baseline_c ≥ 1.3:      # staples (1.2) excluded
    extra_sales_c = baseline_c × (uplift_c − 1)
expected_extra = Σ extra_sales_c                                   = 5,600 + 7,200 + 5,600 + 9,000 = ₹27,400
order_total    = round_to_100(expected_extra × (1 − 0.18) × 0.8)    = round_to_100(17,974) = ₹18,000
overall_uplift = Σ festive / Σ baseline = 88,900 / 55,500            ≈ 1.6
```
**On approval of the festive action:** create bill `B1` (Sharma Traders, ₹18,000, due Fri 6 Nov 2026) → `gap = order_total − cash_available_by_bill_due = 18,000 − 8,800 = ₹9,200` → create a Stock Advance offer automatically.

**Stock Advance sizing:**
```
V_eligible = verified open receivables at S1 from customers with score ≥ 550
           = 21,500 (regulars) + 1,700 (Ramesh) = 23,200        # Vikram excluded (438)
cap        = 0.4 × V_eligible = 9,280
amount     = min(gap, cap, bill.amount) = 9,200
fee        = round(amount × 0.015) = 138;  total_due = 9,338
split_rate = 0.20;  backstop = accepted_at + 30 days (30 Nov 2026)
```
States: `offered → accepted → disbursed → repaying → closed` | `declined`. Accepting moves straight through `disbursed` ("Partner NBFC paid Sharma Traders ₹9,200") to `repaying`; bill B1 is marked paid (₹9,200 by lender + ₹8,800 by store).

### 4.7 Growth plan (code computes; AI only words it)
Generated on reset (and regenerated after any approval to update states). Three candidate actions, ranked by expected impact:

| Rank | action_id | Type | Facts (code) | Expected impact | On approve |
|---|---|---|---|---|---|
| 1 | `A_DIWALI` | festive_stock | Diwali 8 Nov; last year ≈1.6× sales; order ₹18,000 from Sharma Traders (sweets & dry fruits, oil & ghee, snacks, puja items) | **+₹27,400** expected sales | Create B1 → gap → Stock Advance offer |
| 2 | `A_REMIND` | collect_overdue | Ramesh ₹1,700 (19 days), Vikram ₹2,600 (41 days) | **₹4,300** overdue | Send reminder messages to both (§4.11) |
| 3 | `A_BASKET` | monthly_basket | Priya buys the same basket every month; ₹1,850; within her limit | **₹1,850** order | Send basket offer to Priya (§4.8) |

Action states: `proposed → approved → done`. Table `growth_actions(id, store_id, action_id, type, facts JSON, impact INT, rank INT, title, why, state, updated_at)`.

### 4.8 Monthly basket (Priya)
```
cycles   = purchases in days 1–7 of each of the last 3 calendar months (Aug, Sep, Oct)
eligible = purchases present in ≥ 2 of 3 cycles
items    = SKUs present in ≥ 2 cycles, qty = median qty
value    = Σ qty × price                                    = ₹1,850 for Priya
```
Offer only if `value ≤ safe_limit`. States: `offered → accepted → delivered` | `declined`. Accepting creates a `verified` entry (source `basket`, items attached). Merchant sees it in **Orders** and can mark it delivered.

### 4.9 Salary-week auto-pay (compliant design; set up and scheduled, not executed)
Real-world basis: UPI AutoPay mandates are approved by the customer but **each debit is triggered by the merchant side**, after a **pre-debit notification at least 24 hours before**. Debits under ₹15,000 need no re-authentication. "As presented" frequency allows a variable amount up to a cap.

Bharosa's design:
- The customer sets up a mandate for Lakshmi Stores with a **cap** (default ₹3,000) and a **collection day** (default the 2nd of each month).
- Each month, the day before collection, Bharosa sends a **pre-debit notice** with the exact verified dues (never more than the cap). The customer can **skip** that month in the app.
- On the collection day, the merchant side triggers the debit; the split (§4.5) applies.

**In the prototype:** only setup and schedule. After Ramesh sets it up: "Next collection: Mon 2 Nov 2026 · up to ₹3,000 · amount = your verified dues (now ₹1,900) · notice on Sun 1 Nov". **No execution, no clock.** Table `mandates(id, customer_id, store_id, cap, collection_day, status, created_at)`; the schedule is computed from `DEMO_DATE`.

### 4.10 Integrity (lightweight)
On every confirmation, record `device_id` (a random ID stored in the customer app's localStorage, sent with each confirm). If the same `device_id` confirmed entries for **a different customer** at the same store in the last 24 hours, flag the new entry `integrity_flag=true`, exclude it from `V_eligible`, and add an activity line "Possible shared device: entry excluded from advance eligibility". (The full fraud-ring explanation lives on the Overview page.)

### 4.11 Reminders, replies and promises
- Approving `A_REMIND` creates one outgoing message per customer (Recovery Agent draft or template), visible in their app's **Messages**.
- The customer can reply. The reply is interpreted (Recovery Agent, or keyword fallback) into `intent ∈ {promise, pay_now, dispute, hardship, other}`.
- A `promise` is stored (`promises(customer_id, store_id, amount, date)`) and the reply suggests auto-pay if the customer has no mandate, with an in-message button **"Set up salary-week auto-pay"**.
- **Contract (template fallback must satisfy it too):** Ramesh replies "Salary 1 tareekh ko aati hai, tab de dunga" → `promise {amount: 1900, date: 2026-11-01}`, `suggest_mandate: true`.

### 4.12 Activity log
Table `activity(id, ts, store_id, kind, text, source)` where `kind ∈ {guardrail, confirm, payment, advance, growth, ai, integrity, message}` and `source ∈ {rule, ai, template}`. Shown on the presenter screen and in the merchant app's activity list. Replaces v1's trace.

---

## 5. End-to-end flows

### 5.1 Flow A: credit for a known customer (Priya, Ramesh, Vikram)
1. **Soundbox** (`/soundbox`): the operator taps a preset ("Ramesh 340") or types/speaks "Ramesh 340 udhaar" → `POST /api/soundbox/udhaar {text}`.
2. Backend parses (rules, or Counter Agent when AI is on) → resolves the customer → computes the guardrail (§4.2).
3. Soundbox **top display** shows band + verdict + "Why?". When AI is on, the verdict is spoken once in Kannada.
4. Operator taps **Use suggestion** (or **Override: give full amount**) → `POST /api/soundbox/accept {override}` → creates a `proposed` entry for `credit_now` and a `pending_request(kind=confirm)` → the **front screen** shows the QR: "Scan to confirm ₹200 udhaar · Lakshmi Stores" (and "₹140 to pay now" when `collect_now > 0`).
5. For green with `collect_now = 0`, the QR only confirms credit; for red (`credit_now = 0`), no entry is created and the front screen shows "Please pay ₹340" with the shop QR.
6. **Phone** (customer app, logged in as Ramesh): **Scan QR** → opens `/c/r/{token}` → **Confirm sheet**: "Lakshmi Stores · ₹200 on credit · due 30 Nov" + "Pay ₹140 now" with method choice (UPI / Credit line on UPI) → one button **"Pay ₹140 & confirm"** (or **Dispute**).
7. Backend: records the ₹140 `sale` payment, sets entry `verified`, completes the request, runs the integrity check, logs activity, sends "changed" pings.
8. **Laptop within ~1 s:** front screen shows "✓ Confirmed by Ramesh"; top display returns to idle; merchant app shows the entry as Verified; Ramesh's dues are now ₹1,900. When AI is on, the Soundbox says (Kannada) "Ramesh confirmed ₹200 udhaar".

### 5.2 Flow B: new customer via Portable Trust (Anita)
1. Soundbox: "Anita 2000" → the customer is known to the network but has no entries at S1 and no share → top display: "New customer. Ask them to scan to share their Bharosa Score. Starter limit ₹500." Front screen: **"New here? Scan to share your Bharosa Score"** QR (`kind=share`).
2. Anita's phone scans → **Share sheet**: "Share your Bharosa Score with Lakshmi Stores? They'll see your score band and a suggested limit. They will never see your other shops or amounts." **Share** / **Not now**.
3. **Share** → `score_shares` row → guardrail recomputed: ₹1,500 credit + ₹500 now → the merchant's top display updates: "🟠 Network-trusted new customer · Give ₹1,500 on credit, collect ₹500" → the proposed entry and confirm step are created **automatically** (the operator does not need to tap again for the share case) → Anita's phone moves straight to the Confirm sheet (same session, no second scan).
4. Anita chooses **Credit line on UPI (Partner Bank)** for the ₹500 → **"Pay ₹500 & confirm"**.
5. Merchant app: entry Verified, tagged **"New · Paytm network"**; "New customers won this week: 1".
6. **Not now** → starter limit ₹500 → confirm flow as in 5.1.
7. Anita can revoke the share later in her app (Score → "Shared with").

### 5.3 Flow C: Diwali stock-up with the Stock Advance
1. Merchant logs in → Home → **Growth plan** shows A_DIWALI (rank 1).
2. **Approve** → B1 created → Stock card: "Order ₹18,000 to Sharma Traders · due Fri 6 Nov · ₹9,200 short" → **Stock Advance offer**: ₹9,200 · fee ₹138 · repaid from 20% of repayments · backstop 30 Nov.
3. **Accept** → "Partner NBFC paid Sharma Traders ₹9,200 ✓" → progress bar 0 / ₹9,338.

### 5.4 Flow D: reminders, a reply, auto-pay setup, and the split
1. Merchant approves **A_REMIND** → Ramesh and Vikram each get a message in their app.
2. Ramesh replies "Salary 1 tareekh ko aati hai, tab de dunga" → "Promised ₹1,900 on 1 Nov" (merchant Collect screen) → reply to Ramesh suggests auto-pay with a button.
3. Ramesh taps **Set up salary-week auto-pay** → sheet: cap ₹3,000, collection day 2nd, notice the day before, "Enter UPI PIN ●●●●" (simulated) → **Activate** → schedule card in his app and in the merchant's Collect screen.
4. Ramesh also taps **Pay ₹500 now** on his dues → repayment → split **₹400 shop / ₹100 lender** → the merchant's advance progress bar moves to ₹100 / ₹9,338.

### 5.5 Flow E: Priya's monthly basket
1. Merchant approves **A_BASKET** → Priya's app shows **Action needed: "Your monthly basket at Lakshmi Stores · ₹1,850 · 8 items · Pay on credit by 30 Nov"**.
2. **Accept** → verified entry ₹1,850 → merchant **Orders**: "Priya Nair · ₹1,850 · 8 items · To deliver" → **Mark delivered**.

### 5.6 Flow F: dispute
On the Confirm sheet, **Dispute** with a reason ("Wrong amount" / "I didn't take this") → entry `disputed` → merchant sees it under Udhaar Book with **Cancel entry**.

---

## 6. Apps, authentication and roles

### 6.1 Users and login
- `users(id, role, phone, store_id NULL, customer_id NULL)`: one merchant (S1), four customers, and admin access via key.
- **Login:** phone number → "Enter OTP" → the OTP is always `DEMO_OTP` (default `123456`). No SMS is sent; show a note "Demo OTP: 123456".
- **Login QR (magic link):** `GET /api/auth/magic/{code}` with a one-time code (10-minute expiry) → sets the customer cookie → redirects to `/customer`. The presenter screen shows one login QR per customer.
- **Sessions:** `sessions(token, user_id, role, expires_at)` (12 hours).
- **Separate cookies per app** so one browser can be logged in as merchant and as a customer at the same time: `bh_merchant`, `bh_customer`. Admin uses the header `X-Admin-Key: ${ADMIN_KEY}` (the presenter page stores it after a one-time prompt).

### 6.2 Authorisation (enforced on every API)
| Role | Can read | Can do |
|---|---|---|
| merchant | Own store's ledger, customers at the store (band, limit, score band, dues), growth plan, advance, orders, messages | Approve actions, accept/decline advance, cancel disputed entries, mark baskets delivered |
| customer | Own profile, own dues across stores, own score breakdown, own pending requests, own messages, own mandates | Confirm, dispute, share/revoke score, pay, reply, set up auto-pay, accept/decline basket |
| soundbox | Its store's counter state | Submit udhaar text/voice, accept/override suggestion |
| admin | Everything | Reset, create magic links |

**Privacy check:** the merchant API never returns entries from `NET`, store names other than S1, or per-store amounts for a customer.

### 6.3 Presenter screen (`/demo`)
- Left: `/soundbox` (iframe). Centre: `/merchant` (iframe, merchant cookie). Right: `/customer` in a phone frame (iframe, customer cookie), used as the **no-phone fallback** and to mirror what's happening.
- A slim strip at the bottom: four **login QR codes** (Priya, Ramesh, Vikram, Anita) + the **activity list** (last 10 lines) + **Reset**.
- Nothing else. No steps, no captions, no controls.
- On stage it is shown as the **Live Demo** section of the home page (§10.7); `/demo` still works on its own.

---

## 7. API contract

All JSON under `/api`. Auth as in §6.

**Auth**
| Method | Path | Body / result |
|---|---|---|
| POST | `/auth/otp/start` | `{phone, app: "merchant"\|"customer"}` → `{ok}` |
| POST | `/auth/otp/verify` | `{phone, otp, app}` → sets cookie → `{role, name}` |
| GET | `/auth/magic/{code}` | Sets cookie, redirects |
| POST | `/auth/logout` | Clears that app's cookie |
| POST | `/admin/magic` (admin) | `{customer_id}` → `{url}` |

**Soundbox**
| Method | Path | Purpose |
|---|---|---|
| GET | `/soundbox/presets` | `[{label: "Priya 340", customer_id, amount}, …]` built from seed (keeps names out of frontend code) |
| GET | `/soundbox/state` | `{top: {band, text, reasons[], customer, amount}, front: {mode, qr_url, credit_now, collect_now, message}}` |
| POST | `/soundbox/udhaar` | `{text}` or `{customer_id, amount}` → guardrail result |
| POST | `/soundbox/accept` | `{override: bool}` → creates proposed entry + pending request |
| POST | `/soundbox/clear` | Resets the counter display |

**Voice (only when `SARVAM_ENABLED=true`; otherwise 404)**
| Method | Path | Purpose |
|---|---|---|
| POST | `/voice/transcribe` | multipart `file` (webm/wav ≤ 30 s) → `{transcript, language_code}` |
| GET | `/voice/speak?text=&lang=` | → `audio/wav` |

**Customer**
| Method | Path | Purpose |
|---|---|---|
| GET | `/customer/home` | Profile, `action_needed` (single highest priority: confirm/share > basket > message), score + breakdown, dues per store, mandate + schedule, shares |
| GET | `/requests/{token}` | Request details if it belongs to the logged-in customer |
| POST | `/requests/{token}/share` | `{decision: "share"\|"decline"}` |
| POST | `/requests/{token}/confirm` | `{pay_method: "upi"\|"credit_line"\|null, device_id}` |
| POST | `/requests/{token}/dispute` | `{reason}` |
| POST | `/customer/pay` | `{store_id, amount, method: "upi"}` → repayment |
| GET | `/customer/messages` | Threads |
| POST | `/customer/messages/reply` | `{store_id, text}` |
| POST | `/customer/mandates` | `{store_id, cap, collection_day}` |
| POST | `/customer/shares/{store_id}/revoke` | Revoke |
| POST | `/customer/baskets/{id}/accept` \| `/decline` | Basket |

**Merchant**
| Method | Path | Purpose |
|---|---|---|
| GET | `/merchant/home` | `summary {upi_sales_today, outstanding, overdue, due_this_week, new_customers_won}`, `growth_plan`, `counter_feed` (last 5 decisions), `stock {plan, bill, advance}`, `get_paid {outstanding, verified, overdue, promises, replies}` |
| GET | `/merchant/udhaar-book` | Customers: name, outstanding, overdue_days, band (for ₹340), safe_limit, score_band, tags |
| GET | `/merchant/customers/{id}` | Entries (this store only), reasons, messages |
| POST | `/merchant/growth/{action_id}/approve` | Dispatch per §4.7 |
| POST | `/merchant/advance/{id}/accept` \| `/decline` | |
| POST | `/merchant/entries/{id}/cancel` | Only when disputed |
| POST | `/merchant/baskets/{id}/delivered` | |
| GET | `/merchant/collect` | Messages, promises, mandates, schedules |
| POST | `/merchant/ask` | `{question}` → Growth Agent answer (AI on) or "Ask Munim is available when AI is enabled" |

**Shared**
| Method | Path | Purpose |
|---|---|---|
| GET | `/stream` | SSE "changed" pings (§8) |
| GET | `/activity?limit=20` | Activity lines (merchant: own store; admin: all) |
| POST | `/admin/reset` (admin) | Rebuild DB from seed (< 3 s) |
| GET | `/health` | `{ok, sarvam_enabled, demo_date, public_base_url}` |

---

## 8. Real-time updates

- One SSE endpoint, `/api/stream`. After every state change the server sends:
```json
{"type": "changed", "scopes": ["merchant:S1", "customer:C_RAMESH", "soundbox:S1"]}
```
- Each app refetches **its own** view endpoint when a scope it cares about appears (merchant → `merchant:S1`; a customer → `customer:<own id>`; Soundbox → `soundbox:S1`; presenter → all).
- No data travels in the ping, so the stream never leaks one user's data to another.
- Clients reconnect automatically (EventSource). On reconnect, refetch.

---

## 9. AI layer (Sarvam), off by default

### 9.0 Where the agents sit, and why (read before §9.1)

This section is the reference for the architecture slides (§10.8, slides 7–11) and for anyone extending the AI layer. The full reasoning is in `bharosa-explained.md` Parts 5 and 8.

#### 9.0.1 The layers (production view; the prototype keeps the same boundaries)
```
 PAYTM SURFACES     Soundbox (classic or AI)  ·  Paytm for Business (merchant)  ·  Paytm app (customer)
                          │ voice / text              │ approvals                  │ scan · confirm · pay · consent
 ─────────────────────────▼───────────────────────────▼────────────────────────────▼──────────────────────
 ① ACCESS            identity & roles · consent checks                   app/auth.py, app/api/*
 ② AI LAYER          Speech · Counter Agent · Recovery Agent · Growth    app/ai/sarvam.py, app/agents/*, app/voice.py
   (proposes)        Agent (Munim)           │ JSON proposals / words
 ③ VALIDATION        schema · policy · "every ₹ and every name must      validators inside each agent module
   (the firewall)    exist in our data"      │ pass ─► use it   fail ─► rule / template fallback
 ④ TRUST CORE        ledger & entry states · score · risk (limits,       app/core/score.py, risk.py, requests.py
   (deterministic)   exposure cap) · consent · request service (QR)
 ⑤ MONEY & GROWTH    payments · FIFO · 20% split · mandates · festive    app/core/payments.py, mandates.py, festive.py,
   (deterministic)   planner · basket · Stock Advance · growth candidates   basket.py, advance.py, growth.py
 ⑥ PROTECTION        shared-device check · audit (activity log + source)  app/core/requests.py, activity.py
 ⑦ EVENTS            one write lock · "changed" pings · spoken lines      app/bus.py, /api/stream
 ─────────────────────────────────────────────────────────────────────────────────────────────────────────
 RAILS (simulated)   UPI · UPI AutoPay · credit line on UPI · partner NBFC · distributor payment
```
Agents live only in ②. Nothing in ② can write to ④ or ⑤: an agent returns a proposal, ③ checks it, and the deterministic service in ④/⑤ does the work, usually after a human taps a button.

#### 9.0.2 The boundary
```
        NON-DETERMINISTIC (AI)                    │ FIREWALL │          DETERMINISTIC (code)
  voice ─► Speech-to-text ─► Counter Agent ───────┼► validator ─► risk engine ─► safe limit + reasons
  customer reply ─► Recovery Agent ───────────────┼► validator ─► promise stored, actions offered
  growth candidates (code) ─► Growth Agent ───────┼► validator ─► plan wording shown (order = code)
  question ─► Munim (read-only tools) ────────────┼► validator ─► answer shown
  verdict text (code) ─► translate ─► Speech ─────┼► validator ─► one spoken line
                                                  │            score · limits · ledger · payments ·
                                                  │            split · advance · mandates · fraud check
```

#### 9.0.3 What an agent is here
**An agent = an LLM + one job + (optionally) read-only tools + a strict JSON output + a validator + a fallback.**
```
 input ─► rules first ─ match? ─yes─────────────────────────────────────────────► result (source=rule)
                 │ no, and AI on
                 ▼
          prompt ─► LLM ─► JSON proposal ─► VALIDATOR ─ pass ─► result (source=ai)
                     ▲                          │ fail / timeout (8 s) / bad JSON
          read-only tools (Munim only)          ▼
                                         template / rule fallback ─► result (source=template)
```
Agents can read, never write. Every result is logged in the activity list with its source (`rule`, `ai`, `template`).

#### 9.0.4 The agents, and why each is justified
| Agent | Code | Fires in | Job | Why rules alone are not enough | Validator | Fallback | Can never |
|---|---|---|---|---|---|---|---|
| **Speech** (Sarvam STT/TTS) | `ai/sarvam.py`, `voice.py` | Flow A (mic, spoken verdict and confirmation), D (spoken repayment) | Voice → text; one short Kannada line per event | Speech recognition is inherently AI | Spoken line keeps exactly the ₹ figures of the code text | Text only, no audio | Decide anything |
| **Counter Agent** | `agents/counter.py` | Flow A (and B) when the rule parser fails | Messy shopkeeper sentence → `{customer_id, amount}` | Many languages, code-mixing, number words | `customer_id` in the store list; amount 1–50,000 | "Didn't catch that" + preset chips | Invent a customer or amount; set a limit |
| **Recovery Agent** | `agents/recovery.py` | Flow D: draft on A_REMIND approval; interpret every reply that keyword rules miss | Polite reminder in the customer's language; reply → `{intent, promise, suggest_mandate, escalate}` | Replies are open-ended | Only ₹ figure = dues; promise ≤ dues and within 30 days | Template reminder; keyword rules; "other" | Change dues; promise outside policy |
| **Growth Agent (Munim)** | `agents/growth_agent.py` | Flow C/D/E: plan wording (on reset); Ask Munim | Words the three code-ranked actions; answers questions via `get_summary`, `get_growth_plan`, `get_stock`, `list_overdue` | Combining several data sources into plain advice | Same action ids in code order; every ₹ figure in the facts/tool results; ≤ 3 tool calls | Template titles/why; "Available when AI is enabled" | Change numbers or ranking; take an action without the merchant's tap |

**Why not more agents?** Every extra agent adds non-determinism, latency and cost. Score, limits, allocation, the split, Stock Advance sizing, mandates, basket prediction and fraud checks are exact maths or policy: they are code, and they stay code.
**Why not zero agents?** The shopkeeper would have to type an exact format at a busy counter, reminders would be generic, and replies like "salary 1 tareekh ko" would be ignored. That is just another khata app.

#### 9.0.5 The agents along the journey
| Step | Ask | Check | Decide | Confirm | Collect | Grow |
|---|---|---|---|---|---|---|
| Who acts | Shopkeeper (voice/text) | Code | Code + shopkeeper | Customer (own phone) | Code + customer | Code + merchant |
| Agent | Speech → Counter (only if rules fail) | none | none (Speech says the verdict) | none (Speech says "confirmed") | Recovery (draft, read reply) | Growth (words the plan, Munim answers) |
| Code that decides | rule parser, validator | score, risk, exposure cap | request service, ledger | identity check, sale, entry → verified, device check | promise, mandate schedule, FIFO, 20% split | festive planner, Stock Advance, basket, growth candidates |

#### 9.0.6 How non-determinism is contained
1. Strict JSON output; anything else is rejected. 2. Grounding: every ₹ figure and every customer the AI names must exist in our data. 3. Rules first, AI second. 4. Humans approve money: the merchant taps Approve/Accept, the customer confirms. 5. Fallbacks everywhere: with `SARVAM_ENABLED=false` the whole app runs (tested by `test_ai_off.py`). 6. In production: per-language phrase test sets, accuracy monitoring, and logging of every proposal and validator decision.

**One line for judges:** "We use AI where the world is messy (speech, languages, conversations, explanations) and code where money moves. The AI can suggest; it can never decide or pay."

### 9.1 Toggle
```
SARVAM_ENABLED=false   # default. Everything works with rules and templates.
```
| Capability | `false` | `true` |
|---|---|---|
| Parse shopkeeper text | Regex: `<name> <amount>` (+ optional "udhaar/udhar/credit/khata"); fuzzy name match | Counter Agent (Sarvam chat), handles Hinglish, Kannada, multiple actions |
| Mic button (Soundbox) | Hidden | Sarvam speech-to-text → text → same parser |
| Spoken verdict / confirmation | Off | Sarvam text-to-speech, one short line in `kn-IN` |
| Reminder text | Template (customer's language: English/Hinglish) | Recovery Agent draft |
| Reply understanding | Keyword rules (§9.6) | Recovery Agent |
| Growth plan titles and "why" | Template | Growth Agent (ranking stays code-defined) |
| Ask Munim | Disabled with a note | Growth Agent Q&A with read-only tools |
| **Score, limits, payments, split, advance** | **Code** | **Code (never AI)** |

Every AI call: 8-second timeout → on any error, invalid JSON or failed validation, use the template/rule result and log `source=template` in activity.

### 9.2 Environment
```
SARVAM_ENABLED=false
SARVAM_API_KEY=                     # never commit; .env is git-ignored
SARVAM_CHAT_MODEL=sarvam-105b
SARVAM_STT_MODEL=saaras:v3          # VERIFY in Sarvam docs (Saarika v2.5 is deprecated)
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER=shubh            # default speaker for bulbul:v3; VERIFY a Kannada-suitable voice
SARVAM_TIMEOUT_S=8
```

### 9.3 Sarvam client (`app/ai/sarvam.py`)
Uses `httpx` (already a dependency) against the documented REST endpoints. The official `sarvamai` Python SDK may be used instead, with the same function signatures.

```python
"""Thin Sarvam AI client. Disabled unless SARVAM_ENABLED=true.
Never logs or prints the API key."""
import base64
import json
import os
import re

import httpx

BASE_URL = "https://api.sarvam.ai"


def enabled() -> bool:
    return os.getenv("SARVAM_ENABLED", "false").strip().lower() == "true"


def _headers() -> dict:
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("SARVAM_API_KEY is not set")
    return {"api-subscription-key": key}


def _timeout() -> float:
    return float(os.getenv("SARVAM_TIMEOUT_S", "8"))


def _extract_json(text: str) -> dict:
    """Accept raw JSON or JSON wrapped in ```json fences."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


async def chat_json(system: str, user: str) -> dict | None:
    """Returns parsed JSON from the chat model, or None if disabled/failed."""
    if not enabled():
        return None
    payload = {
        "model": os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{BASE_URL}/v1/chat/completions",
                                  headers=_headers(), json=payload)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            return _extract_json(content)
    except Exception:
        return None


async def text_to_speech(text: str, language_code: str = "kn-IN") -> bytes | None:
    """Returns WAV bytes, or None if disabled/failed."""
    if not enabled():
        return None
    payload = {
        "text": text[:2500],
        "language_code": language_code,
        "model": os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
        "speaker": os.getenv("SARVAM_TTS_SPEAKER", "shubh"),
    }
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{BASE_URL}/text-to-speech",
                                  headers=_headers(), json=payload)
            r.raise_for_status()
            return base64.b64decode(r.json()["audios"][0])
    except Exception:
        return None


async def speech_to_text(audio: bytes, filename: str, mime: str,
                         language_code: str = "unknown") -> dict | None:
    """Returns {"transcript", "language_code"} or None.
    language_code "unknown" = auto-detect (supports code-mixed speech)."""
    if not enabled():
        return None
    data = {"model": os.getenv("SARVAM_STT_MODEL", "saaras:v3"),
            "language_code": language_code}
    files = {"file": (filename, audio, mime)}
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            r = await client.post(f"{BASE_URL}/speech-to-text",
                                  headers=_headers(), data=data, files=files)
            r.raise_for_status()
            body = r.json()
            return {"transcript": body.get("transcript", ""),
                    "language_code": body.get("language_code")}
    except Exception:
        return None
```
`VERIFY`: the exact speech-to-text response field names and the recommended STT model name in Sarvam's current docs; adjust the two lines that read `transcript` and `language_code` if needed.

### 9.4 First-call smoke script (`scripts/sarvam_smoke.py`)
Run once after setting the key, to confirm one working call. Exits early when disabled. Prints results, **never the key**.
```python
"""Usage: SARVAM_ENABLED=true python scripts/sarvam_smoke.py"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ai import sarvam  # noqa: E402


async def main() -> None:
    if not sarvam.enabled():
        print("SARVAM_ENABLED is false. Set it to true in .env to run this check.")
        return
    print("Chat:", await sarvam.chat_json(
        "Reply only with JSON.",
        'Return {"greeting": "<one word hello in Kannada>"}'))
    audio = await sarvam.text_to_speech("ರಮೇಶ್ ಇನ್ನೂರು ರೂಪಾಯಿ ಸಾಲವನ್ನು ದೃಢಪಡಿಸಿದರು", "kn-IN")
    if audio:
        with open("sarvam_tts_test.wav", "wb") as f:
            f.write(audio)
        print("TTS: wrote sarvam_tts_test.wav", len(audio), "bytes")
    else:
        print("TTS: failed")


asyncio.run(main())
```
`.gitignore` must include `.env` and `sarvam_tts_test.wav`.

### 9.5 Counter Agent (`app/agents/counter.py`)
- **When:** `/soundbox/udhaar` with free `text` (typed or transcribed). Presets send `{customer_id, amount}` and skip parsing.
- **Rule parser first** (always): `^\s*([A-Za-zಀ-೿ऀ-ॿ ]+?)\s+(\d{2,6})\b`, fuzzy-match the name against the 10 store customers + Anita (`difflib`, cutoff 0.75). If it resolves to exactly one customer and an amount, use it **without calling the AI** (fast, deterministic).
- **AI only if the rule parser fails** (and AI is on). System prompt:
```
You convert a kirana shopkeeper's short sentence (English, Hindi, Kannada or mixed) into JSON.
Known customers: {list of {id, name}}.
Return {"customer_id": "<id or null>", "amount": <integer rupees or null>, "type": "udhaar"|"cash_repayment"|"unknown", "clarify": "<short question or null>"}.
Use only ids from the list. Convert number words to digits. Never invent a customer or amount. JSON only.
```
- **Validator:** `customer_id` in the list; `amount` integer 1–50,000; otherwise show "Didn't catch that. Tap a name or type again."

### 9.6 Recovery Agent (`app/agents/recovery.py`)
**Draft (on A_REMIND approval).** Template fallback (Hinglish for hi-IN, English otherwise):
"Namaste {name} ji, Lakshmi Stores par aapka ₹{dues} udhaar baaki hai ({days} din se). Aap Paytm se 'Pay now' kar sakte hain. Dhanyavaad!"
AI prompt: write ≤ 300 characters, polite, in the customer's language, must include the exact amount `₹{dues}` and no other ₹ figure. **Validator:** the only ₹ figure equals `dues`.

**Interpret reply.** Keyword fallback (applied first; AI only if no keyword matches and AI is on):
| Pattern (case-insensitive) | Result |
|---|---|
| `salary\|tankhwa\|tankha\|1 tareekh\|first\|1st\|pagar` | `promise {amount: dues_total, date: next 1st}`, `suggest_mandate: !has_mandate` |
| `abhi\|now\|pay kar\|bhej` | `pay_now` |
| `galat\|wrong\|nahi liya\|didn't` | `dispute` (escalate) |
| `problem\|mushkil\|hospital\|job` | `hardship` (escalate) |
AI output schema: `{"intent", "promise": {"amount", "date"} | null, "suggest_mandate": bool, "reply_message", "escalate": bool}`. **Validator:** promise date within 30 days of `DEMO_DATE`; amount ≤ dues; reply contains no ₹ figure other than dues.

### 9.7 Growth Agent (`app/agents/growth.py`)
**Plan wording.** Input: the three code-computed actions (facts + impact). Output:
```json
{"summary": "≤ 35 words", "actions": [{"action_id": "A_DIWALI", "title": "≤ 8 words", "why": "≤ 30 words"}]}
```
Validator: same three action_ids, each once; every ₹ figure must equal a figure in that action's facts; ranking is **not** taken from AI (code order). Template fallback:
- A_DIWALI: "Stock up for Diwali" / "Last year your Diwali-week sales were about 1.6× normal. A ₹18,000 order could bring about ₹27,400 in extra sales."
- A_REMIND: "Remind 2 overdue customers" / "₹4,300 is overdue: Ramesh (19 days) and Vikram (41 days)."
- A_BASKET: "Offer Priya her monthly basket" / "Priya buys the same 8 items every month. ₹1,850, within her limit."

**Ask Munim (AI on only).** JSON tool loop (max 3 tool calls) over read-only tools: `get_summary`, `get_growth_plan`, `get_stock`, `list_overdue`. Final answer validator: every ₹ figure must appear in a tool result; otherwise answer with a template summary.

### 9.8 Voice pipeline (AI on only)
```
Soundbox mic (MediaRecorder, audio/webm, ≤ 15 s)
 → POST /api/voice/transcribe → Sarvam STT (language "unknown" = auto-detect; code-mixed OK)
 → transcript shown on the Soundbox → /api/soundbox/udhaar {text}
 → verdict → GET /api/voice/speak?text=…&lang=kn-IN → plays once on the Soundbox page
```
Spoken lines (Kannada when AI is on; text only when off), at most one per event:
- Verdict: the template verdict (§4.2), translated by the chat model **only if** AI is on; otherwise not spoken.
- Confirmation: "{name} confirmed ₹{amount} udhaar."
- Repayment: "₹{amount} received from {name}."
Browser mic access requires HTTPS or localhost (the tunnel in §11 provides HTTPS).

---

## 10. UI specification

### 10.1 Principles
1. **Real data only.** No literal names, amounts, dates or statuses in frontend code (the only exceptions are the static pitch pages `static/overview/` and `static/presentation/`); everything comes from the APIs in §7. Remove every `mock*`, `fake*`, `sample*`, `dummy*` file or object.
2. **Max five sections** on any home screen; one primary action per screen.
3. **No audio** except the single spoken line per event when AI is on (Soundbox page only).
4. **Status in words and colour** (Safe / Caution / High risk; Verified / Disputed / Settled).
5. **Paytm visual language:** v1 `tokens.css` (navy `#042E6F`, cyan `#00BAF2`, background `#F5F5F7`, white rounded cards, navy circular icons, bold headings, blue "View all →" links). Footer: "Concept prototype · Team MerchantMavericks".
6. **Mobile-first customer app** (works at 360–430 px wide). Merchant app optimised for a phone frame (390 px) but responsive.
7. Short highlight animation (≤ 300 ms) when a value changes; nothing decorative.

### 10.2 Login screens (merchant and customer)
Paytm-style: logo wordmark, "Enter mobile number", **Continue** → "Enter OTP" with the note "Demo OTP: 123456" → **Verify**. Customer login screen also shows "Or scan a login QR from the presenter screen".

### 10.3 AI Soundbox (`/soundbox`)
A device render (cyan/white body):
- **Top display (shopkeeper):** band bar (green / amber / red / grey for waiting) + one line of verdict text + **Why?** (expands reasons).
- **Front screen (customer):** one mode at a time: `idle` (shop QR card: "Lakshmi Stores · Scan to pay"), `confirm_qr`, `share_qr`, `pay_full` (red case), `done` ("✓ Confirmed by {name}").
- **Input panel below the device:** four preset chips loaded from `/api/soundbox/presets` (**Priya 340 · Ramesh 340 · Vikram 340 · Anita 2000**), a text box "What the shopkeeper said…", and a **🎙 mic button only when AI is on**. A note: "On a real AI Soundbox, the Paytm Button captures this by voice."
- **Action buttons** when a verdict is shown: **Use suggestion** (primary) · **Override** · **Clear**.

### 10.4 Merchant app (`/merchant`)
**Home** (top to bottom, exactly these):
1. **Header + summary strip:** "Lakshmi Stores · Jayanagar"; three numbers: UPI sales today · Udhaar outstanding · Due this week.
2. **This week's growth plan** (primary): summary line + 3 rows (rank, title, expected impact, **Approve** / "Approved ✓" + outcome text).
3. **At the counter:** last 5 decisions (band pill, name, credit/collected, tags like "New · Paytm network", state pill Proposed/Verified/Disputed) + "New customers won this week: N".
4. **Stock:** one card whose content follows the state: Diwali plan → order placed (₹9,200 short) → Stock Advance offer (**Accept** / **Decline**) → "Partner NBFC paid Sharma Traders ₹9,200 ✓" + progress bar `repaid / 9,338` + "20% of repayments".
5. **Get paid:** outstanding / overdue + counters (promises, replies, auto-pay schedules) → **Collect**.

**Bottom navigation:** Home · Udhaar Book · Collect · Orders · Ask Munim (the last shows "Available when AI is enabled" if off).
- **Udhaar Book:** list with search; each row: name, outstanding, overdue days, band pill, score band, tags. Detail: entries at this store (state pills), "Why this limit?", messages; **Cancel entry** on disputed entries.
- **Collect:** reminder threads, promises ("Ramesh · ₹1,900 · 1 Nov"), auto-pay schedules ("Ramesh · next collection Mon 2 Nov · up to ₹3,000").
- **Orders:** basket orders with **Mark delivered**.
- A small **Activity** link in the header opens the last 20 activity lines.

### 10.5 Customer app (`/customer`)
**Home** (exactly these):
1. **Header:** initials avatar, name, bell.
2. **Action needed** (single slot, highest priority): pending confirm/share request ("Lakshmi Stores is waiting for you") → basket offer → unread message. One card, one button.
3. **Bharosa Score:** semicircle gauge (300–900), number, band, "See how it's calculated" (the breakdown list), "Shared with N shops · Manage".
4. **My dues:** a row per store (amount, overdue days if any) with **Pay**.
5. **Salary-week auto-pay:** schedule card if active, otherwise "Set up auto-pay".

**Floating navy pill:** **Scan QR** (opens the camera scanner, §11.3).
**Bottom navigation:** Home · Dues · Score · Messages.
**Sheets:** Share (§5.2), Confirm + pay-now (§5.1), Pay dues, Auto-pay setup (§4.9), Basket offer (§5.5), Dispute.

### 10.6 Overview (`/overview`)
Unchanged; shown as the **Overview** section of the home page (§10.7). Static content, sections: (1) Bharosa in one line + three pillars; (2) the flow: Ask → Check → Decide → Confirm → Collect → Grow; (3) AI vs code table + the five safety rules; (4) Who carries which risk + the protections (exposure cap, new-shop discount, velocity check) + consent; (5) **Fraud rings explained** (§ text in the overview doc); (6) Works on every Paytm Soundbox (Classic: printed QR + speaker + merchant phone; AI Soundbox: voice + displays + dynamic QR); (7) Compliant salary-week auto-pay; (8) Stack + prototype vs production; (9) Team.

---

### 10.7 Home page (`/`)
One page that holds everything shown on stage, as **three sections** chosen by tabs in a slim navy header (wordmark left, tabs centre, context actions right):
1. **Live Demo**: the presenter screen (§6.3) exactly as it is, embedded.
2. **Overview**: the one-page summary (§10.6), unchanged.
3. **Presentation**: the slides (§10.8). Header actions: **Fullscreen**, **PDF**, **PDF with notes**.

Rules: the URL hash selects the section (`/#demo`, `/#overview`, `/#presentation`; default `#demo`), so a refresh keeps it. Each section loads the first time it is opened and is then kept alive, so switching to the slides and back never resets the demo (logins, the Soundbox state and open sheets survive). While the Presentation section is open, the arrow keys, Space, PageUp/PageDown, Home and End drive the slides even when focus is on the header. Every section can still be opened on its own URL.

### 10.8 Presentation (`/presentation`)
The pitch as **16:9 slides** (a 1280×720 canvas scaled to fit), static content from `bharosa-explained.md`. One idea per slide, large type, diagrams drawn in HTML/SVG (no images), Paytm colours. It flows in five acts: **Problem → Challenge → Solution → Architecture & flow → Risks & answers**.

| # | Act | Slide | Content |
|---|---|---|---|
| 1 | | Title | "Bharosa on Paytm · Trust, turned into growth." · team · track |
| 2 | Problem | Every kirana is secretly a lender | ₹340 "later" = an unsecured, interest-free loan → four gaps (no risk check · no proof · no collection · no funding) → rationing → lost growth |
| 3 | Challenge | Trust is invisible | Khata apps record; the gap is verifiable trust. It needs four things at once (counter device · customer app · payment rail · lenders): only Paytm has all four |
| 4 | Solution | Bharosa in one picture | Three pillars (Sell more · Get paid · Stock up) on a trust layer, tied together by the weekly growth plan |
| 5 | Solution | The verified receivable | Khata (one-sided claim) vs Bharosa (customer confirms on their own phone) → score · safe limits · collateral for a Stock Advance |
| 6 | Solution | One transaction, end to end | Ramesh ₹340 swimlane (shopkeeper · Soundbox · platform · phone): ₹3,215 × 0.6 − ₹1,700 → ₹200 credit + ₹140 now; "AI understood one sentence; everything else is code" |
| 7 | Architecture | The architecture | §9.0.1 as a diagram: surfaces → ① access → ② **AI layer (the agents)** → ③ **validation firewall** → ④ trust core → ⑤ money & growth → ⑥ protection → ⑦ events → rails |
| 8 | Architecture | Where AI stops | §9.0.2: the non-deterministic zone, the firewall, the deterministic zone |
| 9 | Architecture | Anatomy of an agent | §9.0.3: rules first → LLM → JSON proposal → validator → result, else fallback; read-only tools; "agents read, never write" |
| 10 | Architecture | The four agents, and why | §9.0.4 (job · why not rules · can never) + why not more / why not zero |
| 11 | Architecture | Agents along the journey | §9.0.5: Ask → Check → Decide → Confirm → Collect → Grow, with the agent and the deciding code at each step |
| 12 | Architecture | Containing non-determinism | §9.0.6 six controls + the one-line answer |
| 13 | Architecture | Prototype vs production | "The intelligence is real; the rails are simulated behind adapters shaped like Paytm's" |
| 14 | Solution | Who benefits | Merchant · Paytm · customers and lenders |
| 15 | Risks | Key design decisions | Decision vs rejected alternative, and why |
| 16 | Risks | Risks & answers (1/2) | Khatabook? · why would a customer confirm? · is AI deciding credit? · why agents at all? · who takes the loss? |
| 17 | Risks | Risks & answers (2/2) | Regulation · auto-pay on salary day · fake receivables · needs the AI Soundbox? · how Paytm earns |
| 18 | | Close | "Make trust verifiable, and credit becomes a growth engine." · "Bharosa: trust, turned into growth." |

**Controls:** ← → / Space / PageUp / PageDown / Home / End; click the right or left half of the slide; **F** fullscreen; **N** shows the speaker notes under the slide; slide number and act progress at the bottom; `#7` in the URL opens slide 7. Every slide carries **speaker notes** (the 2-minute pitch split across slides, plus who-to-lead-with hints).

### 10.9 Presentation as PDF
`python tasks.py pdf` (`scripts/build_pdf.py`) prints the slides with a locally installed Edge or Chrome in headless mode (no extra Python package; it serves `static/` itself on a free local port, so the app server need not run) into:
- `static/presentation/bharosa-pitch.pdf`: one slide per 16:9 page (to share);
- `static/presentation/bharosa-pitch-notes.pdf`: each slide with its speaker notes below it (for rehearsal).
Both are committed and linked from the home page header. Regenerate after any slide change.

## 11. Phone scanning and networking

### 11.1 Public HTTPS address
The phone must reach the backend over HTTPS (phone browsers allow camera access only on HTTPS).
- **Primary:** run the app on the laptop and expose it with a **Cloudflare quick tunnel**:
  `cloudflared tunnel --url http://localhost:8000` → copy the `https://…trycloudflare.com` address into `PUBLIC_BASE_URL` and restart (or set it via `/admin` before the demo).
- **Alternative:** deploy to any HTTPS host that does not sleep (avoid free tiers with cold starts).
- The laptop needs internet (venue Wi-Fi or a phone hotspot); phones can use mobile data.

### 11.2 QR contents
- Request QR: `${PUBLIC_BASE_URL}/c/r/{token}`. Login QR: `${PUBLIC_BASE_URL}/api/auth/magic/{code}`.
- Generated server-side as PNG (Python `qrcode` package) or client-side (vendored `qrcode` JS), large enough to scan from a laptop screen at about 50 cm (≥ 280 px, high contrast, quiet zone).
- In production these would be standard Paytm/UPI QR codes read by the Paytm app; say so on the Overview page.

### 11.3 Scanner in the customer app
- Vendored **html5-qrcode** (pin a version, e.g. 2.3.8) behind the **Scan QR** pill. On a successful scan of a URL with the same host, navigate in-app to the path.
- **Fallback 1:** the phone's native camera app scans the same QR and opens the link in the browser (the customer cookie is per-browser, so log in in that browser first, or use the login QR).
- **Fallback 2 (no internet):** on the presenter screen, click the QR inside the customer phone frame.

### 11.4 Route `/c/r/{token}`
Served by the customer app: if not logged in → login → continue to the request; if the request belongs to someone else → "This request is for another customer"; if expired → "This request has expired. Ask the shop to try again."

---

## 12. Data model (final)

```text
stores(id PK, name, area, voice_lang, starter_limit, due_days, upi_sales_today,
       cash_available_by_bill_due, vpa, is_network BOOL)
customers(id PK, name, phone, vpa, lang, loginable BOOL)
store_customers(store_id, customer_id, credit_balance INT, PRIMARY KEY(store_id, customer_id))
entries(id PK, store_id, customer_id, amount INT, paid INT, state, source  -- counter|basket|seed
        created_at, due_date, settled_at NULL, items JSON NULL, override BOOL,
        integrity_flag BOOL, dispute_reason NULL, device_id NULL)
payments(id PK, store_id, customer_id, amount INT, method, purpose, lender_share INT,
         merchant_share INT, created_at)
allocations(id PK, payment_id, entry_id, amount INT)
pending_requests(token PK, kind, store_id, customer_id, amount_requested INT, credit_now INT,
                 collect_now INT, entry_id NULL, status, created_at, expires_at)
score_shares(id PK, customer_id, store_id, granted_at, revoked_at NULL)
mandates(id PK, customer_id, store_id, cap INT, collection_day INT, status, created_at)
messages(id PK, store_id, customer_id, direction, text, lang, source, created_at, read BOOL)
promises(id PK, store_id, customer_id, amount INT, date, created_at)
catalogue(sku PK, name, category, price INT)
festive_profiles(store_id PK, profile JSON)
bills(id PK, store_id, distributor, amount INT, due_date, status, paid_by_lender INT, paid_by_store INT)
advances(id PK, store_id, bill_id, lender, amount INT, fee INT, total_due INT, repaid INT,
         split_rate REAL, state, backstop_date, created_at)
growth_actions(id PK, store_id, action_id, type, facts JSON, impact INT, rank INT,
               title, why, state, source, updated_at)
basket_offers(id PK, customer_id, store_id, items JSON, value INT, state, entry_id NULL, created_at)
users(id PK, role, phone, store_id NULL, customer_id NULL)
sessions(token PK, user_id, app, expires_at)
magic_links(code PK, customer_id, expires_at, used BOOL)
activity(id PK, ts, store_id, kind, text, source)
soundbox_state(store_id PK, state JSON)
```
All money in integer rupees. Timestamps in IST; "today" = `DEMO_DATE`.

---

## 13. Repository layout, environment and run

```
bharosa/
├── README.md
├── .env.example            # no real key
├── .gitignore              # .env, *.db, sarvam_tts_test.wav
├── requirements.txt
├── Makefile                # run | seed | test | smoke
├── app/
│   ├── main.py             # FastAPI: / (home), /merchant /customer /soundbox /demo /overview /presentation, /c/r/{token}
│   ├── config.py           # env (DEMO_DATE, PUBLIC_BASE_URL, DEMO_OTP, ADMIN_KEY, SARVAM_*)
│   ├── db.py  models.py  seed.py
│   ├── auth.py             # OTP, sessions, magic links, role dependencies
│   ├── core/
│   │   ├── score.py  risk.py  ledger.py  payments.py  requests.py
│   │   ├── advance.py  festive.py  growth.py  basket.py  mandates.py
│   │   ├── messages.py  integrity.py  activity.py
│   ├── ai/
│   │   └── sarvam.py       # §9.3
│   ├── agents/
│   │   ├── counter.py  recovery.py  growth_agent.py
│   ├── api/
│   │   ├── auth_routes.py  soundbox_routes.py  customer_routes.py
│   │   ├── merchant_routes.py  voice_routes.py  admin_routes.py  stream.py
├── static/
│   ├── shared/  tokens.css  base.css  api.js  sse.js  format.js
│   ├── merchant/  index.html  merchant.js  merchant.css
│   ├── customer/  index.html  customer.js  customer.css
│   ├── soundbox/  index.html  soundbox.js  soundbox.css
│   ├── demo/      index.html  demo.js
│   ├── overview/  index.html  overview.css
│   ├── home/      index.html                          # §10.7 three sections
│   ├── presentation/  index.html  presentation.css  presentation.js  bharosa-pitch.pdf  bharosa-pitch-notes.pdf
│   └── vendor/    alpine.min.js  qrcode.min.js  html5-qrcode.min.js  fonts/
├── scripts/
│   ├── sarvam_smoke.py     # §9.4
│   └── build_pdf.py        # §10.9 slides → PDF (headless Edge/Chrome)
└── tests/
    ├── test_score.py  test_risk.py  test_requests.py  test_payments_split.py
    ├── test_festive_advance.py  test_growth.py  test_basket.py  test_recovery_rules.py
    ├── test_auth_privacy.py  test_no_mock_ui.sh
```

### 13.1 `.env.example`
```
DEMO_DATE=2026-10-31
PUBLIC_BASE_URL=http://localhost:8000
DEMO_OTP=123456
ADMIN_KEY=change-me
DB_PATH=bharosa.db

SARVAM_ENABLED=false
SARVAM_API_KEY=
SARVAM_CHAT_MODEL=sarvam-105b
SARVAM_STT_MODEL=saaras:v3
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER=shubh
SARVAM_TIMEOUT_S=8
```

### 13.2 `requirements.txt`
`fastapi`, `uvicorn[standard]`, `sqlmodel`, `pydantic>=2`, `pydantic-settings`, `python-dotenv`, `httpx`, `python-multipart`, `qrcode[pil]`, `pytest`. Optional: `sarvamai` (if using the SDK instead of raw `httpx`).

### 13.3 Run
```
pip install -r requirements.txt
cp .env.example .env                  # set ADMIN_KEY; leave SARVAM_ENABLED=false at first
make seed && make run                 # http://localhost:8000/demo
cloudflared tunnel --url http://localhost:8000     # copy the https URL into PUBLIC_BASE_URL, restart
# AI on: set SARVAM_ENABLED=true and SARVAM_API_KEY in .env, then:
make smoke                            # python scripts/sarvam_smoke.py
```

---

## 14. Tests and acceptance contracts

| Test | Asserts |
|---|---|
| `test_score.py` | Priya 780, Ramesh 662, Vikram 438, Anita 770, each regular 690; breakdown lines sum to the score |
| `test_risk.py` | All five rows of §4.2; Anita's reasons never mention `NET` or "Other Paytm shops" amounts |
| `test_requests.py` | Confirm request only usable by its customer; expiry after 15 min; share → limit 1,500 and confirm step created; decline → 500 |
| `test_payments_split.py` | `sale` payments never allocated; ₹500 repayment by Ramesh after advance → 400/100; FIFO; excess → credit balance |
| `test_festive_advance.py` | expected_extra 27,400; order 18,000; gap 9,200; V_eligible 23,200; cap 9,280; amount 9,200; fee 138; total 9,338 |
| `test_growth.py` | Three actions in order DIWALI, REMIND, BASKET with impacts 27,400 / 4,300 / 1,850; approvals dispatch correctly; AI output with a wrong ₹ figure falls back to template |
| `test_basket.py` | Priya basket 8 items, ₹1,850; accept creates a verified entry with items |
| `test_recovery_rules.py` | The Ramesh reply → promise 1,900 on 2026-11-01, suggest_mandate true (with AI off) |
| `test_auth_privacy.py` | Merchant APIs never return NET entries; customer A cannot read customer B; soundbox cannot read customer data |
| `test_ai_off.py` | With `SARVAM_ENABLED=false`, no outbound HTTP calls are made and every flow in §5 completes |
| `test_no_mock_ui.sh` | `grep -rnE "₹ ?[0-9]\|Ramesh\|Priya\|Vikram\|Anita\|Lakshmi\|Sharma" static --include=*.js --include=*.html` matches only `static/overview/` and `static/presentation/` |
| `test_pages.py` | `/` serves the home page with its three sections; `/presentation` has 18 slides, each with speaker notes, including the architecture, agent and risk slides; every app URL returns 200 |

**Manual acceptance (must pass before presenting):**
1. With AI off, run flows 5.1–5.6 end to end on the presenter screen only (no phone).
2. Via the tunnel, log in as Ramesh on a real phone with the login QR, scan the Soundbox QR, confirm. The laptop updates within about 2 seconds.
3. Same for Anita on a second phone (share → ₹1,500 → credit line ₹500 → confirm).
4. Turn AI on: say "Ramesh, 340 udhaar" in Kannada or Hindi into the mic → transcript → amber verdict spoken in Kannada.
5. Reset returns everything to the seed in under 3 seconds.
6. On `/`, switch Live Demo → Presentation → Live Demo: the demo keeps its state; the slides step with the arrow keys; `python tasks.py pdf` regenerates both PDFs (18 slides each).

---

## 15. Build order (from the v1 codebase)

| Step | Work | Done when |
|---|---|---|
| 1 | **Strip v1** per §2.3 (demo mode, controls, clock jobs, personas, extra stores, compare, audio, replay cache, recon agent) | App starts; old tests for removed features deleted |
| 2 | **New seed + score + risk** (§3, §4.1–4.2) | `test_score`, `test_risk` pass |
| 3 | **Auth + roles + separate cookies + magic links** (§6) | `test_auth_privacy` passes |
| 4 | **Soundbox + pending requests + confirm/share + payments** (§4.3–4.5, §5.1–5.2) and the three app shells reading real APIs | Flows 5.1 and 5.2 work on the presenter screen |
| 5 | **Tunnel + phone scanner** (§11) | Manual acceptance 2 and 3 pass. **Do this early; it's the riskiest part** |
| 6 | **Growth plan + Diwali + Stock Advance + split** (§4.6–4.7, §5.3, §5.4 step 4) | `test_festive_advance`, `test_payments_split`, `test_growth` pass |
| 7 | **Reminders + replies + auto-pay setup + basket** (§4.8–4.9, §4.11) | `test_recovery_rules`, `test_basket` pass |
| 8 | **UI polish** to §10 (five-section homes, Paytm style, no mock data) + Overview page | `test_no_mock_ui.sh` passes |
| 9 | **Sarvam behind the toggle** (§9): smoke script → Counter → Recovery → Growth wording → STT/TTS | `make smoke` works; manual acceptance 4 passes; `test_ai_off` still passes |
| 8b | **Home page + Presentation + PDF** (§9.0, §10.7–10.9) | `test_pages` passes; manual acceptance 6 passes |
| 10 | **Rehearse** with AI off, then on; with phones and without, using the PDF with notes | All manual acceptance items pass |

**If time runs out, cut in this order:** Ask Munim → voice (STT/TTS) → basket → reminders/reply (keep auto-pay setup via the Dues screen) → Overview polish. **Never cut:** phone scan confirm, Anita's Portable Trust, Diwali plan + Stock Advance + split, logins, real data.

**Optional stretch (only if everything above passes):** a "Classic Soundbox" toggle on `/soundbox` that shows the shop's static QR instead of a dynamic one (the customer app then finds the pending request for the logged-in customer at that store); the v1 architecture diagram on the Overview, lighting up from activity lines.

---

## 16. Presenting (no script enforced by the app)

Open `/` on the stage laptop. Start in **Presentation** (slides 1–6: problem, challenge, solution), switch to **Live Demo** for the flows below, then return to **Presentation** for the architecture, the agents and the risks (slides 7–18). **Overview** is the leave-behind.

Suggested demo order (about 5 minutes); the app does not enforce it:
1. Merchant logs in → growth plan (3 actions).
2. Soundbox: Priya 340 (green), Ramesh 340 (amber) → Ramesh's phone scans → confirms → laptop updates.
3. Judge scans the Anita login QR on their phone → Soundbox: Anita 2000 → judge scans → shares → ₹1,500 → pays ₹500 by credit line → confirms → "New · Paytm network".
4. Merchant approves Diwali → accepts the Stock Advance.
5. Merchant approves reminders → Ramesh replies → sets up auto-pay → pays ₹500 now → split 400/100.
6. Merchant approves the basket → Priya accepts → Orders.
7. (AI on) One spoken Kannada line, and one live reply understood by the Recovery Agent.

---

## 17. Assumptions and items to verify

- `ASSUMPTION` The Paytm app could recognise a Bharosa request when scanning a shop's QR (or Bharosa's dynamic QR). Our customer web app plays the Paytm app in the prototype.
- `ASSUMPTION` Lakshmi Stores is a Paytm-onboarded merchant eligible to collect via UPI AutoPay mandates; execution follows the 24-hour pre-debit notice rule. Production needs confirmation from Paytm's compliance team.
- `ASSUMPTION` A partner bank offers credit lines on UPI at the counter (simulated).
- `ASSUMPTION` Festive uplift, the 18% margin and the 0.8 safety factor are illustrative.
- `VERIFY` (production) Sharing Bharosa Scores across merchants may count as regulated credit information sharing; route scoring through a licensed partner. Consent and minimal disclosure are built in.
- `VERIFY` Sarvam: STT model name and response fields; a suitable Kannada TTS speaker for `bulbul:v3`; `response_format` JSON behaviour on `sarvam-105b`.
- **Security:** the Sarvam key lives only in `.env`. If a key was ever shared in chat or elsewhere, rotate it after the event.
