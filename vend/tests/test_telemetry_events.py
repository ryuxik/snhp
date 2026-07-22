"""Unit tests for the two telemetry events added by the STORE fix wave:

  - log_throttle  — one line per 429 (rate-limit reject) so throttled demand
    is countable by the R-gate instruments (GAUNTLET.md #3 instrument gap).
  - log_free_taste — one line per free negotiate/turn call, the top of the
    free->paid funnel.

Both must obey the NEXTMOVE hygiene rule: a presented api_key is stored ONLY
as its keyed repeat_key hash, never raw.
"""
import json
import os

import pytest

from vend import telemetry as _t  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_telemetry_path(tmp_path, monkeypatch):
    """Point telemetry at a FRESH per-test file and keep every helper here on
    the SAME path telemetry actually writes to.

    The old test captured a module-constant `_PATH` at import and set the env
    once, but `telemetry._path()` reads NEXTMOVE_TELEMETRY_PATH at CALL time —
    so any later-collected module that overrode the env (test_session/
    test_store set it at import) diverged the constant from where telemetry
    wrote, and these assertions read a stale file. monkeypatch.setenv restores
    the env after each test, and resolving through `_t._path()` in the helpers
    below means the writes and the reads can never point at different files."""
    p = tmp_path / "telemetry.jsonl"
    monkeypatch.setenv("NEXTMOVE_TELEMETRY_PATH", str(p))
    return p


def _records() -> list[dict]:
    path = _t._path()               # call-time resolution — matches the writer
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _reset():
    open(_t._path(), "w").close()


def test_log_throttle_keyless_shape():
    _reset()
    _t.log_throttle(scope="math_per_ip", had_key=False,
                    path="/v1/auction/bidder/optimal_bid")
    (rec,) = _records()
    assert rec["kind"] == "throttle"
    assert rec["scope"] == "math_per_ip"
    assert rec["had_key"] is False
    assert rec["path"] == "/v1/auction/bidder/optimal_bid"
    assert rec["repeat_key"] is None
    assert isinstance(rec["ts"], float)


def test_log_throttle_hashes_key_never_raw():
    _reset()
    raw = "gt_secret_token_abc123"
    _t.log_throttle(scope="math_per_key", had_key=True, path="/v1/fetch",
                    api_key=raw)
    (rec,) = _records()
    assert rec["had_key"] is True
    # repeat_key is the stable blake2b pseudonym, not the raw key.
    assert rec["repeat_key"] == _t._repeat_key(raw)
    assert rec["repeat_key"] != raw
    assert raw not in json.dumps(rec)


def test_log_throttle_repeat_key_is_stable():
    """Same key -> same repeat_key across calls (repeat measurement works)."""
    _reset()
    raw = "gt_stable_repeat_probe"
    _t.log_throttle(scope="math_per_key", had_key=True, path="/v1/x", api_key=raw)
    _t.log_throttle(scope="math_per_key", had_key=True, path="/v1/y", api_key=raw)
    a, b = _records()
    assert a["repeat_key"] == b["repeat_key"]


def test_log_free_taste_anonymous():
    _reset()
    _t.log_free_taste(None, "http")
    (rec,) = _records()
    assert rec["kind"] == "free_taste"
    assert rec["door"] == "http"
    assert rec["repeat_key"] is None


def test_log_free_taste_hashes_key_never_raw():
    _reset()
    raw = "gt_free_taste_secret"
    _t.log_free_taste(raw, "http")
    (rec,) = _records()
    assert rec["door"] == "http"
    assert rec["repeat_key"] == _t._repeat_key(raw)
    assert raw not in json.dumps(rec)
