"""B4 tests: the Wallet's reliability compounds and is portable; commit GROWS
joint surplus, splits it 50/50, and never pushes the merchant below its
participation floor (the monopsony-safety seed for B5)."""
import pytest

from buyer.agent import BuyerAgent
from buyer.strategies import commit_strategy
from buyer.wallet import Wallet
from buyer.world import draw_vend_population, vend_markdown_merchant


def test_wallet_reliability_and_trust_rise():
    w = Wallet(uid=1, attested=True, reliability=0.0)
    tf0 = w.trusted_frac()
    assert tf0 == 0.5                       # attested newcomer starts at 0.5
    prev = tf0
    for _ in range(6):
        w.fulfilled()
        assert w.trusted_frac() >= prev     # monotone up with fulfilled history
        prev = w.trusted_frac()
    assert w.trusted_frac() > 0.9
    # a default pulls it back down
    before = w.reliability
    w.defaulted()
    assert w.reliability < before


def test_unattested_wallet_starts_at_zero_trust():
    w = Wallet(uid=2, attested=False, reliability=0.0)
    assert w.trusted_frac() == 0.0          # no attestation, no record → no bank


def test_commit_grows_pie_and_splits_5050():
    m = vend_markdown_merchant(20260710)
    pop = draw_vend_population(20260710, 300)
    grew = 0
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        w = Wallet(uid=b.uid, attested=True, reliability=0.5)
        cr = commit_strategy(agent, m, p_spoil=0.4, wallet=w)
        if not cr.committed:
            continue
        assert cr.d_joint >= -1e-9                      # growth, never negative
        assert abs(cr.d_buyer - cr.d_merchant) < 1e-9   # Nash 50/50 split
        assert cr.d_merchant >= -1e-9                   # merchant never below floor
        assert cr.var_reduction >= -1e-9                # risk removed, not added
        if cr.d_joint > 0:
            grew += 1
    assert grew > 0


def test_commit_growth_monotone_in_trust():
    m = vend_markdown_merchant(20260710)
    pop = draw_vend_population(20260710, 120)
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        lo = commit_strategy(agent, m, p_spoil=0.4,
                             wallet=Wallet(b.uid, True, 0.0))
        hi = commit_strategy(agent, m, p_spoil=0.4,
                             wallet=Wallet(b.uid, True, 1.0))
        if lo.committed and hi.committed:
            assert hi.d_joint >= lo.d_joint - 1e-9      # more trust → more banked


def test_wallet_portable_across_merchants():
    # a proven wallet earns more at a BRAND-NEW merchant than a fresh one.
    m_b = vend_markdown_merchant(20260710 + 777)
    pop = draw_vend_population(20260710, 200)
    wins = 0
    for b in pop:
        agent = BuyerAgent(b.uid, b.wtp, b.walk_cost)
        proven = Wallet(b.uid, True, 1.0)
        fresh = Wallet(b.uid, True, 0.0)
        cc = commit_strategy(agent, m_b, p_spoil=0.4, wallet=proven)
        cf = commit_strategy(agent, m_b, p_spoil=0.4, wallet=fresh)
        if cc.committed and cf.committed and cc.d_buyer > cf.d_buyer:
            wins += 1
    assert wins > 0
