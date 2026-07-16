"""MPX market: seeded tick loop, optimistic settlement, delayed delivery, star
ratings, metrics, hash-chained ledger (SPEC "Deterministic seeded market loop").

One RNG (`numpy.default_rng(seed)`) consumed in a fixed order -> `same seed ->
identical ledger hash`.  Agent policies are deterministic; the RNG only draws
the population and the broker spot conditions.

The market executes MONEY and GOODS behind the protocol's messages:
  - ACCEPT -> optimistic payment now (unless the supplier is unattested and
    attestation-gating is on, in which case funds go to ESCROW; A5-ii);
  - delivery lands `ship_date` ticks later and may be late/short (variant
    agents); escrowed funds release only for what actually arrives.
Two fill metrics are kept on purpose: `fill_optimistic` (booked/paid, what an
MPX dashboard shows) vs `fill_realized` (delivered on time, the truth).  Their
gap is the "green dashboard while buyers bleed" of A2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import ledger as L
from .agents import (BrokerAgent, BuyerAgent, DemandLine, SupplierAgent,
                     SupplierParams, buyer_gross_value, supplier_cost)
from .protocol import (Counter, Quote, RFQ, Session, State)

STAR_DEFAULT = 5.0        # unrated suppliers look perfect (optimistic dashboard)
STAR_FLAG = 4.0           # a star mean below this = "flagged" (A2 detection bar)
ATT_MIN_TRADES = 3        # trades before a supplier can earn attestation (A5-ii)
ATT_RATIO_BAR = 0.98      # mean realized/promised needed to stay attested
BARGAIN_SPLIT = 0.5       # where price lands inside the ZOPA (does not move A1)


@dataclass
class MarketConfig:
    n_buyers: int = 40
    n_suppliers: int = 120
    n_brokers: int = 12
    ticks: int = 2000
    n_items: int = 8
    candidates: int = 6            # suppliers sampled per RFQ
    lines_lo: int = 14             # demand lines per buyer
    lines_hi: int = 32
    # demand shape (per-audit regime knobs)
    need_by_lo: int = 2
    need_by_hi: int = 9
    urgency_lo: float = 1.0
    urgency_hi: float = 6.0
    value_lo: float = 70.0
    value_hi: float = 130.0
    cap_lo: int = 3            # supplier ship capacity/tick range
    cap_hi: int = 9
    # A2 deception
    deceptive_fraction: float = 0.0   # f: fraction of suppliers that lie
    deceptive_bad_prob: float = 0.5   # d: per-order probability of a shortfall
    deceptive_short_frac: float = 0.5 # qty fraction withheld on a bad order
    buyer_lag: int = 0                # A3: StaleBuyer belief lag k
    attestation: bool = False         # A5-ii: gate optimistic tier on receipts
    chain_demand: bool = False        # A4: inject broker-only demand
    spot_lo: float = 0.95             # A4: upstream spot cost multiplier range
    spot_hi: float = 1.45
    spot_avail: float = 0.80          # A4: prob an upstream supplier is sourceable
    retry_gap: int = 5                # min ticks between RFQs on the same line
    max_attempts: int = 6             # abandon a line after this many failed rounds
    collect_rfqs: bool = False        # record per-RFQ rows for A1/A5-i


@dataclass
class TradeRecord:
    supplier_id: str
    deceptive: bool
    is_broker: bool
    chain: bool
    price: float               # agreed total price
    amount_paid: float         # what the buyer actually parted with
    promised_qty: int
    realized_qty: float
    realized_cost: float
    buyer_surplus: float       # realized value - amount_paid
    on_time_full: bool
    stars: int


@dataclass
class RFQRecord:
    """Everything the auditor needs to recompute the oracle/nash bundle for one
    RFQ against the SAME counterparty (A1, A5-i)."""

    line_id: int
    supplier_id: str
    need_qty: int
    need_by: int
    unit_value: float
    urgency: float
    c0: float
    c1: float
    cap: float
    expedite: float
    inventory: float
    min_markup: float
    quote_qty: int
    quote_date: int
    quote_price: float
    floor_price: float
    traded: bool
    agreed_price: float
    price_only_joint: float    # realized joint surplus of the price-only outcome


@dataclass
class MarketResult:
    metrics: dict
    trades: list[TradeRecord]
    rfqs: list[RFQRecord]
    ledger: L.Ledger
    supplier_stars: dict           # id -> (sum, count)
    detection: dict                # deceptive id -> trades_to_flag or None


# --- delivery queue item ----------------------------------------------------


@dataclass
class _Pending:
    arrival: int
    buyer: BuyerAgent
    line: DemandLine
    seller_id: str
    deceptive: bool
    is_broker: bool
    chain: bool
    promised_qty: int
    promised_date: int
    actual_qty: float
    actual_date: int
    price: float
    paid_on_accept: float          # 0 if escrowed
    supplier_cost_realized: float
    expected_value: float          # buyer's expected value at accept (for stars)


class Market:
    """One seeded MPX market run."""

    def __init__(self, cfg: MarketConfig, seed: int):
        self.cfg = cfg
        self.rng = np.random.default_rng(seed)
        self.led = L.Ledger()
        self._rfq_ctr = 0
        self._quote_ctr = 0
        # cash accounting (closed system: sum over agents stays 0)
        self.cash: dict[str, float] = {}
        # star reputations: id -> [sum, count]
        self.stars: dict[str, list] = {}
        # attestation history: id -> [n_delivered, sum_ratio, sum_ontime]
        self.att: dict[str, list] = {}
        # deception detection: id -> trades_to_flag (or None if never)
        self.detect: dict[str, Optional[int]] = {}
        self._deceptive_trades: dict[str, int] = {}
        self.pending: dict[int, list[_Pending]] = {}
        self.trades: list[TradeRecord] = []
        self.rfq_records: list[RFQRecord] = []
        self._spend_log: dict[str, list] = {}
        # A4 accumulators (broker chains)
        self._unserved_chain = 0.0
        self._chain_demand = 0.0
        self._broker_exp_margin = 0.0
        self._broker_real_margin_fix = 0.0
        self._build_population()

    # -- population ---------------------------------------------------------
    def _build_population(self) -> None:
        cfg = self.cfg
        rng = self.rng
        items = [f"item{i}" for i in range(cfg.n_items)]

        # suppliers
        self.suppliers: list[SupplierAgent] = []
        n_dec = int(math.ceil(cfg.deceptive_fraction * cfg.n_suppliers)) \
            if cfg.deceptive_fraction > 0 else 0
        for i in range(cfg.n_suppliers):
            k = int(rng.integers(1, 4))
            serves = list(rng.choice(items, size=min(k, len(items)), replace=False))
            c0 = float(rng.uniform(30, 55))
            c1 = float(rng.uniform(0.02, 0.08))
            cap = float(rng.integers(cfg.cap_lo, cfg.cap_hi + 1))
            expedite = float(rng.uniform(1.5, 4.0))
            inventory = float(rng.integers(200, 600))
            markup = float(rng.uniform(0.18, 0.32))
            min_markup = float(rng.uniform(0.03, 0.08))
            params = SupplierParams(c0, c1, cap, expedite, inventory,
                                    markup, min_markup)
            deceptive = i < n_dec
            sid = f"sup{i:03d}"
            self.suppliers.append(SupplierAgent(
                sid, serves, params, deceptive=deceptive,
                bad_prob=(cfg.deceptive_bad_prob if deceptive else 0.0),
                short_frac=(cfg.deceptive_short_frac if deceptive else 0.0)))
            self.cash[sid] = 0.0
            self.stars[sid] = [0.0, 0]
            self.att[sid] = [0, 0.0, 0.0]
            if deceptive:
                self.detect[sid] = None
                self._deceptive_trades[sid] = 0

        # index suppliers by item
        self.by_item: dict[str, list[int]] = {it: [] for it in items}
        for idx, s in enumerate(self.suppliers):
            for it in s.items:
                self.by_item[it].append(idx)

        # brokers
        self.brokers: list[BrokerAgent] = []
        for i in range(cfg.n_brokers):
            k = int(rng.integers(2, 5))
            serves = list(rng.choice(items, size=min(k, len(items)), replace=False))
            markup = float(rng.uniform(0.10, 0.20))
            handling = int(rng.integers(1, 4))
            est = float(rng.uniform(45, 70))
            bid = f"brk{i:03d}"
            self.brokers.append(BrokerAgent(bid, serves, markup, handling, est))
            self.cash[bid] = 0.0
        self.by_item_broker: dict[str, list[int]] = {it: [] for it in items}
        for idx, b in enumerate(self.brokers):
            for it in b.items:
                self.by_item_broker[it].append(idx)

        # buyers + demand lines
        self.buyers: list[BuyerAgent] = []
        line_id = 0
        for i in range(cfg.n_buyers):
            n_lines = int(rng.integers(cfg.lines_lo, cfg.lines_hi + 1))
            lines = []
            for _ in range(n_lines):
                item = str(rng.choice(items))
                qty = int(rng.integers(8, 40))
                unit_value = float(rng.uniform(cfg.value_lo, cfg.value_hi))
                need_by = int(rng.integers(cfg.need_by_lo, cfg.need_by_hi + 1))
                urgency = float(rng.uniform(cfg.urgency_lo, cfg.urgency_hi))
                release = int(rng.integers(0, max(1, cfg.ticks - 50)))
                chain_only = bool(cfg.chain_demand and rng.random() < 0.5)
                lines.append(DemandLine(line_id, item, qty, unit_value, need_by,
                                        urgency, release, chain_only=chain_only))
                line_id += 1
            budget = float(sum(l.qty * l.unit_value for l in lines) * 1.2)
            bid = f"buy{i:03d}"
            self.buyers.append(BuyerAgent(bid, budget, lines, lag=cfg.buyer_lag))
            self.cash[bid] = 0.0
            self._spend_log[bid] = []

    # -- reputation helpers -------------------------------------------------
    def star_mean(self, sid: str) -> float:
        s, n = self.stars.get(sid, [0.0, 0])
        return (s / n) if n else STAR_DEFAULT

    def is_attested(self, sid: str) -> bool:
        n, ratio_sum, ontime_sum = self.att[sid]
        if n < ATT_MIN_TRADES:
            return False
        return (ratio_sum / n) >= ATT_RATIO_BAR and (ontime_sum / n) >= ATT_RATIO_BAR

    # -- money transfer (conserved) ----------------------------------------
    def _transfer(self, payer: str, payee: str, amount: float) -> None:
        self.cash[payer] -= amount
        self.cash[payee] += amount

    # -- main loop ----------------------------------------------------------
    def run(self) -> MarketResult:
        total_demand_qty = sum(l.qty for b in self.buyers for l in b.lines)
        booked_qty = 0.0
        realized_ontime_qty = 0.0

        for tick in range(self.cfg.ticks):
            # 1) deliveries that arrive this tick (goods + escrow release + rating)
            for pend in self.pending.pop(tick, []):
                realized_ontime_qty += self._deliver(pend, tick)
            # 2) buyers act (fixed order -> deterministic RNG stream)
            for buyer in self.buyers:
                line = self._next_open_line(buyer, tick)
                if line is None:
                    continue
                booked = self._negotiate(buyer, line, tick)
                booked_qty += booked
                if booked <= 0.0 and not line.committed:
                    line.attempts += 1
                    if line.attempts >= self.cfg.max_attempts:
                        line.dead = True   # buyer gives up sourcing this line

        # flush any deliveries scheduled past the horizon (settle the books)
        for t in sorted(self.pending):
            for pend in self.pending[t]:
                realized_ontime_qty += self._deliver(pend, self.cfg.ticks)

        return self._finalize(total_demand_qty, booked_qty, realized_ontime_qty)

    def _next_open_line(self, buyer: BuyerAgent, tick: int) -> Optional[DemandLine]:
        """Earliest-released open line the buyer BELIEVES it still needs."""
        best = None
        for line in buyer.lines:
            if tick - line.last_rfq_tick < self.cfg.retry_gap:
                continue                      # cooldown: no per-tick RFQ spam
            if buyer.line_is_open(line, tick):
                if best is None or line.release_tick < best.release_tick:
                    best = line
        return best

    # -- one negotiation ----------------------------------------------------
    def _negotiate(self, buyer: BuyerAgent, line: DemandLine, tick: int) -> float:
        cfg = self.cfg
        self._rfq_ctr += 1
        rid = self._rfq_ctr
        line.last_rfq_tick = tick
        unmet = max(1, line.qty - int(line.delivered_qty))
        rfq = RFQ(rid, buyer.agent_id, line.item, unmet, line.need_by, tick,
                  line.unit_value, line.urgency,
                  buyer.believed_budget(tick, self._spend_log[buyer.agent_id]))
        self.led.append(L.EV_RFQ, tick, {
            "rfq": rid, "buyer": buyer.agent_id, "item": line.item,
            "qty": unmet, "need_by": line.need_by})

        if line.chain_only:
            return self._broker_path(buyer, line, rfq, tick)

        # gather candidate supplier quotes
        cand = self.by_item.get(line.item, [])
        if not cand:
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "no_supplier"})
            return 0.0
        avail = [i for i in cand if self.suppliers[i].params.inventory > 0]
        if not avail:
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "no_inventory"})
            return 0.0
        pick = avail if len(avail) <= cfg.candidates else list(
            self.rng.choice(avail, size=cfg.candidates, replace=False))

        best = None  # (score, supplier_idx, quote_qty, date, price, floor)
        for si in pick:
            sup = self.suppliers[si]
            terms = sup.quote_terms(line.item, unmet, line.need_by,
                                    max_lot=int(unmet))
            if terms is None:
                continue
            qq, dd, price, floor = terms
            self._quote_ctr += 1
            self.led.append(L.EV_QUOTE, tick, {
                "rfq": rid, "supplier": sup.agent_id, "qty": qq,
                "ship_date": dd, "price": round(price, 2)})
            reservation = buyer.reservation(qq, dd, line)
            exp_surplus = reservation - price
            # buyers softly prefer higher-rated suppliers (lets stars bite)
            score = exp_surplus + 3.0 * (self.star_mean(sup.agent_id) - 3.0)
            if best is None or score > best[0]:
                best = (score, si, qq, dd, price, floor, reservation, exp_surplus)

        if best is None:
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "no_quote"})
            return 0.0

        _, si, qq, dd, price, floor, reservation, _ = best
        sup = self.suppliers[si]

        # record for A1/A5-i regardless of trade outcome (chosen counterparty)
        rec = RFQRecord(
            line_id=line.line_id,
            supplier_id=sup.agent_id, need_qty=unmet, need_by=line.need_by,
            unit_value=line.unit_value, urgency=line.urgency,
            c0=sup.params.c0, c1=sup.params.c1, cap=sup.params.cap,
            expedite=sup.params.expedite, inventory=sup.params.inventory,
            min_markup=sup.params.min_markup, quote_qty=qq, quote_date=dd,
            quote_price=price, floor_price=floor, traded=False,
            agreed_price=0.0, price_only_joint=0.0)

        # price-only bargaining (session enforces price-only + <=3 rounds)
        session = Session(Quote(self._quote_ctr, rid, sup.agent_id, price, qq,
                                dd, tick + 50), rfq)
        ok = self._bargain(session, reservation, floor, tick, rid)
        if not ok:
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "no_deal"})
            if cfg.collect_rfqs:
                self.rfq_records.append(rec)
            return 0.0

        agreed = session.agreed_price
        # budget belief gate (StaleBuyer may believe it can afford when it can't)
        if rfq.budget_left < agreed:
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "budget"})
            if cfg.collect_rfqs:
                self.rfq_records.append(rec)
            return 0.0

        self._execute(buyer, line, sup, session, qq, dd, agreed, tick)

        if cfg.collect_rfqs:
            rec.traded = True
            rec.agreed_price = agreed
            # realized joint surplus of the price-only outcome (honest ctx for A1)
            lateness = max(0, dd - line.need_by)
            val = buyer_gross_value(qq, unmet, line.unit_value, line.urgency,
                                    lateness)
            cost = supplier_cost(qq, dd, sup.params.c0, sup.params.c1,
                                 sup.params.cap, sup.params.expedite)
            rec.price_only_joint = val - cost
            self.rfq_records.append(rec)
        return float(qq)

    def _bargain(self, session: Session, reservation: float, floor: float,
                 tick: int, rid: int) -> bool:
        """Deterministic price-only bargaining inside the ZOPA [floor, R], <=3
        buyer counters (the session enforces the cap). Outcome lands near the
        split; the exact price does NOT affect A1 (price only splits the pie).
        Every COUNTER is receipted to the ledger (the negotiation transcript)."""
        ask0 = session.standing_price
        if reservation < floor:
            session.walk()
            return False
        ceiling = min(ask0, reservation)
        if ceiling < floor:
            session.walk()
            return False
        target = floor + BARGAIN_SPLIT * (ceiling - floor)
        supplier_ask = ask0
        buyer_offer = floor + 0.15 * (target - floor)
        for _ in range(3):
            if buyer_offer >= supplier_ask:
                session.accept()          # buyer meets the ask
                return True
            session.counter(Counter(buyer_offer))
            self.led.append(L.EV_COUNTER, tick, {
                "rfq": rid, "round": session.counters,
                "price": round(buyer_offer, 2)})
            if buyer_offer >= target:
                session.accept()          # supplier takes the buyer's price
                return True
            new_ask = max(target, supplier_ask - 0.5 * (supplier_ask - target))
            session.concede(new_ask)
            supplier_ask = new_ask
            buyer_offer = min(supplier_ask,
                              buyer_offer + 0.5 * (supplier_ask - buyer_offer))
        if session.standing_price <= reservation:
            session.accept()
            return True
        session.walk()
        return False

    # -- execute an accepted direct trade ----------------------------------
    def _execute(self, buyer, line, sup, session, qq, dd, agreed, tick) -> None:
        session.settle()
        self.led.append(L.EV_ACCEPT, tick, {
            "buyer": buyer.agent_id, "supplier": sup.agent_id,
            "qty": qq, "ship_date": dd, "price": round(agreed, 2)})
        # deplete inventory + mark commitment (truth updates instantly)
        sup.params.inventory = max(0.0, sup.params.inventory - qq)
        if not line.committed:                 # first-commit tick (A3 lag anchor)
            line.committed = True
            line.committed_tick = tick

        roll = float(self.rng.random()) if sup.deceptive else 1.0
        actual_qty, actual_date = sup.actual_delivery(qq, dd, roll)

        # payment: optimistic pay-on-accept unless gated to escrow (A5-ii)
        escrow = self.cfg.attestation and not self.is_attested(sup.agent_id)
        paid = 0.0
        if not escrow:
            paid = agreed
            self._transfer(buyer.agent_id, sup.agent_id, agreed)
            sup.revenue += agreed
            buyer.spent += agreed
            self._spend_log[buyer.agent_id].append((tick, agreed))
            self.led.append(L.EV_SETTLE, tick, {
                "buyer": buyer.agent_id, "supplier": sup.agent_id,
                "amount": round(agreed, 2), "tier": "optimistic"})
        else:
            self.led.append(L.EV_SETTLE, tick, {
                "buyer": buyer.agent_id, "supplier": sup.agent_id,
                "amount": round(agreed, 2), "tier": "escrow"})

        exp_lateness = max(0, dd - line.need_by)
        expected_value = buyer_gross_value(qq, max(1, line.qty), line.unit_value,
                                           line.urgency, exp_lateness)
        cost_real = supplier_cost(actual_qty, actual_date, sup.params.c0,
                                  sup.params.c1, sup.params.cap,
                                  sup.params.expedite)
        arrival = tick + actual_date
        self.pending.setdefault(arrival, []).append(_Pending(
            arrival=arrival, buyer=buyer, line=line, seller_id=sup.agent_id,
            deceptive=sup.deceptive, is_broker=False, chain=False,
            promised_qty=qq, promised_date=dd, actual_qty=actual_qty,
            actual_date=actual_date, price=agreed, paid_on_accept=paid,
            supplier_cost_realized=cost_real, expected_value=expected_value))

    # -- broker two-hop path (A4) ------------------------------------------
    def _broker_path(self, buyer, line, rfq, tick) -> float:
        rid = rfq.rfq_id
        cand = self.by_item_broker.get(line.item, [])
        if not cand:
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "no_broker"})
            return 0.0
        unmet = rfq.qty
        bi = int(self.rng.choice(cand))
        brk = self.brokers[bi]
        qq, dd, price, floor = brk.quote_terms(unmet, line.need_by,
                                               max_lot=int(unmet))
        self.led.append(L.EV_QUOTE, tick, {
            "rfq": rid, "broker": brk.agent_id, "qty": qq,
            "ship_date": dd, "price": round(price, 2)})
        reservation = buyer.reservation(qq, dd, line)
        session = Session(Quote(self._quote_ctr + 1, rid, brk.agent_id, price,
                                qq, dd, tick + 50, is_broker=True), rfq)
        self._quote_ctr += 1
        if not self._bargain(session, reservation, floor, tick, rid):
            self.led.append(L.EV_FAIL, tick, {"rfq": rid, "why": "no_deal_broker"})
            return 0.0
        agreed = session.agreed_price
        session.settle()
        # buyer pays broker optimistically
        self._transfer(buyer.agent_id, brk.agent_id, agreed)
        buyer.spent += agreed
        self._spend_log[buyer.agent_id].append((tick, agreed))
        if not line.committed:
            line.committed = True
            line.committed_tick = tick
        self.led.append(L.EV_ACCEPT, tick, {
            "buyer": buyer.agent_id, "broker": brk.agent_id,
            "qty": qq, "price": round(agreed, 2)})

        # NOW the broker sources upstream at SPOT (no pre-commitment -> exposed)
        expected_up_cost = brk.est_unit_cost * qq
        up = [i for i in self.by_item.get(line.item, [])
              if self.suppliers[i].params.inventory >= qq]
        available = bool(up) and (self.rng.random() < self.cfg.spot_avail)
        exp_lateness = max(0, dd - line.need_by)
        expected_value = buyer_gross_value(qq, max(1, line.qty),
                                           line.unit_value, line.urgency,
                                           exp_lateness)
        if not available:
            # unserved chain demand: buyer paid, nothing ships (the MPX leak)
            self.led.append(L.EV_FAIL, tick, {
                "rfq": rid, "why": "unserved_chain", "broker": brk.agent_id})
            self.trades.append(TradeRecord(
                supplier_id=brk.agent_id, deceptive=False, is_broker=True,
                chain=True, price=agreed, amount_paid=agreed, promised_qty=qq,
                realized_qty=0.0, realized_cost=0.0,
                buyer_surplus=-agreed, on_time_full=False, stars=1))
            # unserved demand is tracked by unserved_chain_pct and the buyer's
            # -agreed surplus above; it is NOT counted in the broker margin
            # metric (that isolates spot-move compression on SERVED chains).
            self._unserved_chain += qq
            self._chain_demand += qq
            return 0.0

        si = int(self.rng.choice(up))
        sup = self.suppliers[si]
        # SPOT sourcing AFTER the buyer commit: no pre-commitment in MPX means
        # the broker takes whatever the spot multiplier is (mean > 1 -> hold-up).
        spot_mult = float(self.rng.uniform(self.cfg.spot_lo, self.cfg.spot_hi))
        c_act = expected_up_cost * spot_mult
        up_natural = math.ceil(qq / sup.params.cap) if sup.params.cap > 0 else 0
        base_cost = supplier_cost(qq, up_natural, sup.params.c0, sup.params.c1,
                                  sup.params.cap, sup.params.expedite)
        self._transfer(brk.agent_id, sup.agent_id, c_act)
        sup.params.inventory = max(0.0, sup.params.inventory - qq)
        sup.revenue += c_act
        sup.realized_cost += base_cost
        self._chain_demand += qq
        # margin metrics over SERVED chains only (unserved handled above)
        self._broker_exp_margin += (agreed - expected_up_cost)
        self._broker_real_margin_fix += (agreed - c_act)
        arrival = tick + dd
        self.pending.setdefault(arrival, []).append(_Pending(
            arrival=arrival, buyer=buyer, line=line, seller_id=brk.agent_id,
            deceptive=False, is_broker=True, chain=True, promised_qty=qq,
            promised_date=dd, actual_qty=float(qq), actual_date=dd,
            price=agreed, paid_on_accept=agreed,
            supplier_cost_realized=c_act, expected_value=expected_value))
        return float(qq)

    # -- delivery + rating --------------------------------------------------
    def _deliver(self, pend: _Pending, now: int) -> float:
        line = pend.line
        buyer = pend.buyer
        remaining_need = max(0, line.qty - int(line.delivered_qty))
        lateness = max(0, pend.actual_date - pend.promised_date) + \
            max(0, pend.promised_date - line.need_by)
        # value only counts toward unmet need; excess (double-buy) ~ worthless
        realized_value = buyer_gross_value(
            pend.actual_qty, remaining_need if remaining_need > 0 else 0,
            line.unit_value, line.urgency, lateness, residual_frac=0.0)
        line.delivered_qty += pend.actual_qty
        if line.delivered_qty >= line.qty - 1e-9:
            line.fulfilled = True

        # escrow release (A5-ii): pay only for what actually arrived. Optimistic
        # trades were already paid in full at settle (pend.paid_on_accept>0).
        amount_paid = pend.paid_on_accept
        sup = None if pend.is_broker else self._supplier_by_id(pend.seller_id)
        if pend.paid_on_accept == 0.0 and not pend.is_broker:
            frac = pend.actual_qty / pend.promised_qty if pend.promised_qty else 0.0
            release = pend.price * frac
            self._transfer(buyer.agent_id, pend.seller_id, release)
            buyer.spent += release
            amount_paid = release
            if sup is not None:
                sup.revenue += release
        # book realized cost against the direct seller (broker upstream cost is
        # booked in _broker_path against the true upstream supplier)
        if sup is not None:
            sup.realized_cost += pend.supplier_cost_realized

        on_time_full = (pend.actual_date <= line.need_by + 1e-9) and \
            (pend.actual_qty >= pend.promised_qty - 1e-9)
        buyer_surplus = realized_value - amount_paid

        # stars: satisfaction = fill ratio * lateness decay (self-reported)
        fill_ratio = (pend.actual_qty / pend.promised_qty) if pend.promised_qty else 0.0
        late_decay = 1.0 / (1.0 + 0.5 * max(0, pend.actual_date - line.need_by))
        sat = max(0.0, min(1.0, fill_ratio * late_decay))
        stars = int(max(1, min(5, round(1 + 4 * sat))))
        s = self.stars.setdefault(pend.seller_id, [0.0, 0])
        s[0] += stars
        s[1] += 1
        self.led.append(L.EV_DELIVER, now, {
            "seller": pend.seller_id, "qty": round(pend.actual_qty, 3),
            "promised_qty": pend.promised_qty,
            "late": max(0, pend.actual_date - line.need_by)})
        self.led.append(L.EV_RATE, now, {
            "seller": pend.seller_id, "stars": stars})

        # attestation history (for A5-ii gating on FUTURE trades)
        if not pend.is_broker:
            a = self.att[pend.seller_id]
            a[0] += 1
            a[1] += fill_ratio
            a[2] += 1.0 if pend.actual_date <= line.need_by else 0.0

        # deception detection: count deceptive trades, flag when star mean dips
        if pend.deceptive:
            self._deceptive_trades[pend.seller_id] = \
                self._deceptive_trades.get(pend.seller_id, 0) + 1
            if self.detect.get(pend.seller_id) is None and \
                    self.star_mean(pend.seller_id) < STAR_FLAG:
                self.detect[pend.seller_id] = self._deceptive_trades[pend.seller_id]

        self.trades.append(TradeRecord(
            supplier_id=pend.seller_id, deceptive=pend.deceptive,
            is_broker=pend.is_broker, chain=pend.chain, price=pend.price,
            amount_paid=amount_paid, promised_qty=pend.promised_qty,
            realized_qty=pend.actual_qty, realized_cost=pend.supplier_cost_realized,
            buyer_surplus=buyer_surplus, on_time_full=on_time_full, stars=stars))
        return pend.actual_qty if on_time_full else 0.0

    def _supplier_by_id(self, sid: str) -> Optional[SupplierAgent]:
        i = self._sup_index.get(sid) if hasattr(self, "_sup_index") else None
        if i is None:
            self._sup_index = {s.agent_id: k for k, s in enumerate(self.suppliers)}
            i = self._sup_index.get(sid)
        return self.suppliers[i] if i is not None else None

    # -- finalize -----------------------------------------------------------
    def _finalize(self, total_demand_qty, booked_qty, realized_ontime_qty):
        # accumulators for A4 initialized lazily; ensure present
        for attr in ("_unserved_chain", "_chain_demand", "_broker_exp_margin",
                     "_broker_real_margin_fix"):
            if not hasattr(self, attr):
                setattr(self, attr, 0.0)

        buyer_paid = sum(t.amount_paid for t in self.trades)
        buyer_value = sum(t.buyer_surplus + t.amount_paid for t in self.trades)
        buyer_surplus = sum(t.buyer_surplus for t in self.trades)
        harmful = sum(1 for t in self.trades if t.buyer_surplus < -1e-9)
        n_trades = len(self.trades)

        honest_margin = 0.0
        honest_n = 0
        dec_margin = 0.0
        dec_n = 0
        for s in self.suppliers:
            m = s.revenue - s.realized_cost
            if s.deceptive:
                dec_margin += m
                dec_n += 1
            else:
                honest_margin += m
                honest_n += 1

        # per-TRADE supplier margin (volume-independent: the unit economics of
        # the exploit, decoupled from the separate detection/volume effect)
        h_pt = [t.amount_paid - t.realized_cost for t in self.trades
                if not t.is_broker and not t.deceptive]
        d_pt = [t.amount_paid - t.realized_cost for t in self.trades
                if not t.is_broker and t.deceptive]
        honest_pt = (sum(h_pt) / len(h_pt)) if h_pt else 0.0
        dec_pt = (sum(d_pt) / len(d_pt)) if d_pt else 0.0

        broker_rev = sum(self.cash[b.agent_id] for b in self.brokers)  # net cash
        total_sup_rev = sum(s.revenue for s in self.suppliers)

        metrics = {
            "n_trades": n_trades,
            "n_rfqs": self._rfq_ctr,
            "total_demand_qty": total_demand_qty,
            "fill_optimistic": booked_qty / total_demand_qty if total_demand_qty else 0.0,
            "fill_realized": realized_ontime_qty / total_demand_qty if total_demand_qty else 0.0,
            "buyer_paid": buyer_paid,
            "buyer_value_realized": buyer_value,
            "buyer_surplus_realized": buyer_surplus,
            "harmful_accepts": harmful,
            "harmful_per_100": (100.0 * harmful / n_trades) if n_trades else 0.0,
            "honest_margin_mean": (honest_margin / honest_n) if honest_n else 0.0,
            "deceptive_margin_mean": (dec_margin / dec_n) if dec_n else 0.0,
            "honest_margin_per_trade": honest_pt,
            "deceptive_margin_per_trade": dec_pt,
            "honest_trades": len(h_pt),
            "deceptive_trades": len(d_pt),
            "honest_n": honest_n,
            "deceptive_n": dec_n,
            "broker_net_cash": broker_rev,
            "total_supplier_revenue": total_sup_rev,
            "unserved_chain_qty": self._unserved_chain,
            "chain_demand_qty": self._chain_demand,
            "unserved_chain_pct": (100.0 * self._unserved_chain / self._chain_demand)
                                  if self._chain_demand else 0.0,
            "broker_expected_margin": self._broker_exp_margin,
            "broker_realized_margin": self._broker_real_margin_fix,
            "broker_margin_compression_pct": (
                100.0 * (self._broker_exp_margin - self._broker_real_margin_fix)
                / self._broker_exp_margin) if self._broker_exp_margin > 1e-9 else 0.0,
            "cash_residual": sum(self.cash.values()),
        }
        # detection: mean trades-to-flag among flagged deceptive suppliers
        flagged = [v for v in self.detect.values() if v is not None]
        metrics["deceptive_flagged"] = len(flagged)
        metrics["deceptive_total"] = len(self.detect)
        metrics["mean_trades_to_flag"] = (sum(flagged) / len(flagged)) if flagged else None

        return MarketResult(metrics=metrics, trades=self.trades,
                            rfqs=self.rfq_records, ledger=self.led,
                            supplier_stars=self.stars, detection=self.detect)
