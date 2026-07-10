"""The Merchant PROTOCOL — the ONLY surface the buyer's agent talks to.

The coupling rule (binding, from DESIGN.md): `BuyerAgent` depends on this
protocol and nothing else. Each sim gets one adapter:

  * `VendMerchant`  wraps vend.scenario.nash_quote / vend.core.MachineState
                    (read-only import; vend/ is owned by another agent and is
                    NEVER edited here). If a vend refactor breaks the import,
                    the agent still runs against `ToyMerchant`.
  * `ToyMerchant`   a minimal in-package merchant (posted board + a linear
                    Nash-split negotiator over a salvage floor) so every buyer
                    test and every strategy can run with zero vend dependency.

What the agent needs from a merchant, and nothing person-based:
  board()           -> {sku: BoardItem(list_price, stock)}   the sticker option
  outside_prices()  -> {sku: price}                          the ever-present
                        competitor (bodega) the buyer can always walk to
  quote(disclosure, intent) -> Quote | None                  the negotiated deal
  salvage_floor(sku)-> float                                 c_eff at expiry
                        (used by commit/coordinate to price would-spoil stock)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class Disclosure:
    """What the buyer's agent tells a merchant. The disclosure — not the
    buyer's identity — is all a lawful mechanism may price on. Honesty is a
    point in this space; strategic misreports (the liar battery) are others."""
    wtp: dict[str, float]
    walk_cost: float
    attested: bool = False   # verified disclosure (the merchant may trust it)
    reliability: float = 0.0  # portable reputation (Wallet), 0..1

    def digest(self) -> tuple:
        return (tuple(sorted((k, round(v, 4)) for k, v in self.wtp.items())),
                round(self.walk_cost, 4), self.attested, round(self.reliability, 3))


@dataclass(frozen=True)
class Intent:
    """The buyer's ask. `allowed` (None = any SKU) lets the buyer forbid
    substitutes; `forward_qty`/`horizon` carry a credible forward commitment
    (commit / coordinate)."""
    allowed: frozenset[str] | None = None
    forward_qty: int = 0
    horizon: int = 1

    def permits(self, sku: str) -> bool:
        return self.allowed is None or sku in self.allowed


@dataclass(frozen=True)
class BoardItem:
    list_price: float
    stock: int


@dataclass(frozen=True)
class Quote:
    """A negotiated quote as the buyer sees it. Carries the merchant-side
    accounting (d_machine / u_machine) so joint-surplus and the monopsony
    audit can be computed without re-entering the merchant.

    The symmetric buyer-side fields (u_buyer / d_buyer) default to 0.0 and are
    UNUSED on the consumer interface (Vend/Toy merchants never set them, so the
    consumer path stays byte-identical). They exist for the SUPPLY MIRROR: when
    a Merchant's value model is not the consumer's linear-decay bundle_value but
    a newsvendor (a Supplier selling cases to a venue), the adapter carries the
    buyer/venue-side utility on the Quote — the same rationale as u_machine, so
    the procurement agent can grade a deal without re-entering the supplier.
    See wholesale/supply.py (the SupplierMerchant adapter)."""
    merchant_id: str
    sku: str
    qty: int
    unit_price: float
    list_price: float
    why: tuple[str, ...]
    d_machine: float = 0.0    # merchant disagreement margin (sticker counterfactual)
    u_machine: float = 0.0    # merchant margin of THIS outcome
    salvage_floor: float = 0.0
    u_buyer: float = 0.0      # buyer/venue utility of THIS outcome (supply mirror)
    d_buyer: float = 0.0      # buyer/venue disagreement utility (supply mirror)

    @property
    def total(self) -> float:
        return round(self.unit_price * self.qty, 2)

    @property
    def machine_gain(self) -> float:
        """Merchant surplus created over its no-deal counterfactual."""
        return self.u_machine - self.d_machine

    @property
    def buyer_gain(self) -> float:
        """Buyer/venue surplus created over its no-deal event (supply mirror)."""
        return self.u_buyer - self.d_buyer


@runtime_checkable
class Merchant(Protocol):
    merchant_id: str

    def board(self) -> dict[str, BoardItem]: ...
    def outside_prices(self) -> dict[str, float]: ...
    def salvage_floor(self, sku: str) -> float: ...
    def quote(self, disclosure: Disclosure, intent: Intent) -> Quote | None: ...
    def settle(self, quote: Quote) -> None: ...


# ── VendMerchant: the vend adapter (read-only import of vend) ───────────────

class VendMerchant:
    """Wraps one vend MachineState. Constructed via `from_vend(...)` so the
    vend import is localized; if vend is mid-refactor and the import breaks,
    only this constructor fails and the buyer falls back to ToyMerchant."""

    def __init__(self, machine_id: str, state, catalog, *,
                 dow_mult: float = 1.0, mult_hat: float = 1.0,
                 traffic_scale: float = 1.0, attested_only: bool = False):
        self.merchant_id = machine_id
        self._state = state
        self._catalog = catalog
        self._dow_mult = dow_mult
        self._mult_hat = mult_hat
        self._traffic_scale = traffic_scale
        # attested_only mirrors vend's a2a attestation: a merchant that only
        # honors verified disclosures cannot be anchored by a liar.
        self._attested_only = attested_only

    @classmethod
    def from_vend(cls, machine_id: str, cfg=None, *, seed: int = 0,
                  day: int = 0, tick: int = 40, attested_only: bool = False):
        """Build a fresh vend machine at (day, tick). Local import keeps the
        coupling contained."""
        from vend.world import (WorldConfig, build_catalog, fresh_machine,
                                day_state)
        cfg = cfg or WorldConfig()
        catalog = build_catalog(cfg, seed)
        state = fresh_machine(machine_id, catalog, cfg, seed)
        state.day, state.tick = day, tick
        ds = day_state(cfg, seed, day)
        m = cls(machine_id, state, catalog, dow_mult=ds.dow_mult,
                traffic_scale=cfg.traffic_scale, attested_only=attested_only)
        return m

    def board(self) -> dict[str, BoardItem]:
        return {sku: BoardItem(list_price=l.list_price,
                               stock=self._state.stock(sku))
                for sku, l in self._catalog.items()}

    def outside_prices(self) -> dict[str, float]:
        return {sku: l.bodega_price for sku, l in self._catalog.items()}

    def salvage_floor(self, sku: str) -> float:
        from vend.scenario import c_eff
        return c_eff(self._state, sku)

    def quote(self, disclosure: Disclosure, intent: Intent) -> Quote | None:
        from vend.scenario import nash_quote
        # attestation: an attested-only merchant demands a VERIFIED report and
        # refuses to price on an unattested one, so no anchoring exploit is
        # possible (this is vend's a2a-attested semantics, buyer-side).
        if self._attested_only and not disclosure.attested:
            return None
        wtp, walk = disclosure.wtp, disclosure.walk_cost
        allowed = None
        if intent.allowed is not None:
            allowed = lambda o: o.sku in intent.allowed  # noqa: E731
        nq = nash_quote(self._state, wtp, walk, dow_mult=self._dow_mult,
                        mult_hat=self._mult_hat,
                        traffic_scale=self._traffic_scale, allowed=allowed)
        if nq.outcome is None:
            return None
        o = nq.outcome
        return Quote(merchant_id=self.merchant_id, sku=o.sku, qty=o.qty,
                     unit_price=o.unit_price,
                     list_price=self._catalog[o.sku].list_price,
                     why=tuple(nq.why), d_machine=nq.d_machine,
                     u_machine=nq.u_machine, salvage_floor=self.salvage_floor(o.sku))

    def settle(self, quote: Quote) -> None:
        """Decrement stock for an accepted quote. Provided for protocol
        fidelity and used by depleting runners; the shared-state regret study
        (buyer/world.py) deliberately does NOT deplete between paired buyers, so
        it never calls this — every buyer must face the identical board for
        pairing to be exact."""
        self._state.take(quote.sku, quote.qty)


# ── ToyMerchant: the decoupling stand-in (no vend at all) ───────────────────

@dataclass
class ToyListing:
    sku: str
    list_price: float
    unit_cost: float
    salvage: float
    stock: int
    bodega_price: float
    near_expiry: bool = False   # this stock spoils to salvage if unsold


class ToyMerchant:
    """A minimal, self-contained merchant: a posted board plus a Nash-split
    negotiator over a salvage/cost floor. Enough structure for every buyer
    strategy (shop/time/commit/coordinate) to be exercised without vend."""

    def __init__(self, merchant_id: str, listings: dict[str, ToyListing],
                 *, attested_only: bool = False):
        self.merchant_id = merchant_id
        self._l = listings
        self._attested_only = attested_only

    def board(self) -> dict[str, BoardItem]:
        return {s: BoardItem(l.list_price, l.stock) for s, l in self._l.items()}

    def outside_prices(self) -> dict[str, float]:
        return {s: l.bodega_price for s, l in self._l.items()}

    def salvage_floor(self, sku: str) -> float:
        l = self._l[sku]
        return l.salvage if l.near_expiry else l.unit_cost

    def quote(self, disclosure: Disclosure, intent: Intent) -> Quote | None:
        from buyer.values import QTY_CAP, bundle_value
        if self._attested_only and not disclosure.attested:
            return None
        wtp, walk = disclosure.wtp, disclosure.walk_cost
        # buyer disagreement: best of bodega (−walk) and the sticker board.
        d_buyer = _toy_outside(self, wtp, walk)
        best, best_score = None, None
        for sku, l in self._l.items():
            if not intent.permits(sku) or l.stock <= 0:
                continue
            floor = self.salvage_floor(sku)
            lp = l.list_price
            if floor >= lp:
                rungs = [lp]
            else:
                rungs = [round(floor + i * (lp - floor) / 11, 4) for i in range(12)]
            for qty in range(1, min(QTY_CAP, l.stock) + 1):
                # merchant disagreement = margin if the buyer just bought at list
                d_machine = 0.0
                bval = bundle_value(wtp, sku, qty)
                if bval - qty * lp > 0:
                    d_machine = qty * (lp - floor)
                for p in rungs:
                    u_b = bval - qty * p
                    u_m = qty * (p - floor)
                    gb, gm = u_b - d_buyer, u_m - d_machine
                    if gb >= -1e-9 and gm >= -1e-9:
                        score = (gb * gm, gb + gm)
                        if best_score is None or score > best_score:
                            best = (sku, qty, p, d_machine, u_m)
                            best_score = score
        if best is None or (best_score[0] <= 0 and best_score[1] <= 1e-9):
            return None
        sku, qty, p, d_machine, u_m = best
        why = ("negotiated for you", f"{qty} unit{'s' if qty > 1 else ''}",
               f"${self._l[sku].list_price - p:.2f}/unit under list")
        return Quote(merchant_id=self.merchant_id, sku=sku, qty=qty,
                     unit_price=round(p, 2), list_price=self._l[sku].list_price,
                     why=why, d_machine=d_machine, u_machine=u_m,
                     salvage_floor=self.salvage_floor(sku))

    def settle(self, quote: Quote) -> None:
        """Decrement stock for an accepted quote (protocol fidelity; the
        shared-state runs don't deplete — see VendMerchant.settle)."""
        self._l[quote.sku].stock = max(0, self._l[quote.sku].stock - quote.qty)


def _toy_outside(m: "ToyMerchant", wtp: dict[str, float], walk: float) -> float:
    from buyer.values import best_bundle
    _, _, s_bod = best_bundle(wtp, m.outside_prices())
    s_bod = max(0.0, s_bod - walk)
    board = m.board()
    prices = {s: b.list_price for s, b in board.items()}
    stock = {s: b.stock for s, b in board.items()}
    _, _, s_stk = best_bundle(wtp, prices, stock)
    return max(0.0, s_bod, s_stk)
