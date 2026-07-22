"""W2 handoff: signed receipts surfaced on the advice / nextmove doors.

GAUNTLET #4 asked the store to stop grading its own homework. W2 signed the
receipts; this pins that every paid move hands one back through BOTH doors, and
that close returns a signed session-summary receipt alongside the `closed` flag
(without changing close_session's bool contract). The signatures VERIFY here —
against the process's ambient notary key — so the handoff is real, not a field
the store merely wrote about itself.
"""
import os
import tempfile
import uuid

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_advice_doors.db"))
os.environ.setdefault("NEXTMOVE_TELEMETRY_PATH",
                      os.path.join(_tmp, "telemetry.jsonl"))

from fastapi.testclient import TestClient  # noqa: E402

from gametheory.server import mcp_server  # noqa: E402
from gametheory.server.http import app  # noqa: E402
from gametheory.server.onboarding import issue_key, wallet_credit  # noqa: E402
from vend.receipt_signing import verify_receipt  # noqa: E402

client = TestClient(app)


def _key(cents=1000):        # $10 funded — comfortably over a $2 session
    k = issue_key(agent_id=f"adv-door-{uuid.uuid4().hex[:8]}",
                  contact_email="t@example.com",
                  intended_use_summary="advice door tests")["api_key"]
    if cents:
        wallet_credit(k, cents * 1000, bucket="funded")
    return k


_OPEN = dict(category="resale", side="sell", walk_away=170, target=210)


def test_http_move_and_close_carry_signed_receipts():
    key = _key()
    # open with their_offers → the first move rides back WITH a signed receipt
    r = client.post("/v1/advice/session",
                    json={"api_key": key, **_OPEN, "their_offers": [150]})
    assert r.status_code == 200, r.text
    body = r.json()
    sid = body["session_id"]
    assert verify_receipt(body["first_move"]["receipt"])
    # a subsequent move carries its own signed receipt
    m = client.post("/v1/advice/move",
                    json={"api_key": key, "session_id": sid,
                          "their_offers": [150, 165]})
    assert m.status_code == 200, m.text
    assert verify_receipt(m.json()["receipt"])
    # close returns the bool AND a signed session-summary receipt
    c = client.post("/v1/advice/close",
                    json={"api_key": key, "session_id": sid})
    assert c.status_code == 200, c.text
    cb = c.json()
    assert cb["closed"] is True                                   # bool contract kept
    assert cb["receipt"]["kind"] == "nextmove.session_summary"
    assert verify_receipt(cb["receipt"])


def test_http_bundle_move_carries_receipt():
    key = _key()
    sess = client.post("/v1/advice/session",
                       json={"api_key": key, "category": "supply", "side": "buy",
                             "walk_away": 5000, "target": 4200}).json()
    issues = [
        {"name": "price", "options": ["4800", "5000"],
         "my_utility": [1.0, 0.5], "their_utility": [0.3, 1.0]},
        {"name": "delivery", "options": ["2wk", "4wk"],
         "my_utility": [0.9, 0.4], "their_utility": [0.3, 0.9]},
    ]
    b = client.post("/v1/advice/bundle",
                    json={"api_key": key, "session_id": sess["session_id"],
                          "issues": issues, "my_batna": 0.4})
    assert b.status_code == 200, b.text
    assert verify_receipt(b.json()["receipt"])


def test_mcp_advise_and_close_carry_receipts():
    key = _key()
    opened = mcp_server.nextmove_open(api_key=key, category="resale", side="sell",
                                      walk_away=170, target=210,
                                      their_offers=[150])
    sid = opened["session_id"]
    assert verify_receipt(opened["first_move"]["receipt"])
    adv = mcp_server.nextmove_advise(api_key=key, session_id=sid,
                                     their_offers=[150, 165])
    assert verify_receipt(adv["receipt"])
    closed = mcp_server.nextmove_close(api_key=key, session_id=sid)
    assert closed["closed"] is True
    assert closed["receipt"]["kind"] == "nextmove.session_summary"
    assert verify_receipt(closed["receipt"])


def test_close_unknown_session_http_404_mcp_error():
    key = _key()
    r = client.post("/v1/advice/close",
                    json={"api_key": key, "session_id": "ns_never"})
    assert r.status_code == 404
    out = mcp_server.nextmove_close(api_key=key, session_id="ns_never")
    assert out["closed"] is False and "error" in out
