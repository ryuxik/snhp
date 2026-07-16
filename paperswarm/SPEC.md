# PAPERSWARM — a paper-traded agent-swarm trading desk on real market data

*Registered 2026-07-16, BEFORE implementation. Founder mandate: build the
paper-traded swarm demo on a domain that "resolves as fast for real as in
a sim," with real money on the table if the experiment clears its gate.
Design: Fable. Build: Opus agents. Discipline: identical to the swarm
benchmark — pre-registered predictions, kill conditions, signed receipts,
no number published that doesn't regenerate from the ledger.*

## Venue and why

**Graded trading cards on eBay (launch niche: PSA-graded Pokémon; niche is
a config, not an architecture).** Chosen against the registered checklist:
KNOWN FIELD (listings are indexable — bargaining's home turf per v11);
MEETING DENSITY (thousands of daily clearing events); FAST RESOLUTION
(auctions end on a clock; sold comps observable in hours-days); PERFECT
IDENTITY (PSA cert numbers — no fuzzy matching); ATTESTABLE (every fill
has a public counterfactual). Classic sponsorship deals fail the
fast-resolution test (weeks); sponsorship remains the phase-3 vertical
once the engine is proven.

## The honesty protocol (the whole point)

Paper P&L is notorious self-deception. Every fill and mark follows rules
committed HERE, before any data is seen:
- **BUY (auctions only, the provably-honest fill):** the agent must commit
  a max bid ≥60s before auction close (timestamped, hash-chained, signed
  once the notary lands). If realized hammer < our max bid, we won at
  hammer + one increment. If hammer ≥ max bid, we lost. No BIN paper-buys
  in phase 1 (BIN fills need a race-winner assumption — optimistic bias).
- **SELL (mark-to-realized, never to ask):** inventory marks at the 25th
  percentile of REALIZED sold prices for the same cert-grade/card within
  the trailing 14 days, minus full friction (13.25% fees + $5 shipping +
  3% payment), with an unsold-risk haircut from the observed sell-through
  rate. If fewer than 5 comps exist, the position marks at ZERO until
  comps exist (no thin-comp fantasy marks).
- **Budget realism:** fixed paper bankroll ($2,000), one concurrent bid
  per listing, capital locked from bid commit to resolution, API/LLM costs
  metered and charged against P&L (energy is not free — the sim said so).
- **Every event is a receipt:** bid commits, fills, marks, internal deals —
  hash-chained ledger from day one, upgraded to notary-signed (core/notary
  N1) when it ships. The dashboard shows NOTHING that is not derivable
  from the receipt chain.

## The swarm (the sim made real)

- **Scout agents** (per-niche searchers): find candidate listings, produce
  LEADS (listing + identity + close time).
- **Pricer agent(s):** comp-model fair value from our own observed-sold
  database; decide max bids.
- **Treasury/risk:** allocates bankroll; enforces exposure caps.
- **The internal market (the experiment):** scouts SELL leads to pricers
  through the snhp bundling engine (lead + exclusivity window + a share of
  realized margin — a genuine multi-issue bundle); niche CLAIMS are traded
  (no two scouts cover one niche); budget allocations are the energy
  market. Internal deals settle in paper-P&L share and are receipted.
- **LLM usage:** parsing/identity extraction only (haiku-class); pricing is
  deterministic from comps (auditable). No LLM "vibes" prices.

## Arms (the registered comparison — the sim ladder, on real data)

- **A (monolith):** one agent, same comp model, same bankroll — the "is a
  swarm even useful" control.
- **B (swarm, fixed assignment):** scouts+pricer+treasury, niches assigned
  by fiat, no internal trading.
- **C (swarm + internal market):** B plus lead-sales, claim trades, budget
  bargaining via the snhp engine.
All three run the SAME window on the same feed (paper fills don't collide —
counterfactuals are non-rival; flag any same-listing overlap in reporting).

## Pre-registered predictions & gates (P-PS)

- **P-PS1 (viability):** over a 30-day window, arm C's paper ROI net of
  ALL friction and metered compute is positive and ≥ $150 absolute on the
  $2k bankroll (≥7.5%/mo). Below that, the edge doesn't clear real-world
  noise.
- **P-PS2 (the swarm question):** C > A on risk-adjusted paper P&L (the
  internal market must EARN its complexity). If A ≥ C, publish that —
  "one good agent beats a bureaucracy of them" is a headline we accept.
- **P-PS3 (fill-model audit):** at month end, a random 10% of "won"
  paper-auctions are audited against full bid histories where visible;
  systematic optimism in the fill model → all results voided, protocol
  revised, window re-run.
- **GO-REAL GATE:** P-PS1 AND P-PS2 held for two consecutive 30-day
  windows AND the founder approves a real bankroll (size = founder's call,
  suggested $500–1,000 pilot). Real trading is a FOUNDER decision at the
  gate — never automatic. (Roadmap note: paper mode is a demo/marketing
  asset under R4; flipping real makes it a vertical — that decision
  belongs to the Phase-2-exit review.)
- **KILL:** two consecutive negative windows, or a failed fill audit twice
  → the desk shuts, the post-mortem publishes, the receipts stay up.

## Phase plan

- **Phase 1 (this build):** eBay data layer (Browse API poller for the
  niche + our OWN outcome tracker building the sold-comp DB — no
  restricted APIs), hash-chained ledger, paper-fill engine per protocol,
  ONE scout + pricer + treasury (arm B skeleton), CLI status report.
  Collect ≥7 days of comps before any bid commits (cold-start rule).
- **Phase 2:** arms A and C (internal market via snhp engine), dashboard
  page on arena.snhp.dev (receipt-backed), notary signing when N1 lands.
- **Phase 3 (post-gate):** founder go/no-go on real capital; sponsorship
  vertical revisited.

## Protocol amendments (post-build, approved by registrar)

- **Win price capped at committed max** (2026-07-16, builder-flagged): the
  literal "hammer + one increment" can exceed the committed max bid; the
  implementation caps win_price = min(max_bid, hammer + increment),
  matching real eBay proxy-bid semantics. Approved — the cap is more
  conservative and more realistic, never less honest.
- **Real-mode outcome observability**: the public Browse API exposes no
  clean post-close hammer; the tracker records SOLD-at-final-price when
  bidCount>0, UNSOLD otherwise, and UNKNOWN rather than inventing a
  price. UNKNOWN listings never become comps or fills. Approved.
