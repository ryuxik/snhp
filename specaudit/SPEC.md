# SPECAUDIT — the 2026 agent-commerce stack, examined as a deal substrate

*Registered 2026-07-16, BEFORE any spec is read for mapping. Public,
real-name audit of the published agent-commerce specifications (AP2 —
agent payments/mandates; ACP — agentic checkout), succeeding the MERIDIAN
demo whose evidential value was correctly discounted as self-authored.
This audit's patient is someone else's public design; its credibility
mechanism is a contestable mapping. DRAFT-FOR-COMMENT ONLY until founder
review — nothing publishes from this work without an explicit founder
decision.*

## Fairness protocol (binding)

1. Mapping built ONLY from public, versioned spec documents; every mapping
   row cites the exact section/quote and records the spec version+date.
2. No security-vulnerability claims or language. This is mechanism
   economics: what deal shapes the spec can EXPRESS, what it DELEGATES,
   and what happens in the delegated space by default.
3. Credit what the specs get right with the same rigor as what they omit
   (e.g., AP2 mandates/verifiable credentials are a genuine
   receipt-primitive — say so plainly if the mapping supports it).
4. The mapping table is published for the specs' own engineers to
   contest; corrections will be published with the same prominence.
5. Structural findings stated with certainty (schema-level properties);
   magnitudes ONLY as sensitivity bands over declared utility families —
   never point estimates from invented utilities.
6. "What we did not find" section mandatory.

## Battery (adapted from MERIDIAN; pre-stated)

- **S1 — Expressible deal space (structural):** from each spec's message
  schemas: can an offer/counteroffer carry multi-issue terms (price ×
  quantity × delivery/timing × conditions)? Is there ANY counteroffer
  surface at all? Deliverable: the contract-space table with citations.
- **S2 — Settlement & recourse (structural):** payment-vs-delivery
  ordering, clawback/dispute surface, what a deceptive counterparty's
  exposure window is under each spec's own flows.
- **S3 — Attestation surface (structural, credit due):** what is signed,
  by whom, covering what; where the receipt chain breaks (who can fake
  what).
- **S4 — Chain/delegation flows (structural):** multi-agent flows
  (user→agent→merchant-agent→processor): where pre-commitment exists and
  where hold-up surfaces are inherited.
- **S5 — Default-gap simulation (magnitude, banded):** a faithful minimal
  implementation of each spec's flow, embedded in the MERIDIAN market
  harness; the MPX battery re-run on what the spec leaves unspecified,
  reported as sensitivity bands across the declared utility family — the
  measured cost of the gap the stack delegates to implementers.
- **S6 — The fix demo:** the same flows with a bundled-negotiation layer
  (snhp engine) + receipt gating added WHERE THE SPEC ALREADY HAS
  EXTENSION POINTS, deltas reported as bands.

## Deliverable

`specaudit/report.md` (draft-for-comment watermark): exec summary, the
cited mapping tables, S1–S6 findings, corrections policy, regeneration
command. Doubles as: the public sample audit (real patient), the
ROADMAP Phase-2 standards-ecosystem artifact, and the evidence layer the
Thiel memo currently lacks.
