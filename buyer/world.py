"""The buyer's environment: merchants to negotiate against and a seeded buyer
population with true values. This is the ADAPTER/environment layer — it may
import vend to build vend-backed merchants and to draw buyers from vend's true
demand process. A toy path (no vend) mirrors it so every experiment can run if
vend is mid-refactor.

Design choices, stated for reviewers to attack:
  * The population faces a SHARED merchant state (one board, many buyers, no
    stock depletion between them). That makes each buyer's frontier well-defined
    and IDENTICAL across policy arms for the same identity — exact pairing on
    buyer identity, the whole rigor rule. It deliberately drops the stock-
    competition dynamics vend's full sim has; that is a separate question from
    "is the buyer near its own frontier", which is what this package measures.
  * Buyers are drawn across operating hours (per-buyer tick) so the population
    spans low-value off-peak strollers and high-value lunch WTP — heterogeneity
    that gives shop/time/commit something to act on.
"""
from __future__ import annotations

from dataclasses import dataclass

from buyer.merchant import ToyListing, ToyMerchant, VendMerchant


@dataclass(frozen=True)
class BuyerDraw:
    uid: int
    wtp: dict[str, float]
    walk_cost: float


# ── vend-backed environment ─────────────────────────────────────────────────

def vend_config(**kw):
    from vend.world import WorldConfig
    return WorldConfig(**kw)


def draw_vend_population(master_seed: int, n: int, *, cfg=None,
                        day: int = 0, tick_lo: int = 6, tick_hi: int = 84
                        ) -> list[BuyerDraw]:
    """Draw n buyers from vend's TRUE demand process. Each buyer arrives at a
    per-buyer tick (seeded on identity) so the population spans the day's WTP
    range. Keyed only on (master_seed, k) → paired across arms by construction."""
    from vend.core import substream
    from vend.world import build_catalog, sample_consumer
    import numpy as np
    cfg = cfg or vend_config()
    catalog = build_catalog(cfg, master_seed)
    pop = []
    for k in range(n):
        tk = int(np.random.default_rng(substream(master_seed, "btick", k)
                                       ).integers(tick_lo, tick_hi))
        c = sample_consumer(master_seed, day, tk, k, catalog, cfg)
        pop.append(BuyerDraw(uid=c.uid, wtp=dict(c.wtp), walk_cost=c.walk_cost))
    return pop


def vend_markdown_merchant(master_seed: int, *, cfg=None, day: int = 0,
                           tick: int = 40, merchant_id: str = "vend-markdown",
                           attested_only: bool = False) -> VendMerchant:
    """The near-future END-OF-DAY state a TIME-ing buyer defers for: the
    perishables (shelf_life <= 3) are now expiring TONIGHT (days-to-expiry = 0),
    so their opportunity cost drops to salvage (c_eff = salvage << cost) and the
    Nash engine marks them down hard. This is the consumer-side mirror of the
    seller's yield management. Built on the buyer's OWN machine instance
    (vend/ is never edited): the fresh perishable lots are replaced by lots
    dated to expire today, plus a glut second lot to make the markdown deep."""
    from vend.core import Lot
    from vend.world import build_catalog, day_state, fresh_machine
    cfg = cfg or vend_config()
    catalog = build_catalog(cfg, master_seed)
    state = fresh_machine(merchant_id, catalog, cfg, master_seed)
    state.day, state.tick = day, tick
    for sku, l in catalog.items():
        if l.shelf_life_days <= 3:
            state.lots = [x for x in state.lots if x.sku != sku]  # drop fresh lot
            state.lots.append(Lot(sku=sku, quantity=2 * l.par_stock,
                                  expires_day=day))               # expires tonight
    ds = day_state(cfg, master_seed, day)
    return VendMerchant(merchant_id, state, catalog, dow_mult=ds.dow_mult,
                        traffic_scale=cfg.traffic_scale,
                        attested_only=attested_only)


def vend_merchants(master_seed: int, specs: list[dict]) -> list[VendMerchant]:
    """Build a set of vend machines. Each spec is a dict of
    {id, cfg_kwargs, seed_offset, day, tick, attested_only}. Different seeds/
    days/glut draws make the boards differ, giving shop/time room to act."""
    out = []
    for i, sp in enumerate(specs):
        cfg = vend_config(**sp.get("cfg_kwargs", {}))
        m = VendMerchant.from_vend(
            sp.get("id", f"vend-{i:02d}"), cfg,
            seed=master_seed + sp.get("seed_offset", 0),
            day=sp.get("day", 0), tick=sp.get("tick", 40),
            attested_only=sp.get("attested_only", False))
        out.append(m)
    return out


# ── toy environment (no vend) ────────────────────────────────────────────────

_TOY_SPEC = [
    # sku, list, cost, salvage, stock, bodega
    ("cola",     2.60, 0.70, 0.10, 12, 2.24),
    ("water",    0.85, 0.30, 0.05, 12, 1.55),
    ("chips",    1.55, 0.60, 0.10, 10, 1.90),
    ("energy",   2.55, 1.10, 0.15,  8, 3.22),
    ("sandwich", 5.15, 2.20, 0.30,  6, 5.58),
]


def toy_merchant(merchant_id: str = "toy-00", *, price_mult: float = 1.0,
                 stock_mult: float = 1.0, near_expiry_skus=()) -> ToyMerchant:
    listings = {}
    for sku, lp, cost, salv, stock, bod in _TOY_SPEC:
        listings[sku] = ToyListing(
            sku=sku, list_price=round(lp * price_mult, 2), unit_cost=cost,
            salvage=salv, stock=max(1, int(stock * stock_mult)),
            bodega_price=bod, near_expiry=(sku in near_expiry_skus))
    return ToyMerchant(merchant_id, listings)


def draw_toy_population(master_seed: int, n: int) -> list[BuyerDraw]:
    """A lognormal buyer population over the toy catalog, no vend dependency."""
    import numpy as np
    from buyer.values import QTY_CAP  # noqa: F401 (documents the value model)
    skus = [s for s, *_ in _TOY_SPEC]
    mus = {s: lp / 1.3 for s, lp, *_ in _TOY_SPEC}  # true value ~ below list
    pop = []
    for k in range(n):
        rng = np.random.default_rng((master_seed * 1_000_003 + k) & 0x7FFFFFFF)
        wtp = {s: float(rng.lognormal(np.log(mus[s]), 0.30)) for s in skus}
        pop.append(BuyerDraw(uid=(master_seed << 20) | k,
                             wtp=wtp, walk_cost=float(rng.uniform(0.5, 2.0))))
    return pop
