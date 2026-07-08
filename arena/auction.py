"""The Grand Auction — the communal set piece every N generations. A single pot
auctioned with the real auction natives (optimal_bid). Format rotates so the
crowd sees first-price *shading* vs Vickrey *truthfulness*: each bidder's true
valuation and its recommended bid are both shown. Strategy is the engine's;
this module only stages it.
"""
from __future__ import annotations

import hashlib

import numpy as np

from gametheory.auctions.bidder import optimal_bid

_FORMATS = ("second_price_vickrey", "first_price", "english_ascending")


def _seed(base: int, k: int) -> None:
    h = hashlib.blake2b(f"auc:{base}:{k}".encode(), digest_size=8).digest()
    np.random.seed(int.from_bytes(h, "big") & 0x7FFFFFFF)


def run_auction(world, agents):
    """Generator yielding auction.* events. `world` is the World (for energy /
    ledger / event envelope); agents is the current population list."""
    cfg = world.cfg
    rng = world.rng
    fmt = _FORMATS[(world.gen // max(cfg.auction_every_gens, 1)) % len(_FORMATS)]

    # Up to 8 wealthiest agents bid; private valuations = f(genome, energy).
    bidders = sorted(agents, key=lambda a: a.energy, reverse=True)[:8]
    if len(bidders) < 2:
        return
    valuations = {}
    for a in bidders:
        v = 20.0 + 40.0 * a.genome.pareto_knob + 20.0 * a.genome.open_aggression \
            + float(rng.uniform(-5, 5))
        valuations[a.id] = max(1.0, v)

    vals = np.array(list(valuations.values()))
    prior = {"family": "uniform", "params": {"low": float(max(1.0, vals.min() - 10)),
                                             "high": float(vals.max() + 10)}}

    yield world._ev("auction.start", format=fmt, pot=cfg.auction_pot,
                    n_bidders=len(bidders),
                    bidders=[{"id": a.id, "name": a.name} for a in bidders])

    bids = {}
    for k, a in enumerate(bidders):
        _seed(world.cfg.seed * 31 + world.gen, k)
        rec = optimal_bid(auction_format=fmt, my_valuation=valuations[a.id],
                          n_competing_bidders=len(bidders) - 1,
                          competitor_value_prior=prior,
                          risk_aversion=float(np.clip(0.3 + 0.7 * (1 - a.genome.walk_margin), 0.1, 1.0)))
        bid = float(rec["optimal_bid"])
        bids[a.id] = bid
        yield world._ev("auction.bid", id=a.id, value=round(valuations[a.id], 2),
                        bid=round(bid, 2),
                        shaded=round(valuations[a.id] - bid, 2),
                        truthful=bool(rec.get("dominant_strategy", False)))

    # Resolve: highest bid wins; price by format.
    ranked = sorted(bids.items(), key=lambda x: x[1], reverse=True)
    winner_id, top_bid = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if fmt == "first_price":
        price = top_bid
    else:  # vickrey / english both pay ~second price
        price = second
    winner = world.agents.get(winner_id)
    gain = 0.0
    if winner is not None:
        surplus_frac = float(np.clip((valuations[winner_id] - price) / max(valuations[winner_id], 1e-6), 0.0, 1.0))
        gain = cfg.auction_pot * surplus_frac
        winner.energy += gain
        world.ledger["auction"] += gain
        world._cap(winner)
    yield world._ev("auction.hammer", winner=winner_id,
                    price=round(price, 2), gain=round(gain, 1), format=fmt)
    yield world._ev("highlight", kind="grand_auction",
                    refs={"winner": winner_id, "format": fmt},
                    blurb=f"grand auction ({fmt.split('_')[0]}) won for {price:.0f}")
