"""Gauntlet seats — the policies that occupy one side of a match.

A seat sees a SeatView (its private frame: per-option utilities, TRUE priority
weights, BATNA, the offer history) and returns an Action. Three seats:

  EngineSeat — the standardized SNHP sparring partner / reference row: honest
      priorities, adversarial negotiate_bundle each turn (the RAW recommender
      config the arena science benchmarks against).
  NaiveSeat  — the published-baseline caricature: anchors on its best package,
      concedes toward the middle option on every issue, accepts late. This is
      the "splits every issue" bargainer the frontier oracle's naive term models.
  LLMSeat    — a frontier model over an API (anthropic SDK or OpenAI-compatible
      HTTP), speaking strict JSON. condition="advised" injects the SNHP
      recommendation for the model to adopt or overrule (advice-following is
      itself scored).

Determinism: engine calls reseed the global NumPy RNG per (match_seed, turn)
exactly like arena.executor does, so gauntlet numbers are reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from gametheory.negotiation.bundle import negotiate_bundle

BATNA = 0.30            # both sides' true walk-away (matches arena.executor)
BATNA_EST = 0.40        # blind estimate of the other side's (adversarial default)


@dataclass
class SeatView:
    """One seat's private frame of the match at its turn to act."""
    role: str                       # "seller" | "buyer"
    issues: list                    # negotiate_bundle-style issue dicts (my frame)
    weights: dict                   # TRUE priorities {issue: w}, sum 1 — payoff basis
    my_offers: list                 # packages I've put on the table (oldest first)
    opp_offers: list                # packages they've put on the table (oldest first)
    turn: int                       # 0-based global turn index
    deadline: int                   # total turns available
    advisor: Optional[dict] = None  # advised condition: SNHP rec for THIS turn


@dataclass
class Action:
    kind: str                       # "offer" | "accept" | "walk"
    package: Optional[dict] = None  # for "offer": {issue: option_label}
    meta: dict = field(default_factory=dict)


def _reseed(match_seed: int, turn: int) -> None:
    """Deterministic global-RNG reseed before an engine call (same recipe as
    arena.executor._seed, different domain tag so runs don't collide)."""
    h = hashlib.blake2b(f"gauntlet:{match_seed}:{turn}".encode(), digest_size=8).digest()
    np.random.seed(int.from_bytes(h, "big") & 0x7FFFFFFF)


def engine_advice(view: SeatView, match_seed: int) -> dict:
    """One negotiate_bundle call from this seat's frame (honest priorities,
    adversarial path) — used by EngineSeat to act and by the advised condition
    as the injected recommendation."""
    _reseed(match_seed, view.turn)
    return negotiate_bundle(
        issues=view.issues,
        their_offers=view.opp_offers or None,
        my_priorities=dict(view.weights),
        my_batna=BATNA,
        their_batna_estimate=BATNA_EST,
    )


class EngineSeat:
    """SNHP itself in the seat — the reference row and standard counterparty."""
    name = "snhp-engine"

    def __init__(self, match_seed: int):
        self._seed = match_seed

    def act(self, view: SeatView) -> Action:
        adv = engine_advice(view, self._seed)
        if adv["action"] == "accept" and view.opp_offers:
            return Action("accept")
        if adv["action"] == "walk":
            return Action("walk")
        return Action("offer", dict(adv["recommended_offer"]))


class GenomeSeat:
    """The arena's evolved champion in the seat. Preferences come from the
    scenario like every candidate's — the genome brings only its POLICY: the
    sharpness gene reshapes the priorities it DECLARES to the engine, and its
    tactic family (shifted by the concession gene) gates when it may accept.
    A neutral genome reproduces EngineSeat exactly (same as the arena)."""

    def __init__(self, genome, match_seed: int, name: str = "evolved-champion"):
        from arena.executor import _BUNDLE_SHARP_BASE, _BUNDLE_CONCEDE_SPAN
        self.genome = genome
        self.name = name
        self._seed = match_seed
        self._sharp_base = _BUNDLE_SHARP_BASE
        self._concede_span = _BUNDLE_CONCEDE_SPAN

    def _declared(self, view: SeatView) -> dict:
        w = np.array([max(1e-6, float(view.weights.get(iss["name"], 0.0)))
                      for iss in view.issues])
        w = w ** (2.0 ** (self._sharp_base * float(self.genome.bundle_tactic[0])))
        w = w / w.sum()
        return {iss["name"]: float(wi) for iss, wi in zip(view.issues, w)}

    def _may_accept(self, t: float, n_opp_offers: int) -> bool:
        # arena.executor._tactic_bundle_accept, on the gauntlet's clock
        g = self.genome
        shift = self._concede_span * g.bundle_tactic[2]
        fam = g.tactic_family
        if fam == "closer":
            return t >= (0.55 + 0.2 * g.open_aggression) - shift
        if fam == "mirror":
            return n_opp_offers >= (1 if shift > 0.12 else 2)
        if fam in ("boulware", "patient"):
            return t >= 0.4 - shift
        return True

    def act(self, view: SeatView) -> Action:
        h = hashlib.blake2b(f"champion:{self._seed}:{view.turn}".encode(),
                            digest_size=8).digest()
        np.random.seed(int.from_bytes(h, "big") & 0x7FFFFFFF)
        adv = negotiate_bundle(
            issues=view.issues, their_offers=view.opp_offers or None,
            my_priorities=self._declared(view), my_batna=BATNA,
            their_batna_estimate=BATNA_EST)
        t = (view.turn + 1) / max(view.deadline, 1)
        if adv["action"] == "accept" and view.opp_offers \
                and self._may_accept(t, len(view.opp_offers)):
            return Action("accept")
        if adv["action"] == "walk":
            return Action("walk")
        return Action("offer", dict(adv["recommended_offer"]))


class NaiveSeat:
    """Anchor-then-split baseline: open at your best package, concede one issue
    per turn toward its middle option, accept once time is nearly up or the
    opponent's package clears a modest bar. No logrolling — by construction."""
    name = "naive-split"

    def act(self, view: SeatView) -> Action:
        n = len(view.issues)
        t = (view.turn + 1) / max(view.deadline, 1)
        # my utility of their latest package
        if view.opp_offers:
            u_theirs = _package_utility(view, view.opp_offers[-1])
            if u_theirs >= 0.5 or (t >= 0.75 and u_theirs > BATNA):
                return Action("accept")
        # best-for-me option per issue, conceded issue-by-issue toward the middle
        pkg = {}
        conceded = int(t * n + 1e-9)  # 0,1,..,n issues moved to their midpoint
        for k, iss in enumerate(view.issues):
            opts, mu = iss["options"], iss["my_utility"]
            if k < conceded:
                pkg[iss["name"]] = opts[len(opts) // 2]
            else:
                pkg[iss["name"]] = opts[int(np.argmax(mu))]
        return Action("offer", pkg)


def action_from_obj(obj, view: SeatView) -> Optional[Action]:
    """Validate a decoded {action, package?} object into a legal Action —
    the shared contract for LLM replies and community HTTP bots. Returns None
    on anything illegal (unknown action, incomplete package, premature accept)."""
    if not isinstance(obj, dict):
        return None
    act = str(obj.get("action", "")).lower()
    if act == "accept":
        return Action("accept") if view.opp_offers else None
    if act == "walk":
        return Action("walk")
    if act == "offer":
        pkg = obj.get("package") or {}
        out = {}
        for iss in view.issues:
            v = pkg.get(iss["name"])
            if v is None or str(v) not in [str(o) for o in iss["options"]]:
                return None
            # normalize back to the canonical option object
            out[iss["name"]] = iss["options"][[str(o) for o in iss["options"]].index(str(v))]
        return Action("offer", out)
    return None


def _package_utility(view: SeatView, package: dict) -> float:
    """This seat's TRUE utility of a package (same math as executor._bundle_realized)."""
    total = 0.0
    for iss in view.issues:
        w = float(view.weights.get(iss["name"], 0.0))
        opt = package.get(iss["name"])
        idx = iss["options"].index(opt) if opt in iss["options"] else 0
        total += w * float(iss["my_utility"][idx])
    return total


# ── LLM seat ──────────────────────────────────────────────────────────────────

_SYSTEM = """You are negotiating a multi-issue business deal. You are the {role}.

THE GAME
- {n} issues are on the table. Each issue has a fixed set of options.
- Your private scoresheet below gives YOUR points for each option (0-100 per
  issue) and how much each issue matters to you (weight, sums to 1). Your total
  score for a package = sum over issues of weight x points(option chosen).
- The other side has its own private scoresheet with OPPOSITE per-option
  direction on every issue but UNKNOWN weights. Trading across issues (conceding
  where you care little to win where you care much) can make you BOTH better off.
- Walking away scores {batna} for you. A deal below that is worse than no deal.
- Offers alternate. On your turn you either OFFER a full package (one option per
  issue), ACCEPT the other side's latest package as-is, or WALK away for good.
- The negotiation ends with no deal (both score {batna}) after {deadline} total
  turns.

RESPONSE FORMAT — reply with ONE JSON object, nothing else:
  {{"action": "offer", "package": {{<issue>: <option>, ...}}}}
  {{"action": "accept"}}
  {{"action": "walk"}}
Every issue must appear in an offer, and every option must be copied exactly
from the listed options."""

_ADVISOR_NOTE = """
YOUR NEGOTIATION ENGINE (SNHP) RECOMMENDS: {rec}
Rationale: {logic}
You may adopt this recommendation exactly, adjust it, or ignore it."""


def _render_turn(view: SeatView) -> str:
    lines = []
    lines.append("YOUR PRIVATE SCORESHEET:")
    for iss in view.issues:
        w = view.weights.get(iss["name"], 0.0)
        opts = ", ".join(f"{o}={round(float(u) * 100)}" for o, u in
                         zip(iss["options"], iss["my_utility"]))
        lines.append(f"- {iss['name']} (weight {w:.2f}): {opts}")
    lines.append("")
    hist = []
    n_off = {"me": 0, "them": 0}
    seq = _interleave(view)
    for who, pkg in seq:
        n_off[who] += 1
        hist.append(f"  {'YOU' if who == 'me' else 'THEM'}: {json.dumps(pkg)}")
    lines.append("OFFER HISTORY (oldest first):" if hist else
                 "OFFER HISTORY: none yet — you open.")
    lines.extend(hist)
    turns_left = view.deadline - view.turn
    lines.append(f"\nTurn {view.turn + 1} of {view.deadline} "
                 f"({turns_left} turns remain, counting this one). Your move.")
    if view.advisor is not None:
        adv = view.advisor
        act = adv.get("action")
        if act == "accept":
            rec_txt = "ACCEPT their latest package"
        elif act == "walk":
            rec_txt = "WALK AWAY — no package on the table beats your walk-away"
        else:
            rec_txt = json.dumps(adv.get("recommended_offer"))
        note = _ADVISOR_NOTE.format(rec=rec_txt, logic=adv.get("trade_logic", ""))
        lines.append(note)
    return "\n".join(lines)


def _interleave(view: SeatView):
    """Reconstruct chronological offer order from the two per-side lists. The
    seller always opens (turn 0), so the seller's i-th offer precedes the
    buyer's i-th offer."""
    me, them = list(view.my_offers), list(view.opp_offers)
    mine_first = view.role == "seller"
    a, b = (me, them) if mine_first else (them, me)
    ta, tb = ("me", "them") if mine_first else ("them", "me")
    seq = []
    for i in range(max(len(a), len(b))):
        if i < len(a):
            seq.append((ta, a[i]))
        if i < len(b):
            seq.append((tb, b[i]))
    return seq



# ── shared transport retry: THE integrity rule for paid API calls ──────────
# Patient on transient errors (rate limit, overload, connection): a
# multi-hour run must survive a brief API incident. Fail-FAST on permanent
# ones (bad request, auth, credits, config): retrying can't fix them, and we
# NEVER fabricate a model's play. Used by the gauntlet seats AND vend's LLM
# arm — one implementation, one rule.
_TRANSIENT_NAME_HINTS = ("Timeout", "Connect", "Transport", "Network",
                         "Broken", "Reset", "JSONDecode")


def _status_of(e: Exception):
    sc = getattr(e, "status_code", None)
    if sc is None:
        sc = getattr(getattr(e, "response", None), "status_code", None)
    return sc


def transport_retry(fn, what: str, retries: int = 8):
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            sc = _status_of(e)
            if sc is not None:
                retryable = sc in (408, 409, 429) or sc >= 500
            else:
                name = type(e).__name__
                retryable = any(h in name for h in _TRANSIENT_NAME_HINTS)
            if not retryable or attempt == retries:
                raise RuntimeError(
                    f"transport failure for {what} after "
                    f"{attempt + 1} attempts: {e}") from e
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise AssertionError("unreachable")


class LLMSeat:
    """A frontier model in the seat. provider: "anthropic" | "openai-compat" |
    "scripted-naive" (offline testing — delegates to NaiveSeat). The advised
    condition is driven by run_match (it fills view.advisor); the seat just
    renders whatever it is given."""

    def __init__(self, provider: str, model: str, *, base_url: str | None = None,
                 api_key_env: str | None = None, temperature: float | None = None,
                 max_retries: int = 2, transport_retries: int = 8,
                 thinking_disabled: bool = True):
        # temperature defaults to None (provider default): newer Anthropic
        # models reject the param outright ("deprecated for this model")
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.max_retries = max_retries          # format (unparseable-reply) retries
        self.transport_retries = transport_retries
        # anthropic only: send thinking={"type":"disabled"} (see _complete for
        # why — default adaptive thinking on Sonnet 5+ silently burns the
        # max_tokens budget). Set False only for a model that requires thinking.
        self.thinking_disabled = thinking_disabled
        self.name = model
        self.format_failures = 0
        self._naive = NaiveSeat()
        self._client = None  # lazy, reused across calls (connection pooling)

    # -- transport ------------------------------------------------------------
    def _complete(self, system: str, user: str) -> str:
        if self.provider == "scripted-naive":
            raise RuntimeError("scripted-naive short-circuits in act()")
        if self.provider == "anthropic":
            if self._client is None:
                import anthropic
                self._client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
            kwargs = {} if self.temperature is None else {"temperature": self.temperature}
            # Disable adaptive thinking. On Sonnet 5+ (and Opus 4.8) thinking is
            # ON by default when the field is omitted, and max_tokens caps
            # thinking+response TOGETHER — so a 500-token cap gets spent on
            # billed thinking ($15/M on Sonnet) and truncates the JSON, forcing
            # unparseable-reply retries (each a fresh billed generation). This
            # seat only needs a one-line JSON offer; thinking is pure cost here.
            # Accepted on Sonnet 5 / Haiku 4.5 / Opus 4.8; Fable 5 would 400
            # (it is always-on) — not a model we seat.
            if self.thinking_disabled:
                kwargs["thinking"] = {"type": "disabled"}
            resp = self._client.messages.create(
                model=self.model, max_tokens=500, system=system,
                messages=[{"role": "user", "content": user}], **kwargs)
            return "".join(b.text for b in resp.content if b.type == "text")
        if self.provider == "openai-compat":
            import httpx
            if self._client is None:
                self._client = httpx.Client(timeout=120.0)
            key = os.environ.get(self.api_key_env or "OPENAI_API_KEY", "")
            url = (self.base_url or "https://api.openai.com/v1") + "/chat/completions"
            body = {"model": self.model,
                    "messages": [{"role": "system", "content": system},
                                 {"role": "user", "content": user}]}
            if self.temperature is not None:
                body["temperature"] = self.temperature
            r = self._client.post(url, headers={"Authorization": f"Bearer {key}"},
                                  json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        raise ValueError(f"unknown provider {self.provider!r}")

    def _complete_with_retry(self, system: str, user: str,
                             retries: int | None = None) -> str:
        return transport_retry(lambda: self._complete(system, user),
                               self.model,
                               self.transport_retries if retries is None else retries)

    # -- parsing --------------------------------------------------------------
    @staticmethod
    def _parse(text: str, view: SeatView) -> Optional[Action]:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        return action_from_obj(obj, view)

    # -- policy ---------------------------------------------------------------
    def act(self, view: SeatView) -> Action:
        if self.provider == "scripted-naive":
            return self._naive.act(view)
        system = _SYSTEM.format(role=view.role, n=len(view.issues),
                                batna=round(BATNA * 100), deadline=view.deadline)
        user = _render_turn(view)
        for attempt in range(self.max_retries + 1):
            # transport failures abort inside the wrapper (patient backoff on
            # transient errors first); this loop only retries unparseable output
            text = self._complete_with_retry(system, user)
            action = self._parse(text, view)
            if action is not None:
                if view.advisor is not None:
                    adv_act = view.advisor.get("action")
                    rec = view.advisor.get("recommended_offer")
                    # credit only moves matching the ADVISED action (an offer of
                    # the rec package while advised to ACCEPT is not following)
                    action.meta["followed_advice"] = bool(
                        (adv_act == "accept" and action.kind == "accept")
                        or (adv_act == "walk" and action.kind == "walk")
                        or (adv_act == "counter" and rec is not None
                            and action.kind == "offer" and action.package == rec))
                return action
            user = user + ("\n\nYour previous reply was not valid. Reply with ONE "
                           "valid JSON object exactly as specified, options copied "
                           "verbatim from the lists.")
        # persistent FORMAT failure (transport fine, output unparseable): safest
        # legal fallback — repeat my last offer, else the naive baseline's move.
        # Counted per turn and reported on the leaderboard row.
        self.format_failures += 1
        if view.my_offers:
            return Action("offer", dict(view.my_offers[-1]), meta={"fallback": True})
        return self._naive.act(view)


# ── community bots: bring-your-own-endpoint ──────────────────────────────────

PROTOCOL = "snhp-gauntlet/1"


def view_payload(view: SeatView, match_id: str) -> dict:
    """The wire format a community bot receives each turn — the SeatView,
    verbatim JSON. Documented at /submit.html; changing it is a protocol bump."""
    return {
        "protocol": PROTOCOL,
        "match_id": match_id,
        "role": view.role,
        "turn": view.turn,
        "deadline": view.deadline,
        "batna": BATNA,
        "issues": [{"name": i["name"], "options": list(i["options"]),
                    "my_utility": list(i["my_utility"]),
                    "their_utility": list(i["their_utility"])} for i in view.issues],
        "weights": dict(view.weights),
        "your_offers": list(view.my_offers),
        "their_offers": list(view.opp_offers),
    }


class HTTPSeat:
    """A community bot behind one HTTP endpoint. We POST the match view each
    turn; the bot returns {"action": "offer"|"accept"|"walk", "package": {...}}.
    Same integrity rules as LLM seats: invalid replies are counted and fall
    back (visible on the row); a dead endpoint ABORTS the run — a leaderboard
    row is the bot or nothing."""

    def __init__(self, endpoint: str, name: str = "community-bot", *,
                 timeout: float = 30.0, max_retries: int = 1):
        self.endpoint = endpoint
        self.name = name
        self.timeout = timeout
        self.max_retries = max_retries
        self.format_failures = 0
        self._naive = NaiveSeat()
        self._client = None
        self._match_id = "m0"

    def new_match(self, match_id: str) -> None:
        self._match_id = match_id

    def act(self, view: SeatView) -> Action:
        import httpx
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        payload = view_payload(view, self._match_id)
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                r = self._client.post(self.endpoint, json=payload)
                r.raise_for_status()
                obj = r.json()
                last_err = None
            except Exception as e:            # transport/HTTP/JSON-decode error
                last_err = e
                time.sleep(1.0 * (attempt + 1))
                continue
            action = action_from_obj(obj, view)
            if action is not None:
                return action
            break                              # decoded but illegal → format failure
        if last_err is not None:
            raise RuntimeError(
                f"endpoint failure for {self.name} ({self.endpoint}) after "
                f"{self.max_retries + 1} attempts: {last_err}")
        self.format_failures += 1
        if view.my_offers:
            return Action("offer", dict(view.my_offers[-1]), meta={"fallback": True})
        return self._naive.act(view)
