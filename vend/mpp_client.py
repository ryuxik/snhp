"""
mpp_client.py — a tiny, dependency-free reference client for paying an MPP
(Machine Payments Protocol) endpoint with a Stripe Shared Payment Token (SPT).

SPDX-License-Identifier: MIT
Copyright (c) 2026 SNHP. Permission is hereby granted, free of charge, to any
person obtaining a copy of this file, to use, copy, modify, publish, and
distribute it without restriction. Provided "AS IS", without warranty of any
kind. Copy-paste it, vendor it, publish it — it depends on nothing but the
Python standard library.

WHAT THIS IS
    The buyer half of the MPP handshake, in ~150 lines of stdlib `urllib`. Point
    it at an MPP resource, hand it a Shared Payment Token you already minted, and
    it runs the whole 402 -> authorize -> retry -> receipt dance:

        1. POST the resource with no credential            -> server answers 402
        2. parse the signed `WWW-Authenticate: Payment` challenge
        3. build an `Authorization: Payment` credential carrying your SPT
        4. retry                                           -> server settles, 200
        5. read the resource body + the `Payment-Receipt` header

    The wire format mirrors the SNHP server's own (gametheory/server/mpp.py):
    the challenge params are carried through verbatim (the base64url `request`
    string is never re-canonicalized here), so the HMAC-bound challenge id the
    server minted still verifies on the retry. A credential this client builds is
    accepted byte-for-byte by mpp.parse_credential + mpp.verify_challenge.

MINT-AGNOSTIC — WHO MINTS THE SPT
    Minting the SPT is the BUYER PLATFORM's job, not this client's and not the
    store's. An SPT is a scoped, delegated payment credential the buyer (or the
    buyer's agent platform — a Link/ACP-integrated wallet) grants, carrying a
    currency, a max amount, and an expiry. The store NEVER sees the buyer's card;
    it only redeems a token the buyer scoped to it. This client takes that token
    as an opaque string (`spt_token`) and spends it. If your platform cannot yet
    mint an SPT, use the store's human-clickable Checkout top-up instead (see the
    acceptance manifest at GET /v1/mpp/manifest, field `human_onramp`).

3-LINE HAPPY PATH
    from vend.mpp_client import pay
    out = pay("https://api.snhp.dev", "/v1/mpp/topup", spt_token, api_key="gt_your_key")
    print(out["ok"], out["result"], out["receipt"])   # True, {...}, {reference: "pi_..."}

No LLM anywhere in this path. Integer money. Stdlib only.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Optional

# The MPP auth scheme token (RFC 7235). Matches SCHEME in gametheory/server/mpp.py.
SCHEME = "Payment"


class MppClientError(Exception):
    """A malformed challenge or an unusable server response. Raised by the low-level
    helpers; `pay()` catches it and returns a clean {ok: False, error: ...} dict."""


# ─── base64url (no padding) — matches the server's _b64url_* helpers ─────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# ─── RFC 7235 auth-param parsing (matches the server's _parse_auth_params) ───


def _parse_auth_params(s: str) -> dict:
    """Parse `key="value"` comma-separated auth-params, un-escaping backslashes
    inside quoted strings. Sufficient for the params an MPP challenge emits."""
    out: dict = {}
    i, n = 0, len(s)
    while i < n:
        while i < n and (s[i].isspace() or s[i] == ","):
            i += 1
        start = i
        while i < n and (s[i].isalnum() or s[i] in "_-"):
            i += 1
        key = s[start:i]
        if not key:
            break
        while i < n and s[i].isspace():
            i += 1
        if i >= n or s[i] != "=":
            break
        i += 1
        while i < n and s[i].isspace():
            i += 1
        if i < n and s[i] == '"':
            i += 1
            buf = []
            while i < n:
                c = s[i]
                if c == "\\" and i + 1 < n:
                    buf.append(s[i + 1])
                    i += 2
                    continue
                if c == '"':
                    i += 1
                    break
                buf.append(c)
                i += 1
            out[key] = "".join(buf)
        else:
            start = i
            while i < n and s[i] != ",":
                i += 1
            out[key] = s[start:i].strip()
    return out


def parse_challenge(www_authenticate: str) -> dict:
    """Parse a `WWW-Authenticate: Payment ...` header value into a challenge dict.

    The `request` param is kept as the RAW base64url string the server sent — it
    is NOT decoded and re-encoded here, so it feeds straight back into the
    credential unchanged and the server's HMAC over it still verifies. Raises
    MppClientError if the header is not a parseable Payment challenge."""
    h = (www_authenticate or "").strip()
    if not h.lower().startswith(SCHEME.lower() + " "):
        raise MppClientError("not a Payment challenge")
    params = _parse_auth_params(h[len(SCHEME):].strip())
    if "request" not in params:
        raise MppClientError("challenge missing request parameter")
    return params


def build_credential(challenge: dict, spt_token: str) -> str:
    """Build an `Authorization: Payment <base64url>` value carrying `spt_token`.

    `challenge` is the dict returned by parse_challenge (its `request` is the raw
    base64url string). The result decodes cleanly through the server's
    mpp.parse_credential, and the carried challenge verifies through
    mpp.verify_challenge (the id is untouched, so its HMAC still binds)."""
    if not spt_token:
        raise MppClientError("spt_token is required to build a credential")
    wire = {"challenge": dict(challenge), "payload": {"spt": spt_token}}
    return f"{SCHEME} " + _b64url_encode(json.dumps(wire).encode("utf-8"))


# ─── HTTP seam (stdlib urllib). Tests monkeypatch THIS for a zero-network run ─


def _http_post(url: str, body: bytes, headers: dict, timeout: float):
    """POST `body` to `url`; return (status:int, headers:dict, body:bytes).

    A 402 (or any HTTPError) is returned as a normal tuple, NOT raised — an MPP
    402 challenge is an expected step, not a failure. Connection-level failures
    (URLError) propagate; `pay()` wraps them into a clean error. This is the ONE
    network call site — tests replace it to drive the client with no sockets."""
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def _header(headers: dict, name: str) -> Optional[str]:
    """Case-insensitive header lookup (HTTP header names are case-insensitive)."""
    name = name.lower()
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None


def _decode_body(body: bytes):
    try:
        return json.loads(body.decode("utf-8")) if body else None
    except Exception:
        try:
            return body.decode("utf-8", "replace")
        except Exception:
            return None


def _success(headers: dict, body: bytes) -> dict:
    """Shape a 200 into {ok, result, receipt}. The receipt comes from the
    `Payment-Receipt` header (base64url(JSON)); if absent, fall back to a `receipt`
    field the server echoes in the body."""
    result = _decode_body(body)
    receipt = None
    rc = _header(headers, "Payment-Receipt")
    if rc:
        try:
            receipt = json.loads(_b64url_decode(rc).decode("utf-8"))
        except Exception:
            receipt = None
    if receipt is None and isinstance(result, dict) and isinstance(result.get("receipt"), dict):
        receipt = result["receipt"]
    return {"ok": True, "result": result, "receipt": receipt}


# ─── The one public entry point ──────────────────────────────────────────────


def pay(base_url: str, resource_path: str, spt_token: str, *,
        timeout: float = 30.0, **request_fields) -> dict:
    """Pay for one MPP resource with a Shared Payment Token and return its result.

    Args:
        base_url:       origin of the store, e.g. "https://api.snhp.dev".
        resource_path:  the paid resource, e.g. "/v1/mpp/topup".
        spt_token:      a Shared Payment Token YOU already minted, scoped to this
                        store (this client never mints — see the module docstring).
        timeout:        per-request socket timeout in seconds.
        **request_fields: JSON body sent on BOTH the challenge and the retry
                        (e.g. api_key="gt_..." for /v1/mpp/topup, or the
                        negotiation fields for /v1/mpp/negotiate/turn).

    Returns on success:
        {"ok": True, "result": <response body>, "receipt": <decoded receipt|None>}
    Returns on any failure (never raises for a protocol/HTTP error):
        {"ok": False, "error": <str>, "stage": "challenge"|"settle", ...}
    """
    url = base_url.rstrip("/") + "/" + resource_path.lstrip("/")
    body = json.dumps(request_fields).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # 1) Unpaid request -> expect a 402 challenge (or a 200 if the resource is free).
    try:
        status, resp_headers, resp_body = _http_post(url, body, headers, timeout)
    except Exception as e:  # URLError / socket — a clean error, not a traceback.
        return {"ok": False, "error": f"request failed: {e}", "stage": "challenge"}
    if status == 200:
        return _success(resp_headers, resp_body)
    if status != 402:
        return {"ok": False, "error": f"expected a 402 challenge, got HTTP {status}",
                "status": status, "body": _decode_body(resp_body), "stage": "challenge"}

    www = _header(resp_headers, "WWW-Authenticate")
    if not www:
        return {"ok": False, "error": "402 without a WWW-Authenticate header",
                "stage": "challenge"}
    try:
        challenge = parse_challenge(www)
    except MppClientError as e:
        return {"ok": False, "error": f"malformed challenge: {e}", "stage": "challenge"}

    # 2) Authorize with the SPT and retry. Same body — the server re-reads any
    #    fields it needs (e.g. api_key for a top-up) off the retry request.
    try:
        credential = build_credential(challenge, spt_token)
    except MppClientError as e:
        return {"ok": False, "error": str(e), "stage": "settle"}
    auth_headers = dict(headers)
    auth_headers["Authorization"] = credential
    try:
        status2, resp_headers2, resp_body2 = _http_post(url, body, auth_headers, timeout)
    except Exception as e:
        return {"ok": False, "error": f"retry failed: {e}", "stage": "settle"}
    if status2 == 200:
        return _success(resp_headers2, resp_body2)
    # A 402 here means the credential was rejected or settlement declined; a 4xx
    # (e.g. 400 unknown wallet) means the request was bad. Either way, a clean
    # report the caller can act on — no exception, no partial state.
    return {"ok": False, "error": f"payment not accepted (HTTP {status2})",
            "status": status2, "body": _decode_body(resp_body2), "stage": "settle"}


if __name__ == "__main__":
    # Usage example. Provide a real base URL + a real SPT to run against a live
    # store; with the placeholder token below the store answers 402 and the retry
    # is declined (a clean {ok: False, stage: "settle"}), which is the honest
    # result of trying to spend a token that was never minted.
    import sys

    base = sys.argv[1] if len(sys.argv) > 1 else "https://api.snhp.dev"
    token = sys.argv[2] if len(sys.argv) > 2 else "spt_replace_with_a_real_token"

    # Discover how to pay (pure read, no charge):
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/v1/mpp/manifest", timeout=30) as r:
            manifest = json.loads(r.read().decode("utf-8"))
        print("manifest resources:", [x["path"] for x in manifest.get("resources", [])])
        print("accepted method:", manifest.get("accepted_method", {}).get("method"),
              "| live_ready:", manifest.get("live_ready"))
    except Exception as e:  # noqa: BLE001 — a demo, print and continue
        print("could not fetch manifest:", e)

    # Pay a wallet top-up (needs a real api_key + a real SPT to actually settle):
    out = pay(base, "/v1/mpp/topup", token, api_key="gt_your_key_here")
    print(json.dumps(out, indent=2, default=str))
