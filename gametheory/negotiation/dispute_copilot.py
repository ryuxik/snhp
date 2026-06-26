"""
Dispute co-pilot — the operator-console backend.

Turns a free-text dispute into a structured one, and coaches each round
of a REAL negotiation against a REAL platform: SNHP's negotiation core
(`buy_next_offer`) recommends the next dollar demand, and an LLM drafts
the message the consumer should send.

Unlike `dispute_sim` (which simulates BOTH sides), this module assumes a
real counterparty — the operator relays the platform's actual replies
back in via `parse_platform_reply`. It is the instrument for roadmap
Phase 1: every session produces a real
(dispute, recommendation, action, platform-reply, outcome) record.

LLM calls route through Claude — `claude-haiku-4-5` by default (cheap),
overridable per call and via SNHP_CONSOLE_MODEL. Requires
ANTHROPIC_API_KEY (loaded from the repo-root .env).
"""
from __future__ import annotations

import json
import os

import anthropic
from dotenv import load_dotenv

from gametheory.negotiation.buy import buy_next_offer
# Bare snhp/ import — resolves because the buy import above puts snhp on sys.path.
from dispute_economics import (
    estimate_walk_cost, walk_cost_breakdown, chargeback_cost_to_platform)

# A platform is "stonewalling" once its last offer improved by less than this
# fraction of the gap that remained to the fair claim — i.e. it has effectively
# stopped conceding. That is when the chargeback BATNA gets deployed.
_STONEWALL_IMPROVEMENT_FRAC = 0.15

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# override=True: the environment may carry an empty ANTHROPIC_API_KEY that
# would otherwise shadow the real key in .env.
load_dotenv(os.path.join(_ROOT, ".env"), override=True)

_DEFAULT_MODEL = os.environ.get("SNHP_CONSOLE_MODEL", "claude-haiku-4-5")
_client: anthropic.Anthropic | None = None


# ─── LLM wrapper (provider-swappable — body is the only Claude-specific code) ──


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise RuntimeError("ANTHROPIC_API_KEY not set (expected in repo-root .env)")
        _client = anthropic.Anthropic()
    return _client


def call_llm(prompt: str, *, model: str | None = None, system: str | None = None,
             max_tokens: int = 600, temperature: float = 0.2) -> str:
    """One LLM call, returns the text. The only provider-specific code."""
    kwargs: dict = {
        "model": model or _DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    resp = _get_client().messages.create(**kwargs)
    for block in resp.content:
        if hasattr(block, "text"):
            return block.text.strip()
    return ""


def _call_llm_json(prompt: str, **kw) -> dict:
    raw = call_llm(prompt, **kw).replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Fallback: slice the outermost braces out of a prose-wrapped reply.
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError(f"LLM did not return JSON: {raw[:200]}")


# ─── Intake: free text → structured dispute ─────────────────────────────────


_EXTRACT_PROMPT = """You are SNHP's dispute intake parser. A consumer is
describing a refund dispute — a delivery order, an online purchase, or a
billing problem. Extract a structured summary.

Consumer's description:
<description>
{text}
</description>

Return ONLY a JSON object:
{{
  "platform": "the company/app involved, or unknown",
  "transaction_value": <number: total the consumer paid, USD; null if unclear>,
  "issue_summary": "one sentence on what went wrong",
  "issue_category": "one of: missing_items, never_arrived, wrong_order, quality, late, overcharge, other",
  "severity": "one of: minor, major, critical",
  "disputed_value": <number: your best estimate of the fair USD value of the harm — what the consumer is genuinely owed>,
  "platform_offer": <number: what the platform has already offered, USD; null if nothing offered yet>,
  "platform_offer_form": "one of: cash, credit, null",
  "confidence": <number 0-1>
}}
Extract only what is stated or clearly implied. Do not invent figures."""


def extract_dispute(text: str) -> dict:
    """Free-text dispute description → structured dispute."""
    return _call_llm_json(_EXTRACT_PROMPT.format(text=text), max_tokens=500)


_PARSE_REPLY_PROMPT = """A consumer is negotiating a refund dispute. The
platform's support just sent the reply below. Extract what the platform
is now offering.

Platform's reply:
<reply>
{text}
</reply>

Return ONLY a JSON object:
{{
  "offer_amount": <number: the USD amount the platform is now offering; null if no concrete offer>,
  "offer_form": "one of: cash, credit, null",
  "is_final": <boolean: does the platform present this as final / refuse to move>,
  "tone": "one of: flat_refusal, reluctant, cooperative",
  "gist": "one sentence on what they said"
}}"""


def parse_platform_reply(text: str) -> dict:
    """A pasted platform support reply → their latest offer + posture."""
    return _call_llm_json(_PARSE_REPLY_PROMPT.format(text=text), max_tokens=300)


# ─── Drafting ───────────────────────────────────────────────────────────────


_DRAFT_SYSTEM = (
    "You draft short, firm, polite messages for a consumer negotiating a "
    "refund dispute with a platform's support. Honest and factual — never "
    "invent facts or inflate the claim. The leverage is that the platform "
    "can afford more than it offered, not exaggeration. When a chargeback is "
    "mentioned, frame it as the consumer's factual fallback and a worse "
    "outcome for both sides — collaborative, never a threat. 2-4 sentences."
)

_DRAFT_PROMPT = """The consumer's dispute:
  Platform: {platform}
  Order total: {order_total}
  What went wrong: {issue}
  Fair value of the harm (what the consumer is owed): ${disputed:.2f}
  Share of the order affected (use this exact phrasing if you mention it): {proportion}
{platform_msg}

This round, SNHP's recommendation: {action}
{batna}
Draft the message the consumer should send next. Rules:
- State only true facts. The dollar figures above are the ONLY amounts you
  may use — never invent, recompute, or estimate a number, and never compute
  your own percentage or fraction of the order.
- Firm and specific: state the requested dollar amount clearly.
- Polite, no threats, no exaggeration of the harm.
- 2-4 sentences. Return ONLY the message text, no preamble."""

_BATNA_BLOCK = """
The platform is holding below the fair value. Include — factually and
collaboratively, NOT as a threat — that the consumer's realistic alternative
is a card chargeback for the undelivered ${disputed:.2f}. A chargeback costs
{platform} the refund PLUS a non-refundable bank dispute fee (and dispute-ratio
risk) — more than simply granting ${disputed:.2f} now. Do NOT state a precise
total dollar figure for the chargeback; refer to "the refund plus a
non-refundable bank fee". Make clear the consumer would prefer to resolve it
directly.
"""


def _proportion_text(disputed: float, transaction_value: float | None) -> str:
    """A ready-made, accurate phrase for the share of the order affected, so
    the drafter never has to (mis)compute its own fraction."""
    if not transaction_value or transaction_value <= 0:
        return "not specified"
    frac = disputed / transaction_value
    pct = round(frac * 100)
    if frac >= 0.66:
        qual = "about two-thirds"
    elif frac >= 0.5:
        qual = "more than half"
    elif frac >= 0.33:
        qual = "about a third"
    elif frac >= 0.25:
        qual = "about a quarter"
    else:
        qual = "a portion"
    return f"${disputed:.0f} of the ${transaction_value:.0f} order ({pct}% — {qual})"


def draft_message(*, dispute: dict, demand: float, accept: bool,
                  standing_offer: float | None, platform_last_message: str | None,
                  deploy_batna: bool = False, chargeback_total: float | None = None,
                  model: str | None = None) -> str:
    platform = dispute.get("platform", "the platform")
    disputed = float(dispute.get("disputed_value") or 0.0)
    if accept and standing_offer is not None:
        action = (f"Accept the platform's offer of ${standing_offer:.2f} — "
                  f"it is the best reachable outcome.")
    else:
        action = f"Request ${demand:.2f}, and briefly justify why it is owed."
    tv = dispute.get("transaction_value")
    batna = ""
    if deploy_batna and not accept and chargeback_total is not None:
        batna = _BATNA_BLOCK.format(disputed=disputed, platform=platform,
                                    chargeback_total=chargeback_total)
    prompt = _DRAFT_PROMPT.format(
        platform=platform,
        order_total=f"${float(tv):.2f}" if tv else "not specified",
        issue=dispute.get("issue_summary", ""),
        disputed=disputed,
        proportion=_proportion_text(disputed, float(tv) if tv else None),
        platform_msg=(f"  The platform's last message: \"{platform_last_message}\""
                      if platform_last_message
                      else "  No reply yet — this is the opening message."),
        action=action, batna=batna)
    return call_llm(prompt, system=_DRAFT_SYSTEM, max_tokens=300,
                    temperature=0.4, model=model)


# ─── One coaching round ─────────────────────────────────────────────────────


def coach_round(*, dispute: dict, customer_floor: float,
                platform_offers: list[float], customer_demands: list[float],
                platform_last_message: str | None = None,
                deadline_rounds: int = 10) -> dict:
    """One round of coaching against a REAL platform: recommend the next
    dollar demand (real `buy_next_offer` core) and draft the message.

    `platform_offers` / `customer_demands` are the dollar histories so far.
    """
    disputed = float(dispute.get("disputed_value") or 0.0)
    severity = dispute.get("severity", "major")
    walk = estimate_walk_cost(disputed, severity)
    floor = float(customer_floor)
    span = max(0.5, walk - floor)

    def u_c(s: float) -> float:
        return max(0.0, min(1.0, (s - floor) / span))

    seller_hist = [u_c(o) for o in platform_offers]
    my_hist = [u_c(d) for d in customer_demands]
    adv = buy_next_offer(
        my_reservation=0.0, seller_offer_history=seller_hist,
        my_offer_history=my_hist, deadline_rounds=deadline_rounds, pareto_knob=0.9)
    target_util = float(adv["recommended_offer"])
    # Honest cap: never demand more than the fair value of the harm. The core's
    # aspiration opens high (correct for B2B anchoring) — but in a refund
    # dispute the legitimate claim IS the harm. Early rounds clamp to the full
    # disputed value; the descent only bites once the core drops below it.
    recommended_demand = round(min(floor + target_util * span, disputed), 2)

    standing = platform_offers[-1] if platform_offers else None
    # Accept once the platform's standing offer meets what we'd ask for. Since
    # recommended_demand descends over rounds, this also handles late-game
    # "take the best available".
    accept = standing is not None and standing + 0.50 >= recommended_demand

    # The customer's real BATNA: a card chargeback for the undelivered goods.
    # It costs the platform MORE than the honest claim — that gap is the
    # leverage, surfaced once the platform has stopped conceding below it.
    chargeback = chargeback_cost_to_platform(disputed, severity)
    deploy_batna = (not accept and _is_stonewalling(platform_offers, disputed))

    draft = draft_message(
        dispute=dispute, demand=recommended_demand, accept=accept,
        standing_offer=standing, platform_last_message=platform_last_message,
        deploy_batna=deploy_batna, chargeback_total=chargeback["total"])

    return {
        "estimated_walk_cost": walk,
        "walk_cost_breakdown": walk_cost_breakdown(disputed, severity),
        "chargeback_cost": chargeback,
        "batna_deployed": deploy_batna,
        "recommended_demand": recommended_demand,
        "accept_standing_offer": accept,
        "standing_offer": standing,
        "round": len(seller_hist) + len(my_hist) + 1,
        "rationale": adv.get("rationale", ""),
        "drafted_message": draft,
    }


def _is_stonewalling(platform_offers: list[float], disputed: float) -> bool:
    """True once the platform's latest concession is below
    `_STONEWALL_IMPROVEMENT_FRAC` of the gap that remained to the fair claim
    (it has effectively stopped moving), while still short of that claim."""
    if len(platform_offers) < 2:
        return False
    prev, last = platform_offers[-2], platform_offers[-1]
    if last >= disputed - 0.5:
        return False
    gap = max(0.5, disputed - prev)
    return (last - prev) / gap < _STONEWALL_IMPROVEMENT_FRAC
