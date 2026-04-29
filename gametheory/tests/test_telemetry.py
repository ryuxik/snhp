"""
Tests for the V1 opt-in telemetry / data-moat module.

Covers the privacy contract gates: pepper required, account-level consent
required, per-call share_outcome required, week-bounded join window,
GDPR export + delete, quantization, and the HTTP routes' bearer auth.

The test fixtures place SQLite at a tempdir per session so tests don't
clobber the dev DB.
"""
import os
import tempfile
import time

import pytest

_tmp_dir = tempfile.mkdtemp()
os.environ["GT_KEYS_DB"] = os.path.join(_tmp_dir, "test_telemetry.db")
os.environ["TELEMETRY_PEPPER"] = "test_pepper_DO_NOT_USE_IN_PROD_x" * 2

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server import telemetry  # noqa: E402
from gametheory.server.http import app  # noqa: E402
from gametheory.server.onboarding import issue_key  # noqa: E402

client = TestClient(app)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _consenting_key(agent_id: str) -> str:
    res = issue_key(
        agent_id=agent_id,
        contact_email=f"{agent_id}@test.invalid",
        intended_use_summary="telemetry-on test",
        telemetry_consent=True,
    )
    return res["api_key"]


def _silent_key(agent_id: str) -> str:
    res = issue_key(
        agent_id=agent_id,
        contact_email=f"{agent_id}@test.invalid",
        intended_use_summary="telemetry-off test",
        telemetry_consent=False,
    )
    return res["api_key"]


_BASIC_REQ = {
    "my_reservation": 0.4,
    "deadline_rounds": 8,
    "pareto_knob": 0.5,
}
_BASIC_REC = {
    "recommended_offer": 0.83,
    "acceptance_probability": 0.62,
    "rationale": "this string contains a secret leak vector",
    "posterior": {"mu": 0.812345, "sigma": 0.151111, "n_particles": 200},
}


# ─── Pepper / hash semantics ────────────────────────────────────────────────


def test_pepper_missing_raises(monkeypatch):
    monkeypatch.delenv("TELEMETRY_PEPPER", raising=False)
    with pytest.raises(RuntimeError, match="TELEMETRY_PEPPER not set"):
        telemetry.hash_api_key("gt_anything")


def test_hash_is_deterministic_within_week():
    h1 = telemetry.hash_api_key("gt_abc", week="2026-W17")
    h2 = telemetry.hash_api_key("gt_abc", week="2026-W17")
    assert h1 == h2


def test_hash_changes_across_weeks():
    h1 = telemetry.hash_api_key("gt_abc", week="2026-W17")
    h2 = telemetry.hash_api_key("gt_abc", week="2026-W18")
    assert h1 != h2, "per-week hash must differ across ISO weeks"


def test_iso_week_format():
    s = telemetry._iso_week()
    assert "-W" in s
    year, week = s.split("-W")
    assert 2025 <= int(year) <= 2030
    assert 1 <= int(week) <= 53


# ─── Quantization ───────────────────────────────────────────────────────────


def test_quantize_rounds_floats_to_grid():
    assert telemetry._quantize(0.123) == pytest.approx(0.12)
    assert telemetry._quantize(0.812345) == pytest.approx(0.82)
    assert telemetry._quantize(0.0) == 0.0


def test_quantize_caps_lists():
    out = telemetry._quantize(list(range(50)))
    assert len(out) == 16


def test_quantize_recurses_into_dicts():
    out = telemetry._quantize({"a": 0.123, "b": [0.456, 0.789]})
    assert out["a"] == pytest.approx(0.12)
    assert out["b"] == [pytest.approx(0.46), pytest.approx(0.78)]


def test_quantize_passes_through_non_floats():
    assert telemetry._quantize("string") == "string"
    assert telemetry._quantize(42) == 42
    assert telemetry._quantize(True) is True
    assert telemetry._quantize(None) is None


# ─── Two-gate consent ───────────────────────────────────────────────────────


def test_record_returns_none_without_account_consent():
    key = _silent_key("agent_silent")
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    assert rec_id is None, "no consent → no row written"


def test_record_with_consent_writes_row():
    key = _consenting_key("agent_consenting")
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    assert rec_id is not None
    assert rec_id.startswith("rec_")


def test_record_strips_rationale():
    key = _consenting_key("agent_strip")
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    rows = telemetry.export_agent_records(key)
    matching = [r for r in rows if r["recommendation_id"] == rec_id]
    assert matching, "wrote then read back failed"
    assert "rationale" not in matching[0]["recommendation"]


def test_record_quantizes_features():
    key = _consenting_key("agent_quant")
    weird = {"my_reservation": 0.41234, "deadline_rounds": 8,
             "pareto_knob": 0.50333}
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=weird, recommendation=_BASIC_REC,
    )
    rows = telemetry.export_agent_records(key)
    matching = [r for r in rows if r["recommendation_id"] == rec_id][0]
    # 0.41234 → 0.42; 0.50333 → 0.50 on the 0.02 grid
    assert matching["request_features"]["my_reservation"] == pytest.approx(0.42)
    assert matching["request_features"]["pareto_knob"] == pytest.approx(0.50)


# ─── Outcome reporting ──────────────────────────────────────────────────────


def test_report_outcome_succeeds_in_same_week():
    key = _consenting_key("agent_outcome_ok")
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    ok = telemetry.report_outcome(
        api_key=key, recommendation_id=rec_id, deal_closed=True,
        my_utility=0.71, opponent_utility=0.29,
    )
    assert ok is True


def test_report_outcome_idempotent_second_call():
    key = _consenting_key("agent_idempotent")
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    first = telemetry.report_outcome(
        api_key=key, recommendation_id=rec_id, deal_closed=True,
        my_utility=0.7, opponent_utility=0.3,
    )
    second = telemetry.report_outcome(
        api_key=key, recommendation_id=rec_id, deal_closed=False,
        my_utility=0.0,
    )
    assert first is True and second is False, "second report must be no-op"


def test_report_outcome_rejects_other_agent_forge():
    """Another agent must not be able to attach an outcome to my rec."""
    key_a = _consenting_key("agent_owner")
    key_b = _consenting_key("agent_forger")
    rec_id = telemetry.record_recommendation(
        api_key=key_a, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    forged = telemetry.report_outcome(
        api_key=key_b, recommendation_id=rec_id, deal_closed=True,
    )
    assert forged is False


def test_report_outcome_quantizes_utilities():
    key = _consenting_key("agent_outcome_q")
    rec_id = telemetry.record_recommendation(
        api_key=key, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    telemetry.report_outcome(
        api_key=key, recommendation_id=rec_id, deal_closed=True,
        my_utility=0.71234, opponent_utility=0.28999,
    )
    rows = telemetry.export_agent_records(key)
    row = [r for r in rows if r["recommendation_id"] == rec_id][0]
    assert row["outcome"]["my_utility"] == pytest.approx(0.72)
    assert row["outcome"]["opponent_utility"] == pytest.approx(0.28)


# ─── GDPR ───────────────────────────────────────────────────────────────────


def test_export_returns_only_my_rows():
    key_a = _consenting_key("agent_export_a")
    key_b = _consenting_key("agent_export_b")
    telemetry.record_recommendation(
        api_key=key_a, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    telemetry.record_recommendation(
        api_key=key_b, endpoint="negotiation/sell/next_offer",
        vertical="saas_procurement",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    a_rows = telemetry.export_agent_records(key_a)
    a_verticals = {r["vertical"] for r in a_rows}
    assert "ad_inventory" in a_verticals
    assert "saas_procurement" not in a_verticals, "leaked another agent's data"


def test_delete_removes_all_my_rows():
    key = _consenting_key("agent_delete")
    for _ in range(3):
        telemetry.record_recommendation(
            api_key=key, endpoint="negotiation/sell/next_offer",
            vertical="ad_inventory",
            request_features=_BASIC_REQ, recommendation=_BASIC_REC,
        )
    deleted = telemetry.delete_agent_records(key)
    assert deleted == 3
    assert telemetry.export_agent_records(key) == []


def test_delete_does_not_touch_other_agents():
    key_a = _consenting_key("agent_delete_keep_a")
    key_b = _consenting_key("agent_delete_keep_b")
    telemetry.record_recommendation(
        api_key=key_a, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    telemetry.record_recommendation(
        api_key=key_b, endpoint="negotiation/sell/next_offer",
        vertical="ad_inventory",
        request_features=_BASIC_REQ, recommendation=_BASIC_REC,
    )
    telemetry.delete_agent_records(key_a)
    assert len(telemetry.export_agent_records(key_a)) == 0
    assert len(telemetry.export_agent_records(key_b)) >= 1


# ─── HTTP integration ───────────────────────────────────────────────────────


def test_share_outcome_default_off():
    """A request that doesn't pass share_outcome must not get rec-id back."""
    key = _consenting_key("agent_http_default")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6, 0.55],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
        },
    )
    assert r.status_code == 200
    assert "X-GT-Recommendation-Id" not in r.headers


def test_share_outcome_emits_recommendation_id():
    key = _consenting_key("agent_http_share")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6, 0.55],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "ad_inventory",
        },
    )
    assert r.status_code == 200
    rec_id = r.headers.get("X-GT-Recommendation-Id")
    assert rec_id is not None and rec_id.startswith("rec_")


def test_http_no_consent_account_no_rec_id_emitted():
    """share_outcome=True from a key that didn't opt in at issuance:
    silent no-op, no header — caller can detect absence and ask user
    to issue a consenting key."""
    key = _silent_key("agent_http_silent")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "ad_inventory",
        },
    )
    assert r.status_code == 200
    assert "X-GT-Recommendation-Id" not in r.headers


def test_http_invalid_vertical_rejected():
    """Vertical is a Literal allowlist; free-text is rejected by Pydantic."""
    key = _consenting_key("agent_http_bad_vert")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "<script>alert(1)</script>",
        },
    )
    assert r.status_code == 422


def test_http_report_outcome_round_trip():
    key = _consenting_key("agent_http_outcome")
    r = client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "ad_inventory",
        },
    )
    rec_id = r.headers["X-GT-Recommendation-Id"]
    r2 = client.post(
        "/v1/telemetry/report_outcome",
        headers={"Authorization": f"Bearer {key}"},
        json={"recommendation_id": rec_id, "deal_closed": True,
              "my_utility": 0.7, "opponent_utility": 0.3},
    )
    assert r2.status_code == 200
    assert r2.json()["accepted"] is True


def test_http_delete_endpoint():
    key = _consenting_key("agent_http_delete")
    client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "ad_inventory",
        },
    )
    r = client.delete("/v1/telemetry/delete",
                       headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200
    assert r.json()["rows_deleted"] >= 1


def test_http_export_endpoint():
    key = _consenting_key("agent_http_export")
    client.post(
        "/v1/negotiation/sell/next_offer",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "my_reservation": 0.4,
            "opponent_offer_history": [0.6],
            "my_offer_history": [0.85],
            "deadline_rounds": 8,
            "share_outcome": True,
            "vertical": "ad_inventory",
        },
    )
    r = client.get("/v1/telemetry/export",
                    headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert any(row["vertical"] == "ad_inventory" for row in rows)


def test_http_telemetry_endpoints_require_bearer():
    r1 = client.post("/v1/telemetry/report_outcome",
                      json={"recommendation_id": "rec_x", "deal_closed": True})
    r2 = client.delete("/v1/telemetry/delete")
    r3 = client.get("/v1/telemetry/export")
    for r in (r1, r2, r3):
        assert r.status_code == 401
