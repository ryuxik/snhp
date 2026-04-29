"""
B2B Human Negotiation Archetypes for SNHP Benchmark.

14 archetypes based on documented world-class negotiation styles:

ORIGINAL 7:
1. Anchorer        — Extreme first offer, slow retreat
2. Nibbler         — Cooperative then last-second extras
3. BATNABluffer    — Claims alternatives, holds firm
4. SilentHardliner — Minimal movement, concedes only under pressure
5. ReciprocityPlyr — Small concession, expects large return
6. GoodCopBadCop   — Alternates tough/reasonable offers
7. TheCloser       — Reasonable throughout, pushes deal at ~70% time

NEW 7 (world-class negotiator styles):
8.  TacticalEmpath   — Chris Voss: mirrors opponent, calibrated anchors
9.  PrincipledNeg    — Fisher/Ury: interest-based, expands pie
10. SovietPatience   — Herb Cohen: extreme patience, info hoarding
11. CialdiniPlayer   — Cialdini: reciprocity traps, commitment lock
12. Logroller        — Raiffa: issue-by-issue trading
13. SplitTheDiff     — Corporate default: always proposes midpoint
14. DeadlineExploiter — Procurement: holds firm, drops bomb at final step
"""

from negmas.sao import SAONegotiator, SAOState, ResponseType
from negmas.outcomes import Outcome
from typing import Optional, List, Tuple
import numpy as np


class B2BBase(SAONegotiator):
    """Base class for B2B human-style negotiators."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._my_offers: List[Tuple] = []
        self._opp_offers: List[Tuple] = []
        self._sorted_outcomes: Optional[List[Tuple]] = None
        self._initialized: bool = False
        self._rng = np.random.default_rng()
    
    def _ensure_init(self):
        if self._initialized:
            return
        if self.ufun is None or self.nmi is None:
            return
        self._initialized = True
        outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=2000))
        utilities = [(o, float(self.ufun(o))) for o in outcomes if self.ufun(o) is not None]
        utilities.sort(key=lambda x: x[1], reverse=True)
        self._sorted_outcomes = utilities
    
    def _outcome_at_util(self, target: float) -> Optional[Outcome]:
        """Find outcome nearest to target utility."""
        if not self._sorted_outcomes:
            return None
        best, best_d = None, float('inf')
        for o, u in self._sorted_outcomes:
            d = abs(u - target)
            if d < best_d:
                best_d = d
                best = o
        return best
    
    def _my_util(self, offer) -> float:
        if self.ufun is None or offer is None:
            return 0.0
        u = self.ufun(offer)
        return float(u) if u is not None else 0.0
    
    def _total_steps(self) -> int:
        return getattr(self.nmi, 'n_steps', 10) or 10

    def _opp_best_util(self) -> float:
        """Best utility from any opponent offer so far."""
        if not self._opp_offers:
            return 0.0
        return max(self._my_util(o) for o in self._opp_offers)


# ═══════════════════════════════════════════════════
#  ORIGINAL 7 ARCHETYPES
# ═══════════════════════════════════════════════════

class Anchorer(B2BBase):
    """Extreme first offer (0.97), then slow linear retreat to 0.55."""
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        target = 0.97 if t < 0.01 else 0.95 - 0.40 * t
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.70: return ResponseType.ACCEPT_OFFER
        if t > 0.7 and u >= 0.55: return ResponseType.ACCEPT_OFFER
        if t > 0.95 and u >= 0.45: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class Nibbler(B2BBase):
    """Cooperative then last-second extras. Exploits commitment bias."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._nibbled: bool = False
        self._pre_nibble_target: float = 0.55
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        if t < 0.7:
            target = 0.80 - 0.30 * (t / 0.7)
            self._pre_nibble_target = target
        elif not self._nibbled and t > 0.8:
            self._nibbled = True
            target = self._pre_nibble_target + 0.08
        else:
            target = self._pre_nibble_target - 0.02 * ((t - 0.8) / 0.2)
        offer = self._outcome_at_util(max(0.40, target))
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.60: return ResponseType.ACCEPT_OFFER
        if t > 0.6 and u >= 0.50: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.42: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class BATNABluffer(B2BBase):
    """Claims strong alternatives, holds 70%, then concedes quickly."""
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        if t < 0.70:
            target = 0.90 - 0.08 * (t / 0.70)
        else:
            progress = (t - 0.70) / 0.30
            target = 0.82 - 0.35 * progress
        offer = self._outcome_at_util(max(0.40, target))
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.75: return ResponseType.ACCEPT_OFFER
        if t > 0.70 and u >= 0.55: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.45: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class SilentHardliner(B2BBase):
    """Concedes 1% per step from 0.92. Floor at 0.50. Take it or leave it."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._step_count: int = 0
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        self._step_count += 1
        target = max(0.50, 0.92 - self._step_count * 0.01)
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.70: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.55: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class ReciprocityPlayer(B2BBase):
    """Small concessions, expects larger ones in return. Holds if not reciprocated."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._my_total_concession: float = 0.0
        self._opp_total_concession: float = 0.0
        self._last_target: float = 0.85
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        if len(self._opp_offers) >= 2:
            last_u = self._my_util(self._opp_offers[-1])
            prev_u = self._my_util(self._opp_offers[-2])
            self._opp_total_concession += max(0, last_u - prev_u)
        base_step = 0.02
        if self._my_total_concession > 0.05 and self._opp_total_concession < self._my_total_concession * 0.5:
            base_step = 0.005
        elif self._opp_total_concession > self._my_total_concession * 1.5:
            base_step = 0.01
        self._last_target = max(0.45, self._last_target - base_step)
        self._my_total_concession += base_step
        offer = self._outcome_at_util(self._last_target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.65: return ResponseType.ACCEPT_OFFER
        if t > 0.7 and u >= 0.52: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.45: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class GoodCopBadCop(B2BBase):
    """Alternates tough/reasonable offers. Bad cop anchors, good cop closes."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._step: int = 0
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        self._step += 1
        t = state.relative_time
        baseline = 0.80 - 0.30 * t
        target = baseline + 0.12 if self._step % 2 == 0 else baseline - 0.05
        target = max(0.40, min(0.95, target))
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.65: return ResponseType.ACCEPT_OFFER
        if t > 0.6 and u >= 0.52: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.43: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class TheCloser(B2BBase):
    """Skilled pragmatist. Reasonable concessions, eager to close. Aspiration-style."""
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        target = max(0.42, 0.75 - 0.30 * (t ** 1.5))
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        if u >= 0.55: return ResponseType.ACCEPT_OFFER
        if t > 0.5 and u >= 0.48: return ResponseType.ACCEPT_OFFER
        if t > 0.80 and u >= 0.42: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


# ═══════════════════════════════════════════════════
#  NEW 7 ARCHETYPES — World-Class Negotiator Styles
# ═══════════════════════════════════════════════════

class TacticalEmpath(B2BBase):
    """
    Chris Voss (Never Split the Difference).
    
    Core tactics:
    - Mirrors opponent's last offer (propose something close to their position)
    - Uses calibrated anchors: starts reasonable, then holds
    - "Late no": accepts freely early, then suddenly stops accepting
    - Exploits opponent's expectation of continued cooperation

    In real B2B: "It seems like delivery is really important to you..."
    then uses that intel to extract concessions on price.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._phase = "mirror"  # mirror → anchor → close
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        
        if t < 0.30 and self._opp_offers:
            # MIRROR: propose close to opponent's last offer but slightly better for us
            last_opp_util = self._my_util(self._opp_offers[-1])
            target = last_opp_util + 0.15  # slightly above what they offered us
            target = min(0.85, target)
            self._phase = "mirror"
        elif t < 0.70:
            # ANCHOR: found their range, now hold firm
            self._phase = "anchor"
            target = 0.70 - 0.05 * ((t - 0.30) / 0.40)  # 0.70 → 0.65 slowly
        else:
            # CLOSE: concede to get the deal
            self._phase = "close"
            progress = (t - 0.70) / 0.30
            target = 0.65 - 0.20 * progress  # 0.65 → 0.45
        
        offer = self._outcome_at_util(max(0.42, target))
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        if t < 0.30:
            # Early: accept easily to build rapport ("yes" momentum)
            if u >= 0.55: return ResponseType.ACCEPT_OFFER
        elif t < 0.70:
            # "Late no": suddenly raise standards
            if u >= 0.68: return ResponseType.ACCEPT_OFFER
        else:
            # Endgame: reasonable close
            if u >= 0.50: return ResponseType.ACCEPT_OFFER
            if t > 0.90 and u >= 0.43: return ResponseType.ACCEPT_OFFER
        
        return ResponseType.REJECT_OFFER


class PrincipledNegotiator(B2BBase):
    """
    Fisher & Ury (Getting to Yes).
    
    Core tactics:
    - Insists on "objective criteria" (proposes 50/50 splits early)
    - Expands the pie: looks for integrative solutions
    - Never positional: always reframes as interests
    - Pleasant but firm — won't be bullied but won't bully

    In real B2B: "Let's look at market benchmarks to find something fair."
    """
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        
        # Always aims for ~0.55 (fair split with slight self-advantage)
        # Concedes very slowly because "fairness" is the anchor
        if t < 0.50:
            target = 0.65 - 0.10 * (t / 0.50)  # 0.65 → 0.55
        else:
            target = 0.55 - 0.08 * ((t - 0.50) / 0.50)  # 0.55 → 0.47
        
        offer = self._outcome_at_util(max(0.45, target))
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        # Fair-minded but firm: won't accept significantly below 50/50
        if u >= 0.52: return ResponseType.ACCEPT_OFFER
        if t > 0.70 and u >= 0.47: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.43: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class SovietPatience(B2BBase):
    """
    Herb Cohen (You Can Negotiate Anything).
    
    Core tactics:
    - Extreme patience: barely moves for 90%+ of negotiation
    - Vast time horizon: acts as if deadline doesn't exist
    - Information asymmetry: observes opponent's urgency, never reveals own
    - Final concession: drops significantly only if absolutely necessary

    In real B2B: Soviet delegation style — stone-faced for 3 days,
    then "we might consider..." on the last morning.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._step_count: int = 0
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        self._step_count += 1
        t = state.relative_time
        
        if t < 0.90:
            # STONE WALL: 0.5% concession per step
            target = max(0.60, 0.88 - self._step_count * 0.005)
        else:
            # Final concession: drops 15% in the last 10%
            progress = (t - 0.90) / 0.10
            target = max(0.45, 0.60 - 0.15 * progress)
        
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        # Only accepts very favorable deals — extreme patience
        if u >= 0.75: return ResponseType.ACCEPT_OFFER
        if t > 0.90 and u >= 0.50: return ResponseType.ACCEPT_OFFER
        if t > 0.95 and u >= 0.43: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class CialdiniPlayer(B2BBase):
    """
    Robert Cialdini (Influence).
    
    Core tactics:
    - Reciprocity trap: makes a visible concession, then demands larger return
    - Commitment lock: starts with small agreements, then escalates
    - Creates obligation: "I gave you X, now you owe me Y"
    - Gets opponent to commit to small "yes", then leverages consistency

    In real B2B: "We already agreed on delivery terms. Since I was flexible
    there, I need you to meet me on price."
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._gave_concession: bool = False
        self._demand_phase: bool = False
        self._last_target: float = 0.82
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        
        if t < 0.25:
            # GIFT: make a visible, purposeful concession early
            target = 0.82 - 0.15 * (t / 0.25)  # drop from 0.82 → 0.67
            self._gave_concession = True
        elif t < 0.70 and self._gave_concession:
            # DEMAND: I gave you something, now hold firm
            self._demand_phase = True
            target = 0.67 + 0.03  # actually go BACK UP slightly
        else:
            # Close: concede gracefully
            self._demand_phase = False
            progress = (t - 0.70) / 0.30 if t > 0.70 else 0
            target = max(0.45, 0.67 - 0.20 * progress)
        
        self._last_target = target
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        if self._demand_phase:
            # During demand phase: high threshold
            if u >= 0.65: return ResponseType.ACCEPT_OFFER
        else:
            if u >= 0.55: return ResponseType.ACCEPT_OFFER
            if t > 0.80 and u >= 0.47: return ResponseType.ACCEPT_OFFER
            if t > 0.92 and u >= 0.42: return ResponseType.ACCEPT_OFFER
        
        return ResponseType.REJECT_OFFER


class Logroller(B2BBase):
    """
    Howard Raiffa (The Art and Science of Negotiation).
    
    Core tactics:
    - Issue-by-issue trading: concedes on low-priority, demands on high
    - Identifies opponent's priorities by observing which concessions they make
    - "I'll give you X if you give me Y" (package deals)
    - Explores the Pareto frontier systematically

    In real B2B: "We can flex on warranty, but delivery time is critical."
    
    Implementation: proposes outcomes from different parts of the utility
    space to probe opponent preferences, then exploits discovered tradeoffs.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._probing: bool = True
        self._probe_results: List[Tuple[Tuple, float]] = []  # (offer, their_response_util)
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        
        if t < 0.40 and self._sorted_outcomes:
            # PROBING: offer outcomes from different parts of the utility space
            # to learn which issues opponent cares about
            self._probing = True
            # Select from band of acceptable outcomes (0.55-0.75) with variety
            band = [(o, u) for o, u in self._sorted_outcomes if 0.55 <= u <= 0.75]
            if band:
                # Pick different outcomes to probe: rotate through indices
                idx = len(self._my_offers) % max(1, len(band) // 3)
                step = max(1, len(band) // 4)
                pick_idx = min(idx * step, len(band) - 1)
                offer = band[pick_idx][0]
            else:
                offer = self._outcome_at_util(0.65)
        else:
            # EXPLOIT: propose best outcome for us from what they've shown willingness toward
            self._probing = False
            
            if self._opp_offers:
                # Find the offer from opponent that gave both of us reasonable utility
                best_joint = None
                best_joint_score = -1
                for o in self._opp_offers:
                    our_u = self._my_util(o)
                    if our_u > best_joint_score:
                        best_joint_score = our_u
                        best_joint = o
                
                # Counter near their best offer to us, but slightly better for us
                if best_joint_score > 0.40:
                    target = min(0.75, best_joint_score + 0.08)
                else:
                    progress = (t - 0.40) / 0.60
                    target = max(0.42, 0.65 - 0.20 * progress)
            else:
                target = max(0.42, 0.65 - 0.20 * t)
            
            offer = self._outcome_at_util(target)
        
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        if u >= 0.60: return ResponseType.ACCEPT_OFFER
        if t > 0.50 and u >= 0.50: return ResponseType.ACCEPT_OFFER
        if t > 0.85 and u >= 0.43: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class SplitTheDiff(B2BBase):
    """
    The Corporate Default.
    
    Always proposes the midpoint between their last offer and opponent's last.
    This is what most untrained negotiators do — "let's meet in the middle."
    
    Predictable, exploitable, but closes deals quickly.
    
    In real B2B: "Look, you want $100, I want $80. Let's do $90."
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._my_last_util: float = 0.80
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        
        if not self._opp_offers:
            # First offer: start at 0.80
            target = 0.80
        else:
            # Split the difference: midpoint between our last and their last
            their_util = self._my_util(self._opp_offers[-1])
            target = (self._my_last_util + their_util) / 2
            # But don't go below 0.42
            target = max(0.42, target)
        
        self._my_last_util = target
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        # Very accommodating — will accept anything that's "fair enough"
        if u >= 0.50: return ResponseType.ACCEPT_OFFER
        if t > 0.60 and u >= 0.45: return ResponseType.ACCEPT_OFFER
        if t > 0.85 and u >= 0.40: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class DeadlineExploiter(B2BBase):
    """
    The Procurement Deadline Exploiter.
    
    Holds absolutely firm for 90% of the negotiation, then makes one
    massive concession at the very last step. Forces opponent to choose:
    accept a mediocre deal now or gamble on this final offer.
    
    Exploits: sunk cost fallacy, deadline pressure, loss aversion.
    
    In real B2B: "You've been negotiating for 3 weeks. Here's our final offer.
    Take it today or we go to RFP."
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dropped: bool = False
        self._step_count: int = 0
    
    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        self._step_count += 1
        t = state.relative_time
        
        if t < 0.85:
            # HOLD: barely budge, 0.5% per step
            target = max(0.65, 0.90 - self._step_count * 0.005)
        else:
            # BOMB: massive single concession
            if not self._dropped:
                self._dropped = True
                target = 0.52  # sudden 15%+ drop
            else:
                target = max(0.45, 0.52 - 0.07 * ((t - 0.85) / 0.15))
        
        offer = self._outcome_at_util(target)
        if offer: self._my_offers.append(offer)
        return offer
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        
        # Very high standards early, relaxes only at deadline
        if u >= 0.75: return ResponseType.ACCEPT_OFFER
        if t > 0.85 and u >= 0.52: return ResponseType.ACCEPT_OFFER
        if t > 0.95 and u >= 0.45: return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class FairDemand(B2BBase):
    """
    Nash Demand Game optimal: always propose 0.51 utility, accept >= 0.49.
    
    The simplest possible "fair" strategy. Proposes a consistent slight
    advantage and accepts anything near-fair. No adaptation, no modeling,
    no state. If this beats complex strategies, complexity is a liability.
    """
    
    def propose(self, state):
        self._ensure_init()
        return self._outcome_at_util(0.51)
    
    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        u = self._my_util(offer)
        t = state.relative_time
        
        # Accept anything >= 0.49 (near-fair split)
        if u >= 0.49:
            return ResponseType.ACCEPT_OFFER
        # At deadline, accept anything >= 0.42
        if t > 0.90 and u >= 0.42:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


# ═══════════════════════════════════════════════════
#  REGISTRY
# ═══════════════════════════════════════════════════
#  HUMAN-LIKE BIAS ARCHETYPES (Binmore: behavioral game theory)
# ═══════════════════════════════════════════════════
#
# The original 14 archetypes are tactical strategies (Anchorer, Cialdini, etc.).
# These four model COGNITIVE BIASES from the behavioral negotiation literature:
#
# 1. AnchoringBias  — Tversky & Kahneman (1974): people anchor on first offer
#    and inadequately adjust. Implementation: concede much slower than the
#    rational concession curve once anchored.
# 2. FairnessNorm   — Güth, Schmittberger, Schwarze (1982) ultimatum game:
#    reject offers where self surplus < ~40% of joint surplus, even if above
#    BATNA. Captures human "spite" responses to perceived unfairness.
# 3. LossAversion   — Kahneman & Tversky (1979): losses loom ~2x larger than
#    equivalent gains. Implementation: refuses to walk back from a previously
#    proposed offer (won't accept a deal worse than what it last proposed).
# 4. SunkCostFallacy — escalation of commitment: the more rounds invested,
#    the more pressure to close even when rational play would walk.
#
# All are programmatic (no LLM cost) so they integrate cheaply into the
# tournament. Each has a SAOMechanism propose/respond pair that NegMAS
# accepts directly.


class AnchoringBiasedBuyer(B2BBase):
    """
    Anchors on its opening offer at 0.95 utility-to-self. Concession rate is
    deliberately ~30% of what's rational given the time remaining; the bias
    is asymmetric updating from the anchor (Tversky-Kahneman 1974).

    Empirically: this opponent should be HARDER than Anchorer because the
    concession curve isn't a clean linear retreat — it sticks near 0.85-0.90
    for most of the negotiation and only collapses at the final two steps.
    """

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        # Anchor sticks near 0.90 for first 80% of game, then collapses
        if t < 0.80:
            target = 0.95 - 0.07 * t  # 0.95 → 0.894 over first 80%
        else:
            late_t = (t - 0.80) / 0.20
            target = 0.89 - 0.39 * late_t  # 0.89 → 0.50 over last 20%
        offer = self._outcome_at_util(target)
        if offer:
            self._my_offers.append(offer)
        return offer

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        if offer is not None:
            self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        # Asymmetric acceptance: anchored on 0.85, slow to budge
        if u >= 0.85:
            return ResponseType.ACCEPT_OFFER
        if t > 0.85 and u >= 0.65:
            return ResponseType.ACCEPT_OFFER
        if t > 0.97 and u >= 0.50:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class FairnessNormBuyer(B2BBase):
    """
    Ultimatum-game-style fairness enforcer. Estimates joint surplus from
    own + opponent offer trajectories and rejects deals where self share
    falls below ~40% of the joint surplus, EVEN IF above BATNA.

    This is the canonical pattern from Güth, Schmittberger, Schwarze (1982):
    humans reject 80/20 splits at cost to self because they perceive the
    split as unfair. SNHP-style optimizers that maximize self-utility fall
    into this trap by proposing aggressive splits.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fairness_floor = 0.40  # require >=40% of joint surplus

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        # Demand fair share: starts asking for slightly above 50/50
        target = 0.55 - 0.10 * t  # 0.55 → 0.45 over the game
        offer = self._outcome_at_util(target)
        if offer:
            self._my_offers.append(offer)
        return offer

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        if offer is not None:
            self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time

        # Fairness check: reject if our share is below the fairness floor of
        # the joint surplus, regardless of BATNA-positivity. This produces
        # the ultimatum-game spite pattern.
        # Estimate joint surplus from observed offers: max combined utility
        # we've seen so far is a lower bound on what's achievable.
        if self._opp_offers and self._sorted_outcomes:
            opp_util_estimate = 1.0 - u  # rough zero-sum projection
            joint = max(0.5, u + opp_util_estimate)
            our_share = u / joint if joint > 0 else 0.5
            if our_share < self._fairness_floor:
                # Spite-rejection: do not accept even if above BATNA
                return ResponseType.REJECT_OFFER

        # Standard acceptance otherwise
        if u >= 0.50:
            return ResponseType.ACCEPT_OFFER
        if t > 0.80 and u >= 0.40:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class LossAverseBuyer(B2BBase):
    """
    Once this player proposes an offer at utility-to-self U, it won't accept
    or propose anything below U - margin. Refuses to "walk back" from a
    previously stated position.

    This is Kahneman-Tversky loss aversion: giving up something you've
    already mentally claimed is felt as a loss, weighted ~2x a forgone gain.
    Captures the "I already said no to less than X, accepting now feels
    worse than walking" pattern.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._high_water_mark: float = 0.0  # highest utility we've claimed
        self._loss_aversion_margin: float = 0.05

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        # Standard linear concession from 0.85 to 0.45...
        target = 0.85 - 0.40 * t
        # ...but never below high-water-mark - margin
        target = max(target, self._high_water_mark - self._loss_aversion_margin)
        offer = self._outcome_at_util(target)
        if offer:
            self._my_offers.append(offer)
            u = self._my_util(offer)
            self._high_water_mark = max(self._high_water_mark, u)
        return offer

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        if offer is not None:
            self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time

        # Loss aversion: never accept below high-water-mark - margin, even
        # if above BATNA. Makes us un-exploitable by patient lowballers.
        loss_aversion_floor = self._high_water_mark - self._loss_aversion_margin
        if u < loss_aversion_floor:
            return ResponseType.REJECT_OFFER

        if u >= 0.65:
            return ResponseType.ACCEPT_OFFER
        if t > 0.80 and u >= 0.50:
            return ResponseType.ACCEPT_OFFER
        if t > 0.97 and u >= max(0.40, loss_aversion_floor):
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


class SunkCostBuyer(B2BBase):
    """
    Escalating commitment: the more rounds invested, the more pressure to
    close even when walking away would be rational. Concession curve
    accelerates with round count, not just relative time.

    Captures the sunk-cost fallacy: humans struggle to walk away from
    negotiations they've already invested time in, even when the BATNA
    is becoming the better choice.
    """

    def propose(self, state: SAOState) -> Optional[Outcome]:
        self._ensure_init()
        t = state.relative_time
        n_offers = len(self._my_offers)
        # Sunk-cost acceleration: each prior offer increases concession pressure
        sunk_cost_pressure = min(0.30, n_offers * 0.04)
        target = 0.85 - 0.40 * t - sunk_cost_pressure
        target = max(0.30, target)  # floor
        offer = self._outcome_at_util(target)
        if offer:
            self._my_offers.append(offer)
        return offer

    def respond(self, state: SAOState, source: str = None) -> ResponseType:
        self._ensure_init()
        offer = state.current_offer
        if offer is not None:
            self._opp_offers.append(offer)
        u = self._my_util(offer)
        t = state.relative_time
        n_invested = max(len(self._my_offers), len(self._opp_offers))

        # Lower acceptance bar as more rounds are sunk
        bar = max(0.30, 0.65 - 0.04 * n_invested)
        if u >= bar:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER


# ═══════════════════════════════════════════════════

# Ground-truth opponent type labels for the validation framework.
# Used by snhp/eval_metrics.py to bucket per-type utility (separate from
# the runtime OpponentModel classifier — these are the "true" labels we
# evaluate the classifier against). Categories follow the same 4-class
# taxonomy the classifier uses: BOULWARE / CONCEDER / MIRROR / RANDOM.
#
# Assignment rationale (from each agent's docstring + propose() shape):
#   BOULWARE  — extreme open + slow concession, refuses to converge
#   CONCEDER  — aspiration-style cooperative descent
#   MIRROR    — reflects/responds to our offers (tit-for-tat-ish)
#   RANDOM    — erratic, exploits cognitive biases inconsistently
OPPONENT_TYPE_TAGS: dict[str, str] = {
    # BOULWARE — firm anchorers
    "Anchorer":           "BOULWARE",
    "BATNA Bluffer":      "BOULWARE",
    "Silent Hardliner":   "BOULWARE",
    "Soviet Patience":    "BOULWARE",
    "Deadline Exploiter": "BOULWARE",
    "Anchoring Bias":     "BOULWARE",
    "Loss Averse":        "BOULWARE",
    # CONCEDER — cooperative aspiration-style
    "The Closer":         "CONCEDER",   # docstring: "Aspiration-style"
    "Principled":         "CONCEDER",   # Fisher & Ury 50/50
    "Logroller":          "CONCEDER",   # cross-attribute trades
    "Split-the-Diff":     "CONCEDER",
    "Fair Demand":        "CONCEDER",
    "Fairness Norm":      "CONCEDER",
    "Aspiration":         "CONCEDER",   # added by run_round_robin (NegMAS classic)
    # MIRROR — tit-for-tat-ish reflectors
    "Reciprocity":        "MIRROR",
    "GoodCop/BadCop":     "MIRROR",
    "Tactical Empath":    "MIRROR",     # docstring: "Mirrors opponent's last offer"
    "Cialdini":           "MIRROR",
    # RANDOM — erratic, bias-exploiting
    "Nibbler":            "RANDOM",     # last-second extras pattern
    "Sunk Cost":          "RANDOM",
}


B2B_OPPONENTS = {
    # Original 7
    "Anchorer": Anchorer,
    "Nibbler": Nibbler,
    "BATNA Bluffer": BATNABluffer,
    "Silent Hardliner": SilentHardliner,
    "Reciprocity": ReciprocityPlayer,
    "GoodCop/BadCop": GoodCopBadCop,
    "The Closer": TheCloser,
    # New 7 — World-class styles
    "Tactical Empath": TacticalEmpath,
    "Principled": PrincipledNegotiator,
    "Soviet Patience": SovietPatience,
    "Cialdini": CialdiniPlayer,
    "Logroller": Logroller,
    "Split-the-Diff": SplitTheDiff,
    "Deadline Exploiter": DeadlineExploiter,
    # Benchmark
    "Fair Demand": FairDemand,
    # Human-bias archetypes (Sprint D)
    "Anchoring Bias": AnchoringBiasedBuyer,
    "Fairness Norm": FairnessNormBuyer,
    "Loss Averse": LossAverseBuyer,
    "Sunk Cost": SunkCostBuyer,
}

# MiCRO synchronizes per-round concession with whoever moved last —
# functionally a stricter mirror, so tag it as MIRROR for ground-truth.
OPPONENT_TYPE_TAGS["MiCRO"] = "MIRROR"
