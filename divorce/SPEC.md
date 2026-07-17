# IRRECONCILABLE AGENTS — spec v2

**Subtitle (under the logo):** *The divorce is fake. The math is real.*

**One-liner:** Build two people who can't stand each other. Watch their lawyers fail, item by item. Then watch a bored clerk ask nine questions, bundle the whole pile, and hand the judge a receipt stamped NOBODY PEEKED.

**Pillars (fixed):** humor · clarity · playfulness · competitiveness · **nothing on screen is scripted** — the deadlock, the elicitation, and the settlement all come from the real engine, and the demo can visibly fail (NO DECREE is a designed outcome, not an error screen).

**Provenance:** v1 (founder, Jul 17 2026 creative panel) → conceptual-artist punch-up pass + CTO feasibility/science pass (Jul 17 2026) → this synthesis. CTO code claims spot-verified against the repo.

---

## 0. Rulings — what changed from v1 and why

| v1 element | Ruling | Why |
|---|---|---|
| Poker Face slider + bluff subsystem | **CUT from demo; kept as registered harness experiment K4** | Artist: a second unverified demo inside the first; scorecard forces showing private numbers mid-run, detonating "nobody peeked." CTO: most science-exposed beat — intensity-lies under Nash selection can genuinely pay. Revive with The Peacemaker archetype in v2 only if K4 says lying loses. |
| Poker Face's slot | **Replaced by Spite** | Weight λ on the ex's loss (u = own − λ·ex_gain). A real utility term, and it *generates* the pettiness tax honestly. |
| Leverage meter | **CUT** | Both seats independently: no engine quantity exists mid-elicitation that it would honestly render. The one element v1 would have had to fake. |
| Elicitation before deadlock | **REORDERED: deadlock first** | Item-by-item bargaining needs no interview (each side knows its own values) — only the bundle-builder must ask. Failure first makes the causality legible: lawyers fight over items; the clerk asks questions; questions build the bundle; the bundle clears. |
| Free-text "describe your ex" (open q. 1) | **RESOLVED: archetype cards + one player-named noun on a fixed slot** | LLM-compiled utilities are unverifiable and un-registerable (the demo-discipline circularity), and invite real-grievance moderation incidents. The named wildcard item ("his mother's painting") is a *label* on a mechanically fixed slot — comedy from the noun, mechanics from the registration. |
| Headline number (open q. 2) | **RESOLVED: pettiness tax is the headline; surplus split is the scoreboard; never equal weight** | A dollar amount set on fire over a named domestic object beats a percentage. Tax is a real counterfactual re-run, not a vibe. When tax = $0, time-to-settle is the number. |
| 8 assets, random wildcard, air miles, custody calendar | **6 assets; wildcard player-named on fixed slot; miles cut; custody ternary** | Every asset must be a character; and the outcome-space cap is hard: `_MAX_OUTCOMES = 4000` (gametheory/negotiation/bundle.py:44). |
| Hotseat + two-device 2P | **v1 ships solo-vs-house; QR two-device is v1.1; hotseat dead forever** | Hotseat leaks the secret hill. 2P adds session infra + abuse surface with zero evidentiary value; the run API takes two persona configs, so 2P bolts on later without rearchitecting. |
| "Envy-free" on the receipt | **Demoted to a reported per-episode check; never a mechanism claim** | No EF code exists in the repo and the Nash point over a discrete frontier doesn't guarantee it. A cash-equalization post-pass buys EF per-episode honestly; the receipt reports YES/NO under each side's own elicited valuations. |
| §8 kill "opposed personas must deadlock" | **Rewritten as registered K1–K4 + trap check, thresholds frozen before chrome** | v1 registered on inputs and vibes — the exact failure mode of the article-3 draft. |
| Build on "core/ engine (offer_graph)" | **CORRECTED: gametheory/negotiation + snhp/nash_solver + core/notary** | core/engine.quote() is buyer-vs-shop over price rungs; OfferGraph options carry shop semantics (price_delta, unit_cost, salvage). The divorce's home game is `filter_pareto_frontier` / Nash selection / `joint_frontier`. Notary half of v1 was right. |
| Presets: The Amicable | **CUT** | Nobody has ever watched an amicable divorce on purpose. |
| Names | **Irreconcilable Agents** | "Splitsville" is a 2025 feature film — SEO roadkill. "Custody of the Dog" survives as the flagship preset's episode title. |

**New in v2 (not in v1):** the Showdown Flip (§6), the county-clerk mediator (§4), the full-disclosure third arm ARM-D (§8), the NO DECREE card (§7), the rematch loop (§7), same-origin/CORS serving decision (§9).

---

## 1. The Persona Builder — "Build Your Ex"

Archetype cards are slider presets made visible: pick a card, nudge the sliders, the system teaches itself. **Five archetypes:**

1. **The Spreadsheet** — "Everything at market price. Including the dog." The control arm in a costume.
2. **The Sentimental Hoarder** — "The concert stub is priceless. The crypto is whatever." Value concentrated in low-dollar memory items.
3. **Scorched Earth** — "Would rather burn it than split it." High λ spite term.
4. **The Already-Healed** — "Wants nothing. Which is a problem, because wanting nothing is leverage." Low valuations, high walk-away: indifference as BATNA.
5. **The Ledger** — "Every item is priced in grievances. The Vespa is worth one missed anniversary." Pettiness distributed across many items; infinite patience. (Sentiment vs. justice distinguishes it from the Hoarder.)

Cut from v1: The Grinder (it's the Patience slider at max, not a person) and The Peacemaker-Who-Secretly-Wants-It-All (it's the bluff mechanic in a trench coat; dies with it, revives with it).

**Three sliders** (human label, math on hover): **Pettiness** — value multiplier on low-dollar symbolic items · **Spite** — λ weight on the ex's loss · **Patience** — walk-away threshold. Each archetype is a preset over these plus a valuation shape.

**The hill I'll die on:** pick ONE asset this persona irrationally overvalues — and it is **SECRET**. The opponent (and audience) learns it only when the elicitation heat-map spikes red mid-interview: *hill detected in four questions*. That beat is elicitation-as-star made visceral and only exists if the hill is hidden. Both players picking the same hill is not prevented — that collision is the jackpot ("Both of you? The espresso machine?").

**The named item:** the player types one noun into the marital estate — "the Le Creuset," "his mother's painting," "the karaoke machine." It fills a mechanically fixed wildcard slot (fixed valuation parameters, registered); the name is chrome. Name passes a moderation filter.

**Compilation:** each persona compiles server-side to a hidden dollar-valuation table over the assets + walk-away (litigation BATNA: fight cost + expected court split) + λ. Neither side, nor the audience, sees the other's numbers — see §6 for how that secrecy becomes checkable rather than asserted.

## 2. The Asset Table

Six assets, every one a character, and the arithmetic fits the engine's hard cap:

| Asset | Type | Options |
|---|---|---|
| The dog 🐕 | custody | hers / his / alternating (3) |
| The lake-house weeks | divisible | 5-point split grid |
| The joint crypto wallet | continuous (money) | 11-point split grid — also the cash-equalization dimension |
| The vinyl collection | indivisible | 2 |
| The espresso machine | indivisible, petty-magnet | 2 |
| The named wildcard | indivisible, fixed slot, player-named | 2 |

Outcome space: 3 × 5 × 11 × 2³ = **1,320** < 4,000 (`_MAX_OUTCOMES`, bundle.py:44). Do not add assets without redoing this arithmetic; the Pareto filter is O(n²).

## 3. Structure — the beat sheet

Three claims, three beats: **elicitation is the laugh** (personas answering in character), **the bundle clearing is the gasp** (the *second* signature is the miracle), **the receipt is the click** (nobody peeked — and here's proof). Tension lives in the deadlock's *specificity*, not its length: two items settling instantly while the dog absorbs 27 fruitless exchanges is funny; six items all stalling is static.

**90-second spectator cut:**
- **0:00–0:08 — Cold open.** Two portraits slam in, versus-card style. Corner stamp: *valuations sealed · #a3f9c2* (the Showdown Flip begins here, §6).
- **0:08–0:22 — Act I: "Your lawyers' way."** Item-by-item montage at ~10 exchanges/sec, counter blurring. Playback speed is chrome; **every number is the real ARM-I trace** — if the trace says 3 assets settled, the counter says 3. Freeze on: **THE DOG — 27 exchanges, 0 progress.**
- **0:22–0:26 — The turn.** The mediator appears. One line: "I have some questions."
- **0:26–0:50 — Act II: The interview.** Alternating would-you-rathers, 3–4 per side. Each answer visibly narrows a confidence band — the only instrument on screen. Mid-beat: one band spikes red. *Hill detected.*
- **0:50–1:05 — Act III: The offer.** One all-or-nothing bundle assembles onto a single tray. Two sealed walk-away markers sit face-down. Both agents sign; the gasp is the second signature.
- **1:05–1:20 — The decree.** Thermal-printer sound (the one sound effect this demo needs). Decree scrolls, stamp thunks: **NOBODY PEEKED**. Face-down cards flip, the hash verifies on screen, the pettiness tax burns onto the card.
- **1:20–1:30 — Share card** + stinger button: "The Two Spreadsheets — watch two rational people divorce in 3 seconds."

**Solo session (~5 min):** Build Your Ex (card, three sliders, secret hill, name the wildcard) → sealing ceremony (both utility functions hash on screen — ten seconds of ritual) → the 90-second run → verdict card (surplus split, pettiness tax each, hill autopsy: "Your hill: the espresso machine. It cost you $1,900. It retails for $340.") → **rematch loop**: one button, "Pay less tax," re-runs the same divorce with pettiness dialed down 20%. A real re-run, a real delta — the engine already computes the counterfactual. **v1.1 (QR two-device):** same flow, personas built in parallel on phones, each phone shows only its own ledger.

**The mediator is cast: a county clerk of the heart.** Bored, procedural, has processed ten thousand of these. "Question 4 of 9. The dog, or July." "Noted." "That contradicts question 2." Every deadpan line is a **template bound to a real engine event** (band narrowed, contradiction detected, hill found, IR cleared) — comedy is mechanics with a voice, never writing. The flatness IS the science: this is what "a skeptic who trusts neither" sounds like. Cost: ~20 templated strings. Persona dialogue may additionally be LLM-voiced server-side (Haiku); the numeric episode is identical with voicing off.

## 4. Elicitation — the star, the honest version

Carrier: the `PosteriorLearner` machinery in buyer/preflearn.py — pairwise would-you-rather updates (`update_pairwise` :198), yes/no probes (`update_probe` :156), info-gain query selection (`_best_query` :376), bands from posterior quantiles (`quantile` :138). Adapted from vend SKUs to per-asset dollar values with an archetype-population prior (~250 lines).

**Three non-negotiables** (these keep the demo on the right side of the WTP-null — elicitation is self-selection, not inference):

1. Every narrowing step on screen is **caused by a displayed question and its answer** ("dog, or lake-house July?"; "the espresso machine, or $300 more of the wallet?"). Never an ambient heat-map sharpening while agents merely talk.
2. The settlement is computed **from the elicited posteriors only**. If the decree secretly used oracle utilities, "nobody peeked" is a lie and the receipt is theater. Enforced structurally, `test_no_ground_truth_leak` pattern (buyer/tests/test_preflearn.py:50).
3. The mediator does **not** use `negotiate_bundle`'s particle-filter inference-from-offers path (bundle.py:186–204) — that is inferring hidden values from observed behavior, the killed mechanism wearing the shipped engine's clothes. The mediator holds the two elicited posteriors and calls the frontier directly.

Copy-writing rule everywhere: *"every answer is a choice; the mediator knows only what your choices imply"* — never "the AI figures out what they really want."

Elicitation must also be *shown* to be load-bearing, not decorative chrome over an oracle: kill condition K3 (§8) registers a sufficiency threshold at the watchable budget (~6–10 questions/side).

## 5. Settlement

*(Updated after the kill-harness build — divorce/RESULTS.md records why each
piece exists; the first mediator design shipped 77% refused decrees.)*

Mediator holds both elicited posteriors → scores every bundle by each side's
**IR margin on the elicited scale** — `(1+λ)·Σ(share−0.5)·v̂ + fight_cost`,
from posterior **medians** and the persona's **structured declarations** (λ,
fight cost; never a raw walk-away number, which mixes true and estimated
scales) → restricts to bundles whose **pessimistic** margins clear (receive
at q25, concede at q75) → `filter_pareto_frontier` + Nash selection
(snhp/nash_solver.py) → **cash-equalization post-pass** on the wallet (closed
form) → **ratification**: the draft goes to each side as a direct yes/no
("better than court for you? don't tell me why"). A refusal updates the
refuser's posterior (it is a linear inequality on their values) and excludes
that allocation at that-or-worse compensation; ≤ 6 drafts, then the mediator
**abstains** → NO DECREE. Ratification is still self-selection — the most
decision-relevant choice there is — and it is the demo's best procedural beat
("Draft #2. Refused. Noted."). Implemented: divorce/elicit.py.

## 6. The Receipt + the Showdown Flip

**The Showdown Flip — the honesty pillar made diegetic.** At second zero, both compiled utility tables are hashed (`canon_hash`, core/notary.py:92) and the hash is stamped in the corner: *valuations sealed · #a3f9c2*. Throughout the run, every private number — valuations, walk-away lines — renders as **face-down cards**: the audience knows they exist and cannot see them. At settlement, the cards flip like a poker showdown and the hash verifies against the flipped numbers, on screen, checkably. This is a commitment scheme — the actual notary doing its actual job as theater — and it converts "trust us, it's real" into the demo's best visual beat. The audience becomes the judge. It also resolves the walk-away-line leak (drawing labeled walk-away lines mid-run would have peeked on the audience's behalf) and proves the personas weren't retro-fitted to flatter the outcome.

**What the receipt attests (exactly this, and nothing more — the notary.py:9 standard):**
1. The settlement is the joint-max/Nash point **within the elicited bounds** — replayable: same two disclosure digests + engine version ⇒ same settlement (`context_hash` discipline).
2. IR: both sides clear their stated walk-away under their own elicited valuations.
3. The mediator's inputs were exactly two one-way disclosure digests (`disclosure_digest`, notary.py:98) — neither side's numbers appear in, or are recoverable from, the receipt.
4. Envy-free under each side's own elicited valuations: **YES/NO** — a reported per-episode check, never a mechanism guarantee.

Receipt fine-print sentence (verbatim): *"Settlement is the joint-max within both parties' elicited bounds; both sides clear their stated walk-away; envy-free under each side's own elicited valuations: YES; computed from two one-way disclosure digests — verify by replay; snhp engine vX, key fpr …"*

Implementation: a sibling `snhp-notary/settlement-1` protocol module reusing the Ed25519 key, canonical hashing, and the `verify_receipt`/`verify_chain` pattern (~250 lines + route). The existing quote-receipt and ledger-receipt shapes both hard-require shop semantics — do not stretch them.

**The stamp is the brand atom:** wax-red, rotated eight degrees, **NOBODY PEEKED — verified · snhp**, with the fine print beneath. "Nobody peeked" is defined on the card as what it is: a replayability + information-partition property — *computed from two one-way digests only; verify by replay.* Protect the two words: they work as a stamp, a t-shirt, and a physical stamper at a booth.

## 7. Scorecards & shareables

**Headline: the pettiness tax.** Operationally real and stated so on the card: the engine re-runs the settlement with your hill valued at market and reports the joint surplus you forfeited. A counterfactual, not a vibe. **Scoreboard: surplus split** — decides who won, drives the rematch. Never both in one sentence; the delicious outcome class is winning both: took the surplus, still led the league in arson. When tax = $0, time-to-settle is the headline ("settled in 3.1 seconds").

**The one image: the Decree.** Portrait 4:5, cream paper, scan texture. Letterspaced small-caps header — **FINAL DECREE · IN RE: THE MARRIAGE OF D. & M.** Quiet serif ledger lines (*THE DOG — Tue/Thu, alternating birthdays. THE LAKE HOUSE — July: hers. August: his.*). Ruled divider, then the number at 4× body: **PETTINESS TAX: $2,400** *(the espresso machine, retail $340)*. Bottom third: the NOBODY PEEKED stamp overlapping the ledger like it was slammed down by someone who does this all day; one tiny monospace line: `engine v2.1 · #a3f9c2 · both parties above walk-away`. One illustrated element: a small courtroom-etching dog, seated, dignified. Palette: cream, ink, one red. Must survive thumbnail size, where only the red stamp and the red number read — that's correct.

**Card copy targets** (tone; every number on a real card comes from the run):

> **DECREE #4471 — settled, barely.** He kept: the dog, the vinyl, August. She kept: the lake house, the wallet, July. **PETTINESS TAX: $2,400** — his, dying on Espresso Machine Hill (retail: $340). Both above walk-away. Nobody peeked.

> **DECREE #4473 — settled in 3.1 seconds.** Everything at market price. Custody optimized. **PETTINESS TAX: $0.00.** Nothing set on fire. Was it ever love? Nobody peeked. Nobody needed to.

> **NO DECREE.** 6 assets. 214 exchanges. 9 questions. No overlap exists. **PETTINESS TAX: everything.** Some marriages even math can't save. Nobody peeked.

The NO DECREE card is a **designed outcome** — unscripted means it will happen live, and a demo that visibly can fail is a demo people believe. The kill harness reports no-deal frequency (§8); do not quietly narrow the persona space to make deadlocks stop happening.

**Presets:** "The Bloodbath" (demo opener) · "Custody of the Dog" (flagship episode) · "The Two Spreadsheets" (post-credits stinger — engine speed as deadpan). The Amicable is cut.

## 8. Pre-registered kill (frozen BEFORE chrome)

Registered in CO2-S style. **Population:** N = 100 persona pairs, seeds 1–100, stratified over the 5-archetype grid × slider levels × hill assignments, fixed asset table, published before the harness runs. Utilities in dollars; walk-away = litigation BATNA.

**"Genuinely opposed hidden utilities," operationally** (the boba-$0 confound killer):
1. *Information partition is structural, not prompted*: true tables in separate harness objects; mediator receives only query answers; each persona prompt contains only its own table and transcript. Enforced by leak tests + a prompt-content assertion (the other side's numbers, as strings, never appear in any prompt or mediator input).
2. *Opposition is measured, not asserted*: a pair qualifies only if ≥ 2 indivisible assets are contested (both sides value it ≥ 20% of their own total bundle valuation); compiler resamples until met; contestedness distribution reported.
3. *Accept/reject is a utility rule, not LLM goodwill*: acceptance iff true-utility surplus ≥ IR threshold (+ seeded noise). LLMs voice dialogue only; they never decide acceptance. **The kill harness runs LLM-free.**

**Arms** (same personas, same elicitation transcript where applicable, same round budget R = 40):
- **ARM-I** — item-by-item sequential, **cash equalization allowed per item** (forbidding side payments item-by-item while allowing them in the bundle would be a strawman; the dog deadlock must *emerge* from value exceeding any feasible fragmented cash offer, not be forced by protocol asymmetry).
- **ARM-B** — mediated bundle (elicited posteriors → frontier → selection → cash post-pass).
- **ARM-O** — oracle bundle (true utilities → frontier). Measurement only; never shown as product.
- **ARM-D** — direct LLM-vs-LLM bundle negotiation with full mutual disclosure, no mediator. Expected: they find a similar bundle — *but only by showing each other their numbers, with nothing a judge can verify afterward.* This arm turns the raw-logroller-at-ceiling result from a liability into the sharpest honest beat and inoculates against the obvious skeptic's reply. In the demo it appears as a post-decree footnote card, not in the 90-second cut.

**Registered elicitation parameters** (set by pilot, per the tuning allowance
below): Q = **10 questions/side** (Q=8 was marginal on K2/K3), ratification
drafts ≤ **6** (counted into the question total; median total ≈ 22),
declarations = λ + fight cost (stated truthfully in all arms; bluff arm
distorts elicitation answers only, hill intensity ×1.5).

**Kill conditions (bidirectional):**
- **K1 (deadlock is real):** if ARM-I fully settles with both IR satisfied in ≥ (ARM-B's rate − 5pp) of pairs → the two-act structure is fake for this population; do not ship the deadlock act.
- **K2 (bundle actually clears):** if ARM-B violates either side's true-utility IR in > 10% of pairs, or median joint-surplus advantage of ARM-B over ARM-I < 15% → do not ship "the deal you'd both secretly take."
- **K3 (elicitation is load-bearing):** if ARM-B joint surplus < 80% of ARM-O (median) at the demo's query budget (6–10 questions/side) → the star beat fails; raise the budget or do not bill elicitation as the star.
- **K4 (bluff, reportable both directions):** bluff policy ON vs OFF one side, same seeds. If bluffing gains > 10% of the bluffer's surplus → no manipulation-resistance language anywhere in the demo, ever.
- **Trap check:** LLM-fronted replication of ARM-I on 20 pairs; any accepted deal violating the acceptance rule's IR bound = goodwill leak = harness bug; fix before any result counts.

Thresholds (5pp / 10% / 15% / 80% / 10%) may be tuned in a 20-pair pilot, then **frozen before the chrome build starts**. Also reported, not gated: no-deal frequency per arm; the claim "snhp found a deal the agents couldn't" is banned regardless of results — the honest contrast is **protocol (bundling) + privacy + verification**, not intelligence.

**STATUS (Jul 17 2026):** steps 1+2 run — **all four kills survive** on seed 7
(N=100, the tuning population) and on seed 11 (N=100, clean holdout):
ARM-I 11%/4% vs ARM-B 76%/82% full-settle; 0 decrees violating true IR;
bundle advantage 46% of oracle headroom; elicited/oracle 85%/90% at 10
Q/side; bluff gain 0. The 20-pair LLM-fronted **trap check is COMPLETE and
CONFIRMS the confound**: 40/503 decisions (8%) were goodwill leaks — Haiku
accepting offers clearly below the IR bound (median $4.5k below), while
aggregate accept rates matched the rule exactly (16.5% = 16.5%), so only
per-decision grading exposes it. The LLM-free acceptance rule is
load-bearing. Numbers + caveats in divorce/RESULTS.md. Remaining before
results are quotable: founder threshold freeze (§11.1) and the confirmatory
run on a fresh seed.

## 9. Build shape

**Engine substrate:** gametheory/negotiation (`bundle.py`, `frontier.py`) + snhp/nash_solver + buyer/preflearn (adapted) + core/notary. **Not core/engine.quote()** — that is buyer-vs-shop over price rungs; OfferGraph options carry shop semantics. v1's build section named the wrong engine half.

**Shape:** everything real runs server-side on api.snhp.dev (Python owns the posterior, the frontier, the notary key). One **`POST /v1/divorce/run`**: persona params in → full deterministic seeded episode out (elicitation Q&A trace, ARM-I trace, ARM-B settlement, scorecards, signed settlement receipt) → the browser **plays the trace back cinematically**. Preserves nothing-is-scripted (the engine generated every event) with zero session infrastructure; matches the boba-trace precedent but live-generated per user. LLM voicing is an optional server-side pass; persona LLMs never run in the browser. **Serving:** gametheory/server has no CORS middleware (verified) — either add CORS for arena.snhp.dev or serve the page from api.snhp.dev alongside demo.html. No JS port of the posterior machinery (goldens discipline; zero benefit).

**New code:** ✅ `divorce/personas.py` (compiler + measured-opposition sampler) · ✅ `divorce/elicit.py` (preflearn-based interview + margin/ratification mediator + ARM-B) · ✅ `divorce/arms.py` (ARM-I with litigation-credit acceptance and easy-items-first ordering; ARM-O; pettiness-tax counterfactual) · ✅ `divorce/kill_harness.py` (+ `divorce/tests/`) — all built Jul 17 2026, ~1.2k lines. ✅ `divorce/receipt.py` (settlement-1 protocol on notary DNA: seal commitments, one-way input digests, ratification-gated signing, standalone verify — NO DECREE gets no receipt by construction). Remaining: `/v1/divorce/run` route + serving (~150), `arena/web/divorce/` chrome (~1.5–2.5k JS/HTML — the long pole, the viral surface).

**Build order:** (1) ✅ headless kill harness (personas + ARM-I/ARM-O, 100 seeds) — the deadlock→bundle direction is real; (2) ✅ elicitation + ARM-B — K3 clears at 10 Q/side; (3) **freeze thresholds (founder), confirmatory fresh-seed run, LLM trap check**; (4) only then: receipt module, route, chrome. Publish founder-gated as always.

## 10. Cut list (with revival conditions)

- **Bluff subsystem / Poker Face** → revive in v2 with The Peacemaker archetype iff K4 shows lying loses.
- **Leverage meter** → revivable only as a *post-settlement* reveal computed from real BATNAs.
- **Free-text persona compilation** → dead (unverifiable, un-registerable, moderation trap). The named-noun wildcard slot is the surviving spark.
- **Air miles; 7th–8th assets** → dead (outcome-space budget; asset fame).
- **Dog custody calendar** → ternary custody (hers/his/alternating) preserves the joke at a fraction of the outcome budget.
- **Hotseat** → dead forever (leaks the secret hill). **Two-device QR 2P** → v1.1.
- **"The Amicable" preset** → dead.
- **Random sentimental wildcard** → dead (dice rolls aren't comedy); replaced by the player-named fixed slot.

## 11. Design choices still open (none block the build)

1. ~~Threshold freeze~~ — **FROZEN 2026-07-17** (commit = the registration; every threshold had passed with wide margin). "Freeze" means exactly this: the numbers are committed before the chrome exists, so post-launch skeptics can check the hash order — nothing more ceremonial than that.
2. **ARM-D in the shipped demo** — post-decree footnote card (recommended) vs. harness-only.
3. **Serving** — CORS from api.snhp.dev to arena.snhp.dev vs. same-origin hosting of the divorce page on api.snhp.dev.
4. **Name check** — "Irreconcilable Agents" pending a quick trademark/collision look.
