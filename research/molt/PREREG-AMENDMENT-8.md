# PREREG AMENDMENT 8 — if not the manager, then what?

*Written 2026-07-25, before any v11 code exists. Exploratory.*

## A8.0 What Amendment 7 removed

The menu is iso-cost to the firm and hands the employee $1,116–$2,841. My leading
explanation for why the world doesn't do it was the manager: the firm gains, but
the person who'd offer the menu has a different bonus.

**A7 killed that.** Even at `alpha = 0.2` with a comp-budget penalty, the menu is
worth **+$4,789** to the employee over haggling (K40 did not fire) and costs the
manager **$2,589 less comp budget** than arguing does (K42 did not fire). It is
not merely tolerable to a squeezed manager — it is their cheapest route to
retention.

So the puzzle is worse. Two candidates left, both untested.

## A8.1 The band

A menu of three packages the employer would equally sign **reveals the size of its
flexibility**. That is information comp teams spend real effort withholding, and
my employer's payoff has no term for losing it — which is why the menu is free in
the model and may not be free in life.

Modelled as `band_leak`: offering a menu of K items raises the employee's
estimate of the employer's slack, and that estimate carries into **next season's**
negotiation. This requires the first cross-season link in the study; seasons have
been independent since v1.

## A8.2 Precedent

One person's menu becomes everyone's expectation. `peer_spill = 0.30` captures
this for base pay only — a raise leaks to the band. Nothing makes the *menu*
leak. Modelled as `menu_precedent`: the share of the crew who expect a menu next
season after seeing one.

## A8.3 Kills

Bar: **2% of salary ≈ $2,253**.

**K44 — DOES THE BAND EXPLAIN IT?** If, with `band_leak` on, the employer's
two-season payoff from offering a menu falls below its payoff from refusing, then
band secrecy is the explanation and the product must be sold as something an
employer can offer *without* revealing slack. If it does not fire, band secrecy is
not the reason either.

**K45 — DOES PRECEDENT EXPLAIN IT?** Same test for `menu_precedent`.

**K46 — IS THERE ANY MODELLED REASON AT ALL?** If both K44 and K45 fail to fire,
this study has **no mechanism that explains why employers don't already do this**,
and the article says exactly that rather than inventing one.

**K47 — THE BELIEF ANOMALY.** A7 produced a firm that is *better off* under a
stingy manager (−5,893 vs −11,038) despite attrition rising 15% → 23%. That is the
belief-versus-truth gap: an aligned manager buys retention it cannot verify it
needs. If the firm's realised payoff is not maximised by its own belief-optimal
policy, the belief model is mis-specified in a way that flatters stinginess, and
every employer-side number in v7 is suspect until it is explained.

## A8.4 Predictions

1. **K44 fires** — band secrecy is the real cost.
2. **K45 does not fire** — precedent is second-order next to the band.
3. **K46 does not fire**, because K44 fires.
4. **K47 fires** — I expect the anomaly to be real mis-specification, not a finding.
