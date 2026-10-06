"""`snhp` — a local (stdio) MCP server for SNHP: negotiation rules a seller's AI can't break.

The four tools call the hosted service at https://snhp.dev (override with SNHP_BASE_URL):

    compile_offer_policy     your offer in plain words (or a template) -> negotiation rules
    draft_negotiation_reply  a buyer's message -> the reply to send + the offer, checked against your rules
    check_offer_policy       validate an edited policy (free)
    verify_deal_receipt      re-check a signed deal receipt against your policy (free)

Compiling a description and drafting replies run a language model and need an access key: set SNHP_ACCESS_KEY in the
server's environment (or pass `access_key`). Pilot businesses get one at https://snhp.dev/#pilot.
The service stores no conversations: keep the `state` a reply returns and send it with the next message.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE = os.environ.get("SNHP_BASE_URL", "https://snhp.dev").rstrip("/")
TIMEOUT = float(os.environ.get("SNHP_TIMEOUT", "120"))

mcp = FastMCP("snhp", instructions=(
    "SNHP: negotiation rules a seller's AI can't break. Start with compile_offer_policy (describe the offer, or pass "
    "a template: used-car, saas, wholesale-water), then call draft_negotiation_reply for each buyer message, passing "
    "back the `state` it returns. Every offer is decided by the SNHP engine inside the rules and checked before it "
    "leaves; a deal needs the buyer's yes and comes with a signed receipt (verify_deal_receipt). Drafting and "
    "compiling need an access key (SNHP_ACCESS_KEY or `access_key`)."))


def _key(access_key: str) -> str:
    return (access_key or os.environ.get("SNHP_ACCESS_KEY", "")).strip()


def _call(method: str, path: str, body: Optional[dict] = None, access_key: str = "") -> dict[str, Any]:
    headers = {"User-Agent": "snhp-mcp/0.5.0"}
    if access_key:
        headers["X-SNHP-Key"] = access_key
    try:
        r = httpx.request(method, BASE + path, json=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        return {"error": f"could not reach {BASE}: {type(e).__name__}"}
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        return {"error": data.get("detail") if isinstance(data, dict) else f"HTTP {r.status_code}",
                "status": r.status_code}
    return data


@mcp.tool()
def compile_offer_policy(description: str = "", template: str = "", access_key: str = "") -> dict:
    """Turn a seller's offer, described in plain words, into negotiation RULES an AI agent cannot break.

    Describe: the listed price, the lowest price you'd take for a plain deal, what you'd trade a discount for
    (financing with you, a trade-in, a longer commitment, paying sooner, buying this week), extras you can add and what
    they cost you, and anything never on the table. Or pass `template` = "used-car", "saas" or "wholesale-water"
    (free). Returns {ok, policy, issues, summary}; pass `policy` to draft_negotiation_reply.
    """
    if template:
        tpls = _call("GET", "/v1/policy/templates")
        if "error" in tpls:
            return tpls
        for t in tpls.get("templates", []):
            if t.get("id") == template:
                return _call("POST", "/v1/policy/check", {"policy": t["policy"]})
        return {"error": f"unknown template {template!r}; one of "
                         f"{[t.get('id') for t in tpls.get('templates', [])]}"}
    return _call("POST", "/v1/policy/compile", {"description": description}, _key(access_key))


@mcp.tool()
def draft_negotiation_reply(policy: dict, message: str, state: Optional[dict] = None, engine: str = "",
                            flags: Optional[dict] = None, access_key: str = "") -> dict:
    """Draft the seller's reply to a buyer's message — the offer is decided by the SNHP engine INSIDE the policy.

    Pass the policy and the buyer's latest message exactly as written; pass back the `state` from your previous call
    (omit to start). `flags` = what YOUR records confirm about the buyer, never what they claim. Returns {kind
    (offer | deal | handoff | decline), reply_with_offer, offer {terms, line, price, inside_policy}, decided_by, state,
    receipt on a deal}.
    """
    body = {"policy": policy, "message": message, "state": state, "flags": flags}
    if engine:
        body["engine"] = engine
    return _call("POST", "/v1/reply", body, _key(access_key))


@mcp.tool()
def check_offer_policy(policy: dict) -> dict:
    """Check an edited negotiation policy: returns {ok, policy, issues, summary}. Free, no model call."""
    return _call("POST", "/v1/policy/check", {"policy": policy})


@mcp.tool()
def verify_deal_receipt(receipt: dict, policy: dict, flags: Optional[dict] = None) -> dict:
    """Verify a signed deal receipt against your policy: signature, policy digest and every rule re-checked.
    Returns {ok, problems, checks}. Free."""
    return _call("POST", "/v1/receipt/verify", {"receipt": receipt, "policy": policy, "flags": flags})


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
