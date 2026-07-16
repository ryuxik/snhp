"""MERIDIAN test suite (SPEC "test_meridian.py").

Covers: protocol state-machine rules; settlement/delivery conservation of money
and goods; determinism (same seed -> identical ledger hash); the deceptive
supplier profits ONLY through the documented pay-on-accept channel; oracle
sanity (bundled optimum >= price-only always); ledger tamper detection.

Fast: market-level tests use a small market unless a magnitude claim needs the
audit regime. Run: `python -m pytest meridian/test_meridian.py -q`.
"""

from __future__ import annotations

import math

import pytest

from meridian import ledger as L
from meridian.agents import (buyer_gross_value, joint_surplus, supplier_cost,
                             unit_realized_value)
from meridian.audit import nash_bundle, oracle_best
from meridian.market import Market, MarketConfig
from meridian.protocol import (Counter, ProtocolError, Quote, RFQ, Session,
                               State)


def _rfq(qty=10, need_by=3):
    return RFQ(1, "buy000", "item0", qty, need_by, 0, 100.0, 2.0, 1e9)


def _quote(price=1000.0, qty=10, ship_date=3):
    return Quote(1, 1, "sup000", price, qty, ship_date, 100)


def _session():
    return Session(_quote(), _rfq())


# ---------------------------------------------------------------------------
# Protocol state machine
# ---------------------------------------------------------------------------
def test_counter_is_price_only_structurally():
    """A Counter has a price and no qty/ship_date field: a bundle counter is
    inexpressible in MPX (A1's mechanism)."""
    c = Counter(900.0)
    assert hasattr(c, "price")
    assert not hasattr(c, "qty") and not hasattr(c, "ship_date")


def test_qty_and_ship_date_are_immutable_across_a_session():
    s = _session()
    q0, d0 = s.quote.qty, s.quote.ship_date
    s.counter(Counter(900.0))
    s.concede(950.0)
    s.counter(Counter(920.0))
    assert s.quote.qty == q0 and s.quote.ship_date == d0  # never negotiable


def test_counter_cap_enforced():
    """MPX allows <=3 buyer counters; the 4th raises."""
    s = _session()
    for _ in range(3):
        s.counter(Counter(900.0))
    with pytest.raises(ProtocolError):
        s.counter(Counter(900.0))


def test_happy_path_transitions():
    s = _session()
    s.counter(Counter(900.0))
    s.accept()
    assert s.state == State.ACCEPTED and s.agreed_price == 900.0
    s.settle(); s.deliver(); s.rate()
    assert s.state == State.RATED


def test_illegal_transitions_raise():
    s = _session()
    with pytest.raises(ProtocolError):
        s.settle()                 # settle before accept
    s.accept()
    with pytest.raises(ProtocolError):
        s.deliver()                # deliver before settle
    s.settle()
    with pytest.raises(ProtocolError):
        s.rate()                   # rate before deliver
    with pytest.raises(ProtocolError):
        s.counter(Counter(1.0))    # counter after settled


def test_concede_only_after_counter():
    s = _session()
    with pytest.raises(ProtocolError):
        s.concede(950.0)           # nothing to concede against yet


# ---------------------------------------------------------------------------
# Economic primitives
# ---------------------------------------------------------------------------
def test_unit_value_floors_at_zero():
    assert unit_realized_value(100.0, 10.0, 5) == 50.0
    assert unit_realized_value(100.0, 30.0, 5) == 0.0   # never negative


def test_expedite_raises_cost_as_date_pulled_in():
    slow = supplier_cost(20, 5, 40, 0.05, 5, 3.0)   # natural lead = 4, no expedite
    fast = supplier_cost(20, 1, 40, 0.05, 5, 3.0)   # pulled in 3 ticks
    assert fast > slow


def test_excess_units_are_near_worthless():
    """A double-buy (delivery beyond the need) has ~0 marginal value (A3)."""
    on_need = buyer_gross_value(10, 10, 100.0, 0.0, 0)
    over = buyer_gross_value(20, 10, 100.0, 0.0, 0, residual_frac=0.0)
    assert on_need == pytest.approx(1000.0)
    assert over == pytest.approx(1000.0)   # the extra 10 units add nothing


# ---------------------------------------------------------------------------
# Market: conservation
# ---------------------------------------------------------------------------
def _small(**over):
    base = dict(n_buyers=8, n_suppliers=20, n_brokers=0, ticks=300)
    return MarketConfig(**{**base, **over})


def test_money_is_conserved():
    m = Market(_small(), seed=7)
    m.run()
    assert abs(sum(m.cash.values())) < 1e-6   # closed system


def test_money_conserved_with_brokers_and_deception():
    m = Market(_small(n_brokers=4, chain_demand=True, deceptive_fraction=0.25),
               seed=7)
    m.run()
    assert abs(sum(m.cash.values())) < 1e-6


def test_goods_never_exceed_commitment():
    res = Market(_small(deceptive_fraction=0.25), seed=7).run()
    for t in res.trades:
        assert t.realized_qty <= t.promised_qty + 1e-9   # no phantom goods


def test_honest_supplier_delivers_in_full():
    res = Market(_small(deceptive_fraction=0.0), seed=7).run()
    for t in res.trades:
        if not t.is_broker:
            assert t.realized_qty == pytest.approx(t.promised_qty)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_same_seed_identical_ledger_hash():
    cfg = _small(deceptive_fraction=0.1, chain_demand=True, n_brokers=4)
    h1 = Market(cfg, seed=11).run().ledger.head_hash()
    h2 = Market(cfg, seed=11).run().ledger.head_hash()
    assert h1 == h2


def test_different_seed_different_ledger_hash():
    cfg = _small()
    h1 = Market(cfg, seed=11).run().ledger.head_hash()
    h2 = Market(cfg, seed=12).run().ledger.head_hash()
    assert h1 != h2


# ---------------------------------------------------------------------------
# Deceptive supplier profits ONLY through the documented channel
# ---------------------------------------------------------------------------
_A2 = dict(n_buyers=20, n_suppliers=60, n_brokers=0, ticks=800,
           need_by_lo=6, need_by_hi=16, urgency_lo=0.5, urgency_hi=3.0)


def test_under_delivery_is_the_only_profit_channel():
    """Population-controlled: SAME seed (same suppliers, same deceptive set),
    toggle only the under-delivery channel. With bad_prob=0 the liars behave
    honestly; turning the channel on is the ONLY thing that lifts their margin.
    (Cross-group honest-vs-liar comparison is confounded by the random cost
    draws of the two supplier subsets, so we compare the liar group to itself.)"""
    off = Market(MarketConfig(**_A2, deceptive_fraction=0.25,
                              deceptive_bad_prob=0.0), seed=3).run().metrics
    on = Market(MarketConfig(**_A2, deceptive_fraction=0.25,
                             deceptive_bad_prob=0.5), seed=3).run().metrics
    assert on["deceptive_margin_per_trade"] > 1.3 * off["deceptive_margin_per_trade"]


def test_liar_edge_vanishes_under_attestation_escrow():
    """With attestation-gated escrow the liar is paid only for what it ships;
    the pay-on-accept windfall is the ONLY channel, so its edge collapses."""
    off = Market(MarketConfig(**_A2, deceptive_fraction=0.25),
                 seed=3).run().metrics
    on = Market(MarketConfig(**_A2, deceptive_fraction=0.25, attestation=True),
                seed=3).run().metrics
    assert off["deceptive_margin_per_trade"] > 1.5 * off["honest_margin_per_trade"]
    assert on["deceptive_margin_per_trade"] < 1.25 * on["honest_margin_per_trade"]


def test_attestation_does_not_penalize_honest_suppliers():
    off = Market(MarketConfig(**_A2, deceptive_fraction=0.25),
                 seed=3).run().metrics
    on = Market(MarketConfig(**_A2, deceptive_fraction=0.25, attestation=True),
                seed=3).run().metrics
    assert on["honest_margin_per_trade"] == pytest.approx(
        off["honest_margin_per_trade"], rel=0.05)


# ---------------------------------------------------------------------------
# A3 stale buyer
# ---------------------------------------------------------------------------
def test_stale_buyer_produces_harmful_accepts():
    m0 = Market(_small(buyer_lag=0), seed=7).run().metrics
    mk = Market(_small(buyer_lag=30), seed=7).run().metrics
    assert m0["harmful_per_100"] == pytest.approx(0.0, abs=1e-9)
    assert mk["harmful_per_100"] > m0["harmful_per_100"]


# ---------------------------------------------------------------------------
# Oracle sanity (A1) + nash IR (A5-i)
# ---------------------------------------------------------------------------
_A1 = dict(n_buyers=12, n_suppliers=30, n_brokers=0, ticks=400,
           need_by_lo=1, need_by_hi=4, urgency_lo=3.0, urgency_hi=9.0,
           value_lo=65.0, value_hi=110.0, cap_lo=2, cap_hi=5, collect_rfqs=True)


def test_oracle_dominates_price_only_on_every_rfq():
    res = Market(MarketConfig(**_A1), seed=5).run()
    for rec in res.rfqs:
        J, _, _ = oracle_best(rec)
        assert J >= rec.price_only_joint - 1e-6   # bundle >= price-only, always


def test_nash_bundle_is_individually_rational():
    res = Market(MarketConfig(**_A1), seed=5).run()
    checked = 0
    for rec in res.rfqs[:200]:
        J, _, _ = oracle_best(rec)
        if J <= 0:
            continue
        joint, q, d, p = nash_bundle(rec)
        lateness = max(0, d - rec.need_by)
        u_b = buyer_gross_value(q, rec.need_qty, rec.unit_value, rec.urgency,
                                lateness) - p
        u_s = p - supplier_cost(q, d, rec.c0, rec.c1, rec.cap, rec.expedite)
        assert u_b >= -1e-6 and u_s >= -1e-6   # both parties gain (IR)
        checked += 1
    assert checked > 0


def test_bundling_recovers_most_of_the_gap():
    res = Market(MarketConfig(**_A1), seed=5).run()
    s_oracle = s_po = s_nash = 0.0
    for rec in res.rfqs:
        J, _, _ = oracle_best(rec)
        Jn, _, _, _ = nash_bundle(rec)
        s_oracle += J
        s_po += rec.price_only_joint
        s_nash += max(0.0, Jn)
    assert s_oracle > s_po                      # there is a real gap
    assert s_nash >= 0.9 * s_oracle             # nash recovers most of it


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def test_clean_chain_verifies():
    res = Market(_small(), seed=7).run()
    chk = L.verify_chain(res.ledger)
    assert chk.ok and chk.length == len(res.ledger)


def test_tamper_is_detected():
    res = Market(_small(), seed=7).run()
    led = res.ledger
    assert len(led.records) > 10
    rec = led.records[8]
    led.records[8] = L.Record(rec.seq, rec.tick, rec.type,
                              {**rec.data, "injected": True}, rec.prev_hash,
                              rec.hash)
    chk = L.verify_chain(led)
    assert not chk.ok and chk.error_seq == rec.seq


def test_reorder_is_detected():
    res = Market(_small(), seed=7).run()
    led = res.ledger
    led.records[5], led.records[6] = led.records[6], led.records[5]
    assert not L.verify_chain(led).ok


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
