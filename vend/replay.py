"""P3 — sessioned vend matches for the theater, via the REAL gauntlet
machinery: `run_match` with the engine in both seats on a vend-shaped
scenario (PRICE × ITEM × QUANTITY, zero-sum rails, private priorities — the
exact structure every leaderboard replay uses, so the multi-turn concession
drama is the engine's real behavior, not scripting). The sim's economics
stay with the exact Nash engine (scenario.py); these are mode-B sessions
made watchable.

  python3 -m vend.replay          # writes arena/web/vend-replays.json
"""
from __future__ import annotations

import json

from arena.gauntlet.agents import EngineSeat
from arena.gauntlet.protocol import run_match
from arena.gauntlet.replay import match_to_duel_script
from arena.scenarios import BundleScenario

from vend.core import substream
from vend.world import (WorldConfig, build_catalog, fresh_machine, hour_of,
                        sample_consumer)

DEADLINE = 12
PRICE_RUNGS = 8
# the logroll structure: buyer weights price; the machine weights which item
# moves (expiring stock) and volume
W_MACHINE = [0.25, 0.40, 0.35]   # price, item, quantity
W_BUYER = [0.50, 0.30, 0.20]


def _norm(vals):
    lo, hi = min(vals), max(vals)
    return [0.5 if hi == lo else (v - lo) / (hi - lo) for v in vals]


def vend_scenario(state, consumer, catalog) -> tuple[BundleScenario, list, float]:
    """A vend situation as a gauntlet scenario. Rail direction = machine-
    favorable (buyer utility is 1 − that, per BundleScenario semantics)."""
    skus = sorted(catalog, key=lambda s: -consumer.wtp[s])[:4]
    skus.sort(key=lambda s: (state.days_to_expiry(s) or 99))
    lead = catalog[skus[0]]
    floor = max(lead.salvage, 0.3 * lead.list_price)
    rungs = [round(floor + i * (lead.list_price - floor) / (PRICE_RUNGS - 1), 2)
             for i in range(PRICE_RUNGS)]
    dte = {s: state.days_to_expiry(s) for s in skus}
    item_dirs = _norm([(2.0 if (dte[s] is not None and dte[s] <= 1) else 0.0)
                       + state.stock(s) / 10.0 for s in skus])
    sc = BundleScenario(
        issues=[("price", [f"${r:.2f}" for r in rungs]),
                ("item", skus),
                ("quantity", ["1", "2", "3"])],
        seller_dirs=[[i / (PRICE_RUNGS - 1) for i in range(PRICE_RUNGS)],
                     item_dirs,
                     [0.2, 0.6, 1.0]],
        era="vend")
    return sc, skus, floor


def main() -> int:
    cfg = WorldConfig(sigma_cal=0.3, dow=True, glut_prob=1.0)
    catalog = build_catalog(cfg, master_seed=20260713)

    # Run a batch of REAL matches and curate the watchable ones (deals that
    # took a genuine concession dance) — the featured_replays pattern: every
    # kept script is a real match, selection is only about legibility.
    candidates = []
    for i in range(24):
        day, tick = i % 4, (18 + i * 9) % 90
        state = fresh_machine("replay", catalog, cfg, master_seed=20260713)
        state.day, state.tick = day, tick
        consumer = sample_consumer(20260713, day, tick, i, catalog, cfg)
        sc, skus, floor = vend_scenario(state, consumer, catalog)
        seed = substream(20260713, "vendreplay", i)
        mr = run_match(EngineSeat(seed), sc, W_MACHINE, W_BUYER,
                       role="buyer", condition="solo",
                       scenario_id=i, match_seed=seed, deadline=DEADLINE)
        candidates.append((mr, sc, skus, state, consumer))

    deals = [c for c in candidates if c[0].deal and 3 <= c[0].rounds <= 10]
    deals.sort(key=lambda c: -c[0].capture)
    picked = deals[:3] or [c for c in candidates if c[0].deal][:3]

    scripts = []
    for mr, sc, skus, state, consumer in picked:
        m = mr.to_dict()
        m["model"] = "your agent"
        script = match_to_duel_script(m, sc, W_MACHINE, W_BUYER)

        # reskin the gauntlet framing as the vend theater
        dte = state.days_to_expiry(skus[0])
        script["names"] = {"seller": "THE MACHINE", "buyer": "YOUR AGENT"}
        script["origins"] = {
            "seller": f"stock {state.stock(skus[0])}"
                      + (f" · expires in {dte}d" if dte is not None and dte <= 2 else "")
                      + f" · {hour_of(state.tick)}:00",
            "buyer": f"your preferences · walk cost ${consumer.walk_cost:.2f}",
        }
        script["subtitle"] = ("a real engine-vs-engine vend negotiation — "
                              "every turn is the live engine")
        if mr.deal and mr.package:
            script["reveal"]["line"] = (
                f"Deal in {mr.rounds} rounds: {mr.package['quantity']}× "
                f"{mr.package['item']} at {mr.package['price']} — "
                f"{mr.capture:.0%} of the frontier captured.")
        scripts.append(script)

    out = "arena/web/vend-replays.json"
    with open(out, "w") as f:
        json.dump(scripts, f, indent=1)
    print(f"wrote {out}: {len(scripts)} real matches, "
          f"rounds={[c[0].rounds for c in picked]}, "
          f"capture={[round(c[0].capture, 2) for c in picked]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
