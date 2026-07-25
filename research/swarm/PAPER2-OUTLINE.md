# Paper 2 outline — "Green Dashboard, Robbed Books: Integrity Failures in Mixed-Ownership Robot Fleets"

*Companion to PAPER-DRAFT.md (Paper 1: the benchmark and C1/C2/C3), split per
review/PAPER-REVIEW-2026-07-23.md B5. The review's assessment: "the sleeper —
integrity-under-error for mixed-ownership fleets has no incumbent literature
and your data is already sufficient." All numbers below are from RESULTS.md /
SPEC.md / SPEC-ADDENDUM-2026-07-23.md; nothing new needs to be run for a
first draft, though a 64-seed re-pin of the v6/v7 headline cells (mirroring
column R1) should be registered before submission.*

## Thesis (one sentence)

Across four independent error sources — strategic lies, self-knowledge error,
stale maps, and a moving field — system output stays flat while individual
books silently bleed; the effective countermeasures are structural (a
true-loss veto, attestation gating, auditable receipts), not behavioral.

## 1. Introduction

- Setting inherited from Paper 1: fleets owned by different parties; IR
  coordination; the benchmark world (cite Paper 1 for world/ladder detail).
- The operator's-eye framing: every failure mode below leaves the fleet
  dashboard green (delivered ~flat) while redistributing value between
  owners. The threat model for mixed-ownership robotics is not crashes; it
  is audit holes.

## 2. Deception tolerance of the veto tier (v6.0 — a registered kill, reported as the headline)

- BATNA inflation barely pays: +3.9 credit on a ~95 base, p=0.71; at f=1.0
  deal volume collapses (90→37, 92→23) and delivered lands on the rules-arm
  floor (231.2 vs 230.6).
- The discovery under the fired kill: Nash-IR bargaining with a true-loss
  veto is intrinsically deception-tolerant — every executed deal clears both
  TRUE disagreement points by construction; lies only make the liar pickier.
- Attested-all ≡ honest-all bit-identically (pinned test).

## 3. Attestation gates cooperation (v6.1)

- Open joint-optimization tier with liars = feeding frenzy: liar advantage
  +179/+126 credits (p<1e-4), 271–326 strip deals/run, delivered flat
  (corrected-physics numbers).
- Attestation gating (liars cannot attest; relegated to the veto tier):
  liar advantage +9.5/−2.2 n.s., strip deals 0.0 exactly.
- The gated dividend under corrected physics is survival, not speed: gated
  fleets end 1.06 stranded vs the veto tier's 15.31 (k5: 235 vs 162).

## 4. The gauge is a sensor too (v7)

- Gauge miscalibration leaves output flat but poisons receipts: poisoned
  deals 0 → 13.2 → 23.4/run as gauge noise grows (corrected numbers).
- The inward self-margin defense missed its registered ≥70% bar (roughly
  halves poisoning at ~30% fewer deals) — a price-of-safety dial, not a fix.
- Emergent echo: liar pickiness acts as an involuntary safety margin against
  self-noise.

## 5. Maps are gauges for the field (columns I and J)

- Static field (I): oracle − belief = +0.2 delivered n.s. — but belief-mode
  veto arms sign 3.4–9.2 truly-harmful deals/run vs zero under oracle. The
  swarm is its own sensor network (trading fleets hold ~3× fresher maps,
  165 vs 525 ticks staleness).
- Moving field (J): the significant information-value channel is the books
  (+7.0 poisoned deals, p=.0004), not output (+11.4, p=.15, n.s. at 16
  seeds — P16a failed as registered); ghosts double the net arm's poisoning
  (3.4 → 7.0/run).
- The generalized law: ANY self-input error (sensor or map) leaves output
  intact and corrupts books.

## 6. The information market heals books, not output (column K)

- Map market: 40 executed syncs/run, nothing for discovery (−0.7, p=1.0),
  poisoned deals cut ~30% — 64-seed re-pin (R1b, WIN): 5.00 → 3.53,
  p_w=.0007; delivered a descriptive wash (+4.53, p_w=.46).
- The bad-news trap, structural: bad-news-only syncs are IR-vetoed; bad news
  trades only when bundled with enough good news — Paper 1's C1 recursing
  into the information layer.

## 7. Discussion: from mechanism to settlement infrastructure

Move Paper 1's cut §5 paragraph here (one paragraph, flagged as motivation,
per the review): if the first casualty of every information failure is
receipt integrity, the durable product of a coordination layer for
mixed-ownership fleets is the audit trail — attested state and deal records
priced against ground truth — rather than the point improvement in delivered
ore. Column K makes it concrete: an information market that does nothing for
output is still worth running because it heals the books. Countermeasure
taxonomy: true-loss veto where self-knowledge is good; attestation gating
where trust is required; receipts audited against ground truth everywhere.

## 8. Limitations / TODO before drafting

- 16-seed columns for v6/v7/I/J cells: register and run a 64-seed re-pin of
  the headline cells (R1-style) before submission.
- The v6/v7 numbers must cite post-correction artifacts only (RESULTS.md
  retains superseded pre-correction section text — same policy as Paper 1
  submission note 1).
- Prior-art sweep for THIS paper's claims (adversarial robustness of
  negotiation, mechanism-design-with-verification, trust/reputation in MRS)
  has NOT been done — the LITERATURE.md sweep covered the bargaining niche,
  not the integrity niche.
- Venue: AAMAS or JAAMAS per the review; the settlement paragraph stays one
  paragraph, motivation-flagged.
