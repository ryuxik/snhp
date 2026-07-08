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


# ─── The tactic layer: how an agent FOLLOWS its SNHP advisor ────────────────
# SNHP computes every offer; the tactic_family gene is the agent's DISCIPLINE
# in following that advice — opening anchors and acceptance thresholds — the
# same architecture as the shipped product, where an LLM compliance layer sits
# between the advisor and the table (gametheory/negotiation/_sim.py). This is
# what makes "strategy" a real, selected trait rather than a cosmetic label:
# a Closer that snubs early deals impasses more in thin markets; a Conceder
# banks volume; an Anchorer squeezes wide ones. `open_aggression` scales the
# whole disposition, so the continuous gene evolves WITHIN a tactic.

def _tactic_offer(g: Genome, advisor_u: float, turn: int, t: float,
                  opp_step: float = 0.0) -> float:
    """Possibly override the advisor's recommended offer (own-utility frame).
    Holds are SUSTAINED (decay toward the advisor over the whole horizon), so a
    bold agent's standing offer is still high when the counterparty's
    late-deadline acceptance fires — brinkmanship that pays when it closes and
    walks when it doesn't. That's the real margin-vs-volume trade."""
    a = g.open_aggression
    fam = g.tactic_family
    if fam == "anchorer":
        anchor = 0.80 + 0.17 * a
        w = (1.0 - t) ** 0.7                      # slow decay: still holding late
        return max(advisor_u, min(0.97, w * anchor + (1 - w) * advisor_u))
    if fam == "boulware":
        lift = (0.10 + 0.14 * a) * (1.0 - t ** 2)  # concede only near the end
        return max(advisor_u, min(0.97, advisor_u + lift))
    if fam == "mirror":
        # reactive: give ground in proportion to the opponent's last concession
        lift = max(0.0, (0.08 + 0.06 * a) - 1.5 * max(0.0, opp_step))
        return max(advisor_u, min(0.97, advisor_u + lift * (1.0 - t)))
    if fam == "conceder":
        # shade slightly under the advisor: closes even faster, thinner split
        return max(0.05, advisor_u - (0.02 + 0.03 * a) * (1.0 - t))
    return advisor_u  # patient / closer: the advisor's own curve, verbatim


def _tactic_accept_bar(g: Genome, advisor_u: float, t: float,
                       opp_conceded: bool) -> float:
    """The utility bar an incoming offer must clear (fed to snhp_accept as the
    advisor target). Offsets shift how eagerly the agent takes the deal."""
    a = g.open_aggression
    fam = g.tactic_family
    if fam == "conceder":
        return advisor_u - (0.03 + 0.04 * a)          # takes deals readily
    if fam == "boulware":
        return advisor_u + (0.03 + 0.06 * a) * (1.0 - t)  # hard to please early
    if fam == "closer":
        if t < 0.55 + 0.2 * a:
            return 1.5                                 # snubs everything early...
        return advisor_u - 0.04                        # ...then snipes the deadline
    if fam == "mirror":
        # tit-for-tat acceptance: only warms up if the opponent gave ground
        return advisor_u if opp_conceded else advisor_u + 0.06 + 0.04 * a
    if fam == "patient":
        return advisor_u + (0.02 + 0.03 * a) if t < 0.85 else advisor_u
    return advisor_u  # anchorer: normal acceptance; its edge is the opening


def _tactic_no_walk(g: Genome, t: float) -> bool:
    """Patient agents refuse to walk early — outlasting IS the strategy."""
    return g.tactic_family == "patient" and t < 0.9


_CONCESSION_SPAN = 0.15  # max utility the evolvable schedule can shift an offer


def _concession_mod(g: Genome, t: float, opp_step: float, era_signal: float) -> float:
    """The EVOLVABLE layer: a learned utility offset on top of the advisor's
    recommendation, a small function of (hold-early, reactivity, era). All-zero
    coefficients => 0 (raw advisor). This is the room evolution has to find a
    schedule the fixed recommender does not express. tanh-bounded."""
    c = g.concession
    if c[0] == 0.0 and c[1] == 0.0 and c[2] == 0.0 and c[3] == 0.0:
        return 0.0
    z = c[0] + c[1] * (1.0 - t) + c[2] * float(np.clip(opp_step * 4.0, -1, 1)) + c[3] * era_signal
    return _CONCESSION_SPAN * float(np.tanh(z))


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
    # era signal the evolvable concession schedule can key off (+1 sellers' market
    # rewards holding, -1 buyers'), so a strategy can be market-conditional
    _ERA_SIG = {"sellers": 1.0, "buyers": -1.0, "contract": 0.4, "symmetric": 0.0}
    era_sig = _ERA_SIG.get(getattr(sc, "era", "symmetric"), 0.0)

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
    # mechanism ("a credible declaration channel"). peer_mode stays off for PRICE
    # (its cooperative descent is infeasible on single-issue divide-the-dollar);
    # BUNDLE pacts run the engine's real multi-issue peer_mode instead.
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
            # has the buyer given ground since their previous offer? (for mirror)
            s_opp_step = (b_offers_as_s[-1] - b_offers_as_s[-2]) if len(b_offers_as_s) >= 2 else 0.0
            s_opp_conc = s_opp_step > 0.005
            if last_to_seller is not None:
                recv_u = last_to_seller  # seller utility from buyer's position
                bar = _tactic_accept_bar(seller.genome, target, t_frac, s_opp_conc)
                if snhp_accept(recv_u, bar, s_res_u, t_frac):
                    close_pos = last_to_seller
                    turn += 1
                    break
            if not _tactic_no_walk(seller.genome, t_frac) and \
                    _should_walk(adv, target, s_res_u, last_to_seller, turn):
                yield {"type": "neg.walk", "actor": "seller", "reason": "below_floor"}
                return _walk_outcome(turn, cfg, peer)
            pos = _tactic_offer(seller.genome, target, turn, t_frac, s_opp_step)
            pos = float(np.clip(pos + _concession_mod(seller.genome, t_frac, s_opp_step, era_sig), 0.02, 0.99))
            s_offers.append(pos)
            s_offers_as_b.append(1.0 - pos)
            last_to_buyer = pos
            yield {"type": "neg.offer", "turn": turn, "actor": "seller",
                   "pos": round(pos, 4), "adv_pos": round(target, 4),
                   "action": "counter",
                   "spread": round(_spread(last_to_buyer, last_to_seller), 4)}
        else:
            adv = b_advice()
            u_b = float(adv["recommended_offer"])   # buyer utility
            b_opp_step = (s_offers_as_b[-1] - s_offers_as_b[-2]) if len(s_offers_as_b) >= 2 else 0.0
            b_opp_conc = b_opp_step > 0.005
            if last_to_buyer is not None:
                recv_u = 1.0 - last_to_buyer         # buyer utility from seller's position
                bar = _tactic_accept_bar(buyer.genome, u_b, t_frac, b_opp_conc)
                if snhp_accept(recv_u, bar, b_res_u, t_frac):
                    close_pos = last_to_buyer
                    turn += 1
                    break
            if not _tactic_no_walk(buyer.genome, t_frac) and \
                    _should_walk(adv, u_b, b_res_u, (1.0 - last_to_buyer) if last_to_buyer is not None else None, turn):
                yield {"type": "neg.walk", "actor": "buyer", "reason": "below_floor"}
                return _walk_outcome(turn, cfg, peer)
            offer_u = _tactic_offer(buyer.genome, u_b, turn, t_frac, b_opp_step)
            offer_u = float(np.clip(offer_u + _concession_mod(buyer.genome, t_frac, b_opp_step, era_sig), 0.02, 0.99))
            pos = 1.0 - offer_u                      # position buyer proposes
            b_offers.append(pos)
            b_offers_as_s.append(pos)
            last_to_seller = pos
            yield {"type": "neg.offer", "turn": turn, "actor": "buyer",
                   "pos": round(pos, 4), "adv_pos": round(1.0 - u_b, 4),
                   "action": "counter",
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
# The evolvable multi-issue CEILING (genome.bundle_tactic = sharpness, cooperation,
# concession), the logrolling analog of the price concession layer. All-zero =
# the raw recommender with honest, unsharpened priorities.
_BUNDLE_SHARP_BASE = 1.3     # sharpness gene -> priority exponent 2**(base*gene)
_BUNDLE_COOP_BASE = 0.6      # neutral peer cooperation (== bundle_peer_cooperation)
_BUNDLE_COOP_SPAN = 0.4      # cooperation gene shifts the peer dial by +-this
_BUNDLE_CONCEDE_SPAN = 0.25  # concession gene shifts the accept time-gate by +-this


def _bundle_issues(sc: BundleScenario, role: str) -> list:
    """The negotiate_bundle `issues` list (per-option utility structure) from a
    role's frame. Directions are common knowledge; only priorities are private."""
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
    return issues


def _true_weights(genome: Genome, n: int) -> np.ndarray:
    """The agent's HONEST priority weights (what its realized payoff is measured
    on) — raw normalized bundle_focus."""
    w = np.array([max(0.0, x) for x in genome.bundle_focus[:n]], dtype=float)
    return w / w.sum() if w.sum() > 0 else np.ones(n) / n


def _declared_priorities(genome: Genome, sc: BundleScenario) -> dict:
    """The priorities the agent DECLARES to the engine — its true weights sharpened
    by the evolvable `sharpness` gene. Declaring sharper than you truly are presses
    the engine's logroll to win your top issues; over-sharpening concedes mid-value
    issues too cheaply. Gene 0 -> exponent 1 -> honest weights."""
    n = len(sc.issues)
    w = np.clip(_true_weights(genome, n), 1e-6, None)
    exp = 2.0 ** (_BUNDLE_SHARP_BASE * float(genome.bundle_tactic[0]))
    w = w ** exp
    w = w / w.sum()
    return {name: float(wi) for (name, _), wi in zip(sc.issues, w)}


def _peer_cooperation(genome: Genome) -> float:
    """This agent's cooperation dial for VERIFIED-PEER bundle deals — the tuned
    default shifted by the evolvable `cooperation` gene. This is where attestation
    pays on multi-issue: two staked cooperators grow the joint pie via logrolling
    (validated: bundle_validation --cooperation). Gene 0 -> 0.6 (the shipped
    peer default), so a neutral genome reproduces current peer behavior exactly."""
    return float(np.clip(_BUNDLE_COOP_BASE + _BUNDLE_COOP_SPAN * genome.bundle_tactic[1],
                         0.0, 1.0))


def _bundle_realized(genome: Genome, sc: BundleScenario, role: str, package: dict) -> float:
    """Utility this agent TRULY gets from a settled package — measured on its
    honest weights (not the possibly-sharpened declaration)."""
    issues = _bundle_issues(sc, role)
    w = _true_weights(genome, len(issues))
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
    s_issues = _bundle_issues(sc, "seller")
    b_issues = _bundle_issues(sc, "buyer")
    s_pri = _declared_priorities(seller.genome, sc)   # sharpened by the ceiling gene
    b_pri = _declared_priorities(buyer.genome, sc)

    # BATNAs: default blind 0.40; staked pairs pass each other's true 0.30.
    s_batna = 0.30
    b_batna = 0.30
    s_their_est = b_batna if peer else 0.40
    b_their_est = s_batna if peer else 0.40
    # Cooperation dial: the peer logrolling payoff, set per-side by the evolvable
    # gene, ONLY among verified peers. Adversarial deals stay pure Nash (None).
    s_coop = _peer_cooperation(seller.genome) if peer else None
    b_coop = _peer_cooperation(buyer.genome) if peer else None

    s_offers: list[dict] = []
    b_offers: list[dict] = []
    close_pkg: Optional[dict] = None
    close_by: Optional[str] = None
    turn = 0

    def _tactic_bundle_accept(g: Genome, t: float, n_opp_offers: int) -> bool:
        """Acceptance discipline on bundle deals: may the tactic take the engine's
        'accept' now? (Closers snub early; mirrors want to see movement first.)
        The evolvable `concession` gene shifts the time-gate: >0 accept earlier,
        <0 hold out longer."""
        fam = g.tactic_family
        shift = _BUNDLE_CONCEDE_SPAN * g.bundle_tactic[2]
        if fam == "closer":
            return t >= (0.55 + 0.2 * g.open_aggression) - shift
        if fam == "mirror":
            return n_opp_offers >= (1 if shift > 0.12 else 2)
        if fam == "boulware" or fam == "patient":
            return t >= 0.4 - shift
        return True  # conceder / anchorer take the engine's accept as-is

    while turn < deadline and close_pkg is None:
        t_frac = min(1.0, (turn + 1) / max(deadline, 1))
        if turn % 2 == 0:
            _seed(neg_seed, turn)
            # verified pact (both staked): run the engine's multi-issue PEER path
            # — truthful BATNA (already exchanged above) + cooperative efficient
            # selection. THIS is where the +0.186-lineage cooperation actually
            # lives now, on the multi-issue frontier where it is valid.
            adv = negotiate_bundle(issues=s_issues, their_offers=b_offers or None,
                                   my_priorities=s_pri, my_batna=s_batna,
                                   their_batna_estimate=s_their_est, peer_mode=peer,
                                   cooperation=s_coop)
            if adv["action"] == "accept" and b_offers and \
                    _tactic_bundle_accept(seller.genome, t_frac, len(b_offers)):
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
                                   their_batna_estimate=b_their_est, peer_mode=peer,
                                   cooperation=b_coop)
            if adv["action"] == "accept" and s_offers and \
                    _tactic_bundle_accept(buyer.genome, t_frac, len(s_offers)):
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
