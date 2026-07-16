"""Paper-fill engine + Treasury (SPEC.md "The honesty protocol", verbatim).

Paper P&L is notorious self-deception, so every rule here was committed in
SPEC.md before any data was seen:
  * BUY is AUCTION-ONLY; max bid committed >=60s before close (timestamp
    enforced); win IFF realized hammer < max_bid; fill at hammer + one eBay
    increment (capped at the committed max — you never pay above your max).
  * Bankroll $2,000; capital LOCKED from commit to resolution; one bid/listing;
    metered compute charged to P&L.
All desk state is RECONSTRUCTED from the ledger — the ledger is the single
source of truth (SPEC: "shows NOTHING that is not derivable from the receipts").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import config, ledger as ledger_mod
from .comps import Comps
from .feed import Listing
from .ledger import Ledger
from .timeutil import epoch, iso, parse_iso


class BidRejected(Exception):
    """A bid the honesty protocol forbids. `reason` is a stable machine tag."""
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class DeskState:
    """Desk state reconstructed from the receipt chain (never held elsewhere)."""
    cash: float = config.BANKROLL_USD
    locked: float = 0.0
    compute_cost: float = 0.0
    open_bids: dict = field(default_factory=dict)     # listing_id -> commit data
    inventory: list = field(default_factory=list)     # won positions (held)
    won: int = 0
    lost: int = 0

    @property
    def available(self) -> float:
        """Unlocked, unspent capital available for a new bid."""
        return self.cash - self.locked


def reconstruct(led: Ledger) -> DeskState:
    """Replay the ledger into a DeskState (SPEC single-source-of-truth)."""
    st = DeskState()
    for rec in led.records():
        d = rec.data
        if rec.type == ledger_mod.EV_BID_COMMIT:
            st.open_bids[d["listing_id"]] = d
            st.locked += float(d["max_bid"])
        elif rec.type == ledger_mod.EV_FILL:
            lid = d["listing_id"]
            commit = st.open_bids.pop(lid, None)
            if commit is not None:
                st.locked -= float(commit["max_bid"])
            if d["outcome"] == "won":
                st.cash -= float(d["win_price"])
                st.inventory.append({
                    "listing_id": lid,
                    "cost_basis": float(d["win_price"]),
                    "comp_key": d.get("comp_key"),
                    "title": d.get("title", ""),
                })
                st.won += 1
            else:
                st.lost += 1
        elif rec.type == ledger_mod.EV_SPEND:
            amt = float(d["amount"])
            st.compute_cost += amt
            st.cash -= amt
    return st


class Treasury:
    """Bankroll, exposure caps, one-bid-per-listing (SPEC swarm: Treasury/risk)."""

    def __init__(self, cfg: config.RuntimeConfig | None = None):
        self.cfg = cfg or config.DEFAULT
        self.max_exposure = config.MAX_EXPOSURE_FRACTION * self.cfg.bankroll

    def check(self, state: DeskState, listing_id: str, max_bid: float) -> None:
        """Raise BidRejected unless this bid respects every capital rule."""
        if listing_id in state.open_bids:
            raise BidRejected("duplicate_listing", "one concurrent bid per listing")
        if max_bid <= 0:
            raise BidRejected("nonpositive_bid", str(max_bid))
        if max_bid > self.max_exposure + 1e-9:
            raise BidRejected("exposure_cap",
                              f"max_bid {max_bid:.2f} > cap {self.max_exposure:.2f}")
        if len(state.open_bids) >= config.MAX_CONCURRENT_LOCKS:
            raise BidRejected("too_many_locks", f">= {config.MAX_CONCURRENT_LOCKS} open")
        if max_bid > state.available + 1e-9:
            raise BidRejected("insufficient_capital",
                              f"need {max_bid:.2f}, available {state.available:.2f}")


class FillEngine:
    """Commits bids and resolves auctions under the honesty protocol."""

    def __init__(self, led: Ledger, comps: Comps | None = None,
                 cfg: config.RuntimeConfig | None = None):
        self.led = led
        self.comps = comps
        self.cfg = cfg or config.DEFAULT
        self.treasury = Treasury(self.cfg)

    def state(self) -> DeskState:
        return reconstruct(self.led)

    # -- BUY: commit --------------------------------------------------------
    def commit_bid(self, listing: Listing, max_bid: float, *,
                   comp_key: str | None, commit_time: datetime,
                   arm: str = "B", fair_value: float | None = None):
        """Commit a max bid (SPEC BUY rule). Enforces auction-only + 60s cutoff.

        Raises BidRejected on any protocol violation. Otherwise writes a
        hash-chained bid_commit receipt and locks capital.
        """
        if not listing.is_auction:
            raise BidRejected("not_auction", "phase-1 fills are auction-only")
        if listing.close_time is None:
            raise BidRejected("no_close_time", "cannot enforce 60s cutoff")

        seconds_before_close = epoch(listing.close_time) - epoch(commit_time)
        if seconds_before_close < config.BID_CUTOFF_SECONDS:
            raise BidRejected(
                "bid_after_cutoff",
                f"{seconds_before_close:.0f}s before close < {config.BID_CUTOFF_SECONDS}s",
            )

        state = self.state()
        self.treasury.check(state, listing.listing_id, max_bid)

        data = {
            "listing_id": listing.listing_id,
            "title": listing.title,
            "max_bid": round(float(max_bid), 2),
            "fair_value": round(float(fair_value), 2) if fair_value is not None else None,
            "comp_key": comp_key,
            "commit_time": iso(commit_time),
            "close_time": iso(listing.close_time),
            "seconds_before_close": round(seconds_before_close, 1),
            "arm": arm,
        }
        return self.led.bid_commit(data)

    # -- BUY: resolve -------------------------------------------------------
    def resolve(self, listing_id: str, hammer: float | None, *,
                resolve_time: datetime, status: str = "SOLD"):
        """Resolve a committed auction to a fill (SPEC BUY rule).

        won IFF status==SOLD and hammer < committed max_bid; win price =
        min(max_bid, hammer + one increment) — capped at the committed max so we
        never pay above what we locked. Writes a fill receipt; unlocks capital.
        """
        state = self.state()
        commit = state.open_bids.get(listing_id)
        if commit is None:
            raise BidRejected("no_open_bid", listing_id)

        max_bid = float(commit["max_bid"])
        won = (status == "SOLD" and hammer is not None and float(hammer) < max_bid)

        if won:
            inc = config.bid_increment(float(hammer))
            win_price = round(min(max_bid, float(hammer) + inc), 2)
            data = {
                "listing_id": listing_id,
                "title": commit.get("title", ""),
                "outcome": "won",
                "hammer": round(float(hammer), 2),
                "increment": inc,
                "win_price": win_price,
                "max_bid": max_bid,
                "comp_key": commit.get("comp_key"),
                "resolve_time": iso(resolve_time),
                "arm": commit.get("arm", "B"),
            }
        else:
            data = {
                "listing_id": listing_id,
                "title": commit.get("title", ""),
                "outcome": "lost",
                "hammer": round(float(hammer), 2) if hammer is not None else None,
                "status": status,
                "max_bid": max_bid,
                "comp_key": commit.get("comp_key"),
                "resolve_time": iso(resolve_time),
                "arm": commit.get("arm", "B"),
            }
        return self.led.fill(data)

    # -- metered compute ----------------------------------------------------
    def meter(self, cost: float, reason: str):
        """Charge metered compute to P&L via a spend receipt (SPEC)."""
        return self.led.spend({"amount": round(float(cost), 6), "reason": reason})


@dataclass(frozen=True)
class PnL:
    """P&L derived ONLY from ledger + comps (SPEC report rule)."""
    bankroll: float
    cash: float
    locked: float
    available: float
    compute_cost: float
    inventory_mark: float
    nav: float
    pnl: float
    roi_pct: float
    won: int
    lost: int
    open_positions: int
    inventory_positions: int


def compute_pnl(led: Ledger, comps: Comps, as_of: datetime | None = None,
                cfg: config.RuntimeConfig | None = None) -> PnL:
    """NAV = cash + marked inventory; P&L = NAV - bankroll.

    Inventory marks come straight from comps.mark() (25th-pct realized, net
    friction, unsold haircut; ZERO under thin comps). Nothing here is invented —
    every input is a receipt or a realized comp.
    """
    cfg = cfg or config.DEFAULT
    state = reconstruct(led)
    inv_mark = 0.0
    for pos in state.inventory:
        key = pos.get("comp_key")
        if key:
            inv_mark += comps.mark(key, as_of).mark
    nav = state.cash + inv_mark
    pnl = nav - cfg.bankroll
    roi = (pnl / cfg.bankroll) * 100.0 if cfg.bankroll else 0.0
    return PnL(
        bankroll=round(cfg.bankroll, 2),
        cash=round(state.cash, 4),
        locked=round(state.locked, 2),
        available=round(state.available, 4),
        compute_cost=round(state.compute_cost, 6),
        inventory_mark=round(inv_mark, 4),
        nav=round(nav, 4),
        pnl=round(pnl, 4),
        roi_pct=round(roi, 4),
        won=state.won,
        lost=state.lost,
        open_positions=len(state.open_bids),
        inventory_positions=len(state.inventory),
    )
