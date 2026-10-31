# Bharosa: The Complete Explanation

*A first-principles guide to the product, the architecture, the role of AI, and the pitch. It describes the **real solution**, not just the demo.*
*Companion to `bharosa-arch-v2.md` (spec) and `bharosa-overview-v2.md` (overview). The Presentation (`/presentation`) is built from this document.*

---

## Part 1: The idea in 30 seconds

> **"Every kirana in India is secretly a lender. It gives udhaar to win and keep customers, but it does this blind: no risk check, no proof, no collections, no funding. So shopkeepers ration credit out of fear, and every 'no' is a lost sale.
> Bharosa makes the trust between a shop and its customer verifiable, using what Paytm already has: the Soundbox on the counter, the Paytm app in the customer's hand, UPI, and lending partners. With verifiable trust, a merchant can sell more on credit safely, get paid without chasing, and stock up without cash.
> Khata apps record udhaar. Bharosa turns it into growth."**

---

## Part 2: The problem, from first principles

Strip udhaar down to what it really is:

```
   Customer takes ₹340 of goods today, pays "later"
                     │
                     ▼
   The SHOP has just made an unsecured, interest-free LOAN
                     │
   ┌─────────────────┼──────────────────┬──────────────────┐
   ▼                 ▼                  ▼                  ▼
 No risk check    No proof          No collection      No funding
 (gut feel)       (notebook;        (awkward to        (paid from
                   customer never    chase a            stock money)
                   agrees)           neighbour)
                     │
                     ▼
   Result: the shopkeeper RATIONS credit out of fear
   → refuses new customers → caps good customers → can't stock up for festivals
                     │
                     ▼
   LOST GROWTH
```

**The key insight:** the problem isn't record-keeping (khata apps already solved that). The problem is that **trust is invisible**. If trust became *visible and verifiable*, credit would stop being a risk to ration and become a tool to grow with.

**Why Paytm specifically:** making trust verifiable needs four things at once: a device at the counter, an app in the customer's hand, a payment rail, and lenders. Paytm already has all four. Nobody else has them together.

---

## Part 3: The product in one picture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              BHAROSA                                │
├──────────────────────┬──────────────────────┬───────────────────────┤
│   1. SELL MORE       │   2. GET PAID        │   3. STOCK UP         │
│   ─────────────      │   ───────────        │   ──────────          │
│   Udhaar Guardrail   │   Scan-to-Confirm    │   Festive demand plan │
│   (safe limit)       │   Smart reminders    │   Stock Advance       │
│   Portable Trust     │   (understands       │   (lender pays the    │
│   (new customers)    │    replies)          │    distributor; 20%   │
│   Monthly basket     │   Salary-week        │    of repayments go   │
│   (repeat orders)    │   auto-pay           │    back to lender)    │
├──────────────────────┴──────────────────────┴───────────────────────┤
│   GROWTH PLAN: a weekly to-do list for the merchant, by impact      │
├─────────────────────────────────────────────────────────────────────┤
│   TRUST LAYER: verified receivables · Bharosa Score · consent ·     │
│   exposure caps · fraud checks                                      │
└─────────────────────────────────────────────────────────────────────┘
```

**How to read it:** the **trust layer** is the foundation. The three pillars are the merchant-facing benefits built on it. The **growth plan** pulls them together into one weekly action list.

---

## Part 4: The core concept everything depends on, the verified receivable

```
 TODAY (khata app)                         BHAROSA
 ─────────────────                         ───────
 Shopkeeper writes: "Ramesh ₹200"          Shopkeeper records: "Ramesh ₹200"
          │                                          │
          ▼                                          ▼
 One-sided claim                           Ramesh confirms on HIS phone
 (could be wrong, inflated, disputed)      (his logged-in Paytm account)
          │                                          │
          ▼                                          ▼
 Useless to anyone else                    VERIFIED RECEIVABLE
                                           = a debt both sides acknowledged
                                           + a digital repayment trail (UPI)
                                                     │
                       ┌─────────────────────────────┼─────────────────────────┐
                       ▼                             ▼                         ▼
               Bharosa Score               Safe limits for              Collateral for a
               (credit identity)           future credit               Stock Advance
```

**Why this matters:** once a debt is verified, it becomes **data**, and data can be used to decide limits, build a credit identity, and get the shop funded. Everything in Bharosa flows from this one step.

---

## Part 5: The real architecture (production view)

This is the solution as it would run inside Paytm. The demo simulates the outer edges; the middle is the real product.

```
┌────────────────────────────── PAYTM SURFACES ──────────────────────────────────┐
│  Soundbox (classic or AI)      Paytm for Business app       Paytm consumer app │
│  speaker, display, voice       (merchant)                   (customer)         │
└──────────────┬───────────────────────────┬────────────────────────────┬────────┘
               │ intents, voice text        │ approvals, views           │ scans, confirms,
               ▼                            ▼                            ▼ pays, consents
┌──────────────────────────────── BHAROSA PLATFORM ──────────────────────────────┐
│                                                                                │
│  ① ACCESS LAYER   API gateway · identity & roles · consent checks              │
│                                                                                │
│  ② AI LAYER (proposes, never decides)                                          │
│     Speech in/out · Counter Agent · Recovery Agent · Growth Agent              │
│                 │  structured proposals                                        │
│                 ▼                                                              │
│  ③ VALIDATION    schemas · policy rules · "numbers must match the ledger"      │
│                 │                                                              │
│                 ▼                                                              │
│  ④ TRUST CORE (deterministic: the source of truth)                             │
│     Ledger & entry life cycle · Score engine · Risk engine (safe limits,       │
│     exposure caps) · Consent & Portable Trust · Request service (QR bridge)    │
│                                                                                │
│  ⑤ MONEY & GROWTH SERVICES (deterministic)                                     │
│     Payments & allocation · Split router · Mandate scheduler (AutoPay) ·       │
│     Festive planner · Basket predictor · Stock Advance · Growth candidates     │
│                                                                                │
│  ⑥ PROTECTION      Integrity / fraud graph · velocity checks · audit log       │
│                                                                                │
│  ⑦ EVENTS & NOTIFICATIONS   event stream · push / SMS / Soundbox audio         │
└───────────────────────────────────────────┬────────────────────────────────────┘
                                            ▼
┌────────────────────────────────── RAILS ───────────────────────────────────────┐
│  UPI · UPI AutoPay · Credit line on UPI (partner banks) · Lending partners     │
│  Distributor payments · Licensed credit-information partner (for scoring)      │
└────────────────────────────────────────────────────────────────────────────────┘
```

### Each layer in one sentence
| Layer | What it does | Why it's separate |
|---|---|---|
| ① Access | Knows who you are (merchant/customer) and what you may see | Privacy is enforced in one place, not scattered |
| ② AI | Turns messy human input into structured suggestions, and numbers into human words | Isolates non-determinism |
| ③ Validation | Checks every AI suggestion against rules and real data | The firewall between AI and money |
| ④ Trust core | The ledger, scores, limits, consent: the truth | Must be exact, auditable, explainable |
| ⑤ Money & growth | Moves money, splits repayments, plans stock, predicts baskets | Deterministic maths |
| ⑥ Protection | Catches fraud patterns, logs everything | Lending needs an audit trail |
| ⑦ Events | Tells every screen and device what changed | Real-time experience |

---

## Part 6: One transaction, end to end

*Ramesh asks for ₹340 on credit. He owes ₹1,700, 19 days overdue.*

```
Shopkeeper        Soundbox        Bharosa platform                     Ramesh's phone
    │                │                   │                                   │
    │ "Ramesh 340"   │                   │                                   │
    │──────────────► │ text / intent ──► │ ① who is "Ramesh"? (rule match,   │
    │                │                   │    or Counter Agent if messy)     │
    │                │                   │ ④ Risk engine:                    │
    │                │                   │    score 662 → base ₹3,215        │
    │                │                   │    overdue 19d → ×0.6             │
    │                │                   │    minus ₹1,700 owed → ₹200       │
    │                │ ◄── 🟠 "Give ₹200, collect ₹140" (+ reasons)           │
    │ accepts        │                   │                                   │
    │──────────────► │ ────────────────► │ ④ Ledger: entry PROPOSED          │
    │                │                   │    Request service: one-time token│
    │                │ ◄── QR (token)    │                                   │
    │                │                   │                                   │
    │                │      Ramesh scans QR with his app ───────────────────►│
    │                │                   │ ◄── "Pay ₹140 & confirm" ─────────│
    │                │                   │ ① identity check: is this Ramesh? │
    │                │                   │ ⑤ ₹140 recorded as a SALE         │
    │                │                   │ ④ entry → VERIFIED                │
    │                │                   │ ⑥ fraud check (shared device?)    │
    │                │                   │ ⑦ notify all screens              │
    │                │ ◄── "✓ Confirmed by Ramesh" (+ spoken line)            │
    │ ledger updated │                   │                                   │
```

**Notice what AI did:** at most, it understood the sentence "Ramesh 340". **Everything after that is deterministic code.**

---

## Part 7: The components, explained simply

### 7.1 Ledger and entry life cycle (the truth)
```
proposed ─confirm─► verified ─part paid─► partly paid ─paid─► settled
   ├─dispute─► disputed ─cancel─► cancelled
   └─no confirm─► expired
```
- Every credit is an **entry** with a state. Only the customer's confirmation makes it **verified**.
- **Design decision:** a state machine, not free-form records, so every entry is always in exactly one known state, and lenders can trust what "verified" means.

### 7.2 Score engine (credit identity)
```
Score = 600 + 15×(on-time repayments) − 10×(late) − 2×(days overdue now) − 60×(never repaid)
        kept between 300 and 900
```
- **Computed live from history, never stored as a number someone can edit.**
- **Design decision:** a simple, transparent formula rather than a black-box ML model, because a customer must understand why their score moved, a merchant must trust it, and a regulator must be able to audit it. In production this could become a learned model, but it would still need explainable reasons.

### 7.3 Risk engine (the Udhaar Guardrail)
```
base limit ← score (₹500 … ₹5,000)
   × overdue penalty here (1.0 / 0.75 / 0.6 / 0)
   − what they already owe here
   capped by the network exposure room (total owed across all shops)
New to this shop?  no consent → starter ₹500
                   consent    → 40% of base, max ₹1,500
```
- Output: a **safe limit**, a **colour** and **reasons**.
- **Design decisions:**
  - *Suggest, never block:* the shopkeeper can always override (it's their money).
  - *Exposure cap:* stops one customer borrowing across many shops.
  - *New-shop discount:* trust is earned locally, not just imported.

### 7.4 Consent and Portable Trust
- A customer's score is used at a new shop **only after they tap "Share"**. They can revoke it.
- The merchant sees a **limit and a band**, never other shops' names or amounts.
- **Design decision:** consent and minimal disclosure are built in from day one, because sharing repayment data across businesses is sensitive and likely regulated.

### 7.5 Request service (the QR bridge)
- When credit is proposed, Bharosa creates a **one-time, short-lived request** tied to a specific customer.
- The QR (or a push notification) points to it. Only the **right logged-in customer** can open it.
- **Design decision:** this bridge lets *any* device (classic Soundbox with a printed QR, AI Soundbox with a screen, or just the merchant's phone) connect a counter action to the customer's phone. **No new hardware required.**

### 7.6 Payments, allocation and the split router
- A payment is either a **sale** (paying now for today's goods) or a **repayment** (paying off udhaar).
- Repayments clear the **oldest debt first**.
- If the shop has a Stock Advance, each UPI/auto-pay repayment is **split 80/20** between shop and lender until the advance is repaid.
- **Design decision:** repayment follows the shop's own cash flow. Good weeks repay faster, bad weeks don't hurt.

### 7.7 Mandate scheduler (salary-week auto-pay)
- The customer approves a UPI AutoPay mandate: a **cap** and a **collection day**.
- Bharosa sends a **notice 24 hours before**, with the exact verified dues, and the customer can **skip** a month.
- The merchant side triggers the debit on the day.
- **Design decision:** follow UPI AutoPay's actual rules (merchant-triggered, pre-debit notice), not "debit when salary lands", which isn't allowed and would need bank-account access.

### 7.8 Growth services
- **Festive planner:** last year's festive-week sales ÷ normal weeks → uplift by category → a recommended order.
- **Basket predictor:** items bought in the same week of most months → a predicted monthly basket.
- **Stock Advance:** gap = order − cash available; capped at 40% of verified receivables from reliable customers; paid **directly to the distributor**.
- **Growth candidates:** the code produces a short list of actions with **expected impact in rupees**.
- **Design decision:** growth is computed from the shop's own data by code; AI only explains it.

### 7.9 Protection
- Fraud patterns: same device for many customers, instant confirmations, round amounts, money going in circles, credit at many new shops quickly.
- Suspicious entries are **excluded from lending decisions**; advances can be blocked.
- Everything is **logged** (who, what, when, why).

---

## Part 8: The role of AI, explained from scratch

### 8.1 The fundamental question: what is an LLM good and bad at?
| LLMs are good at | LLMs are bad at |
|---|---|
| Understanding messy language ("Ramesh ne kal ke 200 diye aur aaj 340 liya") | Exact arithmetic |
| Many languages and code-mixing | Giving the same answer every time |
| Writing natural, polite messages | Being auditable ("why exactly did you decide this?") |
| Explaining numbers in plain words | Not inventing facts when unsure |
| Planning which tools to call to answer a question | Being trusted with money |

**So the design follows directly:** use AI only where its strengths matter, and never where its weaknesses are dangerous.

### 8.2 The boundary: deterministic vs non-deterministic
```
                 NON-DETERMINISTIC ZONE            │        DETERMINISTIC ZONE
                 (AI: may vary run to run)         │        (code: same input → same output)
                                                   │
  Voice ──► Speech-to-text ──► Counter Agent ──────┼──► Validator ──► Risk engine ──► Limit
                                                   │
  Customer reply ──► Recovery Agent ───────────────┼──► Validator ──► Promise stored
                                                   │
  Growth candidates (from code) ──► Growth Agent ──┼──► Validator ──► Plan text shown
  (numbers fixed)                  (writes words)  │
                                                   │    Score · Limits · Ledger ·
                                                   │    Payments · Split · Advance ·
                                                   │    Mandates · Fraud checks
                                        ▲          │
                                        │          │
                               THE FIREWALL: every AI output crosses a validator
```

**The rule:** **"AI proposes, code disposes."** AI output is only ever a *proposal* (a structured suggestion or some words). A deterministic validator decides whether it's accepted.

### 8.3 What an "agent" means here
In Bharosa, an agent is: **an LLM + a specific job + (sometimes) read-only tools + a strict output format + a validator + a fallback.**

```
            ┌───────────────────────────── ONE AGENT ─────────────────────────────┐
 input ───► │ prompt (job + rules) ──► LLM ──► JSON proposal ──► VALIDATOR ──┐     │
            │                           ▲                                    │     │
            │                 read-only tools (optional)        pass? ──yes──┼──► action / words
            │                 e.g. get_forecast, list_overdue        │       │     │
            │                                                        no      │     │
            │                                     FALLBACK (rules/template) ─┘     │
            └─────────────────────────────────────────────────────────────────────┘
```

**Agents can read, never write.** Tools only fetch information. Any change to data goes through the normal deterministic services, usually after a human taps a button.

### 8.4 The agents and why each one is justified
| Agent | Job | Why rules alone aren't enough | What it can never do |
|---|---|---|---|
| **Speech (Sarvam)** | Voice → text, text → voice, in Kannada/Hindi/English | Speech recognition is inherently AI | Decide anything |
| **Counter Agent** | "Ramesh ne 340 ka saaman liya" → `{customer, amount}` | 11 languages, mixing, number words, multiple instructions | Invent a customer or amount; set a limit |
| **Recovery Agent** | Writes reminders; turns "salary late hai, 10 ko half dunga" into `{promise: 50%, 10th}` | Replies are open-ended; templates can't understand them | Change dues; approve a plan outside policy |
| **Growth Agent (Munim)** | Explains the weekly plan; answers "How do I pay Sharma on Friday?" using tools | Combining several data sources into advice in plain words | Change numbers (every ₹ figure must match code's) or take actions without approval |

**Why not more agents?** Every extra agent adds non-determinism, latency and cost. We used AI only where the input is genuinely messy language.

**Why not zero agents?** Then the merchant must type exact formats, reminders are generic, and replies are ignored. That's just another khata app, and it doesn't work for a shopkeeper speaking Kannada at a busy counter.

### 8.5 How non-determinism is contained
1. **Strict output formats:** the LLM must return JSON in a fixed shape; anything else is rejected.
2. **Grounding checks:** any rupee figure the AI writes must exist in the system's own numbers. Any customer it names must exist.
3. **Rules first, AI second:** simple inputs ("Ramesh 340") are parsed by rules; AI is called only when rules fail. That's faster, cheaper and predictable.
4. **Human approval for money:** the shopkeeper approves actions; the customer confirms credit.
5. **Fallbacks everywhere:** if the AI is down or wrong, templates and rules take over. The product keeps working.
6. **In production, add:** test sets of real phrases per language, accuracy monitoring, and logging of every AI proposal and validator decision.

### 8.6 The one-sentence answer for judges
> **"We use AI where the world is messy (speech, languages, conversations, explanations) and code where money moves. The AI can suggest; it can never decide or pay."**

---

## Part 9: Key design decisions (and why)

| Decision | Alternative we rejected | Why |
|---|---|---|
| **Customer confirms on their own phone** | Shopkeeper-only records | A one-sided record can't be trusted by anyone else |
| **Works with any Soundbox + printed QR** | Require the AI Soundbox | Most merchants have speaker-only devices; no new hardware |
| **Score from a transparent formula** | Black-box ML score | Customers, merchants and regulators need to understand it |
| **Suggested limit, override allowed** | Hard block | It's the shopkeeper's money and relationship |
| **Consent before using network score** | Share by default | Privacy, and likely regulation |
| **Merchant sees band + limit only** | Show full history | Minimal disclosure; no neighbourhood gossip |
| **Exposure cap across shops** | Per-shop limits only | Stops one customer borrowing everywhere at once |
| **Lender pays distributor directly** | Cash loan to the merchant | Can't be misspent; lower risk; cheaper |
| **Repay via 20% of repayments** | Fixed instalments | Follows the shop's cash flow; nothing to remember |
| **Merchant-triggered AutoPay with 24h notice** | "Debit when salary lands" | That's how UPI AutoPay actually works |
| **Above-limit credit goes to a partner bank** | Shop extends more risk | The regulated bank carries that risk |
| **Rules before AI** | AI for everything | Speed, cost, predictability |
| **AI never touches money** | AI decides limits | Non-determinism + money = unacceptable |

---

## Part 10: Demo vs real solution

| Part | In the real solution | In our prototype |
|---|---|---|
| Soundbox | Paytm devices send voice/text | A web page that looks and behaves like the AI Soundbox |
| Customer app | Bharosa inside the Paytm app | Our phone web app, styled like Paytm |
| Merchant app | Bharosa inside Paytm for Business | Our web app, styled like it |
| Ledger, score, limits, requests, split, advance sizing, fraud check | **Same logic** | **Real code** |
| UPI, AutoPay, credit line, lender, distributor | Real rails and partners | Simulated adapters with the same shape |
| Customer history | Real Paytm data, with consent | 4 customers + 6 regulars, fixed seed |
| AI | Sarvam (or Paytm's own models) | Sarvam, behind an on/off switch |
| Infrastructure | Paytm's cloud: Postgres, event streaming, caches | FastAPI + SQLite on a laptop, with a secure tunnel for phones |

**The line to use:** *"The intelligence is real; the rails are simulated behind adapters shaped like Paytm's. Swap the adapters, and this runs on Paytm."*

---

## Part 11: Who benefits, and how

### For the merchant
| Benefit | Mechanism |
|---|---|
| **More customers** | Portable Trust: safely serve people they've never met |
| **More sales per customer** | Clear safe limits; monthly baskets become repeat orders |
| **Seasonal growth** | Diwali stock planned and funded |
| **Money back faster** | Confirmed debts, reminders that understand replies, salary-week auto-pay |
| **Fewer losses** | The guardrail stops over-extending to overdue customers |
| **No awkwardness** | The system reminds, so the shopkeeper doesn't have to |

### For Paytm
| Benefit | Why it matters to Paytm |
|---|---|
| **Soundbox engagement** | Daily use beyond payment alerts; supports device subscription retention (about 1.57 crore merchant subscriptions) |
| **Lending distribution growth** | Stock Advances and better-timed merchant loans, where Paytm already earns distribution revenue |
| **New consumers in the Paytm app** | Customers install Paytm to confirm credit and build a score |
| **More UPI and AutoPay volume** | Repayments and mandates flow through Paytm |
| **A network moat** | Portable Trust gets more valuable with every merchant; a competitor with fewer merchants can't copy it |
| **No balance-sheet risk** | Paytm doesn't lend udhaar; regulated partners carry credit risk |

### For customers and lenders
- **Customers:** credit at more shops, a credit identity from everyday life, convenience.
- **Lenders:** short, self-repaying advances backed by verified receivables; new pre-verified borrowers.

---

## Part 12: The pitch

### 30-second version
> "Every kirana is secretly a lender. It gives udhaar to keep customers, but it does it blind, so it rations credit out of fear, and every 'no' is a lost sale. Bharosa makes that trust verifiable using Paytm's Soundbox, the Paytm app, UPI and lending partners. Merchants sell more on credit safely, including to new customers carrying their Bharosa Score; they get paid without chasing; and they stock up for Diwali without cash. Khata apps record udhaar. Bharosa turns it into growth."

### 2-minute version
1. **Problem (20 s):** "Udhaar is a kirana's loyalty programme and its weapon against quick commerce. But the shopkeeper lends blind: no risk check, no proof, no collections, no funding. So they ration it, and lose sales."
2. **Insight (15 s):** "The problem isn't the notebook. It's that trust is invisible. Make it verifiable and credit becomes a growth tool."
3. **Product (40 s):** "At the counter, the Guardrail suggests a safe limit in a second. The customer confirms on their own phone, so the debt is verified. A customer new to the shop can share their Bharosa Score and get credit safely: a new customer won. Reminders understand replies; auto-pay collects in salary week. And for Diwali, Bharosa plans the stock and a partner lender pays the distributor directly, repaid from 20% of incoming repayments."
4. **AI (20 s):** "AI handles what's messy: Kannada and Hindi speech, conversations, explanations. Code handles money: scores, limits, payments. The AI suggests; it never decides."
5. **Why Paytm (15 s):** "Only Paytm has the device on the counter, the app in the customer's hand, the payment rail and the lenders, plus a merchant network that makes portable trust possible."
6. **Close (10 s):** "Bharosa grows merchants, grows Paytm's lending and app usage, and carries no balance-sheet risk. Trust, turned into growth."

### Closing line
> **"Bharosa: trust, turned into growth."**

---

## Part 13: Tough questions, short answers

| Question | Answer |
|---|---|
| Isn't this Khatabook? | Khatabook records. We check risk *before* credit, get the customer's confirmation, win new customers through the network, collect automatically, and fund stock. |
| Why would a customer confirm their own debt? | One scan, and on-time repayment of confirmed credit raises their score, which means higher limits at every Paytm shop. |
| Is AI deciding credit? | No. A transparent formula decides; the shopkeeper has the final say. AI handles language. |
| Why agents at all? | Only where input is messy human language. Each agent's output is validated by code, with a fallback if it fails. |
| Who takes the loss if a customer defaults? | The shopkeeper, as today, but with far better information. Paytm takes no credit risk; advances come from regulated lenders. |
| Isn't sharing scores regulated? | Likely, which is why sharing is customer-controlled, disclosure is minimal, and production scoring would run through a licensed partner. |
| Can auto-pay debit on salary day? | Not instantly. UPI AutoPay needs 24-hour notice, so we collect on a date the customer picks in salary week, and they can skip. |
| Can shops fake receivables to get advances? | We check for shared devices, instant confirmations, round amounts and money going in circles, and exclude suspicious entries. |
| Does it need the new AI Soundbox? | No. It works with any Soundbox and the printed QR; the AI Soundbox just adds voice and screens. |
| How does Paytm make money? | Lending distribution fees on advances and loans, bank fees for credit-line customers acquired at the counter, collections, and an optional premium tier. |

---

## Part 14: How to explain it to different people

- **Business judge:** lead with the merchant's lost sales, Portable Trust (new customers) and Diwali stock. End with Paytm's revenue lines and zero balance-sheet risk.
- **Technical mentor:** lead with the verified receivable, the deterministic core, the AI firewall (proposal → validator → fallback) and the adapter design.
- **Risk or compliance person:** lead with consent, minimal disclosure, the exposure cap, the fraud checks, AutoPay compliance and who carries which risk.
- **Anyone short on time:** the 30-second pitch, then hand them the phone to scan the QR.

One sentence to hold everything together: **"Make trust verifiable, and credit becomes a growth engine. AI handles the language, code handles the money, and Paytm already has every piece."**
