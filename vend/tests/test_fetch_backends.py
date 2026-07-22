"""Fetch-slot backend tests — HTTP fully mocked, zero network.

Every test monkeypatches vend.fetch_backends._http_request (the single
network seam); nothing here opens a socket. Coverage mirrors the fetch
backend contract: happy path + normalized payload shape, non-2xx,
empty body, transport error, missing key (available() False), cost-basis
exact-vs-estimated flagging, url validation, predicate pass/fail, and the
no-key-material-in-results guard.
"""
import json
import math
import urllib.error

import pytest

import vend.fetch_backends as fb
from vend.fetch_backends import (
    BackendError, BackendResult, FirecrawlBackend, JinaReaderBackend,
    PREDICATE_ID, PREDICATE_ID_V2, fetch_predicate_v1, fetch_predicate_v2,
    validate_fetch_request,
)


def _resp(status=200, headers=None, text=""):
    return fb._HttpResponse(
        status=status,
        headers={k.lower(): v for k, v in (headers or {}).items()},
        text=text)


def _patch_http(monkeypatch, fn):
    monkeypatch.setattr(fb, "_http_request", fn)


# ── Jina: happy path + normalized payload ────────────────────────────────────

def test_jina_happy_path_payload_shape(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "test-key")
    captured = {}

    def fake(**kw):
        captured.update(kw)
        return _resp(200, {"x-total-tokens": "1234"}, "# Title\n\nbody text")

    _patch_http(monkeypatch, fake)
    res = JinaReaderBackend().call({"url": "https://example.com/a"})

    assert isinstance(res, BackendResult)
    assert res.backend_id == "jina-reader"
    assert set(res.payload) == {"markdown", "url", "final_url", "title"}
    assert res.payload["markdown"].startswith("# Title")
    assert res.payload["url"] == "https://example.com/a"
    assert res.payload["final_url"] is None      # text/plain carries none
    assert res.payload["title"] is None
    # exact cost from the usage header
    assert res.wholesale_estimated is False
    assert res.wholesale_millicents == math.ceil(1234 * fb.JINA_MILLICENTS_PER_TOKEN)
    assert isinstance(res.wholesale_millicents, int)
    # request shape: r.jina.ai/<url>, bearer + text/plain
    assert captured["url"] == "https://r.jina.ai/https://example.com/a"
    assert captured["method"] == "GET"
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert captured["headers"]["Accept"] == "text/plain"


def test_jina_estimated_cost_when_no_usage_header(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")
    text = "x" * 400        # ~100 tokens at 4 chars/token
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, text))
    res = JinaReaderBackend().call({"url": "https://example.com"})
    assert res.wholesale_estimated is True
    assert res.meta["tokens"] == math.ceil(len(text) / 4)
    assert res.wholesale_millicents == math.ceil(
        math.ceil(len(text) / 4) * fb.JINA_MILLICENTS_PER_TOKEN)


def test_jina_non_2xx_raises(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")
    _patch_http(monkeypatch, lambda **kw: _resp(429, {}, "rate limited"))
    with pytest.raises(BackendError, match="429"):
        JinaReaderBackend().call({"url": "https://example.com"})


def test_jina_empty_body_raises(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, "   \n  "))
    with pytest.raises(BackendError, match="empty"):
        JinaReaderBackend().call({"url": "https://example.com"})


def test_jina_transport_error_raises(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")

    def boom(**kw):
        raise urllib.error.URLError("dns failure")

    _patch_http(monkeypatch, boom)
    with pytest.raises(BackendError, match="transport"):
        JinaReaderBackend().call({"url": "https://example.com"})


def test_jina_available_requires_nonempty_key(monkeypatch):
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    assert JinaReaderBackend().available() is False
    monkeypatch.setenv("JINA_API_KEY", "   ")        # blank counts as unset
    assert JinaReaderBackend().available() is False
    monkeypatch.setenv("JINA_API_KEY", "x")
    assert JinaReaderBackend().available() is True


def test_jina_call_without_key_raises(monkeypatch):
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    with pytest.raises(BackendError, match="JINA_API_KEY"):
        JinaReaderBackend().call({"url": "https://example.com"})


# ── Firecrawl: happy path + normalized payload ───────────────────────────────

def test_firecrawl_happy_path_payload_shape(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-key")
    body = json.dumps({
        "success": True,
        "data": {
            "markdown": "# Hello\n\nworld",
            "metadata": {"title": "Hello Page",
                         "sourceURL": "https://example.com/x",
                         "url": "https://example.com/final",
                         "creditsUsed": 3},
        },
    })
    captured = {}

    def fake(**kw):
        captured.update(kw)
        return _resp(200, {}, body)

    _patch_http(monkeypatch, fake)
    res = FirecrawlBackend().call({"url": "https://example.com/x"})

    assert res.backend_id == "firecrawl"
    assert set(res.payload) == {"markdown", "url", "final_url", "title"}
    assert res.payload["markdown"].startswith("# Hello")
    assert res.payload["title"] == "Hello Page"
    assert res.payload["final_url"] == "https://example.com/final"
    assert res.payload["url"] == "https://example.com/x"
    # exact credits from the envelope
    assert res.wholesale_estimated is False
    assert res.wholesale_millicents == math.ceil(3 * fb.FIRECRAWL_MILLICENTS_PER_CREDIT)
    assert isinstance(res.wholesale_millicents, int)
    # POST body carried the v1 scrape shape
    sent = json.loads(captured["body"])
    assert sent == {"url": "https://example.com/x", "formats": ["markdown"]}
    assert captured["method"] == "POST"


def test_firecrawl_estimated_cost_when_no_credits_reported(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    body = json.dumps({"success": True,
                       "data": {"markdown": "content here", "metadata": {}}})
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, body))
    res = FirecrawlBackend().call({"url": "https://example.com"})
    assert res.wholesale_estimated is True
    assert res.wholesale_millicents == math.ceil(
        fb.FIRECRAWL_CREDITS_PER_SCRAPE * fb.FIRECRAWL_MILLICENTS_PER_CREDIT)
    assert res.payload["title"] is None
    assert res.payload["final_url"] is None


def test_firecrawl_non_2xx_raises(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    _patch_http(monkeypatch, lambda **kw: _resp(500, {}, "err"))
    with pytest.raises(BackendError, match="500"):
        FirecrawlBackend().call({"url": "https://example.com"})


def test_firecrawl_empty_markdown_raises(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    body = json.dumps({"success": True,
                       "data": {"markdown": "   ", "metadata": {}}})
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, body))
    with pytest.raises(BackendError, match="empty"):
        FirecrawlBackend().call({"url": "https://example.com"})


def test_firecrawl_success_false_raises(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    body = json.dumps({"success": False, "error": "blocked"})
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, body))
    with pytest.raises(BackendError, match="failure"):
        FirecrawlBackend().call({"url": "https://example.com"})


def test_firecrawl_non_json_raises(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, "<html>nope</html>"))
    with pytest.raises(BackendError, match="non-JSON"):
        FirecrawlBackend().call({"url": "https://example.com"})


def test_firecrawl_available_requires_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    assert FirecrawlBackend().available() is False
    monkeypatch.setenv("FIRECRAWL_API_KEY", "x")
    assert FirecrawlBackend().available() is True


# ── url validation (before any network) ──────────────────────────────────────

def test_validate_rejects_bad_scheme():
    with pytest.raises(ValueError, match="scheme"):
        validate_fetch_request({"url": "ftp://example.com/file"})
    with pytest.raises(ValueError, match="scheme"):
        validate_fetch_request("file:///etc/passwd")


def test_validate_rejects_garbage():
    with pytest.raises(ValueError):
        validate_fetch_request("not a url")
    with pytest.raises(ValueError):
        validate_fetch_request({"url": ""})
    with pytest.raises(ValueError):
        validate_fetch_request({})
    with pytest.raises(ValueError):
        validate_fetch_request(123)


def test_validate_rejects_oversize():
    long = "https://example.com/" + "a" * 3000
    with pytest.raises(ValueError, match="2048|exceeds"):
        validate_fetch_request(long)


def test_validate_accepts_http_and_https():
    assert validate_fetch_request("https://example.com/x") == "https://example.com/x"
    assert validate_fetch_request({"url": "http://example.com"}) == "http://example.com"


def test_call_validates_before_network(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")

    def must_not_run(**kw):
        raise AssertionError("network reached despite invalid url")

    _patch_http(monkeypatch, must_not_run)
    with pytest.raises(ValueError):
        JinaReaderBackend().call({"url": "ftp://example.com"})


# ── predicate ────────────────────────────────────────────────────────────────

def test_predicate_pass_and_fail():
    ok, _ = fetch_predicate_v1({"markdown": "content"})
    assert ok is True
    bad, reason = fetch_predicate_v1({"markdown": "   "})
    assert bad is False and reason
    assert fetch_predicate_v1({"markdown": None})[0] is False
    assert fetch_predicate_v1({})[0] is False
    assert fetch_predicate_v1("not a dict")[0] is False


def test_predicate_id_constant():
    assert PREDICATE_ID == "fetch.v1"
    assert PREDICATE_ID_V2 == "fetch.v2"


# ── predicate v2: block-page screen (GAUNTLET #6) ────────────────────────────

def test_v2_catches_short_block_page():
    # a terse anti-bot interstitial is caught → uncharged non-delivery
    ok, reason = fetch_predicate_v2({"markdown": "Just a moment...\nPlease wait"})
    assert ok is False and reason.startswith("block_page:")
    for wall in ("Access Denied", "verify you are human",
                 "Please enable JavaScript and cookies to continue",
                 "complete the CAPTCHA"):
        assert fetch_predicate_v2({"markdown": wall})[0] is False


def test_v2_passes_long_article_that_mentions_a_phrase():
    # a full-length article that merely QUOTES "access denied" in prose runs well
    # past the short-doc bound, so it is NOT a false positive.
    article = ("# On refusals\n\n" + "The server said access denied. " * 60)
    assert len(article) >= 500
    ok, reason = fetch_predicate_v2({"markdown": article})
    assert ok is True and reason == "ok"


def test_v2_empty_still_fails_and_matches_v1_on_clean_docs():
    assert fetch_predicate_v2({"markdown": "   "})[0] is False
    assert fetch_predicate_v2({})[0] is False
    assert fetch_predicate_v2("not a dict")[0] is False
    # a clean short doc passes both v1 and v2
    clean = {"markdown": "# Real page\n\nactual content here"}
    assert fetch_predicate_v1(clean)[0] is True
    assert fetch_predicate_v2(clean)[0] is True


# ── safety posture: private / localhost hosts refused up front ───────────────

def test_validate_rejects_localhost_and_local_hosts():
    for bad in ("http://localhost/x", "https://LOCALHOST:8080/y",
                "http://printer.local/status", "http://foo.localhost/z"):
        with pytest.raises(ValueError, match="local"):
            validate_fetch_request(bad)


def test_validate_rejects_private_and_reserved_ip_literals():
    for bad in ("http://127.0.0.1/x", "http://10.0.0.5/y",
                "http://192.168.1.1/z", "http://169.254.169.254/latest/meta-data",
                "http://[::1]/x", "http://0.0.0.0/y"):
        with pytest.raises(ValueError, match="private|reserved|local"):
            validate_fetch_request(bad)


def test_validate_still_accepts_public_hosts_and_public_ip():
    assert validate_fetch_request("https://example.com/a") == "https://example.com/a"
    # a public IP literal is fine (no DNS, just a private/reserved screen)
    assert validate_fetch_request("http://93.184.216.34/") == "http://93.184.216.34/"


# ── upstream evidence passthrough (whitelisted; first rung) ──────────────────

def test_jina_upstream_ref_present_when_headers_carry_a_request_id(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")
    # exact tokens header + a request id → both ride along as evidence
    _patch_http(monkeypatch, lambda **kw: _resp(
        200, {"x-total-tokens": "500", "x-request-id": "jina-req-9"}, "# hi\n\nbody"))
    res = JinaReaderBackend().call({"url": "https://example.com"})
    assert res.wholesale_estimated is False
    ref = res.meta["upstream_ref"]
    assert ref["x-request-id"] == "jina-req-9"
    assert ref["usage"] == {"tokens": 500}          # vendor-reported, exact only


def test_jina_upstream_ref_absent_when_no_evidence_headers(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")
    # no request id AND estimated cost → nothing the VENDOR asserted → None
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, "x" * 40))
    res = JinaReaderBackend().call({"url": "https://example.com"})
    assert res.wholesale_estimated is True
    assert res.meta["upstream_ref"] is None         # no usage (estimate isn't evidence)


def test_firecrawl_upstream_ref_present_and_absent(monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "k")
    # present: a cf-ray header + exact credits from the envelope
    body = json.dumps({"success": True,
                       "data": {"markdown": "# x\n\ny",
                                "metadata": {"creditsUsed": 2}}})
    _patch_http(monkeypatch, lambda **kw: _resp(200, {"cf-ray": "abc-DFW"}, body))
    res = FirecrawlBackend().call({"url": "https://example.com"})
    assert res.meta["upstream_ref"] == {"cf-ray": "abc-DFW",
                                        "usage": {"credits": 2.0}}
    # absent: no whitelisted header and estimated credits → None
    body2 = json.dumps({"success": True,
                        "data": {"markdown": "# x\n\ny", "metadata": {}}})
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, body2))
    res2 = FirecrawlBackend().call({"url": "https://example.com"})
    assert res2.wholesale_estimated is True
    assert res2.meta["upstream_ref"] is None


def test_upstream_ref_only_whitelisted_headers_and_capped(monkeypatch):
    monkeypatch.setenv("JINA_API_KEY", "k")
    # a non-whitelisted header (set-cookie) must NOT ride along; the value cap holds
    _patch_http(monkeypatch, lambda **kw: _resp(
        200, {"x-request-id": "r" * 500, "set-cookie": "sid=secret"},
        "# hi\n\nbody"))
    ref = JinaReaderBackend().call({"url": "https://example.com"}).meta["upstream_ref"]
    assert "set-cookie" not in ref                   # whitelist, not blocklist
    assert len(ref["x-request-id"]) == fb._UPSTREAM_REF_MAX_VALUE  # length-capped


# ── key material never surfaces in a result ──────────────────────────────────

def test_key_never_in_result(monkeypatch):
    secret = "super-secret-key-value"
    monkeypatch.setenv("JINA_API_KEY", secret)
    _patch_http(monkeypatch, lambda **kw: _resp(200, {}, "body"))
    res = JinaReaderBackend().call({"url": "https://example.com"})
    assert secret not in json.dumps(res.meta)
    assert secret not in json.dumps(res.payload)
