"""Tests for the multi-issue logrolling tool (gametheory.negotiation.bundle)."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from gametheory.negotiation.bundle import negotiate_bundle, BundleInputError

# Two competitive issues: on each, I prefer "hi", they prefer "lo".
TWO_ISSUES = [
    {"name": "A", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]},
    {"name": "B", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]},
]


def test_logrolls_holds_high_priority_concedes_low():
    # I weight A far above B -> I should HOLD A (my preferred "hi") and CONCEDE B.
    r = negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": 0.8, "B": 0.2})
    assert r["recommended_offer"]["A"] == "hi"     # held my top priority
    assert r["recommended_offer"]["B"] == "lo"     # conceded the issue I value least
    assert r["my_utility"] > 0.5


def test_recommended_is_pareto_efficient():
    # No other full outcome should dominate the recommendation on both utilities.
    import itertools
    import numpy as np
    from gametheory.negotiation.bundle import _norm01
    r = negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": 0.6, "B": 0.4})
    rec = r["recommended_offer"]
    my_u = [_norm01(i["my_utility"]) for i in TWO_ISSUES]
    their_u = [_norm01(i["their_utility"]) for i in TWO_ISSUES]
    mw = np.array([0.6, 0.4])
    tw = np.array([r["inferred_their_priorities"]["A"], r["inferred_their_priorities"]["B"]])
    def util(combo):
        me = sum(mw[i] * my_u[i][combo[i]] for i in range(2))
        them = sum(tw[i] * their_u[i][combo[i]] for i in range(2))
        return me, them
    rec_idx = (TWO_ISSUES[0]["options"].index(rec["A"]), TWO_ISSUES[1]["options"].index(rec["B"]))
    rme, rthem = util(rec_idx)
    for combo in itertools.product(range(2), range(2)):
        me, them = util(combo)
        dominates = (me >= rme and them >= rthem) and (me > rme + 1e-9 or them > rthem + 1e-9)
        assert not dominates, f"{combo} dominates the recommendation"


def test_infers_priorities_from_offers():
    # Counterparty repeatedly protects B (holds their-preferred "lo" on B, flexes on A)
    # -> their inferred weight on B should exceed A.
    offers = [{"A": "lo", "B": "lo"}, {"A": "hi", "B": "lo"}, {"A": "hi", "B": "lo"}]
    r = negotiate_bundle(issues=TWO_ISSUES, their_offers=offers, my_priorities={"A": 0.5, "B": 0.5})
    p = r["inferred_their_priorities"]
    assert abs(p["A"] + p["B"] - 1.0) < 1e-6
    assert p["B"] > p["A"]


def test_walk_when_nothing_clears_batna():
    r = negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": 0.5, "B": 0.5}, my_batna=0.99)
    assert r["action"] == "walk"
    assert r["recommended_offer"] is None
    assert r["fit"]["score"] == "poor"


def test_accept_when_their_offer_is_already_best_for_us():
    # Their latest offer hands us our best on both issues -> accept.
    r = negotiate_bundle(issues=TWO_ISSUES, their_offers=[{"A": "hi", "B": "hi"}],
                         my_priorities={"A": 0.5, "B": 0.5})
    assert r["action"] == "accept"


def test_single_issue_redirects_to_negotiate_turn():
    one = [{"name": "price", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]}]
    r = negotiate_bundle(issues=one, my_priorities={"price": 1.0})
    assert r["fit"]["score"] == "marginal"
    assert "negotiate_turn" in r["fit"]["reason"]


def test_input_validation_mismatched_lengths():
    bad = [{"name": "A", "options": ["lo", "hi"], "my_utility": [0, 1, 2], "their_utility": [1, 0]}]
    with pytest.raises(BundleInputError):
        negotiate_bundle(issues=bad)


def test_partial_counterparty_offer_rejected():
    # An offer missing an issue must NOT be silently scored as option 0.
    with pytest.raises(BundleInputError):
        negotiate_bundle(issues=TWO_ISSUES, their_offers=[{"A": "lo"}],  # missing "B"
                         my_priorities={"A": 0.5, "B": 0.5})


def test_nonnumeric_priorities_rejected():
    with pytest.raises(BundleInputError):
        negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": "high", "B": 0.5})


def test_negative_priorities_rejected():
    with pytest.raises(BundleInputError):
        negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": -1, "B": 2})


def test_http_bundle_partial_offer_is_400():
    c = _client()
    resp = c.post("/v1/negotiate/bundle", json={
        "issues": [
            {"name": "A", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]},
            {"name": "B", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]},
        ],
        "their_offers": [{"A": "lo"}],  # missing B -> clean 400, not 500
    })
    assert resp.status_code == 400


def test_outcome_space_cap():
    big = [{"name": f"i{k}", "options": list(range(10)),
            "my_utility": list(range(10)), "their_utility": list(range(10))} for k in range(5)]
    with pytest.raises(BundleInputError):
        negotiate_bundle(issues=big)  # 10^5 outcomes > cap


# ─── Surface wiring: HTTP, catalog, MCP ──────────────────────────────────────

def _client():
    os.environ.setdefault("GT_KEYS_DB", os.path.join(tempfile.mkdtemp(), "t.db"))
    from gametheory.server.http import app
    return TestClient(app)


def test_http_bundle_endpoint():
    c = _client()
    resp = c.post("/v1/negotiate/bundle", json={
        "issues": [
            {"name": "price", "options": ["$50", "$30"], "my_utility": [0, 1], "their_utility": [1, 0]},
            {"name": "sla", "options": ["99%", "99.9%"], "my_utility": [0, 1], "their_utility": [1, 0]},
        ],
        "my_priorities": {"price": 0.8, "sla": 0.2},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "recommended_offer" in body and "inferred_their_priorities" in body


def test_http_bundle_bad_input_400():
    c = _client()
    resp = c.post("/v1/negotiate/bundle", json={
        "issues": [{"name": "A", "options": ["lo", "hi"], "my_utility": [0], "their_utility": [1, 0]}],
    })
    assert resp.status_code == 400


def test_catalog_lists_bundle():
    c = _client()
    names = [t["name"] for t in c.get("/v1/catalog").json()["tools"]]
    assert "gt.negotiate.bundle" in names


def test_mcp_exposes_bundle_tool():
    from gametheory.server import mcp_server
    assert hasattr(mcp_server, "gt_negotiate_bundle")
    out = mcp_server.gt_negotiate_bundle(
        issues=[{"name": "A", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]},
                {"name": "B", "options": ["lo", "hi"], "my_utility": [0, 1], "their_utility": [1, 0]}],
        my_priorities={"A": 0.8, "B": 0.2})
    assert out["recommended_offer"]["A"] == "hi"


# ─── verified-peer multi-issue path ──────────────────────────────────────────
def test_peer_mode_backward_compatible():
    """Default (peer_mode=False) is unchanged."""
    base = negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": 0.8, "B": 0.2})
    explicit = negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": 0.8, "B": 0.2},
                                peer_mode=False)
    assert base["recommended_offer"] == explicit["recommended_offer"]


def test_peer_mode_returns_valid_package():
    out = negotiate_bundle(issues=TWO_ISSUES, my_priorities={"A": 0.8, "B": 0.2},
                           my_batna=0.3, their_batna_estimate=0.3, peer_mode=True)
    assert out["action"] in ("counter", "accept")
    assert set(out["recommended_offer"]) == {"A", "B"}


def test_peer_mode_lifts_joint_welfare():
    """Two peers grow the joint pie vs two adversaries, on the same profiles."""
    import numpy as np
    from gametheory.negotiation import bundle_validation as bv
    peer_j, adv_j = [], []
    for i in range(120):
        p = bv._run_bilateral(np.random.default_rng(11 + i), peer=True)
        a = bv._run_bilateral(np.random.default_rng(11 + i), peer=False)
        if p and a:
            peer_j.append(p[0]); adv_j.append(a[0])
    assert np.mean(peer_j) > np.mean(adv_j)                 # positive lift
    assert np.mean(np.array(peer_j) >= np.array(adv_j)) > 0.6  # robust across profiles
