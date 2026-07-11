"""Tests for B6 flywheel (task #71): the phase-diagram / adoption-fixed-point
machinery and the two headline properties (the edge grows with φ via
coordination; there is no robust tipping point). The fixed-point detector is
tested against SYNTHETIC S-curves and concave curves so the "no k*" verdict is
demonstrably NOT an artifact of a broken detector."""
import json
import pathlib

import pytest

from block import flywheel
from block.flywheel import FlyConfig

SEED = 20260710


# ── the fixed-point / tipping detector, exercised on synthetic responses ─────

def test_fixed_point_detector_finds_a_tipping_point_in_an_s_curve():
    """A bistable S-shaped adoption response MUST yield: φ=0 stable, an unstable
    interior tipping point k*, and φ=1 stable. This proves the detector can find
    a k* when one exists (so the block's monostable verdict is real, not a
    blind detector)."""
    phi = (0.0, 0.25, 0.5, 0.75, 1.0)
    F = [0.0, 0.10, 0.40, 0.85, 1.0]          # classic sigmoid critical-mass curve
    fps = flywheel.fixed_points(phi, F)
    assert flywheel._classify(fps) == "bistable"
    tips = [f for f in fps if f["stability"] == "unstable"]
    assert len(tips) == 1 and 0.0 < tips[0]["phi_star"] < 1.0
    # φ=0 and φ=1 are both stable (tip-or-die)
    stables = [f["phi_star"] for f in fps if f["stability"] == "stable"]
    assert 0.0 in stables and 1.0 in stables


def test_fixed_point_detector_reports_monostable_for_a_concave_response():
    """A concave response with F(0)>0 (a standalone-value product: some adopt at
    zero penetration) has a SINGLE stable interior fixed point and NO tipping
    point — exactly the block's measured shape."""
    phi = (0.0, 0.25, 0.5, 0.75, 1.0)
    F = [0.30, 0.70, 0.85, 0.90, 0.92]         # jumps then saturates (concave)
    fps = flywheel.fixed_points(phi, F)
    assert not any(f["stability"] == "unstable" for f in fps)   # no k*
    assert flywheel._classify(fps).startswith("monostable")


def test_adoption_response_is_the_fraction_below_the_edge():
    import numpy as np
    edges = np.array([0.1, 0.2, 0.3, 0.4])
    costs = np.array([0.25, 0.25, 0.25, 0.25])
    # two of four have edge > cost
    assert flywheel.adoption_response(edges, costs) == pytest.approx(0.5)


# ── the sharpening laws (the two flywheel channels) ──────────────────────────

def test_sharpening_channels_are_monotone_in_phi():
    """σ_cal(φ) and COGS(φ) both start at their φ=0 anchors (σ0, 1.0 — the world
    SNHP replaces) and fall monotonically as disclosure accumulates (the B6.1
    conjugate shrinkage). This is the mechanical flywheel input."""
    cfg = FlyConfig()
    assert flywheel.sigma_cal(0.0, cfg) == pytest.approx(cfg.sigma0)
    assert flywheel.cogs_scale(0.0, cfg) == pytest.approx(1.0)
    phis = [i / 20 for i in range(21)]
    sig = [flywheel.sigma_cal(p, cfg) for p in phis]
    cog = [flywheel.cogs_scale(p, cfg) for p in phis]
    assert all(sig[i + 1] <= sig[i] + 1e-12 for i in range(len(sig) - 1))
    assert all(cog[i + 1] <= cog[i] + 1e-12 for i in range(len(cog) - 1))
    assert sig[-1] < sig[0] and cog[-1] < cog[0]


# ── the committed sweep (one module-scoped run, ~30s) ────────────────────────

@pytest.fixture(scope="module")
def sweep():
    """The committed flywheel sweep — the same config block/results-flywheel.json
    records."""
    return flywheel.run_sweep(FlyConfig(seeds=8, pop_per_seed=700), seed0=SEED)


def test_edge_grows_with_phi(sweep):
    """Q1: the agent's realized consumer edge over the strong posted board GROWS
    with agent penetration φ (CI on the φ=1−φ=0 paired diff excludes zero)."""
    g = sweep["Q1_edge_grows_with_phi"]["delta_total_phi1_minus_phi0"]
    assert g["ci95"][0] > 0.0
    assert sweep["Q1_edge_grows_with_phi"]["grows"]


def test_growth_is_coordination_not_shopping(sweep):
    """The flywheel force is the DURABLE growth channel (coordination), not the
    shopping transfer: E_shop is flat across φ (the transfer competes to a
    bounded level) while E_coord rises from 0. This is the antagonism finding
    made mechanical."""
    q1 = sweep["Q1_edge_grows_with_phi"]
    assert q1["shop_channel_flat"]                       # E_shop CI(φ1−φ0) ∋ 0
    coord = q1["E_coord_by_phi"]
    assert coord[0] == 0.0                               # no cluster at φ=0
    assert coord[-1] > coord[1] > 0.0                    # rises then saturates


def test_no_robust_tipping_point(sweep):
    """Q2 headline: under realistic adoption-cost heterogeneity (σ ≥ 0.3) there
    is NO tipping point at any adoption-cost median — adoption is monostable.
    The standalone spot edge means a low-cost tail always adopts (F(0)>0), so
    adoption never collapses to zero and there is no critical mass to cross."""
    phase = sweep["Q2_phase_diagram"]
    for blk in phase["blocks"]:
        if blk["adopt_cost_sigma"] >= 0.3:
            assert not blk["any_tipping_point"]
            for r in blk["rows"]:
                assert r["k_star"] is None
                assert r["class"].startswith("monostable")
    assert not sweep["verdict"]["robust_tipping_point_under_heterogeneity"]


def test_merchant_margin_does_not_collapse_with_phi(sweep):
    """The other side of the two-sided flywheel: agent-mediated merchant margin
    per consumer does NOT collapse as φ rises — the shopping transfer is bounded
    (confined to the commodity overlap), so adding agents does not drive margin
    to zero."""
    ma = [c["merchant_margin_agent"]["mean"] for c in sweep["cells"]]
    assert min(ma) > 0.0
    assert max(ma) - min(ma) < 0.3 * max(ma)            # roughly flat


def test_committed_flywheel_results_stay_reproducible(sweep):
    """block/results-flywheel.json reproduces byte-identically at its config."""
    path = pathlib.Path(__file__).parents[1] / "results-flywheel.json"
    committed = json.load(open(path))
    assert json.dumps(sweep, sort_keys=True) == json.dumps(committed,
                                                           sort_keys=True)


def test_flywheel_is_deterministic():
    """The whole sweep reproduces byte-identically from the same seed (small
    config for speed)."""
    a = flywheel.run_sweep(FlyConfig(seeds=2, pop_per_seed=120), seed0=5)
    b = flywheel.run_sweep(FlyConfig(seeds=2, pop_per_seed=120), seed0=5)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
