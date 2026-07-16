"""Our OWN sold-comp store (SPEC.md Phase 1: "our OWN outcome tracker building
the sold-comp DB — no restricted APIs").

sqlite at paperswarm/data/paperswarm.db (gitignored). Marks are computed from
REALIZED sold prices only, never asks (SPEC SELL rule). Percentile + sell-through
math lives here so the mark model is one auditable place.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import config
from .timeutil import epoch, iso, now_utc, parse_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS comps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    comp_key    TEXT NOT NULL,
    card_name   TEXT,
    number      TEXT,
    grade       TEXT,
    cert        TEXT,
    listing_id  TEXT NOT NULL UNIQUE,
    status      TEXT NOT NULL,           -- 'SOLD' | 'UNSOLD'
    sold_price  REAL,                    -- realized hammer; NULL if UNSOLD
    sold_epoch  REAL NOT NULL,
    sold_time   TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comps_key   ON comps(comp_key);
CREATE INDEX IF NOT EXISTS idx_comps_epoch ON comps(sold_epoch);
"""


def make_comp_key(card_name: str | None, number: str | None, grade: str | None) -> str | None:
    """Bucket key: card_name|number|grade, lowercased (SPEC: cert-grade/card)."""
    if card_name and grade:
        return f"{card_name.strip().lower()}|{(number or '?')}|{grade}"
    return None


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (numpy 'linear' method), deterministic.

    Used for the 25th-percentile mark (SPEC SELL rule). Empty -> 0.0.
    """
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    rank = (pct / 100.0) * (len(xs) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    frac = rank - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


@dataclass(frozen=True)
class MarkResult:
    """A mark-to-realized result with every input exposed for audit."""
    comp_key: str
    n_comps: int          # realized SOLD comps in window
    p25_price: float      # 25th percentile realized price (pre-friction)
    sell_through: float   # SOLD / (SOLD + UNSOLD)
    mark: float           # final mark net of friction and unsold haircut
    reason: str           # "marked" | "thin_comps_zero"


class Comps:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or config.DB_PATH)
        if self.db_path != ":memory:":
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # -- writes ------------------------------------------------------------
    def record(
        self,
        *,
        card_name: str | None,
        number: str | None,
        grade: str | None,
        cert: str | None,
        listing_id: str,
        status: str,
        sold_price: float | None,
        sold_time: str | datetime,
    ) -> bool:
        """Insert a terminal outcome. Idempotent on listing_id (re-poll safe).

        Returns True if a new row was written. SOLD requires a realized price.
        """
        key = make_comp_key(card_name, number, grade)
        if key is None:
            return False
        if isinstance(sold_time, datetime):
            st_dt = sold_time
        else:
            st_dt = parse_iso(sold_time) or now_utc()
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO comps
               (comp_key, card_name, number, grade, cert, listing_id, status,
                sold_price, sold_epoch, sold_time, recorded_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                key, (card_name or "").strip().lower(), number, grade, cert,
                listing_id, status,
                float(sold_price) if sold_price is not None else None,
                epoch(st_dt), iso(st_dt), iso(now_utc()),
            ),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def seed_from_fixture(self, name: str = "seed_comps.json") -> int:
        """Bootstrap the store from a checked-in comp fixture (offline demo)."""
        with open(config.FIXTURE_DIR / name, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        n = 0
        for c in payload.get("comps", []):
            if self.record(
                card_name=c["card_name"], number=c.get("number"), grade=c.get("grade"),
                cert=c.get("cert"), listing_id=c["listing_id"], status=c["status"],
                sold_price=c.get("sold_price"), sold_time=c["sold_time"],
            ):
                n += 1
        return n

    # -- reads -------------------------------------------------------------
    def _window_rows(self, comp_key: str, as_of: datetime, window_days: int) -> list[sqlite3.Row]:
        lo = epoch(as_of - timedelta(days=window_days))
        hi = epoch(as_of)
        return list(self.conn.execute(
            "SELECT * FROM comps WHERE comp_key=? AND sold_epoch>=? AND sold_epoch<=?"
            " ORDER BY sold_epoch",
            (comp_key, lo, hi),
        ))

    def realized_prices(self, comp_key: str, as_of: datetime | None = None,
                        window_days: int = config.COMP_WINDOW_DAYS) -> list[float]:
        as_of = as_of or now_utc()
        return [r["sold_price"] for r in self._window_rows(comp_key, as_of, window_days)
                if r["status"] == "SOLD" and r["sold_price"] is not None]

    def sell_through(self, comp_key: str, as_of: datetime | None = None,
                    window_days: int = config.COMP_WINDOW_DAYS) -> float:
        """SOLD / (SOLD + UNSOLD) in window. No data -> 0.0 (conservative)."""
        as_of = as_of or now_utc()
        rows = self._window_rows(comp_key, as_of, window_days)
        sold = sum(1 for r in rows if r["status"] == "SOLD")
        total = sum(1 for r in rows if r["status"] in ("SOLD", "UNSOLD"))
        return sold / total if total else 0.0

    def store_span_days(self) -> float:
        """Days between earliest and latest comp in the store (cold-start clock)."""
        row = self.conn.execute(
            "SELECT MIN(sold_epoch) AS lo, MAX(sold_epoch) AS hi FROM comps"
        ).fetchone()
        if row["lo"] is None:
            return 0.0
        return (row["hi"] - row["lo"]) / 86400.0

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) AS c FROM comps").fetchone()["c"]

    # -- the mark model ----------------------------------------------------
    def mark(self, comp_key: str, as_of: datetime | None = None) -> MarkResult:
        """Mark-to-realized for one bucket (SPEC SELL rule, exactly).

        mark = net_of_friction(p25 realized price) * sell_through_haircut.
        Fewer than MIN_COMPS_FOR_MARK realized comps -> mark ZERO (no thin-comp
        fantasy). Friction = 13.25% fee + 3% payment + $5 shipping.
        """
        as_of = as_of or now_utc()
        prices = self.realized_prices(comp_key, as_of, config.COMP_WINDOW_DAYS)
        n = len(prices)
        if n < config.MIN_COMPS_FOR_MARK:
            return MarkResult(comp_key, n, 0.0, 0.0, 0.0, "thin_comps_zero")
        p25 = percentile(prices, config.MARK_PERCENTILE)
        st = self.sell_through(comp_key, as_of, config.COMP_WINDOW_DAYS)
        net = net_of_friction(p25)
        return MarkResult(comp_key, n, p25, st, round(net * st, 4), "marked")


def net_of_friction(price: float) -> float:
    """SELL proceeds net of full friction (SPEC: 13.25% + 3% + $5 shipping).

    net = price * (1 - fee_rate - payment_rate) - shipping.
    """
    return price * (1.0 - config.FRICTION_RATE) - config.SHIPPING_USD
