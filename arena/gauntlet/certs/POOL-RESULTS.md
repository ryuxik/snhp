# Counterparty-pool experiment — results (registered: PREREG-pool.md)

**VERDICT: SURVIVE.** Engine separates from the naive baseline on pooled own-utility, delta > 0 with p < 0.01 on BOTH scenario sets — per the registration, candidate skill is certifiable against the declared pool and the certificate's primary claim moves to pooled own-utility (spec gauntlet-cert/3).

## Primary statistic (pooled own-utility, the registered kill)

| scenario set | n pairs | engine u | naive u | delta | Cohen's d | perm p | passes (delta>0 & p<0.01) |
|---|---|---|---|---|---|---|---|
| PUBLIC (seed 20260709) | 360 | 0.5591 | 0.4524 | +0.1067 | +0.560 | 0.0001 | YES |
| HELD-OUT-NEW (seed 20260718) | 360 | 0.5651 | 0.4566 | +0.1086 | +0.563 | 0.0001 | YES |

## Per-counterparty breakdown — PUBLIC (seed 20260709)

| counterparty | engine u | naive u | delta | perm p | engine deal% | naive deal% |
|---|---|---|---|---|---|---|
| naive | 0.5953 | 0.5249 | +0.0704 | 0.0004  ** | 93% | 95% |
| hardball | 0.4742 | 0.3020 | +0.1722 | 0.0001  ** | 53% | 2% |
| conceder | 0.6079 | 0.5303 | +0.0776 | 0.0001  ** | 99% | 93% |
| POOLED | 0.5591 | 0.4524 | +0.1067 | 0.0001  ** | 82% | 63% |

(`**` marks delta>0 AND p<0.01 on that row; only the POOLED row feeds the verdict. A pool that separates only via one member is exactly that — see the rows.)

## Per-counterparty breakdown — HELD-OUT-NEW (seed 20260718)

| counterparty | engine u | naive u | delta | perm p | engine deal% | naive deal% |
|---|---|---|---|---|---|---|
| naive | 0.6013 | 0.5303 | +0.0711 | 0.0003  ** | 96% | 90% |
| hardball | 0.4873 | 0.3034 | +0.1838 | 0.0001  ** | 59% | 2% |
| conceder | 0.6068 | 0.5360 | +0.0708 | 0.0001  ** | 98% | 93% |
| POOLED | 0.5651 | 0.4566 | +0.1086 | 0.0001  ** | 84% | 62% |

(`**` marks delta>0 AND p<0.01 on that row; only the POOLED row feeds the verdict. A pool that separates only via one member is exactly that — see the rows.)

---

# Reference tier (SNHP engine) — SEPARATELY REPORTED, NOT part of the certified claim

> The certified verdict above concerns the FROZEN THREE (naive, hardball, conceder) and is unchanged by anything in this section. The SNHP engine is an ADDITIONAL reported opponent (PREREG-pool.md Amendment 1); adding it to a registration that just passed would be the forking-paths error this program avoids, so it is never pooled into the primary statistic under any outcome.

**The registered prediction, stated before this arm was run:**

> Registered before running (PREREG-pool.md Amendment 1): the SNHP-reference tier does NOT separate competent from adequate (prior measurement: own-utility delta +0.006, p=0.68) but DOES catch weak agents downward (recorded solo capture: Sonnet -0.093, Haiku -0.161, both p=0.0001). We predict it functions as a FLOOR test, not a RANKING test.

**The outcome:**

| scenario set | n pairs | engine u | naive u | delta | Cohen's d | perm p | separates (delta>0 & p<0.01) |
|---|---|---|---|---|---|---|---|
| PUBLIC (seed 20260709) | 120 | 0.6611 | 0.6595 | +0.0016 | +0.010 | 0.9158 | NO |
| HELD-OUT-NEW (seed 20260718) | 120 | 0.6620 | 0.6881 | -0.0260 | -0.158 | 0.0881 | NO |

**Verdict on the prediction: HELD.**

The reference tier does not separate the competent candidate from the adequate baseline at the registered bar on both sets — as predicted. Published as exactly that: **the reference tier catches weakness; it cannot rank strength.** It stays out of the certified statistic permanently, per the registration.

Context — what the tier is good for (the floor half of the prediction) is evidenced by the recorded historical run: solo Sonnet and Haiku separate DOWNWARD vs the naive baseline at p=0.0001 (capture; see certs/SEPARATION.md). Those agents never played the pool, so they are historical context, not pool-certified.

---

## Context (no role in the verdict)

| set | candidate | capture | logroll | deal_rate |
|---|---|---|---|---|
| PUBLIC | engine | 0.8343 | 0.2575 | 82% |
| PUBLIC | naive | 0.6607 | -0.2782 | 63% |
| PUBLIC | champion | 0.8378 | 0.2736 | 83% |
| HELD-OUT-NEW | engine | 0.8549 | 0.2390 | 84% |
| HELD-OUT-NEW | naive | 0.6643 | -0.3613 | 62% |
| HELD-OUT-NEW | champion | 0.8593 | 0.2649 | 86% |

- champion vs naive (context, PUBLIC): own-u delta +0.0918, p=0.0001 — not part of the kill.
- champion vs naive (context, HELD-OUT-NEW): own-u delta +0.0977, p=0.0001 — not part of the kill.

_Registered design executed verbatim: pool parameters frozen in PREREG-pool.md; 60 scenarios x 2 roles x 3 counterparties per candidate per set; pairing by (scenario_id, role, counterparty); two-sided sign-flip permutation, n_perm=10000, RNG derived from the scenario-set seed exactly as in certify.py. Deterministic local seats only — no LLM, no network. Raw records: certs/pool-matches.json._
