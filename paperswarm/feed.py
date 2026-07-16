"""eBay Browse API data layer (SPEC.md Phase 1: "Browse API poller ... no
restricted APIs").

Client-credentials app token; env EBAY_CLIENT_ID / EBAY_CLIENT_SECRET. Absent
keys -> FIXTURE mode serving checked-in payloads so the whole desk tests
offline. Every network call is metered and charged to P&L (SPEC: "API/LLM
costs metered and charged against P&L").
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from . import config

Meter = Callable[[float, str], None]  # (cost_usd, reason) -> None


@dataclass(frozen=True)
class Listing:
    """Normalized listing (SPEC Phase 1 fields).

    listing_id, title, price, listing_type (AUCTION|BIN i.e. FIXED_PRICE),
    close_time, seller, raw.
    """
    listing_id: str
    title: str
    price: float
    listing_type: str          # "AUCTION" | "FIXED_PRICE"
    close_time: datetime | None
    seller: str
    raw: dict

    @property
    def is_auction(self) -> bool:
        """Phase-1 fills are auction-only (SPEC BUY rule: no BIN paper-buys)."""
        return self.listing_type == "AUCTION"


def _parse_ebay_time(value: str | None) -> datetime | None:
    """Parse eBay ISO-8601 close time (e.g. '2026-07-16T20:00:00.000Z')."""
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_summary(item: dict) -> Listing:
    """eBay item_summary -> Listing. AUCTION iff 'AUCTION' in buyingOptions."""
    options = item.get("buyingOptions") or []
    listing_type = "AUCTION" if "AUCTION" in options else "FIXED_PRICE"

    # Auctions: current bid is the live price; else the fixed price.
    price_obj = item.get("currentBidPrice") or item.get("price") or {}
    try:
        price = float(price_obj.get("value")) if price_obj.get("value") is not None else 0.0
    except (TypeError, ValueError):
        price = 0.0

    seller = (item.get("seller") or {}).get("username", "")
    return Listing(
        listing_id=item.get("itemId", ""),
        title=item.get("title", ""),
        price=price,
        listing_type=listing_type,
        close_time=_parse_ebay_time(item.get("itemEndDate")),
        seller=seller,
        raw=item,
    )


class EbayFeed:
    """Browse API client. FIXTURE mode when keys absent (config.fixture_mode())."""

    def __init__(self, meter: Meter | None = None, fixture: bool | None = None):
        self._meter = meter or (lambda cost, reason: None)
        self._fixture = config.fixture_mode() if fixture is None else fixture
        self._token: str | None = None
        self._token_expiry: float = 0.0

    @property
    def fixture(self) -> bool:
        return self._fixture

    # -- token -------------------------------------------------------------
    def _app_token(self) -> str:
        """Client-credentials app token (cached until ~expiry). Real mode only."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        import requests  # lazy: fixture path stays stdlib-only

        creds = f"{config.EBAY_CLIENT_ID}:{config.EBAY_CLIENT_SECRET}".encode()
        headers = {
            "Authorization": "Basic " + base64.b64encode(creds).decode(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials", "scope": config.EBAY_SCOPE}
        resp = requests.post(config.EBAY_OAUTH_URL, headers=headers, data=data, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + int(payload.get("expires_in", 7200))
        return self._token

    # -- fixtures ----------------------------------------------------------
    @staticmethod
    def _load_fixture(name: str) -> dict:
        with open(config.FIXTURE_DIR / name, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # -- search ------------------------------------------------------------
    def search(self, query: str | None = None, limit: int = 50) -> list[Listing]:
        """Poll the launch niche -> normalized listings (SPEC Phase 1 poller).

        Metered: one API-call charge to P&L per search (energy is not free).
        """
        query = query or config.LAUNCH_NICHE.search_query
        self._meter(config.API_CALL_COST_USD, "ebay_search")

        if self._fixture:
            payload = self._load_fixture("search_psa_pokemon.json")
        else:
            import requests

            headers = {
                "Authorization": f"Bearer {self._app_token()}",
                "X-EBAY-C-MARKETPLACE-ID": config.LAUNCH_NICHE.ebay_marketplace,
            }
            params = {
                "q": query,
                "category_ids": config.LAUNCH_NICHE.category_ids,
                "filter": "buyingOptions:{AUCTION}",
                "limit": str(limit),
            }
            resp = requests.get(
                config.EBAY_BROWSE_SEARCH_URL, headers=headers, params=params, timeout=30
            )
            resp.raise_for_status()
            payload = resp.json()

        return [normalize_summary(it) for it in payload.get("itemSummaries", [])]

    # -- item detail -------------------------------------------------------
    def get_item(self, listing_id: str) -> dict:
        """Item detail (localizedAspects for identity). Metered per call."""
        self._meter(config.API_CALL_COST_USD, "ebay_item")
        if self._fixture:
            # Fixture files are keyed by the numeric middle of the itemId.
            numeric = listing_id.split("|")[1] if "|" in listing_id else listing_id
            try:
                return self._load_fixture(f"item_detail_{numeric}.json")
            except FileNotFoundError:
                return {}
        import requests

        headers = {
            "Authorization": f"Bearer {self._app_token()}",
            "X-EBAY-C-MARKETPLACE-ID": config.LAUNCH_NICHE.ebay_marketplace,
        }
        resp = requests.get(
            f"{config.EBAY_BROWSE_ITEM_URL}/{listing_id}", headers=headers, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def aspects_from_detail(detail: dict) -> dict[str, str]:
        """Flatten eBay localizedAspects -> {name: value} for identity.parse."""
        out: dict[str, str] = {}
        for asp in detail.get("localizedAspects", []) or []:
            name = asp.get("name")
            value = asp.get("value")
            if name and value is not None:
                out[name] = value
        return out
