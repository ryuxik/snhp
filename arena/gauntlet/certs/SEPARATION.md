# Gauntlet certificate — separation analysis (the registered kill + the post-hoc redesign)

## 1. The registered kill: CAPTURE — **KILL FIRES** (verdict unchanged)

The pre-registered bar: the gauntlet must separate a *competent scripted* candidate (the SNHP `EngineSeat`) from the *naive split-the-difference* baseline (`NaiveSeat`) on **capture**, two-sided paired permutation test, **p < 0.01**. If it cannot, the certified capture number carries no information.

- **Public practice seed** (20260709, n=60x2 roles): engine capture 0.9207 vs naive 0.8770, delta +0.0437, **p = 0.0128** — fails p<0.01 (Cohen's d ~ 0.23).
- **Held-out ranking seed** (recorded, read-only): engine capture 0.9078 vs naive 0.9118, delta -0.0041, **p = 0.7573** — the naive baseline is, if anything, *ahead*.

**Diagnosis** (coordinator, confirmed here): capture is *joint* efficiency against a counterparty (`EngineSeat`) that logrolls hard from its own side. When one seat does the frontier-finding, even a plain anchor-and-split bargainer rides along to ~90% of the ceiling. Capture measures the pair, not the candidate. The same test DOES flag *below-baseline* agents sharply (sonnet/haiku, tables below) — capture detects incompetence, it cannot certify skill.

## 2. Redesign: logroll as the certified statistic — **NOT VALIDATED — held-out logroll does not separate**

**Post-hoc disclosure (non-negotiable):** logroll was adopted as the primary certified statistic AFTER the capture kill fired. That is a post-hoc metric change — the hypothesis was formed on the same public-seed data that suggested it, so it proves nothing by itself and must clear a held-out validation: engine-vs-naive **logroll** on the recorded held-out ranking set, p < 0.01. The recorded matches carry per-match logroll (all 1200 rows; checked), so the validation is computable read-only.

- **The gate — held-out logroll (recorded, read-only):** engine 0.6152 vs naive 0.6662, delta -0.0510, **p = 0.4261** (120 scored-both pairs) — naive is *ahead*; nowhere near p<0.01. **The gate fails.**
- **Public seed, the certificate's own match-seed recipe** (leaderboard blake2b): engine logroll 0.6831 vs naive 0.4600, delta +0.2232, **p = 0.0143** — misses p<0.01 under this recipe. The redesign's motivating run (coordinator, a different match-seed recipe) reported delta +0.2254 at p=0.0019 on the same scenario set — the direction and magnitude REPRODUCE, the significance does not: p flips across the 0.01 bar depending on the per-match seed recipe. A significance that depends on the seed recipe is not certification-grade.

**Consequence:** the certificate format now carries logroll as the primary statistic (with the scored-both pairing and pair counts), but the engine certificate is NOT re-issued as "fixed": `not_attested` states in the certificate itself that the primary statistic's held-out validation failed and that the certificate certifies the measurement, not baseline-beating skill. On present evidence NO per-match statistic in the recorded data (capture, logroll, own-utility — the coordinator measured own-utility delta +0.006, p=0.68) separates engine from naive on held-out. The honest read: against a hard-logrolling counterparty, the naive splitter's outcomes are statistically indistinguishable from the engine's, so candidate skill must be measured against a NON-logrolling (or scripted-diverse) counterparty pool — a protocol change, not a metric change. That is the remaining redesign this analysis points to.

## Separation tables (all candidates vs naive)

**LOGROLL (primary; scored-both pairing)**

| comparison | n pairs | candidate | naive | delta | Cohen's d | perm p |
|---|---|---|---|---|---|---|
| engine vs naive (public seed) | 120 | 0.6831 | 0.4600 | +0.2232 | +0.225 | 0.0143 |
| champion vs naive (public seed) | 120 | 0.5565 | 0.4600 | +0.0965 | +0.080 | 0.3844 |
| engine vs naive (HELD-OUT, recorded) | 120 | 0.6152 | 0.6662 | -0.0510 | -0.075 | 0.4261 |
| evolved-champion vs naive (HELD-OUT, recorded) | 120 | 0.5621 | 0.6662 | -0.1041 | -0.112 | 0.2211 |
| claude-opus-4-8 vs naive (HELD-OUT, recorded) | 120 | 0.4961 | 0.6662 | -0.1700 | -0.182 | 0.0461 |
| claude-sonnet-5 vs naive (HELD-OUT, recorded) | 120 | 0.1854 | 0.6662 | -0.4808 | -0.446 | 0.0001 |
| claude-haiku-4-5-20251001 vs naive (HELD-OUT, recorded) | 120 | -0.0133 | 0.6662 | -0.6795 | -0.650 | 0.0001 |

**CAPTURE (secondary; all pairs)**

| comparison | n pairs | candidate | naive | delta | Cohen's d | perm p |
|---|---|---|---|---|---|---|
| engine vs naive (public seed) | 120 | 0.9207 | 0.8770 | +0.0437 | +0.232 | 0.0128 |
| champion vs naive (public seed) | 120 | 0.9071 | 0.8770 | +0.0301 | +0.140 | 0.1312 |
| engine vs naive (HELD-OUT, recorded) | 120 | 0.9078 | 0.9118 | -0.0041 | -0.029 | 0.7573 |
| evolved-champion vs naive (HELD-OUT, recorded) | 120 | 0.9100 | 0.9118 | -0.0018 | -0.011 | 0.9098 |
| claude-opus-4-8 vs naive (HELD-OUT, recorded) | 120 | 0.8840 | 0.9118 | -0.0279 | -0.137 | 0.1381 |
| claude-sonnet-5 vs naive (HELD-OUT, recorded) | 120 | 0.8188 | 0.9118 | -0.0930 | -0.444 | 0.0001 |
| claude-haiku-4-5-20251001 vs naive (HELD-OUT, recorded) | 120 | 0.7506 | 0.9118 | -0.1612 | -0.645 | 0.0001 |

(`**` marks delta>0 AND p<0.01. Local rows use the public scenario seed 20260709 with the leaderboard match-seed recipe; the permutation RNG derives from that seed exactly as in the certificate. Held-out rows are read verbatim from `arena/web/gauntlet-matches.json`; their scenario seed is private, so their permutation RNG uses a fixed documented constant (0). Sonnet/haiku separate DOWNWARD — worse than naive — on both metrics; no candidate separates upward on held-out.)

_Generated by `python -m arena.gauntlet.separation` (n=60, public seed 20260709, alpha=0.01). Numbers are from actual local runs and recorded read-only data; no LLM was called. Section 2 is a disclosed post-hoc analysis._
