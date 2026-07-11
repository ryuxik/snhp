"""Emit arena/web/boba-trace.json: SIMULATED, paired ship-config deals for the
value-prop demo. Ship config = qty_appetite + min_price_frac=0.6 (max 40% off)
+ quote_lookers gated by attestation. Three hero trades (timing / group /
pearls-now) + the headline numbers + an HONEST, split guarantee.

Honesty (owner critique, 2026-07): this is a paired Monte-Carlo simulation vs
a strong, profit-optimal MODELED menu — NOT a real shop's books. The only
UNCONDITIONAL claim is the price rule (never above the menu, type-enforced).
The margin/net-$ figures are contingent on created surplus being realized
(waste + batch bank immediately; freed-capacity value needs the slot to
refill) and are reported at the SEASON level, which models refill +
cannibalization. Customer surfaces show only price + the never-above-menu
rule; all shop economics live behind the 'For shop owners' panel.
"""
import sys, json
sys.path.insert(0, "/Users/ryuxik/Desktop/snhp")
from boba.world import open_shop, sample_consumer, BobaConfig
from boba.policies import cart_nash

CFG = BobaConfig(flexible_share=0.35)
SHIP = dict(qty_appetite=True, min_price_frac=0.6)
PRETTY = {"classic-milk-tea": "Classic Milk Tea", "fruit-tea": "Fruit Tea",
          "brown-sugar": "Brown Sugar Boba", "matcha-latte": "Matcha Latte"}
TP = {"pearls": "pearls", "pudding": "pudding", "grass-jelly": "grass jelly",
      "cheese-foam": "cheese foam"}


def rec(dl, consumer, lever, shop_line):
    return dict(drink=PRETTY[dl.drink], qty=dl.qty, tops=[TP[t] for t in dl.tops],
                slot_min=dl.slot_ticks * 10, menu=round(dl.list_value, 2),
                pay=round(dl.price, 2), save=round(dl.list_value - dl.price, 2),
                off=round(100 * (dl.list_value - dl.price) / dl.list_value),
                flexible=bool(consumer.flexible), lever=lever,
                shop=shop_line, why=list(dl.why))


heroes = {}

# STATE A — a hot lunch counter (a small standing queue -> live balk risk):
# the levers that pay here are pickup-timing and batch. A +60 slot moves the
# order past the lunch peak (hours 12-13, one barista) to when the afternoon
# barista is on (14:00) — the only window that actually frees peak capacity;
# a +30 stays inside the peak and frees nothing. A group order is one prep run.
busy = open_shop(day=0); busy.tick = 20
for o in (2, 2): busy.queue.append(o)
for k in range(600):
    c = sample_consumer(20260710, 0, busy.tick, k, CFG)
    dl = cart_nash(busy, c, quote_lookers=False, **SHIP)
    if dl is None:
        continue
    off = 100 * (dl.list_value - dl.price) / dl.list_value
    if ("timing" not in heroes and dl.slot_ticks == 6 and dl.qty == 1
            and c.flexible and 20 <= off <= 40):
        heroes["timing"] = rec(dl, c, "You set 'flexible on pickup'",
            "moved the order past the lunch peak to when the afternoon barista is on — frees a peak slot IF a hurry-customer refills it")
    if "group" not in heroes and dl.qty >= 3 and dl.slot_ticks > 0:
        heroes["group"] = rec(dl, c, "You're ordering for the group",
            "one prep run for the whole order — batch savings the shop banks immediately")
    if "timing" in heroes and "group" in heroes:
        break

# STATE B — a calm counter near a tapioca batch's end-of-life (no queue): the
# only lever left is ingredient-steering. The agent steers onto pearls from the
# batch about to expire — a NOW pickup, no waiting; the shop clears stock it
# would have tossed (banked immediately). First clean pearls-only rigid deal.
calm = open_shop(day=0); calm.tick = 20
for k in range(600):
    c = sample_consumer(20260710, 0, calm.tick, k, CFG)
    dl = cart_nash(calm, c, quote_lookers=False, **SHIP)
    if dl is None:
        continue
    if (dl.slot_ticks == 0 and dl.qty <= 2 and dl.tops == ("pearls",)
            and not c.flexible
            and "pearls from the expiring batch" in dl.why
            and (100 * (dl.list_value - dl.price) / dl.list_value) >= 25):
        heroes["now"] = rec(dl, c, "Pearls from the batch about to expire",
            "cleared tapioca it would have tossed at close — waste, banked immediately")
        break

out = {
  "meta": {
    "what": ("A SIMULATED, paired SNHP negotiation at a boba shop: your agent "
             "trades on the things you don't care about (when you pick up, "
             "which topping, how many) for a better price — never above the menu."),
    "seed": 20260710,
    "price_guarantee": "You never pay above the menu — a discount-only rule enforced in the code.",
    "margin_note": ("The shop discounts only against value the deal creates: "
                    "waste it clears and batch savings bank immediately, while "
                    "freed-capacity value is realized only when the freed slot "
                    "refills. Net figures are simulated across a season, which "
                    "models slot refill and cannibalization."),
    "attestation": ("Attestation is a verified signal from your ordering app "
                    "that your flexibility and budget are what you claim — "
                    "issued by the app, it's what stops customers lying to grab "
                    "a discount."),
    "take_rate": "Pricing TBD. The figures shown are gross of any SNHP fee.",
    "basis": ("Simulated, not a real shop's books: paired Monte-Carlo — each "
              "dynamic day run against the same crowd as a strong, profit-"
              "optimal modeled menu (not a strawman), 30 paired days."),
    "reproduce": "boba.policies.cart_nash(..., quote_lookers=<attested>, qty_appetite=True, min_price_frac=0.6)",
  },
  "headline": {
    "attested_per_day": 497, "no_attest_per_day": 253, "worst_case_per_day": 0,
    "consumer_surplus_per_day": 509,
    "note": ("Simulated vs a strong, profit-optimal modeled menu (not a "
             "strawman), 30 paired days. Worst case (everyone lies, no "
             "attestation) = exactly the menu."),
  },
  "heroes": heroes,
}
WT = "/Users/ryuxik/Desktop/snhp/.claude/worktrees/agent-a964572a657ddf5d4"
path = WT + "/arena/web/boba-trace.json"
with open(path, "w") as f:
    json.dump(out, f, indent=1)
print(f"wrote {path}\n")
print(json.dumps({k: (v["drink"], v["qty"], v["slot_min"], v["flexible"],
                      v["pay"], v["menu"], v["off"]) for k, v in heroes.items()}, indent=1))
