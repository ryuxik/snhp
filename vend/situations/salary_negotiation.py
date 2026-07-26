"""Salary negotiation — the situation module.

What the study behind this actually found, and therefore what this module is
allowed to do:

  * Negotiating beats not negotiating by a lot, and the size of "a lot" is
    governed by **what it costs to replace you**, not by how well you argue.
  * Putting every term on the table in one sitting beats six weeks of email:
    42 days faster, and the share of negotiations that collapse falls from 35%
    to 16%.
  * An offer you can **show** is worth about $2,851. An offer you can only
    **claim** is worth nothing, because claiming is free and so everyone does it.
  * The engine does NOT out-argue a competent negotiator — that never cleared
    2% of salary in any specification. So this module never says it will.
  * An employer will not hand you the menu, because revealing what it would
    equally sign costs it ~$8,738 over two seasons. So the menu is built from
    the outside, from your replacement cost — and is offered as *what to ask
    for*, never as *what they have agreed to*.

The one thing this module must never do is tell you what your employer will
accept. It does not know, it cannot know, and the whole point of the last
finding is that they are paying real money to keep it that way.
"""
from __future__ import annotations

from vend.situations import salary_evidence as _ev
from vend.situations.schema import (BOOL, CHOICE, COUNT, MONEY, Field, Outcome,
                                    Route, Rule, Situation)

_ROLE_FAMILIES = (
    ("frontline", "Frontline / skilled trade"),
    ("professional", "Individual contributor, professional"),
    ("scarce", "Specialist the market is short of"),
    ("revenue", "Revenue-facing"),
    ("leadership", "Manages people"),
)

FIELDS = (
    Field(
        key="salary",
        label="What you're paid now",
        kind=MONEY,
        required=True,
        unit="per year",
    ),
    Field(
        key="role_family",
        label="Closest description of your role",
        kind=CHOICE,
        required=True,
        options=_ROLE_FAMILIES,
        help="This sets what replacing you costs — the number your leverage "
             "actually comes from.",
        # Straddles the range where replacement cost roughly triples, so the
        # sensitivity engine can see the flip rather than sampling around it.
        sweep=("frontline", "professional", "leadership"),
    ),
    Field(
        key="has_outside_offer",
        label="Do you have an offer somewhere else?",
        kind=BOOL,
        required=True,
        # No default. Defaulting this to False would silently file everyone
        # into the weakest cell without ever asking — and it is the field the
        # whole verdict turns on. The linter caught exactly this.
        sweep=(False, True),
    ),
    Field(
        key="offer_is_provable",
        label="Could you show it to them in writing?",
        kind=BOOL,
        default=False,
        help="A written offer you're willing to show is worth roughly $2,851. "
             "One you can only describe is worth nothing — everybody says they "
             "have one, so saying it carries no information.",
        sweep=(False, True),
    ),
    Field(
        key="offer_premium_pct",
        label="How much more does the other offer pay?",
        kind=COUNT,
        unit="percent",
        default=0,
        sweep=(0, 8, 15),
    ),
    Field(
        key="months_in_role",
        label="How long you've been in the role",
        kind=COUNT,
        required=True,
        unit="months",
        sweep=(6, 18, 36),
    ),
    Field(
        key="cycle_open",
        label="Is the comp or promotion cycle still open?",
        kind=BOOL,
        default=True,
        help="Answering early is worth more than answering well. Once the "
             "window shuts, the same conversation is worth less.",
        sweep=(False, True),
    ),
)


MUST_NOT_ASSERT = (
    # THE central rule. Our own measurement says an employer pays ~$8,738 over
    # two seasons to keep its band secret; a tool that claims to know it is
    # claiming the one thing nobody outside the company has.
    Rule(r"(?<!whether )(?<!\bif )\bthey (will|would) (accept|agree to|approve|say yes)\b",
         "we cannot know what your employer will accept — they spend real money "
         "keeping that private"),
    Rule(r"\byour employer'?s? (budget|band|range|ceiling) is\b",
         "the band is the thing they are protecting; we can only estimate what "
         "you are worth to them"),
    Rule(r"\byou (will|are going to) get\b",
         "no outcome may be promised"),
    Rule(r"\byou (are|'re) (worth|underpaid by) \$",
         "we estimate replacement cost, which is not the same as your market rate"),
    # The product claim that failed its own kill, seven times. It does not
    # reappear in the copy.
    Rule(r"\b(out-?negotiat|beat|outperform)\w*\s+(a\s+)?(human|person|professional|negotiator)\b",
         "measured repeatedly and it never cleared the bar; the value is speed "
         "and completeness, not out-arguing anyone"),
    Rule(r"\b(guarantee|guaranteed|certain|definitely)\b",
         "nothing here is certain"),
    # At-will employment is real and this tool is not a lawyer.
    Rule(r"\bthey (can'?t|cannot) (fire|let you go|retaliate)\b",
         "we cannot make employment-law assertions"),
    Rule(r"\byou (can|could|should) threaten\b",
         "never advise a threat — an offer you cannot show is worth nothing, "
         "and a bluff that is called costs you the relationship"),
)


# --------------------------------------------------------------------- helpers
def _replacement_cost(values: dict) -> float:
    fam = values.get("role_family", "professional")
    mult = _ev.REPLACEMENT_COST.get(fam, _ev.REPLACEMENT_COST["professional"])
    return float(values["salary"]) * mult.value


def _leverage(values: dict) -> tuple[float, str]:
    """What asking is worth, and which measured cell it came from."""
    if values.get("has_outside_offer") and values.get("offer_is_provable"):
        fam = values.get("role_family", "professional")
        costly = _ev.REPLACEMENT_COST.get(fam, _ev.REPLACEMENT_COST["professional"]).value >= 0.80
        k = "leverage_offer_and_costly_to_replace" if costly \
            else "leverage_with_provable_offer"
    elif values.get("has_outside_offer"):
        # Claimable but not showable. The measured value of an unprovable
        # claim is zero, so this person is in the no-offer cell.
        k = "leverage_no_offer"
    else:
        k = "leverage_no_offer"
    return _ev.SIM[k].value, k


def assess(values: dict) -> Outcome:
    """Resolved priors -> the fixed output contract. Pure, cheap, deterministic."""
    salary = float(values["salary"])
    replacement = _replacement_cost(values)
    leverage, cell = _leverage(values)
    provable = bool(values.get("has_outside_offer")) and bool(values.get("offer_is_provable"))
    cycle_open = bool(values.get("cycle_open", True))

    # Verdict. Deliberately reachable at `weak` — a situation that can never
    # tell somebody their position is poor is a horoscope, and lint blocks it.
    if provable and replacement >= 0.80 * salary:
        verdict, label = "strong", "You have real leverage and can prove it"
    elif provable or replacement >= 0.80 * salary:
        verdict, label = "moderate", "You have something to work with"
    else:
        verdict, label = "weak", "Your position is thin — ask anyway, but expect little"
    if not cycle_open:
        verdict = "weak" if verdict == "moderate" else verdict

    routes = [
        Route(
            key="one_sitting",
            label="Put every term on the table in one conversation",
            detail="Pay, title, time off, schedule, scope — all of it, once, "
                   "rather than one item per email over six weeks.",
            why="Settling in one sitting rather than six weeks of email was "
                "worth about {:,.0f} days and cut the share of negotiations "
                "that fall apart from {:.0%} to {:.0%} in our simulation."
                .format(_ev.SIM["days_saved"].value,
                        _ev.SIM["collapse_haggling"].value,
                        _ev.SIM["collapse_one_sitting"].value),
            ease="easiest",
            est_value_usd=int(_ev.SIM["menu_over_haggling"].value),
            ask_phrase="I'd rather cover everything in one conversation than "
                       "go back and forth — can we book thirty minutes and "
                       "settle the whole package?",
        ),
        Route(
            key="ask_for_a_menu",
            label="Ask which shapes they could sign, not which number",
            detail="Ask them to come back with two or three packages that "
                   "cost them about the same, and pick between those.",
            why="What you value and what it costs them are different numbers. "
                "Letting them choose the shape is how both sides gain — and "
                "they will not volunteer it, because showing you the range is "
                "the expensive part for them.",
            ease="moderate",
            ask_phrase="If the total is fixed, are there two or three ways to "
                       "build it? I may value the pieces differently than you'd "
                       "expect.",
        ),
    ]
    if provable:
        routes.insert(0, Route(
            key="show_the_letter",
            label="Show the written offer",
            detail="Put the document in front of them rather than describing it.",
            why="A verifiable offer was worth about ${:,.0f}. An offer you only "
                "describe was worth nothing measurable — claiming is free, so "
                "everyone claims, and the claim stops carrying information."
                .format(_ev.SIM["value_of_provable_offer"].value),
            ease="easiest",
            est_value_usd=int(_ev.SIM["value_of_provable_offer"].value),
            ask_phrase="I've got a written offer and I'd rather be straight "
                       "with you about it than be coy — here it is.",
        ))
    if values.get("has_outside_offer") and not values.get("offer_is_provable"):
        routes.append(Route(
            key="get_it_in_writing",
            label="Get the other offer in writing first",
            detail="An offer you can show is a different object from one you "
                   "can describe.",
            why="Unprovable claims moved nothing in our simulation. Written "
                "ones moved about ${:,.0f}."
                .format(_ev.SIM["value_of_provable_offer"].value),
            ease="moderate",
        ))
    if not cycle_open:
        routes.append(Route(
            key="next_cycle",
            label="Set up the next cycle now",
            detail="Ask what would have to be true next time, and get it "
                   "written down while it is cheap for them to agree.",
            why="Once the window has shut, the same conversation is worth less. "
                "The cheap moment is before the budget is committed, not after.",
            ease="easiest",
            available=True,
        ))

    return Outcome(
        verdict=verdict,
        verdict_label=label,
        headline=("Replacing you plausibly costs them around ${:,.0f}. "
                  "That, not your delivery, is where your leverage comes from."
                  .format(replacement)),
        routes=routes,
        next_step="Book one conversation that covers every term at once.",
        message=None or "",
        exposure=[
            "Saying nothing is not neutral: the standing offer is roughly "
            "{:.1%} and that is what you keep by default."
            .format(_ev.BUDGETED_INCREASE.value),
        ],
        verify=[
            {"action": "Sanity-check what replacing you would cost",
             "where": "your own team's last backfill",
             "note": "How long was the seat empty, who covered it, and what did "
                     "the search cost? You usually know this better than any "
                     "benchmark does."},
            {"action": "Check whether a promotion slot exists at all this cycle",
             "where": "your manager, directly",
             "note": "In our simulation a quarter of the time there was no slot "
                     "in the band at any price. It is worth knowing before you "
                     "spend the conversation on it."},
        ],
        caveats=[
            "Every number here comes from a simulation we built and "
            "pre-registered, not from watching real salary negotiations. It is "
            "a model of the mechanism, not evidence about you.",
            "We do not know what your employer will accept, and we are not "
            "going to guess. Revealing that range costs them real money, which "
            "is precisely why you will not be handed it.",
            "This tool does not out-negotiate anyone. Measured repeatedly, its "
            "advantage over a competent negotiator never cleared 2% of salary. "
            "What it does is get everything on the table at once.",
        ],
        metric_usd=float(leverage),
        evidence_note=("Base rates: {}. Simulation: research/molt, "
                       "pre-registered, 8 amendments."
                       .format(_ev.REPLACEMENT_COST["professional"].source)),
        context={
            "replacement_cost_usd": replacement,
            "leverage_cell": cell,
            "share_who_never_ask": _ev.SHARE_WHO_NEVER_ASK.value,
            "evidence_verified": _ev.VERIFIED,
        },
    )


SITUATION = Situation(
    key="salary_negotiation",
    name="Salary or promotion conversation",
    one_liner="You're going into a pay or promotion conversation and want to "
              "know what you're actually working with.",
    fields=FIELDS,
    assess=assess,
    must_not_assert=MUST_NOT_ASSERT,
    # NOT LIVE. `salary_evidence.VERIFIED` is False: the replacement-cost
    # anchors are consultancy benchmarks and the rest is our own simulation.
    # See salary_evidence.VERIFY_BEFORE_LAUNCH.
    live=False,
    triggers=(
        "raise", "salary", "promotion", "comp", "compensation", "pay review",
        "counter offer", "counteroffer", "asking for more", "performance review",
        "they offered me", "job offer", "negotiate my",
    ),
    intake_hint=(
        "The person is going into a pay or promotion conversation. Look for: "
        "their current salary, what kind of role it is, whether they hold "
        "another offer AND whether they could show it in writing, how long "
        "they have been in the role, and whether the comp cycle is still open."
    ),
)
