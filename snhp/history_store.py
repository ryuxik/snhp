"""
SNHP History Store — Abstraction layer for freelancer contract history.

Currently backed by a local JSON file (~/.snhp/history.json).
The interface is designed so the backend can be swapped to Supabase or
any other persistence layer by implementing the same read/write methods.
"""

import json
import os
from datetime import datetime


# --- Abstract Interface ---

class HistoryBackend:
    """Base interface. Swap this out for SupabaseBackend later."""

    def load_contracts(self) -> list:
        raise NotImplementedError

    def save_contract(self, contract: dict) -> None:
        raise NotImplementedError

    def load_profile(self) -> dict:
        raise NotImplementedError

    def save_profile(self, profile: dict) -> None:
        raise NotImplementedError


# --- Local JSON Backend ---

SNHP_DIR = os.path.expanduser("~/.snhp")
HISTORY_FILE = os.path.join(SNHP_DIR, "history.json")


def _ensure_dir():
    os.makedirs(SNHP_DIR, exist_ok=True)


def _load_store() -> dict:
    _ensure_dir()
    if not os.path.exists(HISTORY_FILE):
        return {"profile": {}, "contracts": []}
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)


def _save_store(data: dict):
    _ensure_dir()
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)


class LocalJsonBackend(HistoryBackend):

    def load_contracts(self) -> list:
        return _load_store().get("contracts", [])

    def save_contract(self, contract: dict) -> None:
        store = _load_store()
        contract.setdefault("date", datetime.now().isoformat()[:10])
        store["contracts"].append(contract)
        _save_store(store)

    def load_profile(self) -> dict:
        return _load_store().get("profile", {})

    def save_profile(self, profile: dict) -> None:
        store = _load_store()
        store["profile"] = profile
        _save_store(store)


# --- Public API (backend-agnostic) ---

_backend: HistoryBackend = LocalJsonBackend()


def set_backend(backend: HistoryBackend):
    global _backend
    _backend = backend


def get_past_contracts() -> list:
    return _backend.load_contracts()


def add_contract(contract: dict):
    _backend.save_contract(contract)


def get_profile() -> dict:
    return _backend.load_profile()


def set_profile(profile: dict):
    _backend.save_profile(profile)


# --- Derived Analytics (deterministic, no LLM) ---

def compute_historical_stats() -> dict:
    """Deterministic stats from past contracts for the math boundary."""
    contracts = get_past_contracts()
    if not contracts:
        return {
            "count": 0,
            "avg_hourly": None,
            "max_hourly": None,
            "min_hourly": None,
            "avg_total": None,
            "trend_pct": None,
            "active_pipeline": 0,
        }

    rates = [c["hourly_rate"] for c in contracts if c.get("hourly_rate")]
    totals = [c["total_value"] for c in contracts if c.get("total_value")]

    # Simple YoY trend: compare last 3 vs first 3
    trend_pct = None
    if len(rates) >= 6:
        early = sum(rates[:3]) / 3
        recent = sum(rates[-3:]) / 3
        if early > 0:
            trend_pct = round(((recent - early) / early) * 100, 1)

    profile = get_profile()

    return {
        "count": len(contracts),
        "avg_hourly": round(sum(rates) / len(rates), 2) if rates else None,
        "max_hourly": max(rates) if rates else None,
        "min_hourly": min(rates) if rates else None,
        "avg_total": round(sum(totals) / len(totals), 2) if totals else None,
        "trend_pct": trend_pct,
        "active_pipeline": profile.get("active_pipeline", 0),
    }
