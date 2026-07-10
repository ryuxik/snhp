"""The five arms behind one small interface.

  sticker/1     — the cultural control: tag price, take it or leave it, with
                  the LES gut ritual (−20% every 30 unsold days). No engine.
  hazard/1      — ablation for H-V3: the ENGINE'S learned per-item hazard
                  drives computed markdowns (weekly re-solve), discount-only;
                  offers don't exist.
  offer/1       — make-an-offer (FIXED, post-reg FIX B): asks stay at tag;
                  the engine accepts/counters/declines against the
                  event-consistent waiting value, with the counter's huff
                  externality priced from a LEARNED shading/huff model.
  retag/1       — post-reg FIX A: the hazard machinery may re-tag UP as well
                  as down (posted, visible, at most weekly per item), toward
                  the posterior-optimal price. No offers (the retag ablation).
  retag+offer/1 — retag/1's board plus offer/1's flow; the offer ceiling is
                  the CURRENT tag.

Every arm owns its OWN engine state (regime-consistent learning, vend's
rule: the hazard you learn is the hazard of the world your mechanism makes).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from vintage.calibration import (F_EWMA, F_INIT, MARKDOWN_AGE,
                                 MARKDOWN_FACTOR, REPRICE_EVERY, RETAG_EVERY)
from vintage.engine import (Beliefs, ShadingLearner, decide_offer,
                            solve_price, solve_price_free)
from vintage.world import Item


@dataclass
class StickerPolicy:
    """The control. Stateless: price is a pure function of (tag, age)."""
    policy_id: str = "sticker/1"
    uses_engine: bool = False
    uses_offers: bool = False

    def admit(self, item: Item) -> None:
        pass

    def day_start(self, day: int, inventory: dict[int, Item]) -> None:
        pass

    def price(self, item: Item, day: int) -> float:
        age = day - item.arrival_day
        return round(item.tag * MARKDOWN_FACTOR ** (age // MARKDOWN_AGE), 2)

    def on_sale(self, uid: int, price: float, browsers: int,
                ask: float | None = None) -> None:
        pass

    def end_of_day(self, day: int, inventory: dict[int, Item],
                   browsers: int) -> None:
        pass


@dataclass
class HazardPolicy:
    """Computed markdowns, no offers (the H-V3 ablation). Weekly per-item
    re-solve on the learned posterior; markdowns are permanent (never
    raise), never above tag (discount-only), floored in the solve."""
    policy_id: str = "hazard/1"
    uses_engine: bool = True
    uses_offers: bool = False
    beliefs: Beliefs = field(default_factory=Beliefs)
    prices: dict[int, float] = field(default_factory=dict)

    def admit(self, item: Item) -> None:
        self.beliefs.admit(item)
        self.prices[item.uid] = item.tag

    def day_start(self, day: int, inventory: dict[int, Item]) -> None:
        for uid, item in inventory.items():
            age = day - item.arrival_day
            if age > 0 and age % REPRICE_EVERY == 0:
                self.prices[uid] = solve_price(self.beliefs, uid,
                                               self.prices[uid], item.tag)

    def price(self, item: Item, day: int) -> float:
        return self.prices[item.uid]

    def on_sale(self, uid: int, price: float, browsers: int,
                ask: float | None = None) -> None:
        self.beliefs.sale(uid, price, browsers)
        del self.prices[uid]

    def end_of_day(self, day: int, inventory: dict[int, Item],
                   browsers: int) -> None:
        for uid in inventory:
            self.beliefs.survival(uid, self.prices[uid], browsers)


@dataclass
class RetagPolicy:
    """FIX A (post-registration, CRITICAL-ANALYSIS §4b): the hazard/1
    machinery with the discount-only shackle removed. The weekly per-item
    re-solve may move the POSTED, VISIBLE price UP as well as DOWN, toward
    the posterior-optimal posted price, bounded by the item's own appeal
    posterior. First solve at ADMISSION — an under-tagged gem sells the
    same day it hits the rack, so a retag that waits a week protects
    nothing — then at most weekly per item (RETAG_EVERY). No offers here:
    this is the retag ablation."""
    policy_id: str = "retag/1"
    uses_engine: bool = True
    uses_offers: bool = False
    beliefs: Beliefs = field(default_factory=Beliefs)
    prices: dict[int, float] = field(default_factory=dict)

    def admit(self, item: Item) -> None:
        self.beliefs.admit(item)
        self.prices[item.uid] = float(item.tag)

    def day_start(self, day: int, inventory: dict[int, Item]) -> None:
        for uid, item in inventory.items():
            age = day - item.arrival_day
            if age % RETAG_EVERY == 0:               # includes age 0
                self.prices[uid] = solve_price_free(self.beliefs, uid,
                                                    item.tag)

    def price(self, item: Item, day: int) -> float:
        return self.prices[item.uid]

    def on_sale(self, uid: int, price: float, browsers: int,
                ask: float | None = None) -> None:
        self.beliefs.sale(uid, price, browsers)
        del self.prices[uid]

    def end_of_day(self, day: int, inventory: dict[int, Item],
                   browsers: int) -> None:
        for uid in inventory:
            self.beliefs.survival(uid, self.prices[uid], browsers)


@dataclass
class OfferPolicy:
    """Make-an-offer (FIXED, post-reg FIX B). The ask never moves (the offer
    flow IS the markdown channel — flagged in results); the engine's waiting
    value assumes future settlement at f̂ x ask, where f̂ is the EWMA of
    realized (price / ask) over THIS arm's own sales — the learner may not
    assume a sticker world its own mechanism abolished. The counter round
    runs against a LEARNED shading/huff/fallback model (ShadingLearner):
    counters are charged the huff externality ĥ x F̂, and DECLINE exists."""
    policy_id: str = "offer/1"
    uses_engine: bool = True
    uses_offers: bool = True
    beliefs: Beliefs = field(default_factory=Beliefs)
    learner: ShadingLearner = field(default_factory=ShadingLearner)
    f_hat: float = F_INIT
    _day_fracs: list[float] = field(default_factory=list)

    def admit(self, item: Item) -> None:
        self.beliefs.admit(item)

    def day_start(self, day: int, inventory: dict[int, Item]) -> None:
        pass

    def price(self, item: Item, day: int) -> float:
        return item.tag                      # browsers see tags, always

    def wait_value(self, item: Item) -> float:
        return self.beliefs.continuation(item.uid, self.f_hat * item.tag)

    def decide(self, offer: float, item: Item) -> tuple[str, float]:
        return decide_offer(offer, item.tag, item.tag, self.wait_value(item),
                            self.learner)

    def observe_counter(self, offer: float, counter: float,
                        outcome: str) -> None:
        self.learner.observe_counter(offer, counter, outcome)

    def observe_continuation(self, value: float) -> None:
        self.learner.observe_continuation(value)

    def on_sale(self, uid: int, price: float, browsers: int,
                ask: float | None = None) -> None:
        self.beliefs.sale(uid, price, browsers)
        if ask:
            self._day_fracs.append(price / ask)

    def _roll_fhat(self) -> None:
        if self._day_fracs:
            obs = sum(self._day_fracs) / len(self._day_fracs)
            self.f_hat = (1 - F_EWMA) * self.f_hat + F_EWMA * obs
            self._day_fracs = []

    def end_of_day(self, day: int, inventory: dict[int, Item],
                   browsers: int) -> None:
        # survival evidence at the EFFECTIVE price: in this regime a
        # connection buys via the offer flow around f̂ x ask, so surviving a
        # day is evidence against appeal at that level, not at the tag
        for uid, item in inventory.items():
            self.beliefs.survival(uid, self.f_hat * item.tag, browsers)
        self._roll_fhat()


@dataclass
class RetagOfferPolicy(OfferPolicy):
    """retag/1's board plus offer/1's flow (FIX A + FIX B). The offer
    ceiling is the CURRENT tag: offers cap at the posted (re-tagged) price
    and counters live under it; the buffer scales with the current tag.
    One engine state serves both levers — one economics, two uses."""
    policy_id: str = "retag+offer/1"
    prices: dict[int, float] = field(default_factory=dict)

    def admit(self, item: Item) -> None:
        super().admit(item)
        self.prices[item.uid] = float(item.tag)

    def day_start(self, day: int, inventory: dict[int, Item]) -> None:
        for uid, item in inventory.items():
            age = day - item.arrival_day
            if age % RETAG_EVERY == 0:               # includes age 0
                self.prices[uid] = solve_price_free(self.beliefs, uid,
                                                    item.tag)

    def price(self, item: Item, day: int) -> float:
        return self.prices[item.uid]

    def wait_value(self, item: Item) -> float:
        return self.beliefs.continuation(item.uid,
                                         self.f_hat * self.prices[item.uid])

    def decide(self, offer: float, item: Item) -> tuple[str, float]:
        ask = self.prices[item.uid]
        return decide_offer(offer, ask, ask, self.wait_value(item),
                            self.learner)

    def on_sale(self, uid: int, price: float, browsers: int,
                ask: float | None = None) -> None:
        super().on_sale(uid, price, browsers, ask)
        del self.prices[uid]

    def end_of_day(self, day: int, inventory: dict[int, Item],
                   browsers: int) -> None:
        for uid in inventory:
            self.beliefs.survival(uid, self.f_hat * self.prices[uid],
                                  browsers)
        self._roll_fhat()


ARMS = {
    "sticker": StickerPolicy,
    "offer": OfferPolicy,
    "hazard": HazardPolicy,
    "retag": RetagPolicy,
    "retag+offer": RetagOfferPolicy,
}
