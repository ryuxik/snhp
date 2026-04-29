"""
HTTP middleware for the SNHP API server.

Three concerns, three middlewares:

  1. BodySizeLimit — reject requests with `Content-Length` > MAX_BODY_BYTES
     before Starlette buffers the payload. Without this, a single 1GB
     POST can OOM the 512MB Fly box.

  2. RateLimit — in-memory token bucket per-IP for the
     un-authenticated `/v1/keys` endpoint, and per-key for everything
     else. Single-instance deploy assumption; for multi-replica swap
     for a Redis-backed limiter (see docs/operations.md, when written).

  3. SecurityHeaders — add HSTS, frame-ancestors deny, content-type
     sniffing block, referrer policy. Cloudflare is DNS-only on api.snhp.dev
     so we own these.

All three are pure ASGI middleware (FastAPI auto-discovers via
`app.add_middleware(...)`). State (token buckets) is module-global; the
process restart resets it. That's fine for short-lived rate limits.
"""
from __future__ import annotations

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
    """Extract a `gt_*` bearer token from the Authorization header. None if
    absent. Single source of truth — middleware (rate limit) and handlers
    (telemetry, GDPR) both call this so they agree on what counts as a
    valid bearer token. Divergence here would be security-relevant.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token.startswith("gt_"):
            return token
    return None


class RateLimit(BaseHTTPMiddleware):
    async def dispatch(self, request: Request,
                        call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        ip = _client_ip(request)

        # /v1/keys: per-IP only (no key yet). Aggressive cap.
        if path == "/v1/keys" and request.method == "POST":
            if not _bucket_for("issue_key_per_ip", ip).take():
                return _ratelimit_response("issue_key_per_ip")

        # First-strike write paths: per-IP cap independent of key.
        elif path in ("/v1/negotiation/declare_first_strike",
                       "/v1/negotiation/reveal_first_strike"):
            if not _bucket_for("first_strike_per_ip", ip).take():
                return _ratelimit_response("first_strike_per_ip")

        # All other /v1/* endpoints: per-IP minimum + per-key bonus when key present.
        elif path.startswith("/v1/"):
            if not _bucket_for("math_per_ip", ip).take():
                return _ratelimit_response("math_per_ip")
            key = bearer_api_key(request)
            if key is not None and not _bucket_for("math_per_key", key).take():
                return _ratelimit_response("math_per_key")

        return await call_next(request)


def _ratelimit_response(scope: str) -> JSONResponse:
    cap, rate = _LIMITS[scope]
    return JSONResponse(
        {"detail": (f"Rate limit exceeded ({scope}: {cap} requests / "
                     f"{int(cap / rate)}s window)")},
        status_code=429,
        headers={"Retry-After": str(max(1, int(1 / rate)))},
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
