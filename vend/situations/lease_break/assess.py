"""Lease break — deterministic core.

WHY THIS IS THE HARDER SITUATION
A renewal is one number and low stakes. A lease break is fear, real
exposure, and several exits most people don't know exist — a clause in
their own lease, assignment, sublet, a negotiated surrender, a statutory
right, or walking and taking the consequences. Which is cheapest is not
obvious, and the ranking inverts with the local market.

THE ARITHMETIC, STATED PLAINLY
What a landlord actually loses when you leave is the time the unit sits
empty plus the cost of filling it. That is the number a rational
settlement lands near, and it is usually far below the rent remaining on
the lease. So the recommended offer is anchored on the landlord's
expected loss rather than on your remaining balance — which is the whole
mechanism this company is built on, pointed at a consumer problem.

The honest counterpart: whether you can hold them to that loss depends
on your state's mitigation rules, which we do not assert. So the
exposure list always carries both numbers — what it costs if the rules
work the way most people assume, and what it costs if they don't.

NO LLM IN ANY JUDGMENT PATH. Same inputs, same verdict, every time.
"""

from __future__ import annotations

from vend.situations.lease_break import evidence, rules
from vend.situations.schema import (
    BOOL, CHOICE, COUNT, METRO, MONEY, MONTHS,
    Field, Outcome, Route, Rule, Situation,
)

# Same table the renewal side uses; a closed vocabulary beats asking a
# model to recall which metro a borough belongs to.
_METRO_KEYS = tuple(sorted(evidence._metros.METROS))

FIELDS = (
    Field(
        key="metro",
        label="Where the place is",
        kind=METRO,
        required=True,
        vocabulary=_METRO_KEYS,
        help="Decides how fast the unit re-rents, which decides your exposure.",
    ),
    Field(
        key="monthly_rent",
        label="Your monthly rent",
        kind=MONEY,
        required=True,
        unit="per month",
    ),
    Field(
        key="months_remaining",
        label="Months left on the lease",
        kind=MONTHS,
        required=True,
        unit="months",
        # Spans the short-tail case (ride it out) through most of a
        # fresh 12-month term, so the sweep sees the verdict change.
        sweep=(1.0, 3.0, 6.0, 11.0),
    ),
    Field(
        key="has_termination_clause",
        label="Does your lease have an early-termination clause?",
        kind=BOOL,
        help=(
            "Look for a section on early termination, lease break, or buy-out. "
            "It usually names a fee and a notice period. If you're not sure, "
            "say no — we'll plan around not having one."
        ),
    ),
    Field(
        key="termination_fee_months",
        label="What the clause charges",
        kind=MONTHS,
        unit="months' rent",
        help="Most clauses state a figure in months of rent, plus notice.",
        sweep=(1.0, 2.0, 3.0),
    ),
    Field(
        key="replacement_tenant_ready",
        label="Do you have someone ready to take over?",
        kind=BOOL,
        help=(
            "Someone who would actually sign — a friend, a colleague, a person "
            "from a listing. This changes the plan more than almost anything else."
        ),
    ),
    Field(
        key="lease_allows_transfer",
        label="Does the lease allow you to assign or sublet?",
        kind=CHOICE,
        options=(
            ("yes", "Yes, with the landlord's consent"),
            ("no", "No, it's prohibited"),
            ("unknown", "I don't know"),
        ),
        default="unknown",
    ),
    Field(
        key="move_out_reason",
        label="Why are you leaving?",
        kind=CHOICE,
        options=(
            ("job", "A job or a move"),
            ("cost", "It's too expensive"),
            ("military", "Military orders"),
            ("safety", "Safety — domestic violence or a protective order"),
            ("habitability", "The place isn't liveable"),
            ("other", "Something else"),
        ),
        default="other",
        help="Some reasons carry rights created by statute rather than by your lease.",
    ),
    Field(
        key="security_deposit",
        label="Your security deposit",
        kind=MONEY,
        unit="total",
        help="Usually the first thing applied against what you owe.",
        # Swept so it can be scored rather than sitting inert. It changes
        # what you're told you're exposed to but not which route wins, so
        # it scores low and is shown for correction rather than asked —
        # which is the right treatment, arrived at rather than assumed.
        sweep=(0, 2000, 5000),
    ),
    # DELIBERATE CONTROL. A plausible-sounding field that never changes
    # the answer. The sensitivity engine sweeps it, scores it at zero,
    # and it is never put on screen — which is the visible proof that
    # questions are earned rather than authored. Do not delete it: the
    # test suite asserts it is never asked.
    Field(
        key="credit_score",
        label="Your credit score",
        kind=COUNT,
        help="Never asked — it does not change any of this.",
        sweep=(560, 700, 810),
    ),
)


# Every one of these is a sentence that would send somebody out of a
# tenancy holding a false premise. Written for this situation
# specifically; the framework only enforces them.
MUST_NOT_ASSERT = (
    Rule(r"\byou (can|may) (legally )?(break|terminate|end) (your|the) lease\b",
         "whether a tenancy can be ended early depends on the lease and the state"),
    Rule(r"\byou (are entitled to|have (a|the) right to)\b",
         "no legal right may be asserted on somebody's behalf"),
    Rule(r"\byou qualify( for)?\b|\byou are eligible\b",
         "statutory routes have documentation tests we cannot apply"),
    Rule(r"\byour landlord (must|has to|is required to)\b",
         "duties vary by state and by lease; we say how to check, not what applies"),
    Rule(r"\byou (owe nothing|will not owe|won'?t owe)\b",
         "we cannot clear somebody of a balance"),
    # These match the ADVISORY form only. An earlier, blunter version
    # matched any mention of withholding and fired on our own warning
    # against it — which is the guard working, and the reason the rules
    # are written against constructions rather than keywords.
    Rule(r"\b(you (can|could|should|may|might)|consider|try|feel free to)\s+"
         r"(stop|cease|quit)\s+paying\b",
         "never advise withholding rent — it is the main way this goes badly"),
    Rule(r"\b(you (can|could|should|may|might)|consider|try|feel free to)\s+withhold",
         "never advise withholding rent"),
    Rule(r"(?m)^\s*(stop paying|withhold)\s+(the\s+|your\s+)?rent\b",
         "never advise withholding rent, including as an imperative"),
    Rule(r"\byou (don'?t|do not) (have to |need to )?(pay|owe)\b",
         "we cannot tell somebody a payment isn't owed"),
    Rule(r"\bjust (walk|leave|move) out\b",
         "walking without a plan is the most expensive route, never the advice"),
    Rule(r"\b(this|that) is (illegal|unlawful|unenforceable)\b",
         "we do not rule on enforceability"),
    Rule(r"\bwe guarantee\b|\byou will (get|win|be released)\b",
         "no outcome may be promised"),
    Rule(r"\bthis is legal advice\b",
         "information, not legal advice"),
)


_VERDICT_LABEL = {
    "strong": "you have a real move here",
    "moderate": "worth negotiating",
    "weak": "nothing to negotiate",
}


def _money(x) -> int:
    return int(round(x))


def assess(values: dict) -> Outcome:
    rent = float(values["monthly_rent"])
    months_left = float(values["months_remaining"])
    if rent <= 0 or months_left <= 0:
        raise ValueError("Rent and months remaining must both be positive.")

    metro_key = values["metro"]
    reason = values.get("move_out_reason") or "other"
    has_clause = values.get("has_termination_clause")
    fee_months = values.get("termination_fee_months")
    replacement = values.get("replacement_tenant_ready")
    transfer = values.get("lease_allows_transfer") or "unknown"
    deposit = values.get("security_deposit")

    mkt = evidence.market(metro_key)
    legal = rules.block(metro_key, reason)

    # ── The two numbers everything else is measured against ──────────
    remaining_balance = rent * months_left
    # What one unscheduled turn actually costs the landlord, pinned to
    # the surveyed 1-2 months envelope. A rational settlement lands near
    # here, not near the remaining balance.
    turn = evidence.turn_cost(metro_key, rent, months_left)
    vacancy = turn["vacancy_months"]
    relet_cost = turn["leasing_cost_usd"]
    landlord_loss = turn["total_usd"]

    routes: list[Route] = []

    # 1. Statutory — checked first because it is not a negotiation.
    statutory = legal.get("statutory_route")
    if statutory:
        routes.append(Route(
            key="statutory",
            label=f"Check the statutory route first — {statutory['label'].lower()}",
            detail=(
                "Before you offer anyone money, find out what your circumstances "
                "carry in law. Take the documents you have to a legal-services "
                "organisation or your state's landlord-tenant office and ask them "
                "directly."
            ),
            why=statutory["note"],
            ease="easiest",
            est_cost_usd=None,
            available=True,
        ))

    # 2. The clause in their own lease.
    #
    # We used to fill in a "typical" 2 months when somebody had a clause
    # but didn't know its terms. That number came from lease templates,
    # not from a survey, and there is no dataset of residential
    # early-termination terms to source it from — so the fix is deletion,
    # not sourcing. A clause states its own figure; the honest move is to
    # send them to read it rather than to anchor them on a made-up one.
    # This is the same failure as the turn cost, caught before shipping
    # rather than after.
    why_clause = (
        "A clause you already agreed to is the one route that does not depend "
        "on the landlord saying yes, on your state's rules, or on finding "
        "anybody. It is certainty, which is worth something even when it is "
        "not the cheapest line on this page."
    )
    if has_clause is True and fee_months:
        clause_cost = _money(float(fee_months) * rent)
        routes.append(Route(
            key="clause",
            label="Use the early-termination clause in your lease",
            detail=(
                f"Give the notice your clause requires and pay what it states — "
                f"${clause_cost:,} at {float(fee_months):g} months' rent."
            ),
            why=why_clause,
            ease="easiest",
            est_cost_usd=clause_cost,
            est_value_usd=max(0, _money(remaining_balance - clause_cost)),
        ))
    elif has_clause is True:
        routes.append(Route(
            key="clause",
            label="Use the early-termination clause in your lease",
            detail=(
                "Go and read what it actually charges, and what notice it wants. "
                "We are not going to guess at the figure: clauses vary widely, "
                "there is no survey of them to draw on, and a number we invented "
                "would be the thing you anchored your whole decision to. Yours "
                "states its own."
            ),
            why=why_clause,
            ease="easiest",
            est_cost_usd=None,   # unknown, and left unknown on purpose
        ))
    else:
        routes.append(Route(
            key="clause",
            label="Use the early-termination clause in your lease",
            detail="",
            why="",
            available=False,
            unavailable_because=(
                "You told us there isn't one — worth a second look at the lease "
                "before you rule it out, since it is usually the simplest exit."
                if has_clause is False else
                "We don't know yet whether your lease has one."
            ),
        ))

    # 3. Assignment — the route that actually ends your liability.
    can_transfer = transfer == "yes"
    transfer_cost = _money(relet_cost)
    if can_transfer or replacement is True:
        routes.append(Route(
            key="assign",
            label="Hand the lease to someone else (assignment)",
            detail=(
                "Ask the landlord in writing to approve an assignment to a named "
                "replacement. An assignment transfers the lease — that is the "
                "difference that matters, because a sublet leaves you on the hook "
                "and an assignment does not."
                + ("" if replacement is True else
                   " You'd need to find the replacement first; the landlord "
                   "usually gets to approve them.")
            ),
            why=(
                "This is the cheapest real exit when it works, because it removes "
                "the landlord's loss entirely rather than paying them for it. "
                "Somebody else is paying the rent from the day you leave, so "
                "there is nothing to argue about."
                + (f" It also matters more than usual here: {mkt['relet_speed']} "
                   "re-letting means the landlord's alternative is worse."
                   if mkt["relet_speed"] == "slow" else "")
            ),
            ease="moderate" if replacement is True else "hardest",
            est_cost_usd=transfer_cost,
            est_value_usd=max(0, _money(remaining_balance - transfer_cost)),
            ask_phrase="approving an assignment of the lease to a replacement tenant",
        ))
    else:
        routes.append(Route(
            key="assign",
            label="Hand the lease to someone else (assignment)",
            detail="",
            why="",
            available=False,
            unavailable_because=(
                "Your lease prohibits it." if transfer == "no"
                else "We don't know yet whether your lease permits it."
            ),
        ))

    # 4. Negotiated surrender — anchored on the landlord's real loss.
    surrender_cost = _money(min(remaining_balance, landlord_loss))
    routes.append(Route(
        key="surrender",
        label="Offer a buy-out and get a signed release",
        detail=(
            f"Offer around ${surrender_cost:,} — about "
            f"{surrender_cost / rent:.1f} months of your rent, which is the "
            f"empty time plus the cost of filling the unit — in exchange for a "
            f"signed agreement ending the tenancy on a fixed date with nothing "
            f"further owed."
        ),
        why=(
            f"That figure is not arbitrary: it is close to what an empty unit "
            f"actually costs them, which is the number they are really weighing "
            f"against the hassle of chasing you. {mkt['relet_note']}"
        ),
        ease="moderate",
        est_cost_usd=surrender_cost,
        est_value_usd=max(0, _money(remaining_balance - surrender_cost)),
        ask_phrase=(
            f"a one-time payment of ${surrender_cost:,} to end the lease on an "
            "agreed date, with a signed release"
        ),
    ))

    # 5. Leaving without an agreement — always shown, never recommended.
    routes.append(Route(
        key="walk",
        label="Leave without an agreement and see what they claim",
        detail=(
            f"Your exposure runs from about ${_money(landlord_loss):,} to the full "
            f"${_money(remaining_balance):,} remaining, depending on rules we can't "
            "check for you and on how quickly the unit fills."
        ),
        why=(
            "This is the route with the widest range of outcomes and the only one "
            "that can end in collections. It is listed so you can see what the "
            "other routes are buying you, not because it is a plan."
        ),
        ease="hardest",
        est_cost_usd=_money(remaining_balance),
        available=True,
    ))

    priced = [r for r in routes if r.available and r.est_cost_usd is not None
              and r.key != "walk"]
    best = min(priced, key=lambda r: r.est_cost_usd) if priced else None
    best_cost = best.est_cost_usd if best else _money(remaining_balance)

    # Show routes cheapest-first among the ones that are actually open,
    # with the statutory check pinned to the top when it applies and the
    # walk-away pinned to the bottom.
    def _order(r: Route):
        if r.key == "statutory":
            return (0, 0)
        # A clause whose terms we don't know is a "go find out" route,
        # not a costed one. Ranking it by its (absent) price buried it
        # below the buy-out, so the recommended action never changed and
        # the framework stopped asking whether a clause existed at all —
        # which is one of the two things that most changes the plan.
        if r.key == "clause" and r.available and r.est_cost_usd is None:
            return (0, 1)
        if r.key == "walk":
            return (3, 0)
        if not r.available:
            return (2, 0)
        return (1, r.est_cost_usd if r.est_cost_usd is not None else 10**9)

    routes.sort(key=_order)

    verdict, headline = _verdict(
        months_left=months_left,
        rent=rent,
        remaining_balance=remaining_balance,
        best=best,
        best_cost=best_cost,
        has_clause=has_clause,
        replacement=replacement,
        mkt=mkt,
        statutory=bool(statutory),
    )

    state = legal.get("state_mitigation")

    exposure = [
        f"Rent left on the lease if nothing changes: ${_money(remaining_balance):,} "
        f"over {months_left:g} months.",
        # Months alongside every dollar: months is the unit both sides are
        # actually measured in, and the only one that can be checked
        # against the surveyed range.
        f"What leaving costs your landlord, in the unit the research uses: "
        f"about {landlord_loss / rent:.1f} months of your rent. The surveyed "
        f"range for a turnover is one to two months, so that is where this "
        f"sits.",
        f"If your state requires the landlord to re-let and they do it at the "
        f"pace this market suggests, the realistic number is nearer "
        f"${_money(landlord_loss):,}. If it doesn't, or they don't, it is the "
        f"full balance. We can't tell you which — that is the single most "
        f"important thing to go and check.",
    ]
    if deposit:
        exposure.append(
            f"Your ${_money(deposit):,} deposit will normally be applied against "
            "whatever is owed before anything is refunded."
        )
    if state:
        # Verified statute, stated as what the law says rather than as
        # what it does for this person. Same framing the renewal module
        # uses for rent-board orders.
        exposure.append(
            f"{state['statute']} — {state['title']}. {state['the_part_people_miss']} "
            f"{state['burden_of_proof']} {state['cannot_be_waived']} "
            f"{state['still_not_a_conclusion']}"
        )
    exposure.append(evidence.move_cost_note(rent))
    exposure.append(
        "An unresolved balance can be sent to collections and show up when you "
        "apply for your next place. That is the real cost of the cheapest-looking "
        "route."
    )

    caveats = list(legal["caveats"])
    # The other side of the proof advice. Stated as the mechanism —
    # unravelling is standard economics, not something our simulation
    # discovered — so no figure from the study reaches a reader.
    caveats.append(
        "Being able to show a landlord something they can check is worth "
        "more than saying it, and that is worth more to you now than it "
        "will be later. Proof works because most people don't bring any, so "
        "bringing some sets you apart. If it ever became the norm, showing "
        "nothing would start to read as having nothing, and renters as a "
        "group would be worse off than when nobody could prove anything. "
        "The edge is real and it is temporary."
    )
    # The finding that reframes the whole page. Built from scratch, the
    # two sides of this arithmetic come out the same size — the "they
    # risk five to gain two" gap the advice genre runs on is not there.
    # Which is not the same as saying you are evenly matched.
    # The comparison, computed from THIS rent rather than asserted.
    # "Both sides come out about the same" is true near a typical rent and
    # false at both ends: the sourced move cost is a flat dollar figure, so
    # it is well over a month for somebody paying $900 and a fifth of a
    # month for somebody paying $5,000, while the landlord's side scales
    # with rent. Stating the midpoint as a universal was wrong.
    move_hi_months = evidence.MOVE_COST_HIGH_USD / rent
    landlord_months = landlord_loss / rent
    if move_hi_months >= landlord_months * 0.6:
        comparison = (
            "At your rent those two are close to level, which is already a "
            "long way from the they-risk-far-more-than-you story the advice "
            "genre runs on."
        )
    else:
        comparison = (
            "At your rent the physical move is the smaller of the two — but "
            "it is only the part anyone has measured. What leaving actually "
            "costs you also includes finding somewhere, deposits, time off, "
            "and the disruption, none of which appears in any survey. The "
            "gap is smaller than the they-risk-far-more-than-you story "
            "suggests, and nobody can tell you by how much."
        )
    caveats.append(
        f"Comparing the two sides: leaving costs your landlord about "
        f"{landlord_months:.1f} months of your rent, and the sourced cost of "
        f"a physical move is roughly {evidence.MOVE_COST_LOW_USD / rent:.1f} "
        f"to {move_hi_months:.1f} months' worth to you. {comparison} And "
        f"equal dollars are not equal stakes — the same few thousand is a "
        f"line item against a portfolio for them and a household shock for "
        f"you. You can lose a negotiation where the numbers are symmetric, "
        f"because only one of you can afford to be wrong."
    )
    caveats.append(evidence.BASIS)
    if not mkt.get("metro_known"):
        caveats.append(
            "We don't have market data for your area, so the re-letting estimate "
            "is national. Treat the market framing as weaker than usual."
        )
    if not legal["rules_verified"]:
        caveats.append(legal["status_note"])

    return Outcome(
        verdict=verdict,
        verdict_label=_VERDICT_LABEL[verdict],
        headline=headline,
        routes=routes,
        next_step=_next_step(verdict, routes, bool(statutory), replacement),
        message=_message(verdict, routes, months_left),
        exposure=exposure,
        verify=legal["how_to_verify"],
        caveats=caveats,
        odds=None,
        # Deliberately empty. There is no survey we trust on how often
        # these negotiations succeed, and inventing one to fill the slot
        # would be the exact failure this framework exists to prevent.
        odds_basis="",
        evidence_note=evidence.BASIS,
        metric_usd=float(best_cost),
        context={
            "market": mkt,
            "legal": legal,
            "remaining_balance_usd": _money(remaining_balance),
            "landlord_expected_loss_usd": _money(landlord_loss),
            "best_route": best.key if best else None,
            "publishable_evidence": evidence.PUBLISHABLE,
        },
    )


def _verdict(*, months_left, rent, remaining_balance, best, best_cost,
             has_clause, replacement, mkt, statutory) -> tuple[str, str]:
    """Three-way call. "weak" must be reachable and must mean it."""

    if months_left <= evidence.SHORT_TAIL_MONTHS:
        return ("weak", (
            f"With {months_left:g} months left, there is not much here to "
            f"negotiate — every route costs about the same as simply seeing the "
            f"lease out. Give notice for the end of the term and move on."
        ))

    if statutory:
        return ("strong", (
            "Before anything else: your circumstances may carry a route created "
            "by statute rather than by your lease. That is a different kind of "
            "conversation from a negotiation, and it is worth finding out first."
        ))

    if replacement is True:
        return ("strong", (
            "Having somebody ready to take over is the strongest position in "
            "this situation. It removes the landlord's actual loss instead of "
            "paying them for it, which is why it is usually the cheapest way out."
        ))

    if has_clause is True and best is not None and best.key == "clause":
        return ("weak", (
            f"Your lease already sets the price of leaving, and at roughly "
            f"${best_cost:,} it is at or below what you could realistically "
            f"negotiate to. Use the clause. There is no leverage to find here, "
            f"and looking for it costs you time you don't have."
        ))

    if mkt.get("relet_speed") == "slow" and months_left >= 6:
        return ("moderate", (
            f"This is a soft rental market, which cuts both ways: your landlord "
            f"will not re-let quickly, so their loss is real — but that also "
            f"means they have a strong reason to settle rather than carry an "
            f"empty unit. Anchor on their loss, roughly ${best_cost:,}, not on "
            f"your remaining balance."
        ))

    if mkt.get("relet_speed") == "fast":
        return ("moderate", (
            f"You are in a tight market, which is quietly good news: the unit "
            f"should re-let quickly, so what the landlord actually loses is "
            f"small — around ${best_cost:,} rather than the "
            f"${_money(remaining_balance):,} left on your lease. That gap is "
            f"what you are negotiating over."
        ))

    return ("moderate", (
        f"You have a real position. The number that matters is what an empty "
        f"unit costs your landlord — roughly ${best_cost:,} — not the "
        f"${_money(remaining_balance):,} left on the lease. Open there."
    ))


def _next_step(verdict: str, routes: list[Route], statutory: bool,
               replacement) -> str:
    """The one thing to do now.

    The urgency here is mechanical rather than a base rate we don't have:
    every week you wait is a week less for the unit to be re-let inside
    your term, and the unfilled time is exactly what gets billed to you.
    """
    urgency = (
        "Start this week rather than next — the longer the unit has to be "
        "re-let before your term ends, the smaller the bill. "
    )

    if statutory:
        return (
            "Before you offer anyone money or sign anything: take your "
            "documents to a legal-services organisation or your state's "
            "landlord-tenant office and ask what your circumstances carry. "
            "That answer changes everything below it."
        )

    top = next((r for r in routes if r.available and r.key != "walk"), None)

    if top is not None and top.key == "clause" and top.est_cost_usd is None:
        return (
            "Before anything else, find the early-termination clause in your "
            "lease and read what it charges and what notice it wants. That "
            "figure decides whether there is anything here worth negotiating, "
            "and it is the one number we will not guess at for you."
        )

    if verdict == "weak":
        if top is not None and top.key == "clause":
            return (
                "Read the termination clause in your lease, give exactly the "
                "notice it asks for, and pay what it states. Skip the "
                "negotiating — there is nothing to win here, and the notice "
                "period is the part people miss."
            )
        return (
            "Give written notice for the end of the term, keep paying on time, "
            "and put your energy into the next place instead."
        )

    if replacement is True:
        return urgency + (
            "Put the assignment request in writing today, naming your "
            "replacement and offering to cover the landlord's screening. "
            "Keep paying rent until something is signed."
        )

    return urgency + (
        "Before you send anything, get hold of the one thing that can be "
        "checked — the new lease's start date, a relocation letter, a named "
        "person ready to take the unit. A landlord has no reason to move for "
        "'I might have to leave', because it is free to say and everyone "
        "says it; a date and a name is a different object. Then send the "
        "message below and ask for a signed release rather than a verbal "
        "yes, keeping rent paid on time until you have one."
    )


def _message(verdict: str, routes: list[Route], months_left: float) -> str:
    """A send-ready note. Factual and warm — you may need a reference."""
    if verdict == "weak":
        return ""
    openers = [r for r in routes if r.available and r.ask_phrase]
    if not openers:
        return ""
    primary = openers[0]
    secondary = next((r for r in openers[1:]), None)

    body = (
        "Hi — I need to move out before the end of my lease, and I'd rather "
        "sort this out with you properly than leave you with a problem.\n\n"
        # The bracket is not a placeholder to be polished away. An
        # unbacked "I need to move" is free to say and everyone can say
        # it, so it carries no information and a landlord is right to
        # ignore it. The specific, checkable thing is the whole message.
        "[Put the specific, checkable thing here: the start date on the new "
        "place, the relocation letter, or the name and number of someone "
        "ready to take the unit. Something they can confirm — not "
        "'I might have to move'.]\n\n"
        f"There are about {months_left:g} months left. I'd like to propose "
        f"{primary.ask_phrase}.\n\n"
    )
    if secondary:
        body += (
            f"If that doesn't work for you, I'm also open to {secondary.ask_phrase}.\n\n"
        )
    body += (
        "I'll keep paying rent on time until we've agreed something in writing. "
        "Happy to talk it through whenever suits you."
    )
    return body


SITUATION = Situation(
    key="lease_break",
    name="Getting out of a lease early",
    one_liner="You've signed, you need out, and you don't know what it will cost.",
    fields=FIELDS,
    assess=assess,
    must_not_assert=MUST_NOT_ASSERT,
    triggers=(
        "break my lease", "break the lease", "breaking a lease", "breaking my lease",
        "get out of my lease", "out of my lease", "out of the lease",
        "leave early", "move out early", "moving out early",
        "terminate my lease", "end my lease", "early termination",
        "just signed", "want out", "need out", "need to be out", "have to be out",
        "months left on", "left on my lease", "left on the lease",
        "before the lease", "before my lease", "leave before",
        "sublet", "sublease", "subletting", "assign my lease", "assignment",
        "buy out", "buyout", "relocating", "new job in",
    ),
    intake_hint=(
        "The person has a lease they want out of before the end of the term. "
        "Look for: monthly rent, how many months are left (or the move-out date "
        "and lease end date), the city, whether they have found anyone to take "
        "over, whether the lease mentions early termination or subletting, and "
        "why they are leaving."
    ),
)
