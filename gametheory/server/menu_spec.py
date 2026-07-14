"""friendly_to_dims — the merchant-facing menu format → core.api.build_graph's
declarative `dims` spec.

The public "run it on your own menu" page (arena/web/yourmenu.js) speaks a
FRIENDLY menu format — the JSON a shop owner PASTES:

    {"name": "corner coffee cart",
     "items":  [{"id": "oat-latte", "price": 5.25, "cost": 1.20}, ...],
     "addons": [{"id": "extra-shot", "price": 1.00, "cost": 0.28}, ...],
     "preferences": [{"id": "cup", "options": [{"id": "for-here"}, ...]}],
     "slots":  [{"id": "now", "minutes": 0}, {"id": "in-20", "minutes": 20,
                 "capacity": 6}],
     "max_qty": 3, "min_price_frac": 0.6}

The engine (and the hosted /v1/offer/* API) speaks the RAW `dims` offer-graph
spec. This module is the ONE bridge, ported field-for-field from yourmenu.js's
`validateMenu` + `menuToSpec` so the hosted engine prices a pasted friendly
menu IDENTICALLY to the page. Parity is pinned by gametheory/tests/
test_menu_spec.py against the numbers in arena/web/yourmenu_verify.test.mjs.

`friendly_to_dims(menu)` returns `{"name", "dims", "cost"}` — exactly what
build_graph accepts. The friendly knobs the page reads at QUOTE time rather
than compile time (`min_price_frac`, `currency`) are not part of the graph, so
they are validated and dropped here; a caller that wants the page's price
floor passes `min_price_frac` in the quote opts (see `friendly_price_floor`).

Mirrors yourmenu.js:
  - items[]  {id,label,price,cost, stock?,expected_demand?, perishable?,salvage?}
        → CHOICE dim "item"  options {id,label,price_delta=price,unit_cost=cost,
          stock_limited=(stock given), perishable, salvage}
  - addons[] → ADDON dim "extras"
  - preferences[] (zero-cost) → PREFERENCE dims (price/cost default 0)
  - slots[]  → FULFILLMENT dim "pickup" (immediate = tick 0, slot_ticks)
  - max_qty  → QUANTITY dim "qty" (qty_cap, default 3)
  - cost stack: ["const"] (+ "salvage_on_expiry" if anything perishable)
    (+ "scarcity_shadow" if any item is stock-limited)

stock / expected_demand / slot capacity / end-of-day expiry are SHOP-STATE
facts, not graph facts — they live in ShopState, not the spec (see
`friendly_state`), exactly as yourmenu.js's makeState builds them.
"""
from __future__ import annotations

import math
import re
from typing import Any, Optional

# ─── field vocabulary + limits (mirrors yourmenu.js) ────────────────────────
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$", re.IGNORECASE)
_RESERVED_DIM_IDS = ("item", "extras", "pickup", "qty")
_TOP_KEYS = ("name", "currency", "items", "addons", "preferences", "slots",
             "max_qty", "min_price_frac")
_ITEM_KEYS = ("id", "label", "price", "cost", "stock", "expected_demand",
              "perishable", "salvage", "note")
_ADDON_KEYS = ("id", "label", "price", "cost", "perishable", "salvage", "note")
_PREF_KEYS = ("id", "label", "options")
_PREF_OPT_KEYS = ("id", "label", "price", "cost", "note")
_SLOT_KEYS = ("id", "label", "minutes", "capacity")

_MAX_ITEMS = 40
_MAX_ADDONS = 12
_MAX_PREFS = 6
_MAX_PREF_OPTS = 8
_MIN_PREF_OPTS = 2
_MAX_SLOTS = 6
_TICK_MINUTES = 10          # 1 engine tick = 10 minutes (yourmenu.js)

_DEFAULT_MAX_QTY = 3
_DEFAULT_MIN_PRICE_FRAC = 0.6


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) \
        and math.isfinite(x)


def _is_obj(x: Any) -> bool:
    return isinstance(x, dict)


def _ticks_of(minutes: int) -> int:
    """Minutes-later → engine ticks, matching JS `s.minutes === 0 ? 0 :
    Math.max(1, Math.round(s.minutes / TICK_MINUTES))`. floor(x+0.5) reproduces
    JS Math.round's round-half-up (Python's round() is banker's)."""
    if minutes == 0:
        return 0
    return max(1, math.floor(minutes / _TICK_MINUTES + 0.5))


def is_friendly(menu: Any) -> bool:
    """A friendly menu carries `items`; the raw engine spec carries `dims`."""
    return isinstance(menu, dict) and "items" in menu


class FriendlyMenuError(ValueError):
    """A friendly menu failed validation — carries every problem found, so the
    caller sees all of them at once (like the page's error list)."""


def _validate(raw: dict) -> dict:
    """Port of yourmenu.js validateMenu: normalize + apply defaults, raising
    FriendlyMenuError (with EVERY problem) on bad input. Returns the validated
    menu dict the transform reads."""
    errors: list[str] = []

    def err(m: str) -> None:
        errors.append(m)

    if not _is_obj(raw):
        raise FriendlyMenuError("the top level must be a JSON object { ... }.")

    for k in raw:
        if k not in _TOP_KEYS:
            err(f'unknown top-level key "{k}" — this page accepts: '
                f'{", ".join(_TOP_KEYS)}.')

    menu: dict = {"name": "your shop", "currency": "$", "items": [],
                  "addons": [], "preferences": [], "slots": None,
                  "max_qty": _DEFAULT_MAX_QTY,
                  "min_price_frac": _DEFAULT_MIN_PRICE_FRAC}

    if raw.get("name") is not None:
        n = raw["name"]
        if not isinstance(n, str) or not n.strip() or len(n) > 60:
            err('"name" must be a non-empty string (max 60 chars).')
        else:
            menu["name"] = n.strip()
    if raw.get("currency") is not None:
        c = raw["currency"]
        if not isinstance(c, str) or not (1 <= len(c) <= 3):
            err('"currency" must be a short string like "$" (display only).')
        else:
            menu["currency"] = c

    seen_ids: dict[str, str] = {}

    def claim_id(oid: str, where: str) -> None:
        if oid in seen_ids:
            err(f'duplicate id "{oid}" ({seen_ids[oid]} and {where}) — ids '
                "must be unique across the whole menu.")
        else:
            seen_ids[oid] = where

    def check_good(o: Any, where: str, keys, kind: str) -> Optional[dict]:
        if not _is_obj(o):
            err(f"{where}: each {kind} must be an object.")
            return None
        for k in o:
            if k not in keys:
                if kind == "add-on" and k in ("stock", "expected_demand"):
                    err(f'{where}: "{k}" is supported on items only — the '
                        "engine's scarcity shadow reprices displaced units for "
                        "the main choice, not add-ons.")
                else:
                    err(f'{where}: unknown key "{k}" — allowed: '
                        f'{", ".join(keys)}.')
        if not isinstance(o.get("id"), str) or not _ID_RE.match(o["id"]):
            err(f'{where}: "id" must be a short slug (letters, digits, - or _),'
                ' e.g. "oat-latte".')
            return None
        lbl = o.get("label")
        label = lbl.strip()[:60] if isinstance(lbl, str) and lbl.strip() \
            else o["id"]
        out: dict = {"id": o["id"], "label": label}
        if not _is_num(o.get("price")) or o["price"] <= 0 or o["price"] > 10000:
            err(f'{where} ("{o["id"]}"): "price" must be a number > 0 (your '
                "list price).")
            return None
        if not _is_num(o.get("cost")) or o["cost"] < 0 or o["cost"] > 10000:
            err(f'{where} ("{o["id"]}"): "cost" must be a number >= 0 (what '
                "one unit costs you to serve).")
            return None
        out["price"], out["cost"] = o["price"], o["cost"]
        peri = o.get("perishable")
        if peri is not None and not isinstance(peri, bool):
            err(f'{where} ("{o["id"]}"): "perishable" must be true or false.')
            return None
        out["perishable"] = bool(peri)
        if o.get("salvage") is not None:
            if not out["perishable"]:
                err(f'{where} ("{o["id"]}"): "salvage" only makes sense with '
                    '"perishable": true.')
                return None
            if not _is_num(o["salvage"]) or o["salvage"] < 0:
                err(f'{where} ("{o["id"]}"): "salvage" must be a number >= 0 '
                    "(its value to you at close).")
                return None
            if o["salvage"] > o["cost"]:
                err(f'{where} ("{o["id"]}"): "salvage" above "cost" would make '
                    "expiry profitable — check the numbers.")
                return None
            out["salvage"] = o["salvage"]
        else:
            out["salvage"] = 0
        if o.get("note") is not None and not isinstance(o["note"], str):
            err(f'{where} ("{o["id"]}"): "note" must be a string.')
            return None
        return out

    # items ──────────────────────────────────────────────────────────────────
    items = raw.get("items")
    if not isinstance(items, list) or len(items) == 0:
        err('"items" is required: a non-empty array of what you sell, each '
            "with id, price and cost.")
    elif len(items) > _MAX_ITEMS:
        err(f'"items": at most {_MAX_ITEMS} (got {len(items)}) — this page '
            "keeps the search space honest and fast.")
    else:
        for i, o in enumerate(items):
            g = check_good(o, f"items[{i}]", _ITEM_KEYS, "item")
            if not g:
                continue
            if o.get("stock") is not None:
                if not isinstance(o["stock"], int) or isinstance(o["stock"], bool) \
                        or o["stock"] < 0:
                    err(f'items[{i}] ("{g["id"]}"): "stock" must be a whole '
                        "number >= 0.")
                    continue
                g["stock"] = o["stock"]
            if o.get("expected_demand") is not None:
                if "stock" not in g:
                    err(f'items[{i}] ("{g["id"]}"): "expected_demand" needs '
                        '"stock" — it tells the scarcity shadow how many '
                        "full-price buyers a discounted unit would displace.")
                    continue
                if not _is_num(o["expected_demand"]) or o["expected_demand"] < 0:
                    err(f'items[{i}] ("{g["id"]}"): "expected_demand" must be '
                        "a number >= 0.")
                    continue
                g["expected_demand"] = o["expected_demand"]
            claim_id(g["id"], f"items[{i}]")
            menu["items"].append(g)

    # addons ──────────────────────────────────────────────────────────────────
    if raw.get("addons") is not None:
        addons = raw["addons"]
        if not isinstance(addons, list):
            err('"addons" must be an array.')
        elif len(addons) > _MAX_ADDONS:
            err(f'"addons": at most {_MAX_ADDONS} (got {len(addons)}) — the '
                "engine enumerates every subset, and caps add-on dimensions "
                f"at {_MAX_ADDONS} options.")
        else:
            for i, o in enumerate(addons):
                g = check_good(o, f"addons[{i}]", _ADDON_KEYS, "add-on")
                if not g:
                    continue
                claim_id(g["id"], f"addons[{i}]")
                menu["addons"].append(g)

    # preferences ──────────────────────────────────────────────────────────────
    if raw.get("preferences") is not None:
        prefs = raw["preferences"]
        if not isinstance(prefs, list):
            err('"preferences" must be an array.')
        elif len(prefs) > _MAX_PREFS:
            err(f'"preferences": at most {_MAX_PREFS}.')
        else:
            for i, p in enumerate(prefs):
                if not _is_obj(p):
                    err(f"preferences[{i}] must be an object.")
                    continue
                for k in p:
                    if k not in _PREF_KEYS:
                        err(f'preferences[{i}]: unknown key "{k}" — allowed: '
                            f'{", ".join(_PREF_KEYS)}.')
                if not isinstance(p.get("id"), str) or not _ID_RE.match(p["id"]):
                    err(f'preferences[{i}]: "id" must be a short slug.')
                    continue
                if p["id"] in _RESERVED_DIM_IDS:
                    err(f'preferences[{i}]: id "{p["id"]}" is reserved by this '
                        f'page (reserved: {", ".join(_RESERVED_DIM_IDS)}).')
                    continue
                if any(x["id"] == p["id"] for x in menu["preferences"]):
                    err(f'preferences: duplicate id "{p["id"]}".')
                    continue
                opts = p.get("options")
                if not isinstance(opts, list) \
                        or not (_MIN_PREF_OPTS <= len(opts) <= _MAX_PREF_OPTS):
                    err(f'preferences[{i}] ("{p["id"]}"): "options" must be an '
                        f"array of {_MIN_PREF_OPTS}-{_MAX_PREF_OPTS} choices.")
                    continue
                plbl = p.get("label")
                pref = {"id": p["id"],
                        "label": plbl.strip()[:60] if isinstance(plbl, str)
                        and plbl.strip() else p["id"],
                        "options": []}
                bad = False
                for j, o in enumerate(opts):
                    if not _is_obj(o):
                        err(f"preferences[{i}].options[{j}] must be an object.")
                        bad = True
                        continue
                    for k in o:
                        if k not in _PREF_OPT_KEYS:
                            err(f"preferences[{i}].options[{j}]: unknown key "
                                f'"{k}" — allowed: {", ".join(_PREF_OPT_KEYS)}.')
                    if not isinstance(o.get("id"), str) or not _ID_RE.match(o["id"]):
                        err(f"preferences[{i}].options[{j}]: \"id\" must be a "
                            "short slug.")
                        bad = True
                        continue
                    olbl = o.get("label")
                    opt = {"id": o["id"],
                           "label": olbl.strip()[:60] if isinstance(olbl, str)
                           and olbl.strip() else o["id"],
                           "price": 0, "cost": 0}
                    if o.get("price") is not None:
                        if not _is_num(o["price"]) or o["price"] < 0:
                            err(f"preferences[{i}].options[{j}]: \"price\" must "
                                "be >= 0.")
                            bad = True
                            continue
                        opt["price"] = o["price"]
                    if o.get("cost") is not None:
                        if not _is_num(o["cost"]) or o["cost"] < 0:
                            err(f"preferences[{i}].options[{j}]: \"cost\" must "
                                "be >= 0.")
                            bad = True
                            continue
                        opt["cost"] = o["cost"]
                    claim_id(opt["id"], f"preferences[{i}].options[{j}]")
                    pref["options"].append(opt)
                if not bad:
                    menu["preferences"].append(pref)

    # slots ────────────────────────────────────────────────────────────────────
    if raw.get("slots") is not None:
        raw_slots = raw["slots"]
        if not isinstance(raw_slots, list) or len(raw_slots) == 0:
            err('"slots" must be a non-empty array (or omit it entirely for a '
                "walk-up-only shop).")
        elif len(raw_slots) > _MAX_SLOTS:
            err(f'"slots": at most {_MAX_SLOTS}.')
        else:
            slots: list[dict] = []
            ticks_seen: dict[int, str] = {}
            for i, s in enumerate(raw_slots):
                if not _is_obj(s):
                    err(f"slots[{i}] must be an object.")
                    continue
                for k in s:
                    if k not in _SLOT_KEYS:
                        err(f'slots[{i}]: unknown key "{k}" — allowed: '
                            f'{", ".join(_SLOT_KEYS)}.')
                if not isinstance(s.get("id"), str) or not _ID_RE.match(s["id"]):
                    err(f'slots[{i}]: "id" must be a short slug.')
                    continue
                mins = s.get("minutes")
                if not isinstance(mins, int) or isinstance(mins, bool) \
                        or not (0 <= mins <= 480):
                    err(f'slots[{i}] ("{s["id"]}"): "minutes" must be a whole '
                        "number 0-480 (how much later than now).")
                    continue
                ticks = _ticks_of(mins)
                if ticks in ticks_seen:
                    err(f'slots[{i}] ("{s["id"]}"): resolves to the same '
                        f'{_TICK_MINUTES}-minute tick as "{ticks_seen[ticks]}" '
                        f"— space slots at least {_TICK_MINUTES} minutes apart.")
                    continue
                ticks_seen[ticks] = s["id"]
                slbl = s.get("label")
                slot = {"id": s["id"],
                        "label": slbl.strip()[:60] if isinstance(slbl, str)
                        and slbl.strip() else s["id"],
                        "minutes": mins, "ticks": ticks}
                if s.get("capacity") is not None:
                    if not _is_num(s["capacity"]) or s["capacity"] <= 0:
                        err(f'slots[{i}] ("{s["id"]}"): "capacity" must be a '
                            "number > 0 (units of room in that slot).")
                        continue
                    if ticks == 0:
                        err(f'slots[{i}] ("{s["id"]}"): "capacity" applies to '
                            "later slots only — the immediate slot has no "
                            "booking book.")
                        continue
                    slot["capacity"] = s["capacity"]
                claim_id(slot["id"], f"slots[{i}]")
                slots.append(slot)
            if slots and not any(s["ticks"] == 0 for s in slots):
                slots.insert(0, {"id": "now", "label": "Right now",
                                 "minutes": 0, "ticks": 0})
            if slots:
                menu["slots"] = slots

    if raw.get("max_qty") is not None:
        mq = raw["max_qty"]
        if not isinstance(mq, int) or isinstance(mq, bool) or not (1 <= mq <= 6):
            err('"max_qty" must be a whole number 1-6.')
        else:
            menu["max_qty"] = mq
    if raw.get("min_price_frac") is not None:
        mpf = raw["min_price_frac"]
        if not _is_num(mpf) or not (0 <= mpf <= 1):
            err('"min_price_frac" must be a number between 0 and 1 (your '
                "floor: never quote below this fraction of list).")
        else:
            menu["min_price_frac"] = mpf

    if errors:
        raise FriendlyMenuError("; ".join(errors))
    return menu


def _menu_to_spec(menu: dict) -> dict:
    """Port of yourmenu.js menuToSpec: validated friendly menu → dims spec."""
    dims: list[dict] = []
    dims.append({
        "id": "item", "kind": "choice",
        "options": [{
            "id": it["id"], "label": it["label"],
            "price_delta": it["price"], "unit_cost": it["cost"],
            "stock_limited": "stock" in it,
            "perishable": it["perishable"], "salvage": it["salvage"],
        } for it in menu["items"]],
    })
    if menu["addons"]:
        dims.append({
            "id": "extras", "kind": "addon",
            "options": [{
                "id": a["id"], "label": a["label"],
                "price_delta": a["price"], "unit_cost": a["cost"],
                "perishable": a["perishable"], "salvage": a["salvage"],
            } for a in menu["addons"]],
        })
    for p in menu["preferences"]:
        dims.append({
            "id": p["id"], "kind": "preference",
            "options": [{
                "id": o["id"], "label": o["label"],
                "price_delta": o["price"], "unit_cost": o["cost"],
            } for o in p["options"]],
        })
    if menu["slots"]:
        dims.append({
            "id": "pickup", "kind": "fulfillment",
            "options": [{
                "id": s["id"], "label": s["label"],
                "immediate": s["ticks"] == 0, "slot_ticks": s["ticks"],
            } for s in menu["slots"]],
        })
    dims.append({"id": "qty", "kind": "quantity", "qty_cap": menu["max_qty"]})

    any_perishable = any(i["perishable"] for i in menu["items"]) \
        or any(a["perishable"] for a in menu["addons"])
    any_stock = any("stock" in i for i in menu["items"])
    cost = ["const"]
    if any_perishable:
        cost.append("salvage_on_expiry")
    if any_stock:
        cost.append("scarcity_shadow")
    return {"name": menu["name"], "dims": dims, "cost": cost}


def friendly_to_dims(menu: dict) -> dict:
    """Compile a FRIENDLY pasted menu into the `{name, dims, cost}` spec that
    core.api.build_graph accepts — byte-for-byte the object yourmenu.js's
    menuToSpec produces from the same paste. Raises FriendlyMenuError (a
    ValueError) with every problem found on bad input."""
    return _menu_to_spec(_validate(menu))


# ─── shop-state + price-floor helpers (the non-graph friendly facts) ────────


def friendly_state(menu: dict, *, end_of_day: bool = False) -> dict:
    """The ShopState dict yourmenu.js's makeState builds from a friendly menu:
    finite stock, expected demand, deferred-slot capacity, and (at end of day)
    the perishables now priced at salvage. Returns a plain dict suitable for
    the hosted /v1/offer/* `state` field (option_id / slot_ticks keys)."""
    m = _validate(menu)
    inventory = {it["id"]: it["stock"] for it in m["items"] if "stock" in it}
    expected_demand = {it["id"]: it["expected_demand"]
                       for it in m["items"] if "expected_demand" in it}
    perishables = [x["id"] for x in m["items"] + m["addons"]
                   if x["perishable"]]
    capacity: dict[int, float] = {}
    for s in m["slots"] or []:
        if s["ticks"] > 0 and "capacity" in s:
            capacity[s["ticks"]] = s["capacity"]
    return {"tick": 0, "inventory": inventory, "capacity": capacity,
            "expiring": perishables if end_of_day else [],
            "expected_demand": expected_demand}


def friendly_price_floor(menu: dict) -> float:
    """The `min_price_frac` a friendly menu declares (default 0.6) — the page's
    quote floor. Pass it in the quote opts to reproduce the page's prices."""
    return _validate(menu)["min_price_frac"]
