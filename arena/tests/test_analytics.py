"""Server-side page analytics: the request middleware, the /api/hit beacon, and
the /api/stats aggregation. Privacy is part of the contract — no IPs, no query
strings, no raw user-agents — so we assert those never land in the JSONL."""
from __future__ import annotations

import importlib
import json


def _fresh_api(monkeypatch, tmp_path):
    """Reload arena.api with a throwaway data dir and no sim loop, so _HITS points
    at tmp and startup doesn't spin the world."""
    monkeypatch.setenv("ARENA_NO_RUN", "1")
    monkeypatch.setenv("ARENA_DATA_DIR", str(tmp_path))
    import arena.api as api
    importlib.reload(api)
    assert api._HITS.startswith(str(tmp_path))
    return api


def _read_hits(api):
    import os
    if not os.path.exists(api._HITS):
        return []
    with open(api._HITS) as f:
        return [json.loads(line) for line in f if line.strip()]


def test_middleware_logs_pageviews_not_assets_or_pii(monkeypatch, tmp_path):
    api = _fresh_api(monkeypatch, tmp_path)
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:
        # a real page view, with a query string that must NOT be stored
        assert client.get("/watch.html?utm_source=secret&token=abc123").status_code == 200
        # the thesis home
        assert client.get("/").status_code == 200
        # things that are NOT pageviews: health, the JSON API, a static asset
        client.get("/health")
        client.get("/api/stats")
        client.get("/nav.js")

    rows = _read_hits(api)
    paths = [r["path"] for r in rows]
    assert "/watch.html" in paths and "/" in paths          # pages counted
    assert not any(p in ("/health", "/api/stats", "/nav.js") for p in paths)  # noise excluded
    # privacy: no query strings, no IP field, only a coarse UA family
    raw = open(api._HITS).read()
    assert "utm_source" not in raw and "token=abc123" not in raw and "?" not in raw
    for r in rows:
        assert set(r) <= {"ts", "path", "ref", "ua", "src"}   # no "ip", no full UA
        assert r["ua"] in ("chrome", "safari", "firefox", "edge", "bot", "other", "unknown")


def test_api_hit_beacon_appends(monkeypatch, tmp_path):
    api = _fresh_api(monkeypatch, tmp_path)
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:
        r = client.post("/api/hit", json={"page": "/read.html"})
        assert r.status_code == 200 and r.json()["ok"] is True
        # malformed / empty bodies must not break (fail-open) and must not log
        assert client.post("/api/hit", content=b"not json").status_code == 200
        assert client.post("/api/hit", json={}).status_code == 200

    beacons = [r for r in _read_hits(api) if r.get("src") == "beacon"]
    assert len(beacons) == 1 and beacons[0]["path"] == "/read.html"


def test_api_stats_aggregates_daily_and_tolerates_legacy(monkeypatch, tmp_path):
    api = _fresh_api(monkeypatch, tmp_path)
    # seed a legacy {t,p} line (old /hit schema) plus the new schema — stats must
    # count both, bucketed by UTC day.
    with open(api._HITS, "a") as f:
        f.write(json.dumps({"t": 1_700_000_000, "p": "board"}) + "\n")
        f.write(json.dumps({"ts": 1_700_000_500, "path": "/read.html"}) + "\n")
        f.write(json.dumps({"ts": 1_700_000_600, "path": "/read.html"}) + "\n")
    from fastapi.testclient import TestClient
    with TestClient(api.app) as client:
        stats = client.get("/api/stats").json()
    assert stats["total"] >= 3
    # 1_700_000_000 → 2023-11-14 UTC
    day = stats["days"]["2023-11-14"]
    assert day["/read.html"] == 2 and day["board"] == 1
