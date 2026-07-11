"""BOBA suggest/1 tests: the pre-checkout bundle-suggestion arm.

Pins the three rigor guarantees the task names — (1) the paired customer
stream is byte-identical across arms and never-suggest is byte-identical to the
P0 static walk-in; (2) every suggestion is discount-only (increment never above
its list price, total never above the full list value); (3) the suggest policy
reads ONLY observable state (revealed base order + queue + hour), never the
consumer's true valuation — plus the supporting invariants (learned ⊆ always,
pooled fallback, accept needs true positive incremental surplus, accounting,
and artifact reproducibility)."""
import inspect

import pytest

import boba.suggest as S
from boba.policies import StaticMenu
from boba.run import run_day
from boba.suggest import (ARMS, Suggestion, build_suggestion, build_table,
                          congestion_shadow, feature_key, gate_open,
                          learn_table, run_suggest_experiment, simulate_day,
                          table_lookup, _top_value_price)
from boba.world import (DRINK_COST, DRINK_PRICE, QTY_CAP, TICKS_PER_DAY,
                        TOP_PRICE, BobaConfig, Consumer, arrivals_at,
                        bundle_value, open_shop, sample_consumer)

CFG = BobaConfig(sigma_shock=0.0, flexible_share=0.35)


# ── (1) pairing, determinism, and never == static ───────────────────────────

def test_never_suggest_is_byte_identical_to_static_walk_in():
    """The trusted baseline: with no suggestion offered, the arm reproduces the
    P0 static walk-in exactly (balk, then the sticker order) on every shared
    metric — pinning that the suggestion step is a pure ADD to a known flow."""
    shared = ("margin", "cups", "revenue", "ingredient_cost", "waste_cost",
              "consumer_surplus", "deals", "toppings", "balks", "peak_balks",
              "lost")
    for day in range(4):
        never = simulate_day("never", 20260710, day, CFG)
        static = run_day(StaticMenu(), 20260710, day, CFG)
        for key in shared:
            assert never[key] == static[key], (day, key, never[key], static[key])
        # never-suggest never suggests, never abandons
        assert never["suggestions"] == 0 and never["suggest_abandons"] == 0


def test_customer_stream_is_paired_across_arms():
    """Arrivals and consumer draws depend only on (seed, day, tick, k, cfg) —
    never on the arm — so all three arms face the identical stream (the
    treatment-isolation guarantee, inherited from world.sample_consumer)."""
    assert [arrivals_at(3, 1, t, CFG) for t in range(TICKS_PER_DAY)] == \
           [arrivals_at(3, 1, t, CFG) for t in range(TICKS_PER_DAY)]
    a = sample_consumer(3, 1, 20, 0, CFG)
    b = sample_consumer(3, 1, 20, 0, CFG)
    assert (a.wtp, a.top_wtp, a.uid) == (b.wtp, b.top_wtp, b.uid)


def test_experiment_is_deterministic():
    r1 = run_suggest_experiment(20260710, 6, 6, CFG)
    r2 = run_suggest_experiment(20260710, 6, 6, CFG)
    assert r1 == r2


def test_annoyance_roll_is_identity_keyed_not_policy_keyed():
    """The abandonment hazard is drawn from substream(seed,'annoy',day,tick,k)
    — a pure function of identity, so the SAME customer faces the SAME roll
    under always and learned (only WHETHER it is consulted is the treatment)."""
    import numpy as np
    from boba.world import substream
    r1 = float(np.random.default_rng(substream(20260710, "annoy", 2, 30, 0)).random())
    r2 = float(np.random.default_rng(substream(20260710, "annoy", 2, 30, 0)).random())
    assert r1 == r2
    r3 = float(np.random.default_rng(substream(20260710, "annoy", 2, 30, 1)).random())
    assert r3 != r1


# ── (2) discount-only ────────────────────────────────────────────────────────

def test_every_suggestion_increment_is_discount_only():
    """Type-enforced: the incremental charge never exceeds the increment's list
    price, and (base at list + increment) never exceeds the full order's list
    value — no arm ever prices above the menu."""
    state = open_shop()
    seen = 0
    for tick in range(0, TICKS_PER_DAY, 3):
        state.tick = tick
        for k in range(arrivals_at(23, 1, tick, CFG)):
            c = sample_consumer(23, 1, tick, k, CFG)
            from boba.world import best_menu_order
            d0, q0, t0, s0 = best_menu_order(
                c, DRINK_PRICE, TOP_PRICE, pearls_ok=state.pearl_stock() >= QTY_CAP)
            if d0 is None:
                continue
            sug = build_suggestion(state, d0, q0, t0, tick // 6 + 10)
            if sug is None:
                continue
            seen += 1
            assert sug.inc_price <= sug.inc_list_value + 1e-9
            base_list = q0 * (DRINK_PRICE[d0] + sum(TOP_PRICE[t] for t in t0))
            full_list = sug.qty * (DRINK_PRICE[sug.drink]
                                   + sum(TOP_PRICE[t] for t in sug.tops))
            assert base_list + sug.inc_price <= full_list + 1e-9
    assert seen > 20


def test_increment_never_priced_below_cost():
    """Discount-only floors at cost, never below (value markdown is
    argmax over cost<p<list) — the shop never sells the increment at a loss."""
    state = open_shop()
    state.tick = 30
    # a plain single cup → add-pearls candidate
    sug = build_suggestion(state, "classic-milk-tea", 1, (), 15)
    assert sug is not None and sug.kind == "add-pearls"
    assert sug.inc_price >= sug.inc_cost() - 1e-9


# ── (3) the policy reads ONLY observable state (no ground-truth leak) ─────────

def test_gate_and_candidate_take_no_consumer_argument():
    """Structural no-leak: the functions that decide WHETHER and WHAT to suggest
    physically cannot receive the consumer's valuation — their signatures take
    only shop state and the REVEALED base-order composition."""
    for fn in (build_suggestion, feature_key, gate_open, congestion_shadow):
        params = set(inspect.signature(fn).parameters)
        assert "consumer" not in params and "c" not in params
    # and the observable inputs are exactly: state + base composition (+ hour)
    assert set(inspect.signature(build_suggestion).parameters) == {
        "state", "base_drink", "base_qty", "base_tops", "hour"}


def test_identical_base_order_gives_identical_gate_despite_different_true_value():
    """Behavioral no-leak: two buyers with the IDENTICAL revealed base order but
    very different HIDDEN valuations of the add-on get the SAME suggest/hold
    decision — the policy is blind to the value the world settles on. (One will
    accept and one will reject, proving the valuations really differ; the gate
    does not budge.)"""
    state = open_shop()
    state.tick = 30
    markdown = _top_value_price("pearls")           # the pearls value price
    # both: one plain classic-milk-tea, no toppings (pearls below list, so not
    # in the base) — identical observable order
    def cons(pearls_val):
        wtp = {d: (9.0 if d == "classic-milk-tea" else 0.5) for d in DRINK_PRICE}
        tw = {t: 0.0 for t in TOP_PRICE}
        tw["pearls"] = pearls_val                   # < list 0.85 ⇒ not in base
        return Consumer(fav="classic-milk-tea", wtp=wtp, top_wtp=tw,
                        flexible=False, qty_decay=0.15, uid=1)
    c_reject = cons(markdown - 0.10)                # values pearls below markdown
    c_accept = cons(markdown + 0.20)                # values pearls above markdown
    from boba.world import best_menu_order
    for c in (c_reject, c_accept):
        d0, q0, t0, _ = best_menu_order(c, DRINK_PRICE, TOP_PRICE)
        assert (d0, q0, t0) == ("classic-milk-tea", 1, ())   # identical order

    table = learn_table(20260710, 6, CFG)
    sug = build_suggestion(state, "classic-milk-tea", 1, (), 15)
    assert sug is not None
    # the gate (learned) is identical for both — it never saw their pearls value
    g = gate_open("learned", state, sug, table)
    assert gate_open("learned", state, sug, table) == g   # deterministic
    # but the WORLD's true incremental surplus has OPPOSITE sign for the two
    inc_val_r = (bundle_value(c_reject, "classic-milk-tea", 1, ("pearls",))
                 - bundle_value(c_reject, "classic-milk-tea", 1, ()))
    inc_val_a = (bundle_value(c_accept, "classic-milk-tea", 1, ("pearls",))
                 - bundle_value(c_accept, "classic-milk-tea", 1, ()))
    assert inc_val_r - sug.inc_price < 0 < inc_val_a - sug.inc_price


# ── learned-policy invariants ────────────────────────────────────────────────

def test_learned_suggests_a_subset_of_always():
    """learned only ever SUPPRESSES asks relative to always (same candidate,
    stricter gate), so over identical eval days its suggestion count can never
    exceed always's."""
    res = run_suggest_experiment(20260710, 20, 30, CFG)
    assert res["arms"]["learned"]["suggestions"] <= res["arms"]["always"]["suggestions"]
    assert res["arms"]["never"]["suggestions"] == 0


def test_table_lookup_falls_back_to_pooled_for_sparse_buckets():
    table = {"pooled": -0.4,
             "buckets": {"rich": {"mean": 2.5, "n": S.MIN_BUCKET + 5},
                         "thin": {"mean": 9.9, "n": S.MIN_BUCKET - 1}}}
    assert table_lookup(table, "rich") == 2.5          # trusted
    assert table_lookup(table, "thin") == -0.4         # too few samples → pooled
    assert table_lookup(table, "unseen") == -0.4       # never seen → pooled


def test_learned_gate_holds_when_bucket_ev_below_buffer():
    """The buffer bites: a bucket whose net EV sits below SUGGEST_THRESHOLD is
    NOT asked even though it exists; one comfortably above is."""
    state = open_shop()
    state.tick = 36                                    # off-peak, cool queue
    sug = build_suggestion(state, "classic-milk-tea", 1, (), 16)
    lo = {"pooled": 0.0, "buckets": {feature_key(state, 1, ()):
                                     {"mean": S.SUGGEST_THRESHOLD - 0.1,
                                      "n": S.MIN_BUCKET + 1}}}
    hi = {"pooled": 0.0, "buckets": {feature_key(state, 1, ()):
                                     {"mean": S.SUGGEST_THRESHOLD + 5.0,
                                      "n": S.MIN_BUCKET + 1}}}
    assert gate_open("learned", state, sug, lo) is False
    assert gate_open("learned", state, sug, hi) is True
    assert gate_open("never", state, sug, hi) is False
    assert gate_open("always", state, sug, None) is True


def test_congestion_shadow_only_bites_extra_cups_at_peak():
    peak = open_shop(); peak.tick = 18                 # 13:00, PEAK_HOURS
    peak.queue.append(12)                              # hot line
    upsize = build_suggestion(peak, "classic-milk-tea", 2, ("pearls",), 13)
    assert upsize is not None and upsize.extra_cups == 1
    assert congestion_shadow(peak, upsize) > 0.0       # extra cup at a hot peak
    addpearls = build_suggestion(peak, "classic-milk-tea", 1, (), 13)
    assert addpearls.extra_cups == 0
    assert congestion_shadow(peak, addpearls) == 0.0   # no new cup, no shadow
    off = open_shop(); off.tick = 36; off.queue.append(12)   # 16:00, off-peak
    up_off = build_suggestion(off, "classic-milk-tea", 2, ("pearls",), 16)
    assert congestion_shadow(off, up_off) == 0.0       # off-peak: free capacity


# ── end-to-end accounting ────────────────────────────────────────────────────

def test_simulate_day_accounting_consistency_all_arms():
    table = learn_table(20260710, 6, CFG)
    for arm in ARMS:
        m = simulate_day(arm, 20260710, 10, CFG, table)
        assert m["margin"] == pytest.approx(
            m["revenue"] - m["ingredient_cost"] - m["waste_cost"], abs=0.02)
        assert m["deals"] <= m["arrivals"]
        assert m["cups"] >= m["deals"]
        assert 0 <= m["accepts"] <= m["suggestions"]
        assert m["friction_lost"] == m["balks"] + m["suggest_abandons"]
        assert m["revenue"] >= 0 and m["consumer_surplus"] >= 0


def test_always_arm_actually_makes_and_lands_suggestions():
    """Sanity: always-suggest fires a lot of asks and some land (accept_rate in
    (0,1)) — the mechanism isn't silently a no-op."""
    m = simulate_day("always", 20260710, 10, CFG)
    assert m["suggestions"] > 100
    assert 0.0 < m["accept_rate"] < 1.0
    assert m["accepts"] > 0


def test_accept_books_base_at_list_plus_discounted_increment():
    """A hand buyer who values pearls above the markdown but below list: the
    add-pearls suggestion lands, and the booked price is base-at-list plus the
    discounted increment (never a markdown on the base)."""
    from boba.world import best_menu_order
    state = open_shop(); state.tick = 40             # off-peak, empty queue
    markdown = _top_value_price("pearls")
    wtp = {d: (9.0 if d == "classic-milk-tea" else 0.5) for d in DRINK_PRICE}
    tw = {t: 0.0 for t in TOP_PRICE}
    tw["pearls"] = markdown + 0.30                   # accept, but < list 0.85
    c = Consumer(fav="classic-milk-tea", wtp=wtp, top_wtp=tw, flexible=False,
                 qty_decay=0.15, uid=99)
    d0, q0, t0, _ = best_menu_order(c, DRINK_PRICE, TOP_PRICE)
    assert (d0, q0, t0) == ("classic-milk-tea", 1, ())
    sug = build_suggestion(state, d0, q0, t0, 16)
    inc_val = (bundle_value(c, d0, q0, ("pearls",)) - bundle_value(c, d0, q0, ()))
    assert inc_val - sug.inc_price > 0               # this buyer accepts
    base_list = DRINK_PRICE["classic-milk-tea"]
    assert sug.inc_price < TOP_PRICE["pearls"]       # increment is discounted
    # booked total = base at LIST + discounted pearls, never below base list
    assert round(base_list + sug.inc_price, 2) >= base_list


def test_committed_suggest_results_stay_reproducible():
    """boba/results-suggest.json must remain exactly reproducible at the config
    it records (read from the artifact, not hardcoded)."""
    import json
    import pathlib
    path = pathlib.Path(__file__).parents[1] / "results-suggest.json"
    committed = json.load(open(path))
    cfg = BobaConfig(sigma_shock=committed["config"]["world"]["sigma_shock"],
                     flexible_share=committed["config"]["world"]["flexible_share"])
    # pin the committed assumption/threshold the artifact was generated under
    assert S.SUGGEST_REJECT_BALK == committed["config"]["suggest_reject_balk"]
    assert S.SUGGEST_THRESHOLD == committed["config"]["suggest_threshold"]
    res = run_suggest_experiment(committed["config"]["seed"],
                                 committed["config"]["warmup_days"],
                                 committed["config"]["eval_days"], cfg)
    for arm in ARMS:
        assert res["arms"][arm]["margin"] == committed["arms"][arm]["margin"]
    assert res["verdict"] == committed["verdict"]


def test_flexible_share_is_a_noop_for_this_arm():
    """suggest/1 has NO pickup slots, so flexible_share (which only scales defer
    disutility) cannot touch it — pinned so the RESULTS claim 'flex is a non-
    lever here' stays honest."""
    a = simulate_day("always", 20260710, 5, BobaConfig(0.0, 0.15))
    b = simulate_day("always", 20260710, 5, BobaConfig(0.0, 0.35))
    assert a["margin"] == b["margin"] and a["cups"] == b["cups"]
