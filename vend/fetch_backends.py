"""THE STORE — the fetch/extract slot's wholesale backends.

The fetch slot's job: one clean read of a stubborn page -> markdown. Two
health-checkable backends behind the slot contract (STORE.md §2b): Jina
Reader (r.jina.ai) and Firecrawl. Both normalize to ONE payload shape so
the slot predicate and receipt never depend on which backend served.

Cost basis is per-call in millicents (1 cent = 1000 millicents): exact where
the upstream reports usage, estimated (and flagged) otherwise (STORE.md
§2d.4/§2d.5 — exact cost on every receipt, debit only on delivery). Per-unit
wholesale RATES below are UNVERIFIED placeholders; each carries a TODO to pin
against the signed paid plan before the slot leaves PROVISIONAL. We do not
invent certainty about a vendor's current pricing.

SEAM NOTE: vend/store.py owns the canonical `BackendError` exception and
`BackendResult` dataclass; this module imports them so a fetch result IS a
store.BackendResult (settlement reads its attributes directly, isinstance
holds). The pair is re-exported below for the backend tests that import it
from here.

House rules honored: no LLM in the delivery/judgment path; key material is
never logged, echoed, or placed in a result; comments state constraints.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from vend.store import BackendError, BackendResult

__all__ = [
    "MILLICENTS_PER_CENT", "PREDICATE_ID", "PREDICATE_ID_V2",
    "BackendError", "BackendResult",
    "JinaReaderBackend", "FirecrawlBackend",
    "validate_fetch_request", "fetch_predicate_v1", "fetch_predicate_v2",
]

# 1 cent = 1000 millicents (STORE.md §Money — the store's one wallet coin).
MILLICENTS_PER_CENT = 1000

# Versioned on every receipt; bump when the predicate's meaning changes. v1 is
# non-empty-only; v2 (below) adds a conservative block-page screen. Both stay
# exported so a slot can pin either.
PREDICATE_ID = "fetch.v1"
PREDICATE_ID_V2 = "fetch.v2"

# Request admission limits — enforced BEFORE any network call.
_MAX_URL_LEN = 2048
_ALLOWED_SCHEMES = ("http", "https")

# Upstream fetches are slow (render + anti-bot); 30s is a per-call ceiling.
_HTTP_TIMEOUT_S = 30.0

# ── wholesale cost bases — UNVERIFIED PLACEHOLDERS, pin before launch ──────
# Jina Reader frames Reader-API pricing per token of returned content. The
# figure below is a stand-in derived from a public pricing-page snapshot
# (jina.ai) and is NOT our contracted per-token rate. It is a float because
# the per-token cost is sub-millicent; the final wholesale is an int
# millicent (ceil), so the money type stays integral.
# TODO(pre-launch): pin JINA_MILLICENTS_PER_TOKEN to the signed paid-plan
#   rate; until then every Jina receipt's cost basis is a guess of a guess.
JINA_MILLICENTS_PER_TOKEN = 0.2

# Jina reports token usage in a response header on paid plans. The EXACT
# header name must be confirmed against the live API; we probe a set of
# plausible names and fall back to a len/4 token estimate when none is
# present (marking the receipt estimated).
# TODO(pre-launch): confirm the real usage header from Jina's docs and
#   collapse this tuple to the one correct key.
_JINA_TOKEN_HEADER_CANDIDATES = (
    "x-total-tokens", "x-usage-tokens", "x-token-count", "x-tokens",
)

# Firecrawl bills in credits. Both numbers are PLACEHOLDERS: the base
# per-scrape credit cost and the per-credit price implied by a public plan
# ($/credit from a monthly bucket). Neither is our contracted rate.
# TODO(pre-launch): pin FIRECRAWL_CREDITS_PER_SCRAPE and
#   FIRECRAWL_MILLICENTS_PER_CREDIT against the signed plan.
FIRECRAWL_CREDITS_PER_SCRAPE = 1
FIRECRAWL_MILLICENTS_PER_CREDIT = 500

# Firecrawl may report credits consumed in the envelope; probe these keys
# (top-level, data, or data.metadata) for an exact basis before estimating.
_FIRECRAWL_CREDITS_KEY = "creditsUsed"

# ── upstream evidence passthrough (first rung; STORE.md §2d.4) ─────────────
# A WHITELIST of response headers that carry the vendor's own reference for a
# call — a request/trace id the vendor can look up in ITS OWN logs. Whitelist,
# not blocklist, so nothing sensitive rides along by accident; values are length-
# capped. This is evidence-PASSTHROUGH (a `wholesale_estimated:false` cost basis
# gains the upstream's own reference), NOT invoice proof — it does not itself
# prove the number, it lets a third party ask the vendor to confirm the call.
_UPSTREAM_REF_HEADERS = ("x-request-id", "x-trace-id", "cf-ray")
_UPSTREAM_REF_MAX_VALUE = 200


def _upstream_ref(headers: dict, usage: dict | None) -> dict | None:
    """Build the whitelisted upstream-evidence dict, or None when the upstream
    returned nothing to carry. `usage` is the vendor-reported usage figure (only
    passed when EXACT — an estimate is our own arithmetic, not the vendor's
    evidence). Mechanical: whitelisted header names + a length cap, no parsing."""
    ref: dict = {}
    for h in _UPSTREAM_REF_HEADERS:
        v = headers.get(h)
        if v:
            ref[h] = str(v)[:_UPSTREAM_REF_MAX_VALUE]
    if usage:
        ref["usage"] = usage
    return ref or None


@dataclass(frozen=True)
class _HttpResponse:
    """A completed HTTP exchange. Non-2xx is a RESPONSE here (the backend
    decides), not an exception — only transport failure raises out of the
    seam below."""
    status: int
    headers: dict                 # lower-cased keys
    text: str


def _lower_headers(raw) -> dict:
    # Header lookups downstream are case-insensitive; normalize once.
    try:
        items = raw.items()
    except AttributeError:
        items = list(raw or [])
    return {str(k).lower(): v for k, v in items}


def _http_request(*, method: str, url: str, headers: dict,
                  body: str | bytes | None = None,
                  timeout: float = _HTTP_TIMEOUT_S) -> _HttpResponse:
    """The single network seam — monkeypatch THIS in tests; zero network.

    Returns an _HttpResponse for ANY completed exchange (including 4xx/5xx).
    Raises the underlying transport error (DNS/connect/TLS/timeout) so the
    caller can convert it to a BackendError with a reason string.
    """
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return _HttpResponse(status=resp.status,
                                 headers=_lower_headers(resp.headers),
                                 text=raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        # A 4xx/5xx is a delivered response the backend must inspect, not a
        # transport failure.
        raw = e.read()
        return _HttpResponse(status=e.code,
                             headers=_lower_headers(e.headers),
                             text=raw.decode("utf-8", "replace"))


def validate_fetch_request(request) -> str:
    """Return a validated URL string, or raise ValueError.

    Enforced BEFORE any network call. We never fetch the URL ourselves —
    the upstream service does, so SSRF exposure is theirs — but a
    non-http(s) scheme is refused outright. Accepts a bare url string or a
    request dict {"url": ...}.
    """
    if isinstance(request, str):
        url = request
    elif isinstance(request, dict):
        url = request.get("url")
    else:
        raise ValueError("fetch request must be a url string or {'url': ...}")
    if not isinstance(url, str) or not url:
        raise ValueError("fetch request requires a non-empty url")
    if len(url) > _MAX_URL_LEN:
        raise ValueError(f"url exceeds {_MAX_URL_LEN} chars")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"url scheme must be one of {_ALLOWED_SCHEMES}, got "
            f"{parsed.scheme!r}")
    if not parsed.netloc:
        raise ValueError("url has no host")
    _reject_private_host(parsed.hostname)
    return url


def _reject_private_host(host: str | None) -> None:
    """Refuse localhost / *.local / *.localhost and private-or-reserved
    IP-LITERAL hosts, up front (safety-posture completion).

    Mechanical stdlib only, NO DNS: we screen the literal host string. A
    hostname that RESOLVES to a private address is the upstream vendor's
    problem — the store never resolves or fetches the url itself, so doing a
    DNS lookup here would only add a network call and a TOCTOU gap without
    closing the hole the vendor already owns. This blocks the obvious literal
    SSRF targets (127.0.0.1, ::1, 10.x, 169.254.x, localhost) cheaply and
    deterministically. `host` is urllib's parsed hostname (lower-cased,
    IPv6 brackets stripped).
    """
    if not host:
        raise ValueError("url has no host")
    low = host.lower()
    if low == "localhost" or low.endswith(".local") or low.endswith(".localhost"):
        raise ValueError(f"refusing local host {host!r}")
    try:
        ip = ipaddress.ip_address(low)
    except ValueError:
        return                     # not an IP literal → a public hostname, fine
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified):
        raise ValueError(f"refusing private/reserved IP-literal host {host!r}")


def fetch_predicate_v1(payload) -> tuple[bool, str]:
    """(ok, reason) — the fetch slot's machine-checkable success predicate.

    Mechanical only, no LLM: markdown non-empty after strip. Upstream 2xx
    is already enforced by the backend raising BackendError on non-2xx; the
    content hash is added at receipt time by the settlement engine.
    """
    md = payload.get("markdown") if isinstance(payload, dict) else None
    if not isinstance(md, str) or not md.strip():
        return False, "empty markdown"
    return True, "ok"


# A conservative block-page phrase list (GAUNTLET #6: fetch.v1 checked non-empty
# only, so a bot-block interstitial would be charged as delivered). These are
# the boilerplate of anti-bot walls, not of real articles. The screen fires ONLY
# on SHORT docs — a full-length article that happens to quote "access denied" in
# prose runs long and passes, so the list can't false-positive legitimate content.
_BLOCK_PHRASES = (
    "access denied",
    "enable javascript and cookies",
    "just a moment",
    "verify you are human",
    "captcha",
)
_BLOCK_MAX_LEN = 500          # only docs shorter than this are block-screened


def fetch_predicate_v2(payload) -> tuple[bool, str]:
    """(ok, reason) — fetch.v2: non-empty markdown AND not a short block page.

    Mechanical only, no LLM (house rule): the same non-empty check as v1, plus a
    block-page screen that fires ONLY when the doc is short (< _BLOCK_MAX_LEN
    chars) AND contains a known anti-bot phrase (case-insensitive). The
    short-doc gate is the false-positive guard — a long legitimate article that
    mentions one of these phrases is well over the length bound and passes; only
    a terse interstitial ("Just a moment…", a captcha wall) is caught, so the
    store doesn't bill for a bot-block dressed up as delivery."""
    md = payload.get("markdown") if isinstance(payload, dict) else None
    if not isinstance(md, str) or not md.strip():
        return False, "empty markdown"
    stripped = md.strip()
    if len(stripped) < _BLOCK_MAX_LEN:
        low = stripped.lower()
        for phrase in _BLOCK_PHRASES:
            if phrase in low:
                return False, f"block_page:{phrase}"
    return True, "ok"


class JinaReaderBackend:
    """id "jina-reader": GET https://r.jina.ai/<url>, Bearer $JINA_API_KEY,
    Accept text/plain (Jina returns markdown)."""

    id = "jina-reader"
    _ENDPOINT = "https://r.jina.ai/"
    _ENV_KEY = "JINA_API_KEY"

    def available(self) -> bool:
        return bool(os.environ.get(self._ENV_KEY, "").strip())

    def call(self, request: dict) -> BackendResult:
        url = validate_fetch_request(request)          # before any network
        api_key = os.environ.get(self._ENV_KEY, "").strip()
        if not api_key:
            raise BackendError("jina-reader unavailable: JINA_API_KEY unset")
        headers = {
            "Authorization": f"Bearer {api_key}",      # never logged/echoed
            "Accept": "text/plain",
        }
        try:
            resp = _http_request(method="GET", url=self._ENDPOINT + url,
                                 headers=headers)
        except (urllib.error.URLError, OSError) as e:
            # Transport failure: reason names the error TYPE, never the key.
            raise BackendError(
                f"jina-reader transport error: {type(e).__name__}") from e
        if not (200 <= resp.status < 300):
            raise BackendError(f"jina-reader upstream status {resp.status}")
        markdown = resp.text
        if not markdown.strip():
            raise BackendError("jina-reader returned empty body")
        tokens, estimated = self._tokens(resp, markdown)
        wholesale = math.ceil(tokens * JINA_MILLICENTS_PER_TOKEN)
        payload = {
            "markdown": markdown,
            "url": url,
            # text/plain mode carries no structured resolved-url or title;
            # None is honest (the schema field is Optional).
            "final_url": None,
            "title": None,
        }
        # Carry the vendor's own evidence when present: the request id + the
        # token count ONLY when it was reported (exact), never our estimate.
        ref = _upstream_ref(resp.headers,
                            {"tokens": tokens} if not estimated else None)
        return BackendResult(
            payload=payload,
            wholesale_millicents=wholesale,
            wholesale_estimated=estimated,
            backend_id=self.id,
            meta={"status": resp.status, "tokens": tokens,
                  "cost_estimated": estimated, "upstream_ref": ref},
        )

    @staticmethod
    def _tokens(resp: _HttpResponse, text: str) -> tuple[int, bool]:
        # Exact when a usage header is present; else estimate ~4 chars/token.
        for h in _JINA_TOKEN_HEADER_CANDIDATES:
            v = resp.headers.get(h)
            if v is None:
                continue
            try:
                n = int(str(v).strip())
            except ValueError:
                continue
            if n >= 0:
                return n, False
        return math.ceil(len(text) / 4), True


class FirecrawlBackend:
    """id "firecrawl": POST https://api.firecrawl.dev/v1/scrape
    {url, formats:["markdown"]}, Bearer $FIRECRAWL_API_KEY."""

    id = "firecrawl"
    _ENDPOINT = "https://api.firecrawl.dev/v1/scrape"
    _ENV_KEY = "FIRECRAWL_API_KEY"

    def available(self) -> bool:
        return bool(os.environ.get(self._ENV_KEY, "").strip())

    def call(self, request: dict) -> BackendResult:
        url = validate_fetch_request(request)          # before any network
        api_key = os.environ.get(self._ENV_KEY, "").strip()
        if not api_key:
            raise BackendError(
                "firecrawl unavailable: FIRECRAWL_API_KEY unset")
        body = json.dumps({"url": url, "formats": ["markdown"]})
        headers = {
            "Authorization": f"Bearer {api_key}",      # never logged/echoed
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = _http_request(method="POST", url=self._ENDPOINT,
                                 headers=headers, body=body)
        except (urllib.error.URLError, OSError) as e:
            raise BackendError(
                f"firecrawl transport error: {type(e).__name__}") from e
        if not (200 <= resp.status < 300):
            raise BackendError(f"firecrawl upstream status {resp.status}")
        # Parse the v1 envelope defensively: {success, data:{markdown,
        # metadata...}}.
        try:
            env = json.loads(resp.text) if resp.text.strip() else {}
        except ValueError as e:
            raise BackendError("firecrawl returned non-JSON body") from e
        if not isinstance(env, dict) or env.get("success") is False:
            raise BackendError("firecrawl reported failure")
        data = env.get("data")
        if not isinstance(data, dict):
            raise BackendError("firecrawl envelope missing data")
        markdown = data.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise BackendError("firecrawl returned empty markdown")
        meta_doc = data.get("metadata")
        if not isinstance(meta_doc, dict):
            meta_doc = {}
        credits, estimated = self._credits(env, data, meta_doc)
        wholesale = math.ceil(credits * FIRECRAWL_MILLICENTS_PER_CREDIT)
        payload = {
            "markdown": markdown,
            "url": url,
            # Firecrawl reports the resolved URL + title in metadata.
            "final_url": (meta_doc.get("url")
                          or meta_doc.get("sourceURL") or None),
            "title": meta_doc.get("title") or None,
        }
        # Carry the vendor's own evidence when present: the request id + the
        # credits consumed ONLY when the envelope reported them (exact).
        ref = _upstream_ref(resp.headers,
                            {"credits": credits} if not estimated else None)
        return BackendResult(
            payload=payload,
            wholesale_millicents=wholesale,
            wholesale_estimated=estimated,
            backend_id=self.id,
            meta={"status": resp.status, "credits": credits,
                  "cost_estimated": estimated, "upstream_ref": ref},
        )

    @staticmethod
    def _credits(env: dict, data: dict, meta_doc: dict) -> tuple[float, bool]:
        # Exact when the envelope reports credits consumed anywhere; else
        # assume the base per-scrape cost and flag the receipt estimated.
        for src in (env, data, meta_doc):
            v = src.get(_FIRECRAWL_CREDITS_KEY)
            if v is None:
                continue
            try:
                n = float(v)
            except (ValueError, TypeError):
                continue
            if n >= 0:
                return n, False
        return float(FIRECRAWL_CREDITS_PER_SCRAPE), True
