"""VINTAGE tests: pairing is real, determinism holds, one-of-one is
conserved, and the engine's decisions come from the right drivers —
the accept floor, the counter bounds, and censoring-aware learning.
Post-reg (CRITICAL-ANALYSIS §4): the bidirectional retag is bounded by the
posterior and weekly per item; the shading learner is censoring-aware and
counter-aggression falls in learned huff risk."""
import math

import pytest

from vintage.calibration import (BELIEF_GRID_Z, BELIEF_SIGMA, BUFFER_ABS,
                                 BUFFER_FRAC, MARKDOWN_FACTOR, P_HUFF,
                                 PRICE_FLOOR_FRAC, RHO_PRIOR_MEAN)
from vintage.core import substream
from vintage.engine import (Beliefs, ShadingLearner, buffer, counter_response,
                            decide_offer, solve_price, solve_price_free)
from vintage.policies import OfferPolicy, RetagPolicy, StickerPolicy
from vintage.run import item_class, run_experiment, run_store, visit_offer
from vintage.world import (Browser, Item, PairDraws, VintageConfig,
                           browsers_for_day, items_for_day)


def _item(uid=1, cost=20.0, appeal=50.0, tag=100.0, day=0):
    return Item(uid=uid, cost=cost, appeal=appeal, tag=tag, arrival_day=day)


# ── pairing & determinism ────────────────────────────────────────────────

def test_item_and_browser_streams_are_policy_independent():
    """Streams depend only on (seed, day, k) — never on anything an arm did."""
    a = items_for_day(11, 4)
    b = items_for_day(11, 4)
    assert a == b
    assert browsers_for_day(11, 4) == browsers_for_day(11, 4)


def test_sigma_tag_moves_only_the_tag():
    """Nested cells: cost and appeal are identical across tag-noise levels;
    only the owner's guess changes. Shading moves only the browsers."""
    lo = items_for_day(11, 4, VintageConfig(sigma_tag=0.3))
    hi = items_for_day(11, 4, VintageConfig(sigma_tag=0.6))
    assert [(i.cost, i.appeal) for i in lo] == [(i.cost, i.appeal) for i in hi]
    assert any(x.tag != y.tag for x, y in zip(lo, hi))
    b_lo = browsers_for_day(11, 4, VintageConfig(shading=0.75))
    b_hi = browsers_for_day(11, 4, VintageConfig(shading=0.90))
    assert all(abs((x.shading - 0.75) - (y.shading - 0.90)) < 1e-12
               for x, y in zip(b_lo, b_hi))


def test_pair_draws_key_on_identity_alone():
    """The same person feels the same way about the same piece in every
    arm: draws are memo-stable and reproducible across fresh caches."""
    it = items_for_day(11, 0)[0]
    br = browsers_for_day(11, 0)[0]
    assert PairDraws().get(br, it) == PairDraws().get(br, it)


def test_experiment_is_deterministic():
    r1 = run_experiment(["sticker", "offer"], days=6, reps=1, seed=13)
    r2 = run_experiment(["sticker", "offer"], days=6, reps=1, seed=13)
    assert r1 == r2


# ── one-of-one conservation ──────────────────────────────────────────────

def test_one_of_one_conservation():
    """An item sells AT MOST once; sold + ending inventory = sourced,
    and a sold item never reappears on the rack."""
    for arm in ("sticker", "offer", "hazard", "retag", "retag+offer"):
        from vintage.policies import ARMS
        run = run_store(ARMS[arm](), VintageConfig(sigma_tag=0.6),
                        master_seed=5, days=25, cache=PairDraws())
        sold = [u for u, r in run["ledger"].items()
                if r["sold_day"] is not None]
        assert len(sold) == len(set(sold))
        assert set(sold).isdisjoint(run["inventory"])
        assert len(sold) + len(run["inventory"]) == len(run["ledger"])
        assert sum(d["units_sold"] for d in run["per_day"]) == len(sold)


# ── the engine: accept floor, counters, learning ─────────────────────────

def test_buffer_floor():
    assert buffer(10.0) == BUFFER_ABS            # $2 beats 8% of a $10 tag
    assert buffer(100.0) == pytest.approx(BUFFER_FRAC * 100.0)


def test_offer_accept_dominance():
    """The engine NEVER accepts below its disagreement value plus the
    buffer — swept across waiting values, asks, and offers. With a fresh
    learner F̂ = 0, so a counter (EV ≥ v_wait) weakly beats declining and
    ties go to the counter: the unlearned engine never declines."""
    for v in (0.0, 5.0, 20.0, 40.0, 55.0, 80.0):
        for offer in (1.0, 10.0, 25.0, 45.0, 60.0, 79.0):
            for ask in (80.0, 120.0):
                action, price = decide_offer(offer, ask, ask, v)
                if action == "accept":
                    assert price == offer
                    assert offer >= v + buffer(ask) - 1e-9
                else:
                    assert action == "counter"
                    assert offer < price <= ask + 1e-9


def test_accept_floor_holds_with_a_learned_model():
    """The floor invariant survives FIX B: whatever the learner has seen —
    heavy huffs, rich fallbacks, extreme shading evidence — the engine
    never accepts below v_wait + buffer."""
    scenarios = []
    hot = ShadingLearner()
    for _ in range(60):
        hot.observe_counter(70.0, 95.0, "huff")
        hot.observe_continuation(15.0)
    cold = ShadingLearner()
    for _ in range(60):
        cold.observe_counter(70.0, 80.0, "accept")
    scenarios = [hot, cold, ShadingLearner()]
    for learner in scenarios:
        for v in (0.0, 20.0, 55.0, 80.0):
            for offer in (1.0, 25.0, 45.0, 60.0, 79.0):
                action, price = decide_offer(offer, 80.0, 80.0, v, learner)
                if action == "accept":
                    assert offer >= v + buffer(80.0) - 1e-9
                elif action == "counter":
                    assert offer < price <= 80.0 + 1e-9
                else:
                    assert action == "decline"


def test_counter_logic():
    """Counters live in (offer, ask], sit at/above the floor when one is
    feasible, and go FIRM (counter = ask) when waiting beats any discount."""
    action, price = decide_offer(50.0, 100.0, 100.0, 60.0)
    assert action == "counter" and 60.0 + buffer(100.0) <= price <= 100.0
    # waiting value so high no discount clears the floor -> firm at ask
    action, price = decide_offer(50.0, 100.0, 100.0, 99.0)
    assert (action, price) == ("counter", 100.0)
    # a believed-hopeless lowball is also met with a firm tag
    action, price = decide_offer(5.0, 100.0, 100.0, 40.0)
    assert action == "counter" and price == 100.0


def test_counter_response_is_tolerance_and_huff():
    assert counter_response(wtp=50.0, counter=45.0, huff_roll=0.9)
    assert not counter_response(wtp=50.0, counter=45.0, huff_roll=P_HUFF / 2)
    assert not counter_response(wtp=40.0, counter=45.0, huff_roll=0.9)


def test_hazard_learner_censoring():
    """Unsold is NOT zero demand. An OVERPRICED survivor contributes almost
    no rate exposure (its sitting says nothing about traffic) and keeps its
    appeal posterior nearly intact; a CHEAP survivor is loud evidence and
    drags its posterior down. The learned rate never hits zero."""
    b_hi, b_lo = Beliefs(), Beliefs()
    hi = _item(uid=1, tag=100.0)
    b_hi.admit(hi)
    b_lo.admit(hi)
    prior_mean = b_hi.appeal_mean(1)
    for _ in range(30):
        b_hi.survival(1, 400.0, 40)      # priced far above any belief
        b_lo.survival(1, 40.0, 40)       # priced under every belief
    assert b_hi.appeal_mean(1) > 0.95 * prior_mean
    assert b_lo.appeal_mean(1) < 0.60 * prior_mean
    assert b_hi.rho == pytest.approx(RHO_PRIOR_MEAN, rel=0.02)  # no exposure
    assert 0 < b_lo.rho < RHO_PRIOR_MEAN                        # much more
    assert b_lo.hazard(1, 40.0) > 0                             # still alive


def test_survival_lowers_the_waiting_value():
    """The event-consistent disagreement: every unsold day at a credible
    price is evidence the piece is over-tagged, so the engine's price to
    beat falls with age — the learned analogue of the gut markdown."""
    b = Beliefs()
    b.admit(_item(uid=1, tag=100.0))
    v0 = b.continuation(1, 100.0)
    for _ in range(15):
        b.survival(1, 100.0, 40)
    assert b.continuation(1, 100.0) < 0.75 * v0
    assert b.continuation(1, 100.0) >= 0.0   # free disposal floors it


def test_markdown_calendar_in_control():
    """sticker/1 is the cultural ritual, exactly: full tag to day 29,
    −20% at 30, −36% at 60 (compounding)."""
    pol = StickerPolicy()
    it = _item(tag=100.0)
    assert pol.price(it, 0) == 100.0
    assert pol.price(it, 29) == 100.0
    assert pol.price(it, 30) == pytest.approx(80.0)
    assert pol.price(it, 59) == pytest.approx(80.0)
    assert pol.price(it, 60) == pytest.approx(100.0 * MARKDOWN_FACTOR ** 2)


def test_computed_markdown_is_discount_only_and_monotone():
    """hazard/1's solve never raises, never exceeds the tag, and marks a
    long-surviving piece down below a fresh one."""
    b = Beliefs()
    b.admit(_item(uid=1, tag=100.0))
    fresh = solve_price(b, 1, 100.0, 100.0)
    assert fresh <= 100.0
    for _ in range(30):
        b.survival(1, 100.0, 40)
    stale = solve_price(b, 1, fresh, 100.0)
    assert stale <= fresh
    assert stale < 100.0
    assert stale >= 0.35 * 100.0 - 1e-9


# ── FIX A: the bidirectional retag (post-registration) ───────────────────

def test_retag_bidirectional_bounded_by_posterior():
    """The free solve moves BOTH directions and never leaves the item's own
    posterior support: a fresh piece (prior centered on the tag, demand-rich
    world) re-tags UP but below the posterior ceiling; a piece that
    survived at a CHEAP price (loud evidence) re-tags DOWN but never below
    the house floor. The censoring rule carries over: surviving at an
    over-belief price is quiet and does NOT trigger a deep markdown."""
    ceiling = 100.0 * math.exp(BELIEF_GRID_Z * BELIEF_SIGMA)
    b = Beliefs()
    b.admit(_item(uid=1, tag=100.0))
    fresh = solve_price_free(b, 1, 100.0)
    assert fresh > 100.0                          # UP: no reference price
    assert fresh <= ceiling + 0.5                 # bounded by the posterior
    b_lo = Beliefs()
    b_lo.admit(_item(uid=2, tag=100.0))
    for _ in range(30):
        b_lo.survival(2, 40.0, 40)                # cheap survivor: loud
    down = solve_price_free(b_lo, 2, 100.0)
    assert down < 100.0                           # DOWN: evidence bites
    assert down >= PRICE_FLOOR_FRAC * 100.0 - 1e-9
    b_hi = Beliefs()
    b_hi.admit(_item(uid=3, tag=100.0))
    for _ in range(30):
        b_hi.survival(3, 400.0, 40)               # overpriced survivor: quiet
    assert solve_price_free(b_hi, 3, 100.0) > 100.0


def test_retag_weekly_cadence():
    """Posted prices move at ADMISSION and then at most every RETAG_EVERY
    days per item — never in between, whatever the evidence says."""
    pol = RetagPolicy()
    it = _item(uid=1, tag=100.0, day=0)
    pol.admit(it)
    inventory = {1: it}
    seen = []
    for day in range(15):
        pol.day_start(day, inventory)
        seen.append(pol.price(it, day))
        pol.end_of_day(day, inventory, browsers=40)   # evidence accrues daily
    assert seen[0] != 100.0                       # the admission-day retag
    assert len(set(seen[0:7])) == 1               # frozen through the week
    assert len(set(seen[7:14])) == 1
    assert seen[7] != seen[0]                     # the weekly re-solve moved
    assert seen[14] != seen[7]


def test_retag_can_sell_above_the_original_tag():
    """FIX A end to end: retag/1 recovers under-tag upside — some sales
    land ABOVE the owner's tag — while nothing ever transacts above the
    posterior ceiling (the current tag is bounded by it)."""
    from vintage.policies import ARMS
    for arm in ("retag", "retag+offer"):
        run = run_store(ARMS[arm](), VintageConfig(sigma_tag=0.6),
                        master_seed=5, days=25, cache=PairDraws())
        sold = [r for r in run["ledger"].values() if r["sold_day"] is not None]
        assert any(r["price"] > r["item"].tag + 1e-9 for r in sold), arm
        cap = math.exp(BELIEF_GRID_Z * BELIEF_SIGMA)
        assert all(r["price"] <= r["item"].tag * cap + 0.5 for r in sold), arm


# ── FIX B: the learned counter round (post-registration) ─────────────────

def test_shading_learner_updates_from_huffs_censoring_aware():
    """A huff moves the learned huff RATE and nothing else — huffing is
    price-blind, so it carries no shading information (the censoring rule).
    Accepted counters raise the believed stick probability; rejects lower
    it."""
    L = ShadingLearner()
    p0_huff, p0_stick = L.p_huff, float(L.p_stick(75.0, [90.0])[0])
    for _ in range(30):
        L.observe_counter(75.0, 90.0, "huff")
    assert L.p_huff > 0.8 > p0_huff               # huff rate learned UP
    assert float(L.p_stick(75.0, [90.0])[0]) == pytest.approx(p0_stick)
    L_acc, L_rej = ShadingLearner(), ShadingLearner()
    for _ in range(30):
        L_acc.observe_counter(75.0, 90.0, "accept")   # s <= 0.833, repeatedly
        L_rej.observe_counter(75.0, 90.0, "reject")   # s > 0.833, repeatedly
    assert float(L_acc.p_stick(75.0, [90.0])[0]) > p0_stick
    assert float(L_rej.p_stick(75.0, [90.0])[0]) < p0_stick


def test_counter_aggression_monotone_in_learned_huff_risk():
    """The pre-registered behavior: counter LESS where huff-cost x
    walk-probability is high. (v3: HUFF_BELIEF moved to 0.58 — Backus et al.
    QJE 2020 — so the PRIOR alone already prices in real huff risk; a fresh
    engine starts cautious rather than learning caution the hard way.) With
    the fallback value F̂ held fixed, rising huff evidence flips the
    below-floor response from counter to DECLINE — monotonically, no
    flip-flops. Above the floor, the fresh/prior-only engine now takes the
    bird in hand (accept) by default — countering a modest offer isn't
    worth a 58%-likely walkout — and only dares to hold out for a counter
    once it LEARNS the population is more forgiving than the prior assumes
    (a run of accepted counters lowers the believed huff rate); that flip
    is monotone too."""
    def learner_huffs(n_huffs):
        L = ShadingLearner()
        for _ in range(40):
            L.observe_continuation(0.5)           # a small but real fallback
        for _ in range(n_huffs):
            L.observe_counter(70.0, 95.0, "huff")
        return L

    acts = [decide_offer(50.0, 100.0, 100.0, 60.0, learner_huffs(n))[0]
            for n in (0, 1, 2, 3, 5, 10, 20, 40, 80)]
    assert acts[0] == "counter"                   # prior huff risk: haggle
    assert acts[-1] == "decline"                  # learned huff risk: don't
    flipped = False
    for a in acts:
        assert a in ("counter", "decline")
        if a == "decline":
            flipped = True
        else:
            assert not flipped                    # monotone: no un-flip

    def learner_accepts(n_accepts):
        L = ShadingLearner()
        for _ in range(40):
            L.observe_continuation(0.5)
        for _ in range(n_accepts):
            L.observe_counter(70.0, 90.0, "accept")   # low huff, high stick
        return L

    # above the floor: the realistic PRIOR alone resolves to bird-in-hand...
    assert decide_offer(70.0, 100.0, 100.0, 60.0, learner_accepts(0))[0] \
        == "accept"
    # ...and only flips to holding out for a counter once the engine has
    # learned this population huffs far less than the 58% prior assumes,
    # monotonically (no un-flip back to accept).
    acts2 = [decide_offer(70.0, 100.0, 100.0, 60.0, learner_accepts(n))[0]
             for n in (0, 1, 2, 3, 5, 10, 20, 40, 80)]
    assert acts2[0] == "accept" and acts2[-1] == "counter"
    flipped2 = False
    for a in acts2:
        assert a in ("accept", "counter")
        if a == "counter":
            flipped2 = True
        else:
            assert not flipped2                   # monotone: no un-flip


def test_decline_keeps_the_browser_no_huff():
    """A decline hands over no number, so it cannot huff: the browser shops
    on and buys their best sticker-beating alternative — but NEVER the
    declined target, even at the ask (no free conversion). The learner
    observes the realized continuation (F̂ rises from zero)."""
    class DecliningPolicy(OfferPolicy):
        def decide(self, offer, item):
            return ("decline", 0.0)

    pol = DecliningPolicy()
    target = _item(uid=1, cost=20.0, appeal=50.0, tag=400.0)
    cheap = _item(uid=2, cost=10.0, appeal=60.0, tag=30.0)
    pol.admit(target)
    pol.admit(cheap)

    class FixedDraws:
        def get(self, b, it):
            #      connect, wtp,  huff_roll (would huff if countered)
            return (True, 450.0 if it.uid == 1 else 55.0, 0.01)

    br = Browser(uid=1, shading=0.8)
    n_conn, sale, flags = visit_offer(br, {1: target, 2: cheap}, pol, 0,
                                      FixedDraws())
    assert flags["decline"] == 1 and flags["huff"] == 0
    assert flags["fallback"] == 1
    assert sale == (2, 30.0, "ask")               # not the target at 400
    assert pol.learner.fallback_value > 0.0       # continuation observed


def test_offer_arm_falls_back_to_the_sticker_board():
    """Never worse UX than the board is ENFORCED: a browser whose target
    negotiation dies (counter above WTP, no huff) still buys their best
    positive-surplus alternative at the ask."""
    from vintage.policies import OfferPolicy

    class FirmPolicy(OfferPolicy):
        def decide(self, offer, item):          # force the counter to fail
            return ("counter", item.tag)

    pol = FirmPolicy()
    target = _item(uid=1, cost=20.0, appeal=50.0, tag=400.0)
    cheap = _item(uid=2, cost=10.0, appeal=60.0, tag=30.0)
    pol.admit(target)
    pol.admit(cheap)

    class FixedDraws:
        def get(self, b, it):
            #      connect, wtp,  huff_roll (never huffs)
            return (True, 200.0 if it.uid == 1 else 55.0, 0.99)

    from vintage.world import Browser
    br = Browser(uid=1, shading=0.8)
    # target = item 1 (optimistic surplus 200-160=40 beats 55-30=25)
    n_conn, sale, flags = visit_offer(br, {1: target, 2: cheap}, pol, 0,
                                      FixedDraws())
    assert n_conn == 2
    assert flags["reject"] == 1 and flags["fallback"] == 1
    assert sale == (2, 30.0, "ask")


def test_sales_never_above_tag_anywhere():
    """Discount-only, end to end: no arm ever transacts above the tag."""
    for arm in ("sticker", "offer", "hazard"):
        from vintage.policies import ARMS
        run = run_store(ARMS[arm](), VintageConfig(sigma_tag=0.6),
                        master_seed=9, days=20, cache=PairDraws())
        for r in run["ledger"].values():
            if r["sold_day"] is not None:
                assert r["price"] <= r["item"].tag + 1e-9


def test_item_class_edges():
    assert item_class(_item(tag=40.0, appeal=50.0)) == "under"   # 40 <= 50/1.2
    assert item_class(_item(tag=50.0, appeal=50.0)) == "fair"
    assert item_class(_item(tag=61.0, appeal=50.0)) == "over"    # >= 1.2x


def test_uids_are_distinct_and_stable():
    a = items_for_day(11, 0) + items_for_day(11, 1)
    uids = [i.uid for i in a]
    assert len(uids) == len(set(uids))
    assert uids[0] == substream(11, "iuid", 0, 0)


# ── v3 recalibration (CALIBRATION-TARGETS.md §2 / #5) ─────────────────────
# One shared 60-day, 4-rep run at a real grid cell (sigma_tag=0.3,
# shading=0.75) backs all three targets below — one ~8s run instead of
# three. sticker/1's time-on-shelf and offer/1's negotiation-thread stats
# are read off the SAME store-life (paired seeds), matching how the full
# arm-table grid is actually run.
@pytest.fixture(scope="module")
def _v3_calibration_run():
    return run_experiment(["sticker", "offer"], days=60, reps=4, seed=20260710,
                          cfg=VintageConfig(sigma_tag=0.3, shading=0.75))


def test_v3_thirty_day_sellthrough_matches_thredup(_v3_calibration_run):
    """ThredUp FY2025 (10-K): ~50% of resale listings sell within 30 days.
    The pre-v3 world sold a fairly-tagged item to ~half its connectors THE
    SAME DAY (median days-to-sale ~0) — flatly contradicted. CONNECT_PROB
    was cut ~53x (calibration.py) to fit sticker/1's 30-day fair-exposure
    cohort share into this band."""
    share = _v3_calibration_run["arms"]["sticker"]["per_rep_means"]["share_sold_30d"]
    assert share is not None
    assert 0.40 <= share <= 0.60


def test_v3_first_offer_ratio_near_ebay_evidence(_v3_calibration_run):
    """Backus et al. (QJE 2020, 88M eBay Best Offer listings): the average
    first offer is ≈60.8% of list. Not forced to an exact match (shading is
    a swept EXPERIMENT variable, {0.75, 0.9}, not a free calibration knob —
    see RESULTS.md) but the emergent ratio (offer/ask over every below-ask
    thread, selection and all) should land in the neighborhood."""
    ratio = _v3_calibration_run["arms"]["offer"]["per_rep_means"]["first_offer_ratio"]
    assert ratio is not None
    assert 0.45 <= ratio <= 0.80


def test_v3_post_counter_decline_near_ebay_evidence(_v3_calibration_run):
    """Backus et al.: buyers decline (walk from) 58% of seller counters —
    P_HUFF moved from 0.25 (labeled "too low" in CALIBRATION-TARGETS.md §2)
    to 0.58. This should land close to the parameter almost by construction
    (the huff roll is independent of the engine's counter strategy), so the
    band is tight."""
    rate = _v3_calibration_run["arms"]["offer"]["per_rep_means"]["decline_after_counter_rate"]
    assert rate is not None
    assert 0.45 <= rate <= 0.70


def test_v3_paired_ci_handles_empty_diffs():
    """core.paired_ci must not NaN out on an empty paired cohort — a real
    possibility now that sales are realistically rare over short windows
    (this broke test_experiment_is_deterministic under v3 until fixed)."""
    from vintage.core import paired_ci
    result = paired_ci([])
    assert result == {"mean": None, "ci95": None, "n": 0}
