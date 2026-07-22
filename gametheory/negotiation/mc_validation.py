"""Does the compute tier actually WIN in realized play — or only in-model?

mc_prototype/mc_multi measured rollout policies in controlled envs. This is the
production check: the SHIPPED recommender WITH a compute budget vs the SAME
recommender at zero budget (the closed form), played out to a deal against a
population of conceder buyers whose concession rate / reservation are drawn from
ranges the MC's internal belief does NOT know exactly (de-circularised — the
opponent is not the rollout's own model). Paired (same buyer faces both arms),
with a 95% CI.

P11 RE-VALIDATION (2026-07-22). The published null (MC − closed = −0.002,
95% CI [−0.043, +0.038], 98% ties) was measured on the PRE-P7 engine, whose
accept-collapse (saturated concession schedule) forced BOTH arms into early
capitulation and crushed MC's action window — the counter nodes are the ONLY
place MC can move the price (`mc_search.py:189` short-circuits accept/walk). The
P7 fix landed (`plain_terms.py:144`, total-horizon), so that window is open for
the first time here; P9 separately proved MC is inert on ACCEPT nodes, so this
harness now isolates MC's COUNTER-price refinement value on the fixed engine.

TWO harness constraints, per the P11 lane:
  * DETERMINISTIC budget only. The old harness used wall-clock `compute_ms`
    (sample count = machine speed → non-reproducible). P11 uses the fixed
    `compute_samples` path (`mc_search.py:196-198`, `anytime_search` with
    `deadline_s=inf`): same seed + inputs ⇒ bit-identical result on any machine.
    Sample tiers are pinned from the shipped provenance `719k rollouts / 200ms`
    (`vend/NEXTMOVE.md:191`, ≈3.6k samples/ms) ⇒ 50ms≈180k, 200ms≈720k; shipped
    default 400k (`vend/advice.py:33`).
  * seed=0 for the population draw AND every MC call.

Run: python -m gametheory.negotiation.mc_validation
"""
import json
import numpy as np

from gametheory.negotiation.plain_terms import negotiate_turn
from gametheory.negotiation.mc_search import negotiate_turn_mc

WALK, TARGET = 100.0, 200.0     # seller floor / aspiration (dollars)
ROUNDS = 8
DELTA = 0.95                    # realized-surplus time cost per round

# Deterministic sample budgets (see module docstring): low bracket (≈old 50ms),
# SHIPPED default (the primary decision tier), high bracket (≈old 200ms).
TIERS = (180_000, 400_000, 720_000)
SHIPPED_TIER = 400_000

# Per-family stratification by the buyer's HIDDEN concession exponent e. The
# rollout belief fixes _E_OPP=2.5 (mc_search.py:46), so realized MC value should
# track how far true e deviates from that belief. Edges pre-registered (P11).
FAMILIES = (
    ("FAST (e<2.0)", 1.3, 2.0),          # concedes earlier than the belief
    ("MATCHED (2.0-3.0)", 2.0, 3.0),     # near the belief 2.5
    ("SLOW (e>=3.0)", 3.0, 4.0001),      # Boulware — concedes later than belief
)


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


def _ci_stats(d):
    """Paired mean, 95% CI half-width, and win/tie/lose fractions for a diff array.
    Tie = |d| <= 1e-6 (the harness's existing convention)."""
    d = np.asarray(d, float)
    n = len(d)
    mean = float(d.mean()) if n else 0.0
    se = float(d.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    win = float((d > 1e-6).mean()) if n else 0.0
    lose = float((d < -1e-6).mean()) if n else 0.0
    return {"n": n, "mean": mean, "ci": 1.96 * se,
            "lo": mean - 1.96 * se, "hi": mean + 1.96 * se,
            "win": win, "tie": 1.0 - win - lose, "lose": lose}


def experiment(n=600, seed=0, compute_samples=SHIPPED_TIER, verbose=True):
    """Paired realized-play measurement at a fixed DETERMINISTIC sample budget.

    Returns a dict with the aggregate delta/CI/tie-rate, deal rates, and the
    per-family (by hidden concession exponent e) breakdown.
    """
    rng = np.random.default_rng(seed)
    # buyer population — concession rate e, reservation b, initial concession c0
    # vary OUTSIDE what the MC rollout assumes (its belief uses a single fixed
    # conceder shape: _C0=0.50, _E_OPP=2.5). De-circularised opponent.
    bs = rng.uniform(115, 200, size=n)
    es = rng.uniform(1.3, 4.0, size=n)
    c0s = rng.uniform(0.30, 0.60, size=n)

    closed = lambda bo, mo, rl: negotiate_turn(
        side="sell", walk_away=WALK, target=TARGET,
        counterparty_offers=bo, my_previous_offers=mo, rounds_left=rl)
    # DETERMINISTIC: fixed compute_samples + seed=0 => bit-identical per node.
    mc = lambda bo, mo, rl: negotiate_turn_mc(
        side="sell", walk_away=WALK, target=TARGET, counterparty_offers=bo,
        my_previous_offers=mo, rounds_left=rl, compute_samples=compute_samples, seed=0)

    su_c, su_m, deal_c, deal_m = [], [], [], []
    for b, e, c0 in zip(bs, es, c0s):
        pc, tc = run_negotiation(closed, b, e, c0)
        pm, tm = run_negotiation(mc, b, e, c0)
        su_c.append(_surplus(pc, tc)); su_m.append(_surplus(pm, tm))
        deal_c.append(pc is not None); deal_m.append(pm is not None)
    su_c, su_m = np.array(su_c), np.array(su_m)
    d = su_m - su_c

    agg = _ci_stats(d)
    agg["surplus_closed"] = float(su_c.mean())
    agg["surplus_mc"] = float(su_m.mean())
    agg["deal_closed"] = float(np.mean(deal_c))
    agg["deal_mc"] = float(np.mean(deal_m))
    agg["rel_pct"] = agg["mean"] / max(su_c.mean(), 1e-9) * 100.0

    families = {}
    for label, lo, hi in FAMILIES:
        mask = (es >= lo) & (es < hi)
        families[label] = _ci_stats(d[mask])

    result = {"n": n, "seed": seed, "compute_samples": int(compute_samples),
              "aggregate": agg, "families": families}

    if verbose:
        _print_tier(result)
    return result


def _verdict(stat):
    if stat["lo"] > 0:
        return "MC EDGE (CI excludes 0 above)"
    if stat["hi"] < 0:
        return "MC NEGATIVE (CI excludes 0 below)"
    return "NULL (CI includes 0)"


def _print_tier(r):
    a = r["aggregate"]
    tag = " <- SHIPPED (primary)" if r["compute_samples"] == SHIPPED_TIER else ""
    print(f"\n=== realized play: closed vs compute  "
          f"(n={r['n']}, compute_samples={r['compute_samples']:,}){tag} ===")
    print(f"  mean discounted surplus:  CLOSED {a['surplus_closed']:7.3f}   "
          f"MC {a['surplus_mc']:7.3f}")
    print(f"  deal rate:                CLOSED {a['deal_closed']*100:5.1f}%   "
          f"MC {a['deal_mc']*100:5.1f}%")
    print(f"  MC - CLOSED:  {a['mean']:+.4f}  95% CI [{a['lo']:+.4f}, {a['hi']:+.4f}]"
          f"  ({a['rel_pct']:+.2f}%)")
    print(f"  win {a['win']*100:.1f}% / tie {a['tie']*100:.1f}% / lose {a['lose']*100:.1f}%")
    print(f"  verdict: {_verdict(a)}")
    print(f"  per-family (by hidden concession exponent e; belief _E_OPP=2.5):")
    for label, f in r["families"].items():
        print(f"    {label:20s} n={f['n']:4d}  Δ {f['mean']:+.4f} "
              f"[{f['lo']:+.4f}, {f['hi']:+.4f}]  tie {f['tie']*100:5.1f}%")


if __name__ == "__main__":
    N = 600
    out = {"n": N, "seed": 0, "tiers": {}}
    for cs in TIERS:
        r = experiment(n=N, seed=0, compute_samples=cs)
        out["tiers"][str(cs)] = r
    # artifact for the RESULTS append (deterministic; re-runnable byte-for-byte)
    with open("/private/tmp/claude-501/-Users-ryuxik-Desktop-snhp/"
              "d80e004f-cc0e-4011-a063-84d12b0195d8/scratchpad/p11_compute_moat/"
              "p11_results.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\n[artifact written to scratchpad/p11_compute_moat/p11_results.json]")
