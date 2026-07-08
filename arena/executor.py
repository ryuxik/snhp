"""Genome -> engine adapters. This is the ONLY place the arena touches the
negotiation library, and it adds no strategy of its own — it maps a scenario +
two genomes into the exact inputs the shipped recommenders expect, paces the
alternating offers one turn at a time (as generators the world clocks), and reads
the shipped acceptance rule. Every strategic decision is the engine's.

Determinism hazard (documented): BayesianParticleFilter draws from *global*
NumPy RNG with no injection point, so we reseed the global RNG from
(neg_seed, turn) before every engine call and keep the sim single-threaded.

Utility frames (see scenarios.py): position x in [0,1]; seller utility = x,
buyer utility = 1 - x. `walk_margin` bluffs the DECLARED reservation (binds both
the advisor floor and the acceptance rule — Schelling commitment); ENERGY is paid
on TRUE surplus. Staked agents don't bluff (attestation = truthful inputs).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

import numpy as np

from arena.config import ArenaConfig
from arena.genome import Genome
from arena.scenarios import PriceScenario, BundleScenario

# Import arena.config FIRST (done above) so SNHP_* particle budgets are set,
# then the engine.
from gametheory.negotiation.sell import sell_next_offer
from gametheory.negotiation.buy import buy_next_offer
from gametheory.negotiation.bundle import negotiate_bundle
from gametheory.negotiation import snhp_accept

_WALK_MARGIN_SPAN = 0.10  # walk_margin gene scales this fraction of the position span
# ^ arena-side gene scaling (NOT an engine change): sets how hard a bluff can
# shrink the *declared* ZOPA. 0.10 keeps over-bluffing a real, selected mistake
# while leaving a healthy fraction of true-ZOPA deals closable within the horizon.


def _seed(neg_seed: int, turn: int) -> None:
    """Reseed the global NumPy RNG deterministically before an engine call."""
    h = hashlib.blake2b(f"{neg_seed}:{turn}".encode(), digest_size=8).digest()
    np.random.seed(int.from_bytes(h, "big") & 0x7FFFFFFF)


def _declared_reservation(true_r: float, walk_margin: float, staked: bool,
                          direction: int) -> float:
    """Bluff a tougher floor. direction=+1 (seller: bluff higher), -1 (buyer:
    bluff lower). Staked agents post the truth."""
    if staked:
        return true_r
    delta = walk_margin * _WALK_MARGIN_SPAN * direction
    return float(np.clip(true_r + delta, 0.02, 0.98))


@dataclass
class Side:
    genome: Genome
    role: str          # "seller" | "buyer"
    true_r: float      # true reservation POSITION
    agent_id: int


@dataclass
class NegOutcome:
    deal: bool
    close_pos: Optional[float]
    surplus_seller: float      # realized utility above TRUE reservation (>=0), minus round cost
    surplus_buyer: float
    rounds_used: int
    peer: bool


def run_price_negotiation(seller: Side, buyer: Side, sc: PriceScenario,
                          deadline: int, neg_seed: int, cfg: ArenaConfig):
    """Generator: yields partial event dicts (type + fields) one per turn; the
    final yielded event is 'neg.accept' or 'neg.walk' and carries the outcome.
    Also returns a NegOutcome via StopIteration.value for the world."""
    peer = bool(seller.genome.staked and buyer.genome.staked)

    # Declared (possibly bluffed) reservations; ignored for staked pairs' bluff.
    s_decl = _declared_reservation(seller.true_r, seller.genome.walk_margin,
                                   peer or seller.genome.staked, +1)
    b_decl = _declared_reservation(buyer.true_r, buyer.genome.walk_margin,
                                   peer or buyer.genome.staked, -1)
    # Advisor reservations in each side's UTILITY frame.
    s_res_u = s_decl                    # seller utility(pos) = pos
    b_res_u = 1.0 - b_decl              # buyer utility(pos) = 1 - pos

    # Patience makes a side hold firm longer, bounded by the TRUE deadline: an
    # impatient agent reports a shorter deadline to its own advisor (concedes
    # fast, closes early, smaller share); a patient one reports the full horizon
    # (holds out). Kept <= true deadline so the late-deadline acceptance branch
    # (which reads true t) still fires for everyone by the real deadline.
    s_deadline = max(1, int(round(deadline * (0.6 + 0.4 * seller.genome.patience))))
    b_deadline = max(1, int(round(deadline * (0.6 + 0.4 * buyer.genome.patience))))

    s_offers: list[float] = []          # seller-proposed positions (= seller utility)
    b_offers_as_s: list[float] = []     # buyer-proposed positions in seller utility (= pos)
    b_offers: list[float] = []          # buyer-proposed positions
    s_offers_as_b: list[float] = []     # seller-proposed positions in buyer utility (= 1-pos)

    last_to_seller: Optional[float] = None   # buyer's standing offer position
    last_to_buyer: Optional[float] = None    # seller's standing offer position
    close_pos: Optional[float] = None
    turn = 0

    # NOTE on staking & peer_mode: peer_mode is the engine's cooperative
    # playbook, validated on MULTI-ISSUE contracts (+0.186 joint welfare). On a
    # single-issue divide-the-dollar it is pathological — both peers open
    # demanding >55% of the one pie and impasse (~9% close rate). So the honest
    # staking benefit on PRICE deals is the *truthful reservation* channel:
    # staked agents don't bluff (see s_decl/b_decl above), which preserves the
    # true ZOPA and closes more deals. That is attestation's actual causal
    # mechanism ("a credible declaration channel"). peer_mode stays off here;
    # bundle deals get the true-BATNA-exchange benefit instead.
    def s_advice():
        _seed(neg_seed, turn)
        return sell_next_offer(
            my_reservation=s_res_u, opponent_offer_history=list(b_offers_as_s),
            my_offer_history=list(s_offers), deadline_rounds=s_deadline,
            pareto_knob=seller.genome.pareto_knob, peer_mode=False)

    def b_advice():
        _seed(neg_seed, turn)
        return buy_next_offer(
            my_reservation=b_res_u, seller_offer_history=list(s_offers_as_b),
            my_offer_history=list(b_offers), deadline_rounds=b_deadline,
            pareto_knob=buyer.genome.pareto_knob,
            defenses=[], peer_mode=False)

    while turn < deadline and close_pos is None:
        # t reaches 1.0 on the final turn so the late-deadline safety net fires.
        t_frac = min(1.0, (turn + 1) / max(deadline, 1))
        if turn % 2 == 0:
            # Seller's turn: maybe accept buyer's standing offer, else propose.
            adv = s_advice()
            target = float(adv["recommended_offer"])
            if last_to_seller is not None:
                recv_u = last_to_seller  # seller utility from buyer's position
                if snhp_accept(recv_u, target, s_res_u, t_frac):
                    close_pos = last_to_seller
                    turn += 1
                    break
            if _should_walk(adv, target, s_res_u, last_to_seller, turn):
                yield {"type": "neg.walk", "actor": "seller", "reason": "below_floor"}
                return _walk_outcome(turn, cfg, peer)
            pos = target
            s_offers.append(pos)
            s_offers_as_b.append(1.0 - pos)
            last_to_buyer = pos
            yield {"type": "neg.offer", "turn": turn, "actor": "seller",
                   "pos": round(pos, 4), "action": "counter",
                   "spread": round(_spread(last_to_buyer, last_to_seller), 4)}
        else:
            adv = b_advice()
            u_b = float(adv["recommended_offer"])   # buyer utility
            pos = 1.0 - u_b                          # position buyer proposes
            if last_to_buyer is not None:
                recv_u = 1.0 - last_to_buyer         # buyer utility from seller's position
                if snhp_accept(recv_u, u_b, b_res_u, t_frac):
                    close_pos = last_to_buyer
                    turn += 1
                    break
            if _should_walk(adv, u_b, b_res_u, (1.0 - last_to_buyer) if last_to_buyer is not None else None, turn):
                yield {"type": "neg.walk", "actor": "buyer", "reason": "below_floor"}
                return _walk_outcome(turn, cfg, peer)
            b_offers.append(pos)
            b_offers_as_s.append(pos)
            last_to_seller = pos
            yield {"type": "neg.offer", "turn": turn, "actor": "buyer",
                   "pos": round(pos, 4), "action": "counter",
                   "spread": round(_spread(last_to_buyer, last_to_seller), 4)}
        turn += 1

    if close_pos is None:
        yield {"type": "neg.walk", "actor": "timeout", "reason": "timeout"}
        return _walk_outcome(turn, cfg, peer)

    # Realized surplus on TRUE reservations, minus round costs both sides.
    cost = cfg.round_cost * turn
    surplus_s = max(0.0, close_pos - seller.true_r) - cost
    surplus_b = max(0.0, (1.0 - close_pos) - (1.0 - buyer.true_r)) - cost
    yield {"type": "neg.accept", "actor": "close", "pos": round(close_pos, 4),
           "surplus": {"seller": round(max(0.0, surplus_s), 4),
                       "buyer": round(max(0.0, surplus_b), 4)},
           "rounds": turn}
    return NegOutcome(deal=True, close_pos=close_pos,
                      surplus_seller=max(0.0, surplus_s),
                      surplus_buyer=max(0.0, surplus_b), rounds_used=turn, peer=peer)


def _spread(last_to_buyer, last_to_seller) -> float:
    if last_to_buyer is None or last_to_seller is None:
        return 1.0
    return abs(last_to_buyer - last_to_seller)


def _should_walk(adv: dict, target_u: float, res_u: float,
                 opp_offer_in_my_u: Optional[float], turn: int) -> bool:
    """Walk when we've effectively fully conceded (recommended offer is at/below
    our floor) and the opponent's standing offer still doesn't clear it — i.e.
    no overlap, continuing only burns round costs. Rewards prompt walks on
    no-ZOPA scenarios (the walk-accuracy skill)."""
    if turn < 3:
        return False
    fully_conceded = target_u <= res_u + 0.02
    opp_below = opp_offer_in_my_u is not None and opp_offer_in_my_u < res_u - 0.01
    return fully_conceded and opp_below


def _walk_outcome(turn: int, cfg: ArenaConfig, peer: bool) -> NegOutcome:
    cost = cfg.round_cost * max(turn, 1)
    return NegOutcome(deal=False, close_pos=None,
                      surplus_seller=-cost, surplus_buyer=-cost,
                      rounds_used=turn, peer=peer)


# ─── Bundle (multi-issue) market negotiation ────────────────────────────────

def _bundle_view(genome: Genome, sc: BundleScenario, role: str):
    """Build the negotiate_bundle `issues` list from this agent's frame + its
    genome priorities. Directions are common knowledge (seller-favorable dir vs
    its complement); only priority weights are private."""
    issues = []
    for (name, labels), dirs in zip(sc.issues, sc.seller_dirs):
        if role == "seller":
            my_u = list(dirs)
            their_u = [round(1.0 - d, 4) for d in dirs]
        else:
            my_u = [round(1.0 - d, 4) for d in dirs]
            their_u = list(dirs)
        issues.append({"name": name, "options": list(labels),
                       "my_utility": my_u, "their_utility": their_u})
    focus = genome.bundle_focus[:len(sc.issues)]
    priorities = {name: float(w) for (name, _), w in zip(sc.issues, focus)}
    return issues, priorities


def _bundle_realized(genome: Genome, sc: BundleScenario, role: str, package: dict) -> float:
    """Weighted-average utility this agent gets from a settled package (matches
    the engine's u_self = my_per_dim @ normalized_weights)."""
    issues, priorities = _bundle_view(genome, sc, role)
    w = np.array([max(0.0, priorities[i["name"]]) for i in issues], dtype=float)
    if w.sum() <= 0:
        w = np.ones(len(issues))
    w = w / w.sum()
    total = 0.0
    for wi, iss in zip(w, issues):
        opt = package.get(iss["name"])
        idx = iss["options"].index(opt) if opt in iss["options"] else 0
        total += wi * iss["my_utility"][idx]
    return float(total)


def run_bundle_negotiation(seller: Side, buyer: Side, sc: BundleScenario,
                           deadline: int, neg_seed: int, cfg: ArenaConfig):
    """Generator over a multi-issue logrolling negotiation using negotiate_bundle
    on each side. Staked pairs exchange TRUE BATNAs (widening the feasible set)."""
    peer = bool(seller.genome.staked and buyer.genome.staked)
    s_issues, s_pri = _bundle_view(seller.genome, sc, "seller")
    b_issues, b_pri = _bundle_view(buyer.genome, sc, "buyer")

    # BATNAs: default blind 0.40; staked pairs pass each other's true 0.30.
    s_batna = 0.30
    b_batna = 0.30
    s_their_est = b_batna if peer else 0.40
    b_their_est = s_batna if peer else 0.40

    s_offers: list[dict] = []
    b_offers: list[dict] = []
    close_pkg: Optional[dict] = None
    close_by: Optional[str] = None
    turn = 0

    while turn < deadline and close_pkg is None:
        if turn % 2 == 0:
            _seed(neg_seed, turn)
            adv = negotiate_bundle(issues=s_issues, their_offers=b_offers or None,
                                   my_priorities=s_pri, my_batna=s_batna,
                                   their_batna_estimate=s_their_est)
            if adv["action"] == "accept" and b_offers:
                close_pkg, close_by = b_offers[-1], "seller"
                turn += 1
                break
            if adv["action"] == "walk":
                yield {"type": "neg.walk", "actor": "seller", "reason": "no_package"}
                return _walk_outcome(turn, cfg, peer)
            pkg = adv["recommended_offer"]
            s_offers.append(pkg)
            yield {"type": "neg.offer", "turn": turn, "actor": "seller",
                   "package": pkg, "action": "counter", "kind": "bundle"}
        else:
            _seed(neg_seed, turn)
            adv = negotiate_bundle(issues=b_issues, their_offers=s_offers or None,
                                   my_priorities=b_pri, my_batna=b_batna,
                                   their_batna_estimate=b_their_est)
            if adv["action"] == "accept" and s_offers:
                close_pkg, close_by = s_offers[-1], "buyer"
                turn += 1
                break
            if adv["action"] == "walk":
                yield {"type": "neg.walk", "actor": "buyer", "reason": "no_package"}
                return _walk_outcome(turn, cfg, peer)
            pkg = adv["recommended_offer"]
            b_offers.append(pkg)
            yield {"type": "neg.offer", "turn": turn, "actor": "buyer",
                   "package": pkg, "action": "counter", "kind": "bundle"}
        turn += 1

    if close_pkg is None:
        yield {"type": "neg.walk", "actor": "timeout", "reason": "timeout"}
        return _walk_outcome(turn, cfg, peer)

    cost = cfg.round_cost * turn
    u_s = _bundle_realized(seller.genome, sc, "seller", close_pkg)
    u_b = _bundle_realized(buyer.genome, sc, "buyer", close_pkg)
    surplus_s = max(0.0, u_s - s_batna) - cost
    surplus_b = max(0.0, u_b - b_batna) - cost
    yield {"type": "neg.accept", "actor": "close", "kind": "bundle",
           "package": close_pkg, "closed_by": close_by,
           "surplus": {"seller": round(max(0.0, surplus_s), 4),
                       "buyer": round(max(0.0, surplus_b), 4)},
           "rounds": turn}
    return NegOutcome(deal=True, close_pos=None,
                      surplus_seller=max(0.0, surplus_s),
                      surplus_buyer=max(0.0, surplus_b), rounds_used=turn, peer=peer)
