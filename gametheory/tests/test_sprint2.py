"""
Sprint 2 acceptance tests.

Per the plan's verification section:
  1. First-strike commit/reveal end-to-end (HTTP): declare → verify
     attestation JWT → reveal → check binding_offer.
  2. Anchor-attack detection over HTTP: anomalous opening flagged, normal
     opening ignored.
  3. Buy-side next_offer with defense bundle over HTTP: returns warnings
     and respects walk-away floor.
  4. Metered-key upgrade flow: free key → upgrade with pm_* → metered key
     unlocks paid endpoint.
  5. draft_message billing gate: 402 without metered key, 400 on
     BATNA-violating draft, 200 + cost header with valid metered key
     (LLM call stubbed).

Run: ../venv/bin/python -m pytest gametheory/tests/test_sprint2.py -v
"""
import os
import tempfile
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient


def _deadline_iso_in_days(days: int) -> str:
    """ISO 8601 deadline N days from now (first-strike caps at 7 days)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

# Use a temp DB so Sprint 2 tests don't pollute Sprint 1 state or the
# user's keys.db.
_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_sprint2_keys.db")

from gametheory.server.http import app
from gametheory.crypto.first_strike import (
    commit_hash, verify_attestation,
)
from gametheory.negotiation.buy import detect_anchor_attack, buy_next_offer


client = TestClient(app)


# ─── Cryptographic first-strike: pure-math round trip ───────────────────────


def test_commit_hash_is_deterministic_and_id_bound():
    """Same inputs → same hash; different buyer/seller IDs → different hash."""
    h1 = commit_hash(0.5, "nonce-a", "salt-a", "buyer-1", "seller-1")
    h2 = commit_hash(0.5, "nonce-a", "salt-a", "buyer-1", "seller-1")
    h3 = commit_hash(0.5, "nonce-a", "salt-a", "buyer-1", "seller-2")
    assert h1 == h2
    assert h1 != h3, "different seller_id must change the hash (no replay)"


# ─── First-strike HTTP round trip ───────────────────────────────────────────


def test_first_strike_end_to_end():
    """declare → verify JWT → reveal → idempotent re-reveal."""
    reservation = 0.42
    nonce = "n-abc"
    salt = "s-xyz"
    buyer = "buyer-acme"
    seller = "seller-globex"
    h = commit_hash(reservation, nonce, salt, buyer, seller)

    # declare
    r = client.post("/v1/negotiation/declare_first_strike", json={
        "buyer_id": buyer,
        "seller_id": seller,
        "reservation_hash": h,
        "deadline_iso": _deadline_iso_in_days(3),
        "binding_ttl_seconds": 3600,
    })
    assert r.status_code == 200, r.text
    declared = r.json()
    assert declared["commitment_id"].startswith("fs_")
    assert declared["expires_at_unix"] > 0
    jwt_token = declared["attestation_jwt"]
    assert jwt_token.count(".") == 2  # header.payload.signature

    # verify attestation against the published trust anchor
    decoded = verify_attestation(jwt_token)
    assert decoded["buyer_id"] == buyer
    assert decoded["seller_id"] == seller
    assert decoded["reservation_hash"] == h
    assert decoded["kind"] == "first_strike_commitment"

    # reveal
    r2 = client.post("/v1/negotiation/reveal_first_strike", json={
        "commitment_id": declared["commitment_id"],
        "reservation": reservation,
        "nonce": nonce,
        "salt": salt,
    })
    assert r2.status_code == 200, r2.text
    revealed = r2.json()
    assert revealed["verified"] is True
    assert abs(revealed["binding_offer"] - reservation) < 1e-9
    assert revealed["reused"] is False

    # idempotent re-reveal
    r3 = client.post("/v1/negotiation/reveal_first_strike", json={
        "commitment_id": declared["commitment_id"],
        "reservation": reservation,
        "nonce": nonce,
        "salt": salt,
    })
    assert r3.status_code == 200
    assert r3.json()["reused"] is True


def test_first_strike_reveal_mismatch_rejected():
    """Wrong nonce/reservation → 400, no binding offer issued."""
    h = commit_hash(0.5, "real-nonce", "real-salt", "b", "s")
    r = client.post("/v1/negotiation/declare_first_strike", json={
        "buyer_id": "b",
        "seller_id": "s",
        "reservation_hash": h,
        "deadline_iso": _deadline_iso_in_days(3),
        "binding_ttl_seconds": 3600,
    })
    cid = r.json()["commitment_id"]
    bad = client.post("/v1/negotiation/reveal_first_strike", json={
        "commitment_id": cid,
        "reservation": 0.5,
        "nonce": "WRONG",
        "salt": "real-salt",
    })
    assert bad.status_code == 400


def test_first_strike_unknown_commitment_404():
    r = client.post("/v1/negotiation/reveal_first_strike", json={
        "commitment_id": "fs_does_not_exist",
        "reservation": 0.5,
        "nonce": "n",
        "salt": "s",
    })
    assert r.status_code == 404


def test_trust_anchor_endpoint_serves_pem():
    r = client.get("/v1/keys/trust_anchor")
    assert r.status_code == 200
    assert "BEGIN PUBLIC KEY" in r.text
    assert "END PUBLIC KEY" in r.text


# ─── Anchor-attack detection ────────────────────────────────────────────────


def test_anchor_attack_flags_extreme_opening():
    """Opening 4σ below market mean → flagged as anchor attack."""
    r = detect_anchor_attack(
        opponent_offer_history=[0.05],
        market_prior={"mu": 0.45, "sigma": 0.10},
    )
    assert r["is_anchor_attack"] is True
    assert r["z_score"] < -2.5
    assert r["recommended_response"] in {"counter_with_market", "walk_away"}


def test_anchor_attack_ignores_normal_opening():
    """Opening near market mean → no flag."""
    r = detect_anchor_attack(
        opponent_offer_history=[0.42],
        market_prior={"mu": 0.45, "sigma": 0.10},
    )
    assert r["is_anchor_attack"] is False
    assert r["recommended_response"] == "ignore"


def test_anchor_attack_endpoint_via_http():
    r = client.post("/v1/negotiation/detect_anchor_attack", json={
        "opponent_offer_history": [0.05],
        "market_prior": {"mu": 0.45, "sigma": 0.10},
    })
    assert r.status_code == 200
    body = r.json()
    assert body["is_anchor_attack"] is True
    assert r.headers["X-GT-Cost-USD"] == "0"


# ─── Buy-side next_offer ────────────────────────────────────────────────────


def test_buy_next_offer_respects_walkaway_floor():
    """Recommended offer must be at or above the buyer's reservation."""
    r = buy_next_offer(
        my_reservation=0.40,
        seller_offer_history=[0.10, 0.15, 0.20],
        my_offer_history=[0.85, 0.80, 0.75],
        deadline_rounds=10,
        pareto_knob=0.5,
        defenses=["schelling_commitment"],
    )
    # In buyer convention, our utility from offering price p is `recommended`;
    # higher recommended = we're willing to pay more (lower price for seller).
    # Schelling floor binds at >= reservation + 0.05 or 0.40.
    assert r["recommended_offer"] >= 0.40
    assert r["schelling_floor"] >= 0.40


def test_buy_next_offer_anchor_defense_attaches_warning():
    """When anchor_attack_detection sees an extreme opening, warnings/actions populate."""
    r = buy_next_offer(
        my_reservation=0.40,
        seller_offer_history=[0.05],
        my_offer_history=[],
        deadline_rounds=10,
        pareto_knob=0.5,
        defenses=["anchor_attack_detection"],
        market_prior={"mu": 0.45, "sigma": 0.10},
    )
    assert any(w["code"] == "anchor_attack_detected" for w in r["warnings"])
    assert len(r["defense_actions"]) >= 1


def test_buy_next_offer_unknown_defense_rejected():
    with pytest.raises(ValueError):
        buy_next_offer(
            my_reservation=0.40,
            seller_offer_history=[0.20],
            my_offer_history=[],
            deadline_rounds=10,
            defenses=["definitely_not_a_real_defense"],
        )


def test_buy_next_offer_endpoint_returns_cost_headers():
    r = client.post("/v1/negotiation/buy/next_offer", json={
        "my_reservation": 0.40,
        "seller_offer_history": [0.20, 0.25],
        "my_offer_history": [0.80, 0.75],
        "deadline_rounds": 10,
        "pareto_knob": 0.5,
        "defenses": ["schelling_commitment"],
    })
    assert r.status_code == 200, r.text
    assert r.headers["X-GT-Cost-USD"] == "0"
    body = r.json()
    assert "recommended_offer" in body
    assert "warnings" in body
    assert "defense_actions" in body


def test_buy_endpoint_requires_market_prior_when_anchor_defense_on():
    """Validation: anchor_attack_detection without market_prior → 400."""
    r = client.post("/v1/negotiation/buy/next_offer", json={
        "my_reservation": 0.40,
        "seller_offer_history": [0.20],
        "my_offer_history": [],
        "deadline_rounds": 10,
        "defenses": ["anchor_attack_detection"],
        # no market_prior
    })
    assert r.status_code == 400


# ─── Metered-key upgrade flow ───────────────────────────────────────────────


def _issue_free_key(agent_id: str) -> str:
    r = client.post("/v1/keys", json={
        "agent_id": agent_id,
        "contact_email": "billing@example.com",
        "intended_use_summary": "Sprint 2 paid endpoint testing",
    })
    assert r.status_code == 200
    return r.json()["api_key"]


def test_key_upgrade_mints_metered_key():
    free_key = _issue_free_key("metered-agent-001")
    assert free_key.startswith("gt_test_")
    r = client.post("/v1/keys/upgrade", json={
        "api_key": free_key,
        "stripe_payment_method_id": "pm_test_visa",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_key"].startswith("gt_live_")
    assert body["tier"] == "metered"
    assert body["rate_limit_per_minute"] == 600
    assert body["stripe_payment_method_id"] == "pm_test_visa"


def test_key_upgrade_rejects_non_pm_id():
    free_key = _issue_free_key("metered-agent-002")
    r = client.post("/v1/keys/upgrade", json={
        "api_key": free_key,
        "stripe_payment_method_id": "tok_visa",  # wrong prefix
    })
    assert r.status_code == 400


def test_key_upgrade_rejects_unknown_key():
    r = client.post("/v1/keys/upgrade", json={
        "api_key": "gt_test_definitely_not_real",
        "stripe_payment_method_id": "pm_test_visa",
    })
    assert r.status_code == 400


# ─── draft_message billing gate (LLM stubbed) ────────────────────────────────


def test_draft_message_402_without_key():
    r = client.post("/v1/negotiation/draft_message", json={
        "numbers": {"recommended_offer": 0.6},
        "client_email": "Hello, what's your best price?",
        "constraints_text": "Need delivery by Q2",
        "tone": "professional",
        "my_reservation": 0.40,
    })
    assert r.status_code == 402


def test_draft_message_402_with_free_key():
    free_key = _issue_free_key("paid-agent-free")
    r = client.post(
        "/v1/negotiation/draft_message",
        json={
            "numbers": {"recommended_offer": 0.6},
            "client_email": "Hi",
            "constraints_text": "Constraints",
            "tone": "professional",
            "my_reservation": 0.40,
        },
        headers={"Authorization": f"Bearer {free_key}"},
    )
    assert r.status_code == 402


def test_draft_message_400_on_batna_violation(monkeypatch):
    """Refuse to draft if proposed offer is below the caller's reservation."""
    free_key = _issue_free_key("paid-agent-batna")
    upgraded = client.post("/v1/keys/upgrade", json={
        "api_key": free_key,
        "stripe_payment_method_id": "pm_test_visa",
    }).json()["api_key"]

    r = client.post(
        "/v1/negotiation/draft_message",
        json={
            "numbers": {"recommended_offer": 0.30},  # below my_reservation
            "client_email": "Hi",
            "constraints_text": "Constraints",
            "tone": "professional",
            "my_reservation": 0.40,
        },
        headers={"Authorization": f"Bearer {upgraded}"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "BATNA" in detail and "reservation" in detail


def test_draft_message_succeeds_with_metered_key(monkeypatch):
    """Stub the LLM helper so the test does not spend real tokens."""
    free_key = _issue_free_key("paid-agent-success")
    upgraded = client.post("/v1/keys/upgrade", json={
        "api_key": free_key,
        "stripe_payment_method_id": "pm_test_visa",
    }).json()["api_key"]

    # Patch the LLM call where it's bound (http.py) so the test is
    # deterministic and free. Patching `llm_extractor._call_llm` would
    # miss because http.py imported the symbol at module load.
    from gametheory.server import http as http_module
    monkeypatch.setattr(
        http_module, "_call_llm",
        lambda prompt, temperature=0.4: "Thanks for the note. Our position is unchanged. We can move ahead at the proposed terms.",
    )

    r = client.post(
        "/v1/negotiation/draft_message",
        json={
            "numbers": {"recommended_offer": 0.65},
            "client_email": "Hi, what's your offer?",
            "constraints_text": "Q2 delivery",
            "tone": "professional",
            "my_reservation": 0.40,
        },
        headers={"Authorization": f"Bearer {upgraded}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Thanks" in body["text"]
    assert float(r.headers["X-GT-Cost-USD"]) > 0


# ─── Catalog discoverability for Sprint 2 ────────────────────────────────────


def test_catalog_lists_sprint2_tools():
    r = client.get("/v1/catalog")
    assert r.status_code == 200
    names = {t["name"]: t for t in r.json()["tools"]}
    for required in [
        "gt.negotiation.buy.next_offer",
        "gt.negotiation.detect_anchor_attack",
        "gt.negotiation.declare_first_strike",
        "gt.negotiation.reveal_first_strike",
        "gt.negotiation.draft_message",
    ]:
        assert required in names, f"missing {required} from catalog"
    # draft_message must be tagged paid so agents can budget.
    assert names["gt.negotiation.draft_message"]["cost_class"] == "paid"
    # The math endpoints must remain free.
    assert names["gt.negotiation.buy.next_offer"]["cost_class"] == "free"
    assert names["gt.negotiation.declare_first_strike"]["cost_class"] == "free"
