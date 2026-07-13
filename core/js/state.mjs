/* state.mjs — ShopState (mirror of core/state.py).
 *
 * The generic shop-side context the cost model reads: a clock, finite
 * inventory, slot capacity, perishable batches, an expiring-option set, and an
 * expected-demand table.  Nothing vertical-specific.
 *
 * Representation choices to mirror Python semantics exactly:
 *   inventory / expected_demand -> plain objects keyed by option id (string)
 *   capacity                    -> Map keyed by slot_ticks (int); may hold
 *                                  -Infinity (a slot the adapter force-drops)
 *   expiring                    -> Set of option ids
 */

export class Batch {
  constructor(servings, expires_tick, key = "") {
    this.servings = servings;
    this.expires_tick = expires_tick;
    this.key = key;
  }
}

export class ShopState {
  constructor({
    tick = 0,
    inventory = {},
    capacity = new Map(),
    batches = [],
    expiring = new Set(),
    expected_demand = {},
    extra = {},
  } = {}) {
    this.tick = tick;
    this.inventory = inventory;
    this.capacity = capacity instanceof Map ? capacity : new Map(Object.entries(capacity).map(([k, v]) => [Number(k), v]));
    this.batches = batches;
    this.expiring = expiring instanceof Set ? expiring : new Set(expiring);
    this.expected_demand = expected_demand;
    this.extra = extra;
  }

  stock(optionId) {
    return Object.prototype.hasOwnProperty.call(this.inventory, optionId)
      ? this.inventory[optionId]
      : 0.0;
  }
}

if (typeof globalThis !== "undefined") {
  globalThis.SNHP_state = { Batch, ShopState };
}
