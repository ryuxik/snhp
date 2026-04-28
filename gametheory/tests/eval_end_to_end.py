"""
End-to-end eval harness — runs the workflows described in the plan as if a
fresh agent were composing the toolkit. Not a pytest test; meant to be run
manually for sanity-checking after a release.

Workflows:
  W1 — Tier 1 sell-side: 3-round negotiation through HTTP, monotone offers
  W2 — Tier 1 buy-side under anchor attack: detect → declare first-strike →
       reveal at agreed price
  W3 — Tier 2 cross-format equivalence: optimal_bid (Vickrey) bids
       valuation; first-price (uniform) bids v(N-1)/N
  W4 — Tier 3 marketplace operator: optimal_auction_design + posted_price
  W5 — Tier 3 stable matching textbook example
  W6 — Onboarding: free-key → upgrade → paid endpoint (LLM stubbed)
  W7 — OpenAPI discovery surface: schema + catalog + llms.txt agree

Run: ../venv/bin/python -m gametheory.tests.eval_end_to_end
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

_tmp = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp, "eval.db")

from fastapi.testclient import TestClient
from gametheory.server.http import app
from gametheory.crypto.first_strike import commit_hash, verify_attestation


client = TestClient(app)
PASS = []
FAIL = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        PASS.append(name)
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def w1_sell_side_3round() -> None:
    print("\nW1 — Sell-side 3-round negotiation (Pareto knob = 0.7):")
    seller_history: list[float] = []
    buyer_history = [0.20, 0.30, 0.45]   # buyer's offers in our utility space
    offers = []
    for r in range(3):
        seller_offers_so_far = seller_history.copy()
        body = {
            "my_reservation": 0.40,
            "opponent_offer_history": buyer_history[: r + 1],
            "my_offer_history": seller_offers_so_far,
            "deadline_rounds": 8,
            "pareto_knob": 0.7,
        }
        resp = client.post("/v1/negotiation/sell/next_offer", json=body)
        assert resp.status_code == 200, resp.text
        offer = resp.json()["recommended_offer"]
        offers.append(offer)
        seller_history.append(offer)
    # Concession: offers should be (weakly) decreasing across rounds.
    monotone = all(offers[i] >= offers[i + 1] - 0.001 for i in range(len(offers) - 1))
    floor_ok = all(o >= 0.40 for o in offers)
    check("offers are monotone non-increasing across rounds", monotone, str(offers))
    check("all offers respect reservation = 0.40", floor_ok)


def w2_buy_side_anchor_then_first_strike() -> None:
    print("\nW2 — Buy-side: detect anchor → first-strike commit → reveal:")
    # Seller opens at 0.05 (in our utility) — extreme anchor
    detect = client.post("/v1/negotiation/detect_anchor_attack", json={
        "opponent_offer_history": [0.05],
        "market_prior": {"mu": 0.45, "sigma": 0.10},
    })
    assert detect.status_code == 200
    body = detect.json()
    check("anchor attack flagged", body["is_anchor_attack"] is True,
          f"z={body['z_score']}")

    # Buyer declares first-strike at reservation 0.55
    nonce, salt, buyer, seller = "n123", "s456", "buy-acme", "sell-globex"
    h = commit_hash(0.55, nonce, salt, buyer, seller)
    deadline = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    declared = client.post("/v1/negotiation/declare_first_strike", json={
        "buyer_id": buyer, "seller_id": seller, "reservation_hash": h,
        "deadline_iso": deadline, "binding_ttl_seconds": 7200,
    })
    assert declared.status_code == 200, declared.text
    cid = declared.json()["commitment_id"]
    jwt_token = declared.json()["attestation_jwt"]

    # Verify attestation against the published trust anchor
    decoded = verify_attestation(jwt_token)
    check("EdDSA attestation verifies", decoded["reservation_hash"] == h)

    # Reveal at the agreed price
    revealed = client.post("/v1/negotiation/reveal_first_strike", json={
        "commitment_id": cid, "reservation": 0.55, "nonce": nonce, "salt": salt,
    })
    assert revealed.status_code == 200, revealed.text
    rb = revealed.json()
    check("reveal returns binding offer", abs(rb["binding_offer"] - 0.55) < 1e-9)


def w3_auction_known_answers() -> None:
    print("\nW3 — Auction known-answer correctness:")
    # Vickrey: bid = valuation
    r = client.post("/v1/auction/bidder/optimal_bid", json={
        "auction_format": "second_price_vickrey",
        "my_valuation": 100, "n_competing_bidders": 3,
        "competitor_value_prior": {"family": "uniform", "params": {"low": 0, "high": 100}},
    })
    assert r.status_code == 200
    check("Vickrey bid == valuation", r.json()["optimal_bid"] == 100)

    # First-price uniform[0,1] N=2: bid = v/2
    r = client.post("/v1/auction/bidder/optimal_bid", json={
        "auction_format": "first_price",
        "my_valuation": 1.0, "n_competing_bidders": 1,
        "competitor_value_prior": {"family": "uniform", "params": {"low": 0, "high": 1}},
    })
    assert r.status_code == 200
    check("first-price uniform[0,1] N=2: bid ≈ 0.5",
          abs(r.json()["optimal_bid"] - 0.5) < 0.01,
          f"got {r.json()['optimal_bid']:.4f}")

    # Optimal reserve uniform[0,100]: r = 50
    r = client.post("/v1/auction/seller/optimal_reserve", json={
        "bidder_value_prior": {"family": "uniform", "params": {"low": 0, "high": 100}},
        "n_bidders": 4, "seller_valuation": 0,
    })
    assert r.status_code == 200
    check("Myerson reserve uniform[0,100]: r ≈ 50",
          abs(r.json()["reserve_price"] - 50.0) < 1.0,
          f"got {r.json()['reserve_price']}")


def w4_marketplace_operator() -> None:
    print("\nW4 — Marketplace operator (optimal auction + posted price):")
    # Asymmetric two-bidder auction
    r = client.post("/v1/mechanism/optimal_auction_design", json={
        "bidder_priors": [
            {"family": "uniform", "params": {"low": 0, "high": 100}},
            {"family": "uniform", "params": {"low": 50, "high": 200}},
        ],
        "seller_valuation": 0, "objective": "revenue",
    })
    assert r.status_code == 200
    body = r.json()
    check("asymmetric reserves differ",
          len(set(body["reserve_prices"].values())) == 2,
          str(body["reserve_prices"]))

    # Posted price for a single-product run
    r = client.post("/v1/mechanism/posted_price_optimal", json={
        "buyer_arrival_prior": {"family": "uniform", "params": {"low": 0, "high": 100}},
        "arrival_rate_per_second": 0.5,
        "inventory": 50, "horizon_seconds": 600.0,
    })
    assert r.status_code == 200
    pp = r.json()
    rel = abs(pp["static_expected_revenue"] - pp["static_simulated_revenue"]) \
        / max(pp["static_expected_revenue"], 1e-9)
    check(f"posted-price analytical/MC within 5% (got {rel:.3%})", rel < 0.05)
    check("dynamic at least as good as static (sim)",
          pp["dynamic_value_estimate"] >= pp["static_simulated_revenue"],
          f"V_dyn={pp['dynamic_value_estimate']}, sim_static={pp['static_simulated_revenue']}")


def w5_stable_matching() -> None:
    print("\nW5 — Gale-Shapley textbook 4×4 (Knuth 1976):")
    r = client.post("/v1/mechanism/gale_shapley", json={
        "proposers": [
            {"id": "1", "preferences": ["A", "B", "C", "D"]},
            {"id": "2", "preferences": ["A", "C", "B", "D"]},
            {"id": "3", "preferences": ["B", "A", "C", "D"]},
            {"id": "4", "preferences": ["D", "A", "C", "B"]},
        ],
        "receivers": [
            {"id": "A", "preferences": ["4", "3", "1", "2"]},
            {"id": "B", "preferences": ["1", "4", "2", "3"]},
            {"id": "C", "preferences": ["3", "1", "2", "4"]},
            {"id": "D", "preferences": ["2", "3", "1", "4"]},
        ],
    })
    assert r.status_code == 200
    matching = r.json()["matching"]
    expected = {"1": "A", "2": "C", "3": "B", "4": "D"}
    check("matches Knuth proposer-optimal answer", matching == expected,
          str(matching))
    check("blocking pairs empty", r.json()["blocking_pairs"] == [])


def w6_onboarding_and_billing() -> None:
    print("\nW6 — Onboarding + billing gate:")
    free = client.post("/v1/keys", json={
        "agent_id": "eval-agent-001",
        "contact_email": "eval@example.com",
        "intended_use_summary": "End-to-end evaluation harness run.",
    }).json()["api_key"]
    check("free key has gt_test_ prefix", free.startswith("gt_test_"))

    # Free-key call to paid endpoint → 402
    r = client.post("/v1/negotiation/draft_message", json={
        "numbers": {"recommended_offer": 0.6}, "client_email": "?",
        "constraints_text": "?", "tone": "professional", "my_reservation": 0.4,
    }, headers={"Authorization": f"Bearer {free}"})
    check("free key → 402 on paid endpoint", r.status_code == 402)

    # Upgrade
    metered = client.post("/v1/keys/upgrade", json={
        "api_key": free, "stripe_payment_method_id": "pm_eval_visa",
    }).json()["api_key"]
    check("upgraded key has gt_live_ prefix", metered.startswith("gt_live_"))


def w7_discovery_surface() -> None:
    print("\nW7 — Discovery surface (catalog / OpenAPI / llms.txt):")
    catalog = client.get("/v1/catalog").json()
    catalog_names = {t["name"] for t in catalog["tools"]}

    spec = client.get("/openapi.json").json()
    paths = set(spec["paths"].keys())

    # Every catalog tool must have its endpoint in the OpenAPI spec.
    missing = []
    for t in catalog["tools"]:
        endpoint_path = t["endpoint"].split(" ", 1)[1]
        if endpoint_path not in paths:
            missing.append(endpoint_path)
    check("every catalog tool is in the OpenAPI spec", not missing, str(missing))

    # llms.txt must mention each tool family
    llms = client.get("/llms.txt").text
    families_ok = all(f in llms for f in [
        "Tier 1", "Tier 2", "Tier 3", "/v1/negotiation", "/v1/auction", "/v1/mechanism",
    ])
    check("llms.txt covers all three tiers", families_ok)


def _safe(name: str, fn) -> None:
    """Wrap a workflow so a single failure (assertion / HTTP error) records
    a FAIL row and the remaining workflows still run."""
    try:
        fn()
    except Exception as e:
        FAIL.append(f"{name} (uncaught)")
        print(f"  FAIL  {name} (uncaught) — {type(e).__name__}: {e}")


if __name__ == "__main__":
    print("=" * 70)
    print("Game-theory toolkit end-to-end eval")
    print("=" * 70)
    _safe("W1", w1_sell_side_3round)
    _safe("W2", w2_buy_side_anchor_then_first_strike)
    _safe("W3", w3_auction_known_answers)
    _safe("W4", w4_marketplace_operator)
    _safe("W5", w5_stable_matching)
    _safe("W6", w6_onboarding_and_billing)
    _safe("W7", w7_discovery_surface)
    print()
    print("=" * 70)
    print(f"PASSED: {len(PASS)}    FAILED: {len(FAIL)}")
    print("=" * 70)
    sys.exit(0 if not FAIL else 1)
