"""THE STORE — the shelf: wire the commodity slots into the registry.

The one place the fetch slot's config is stated (its backends, predicate,
admission cap) and the only place the telemetry sink is bound to the real
logger. Both doors call `ensure_shelf()` before serving; it is idempotent —
the slot is registered once and re-registering is a no-op, so import order
between the MCP and HTTP doors cannot double-stock or race. No hard-coded
store identity beyond a slot's own config (STORE.md §2d.1).
"""
from __future__ import annotations

from vend import store, telemetry
from vend.fetch_backends import (
    PREDICATE_ID_V2, FirecrawlBackend, JinaReaderBackend, fetch_predicate_v2,
)

# The published 2¢ admission cap for the fetch slot (STORE.md §2b/§2d.4). It
# gates admission only — a call SETTLES at wholesale passthrough, which is
# typically well under this. 2¢ = 2000 millicents. Jina leads, Firecrawl fails
# over: order is the failover order the receipt records.
FETCH_MAX_PRICE_MILLICENTS = 2000


def build_fetch_slot() -> store.Slot:
    return store.Slot(
        id="fetch",
        title="Fetch / extract — one clean read of a stubborn page → markdown",
        backends=[JinaReaderBackend(), FirecrawlBackend()],
        # fetch.v2 adds the block-page screen (GAUNTLET #6) over v1's non-empty
        # check, so a bot-block interstitial is an uncharged non-delivery.
        predicate=fetch_predicate_v2,
        predicate_id=PREDICATE_ID_V2,
        max_price_millicents=FETCH_MAX_PRICE_MILLICENTS,
        # request_doc now names api_key (GAUNTLET #7: it was omitted, a 422 tax
        # on every newcomer). The key may also travel in an Authorization/
        # X-API-Key header — see the POST /v1/fetch route.
        request_doc=("{api_key: str, url: str}  # http(s) public web only, "
                     "<= 2048 chars"),
        # The fetch.v2 boundary, stated for the catalog (auditor follow-up): what
        # the settlement predicate catches, and the honest limit of a shape check.
        predicate_doc=(
            "fetch.v2 catches TWO non-delivery shapes, both uncharged: (1) an "
            "EMPTY read (no markdown after strip), and (2) a SHORT block page — a "
            "doc under 500 chars containing a known anti-bot phrase (access "
            "denied, just a moment, verify you are human, captcha, enable "
            "javascript and cookies). A full-length article that merely quotes "
            "such a phrase runs past the length bound and passes. LIMIT: "
            "settlement checks delivery SHAPE, not the TRUTHFULNESS of the "
            "upstream page — a thin-but-non-empty real error page (a 200-shaped "
            "'not found' with prose) still PASSES the predicate and BILLS."),
    )


def ensure_shelf() -> None:
    """Register the commodity slots and bind the telemetry sink. Idempotent:
    the id-keyed check preserves any test-swapped backends, and rebinding the
    same sink is harmless — safe to call on every request from every door."""
    if "fetch" not in store.SLOTS:
        store.register_slot(build_fetch_slot())
    # The engine ships with a no-op sink; wire the real JSONL logger here (the
    # integrator's lane). Every call — uncharged failures included — flows
    # through it, so non-delivery is recorded, not lost.
    store.set_telemetry_sink(telemetry.log_slot_call)
