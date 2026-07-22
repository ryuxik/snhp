# MANDATE — the sponsorship negotiator (wedge spec v1)

**Working name:** Mandate — *"Your agent negotiates. Your numbers stay sealed.
The receipt proves both."*

**One-liner:** A creator's inbound sponsorship deals get auto-triaged and
countered to better terms by an agent that is provably bounded by a sealed
mandate — the creator never reads the lowballs, the brand never sees the
mandate, and both sides can check the receipt.

**Status: PRE-BUILD.** Per the standing pipeline discipline, nothing beyond
this spec + buyer conversations is authorized. The build is gated on (a) 3–5
buyer conversations that bite, and (b) the registered kill harness below
surviving. Provenance: registrar triage 2026-07-17
(research/idea-triage-2026-07-17.md), ranked #1 of the four candidates —
the only one that is a wedge (buyer holding money) rather than a demo.

---

## 1. Why this one

- **All three snhp pillars, on shipped surface.** Sponsorships are textbook
  multi-issue bundles (rate, deliverables, usage rights, exclusivity,
  whitelisting, payment terms, timeline) — isomorphic to `bundle.py`'s own
  SaaS example. The creator's mandate is set by offered choices (elicitation,
  exactly what the WTP-null licenses). The receipt has a real principal-agent
  job on BOTH sides of the trust boundary.
- **A buyer holding money.** Talent managers charge 10–20% for exactly this
  labor (triage + countering inbound deal flow). Creator platforms
  (#paid, Grin, CreatorIQ, Passionfroot) and brand-side media procurement are
  adjacent buyers. A brand negotiating many creators IS procurement of media
  — the same buyer species as the notary GTM, one door down.
- **The pain is repeated and asymmetric.** Mid-tier creators get constant
  inbound; most accept-as-offered or ghost. The counterparty (brand agency)
  negotiates daily; the creator negotiates monthly. Asymmetric-skill bilateral
  bargaining with real dollars is snhp's home game.

## 2. Mechanism sanity check (ran 2026-07-17, shipped engine, zero new code)

A real-shaped inbound lowball ($3,000 · 2 videos · perpetual rights · 90-day
category exclusivity · net-60 · 1-week rush) through `negotiate_bundle` with
a creator mandate (dollar utilities per issue + priorities):

```
action: counter
counter: rate $6,500 · 1 video + 2 stories · 90d paid usage ·
         30d exclusivity · net-60 · 1 week
trade logic: "Give ground on 'payment' (you weight it less, they weight it
  most) to hold firm on 'rate' (your top priority). That trade is what makes
  the package beat splitting every issue down the middle."
acceptance probability: 0.69
```

The engine holds the top-priority issue, concedes the cheap ones, and trades
the poison pills (perpetual rights, 90-day exclusivity) down to bounded
versions — a coherent agency-grade counter from one function call.
Reproduce: the snippet lives in this spec's git history / session log.

**A distinction to keep crisp:** `negotiate_bundle`'s particle-filter
inference about the BRAND from its offers is legitimate opponent modeling in
an adversarial agent (and near-inert after one offer — priorities inferred
nearly uniform; the counter is driven by the creator's own mandate). The
WTP-null constraint applies to the CREATOR side: the mandate must come from
offered-choice elicitation, never from passively "learning" the creator.
Two different sides of the wall; never conflate them in copy.

## 3. The product (creator side first)

1. **Ingestion.** Inbound deal (email/DM/brief) → parsed into the issue
   schema (LLM extraction, human-confirmable). Net-new plumbing.
2. **The mandate interview** — the star, same DNA as the divorce demo's Act
   II. ~8 offered choices set the creator's utility table and walk-away:
   "Would you take $4k with 90-day exclusivity, or $3k with none?" · "Is
   perpetual usage ever on the table? At what price does it start?" · "Below
   what all-in number do we decline without waking you?" Self-selection on
   concrete alternatives; posterior machinery = `buyer/preflearn.py` adapted
   (the divorce build already proved the adaptation pattern and its pitfalls
   — dollar-scaled taus, median point estimates, ratification-style
   confirmation of the compiled mandate: "here's your mandate as I understand
   it — sign it").
3. **The sealed mandate.** Compiled utility table + walk-away + hard bounds
   (never-accept terms), hashed (`disclosure_digest` DNA). The agent
   negotiates FROM the mandate; the creator's raw numbers are never in any
   outbound message.
4. **Auto-pipeline.** Triage (score vs mandate: decline / auto-counter /
   escalate-to-human) → mandate-bounded countering (`negotiate_bundle`,
   alternating offers) → close or walk. Honest split from the triage: the
   triage layer is portfolio scoring, not negotiation — don't market it as
   the mechanism.
5. **The receipt (`snhp-notary/mandate-1`, sibling protocol on notary DNA).**
   What it can honestly attest, and nothing more:
   - to the CREATOR: every counter/accept/decline was the mandate-optimal
     action within the sealed mandate's bounds — verify by replay (same
     digest + engine version ⇒ same actions). "Your agent didn't freelance."
   - to the BRAND: the counters derived from a mandate sealed BEFORE your
     offer arrived (commitment) — not invented after reading your number.
     "The hardball isn't caprice; the walk-away is real."
   - NEVER attested: that the mandate reflects the creator's true feelings,
     or that the outcome is fair. Same §6-divorce discipline: exactly this,
     and nothing more.
6. **Brand side (phase 2, the procurement bridge).** The same engine run for
   a brand negotiating N creators, with the non-collusion notary posture:
   provably independent per-creator negotiations (no cross-creator price
   coordination) — the surveillance-pricing tailwind applies. This is the
   door to the notary GTM's buyer.

## 4. The registered harness (freeze BEFORE build; run before any claim)

**Population:** N = 100 synthetic deals: brand archetypes (agency-lowball,
fair-market, rush-job, rights-grab) × creator tiers (nano/mid/large, distinct
rate cards) × deal sizes. Brand = **utility-rule agent** (budget, target CPM,
walk-away = next-best creator + switching cost), acceptance by rule + seeded
noise. **The trap-check result transfers verbatim: the brand arm must be
LLM-free** — divorce/trap_check.py caught Haiku accepting an offer its own
reasoning computed as bad; a cooperative-LLM brand would fake lift.

**Arms:**
- A0 — accept-as-offered (what most creators do).
- A1 — flat rule-based counter: +25% rate, decline exclusivity, cap usage at
  90d ("the email template"). **The load-bearing control** — anchoring means
  *asking beats not asking*, so lift must be measured against asking naively,
  not against passivity.
- A2 — raw-LLM full-disclosure negotiation (ARM-D analogue; honors
  raw-logroller-at-ceiling: we never claim the engine finds deals LLMs
  can't — the edge is mandate-boundedness + privacy + receipt).
- A3 — Mandate: elicited mandate → engine countering.

**Pre-registered bidirectional kills:**
- **K-down (product is an email template):** if A3's median creator-surplus
  lift over A1 < 15% of A1→oracle headroom → the engine adds nothing a
  template doesn't; do not build.
- **K-up (the engine costs creators money):** if A3's deal-death rate (brand
  walks on deals with positive true joint surplus) exceeds A1's by > 5pp →
  the hardball destroys value; do not build.
- **K-mandate (elicitation sufficiency, K3 analogue):** if A3 with the
  ~8-question mandate recovers < 80% of A3-with-oracle-mandate surplus →
  the interview is chrome; fix or do not claim it.
- Thresholds are proposals; freeze after a 20-deal pilot, before build.

**Confounds, named:** anchoring (killed by A1); cooperative-brand goodwill
(killed by the utility rule + a 20-deal LLM-fronted trap replication, same
protocol as divorce); synthetic-brand realism (report the population's
parameters; validate against 3–5 real deal sheets from buyer conversations
before quoting any number publicly).

## 5. What exists vs what must be built

| Piece | Status |
|---|---|
| Multi-issue countering | ✅ `negotiate_bundle` (sanity-checked above) |
| Mandate elicitation | Adapter on `buyer/preflearn.py` — pattern + pitfalls already solved in divorce/elicit.py |
| Receipt | Net-new `mandate-1` sibling protocol on core/notary.py DNA (~250 lines; divorce's `settlement-1` is the template) |
| Deal ingestion (email/DM → issue schema) | Net-new; LLM extraction + human confirm — the real product-eng surface |
| Brand-arm harness + kills | Net-new (~500 lines, divorce kill-harness shape) |
| Triage/portfolio layer | Net-new, deliberately thin in v1 (score vs mandate, three buckets) |

Estimated harness cost: 2–3 days. Product v1 (single creator, email-in,
dashboard-out): ~2 weeks after harness survives. **Neither is authorized
until the conversations bite.**

## 6. Buyer conversations (the actual next step — roadmap discipline)

**Who (3–5 of):** two talent managers (mid-tier rosters, 10–50 creators),
one creator-platform PM (Passionfroot/#paid-type), one brand-side influencer
media buyer, one high-inbound solo creator.

**The outreach note (founder voice, ≤120 words):**
> You manage inbound sponsorship offers for creators. I build negotiation
> infrastructure — an agent that triages inbound deals and counters them to
> better terms, provably bounded by a mandate the creator sets in a
> 3-minute interview. The counter is math (which issue to hold, which to
> trade), and every action comes with a receipt proving the agent stayed
> inside the mandate — no freelancing, no leaked numbers. Before I build
> more of it, I'm trying to disprove that anyone would pay for this. 20
> minutes to tell me why your job is harder than my model of it?

**Discovery questions (the 10):**
1. Walk me through the last inbound deal you countered — issues, rounds, time.
2. What % of inbound gets accepted as-offered / countered / ghosted?
3. What does a counter template look like today? Who wrote it?
4. Which term actually kills deals — rate, exclusivity, or usage rights?
5. What's the fee for this labor today (agency %, retainer, in-house time)?
6. If an agent countered automatically, what's the disaster scenario?
7. Would a "provably stayed inside the mandate" receipt change whether you'd
   delegate? What would you need to see on it?
8. Brand side: would "our creator negotiations are provably independent"
   matter to your legal/compliance people? (the notary bridge question)
9. What volume makes automation worth onboarding pain — 5 deals/mo? 50?
10. Who else should I talk to? (the pipeline question)

**What "bites" means (pre-committed):** ≥2 of 5 can name a current fee they'd
redirect, OR ≥1 offers a paid pilot on real deal flow. Otherwise the wedge
goes back on the shelf with the notes attached — a clean kill.

## 7. Founder calls

1. Green-light the outreach (the note above, founder-sent) — this is the
   50%-hours-to-pipeline lane, not research.
2. Name check: "Mandate" (collides with generic usage; alternatives:
   Counteroffer, Sealed, Rider).
3. Whether the brand/procurement side (§3.6) appears in the first
   conversations or stays hidden until the creator side validates.
4. Threshold freeze for §4 after the pilot, if and when build is authorized.
