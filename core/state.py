"""ShopState — the generic shop-side context the cost model reads.

boba.world.ShopState (clock + FIFO queue + tapioca batches) and
vend.core.MachineState (clock + per-SKU lots + par stock) are two concrete
instances of the same idea: a clock, some finite inventory, some capacity,
and some perishable batches. The core cost components (core/cost.py) read
only the generic fields below, so one state type feeds both worlds.

Nothing here is vertical-specific: an adapter (Phase 2/3) projects boba's or
vend's live state onto these fields before quoting.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Batch:
    """A perishable lot: `servings` left, dies at `expires_tick`."""
    servings: int
    expires_tick: int
    key: str = ""            # which option/sku this batch belongs to


@dataclass
class ShopState:
    tick: int = 0
    # option_id -> units on hand (finite stock; read by scarcity_shadow)
    inventory: dict[str, float] = field(default_factory=dict)
    # slot -> units the slot can still absorb (read by fulfillment guards)
    capacity: dict[int, float] = field(default_factory=dict)
    # perishable lots (read by salvage_on_expiry / expiry accounting)
    batches: list[Batch] = field(default_factory=list)
    # option_ids currently priced at salvage (batch expiring in excess).
    # An adapter sets this from the vertical's clearance rule — boba's
    # pearls_expiring_excess, vend's days_to_expiry<=0.
    expiring: set[str] = field(default_factory=set)
    # option_id -> expected rest-of-horizon list-price demand (read by
    # scarcity_shadow: units in EXCESS of this are cheap to move; the rest
    # would have sold at list, so discounting them displaces that sale).
    expected_demand: dict[str, float] = field(default_factory=dict)
    # escape hatch for adapter-specific facts a bespoke cost fn might read
    extra: dict = field(default_factory=dict)

    def stock(self, option_id: str) -> float:
        return self.inventory.get(option_id, 0.0)
