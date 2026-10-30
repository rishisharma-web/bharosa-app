# Bharosa: The Complete Overview (v2)

**Team MerchantMavericks** · Sujay Mohanty · Sukruth N · Rishi Sharma
Paytm Build for India AI Hackathon, Bengaluru · Track 1: Merchant Growth AI · Finals: 31 October 2026

*Bharosa (भरोसा / ಭರವಸೆ) means "trust". This document explains Bharosa from scratch: the problem, the philosophy, how it works end to end, where AI fits and where it deliberately doesn't, who carries which risk, how it helps a merchant grow, and exactly what our prototype shows. It replaces the earlier overview. No prior context is needed.*

---

## 1. Bharosa in one minute

Almost every kirana in India runs a quiet credit business. Customers take groceries now and pay later ("udhaar", or "put it on my account"). Udhaar is how a neighbourhood store wins and keeps customers. It's the kirana's loyalty programme and its best answer to quick-commerce apps.

But the shopkeeper runs this credit business blind. Credit is given on gut feel, chased awkwardly, and paid for out of money meant for restocking. So shopkeepers ration credit out of fear, and every "no" is a lost sale.

**Bharosa turns udhaar from a cost into a growth engine.** It's a layer of AI-assisted tools on top of what Paytm already has (the Soundbox on the counter, the Paytm app in the customer's hand, UPI, and Paytm's lending partners) that helps a merchant:

1. **Sell more, safely.** Say "yes" to more customers, including new ones the shop has never seen.
2. **Get paid without chasing.** Customers confirm credit on their own phone, and repayments can be collected automatically in salary week.
3. **Stock up without cash.** Plan for demand like Diwali, and have a lender pay the distributor directly.

> **One-line pitch:** "Khata apps record udhaar. Bharosa turns it into growth: sell more on trust, get paid without chasing, stock up without cash."

---

## 2. The problem, from first principles

### 2.1 A kirana is secretly a lender
When Ramesh takes ₹340 of groceries and says "I'll pay at month-end", Lakshmi Stores has lent him ₹340.

| What a lender does | What the shopkeeper does today |
|---|---|
| Checks risk before lending | Gut feel and memory |
| Gets the borrower to acknowledge the debt | Writes it in a notebook; the customer signs nothing |
| Collects systematically | Awkward reminders to a neighbour, or doesn't ask |
| Has its own funding | Uses stock money |

### 2.2 The squeeze
Distributors want payment in about 7–14 days. Customers pay "when they can". The gap comes out of the shop's working capital, so many kiranas order stock only when they have cash in hand.

### 2.3 Fear limits growth
Because the shopkeeper can't tell a reliable customer from a risky one, they refuse customers they don't know, cap credit even for good customers, and can't stock up for busy seasons. **The real problem isn't record-keeping. Trust is invisible, so the merchant can't safely use credit to grow.**

### 2.4 Why existing tools don't solve it
- **Khata apps** (Khatabook, OkCredit, Paytm's Business Khata) digitised the notebook and send reminders. But only the shopkeeper enters the record, nothing checks risk before credit is given, and nothing helps the shop grow or get funded.
- **The Paytm Soundbox** announces payments; the newer AI Soundbox talks to merchants about their payments. Neither knows who owes the shop money.
- **Merchant loans** exist, but they aren't linked to the udhaar that caused the cash squeeze, or to growth moments like festivals.

---

## 3. The core philosophy

1. **Trust is an asset; make it verifiable.** When both the shopkeeper *and* the customer confirm a credit entry, it becomes a *verified receivable*: data that can be used for limits, planning and funding.
2. **A safe "yes" is growth.** The goal isn't to stop credit; it's to let the merchant say yes more often, to more people, without fear.
3. **AI proposes, code decides.** AI handles messy things (language, conversations, explanations). Anything involving money (limits, scores, balances, payments) is decided by transparent rules. The merchant always has the final say.
4. **Build on Paytm, not beside it.** Reuse the Soundbox, the Paytm app, UPI and lending partners. Add the intelligence layer on top.
5. **The customer controls their data.** A customer's score is shared with a shop only when they choose to. Shopkeepers see a suggested limit and a band, never another shop's records.
6. **Works for every merchant.** Bharosa doesn't need new hardware. It works with any Paytm Soundbox and printed QR, and does more on the AI Soundbox.

---

## 4. What Bharosa is: three pillars and a trust layer

```
        ┌──────────────────────────────────────────────────────────────┐
        │                         BHAROSA                              │
        │          "Udhaar from a cost into a growth engine"           │
        ├───────────────────┬────────────────────┬─────────────────────┤
        │  1. SELL MORE     │  2. GET PAID       │  3. STOCK UP        │
        │  Udhaar Guardrail │  Scan-to-Confirm   │  Diwali stock plan  │
        │  Portable Trust   │  Smart reminders   │  Stock Advance      │
        │  Monthly basket   │  Salary-week       │  (lender pays the   │
        │                   │  auto-pay          │   distributor)      │
        ├───────────────────┴────────────────────┴─────────────────────┤
        │  GROWTH PLAN: the merchant's weekly to-do list, by impact    │
        ├──────────────────────────────────────────────────────────────┤
        │  TRUST LAYER: Bharosa Score · verified receivables ·         │
        │  consent · exposure limits · fraud checks                    │
        └──────────────────────────────────────────────────────────────┘
```

### Pillar 1: Sell more, safely
- **Udhaar Guardrail.** When a customer asks for credit, the shopkeeper instantly sees a suggested safe limit: green (safe), amber (give part on credit, collect the rest now), or red (collect payment), with plain reasons.
- **Portable Trust.** A customer's good record at other Paytm shops can travel with them, if they choose to share it. A shop can then safely give credit to someone it has never seen, and win a customer it would have turned away.
- **Monthly basket.** For regulars who buy the same things every month, Bharosa predicts the basket and offers it on credit. One-off udhaar becomes a repeat order.

### Pillar 2: Get paid without chasing
- **Scan-to-Confirm.** The customer scans a QR at the counter with their phone and confirms the credit in their own app. The debt is now acknowledged by both sides.
- **Smart reminders.** Polite reminders in the customer's language. Replies like "salary 1 tareekh ko aati hai" (my salary comes on the 1st) are understood and recorded as promises.
- **Salary-week auto-pay.** The customer can set up a UPI AutoPay mandate so verified dues are collected on a date they choose in salary week, with advance notice.

### Pillar 3: Stock up without cash
- **Diwali stock plan.** Bharosa compares last year's festive sales with normal weeks and recommends what to stock.
- **Stock Advance.** If buying that stock would leave the shop short, a partner lender pays the distributor directly. The advance is repaid automatically from 20% of incoming repayments.

### The growth plan
Each week the merchant sees a short to-do list, ranked by expected impact, with one-tap approval. In our demo:
1. **Stock up for Diwali:** about +₹27,400 in expected extra sales
2. **Remind 2 overdue customers:** ₹4,300 overdue
3. **Offer Priya her monthly basket:** a ₹1,850 order

### The trust layer
- **Bharosa Score (300–900):** calculated live from a customer's repayment history.
- **Verified receivables:** credit confirmed by both sides; the basis for limits and advances.
- **Consent:** separate permissions for sharing a score and for auto-pay.
- **Exposure limits and fraud checks:** caps on total credit across shops, caution at new shops, and detection of fake-udhaar patterns.

---

## 5. Who uses Bharosa, and how

| Who | Device and app | What they see | What they get |
|---|---|---|---|
| **Shopkeeper** | Paytm Soundbox (any model) + Paytm for Business app on their phone | Safe limits at the counter; growth plan; dues; stock plan and advance | More sales, new customers, faster collection, stock without cash |
| **Customer** | Paytm app | Confirm requests; dues; Bharosa Score and how it's calculated; auto-pay; basket offers | Credit at more shops, a credit identity built from everyday life |
| **Paytm** | The platform | Network of trust (with consent) | Daily Soundbox use, more UPI and AutoPay, more lending distribution, new app users |
| **Partner lender** | Partner APIs | Advance requests backed by verified receivables | Short, self-repaying advances |
| **Distributor** | Receives payments | Bills paid on time | Faster payment, bigger festive orders |

### 5.1 Works on every Paytm Soundbox
Paytm has many Soundbox models. Most are a **speaker** that announces payments next to a **printed QR**; some have small displays; the **AI Soundbox** (launched October 2025) adds a voice assistant button and two displays, including a customer-facing screen that shows the payment QR.

| | Classic Soundbox (most merchants) | AI Soundbox |
|---|---|---|
| Recording credit | Shopkeeper speaks or types in the Paytm for Business app on their phone | Shopkeeper speaks to the Soundbox (Paytm Button) |
| Seeing the guardrail | Spoken by the Soundbox speaker + shown on the phone | Shown on the top display (and spoken) |
| Customer confirmation | Customer scans the shop's **printed QR**; their Paytm app shows the pending request; or a push notification | Customer scans a **QR for this specific entry** on the front screen |

**Our prototype shows the AI Soundbox experience.** The Classic path uses the same backend. Only the screen differs.

### 5.2 The role of sound
Sound is kept short and useful, never chatty:
- **In:** the shopkeeper can say "Ramesh, 340 udhaar" in Kannada, Hindi or English.
- **Out:** one short spoken line per event: the guardrail verdict, "Ramesh confirmed ₹200 udhaar", "₹500 received from Ramesh". For Classic Soundboxes, which have no screen, this is the main way the shopkeeper hears the verdict.

Paytm's Soundbox already understands speech in 11 Indian languages. In our prototype, Sarvam AI's speech models play that role, when the AI switch is on.

---

## 6. How it works end to end

*Our story is set at **Lakshmi Stores**, Jayanagar, Bengaluru, on **Saturday 31 October 2026**, eight days before Diwali.*

### 6.1 The cast
| Customer | Situation | Bharosa Score |
|---|---|---|
| **Priya Nair** | 12 credit purchases this year, always paid on time | **780** (Strong) |
| **Ramesh Kumar** | Usually pays, sometimes late; owes ₹1,700, 19 days overdue | **662** (Good) |
| **Vikram Rao** | Often late, once never paid; owes ₹2,600, 41 days overdue | **438** (Building) |
| **Anita Desai** | Never shopped here; 13 credit purchases at other Paytm shops, 12 on time | **770** (Strong) |

### 6.2 How the score is calculated (code, not AI)
Every customer starts at 600. Then:
- **+15** for each credit repaid on time
- **−10** for each credit repaid late
- **−2** for each day their oldest unpaid credit is overdue
- **−60** for each credit never repaid

The result is kept between 300 and 900. The customer can see exactly how their score was calculated ("12 on-time repayments: +180"). For example, Ramesh: 600 + 8×15 − 2×10 − 19×2 = **662**.

### 6.3 How the safe limit is calculated (code, not AI)
1. A higher score gives a higher **base limit** (₹500 at 300, up to ₹5,000 at 900).
2. If the customer is **overdue here**, the base is reduced (by a quarter for up to 2 weeks, by 40% for up to a month, to zero beyond that).
3. Subtract what they **already owe here**.
4. Never exceed what they can safely owe **across all Paytm shops** (the exposure cap).
5. **At a shop they're new to:** without sharing their score, a small starter limit (₹500). With sharing, 40% of their network base, at most ₹1,500.

The shopkeeper can always override the suggestion; overrides are recorded.

### 6.4 At the counter: three customers, three answers
The shopkeeper records "Priya, 340 udhaar" (by voice, or a tap on the Soundbox):

| Customer | Asks for | What the shopkeeper sees |
|---|---|---|
| Priya | ₹340 | 🟢 "Safe. Priya can take up to ₹4,100." |
| Ramesh | ₹340 | 🟠 "Caution. Give ₹200 on credit, collect ₹140 now." (₹1,700 overdue for 19 days) |
| Vikram | ₹340 | 🔴 "High risk. Collect full payment (₹340)." |

### 6.5 Confirmation on the customer's phone
The shopkeeper accepts the suggestion. The Soundbox's customer-facing screen shows a QR: **"Scan to confirm ₹200 udhaar · Lakshmi Stores"**.

Ramesh scans it with his phone. His app shows: *Lakshmi Stores · ₹200 on credit · due 30 Nov · Pay ₹140 now*. He taps **"Pay ₹140 & confirm"**. Within a second, the Soundbox shows "✓ Confirmed by Ramesh" and the shopkeeper's app shows the entry as **Verified**.

**Why would Ramesh confirm his own debt?** It's one scan, and repaying confirmed credit on time raises his Bharosa Score, which means higher limits at every Paytm shop.

**If something's wrong,** he taps **Dispute** ("wrong amount"). The shopkeeper sees it and can cancel the entry. **If he doesn't scan,** the request expires and nothing is recorded as verified.

The life of a credit entry:
```
proposed ──customer confirms──► verified ──part paid──► partly paid ──paid──► settled
    ├──customer disputes──► disputed ──shopkeeper cancels──► cancelled
    └──no scan in 15 minutes──► expired
```

### 6.6 A new customer, won through the Paytm network
Anita asks for ₹2,000 of groceries on credit. She has never shopped here.
1. The Soundbox shows: *"New customer. Ask her to scan to share her Bharosa Score. Starter limit ₹500."* Its customer screen shows a **"New here? Scan to share your Bharosa Score"** QR.
2. Anita scans. Her app asks: **"Share your Bharosa Score with Lakshmi Stores? They'll see your score band and a suggested limit, never your other shops or amounts."** She taps **Share**.
3. The shopkeeper's display updates: *"Network-trusted new customer. Give ₹1,500 on credit, collect ₹500."*
4. Anita's app moves straight to confirmation. She pays the ₹500 with a **credit line on UPI from a partner bank** (the shop is paid instantly; the bank carries that risk) and confirms the ₹1,500.
5. The shopkeeper's app tags her **"New · Paytm network"**: a customer won that would otherwise have been turned away.

If she taps **Not now**, she gets the ₹500 starter limit. Nothing is shared without her choice, and she can revoke sharing later.

### 6.7 Stocking up for Diwali
The growth plan's top action: *"Stock up for Diwali. Last year your Diwali-week sales were about 1.6× normal. A ₹18,000 order of sweets and dry fruits, oil and ghee, snacks and puja items could bring about ₹27,400 in extra sales."*

1. The shopkeeper taps **Approve**. An ₹18,000 order to Sharma Traders is placed, due Friday 6 November.
2. The shop will only have ₹8,800 available by then: a **₹9,200 gap**.
3. Bharosa offers a **Stock Advance** from a partner lender: ₹9,200, fee ₹138, repaid from 20% of incoming repayments, to be cleared by 30 November.
4. The shopkeeper accepts. **The lender pays Sharma Traders ₹9,200 directly.** The shop pays the other ₹8,800.

**Why the lender can say yes:** the shop has ₹23,200 of **verified** receivables from reliable customers. The advance is capped at 40% of that (₹9,280). Vikram's dues don't count, because his score is too low.

### 6.8 Getting paid
- **Reminders.** The shopkeeper approves "Remind 2 overdue customers". Ramesh and Vikram receive polite messages in their apps.
- **Replies understood.** Ramesh replies: *"Salary 1 tareekh ko aati hai, tab de dunga"* ("My salary comes on the 1st; I'll pay then"). Bharosa records a **promise of ₹1,900 on 1 November** and suggests: *"Set up salary-week auto-pay so you never miss it?"*
- **Salary-week auto-pay.** Ramesh sets it up: up to ₹3,000, collected on the 2nd of each month. His app shows: *"Next collection: Mon 2 Nov · amount = your verified dues (now ₹1,900) · notice on Sun 1 Nov."*
- **The repayment split.** Ramesh also pays ₹500 now. Because the Stock Advance is active, Bharosa splits it automatically: **₹400 to the shop, ₹100 to the lender.** The advance progress bar moves.

### 6.9 The monthly basket
Priya buys the same 8 items in the first week of every month: atta, rice, toor dal, oil, sugar, tea, salt and detergent, totalling ₹1,850. The shopkeeper approves "Offer Priya her monthly basket". Priya's app shows the offer; she accepts. It becomes a verified credit entry, and the shopkeeper sees it in **Orders** to pack and deliver.

---

## 7. Salary-week auto-pay: how it stays within the rules

**How UPI AutoPay works:**
- A **customer approves a mandate**, but **each debit is triggered by the merchant side**, through its payment provider.
- A **pre-debit notification** must reach the customer **at least 24 hours before** each debit.
- Debits **under ₹15,000** go through without the customer re-authenticating.
- A mandate can allow a **variable amount up to a cap** ("as presented").

**What this rules out:** "pay the instant my salary arrives". That would break the 24-hour notice rule, and the shop can't see the customer's bank account anyway.

**Bharosa's design:**
1. The customer sets a **cap** (e.g. ₹3,000) and a **collection day** in salary week (e.g. the 2nd).
2. The day before, Bharosa sends a **notice** with the exact verified dues, never more than the cap. The customer can **skip** that month if salary is late.
3. On the collection day, the merchant side collects; the Stock Advance split applies.

**In the prototype,** auto-pay is shown set up, with its schedule; it doesn't execute, because the demo has no moving clock.

*This reflects published UPI AutoPay rules as described by payment providers. A production launch would need confirmation from Paytm's compliance team.*

---

## 8. Where AI comes in, and where it deliberately doesn't

### 8.1 The rule
**AI is used where the world is messy. Code is used where money moves.**

| Job | AI or code | Why |
|---|---|---|
| Bharosa Score | Code | Transparent, explainable |
| Safe limit | Code | Same answer every time; auditable |
| Payments, the 20% split, the advance | Code | Money must be exact |
| Diwali plan and basket prediction | Statistics on the shop's own history | Numbers, not language |
| **Understanding what the shopkeeper said** | **AI (Counter Agent)** | Kannada, Hindi, English, mixed; "Ramesh ne 340 ka saaman liya" (Ramesh took ₹340 of goods) |
| **Speech in and out** | **AI (Sarvam speech models)** | Indian languages, code-mixed speech |
| **Writing reminders and understanding replies** | **AI (Recovery Agent)** | Free-text replies must become trackable promises |
| **Explaining the growth plan; answering questions** | **AI (Growth Agent, "Munim")** | Turning numbers into plain advice; answering "How do I pay Sharma on Friday?" |

### 8.2 Why agents, not just rules?
- Rules can't cover real speech: many languages, mixing, and endless ways of saying the same thing.
- Reminder templates already exist in khata apps. Understanding a reply and turning it into a promise is new.
- A shopkeeper's open question needs several pieces of data combined and explained. That's exactly what a tool-using agent does.

### 8.3 How AI is kept safe
1. AI only produces **structured suggestions** or **words**.
2. **Code checks every suggestion.** Customers must exist; amounts must match the ledger; any ₹ figure the AI writes must match the system's own numbers.
3. **When unsure, ask a human.** Unclear input asks the shopkeeper to tap a name.
4. **Every money action needs a person:** the shopkeeper's approval or the customer's confirmation.
5. **Fallbacks:** if the AI is unavailable, rules and templates keep everything working.

### 8.4 The AI switch
The prototype has one switch: `SARVAM_ENABLED`. **Off** (the default), everything works with rules and templates: typed names and amounts, standard messages, no voice. **On**, Sarvam AI adds speech in and out (Kannada, Hindi), understanding of free text, and AI-written messages and explanations. **Scores, limits and money are never decided by AI**, whichever way the switch is set.

---

## 9. Risk: who carries what

### 9.1 The money
| Party | Risk |
|---|---|
| **Shopkeeper** | The udhaar loss, as today, but with much better information |
| **Paytm** | None on the money. Paytm doesn't lend, guarantee or insure udhaar |
| **Bharosa's AI** | None. It only suggests |
| **Partner lender** | Stock Advances (backed by verified receivables) |
| **Partner bank** | Credit lines on UPI used at the counter |

Network trust is **information, not a guarantee**, like a reference from other shopkeepers.

### 9.2 Indirect risks Paytm takes on, and how Bharosa handles them
- **Blame risk** (a suggested limit turns out wrong): limits are always suggestions with reasons; customers new to a shop get conservative limits.
- **Bust-out fraud** (a customer builds a score, then borrows at many new shops and disappears): a **network exposure cap**, a **new-shop discount**, and a **velocity check** on credit at several new shops in a short time. The network actually *reduces* this risk: today nobody knows a customer already owes five shops.
- **Regulatory risk:** sharing repayment records between businesses resembles credit information sharing, which is regulated in India (credit bureaus are licensed; personal data needs consent under the DPDP Act). Whether informal udhaar data falls under these rules needs a legal view. Bharosa is designed for this: the customer controls sharing, the merchant sees only a band and a limit, and in production scoring would run through a licensed partner.
- **Above-limit demand** goes to a **credit line on UPI from a partner bank**: the shop is paid instantly, and a regulated bank carries the risk.

> "Paytm doesn't lend a rupee of udhaar. It gives shopkeepers trust information they've never had, with the customer's permission. Credit above the safe limit goes to a regulated bank."

### 9.3 Fraud rings, explained
Because verified receivables can back a Stock Advance, a dishonest shopkeeper might try to **inflate them**:
1. Register friends, relatives or spare SIM cards as "customers".
2. Record large udhaar against them and have them all "confirm".
3. Send them money and have them "repay" it, to fake a good history.
4. Take a big advance against the fake receivables, then disappear.

**The patterns that give it away:** several "customers" confirming from **one phone**; confirmations **seconds** after each entry; **round amounts**; "customers" with **no other payment activity**; and money going **in circles** (shop → customer → shop). Bharosa checks for these. Suspicious entries are excluded from advance eligibility, and the shop's advance can be blocked, with the reasons shown. In the prototype, a simple version runs on every confirmation: credit confirmed from a phone already used by a different customer at the same shop is flagged and excluded.

---

## 10. How Bharosa helps a merchant grow

| Growth lever | How | In the story |
|---|---|---|
| **New customers** | Portable Trust lets a shop safely serve people it doesn't know | Anita: ₹1,500 credit at a new shop |
| **Bigger, safer yes** | Reliable customers get clear, higher limits | Priya: up to ₹4,100 |
| **Repeat orders** | Predicted monthly baskets offered on credit | Priya's ₹1,850 basket |
| **Seasonal upside** | Festive planning plus a Stock Advance | Diwali: about +₹27,400 expected |
| **Freed working capital** | Reminders that work, salary-week auto-pay | Ramesh's promise and auto-pay |
| **Fewer losses** | Guardrail limits exposure to overdue customers | Ramesh: ₹200 instead of ₹340; Vikram: pay first |

The common thread: **credit becomes a tool the merchant uses deliberately, not a risk they ration out of fear.**

---

## 11. Why this, why Paytm, why now

### 11.1 What makes Bharosa different
| Capability | Khata apps | Paytm Soundbox today | Bharosa |
|---|---|---|---|
| Risk check before credit | No | No | Yes |
| Customer confirms on their phone | No | No | Yes |
| Safe credit for new customers | No | No | Yes (Portable Trust) |
| Understands replies; compliant auto-pay | Reminders only | No | Yes |
| Plans and funds festive stock | No | No | Yes |
| Weekly growth plan | No | Payment insights | Yes |

### 11.2 Why only Paytm can do it
- **The device is already on the counter** (Soundboxes, from classic to AI).
- **The customer is already in the app:** identity, UPI, AutoPay, credit lines.
- **The lenders are already partners.**
- **The network:** Portable Trust only works with many merchants on one platform. Paytm reports about 1.57 crore merchant device subscriptions (Q1 FY27).

### 11.3 Why now
- The AI Soundbox (October 2025) brought voice AI to the counter.
- Credit lines on UPI let banks lend small amounts through apps people already use.
- India is preparing for AI agents to make payments on UPI (NPCI's proposed Unified Agent Protocol). Bharosa uses UPI AutoPay today and can use agent mandates when they arrive.

### 11.4 Proof the ideas work elsewhere
- **MYbank** (China) lends to tiny merchants using payment data, with non-performing loans around 1% and processing costs of about RMB 2.30 per loan: data-driven micro-credit can be safe and cheap.
- **Toast** (US) found its merchants' most-used AI request was a short daily briefing; **Shopify** built insights that surface opportunities unprompted. Merchants want AI that speaks first, which is what the growth plan does.

---

## 12. Business model

The core tools (guardrail, confirmation, reminders, score) are **free**. They drive daily use and feed every paid flow.

| Revenue stream | Who pays | Why |
|---|---|---|
| Stock Advance distribution fees | Lending partners | Well-timed advances backed by verified receivables |
| Merchant loan triggers | Lending partners | Better-timed, better-sized loans in Paytm's existing business |
| Credit line on UPI activation | Partner banks | Pre-verified customers acquired at the counter |
| AutoPay collections service | Lending partners / merchants | Automated, compliant collection |
| Bharosa Pro (optional) | Merchants | Advanced planning on the Soundbox subscription |

Paytm carries no balance-sheet risk; credit comes from regulated lenders.

---

## 13. The prototype

### 13.1 Five apps, one backend
| App | Who | What it does |
|---|---|---|
| **Merchant app** (Paytm for Business style) | Lakshmi Stores, logs in with phone + OTP | Growth plan, counter decisions, Diwali stock and advance, collections, orders |
| **Customer app** (Paytm app style) | Priya, Ramesh, Vikram or Anita, log in on a real phone | Scan QR, confirm or share score, pay, score breakdown, messages, auto-pay, basket offers |
| **AI Soundbox** (on the laptop) | The counter | Records credit (tap, type, or voice when AI is on); shows the verdict and the QR |
| **Presenter screen** | The team | Soundbox + merchant app + customer view side by side; login QR codes for the 4 customers; activity list; Reset |
| **Overview** | Everyone | What Bharosa is, the flow, AI vs code, risk and fraud, Soundbox types, auto-pay rules, tech stack |

### 13.2 The highlight: a real phone scan
The Soundbox on the laptop shows a QR. A **real phone** running the customer app (a team member, or a judge logged in as Anita) scans it, shares a score or confirms credit, and **the laptop updates within about a second**. One physical action changes another device, live.

*In production, this would be the Paytm app's own scanner and Paytm's QR codes. In the prototype, our customer web app plays the Paytm app.*

### 13.3 What's real and what's simulated
| Real (working code) | Simulated |
|---|---|
| Score and limits computed live from history | The four customers' past history (fixed seed) |
| Logins, privacy rules, pending requests, phone scanning | UPI payments, credit line on UPI (marked as simulated) |
| Confirmation, disputes, payments, the 20% split | The partner lender and the distributor |
| Diwali plan, Stock Advance, monthly basket, growth plan | Auto-pay execution (setup and schedule only) |
| Reminders and reply understanding (rules; AI when on) | Paytm app and Paytm for Business (our own apps in Paytm style) |
| Sarvam AI speech and language (behind the switch) | — |

**There is no step-by-step demo mode and no simulated crowd.** Every change on screen comes from someone using an app. The demo date is fixed at 31 October 2026, and Reset restores the starting point.

### 13.4 Suggested demo (about 5 minutes)
1. The merchant logs in and sees the growth plan.
2. At the counter: Priya green, Ramesh amber. **Ramesh's phone scans and confirms;** the laptop updates.
3. **A judge becomes Anita** (scans a login QR), scans the share QR, gets ₹1,500 credit, pays ₹500 by credit line, confirms: a new customer won.
4. The merchant approves the Diwali plan and accepts the Stock Advance; the lender pays Sharma Traders.
5. Reminders go out; Ramesh replies; the promise is recorded; he sets up salary-week auto-pay and pays ₹500 now, split ₹400/₹100.
6. Priya accepts her monthly basket; it appears in Orders.
7. With AI on: one spoken Kannada line, and one live reply understood.

---

## 14. Architecture at a glance

```
  Paytm surfaces (our apps)            Bharosa backend                        Rails (simulated)
  ────────────────────────     ─────────────────────────────────────     ─────────────────
  AI Soundbox  ── text/voice ─►  Logins & roles · Live updates            UPI payments
  Merchant app ── approvals ──►                                           Credit line on UPI
  Customer app ── scan, confirm,  AI layer (when switched on)              AutoPay mandates
                  share, pay ───►   Speech in/out · Counter · Recovery ·   Partner lender
                                    Growth wording                         Distributor
                                    (suggests only, always checked)
                                  Core rules (decide)
                                    Score · Safe limit · Portable Trust ·
                                    Requests & confirmation · Payments &
                                    20% split · Diwali plan · Stock Advance ·
                                    Basket · Auto-pay schedule · Fraud check
                                  Database + activity log
```

**Technology:** Python and FastAPI; SQLite; live updates via server-sent events; plain HTML, CSS and JavaScript (with Alpine.js) in Paytm's colours; Sarvam AI for language and speech (switchable); a secure tunnel so phones can reach the laptop. In production, the same rules would run on Paytm's infrastructure, connected to real Paytm and partner systems.

---

## 15. Honest limits and open questions

- **Soundbox integration is our proposal.** We assume the Soundbox can pass text to a partner service and the Paytm app can recognise a Bharosa request when scanning a shop's QR.
- **Score sharing needs a legal view** before launch (section 9.2).
- **Auto-pay** follows published UPI AutoPay rules, but needs Paytm compliance confirmation for this use case.
- **Agent payments on UPI are proposed, not live.**
- **Festive uplift, margins and basket behaviour** come from our synthetic data and stated assumptions; a pilot would measure real numbers.
- **Behaviour change:** customers may hesitate to confirm debts; shopkeepers may hesitate to trust suggested limits. The design addresses both (score benefits, one-scan confirmation, reasons on every suggestion, override always allowed), but a pilot would test it.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| Udhaar | Goods given on credit by a shop to a customer |
| Kirana | A neighbourhood grocery store |
| Verified receivable | A credit entry confirmed by both the shop and the customer |
| Safe limit | The suggested maximum new credit for a customer today |
| Bharosa Score | A customer's repayment record across Paytm shops (300–900), calculated live |
| Portable Trust | Using a customer's Bharosa Score at a new shop, with their consent |
| Exposure cap | The maximum total credit a customer can owe across all shops |
| Salary-week auto-pay | A UPI AutoPay mandate that collects verified dues on a chosen date, with 24-hour notice |
| Monthly basket | A predicted monthly shopping list offered on credit |
| Stock Advance | A lender pays a distributor directly; repaid from 20% of incoming repayments |
| Growth plan | The merchant's weekly list of actions, ranked by expected impact |
| Credit line on UPI | A small bank credit line usable through UPI apps |

---

## 17. References

- Paytm Q1 FY27 earnings datapack: https://paytm.com/document/ir/financial-results/fy2026-27/Paytm_Q1_FY27_Agent_Datapack.md
- Paytm AI Soundbox launch: https://www.fonearena.com/blog/466319/paytm-ai-soundbox-features.html
- Paytm Pocket and Music Soundbox: https://www.fonearena.com/blog/400877/paytm-pocket-soundbox-music-soundbox-features.html
- UPI AutoPay mandate rules (Juspay docs): https://docs.juspay.io/mandates/docs/mandates/description
- NPCI AutoPay on UPI press release: https://npci.org.in/PDF/npci/press-releases/2020/NPCI_Press_Release-NPCI_introduces_AutoPay_facility_on_UPI_for_recurring_payments.pdf
- Sarvam speech-to-text (supported languages): https://docs.sarvam.ai/api-reference-docs/getting-started/models/saarika.md
- Working capital for grocery kiranas (IIM Bangalore): https://repository.iimb.ac.in/handle/2074/19444?mode=full
- MYbank case study (Singapore Management University): https://ccx.smu.edu.sg/sites/cmp.smu.edu.sg/files/ami/7_AMI20_ChinaMybank.pdf
- Toast IQ usage trends: https://pos.toasttab.com/blog/data/q1-2026-restaurant-ai-pos-trends
- NPCI Unified Agent Protocol (proposed): https://www.indianpaycalculator.in/govt-news/ai-agents-upi-payments-npci-unified-agent-protocol-2026
- Credit line on UPI as a loan (RBI, June 2026): https://www.indianpaycalculator.in/govt-news/rbi-upi-credit-line-is-a-loan-june-2026
- Diwali 2026 date: https://haindavam.org/festivals/diwali/2026-11-08/doha
