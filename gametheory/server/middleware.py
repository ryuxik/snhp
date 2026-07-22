"""
HTTP middleware for the SNHP API server.

Three concerns, three middlewares:

  1. BodySizeLimit — reject requests with `Content-Length` > MAX_BODY_BYTES
     before Starlette buffers the payload. Without this, a single 1GB
     POST can OOM the 512MB Fly box.

  2. RateLimit — in-memory token bucket. Two lanes on `/v1/*`, decided by
     whether the request PRESENTS a key credential (a `gt_*` token in either
     `Authorization: Bearer` or `X-API-Key`):
       - keyless  -> 60/min per IP   (the free floor)
       - keyed    -> 600/min per key (its OWN lane; the per-IP floor is
                     SKIPPED, so paid traffic never starves on the free
                     bucket — GAUNTLET.md #3)
     `/v1/keys` (issuance, no key yet) is 10/hour per IP. Body-only keys are
     invisible here (middleware never parses bodies) and so fall to the per-IP
     floor — documented on the affected endpoints. Single-instance deploy
     assumption; for multi-replica swap for a Redis-backed limiter (see
     docs/operations.md, when written).

  3. SecurityHeaders — add HSTS, frame-ancestors deny, content-type
     sniffing block, referrer policy. Cloudflare is DNS-only on api.snhp.dev
     so we own these.

All three are pure ASGI middleware (FastAPI auto-discovers via
`app.add_middleware(...)`). State (token buckets) is module-global; the
process restart resets it. That's fine for short-lived rate limits.
"""
from __future__ import annotations

import math
import time
from collections import defaultdict
from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


# ─── Body size limit ────────────────────────────────────────────────────────


MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB — generous for our payloads


class BodySizeLimit(BaseHTTPMiddleware):
    """Reject requests whose declared Content-Length exceeds MAX_BODY_BYTES.

    Note: this trusts the Content-Length header. A determined attacker
    can chunk-encode and bypass it. For real protection, also enable
    Cloudflare proxy mode (orange cloud) which caps payloads at 100MB
    by default, or front with a hard ASGI body-streamer that counts bytes.
    """

    async def dispatch(self, request: Request,
                        call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                size = int(cl)
            except ValueError:
                return JSONResponse(
                    {"detail": "Malformed Content-Length header"}, status_code=400,
                )
            if size > MAX_BODY_BYTES:
                return JSONResponse(
                    {"detail": f"Request body too large (max {MAX_BODY_BYTES} bytes)"},
                    status_code=413,
                )
        return await call_next(request)


# ─── Rate limiting (in-memory token bucket) ─────────────────────────────────


class _TokenBucket:
    """Per-key bucket; refills `rate` tokens per `period_seconds`.

    Not thread-safe in the strict sense — uvicorn under the default
    worker model runs one event loop per process, so concurrent requests
    don't interleave dispatch midway. Concurrent reads/writes from
    different connections still mostly work; rare double-takes under
    pathological scheduling get tolerated.
    """

    __slots__ = ("capacity", "rate_per_sec", "tokens", "last_refill")

    def __init__(self, capacity: int, rate_per_sec: float):
        self.capacity = capacity
        self.rate_per_sec = rate_per_sec
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    def take(self, n: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


# (capacity, rate_per_sec) per scope.
_LIMITS = {
    # /v1/keys is unauthenticated. Cap aggressively per-IP so an attacker
    # can't fill the keys table.
    "issue_key_per_ip": (10, 10 / 3600),    # 10/hour bucket, refills slowly
    # Math endpoints. Per-IP fallback when no key supplied; per-key when key present.
    "math_per_ip":      (60, 60 / 60),      # 60/minute bucket
    "math_per_key":     (600, 600 / 60),    # 600/minute bucket (matches catalog claim)
    # Per-IP BACKSTOP for KEYED traffic. bearer_api_key is shape-only (no DB), so a
    # unique fake `gt_` token per request mints a fresh, full 600/min per-key lane
    # every time — without a per-IP ceiling that fan-out is UNBOUNDED from one IP
    # (it evaded the 60/min keyless floor entirely). 3000/min is chosen as a hard
    # per-IP cap on total keyed volume that sits WELL ABOVE any single key's 600/min
    # lane (5x): one real paying key — or even a handful of real keys behind one NAT
    # — never trips it (GAUNTLET.md #3: paid traffic must not be floored), yet
    # unbounded fake-key fan-out from one IP is bounded to 3000/min.
    "math_keyed_per_ip": (3000, 3000 / 60), # 3000/minute per-IP backstop (keyed)
    # First-strike commit/reveal — moderately rate-limited per IP regardless.
    "first_strike_per_ip": (30, 30 / 60),
}

_BUCKETS: dict[tuple[str, str], _TokenBucket] = {}


def _bucket_for(scope: str, key: str) -> _TokenBucket:
    cache_key = (scope, key)
    bucket = _BUCKETS.get(cache_key)
    if bucket is None:
        cap, rate = _LIMITS[scope]
        bucket = _TokenBucket(cap, rate)
        _BUCKETS[cache_key] = bucket
    return bucket


def _client_ip(request: Request) -> str:
    """Best-effort IP extraction. Fly forwards the real client IP via
    Fly-Client-IP; Cloudflare uses CF-Connecting-IP. Trust Fly's header
    because requests come through Fly Proxy."""
    for h in ("fly-client-ip", "cf-connecting-ip", "x-forwarded-for"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def bearer_api_key(request: Request) -> str | None:
    """Extract a presented `gt_*` API key from EITHER
    `Authorization: Bearer gt_*` OR `X-API-Key: gt_*` (Authorization wins if
    both are present). None if neither is well-formed.

    Single source of truth — middleware (rate limit) and handlers (auth,
    telemetry, GDPR) both call this so they agree on what counts as a key.
    Divergence here would be security-relevant. Wave 1 shipped X-API-Key on
    /v1/billing/balance; accepting both header forms everywhere spares agents
    from juggling two schemes.

    HOT-PATH CONTRACT: this checks the `gt_` SHAPE only, never the DB — it runs
    on every request for the rate limiter. A syntactically-valid but unknown
    token is returned as-is; the endpoint still 401s it, and letting a bogus
    token occupy its own per-key bucket costs nothing (one dict entry keyed on
    the token string). So a fake key can never borrow the per-IP free floor,
    and can never exhaust a real key's bucket.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token.startswith("gt_"):
            return token
    xkey = request.headers.get("x-api-key", "").strip()
    if xkey.startswith("gt_"):
        return xkey
    return None


class RateLimit(BaseHTTPMiddleware):
    async def dispatch(self, request: Request,
                        call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        ip = _client_ip(request)

        # /v1/keys: per-IP only (no key yet). Aggressive cap.
        if path == "/v1/keys" and request.method == "POST":
            b = _bucket_for("issue_key_per_ip", ip)
            if not b.take():
                _log_throttle("issue_key_per_ip", had_key=False, path=path, key=None)
                return _ratelimit_response("issue_key_per_ip", b)

        # First-strike write paths: per-IP cap independent of key.
        elif path in ("/v1/negotiation/declare_first_strike",
                       "/v1/negotiation/reveal_first_strike"):
            b = _bucket_for("first_strike_per_ip", ip)
            if not b.take():
                key = bearer_api_key(request)
                _log_throttle("first_strike_per_ip", had_key=key is not None,
                              path=path, key=key)
                return _ratelimit_response("first_strike_per_ip", b)

        # All other /v1/* endpoints: TWO lanes, chosen by whether a key
        # credential is presented (header only — bodies are never parsed here).
        elif path.startswith("/v1/"):
            key = bearer_api_key(request)
            if key is not None:
                # Keyed lane: the 600/min per-key bucket. A real credential buys its
                # own lane and MUST NOT be throttled by the shared 60/min per-IP FREE
                # floor — that floor-throttling of paid traffic was GAUNTLET.md #3.
                # Bucketed on the token STRING (no DB hit; see bearer_api_key's
                # hot-path contract).
                b = _bucket_for("math_per_key", key)
                if not b.take():
                    _log_throttle("math_per_key", had_key=True, path=path, key=key)
                    return _ratelimit_response("math_per_key", b)
                # AND a much higher per-IP BACKSTOP. bearer_api_key is shape-only, so
                # a unique fake `gt_` token per request would otherwise mint unlimited
                # fresh 600/min lanes and fan out unbounded from one IP (bypassing the
                # keyless floor). The 3000/min backstop bounds total keyed volume per
                # IP without touching a single real key's 600/min lane (3000 >> 600).
                ipb = _bucket_for("math_keyed_per_ip", ip)
                if not ipb.take():
                    _log_throttle("math_keyed_per_ip", had_key=True, path=path, key=key)
                    return _ratelimit_response("math_keyed_per_ip", ipb)
            else:
                # Keyless lane: the 60/min per-IP free floor. Body-only keys land
                # here too (middleware can't see them) — documented per-endpoint.
                b = _bucket_for("math_per_ip", ip)
                if not b.take():
                    _log_throttle("math_per_ip", had_key=False, path=path, key=None)
                    return _ratelimit_response("math_per_ip", b)

        return await call_next(request)


def _log_throttle(scope: str, *, had_key: bool, path: str, key: str | None) -> None:
    """Best-effort throttle telemetry: one line per 429 so the referendum
    instruments can SEE demand that got rate-limited (429'd calls never reach
    slot telemetry — GAUNTLET.md #3 instrument gap). vend is optional (not in
    the PyPI wheel), so the import is lazy and ANY failure is swallowed:
    telemetry must never break a request path. The raw key is handed to the
    logger only to be hashed there (repeat_key), never stored raw."""
    try:
        from vend import telemetry as _vt
        _vt.log_throttle(scope=scope, had_key=had_key, path=path, api_key=key)
    except Exception:
        pass


def _ratelimit_response(scope: str, bucket: "_TokenBucket | None" = None) -> JSONResponse:
    cap, rate = _LIMITS[scope]
    # Retry-After = whole seconds until at least one token is available. When we
    # have the bucket, compute it from the ACTUAL deficit — (1 - tokens)/rate —
    # so the number reflects this caller's real wait, not a constant. Round UP
    # (ceil) so we never invite a retry before a token exists, and floor at 1s
    # (Retry-After is integer seconds; 0 would license a busy-loop). Without a
    # bucket, fall back to the empty-bucket upper bound 1/rate.
    if bucket is not None and bucket.rate_per_sec > 0:
        deficit = max(0.0, 1.0 - bucket.tokens)
        secs = deficit / bucket.rate_per_sec
    else:
        secs = (1.0 / rate) if rate > 0 else 1.0
    retry_after = max(1, math.ceil(secs))
    return JSONResponse(
        {"detail": (f"Rate limit exceeded ({scope}: {cap} requests / "
                     f"{int(cap / rate)}s window)")},
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )


# ─── Security headers ───────────────────────────────────────────────────────


_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request,
                        call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response
