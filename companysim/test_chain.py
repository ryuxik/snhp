"""v35 CO2-S — offline, fixture-only tests for the three-org settlement / hold-up
harness. Zero network (the LLMOrg live path runs only in the real grid,
run_chain.py). These prove the mechanical claims the experiment rests on BEFORE
any spend:

  * the LOAD-BEARING pair: with an IDENTICAL short-forward by the terminal holder,
    upstream is underpaid under SPOT but paid exactly the attested split under
    CLAIM-STACK — the whole thesis in one comparison;
  * chain-formation: a declined middle (or upstream) leg means the chain never
    forms and the buyer's escrow is refunded, not released;
  * the ledger conserves through BOTH settlement paths incl. partial/short
    forwarding and the decline-refund path;
  * leg N's input is leg N-1's output artifact (real sequential threading);
  * the buyer's escrow is released ONLY on delivery;
  * the claim-stack split is attested and enforced (realized == agreed by
    construction), incl. an over-subscribed stack capped to conserve;
  * anti-theater: the installed objective names neither the regime, a decline,
    nor a short-forward;
  * Opus refused at registration.
"""

from __future__ import annotations

import pytest

from companysim import events as ev
from companysim.chain import (CHAIN_PREAMBLE, ChainConfig, ChainRunner,
                              ForwardDecision, LegDecision, LLMOrg, Regime,
                              FixtureOrg, guidance_for_org, mechanics_for)
from companysim.ledger import acct_buyer, acct_escrow, verify_chain
from companysim.tasks_co2s import LIBRARY_BY_ID, PRICE, task_for_seed

SPOT = Regime.SPOT
STACK = Regime.CLAIM_STACK
TASK = task_for_seed(0)   # the temperature-converter deliverable


def _leg(accept=True, artifact="x", share=30.0, note=""):
    return LegDecision(accept=accept, artifact=artifact, share=share, note=note)


def _fwd(amount, note=""):
    return ForwardDecision(forward_amount=amount, note=note)


class RecordingOrg(FixtureOrg):
    """A fixture org that remembers the view it was shown (for artifact-threading
    and view-content assertions)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seen_leg_view = None
        self.seen_forward_view = None

    def leg(self, view):
        self.seen_leg_view = view
        return super().leg(view)

    def forward(self, view):
        self.seen_forward_view = view
        return super().forward(view)


def _orgs(a_leg, b_leg, c_leg, *, c_fwd=None, b_fwd=None, cls=FixtureOrg):
    return {"A": cls("orgA", "A", a_leg, None),
            "B": cls("orgB", "B", b_leg, b_fwd),
            "C": cls("orgC", "C", c_leg, c_fwd)}


def _run(tmp_path, regime, orgs, task=TASK, **kw):
    cfg = ChainConfig(f"{regime.value}_{task.task_id}", regime, task, orgs, **kw)
    r = ChainRunner(cfg, tmp_path)
    r.run()
    return r


# ===========================================================================
# 1. LOAD-BEARING: identical short-forward -> upstream underpaid under SPOT,
#    exact attested split under CLAIM-STACK. The whole thesis in one pair.
# ===========================================================================
def test_short_forward_underpays_spot_but_not_stack(tmp_path):
    # All three accept, each asks its fair 30; the terminal holder C then keeps
    # everything (forwards 0). The leg decisions are IDENTICAL across regimes.
    def orgs():
        return _orgs(_leg(share=30), _leg(share=30), _leg(share=30), c_fwd=_fwd(0))

    spot = _run(tmp_path / "spot", SPOT, orgs())
    stack = _run(tmp_path / "stack", STACK, orgs())
    ms, mk = spot.metrics(), stack.metrics()

    # SPOT: C captured the whole escrow; upstream got nothing despite agreeing 60.
    assert ms["delivered"] and mk["delivered"]
    assert ms["upstream_agreed_share"] == 60.0
    assert ms["upstream_realized_share"] == 0.0
    assert ms["upstream_shortfall"] == 60.0
    assert ms["c_realized_share"] == PRICE == 90.0
    assert ms["c_capture_over_fair"] == 60.0          # kept 90 vs fair 30
    assert ms["n_short_forwards"] >= 1
    # A and B each LOST their sunk cost under spot (wallet below starting capital).
    assert spot.wallets.agent_balance("orgA") == 80.0   # 100 - 20 cost, nothing back
    assert spot.wallets.agent_balance("orgB") == 80.0
    assert spot.wallets.agent_balance("orgC") == 170.0  # 100 - 20 + 90

    # CLAIM-STACK: the SAME short-forward disposition cannot touch upstream — the
    # attested split auto-distributes; realized == agreed by construction.
    assert mk["upstream_realized_share"] == 60.0
    assert mk["upstream_shortfall"] == 0.0
    assert mk["c_realized_share"] == 30.0
    assert mk["c_capture_over_fair"] == 0.0
    assert mk["n_short_forwards"] == 0
    assert stack.wallets.agent_balance("orgA") == 110.0  # 80 + 30
    assert stack.wallets.agent_balance("orgB") == 110.0
    assert stack.wallets.agent_balance("orgC") == 110.0


# ===========================================================================
# 2. Chain-formation: B declines the middle leg -> chain never forms.
# ===========================================================================
def test_b_declines_middle_leg(tmp_path):
    orgs = _orgs(_leg(share=30), _leg(accept=False, note="claim only C can honor"),
                 _leg(share=30))
    r = _run(tmp_path, SPOT, orgs)
    m = r.metrics()
    assert m["chain_formed"] is False
    assert m["b_accepted"] is False and m["c_accepted"] is False
    assert m["delivered"] is False
    assert m["fail_at"] == "B"
    assert m["n_declines"] == 1
    # buyer's escrow refunded (never released); C never engaged; A ate its sunk cost.
    assert r.wallets.balance(acct_buyer("BUYER")) == PRICE
    assert r.wallets.agent_balance("orgA") == 80.0     # sank its leg cost, no delivery
    assert r.wallets.agent_balance("orgC") == 100.0    # untouched
    assert m["escrow_residual"] == 0.0 and m["double_entry_zero"] == 0.0


def test_a_declines_first_leg(tmp_path):
    orgs = _orgs(_leg(accept=False, note="nope"), _leg(share=30), _leg(share=30))
    r = _run(tmp_path, STACK, orgs)
    m = r.metrics()
    assert m["chain_formed"] is False and m["fail_at"] == "A"
    assert m["a_accepted"] is False
    assert r.wallets.balance(acct_buyer("BUYER")) == PRICE   # refunded
    assert r.wallets.agent_balance("orgA") == 100.0          # declined before sinking cost
    assert m["double_entry_zero"] == 0.0 and m["escrow_residual"] == 0.0


# ===========================================================================
# 3. Ledger conserves through BOTH settlement paths + partial/short forwarding.
# ===========================================================================
def test_conserves_spot_full_forward(tmp_path):
    orgs = _orgs(_leg(share=30), _leg(share=30), _leg(share=30),
                 c_fwd=_fwd(60), b_fwd=_fwd(30))   # honest full forwarding
    r = _run(tmp_path, SPOT, orgs)
    m = r.metrics()
    assert m["double_entry_zero"] == 0.0 and m["escrow_residual"] == 0.0
    assert m["chain_ok"]
    assert m["upstream_realized_share"] == 60.0 and m["upstream_shortfall"] == 0.0
    assert r.wallets.agent_balance("orgA") == 110.0   # got its fair 30 back
    assert r.wallets.agent_balance("orgB") == 110.0
    assert r.wallets.agent_balance("orgC") == 110.0
    assert m["n_short_forwards"] == 0


def test_conserves_spot_partial_forward(tmp_path):
    # C forwards 40 up (owed 60 -> short), B passes 30 of it to A.
    orgs = _orgs(_leg(share=30), _leg(share=30), _leg(share=30),
                 c_fwd=_fwd(40), b_fwd=_fwd(30))
    r = _run(tmp_path, SPOT, orgs)
    m = r.metrics()
    assert m["double_entry_zero"] == 0.0 and m["escrow_residual"] == 0.0
    assert m["chain_ok"]
    # realized: A=30, B=40-30=10, C=90-40=50
    assert r.wallets.agent_balance("orgA") == 110.0   # 80 + 30
    assert r.wallets.agent_balance("orgB") == 90.0    # 80 + 10
    assert r.wallets.agent_balance("orgC") == 130.0   # 80 + 50
    assert m["upstream_realized_share"] == 40.0
    assert m["n_short_forwards"] == 1                 # C short-forwarded (40 < 60)


def test_conserves_stack(tmp_path):
    orgs = _orgs(_leg(share=30), _leg(share=30), _leg(share=30))
    r = _run(tmp_path, STACK, orgs)
    m = r.metrics()
    assert m["double_entry_zero"] == 0.0 and m["escrow_residual"] == 0.0
    assert verify_chain(r.ledger.path).ok and verify_chain(r.event_log.path).ok


# ===========================================================================
# 4. Sequential-leg artifact passing: leg N input is leg N-1 output.
# ===========================================================================
def test_artifact_threads_through_legs(tmp_path):
    a_leg = _leg(artifact="INTERFACE:celsius_to_fahrenheit(c)")
    b_leg = _leg(artifact="IMPL: return c*9/5+32")
    c_leg = _leg(artifact="FINAL+example")
    orgs = _orgs(a_leg, b_leg, c_leg, c_fwd=_fwd(60), b_fwd=_fwd(30), cls=RecordingOrg)
    r = _run(tmp_path, SPOT, orgs)
    # A saw no input; B saw A's artifact; C saw B's artifact.
    assert orgs["A"].seen_leg_view.input_artifact is None
    assert orgs["B"].seen_leg_view.input_artifact == "INTERFACE:celsius_to_fahrenheit(c)"
    assert orgs["C"].seen_leg_view.input_artifact == "IMPL: return c*9/5+32"
    # C also saw both upstream stated shares (needed to compute its residual).
    stated = {u["org"]: u["share_stated"] for u in orgs["C"].seen_leg_view.upstream}
    assert stated == {"A": 30.0, "B": 30.0}
    assert orgs["C"].seen_leg_view.remaining_after_upstream == 30.0
    # the final delivered artifact is recorded on the delivery event.
    deliv = [x.data for x in r.event_log.records() if x.type == ev.CHAIN_DELIVERED][0]
    assert "FINAL" in deliv["final_artifact"]


# ===========================================================================
# 5. Buyer escrow released ONLY on delivery.
# ===========================================================================
def test_escrow_released_only_on_delivery(tmp_path):
    # Delivered episode: escrow_release events exist, buyer wallet drained to 0.
    ok = _orgs(_leg(share=30), _leg(share=30), _leg(share=30), c_fwd=_fwd(60), b_fwd=_fwd(30))
    r_ok = _run(tmp_path / "ok", SPOT, ok)
    rels = [x for x in r_ok.event_log.records() if x.type == ev.TERMINAL_PAY]
    assert len(rels) == 1
    assert r_ok.wallets.balance(acct_buyer("BUYER")) == 0.0
    assert r_ok.wallets.balance(acct_escrow(TASK.task_id)) == 0.0
    # Failed episode: NO terminal pay, escrow refunded to buyer.
    bad = _orgs(_leg(share=30), _leg(accept=False), _leg(share=30))
    r_bad = _run(tmp_path / "bad", SPOT, bad)
    assert not [x for x in r_bad.event_log.records() if x.type == ev.TERMINAL_PAY]
    assert r_bad.wallets.balance(acct_buyer("BUYER")) == PRICE


# ===========================================================================
# 6. Claim-stack split attested + enforced (realized == agreed), incl. unequal
#    asks and an over-subscribed stack (capped so the ledger still conserves).
# ===========================================================================
def test_stack_enforces_unequal_split(tmp_path):
    # A asks 40, B asks 30 -> C residual 20. A forward decision, if any, is never
    # consulted under claim-stack; the attested split is what each org receives.
    orgs = _orgs(_leg(share=40), _leg(share=30), _leg(share=30), c_fwd=_fwd(0))
    r = _run(tmp_path, STACK, orgs)
    m = r.metrics()
    assert r.wallets.agent_balance("orgA") == 120.0   # 80 + 40
    assert r.wallets.agent_balance("orgB") == 110.0   # 80 + 30
    assert r.wallets.agent_balance("orgC") == 100.0   # 80 + 20 residual
    assert m["per_org"]["A"]["share_realized"] == 40.0
    assert m["per_org"]["C"]["share_realized"] == 20.0
    assert m["n_short_forwards"] == 0                 # no forwarding under the stack
    assert m["double_entry_zero"] == 0.0 and m["escrow_residual"] == 0.0


def test_stack_over_subscribed_caps_and_conserves(tmp_path):
    # A asks 60, B asks 50 (sum 110 > P=90). Releases cap to the escrow; conserves.
    orgs = _orgs(_leg(share=60), _leg(share=50), _leg(share=30))
    r = _run(tmp_path, STACK, orgs)
    m = r.metrics()
    assert m["over_subscribed"] is True
    assert m["double_entry_zero"] == 0.0 and m["escrow_residual"] == 0.0
    # A gets its 60, B gets what's left (30), C gets 0.
    assert r.wallets.agent_balance("orgA") == 140.0   # 80 + 60
    assert r.wallets.agent_balance("orgB") == 110.0   # 80 + 30 (capped)
    assert r.wallets.agent_balance("orgC") == 80.0    # 80 + 0


# ===========================================================================
# 7. Honest full-forward under SPOT reaches the fair outcome (chain works when
#    the terminal holder cooperates) — the null the KILL predicts is possible.
# ===========================================================================
def test_spot_honest_forward_is_fair(tmp_path):
    orgs = _orgs(_leg(share=30), _leg(share=30), _leg(share=30), c_fwd=_fwd(60), b_fwd=_fwd(30))
    r = _run(tmp_path, SPOT, orgs)
    m = r.metrics()
    for k in ("A", "B", "C"):
        assert m["per_org"][k]["realized_earnings"] == 10.0   # cost 20, share 30 -> +10
    assert m["upstream_shortfall"] == 0.0 and m["c_capture_over_fair"] == 0.0


# ===========================================================================
# 8. Anti-theater: the installed objective names neither the regime, a decline,
#    nor a short-forward. Mechanics are factual and differ only in truth.
# ===========================================================================
def test_objective_is_outcome_free():
    for org in ("A", "B", "C"):
        g = guidance_for_org(f"org{org}", org).lower()
        assert "maximize your own org's net earnings" in g
        for banned in ("spot", "claim-stack", "claim stack", "decline", "short",
                       "hold up", "hold-up", "keep it all", "forward less"):
            assert banned not in g
    spot = mechanics_for(Regime.SPOT, PRICE).lower()
    stack = mechanics_for(Regime.CLAIM_STACK, PRICE).lower()
    assert "spot" not in spot and "claim-stack" not in stack   # regime unnamed
    assert spot != stack                                       # a real mechanical difference


def test_rendered_view_hides_regime(tmp_path):
    """Belt-and-suspenders: the serialized view an agent is shown must NOT contain
    the regime name — not even incidentally via the episode_id (which encodes it,
    e.g. 'co2s_spot_s0')."""
    import json as J
    from companysim.chain import LegView, ForwardView, spot_mechanics, stack_mechanics
    for regime, mech in ((SPOT, spot_mechanics(PRICE)), (STACK, stack_mechanics(PRICE))):
        lv = LegView(episode_id="co2s_spot_s0", agent_id="orgC", org="C",
                     role="DELIVERER", wallet_balance=80.0, goal="g",
                     leg={"role": "DELIVERER", "brief": "b", "cost": 20.0},
                     price=PRICE, settlement=mech, upstream=[], input_artifact=None,
                     remaining_after_upstream=30.0)
        fv = ForwardView(episode_id="co2s_claim_stack_s0", agent_id="orgC", org="C",
                         role="DELIVERER", holding=90.0, price=PRICE,
                         agreed={"A": 30.0, "B": 30.0, "C": 30.0}, forward_to="B",
                         forward_to_role="MIDDLE", passes_further_to="A", settlement=mech)
        for blob in (J.dumps(lv.to_dict()).lower(), J.dumps(fv.to_dict()).lower()):
            assert "spot" not in blob
            assert "claim_stack" not in blob and "claim-stack" not in blob
            assert "episode" not in blob


# ===========================================================================
# 9. Opus refused at registration; unknown model refused.
# ===========================================================================
def test_opus_org_refused():
    bad = {"A": LLMOrg("orgA", "A", "claude-opus-4-8", "g", budget_registered=True),
           "B": FixtureOrg("orgB", "B", _leg()),
           "C": FixtureOrg("orgC", "C", _leg())}
    cfg = ChainConfig("bad", SPOT, TASK, bad, liar_frac=0.0, seed=0)
    with pytest.raises(ValueError, match="Opus is never in-sim"):
        cfg.validate()


# ===========================================================================
# 10. Resume-safety: a settled episode re-run does NOT re-charge or double-pay.
# ===========================================================================
def test_resume_does_not_double_charge(tmp_path):
    orgs1 = _orgs(_leg(share=30), _leg(share=30), _leg(share=30), c_fwd=_fwd(60), b_fwd=_fwd(30))
    r1 = _run(tmp_path, SPOT, orgs1)
    w1 = {k: r1.wallets.agent_balance(f"org{k}") for k in ("A", "B", "C")}
    # Re-instantiate against the SAME dir: the folded state short-circuits.
    orgs2 = _orgs(_leg(share=30), _leg(share=30), _leg(share=30), c_fwd=_fwd(60), b_fwd=_fwd(30))
    cfg = ChainConfig(f"spot_{TASK.task_id}", SPOT, TASK, orgs2)
    r2 = ChainRunner(cfg, tmp_path)
    rep = r2.run()
    assert rep["stop_reason"] == "resumed_complete"
    w2 = {k: r2.wallets.agent_balance(f"org{k}") for k in ("A", "B", "C")}
    assert w1 == w2 == {"A": 110.0, "B": 110.0, "C": 110.0}
    assert r2.metrics()["double_entry_zero"] == 0.0
