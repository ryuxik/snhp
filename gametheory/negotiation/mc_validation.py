"""Does the compute tier actually WIN in realized play — or only in-model?

mc_prototype/mc_multi measured rollout policies in controlled envs. This is the
production check: the SHIPPED recommender with `compute_ms` vs the SAME recommender
at compute_ms=0 (the closed form), played out to a deal against a population of
conceder buyers whose concession rate / reservation are drawn from ranges the MC's
internal belief does NOT know exactly (de-circularised — the opponent is not the
rollout's own model). Paired (same buyer faces both), with a 95% CI.

If MC wins here, `compute_ms` is a real edge worth promoting. If not, it stays an
off-by-default mechanism and we say so. Run: python -m gametheory.negotiation.mc_validation
"""
import numpy as np

from gametheory.negotiation.plain_terms import negotiate_turn
from gametheory.negotiation.mc_search import negotiate_turn_mc

WALK, TARGET = 100.0, 200.0     # seller floor / aspiration (dollars)
ROUNDS = 8
DELTA = 0.95                    # time cost per round


def willingness(t, b, e, c0):
    """Buyer's max acceptable price at round t — rises from c0*b toward b by the
    deadline (they concede upward). b, e, c0 are the buyer's HIDDEN parameters."""
    return b * (c0 + (1 - c0) * (t / (ROUNDS - 1)) ** (1.0 / e))


def run_negotiation(policy, b, e, c0):
    """Play one negotiation to conclusion. policy(buyer_offers, my_offers, rounds_left)
    -> recommender dict. Returns (deal_price or None, round)."""
    buyer_offers, my_offers = [], []
    for t in range(ROUNDS):
        rec = policy(buyer_offers, my_offers, ROUNDS - t)
        act = rec["action"]
        if act == "accept":
            return (buyer_offers[-1] if buyer_offers else rec["recommended_price"]), t
        if act == "walk":
            return None, t
        price = float(rec["recommended_price"])
        my_offers.append(price)
        w = willingness(t, b, e, c0)
        if price <= w:                       # buyer accepts the seller's ask
            return price, t
        buyer_offers.append(round(w, 2))     # else counters at their current willingness
    return None, ROUNDS


def _surplus(deal_price, t):
    return (deal_price - WALK) * (DELTA ** t) if deal_price is not None else 0.0


def experiment(n=400, seed=0, compute_ms=100):
    rng = np.random.default_rng(seed)
    # buyer population — concession rate e and reservation b vary OUTSIDE what the
    # MC rollout assumes (its belief uses a single fixed conceder shape).
    bs = rng.uniform(115, 200, size=n)
    es = rng.uniform(1.3, 4.0, size=n)
    c0s = rng.uniform(0.30, 0.60, size=n)

    closed = lambda bo, mo, rl: negotiate_turn(
        side="sell", walk_away=WALK, target=TARGET,
        counterparty_offers=bo, my_previous_offers=mo, rounds_left=rl)
    mc = lambda bo, mo, rl: negotiate_turn_mc(
        side="sell", walk_away=WALK, target=TARGET, counterparty_offers=bo,
        my_previous_offers=mo, rounds_left=rl, compute_ms=compute_ms)

    su_c, su_m, deal_c, deal_m = [], [], [], []
    for b, e, c0 in zip(bs, es, c0s):
        pc, tc = run_negotiation(closed, b, e, c0)
        pm, tm = run_negotiation(mc, b, e, c0)
        su_c.append(_surplus(pc, tc)); su_m.append(_surplus(pm, tm))
        deal_c.append(pc is not None); deal_m.append(pm is not None)
    su_c, su_m = np.array(su_c), np.array(su_m)

    d = su_m - su_c
    se = d.std(ddof=1) / np.sqrt(n)
    print(f"\n=== realized play: closed form vs compute (n={n}, compute_ms={compute_ms}) ===")
    print(f"  mean discounted surplus:  CLOSED {su_c.mean():7.3f}   MC {su_m.mean():7.3f}")
    print(f"  deal rate:                CLOSED {np.mean(deal_c)*100:5.1f}%   MC {np.mean(deal_m)*100:5.1f}%")
    print(f"  MC - CLOSED:  {d.mean():+.3f}  95% CI [{d.mean()-1.96*se:+.3f}, {d.mean()+1.96*se:+.3f}]"
          f"   ({d.mean()/max(su_c.mean(),1e-9)*100:+.1f}%)")
    win = (d > 1e-6).mean(); lose = (d < -1e-6).mean()
    print(f"  win {win*100:.0f}% / tie {(1-win-lose)*100:.0f}% / lose {lose*100:.0f}%")
    verdict = "REAL EDGE" if d.mean() - 1.96 * se > 0 else (
        "NO EDGE (CI includes 0)" if d.mean() + 1.96 * se > 0 else "WORSE")
    print(f"  verdict: {verdict}")
    return su_c, su_m


if __name__ == "__main__":
    for ms in (50, 200):
        experiment(compute_ms=ms)
