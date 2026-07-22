"""THE BLIND LOCKER — park & retrieve (STORE.md §2c).

Every invariant the spec hangs on has a test here: the round-trip is byte-exact,
a wrong key cannot retrieve, a hard TTL makes a parcel gone, the size cap rejects
UNCHARGED, the park charges EXACTLY once (never on oversize/failure), retrieve is
FREE, contents never reach telemetry or the DB in the clear, the at-rest layer
means the stored bytes differ from the input, and the raw ticket is never stored
(only its hash). Time is INJECTED (never wall-clock) so the TTL test is
deterministic.
"""
import base64
import os
import tempfile
import uuid

import pytest

_tmp = tempfile.mkdtemp()
os.environ.setdefault("GT_KEYS_DB", os.path.join(_tmp, "test_locker.db"))
os.environ.setdefault("NEXTMOVE_TELEMETRY_PATH",
                      os.path.join(_tmp, "telemetry.jsonl"))
# Exercise the REAL at-rest AEAD path (lock #2) in the suite. Individual tests
# monkeypatch this env to cover the honest-degrade path too.
os.environ.setdefault("LOCKER_AT_REST_KEY", "test-at-rest-secret-do-not-ship")

from vend import locker  # noqa: E402
from vend.receipt_signing import verify_receipt  # noqa: E402


# ─── fixtures ────────────────────────────────────────────────────────────────


def _key():
    """A fresh key with the 50¢ starter credit (50_000 millicents)."""
    from gametheory.server.onboarding import issue_key
    return issue_key(agent_id=f"lock-{uuid.uuid4().hex[:8]}",
                     contact_email="t@example.com",
                     intended_use_summary="locker tests")["api_key"]


def _total(api_key):
    from gametheory.server.onboarding import wallet_available
    return wallet_available(api_key)["total_millicents"]


@pytest.fixture(autouse=True)
def _capture_telemetry():
    """Capture every locker telemetry line so tests can assert the contents
    (blob/ticket/key) never appear in it. Restores the default sink after."""
    lines = []
    locker.set_telemetry_sink(lambda **f: lines.append(dict(f)))
    locker._captured = lines
    yield lines
    locker.set_telemetry_sink(locker._default_sink)


# ─── round-trip ──────────────────────────────────────────────────────────────


def test_park_retrieve_roundtrip_exact_bytes():
    key = _key()
    blob = b"\x00\x01\x02opaque-ciphertext-\xff\xfe payload" * 40
    parked = locker.park(key, blob)
    assert parked["ok"] is True
    assert parked["size_bytes"] == len(blob)
    got = locker.retrieve(key, parked["ticket"])
    assert got["ok"] is True
    assert got["blob"] == blob            # byte-exact
    assert got["size_bytes"] == len(blob)


def test_park_retrieve_roundtrip_via_b64_doors():
    key = _key()
    blob = os.urandom(1234)
    b64 = base64.b64encode(blob).decode()
    parked = locker.park_b64(key, b64)
    assert parked["ok"] is True
    got = locker.retrieve_b64(key, parked["ticket"])
    assert got["ok"] is True
    assert "blob" not in got              # doors return base64, never raw bytes
    assert base64.b64decode(got["blob_b64"]) == blob


def test_bad_base64_is_clean_client_error_uncharged():
    key = _key()
    before = _total(key)
    out = locker.park_b64(key, "!!!not base64!!!")
    assert out["ok"] is False and out["code"] == "bad_encoding"
    assert _total(key) == before          # uncharged


# ─── ownership ───────────────────────────────────────────────────────────────


def test_wrong_key_cannot_retrieve():
    owner, other = _key(), _key()
    blob = b"secret-parcel-bytes"
    parked = locker.park(owner, blob)
    # a non-owner is told not_found — indistinguishable from a missing ticket,
    # so a ticket cannot be probed with someone else's key.
    out = locker.retrieve(other, parked["ticket"])
    assert out["ok"] is False and out["code"] == "not_found"
    # the true owner still retrieves it.
    assert locker.retrieve(owner, parked["ticket"])["blob"] == blob


def test_unknown_ticket_is_not_found():
    key = _key()
    out = locker.retrieve(key, "ticket-that-was-never-issued")
    assert out["ok"] is False and out["code"] == "not_found"


# ─── hard TTL (time injected — deterministic) ────────────────────────────────


def test_expired_ticket_is_gone():
    key = _key()
    t0 = 1_000_000
    parked = locker.park(key, b"perishable", ttl_seconds=60, now=t0)
    assert parked["expires_at"] == t0 + 60
    # still live at t0+59
    assert locker.retrieve(key, parked["ticket"], now=t0 + 59)["ok"] is True
    # gone at t0+61
    out = locker.retrieve(key, parked["ticket"], now=t0 + 61)
    assert out["ok"] is False and out["code"] == "expired"
    # and reaped: a second read finds nothing at all
    again = locker.retrieve(key, parked["ticket"], now=t0 + 62)
    assert again["code"] == "not_found"


def test_ttl_clamped_and_effective_expiry_returned():
    key = _key()
    t0 = 2_000_000
    over = locker.park(key, b"x", ttl_seconds=10 ** 9, now=t0)
    assert over["expires_at"] == t0 + locker.LOCKER_TTL_MAX_S      # clamped up-bound
    under = locker.park(key, b"y", ttl_seconds=1, now=t0)
    assert under["expires_at"] == t0 + locker.LOCKER_TTL_MIN_S     # clamped low-bound
    default = locker.park(key, b"z", now=t0)
    assert default["expires_at"] == t0 + locker.LOCKER_TTL_DEFAULT_S


# ─── size cap ────────────────────────────────────────────────────────────────


def test_size_cap_rejected_uncharged_unstored():
    key = _key()
    before = _total(key)
    big = b"a" * (locker.LOCKER_MAX_BYTES + 1)
    out = locker.park(key, big)
    assert out["ok"] is False and out["code"] == "too_large"
    assert "ticket" not in out
    assert _total(key) == before          # never charged
    # exactly at the cap is accepted
    ok = locker.park(key, b"b" * locker.LOCKER_MAX_BYTES)
    assert ok["ok"] is True


def test_empty_blob_rejected_uncharged():
    key = _key()
    before = _total(key)
    out = locker.park(key, b"")
    assert out["ok"] is False and out["code"] == "empty_blob"
    assert _total(key) == before


# ─── settlement: charged exactly once, retrieve free ─────────────────────────


def test_park_charged_exactly_once_on_success():
    key = _key()
    before = _total(key)
    blob = b"c" * 1024                     # small tier
    parked = locker.park(key, blob)
    price = parked["price_millicents"]
    assert price == locker.LOCKER_PARK_FEE_TIER1_MILLICENTS
    assert _total(key) == before - price   # charged exactly the fee, once
    assert parked["receipt"]["price_millicents"] == price


def test_larger_tier_priced_higher():
    key = _key()
    before = _total(key)
    blob = b"d" * (locker.LOCKER_TIER1_BYTES + 1)   # into tier 2
    parked = locker.park(key, blob)
    assert parked["price_millicents"] == locker.LOCKER_PARK_FEE_TIER2_MILLICENTS
    assert _total(key) == before - locker.LOCKER_PARK_FEE_TIER2_MILLICENTS


def test_retrieve_is_free():
    key = _key()
    parked = locker.park(key, b"free-to-read")
    after_park = _total(key)
    for _ in range(3):
        assert locker.retrieve(key, parked["ticket"])["ok"] is True
    assert _total(key) == after_park       # no retrieve ever charged


def test_oversize_and_empty_never_charge():
    key = _key()
    before = _total(key)
    locker.park(key, b"a" * (locker.LOCKER_MAX_BYTES + 1))
    locker.park(key, b"")
    assert _total(key) == before


def test_insufficient_balance_rejected_uncharged_unstored():
    from gametheory.server.onboarding import wallet_debit, wallet_available
    key = _key()
    # drain the wallet to zero
    wallet_debit(key, wallet_available(key)["total_millicents"])
    assert _total(key) == 0
    out = locker.park(key, b"cannot-afford-this")
    assert out["ok"] is False and out["code"] == "insufficient_balance"
    assert "ticket" not in out
    assert _total(key) == 0


def test_unknown_key_rejected_uncharged():
    out = locker.park("sk_not_a_real_key", b"whatever")
    assert out["ok"] is False and out["code"] == "unknown_key"


# ─── blindness: contents never in telemetry or the DB in the clear ───────────


def test_contents_never_in_telemetry(_capture_telemetry):
    key = _key()
    blob = b"MARKER-PLAINTEXT-LOOKING-CIPHERTEXT-8f3a"
    parked = locker.park(key, blob)
    locker.retrieve(key, parked["ticket"])
    lines = _capture_telemetry
    assert lines, "telemetry must record park + retrieve"
    for rec in lines:
        blob_str = str(rec)
        # the blob (as marker text, base64, or hex), the raw ticket, and the raw
        # key are all absent from every telemetry line — only size + a hashed
        # ticket + a keyed pseudonym are recorded.
        assert "MARKER-PLAINTEXT" not in blob_str
        assert base64.b64encode(blob).decode() not in blob_str
        assert blob.hex() not in blob_str
        assert parked["ticket"] not in blob_str
        assert key not in blob_str
    # what IS recorded: size, a ticket HASH, ok/charged flags
    park_line = next(r for r in lines if r["op"] == "park" and r["ok"])
    assert park_line["size_bytes"] == len(blob)
    assert park_line["ticket_hash"] == parked["ticket_hash"]
    assert park_line["charged"] is True
    retr_line = next(r for r in lines if r["op"] == "retrieve" and r["ok"])
    assert retr_line["charged"] is False   # retrieve is free


def test_default_sink_file_has_no_contents(monkeypatch, tmp_path):
    # exercise the REAL default sink (writes the telemetry JSONL) and prove the
    # file holds no blob/ticket/key.
    path = str(tmp_path / "tele.jsonl")
    monkeypatch.setenv("NEXTMOVE_TELEMETRY_PATH", path)
    locker.set_telemetry_sink(locker._default_sink)
    key = _key()
    blob = b"FILELEVEL-MARKER-bytes-2a91"
    parked = locker.park(key, blob)
    locker.retrieve(key, parked["ticket"])
    with open(path) as f:
        raw = f.read()
    assert "locker" in raw                 # the lines were written
    assert "FILELEVEL-MARKER" not in raw
    assert base64.b64encode(blob).decode() not in raw
    assert parked["ticket"] not in raw
    assert key not in raw


def test_raw_ticket_absent_from_table():
    key = _key()
    parked = locker.park(key, b"row-inspection")
    ticket = parked["ticket"]
    with locker._conn() as c:
        rows = c.execute(
            "SELECT ticket_hash, owner_key_hash, blob, size_bytes FROM locker"
        ).fetchall()
    # the raw claim token appears in NO column; only its hash is the PK.
    for r in rows:
        for col in r:
            assert ticket != col
            assert (ticket not in col) if isinstance(col, str) else True
    # and the presented ticket rehashes to the stored PK.
    assert any(r[0] == locker._ticket_hash(ticket) for r in rows)


def test_raw_key_absent_from_table():
    key = _key()
    locker.park(key, b"owner-inspection")
    with locker._conn() as c:
        rows = c.execute("SELECT owner_key_hash FROM locker").fetchall()
    for (owner_hash,) in rows:
        assert key != owner_hash
        assert key not in owner_hash       # only the keyed hash is stored


# ─── at-rest layer: stored bytes differ from input ───────────────────────────


def test_at_rest_layer_stored_blob_differs_from_input():
    key = _key()
    blob = b"the-customers-own-ciphertext-bytes-1234567890"
    parked = locker.park(key, blob)
    with locker._conn() as c:
        row = c.execute(
            "SELECT blob FROM locker WHERE ticket_hash = ?",
            (parked["ticket_hash"],)).fetchone()
    stored = base64.b64decode(row[0])
    # AES-256-GCM is on (env key set for the suite): the stored bytes are neither
    # the input nor a substring of it, and they carry the AEAD scheme tag.
    assert stored != blob
    assert blob not in stored
    assert stored[:1] == locker._SCHEME_AESGCM
    assert parked["receipt"]["at_rest"] == "aes-256-gcm"


def test_honest_degrade_when_no_at_rest_key(monkeypatch):
    # with the server key UNSET we degrade honestly: the receipt says
    # at_rest="none" rather than claiming a layer we don't have, and the round
    # trip still works (the customer ciphertext is stored under a visible tag).
    monkeypatch.delenv("LOCKER_AT_REST_KEY", raising=False)
    key = _key()
    blob = b"degraded-path-ciphertext"
    parked = locker.park(key, blob)
    assert parked["receipt"]["at_rest"] == "none"
    with locker._conn() as c:
        row = c.execute("SELECT blob FROM locker WHERE ticket_hash = ?",
                        (parked["ticket_hash"],)).fetchone()
    stored = base64.b64decode(row[0])
    assert stored[:1] == locker._SCHEME_PLAINTEXT
    assert locker.retrieve(key, parked["ticket"])["blob"] == blob


def test_sealed_parcel_unreadable_after_key_lost(monkeypatch):
    # a parcel sealed under the env key cannot be opened once that key is gone —
    # an HONEST failure, never a silent wrong-plaintext (this is the point of the
    # at-rest layer: our DB dump alone is sealed boxes).
    monkeypatch.setenv("LOCKER_AT_REST_KEY", "ephemeral-key-abc")
    key = _key()
    parked = locker.park(key, b"sealed-under-a-key")
    monkeypatch.delenv("LOCKER_AT_REST_KEY", raising=False)
    out = locker.retrieve(key, parked["ticket"])
    assert out["ok"] is False and out["code"] == "at_rest_key_unavailable"


# ─── receipt: signed + customer-checkable content_hash ───────────────────────


def test_receipt_is_signed_and_verifiable():
    key = _key()
    parked = locker.park(key, b"receipt-me")
    receipt = parked["receipt"]
    assert receipt.get("signature")        # actually signed (ephemeral in tests)
    assert verify_receipt(receipt) is True


def test_content_hash_is_customer_recomputable():
    import hashlib
    key = _key()
    blob = b"prove-what-i-stored-without-plaintext"
    parked = locker.park(key, blob)
    # the customer holds `blob` (their ciphertext) and recomputes the same anchor
    expected = hashlib.blake2b(blob, digest_size=16).hexdigest()
    assert parked["receipt"]["content_hash"] == expected


# ─── catalog card states the published facts ─────────────────────────────────


def test_catalog_entry_states_ttl_cap_price():
    entry = locker.catalog_entry()
    assert entry["id"] == "locker"
    assert entry["size_cap_bytes"] == locker.LOCKER_MAX_BYTES
    assert entry["ttl"]["max_seconds"] == locker.LOCKER_TTL_MAX_S
    assert entry["price"]["max_price_millicents"] == locker.LOCKER_MAX_PRICE_MILLICENTS
    assert "blind" in entry["privacy"].lower()
