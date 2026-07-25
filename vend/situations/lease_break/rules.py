"""Legal/structural layer for the lease-break situation.

SAME HARD RULE AS vend/rent/jurisdictions.py: this module tells a person
HOW TO CHECK. It never tells them what their legal position IS.

That rule matters more here than it does for a renewal. A renewal
mistake costs money. A lease-break mistake — walking out believing a
statute protects you when it doesn't, or stopping payment on a
habitability theory — costs a judgment, a collections record, and a
rental history that follows you.

So: naming a statute as a place to look is safe and useful. Stating what
it says about YOUR tenancy is not, and `verified` gates every figure the
same way the renewal module gates rent-board rates.

────────────────────────────────────────────────────────────────────
VERIFY BEFORE LAUNCH
────────────────────────────────────────────────────────────────────
Nothing in this module is marked verified. Before this situation is
shown to a member of the public, somebody has to confirm against
primary sources, per state in scope:

  1. Whether the state imposes a landlord duty to mitigate damages on
     residential leases, and whether it can be waived by the lease.
  2. The statutory early-termination rights actually available (military
     / SCRA, domestic violence, senior or health, habitability) and
     their notice and documentation requirements.
  3. CLOSED 2026-07-25. RPL § 227-e verified against nysenate.gov:
     section number, full text, residential scope, burden of proof on
     the party seeking damages, and non-waivability all confirmed. See
     NY_MITIGATION below. Every other state remains outstanding.

Until that happens, `VERIFIED` stays False and the copy stays in the
conditional. The framework's must-not-assert rules enforce it.
"""

from __future__ import annotations

from dataclasses import dataclass

VERIFIED = False
VERIFIED_ON = ""   # set only when a human has checked primary sources

# ── New York: RPL § 227-e ────────────────────────────────────────────
# VERIFIED 2026-07-25 against nysenate.gov, the legislature's own site,
# and cross-checked against Justia's codification.
#
# This is the one state we can say anything concrete about, and note
# WHAT is being said: what the statute says, with a citation. Not what
# it means for a particular tenancy — that still depends on the lease,
# the facts, and a court. The framing is the same one jurisdictions.py
# uses for the RGB orders.
NY_MITIGATION = {
    "statute": "New York Real Property Law § 227-e",
    "title": "Landlord duty to mitigate damages",
    "source": "https://www.nysenate.gov/legislation/laws/RPP/227-E",
    "verified_on": "2026-07-25",
    "applies_to": "Leases covering premises occupied for dwelling purposes.",
    "what_it_says": (
        "Where a tenant leaves in breach of the lease, the statute directs the "
        "landlord to act in good faith and, according to their resources and "
        "abilities, take reasonable and customary actions to re-rent — at fair "
        "market value or the rate in the old lease, whichever is lower."
    ),
    "the_part_people_miss": (
        "Once a new tenant's lease is in effect it TERMINATES the previous "
        "tenant's lease. So the clock on what can be claimed from you stops "
        "when the unit re-rents, rather than running to the end of your term."
    ),
    "burden_of_proof": (
        "The statute puts the burden on the party seeking to recover damages "
        "— which is the landlord, not you."
    ),
    "cannot_be_waived": (
        "A lease provision that exempts the landlord from this duty is void as "
        "contrary to public policy. A clause in your lease saying otherwise "
        "does not, on the face of the statute, get them out of it."
    ),
    "still_not_a_conclusion": (
        "What counts as reasonable, whether your departure was in breach, and "
        "what was actually done to re-rent are all questions of fact. This "
        "tells you which statute to read and what it says; it does not tell "
        "you how your case comes out."
    ),
}


@dataclass(frozen=True)
class VerificationStep:
    """One concrete thing a person can do to establish a fact themselves.

    `where` must be an official source or a document they already hold —
    never a blog and never us.
    """

    action: str
    where: str
    note: str = ""

    def to_dict(self) -> dict:
        return {"action": self.action, "where": self.where, "note": self.note}


# The single most important thing to read, and almost nobody does.
READ_YOUR_LEASE = VerificationStep(
    action="Read the termination, assignment and sublet clauses of your own lease",
    where="Your signed lease",
    note=(
        "This is the first thing to do and it costs nothing. Many leases "
        "contain an early-termination clause with a stated fee and notice "
        "period, and many state whether you may assign the lease or sublet. "
        "What your own lease says outranks anything general we can tell you."
    ),
)

MITIGATION_STEP = VerificationStep(
    action="Find out whether your state requires the landlord to re-rent",
    where="Your state attorney general or a local tenant legal-services organisation",
    note=(
        "In many states a landlord who is owed rent after a tenant leaves "
        "must make reasonable efforts to re-rent the unit rather than let it "
        "sit and bill you. Whether that applies where you live, and what "
        "counts as reasonable, is a state-law question we cannot answer for "
        "you — but it is the question that decides how much walking away "
        "actually costs."
    ),
)

STATUTORY_STEP = VerificationStep(
    action="Check whether a statutory termination right applies to you",
    where="Your state's landlord-tenant statute, or a legal-services organisation",
    note=(
        "Separate from anything in your lease, some circumstances carry "
        "termination rights created by statute — active-duty military orders "
        "under the federal Servicemembers Civil Relief Act is the widest "
        "known one, and many states have provisions covering domestic "
        "violence and some covering serious habitability failures. Each has "
        "its own notice and documentation requirements. These are worth "
        "checking before you negotiate anything, because they are not "
        "negotiations."
    ),
)

WRITING_STEP = VerificationStep(
    action="Put whatever you agree in writing before you hand back the keys",
    where="In writing, to your landlord or managing agent",
    note=(
        "A release you cannot produce later is not a release. Ask for a "
        "signed document saying the tenancy ends on a stated date and that "
        "no further rent is owed."
    ),
)


# Circumstances that may carry a statutory route. These are ROUTING
# HINTS — they decide whether we tell somebody to go and check, never
# whether they qualify.
STATUTORY_TRIGGERS = {
    "military": (
        "Active-duty military orders",
        "The federal Servicemembers Civil Relief Act creates a lease-termination "
        "right for qualifying orders, and it is federal rather than state law, so "
        "it is the same wherever you are. It has strict notice and documentation "
        "requirements. Check this before negotiating anything — if it applies, you "
        "are not negotiating.",
    ),
    "safety": (
        "Domestic violence or a safety order",
        "Many states have lease-termination provisions for tenants in this "
        "situation, usually requiring specific documentation. What is available "
        "varies a great deal by state. A local legal-services organisation is the "
        "right first call, and this route should be checked before any other.",
    ),
    "habitability": (
        "The place is not habitable",
        "Serious, documented, unrepaired conditions can in some places support "
        "ending a tenancy. It is a legal theory with a high bar, not a self-help "
        "right, and the way it goes wrong is people stopping payment first. Keep "
        "paying, document everything in writing, and get advice before acting.",
    ),
}

# Warnings that ride along regardless of route. Written once, shown
# always — these are the failure modes that turn a costly situation into
# a ruinous one.
STANDING_CAVEATS = (
    "Do not stop paying rent while any of this is in progress. Withholding is "
    "how a manageable disagreement becomes a judgment against you, and it "
    "undercuts every other route on this page.",
    "Nothing here is a statement about your legal position, because your "
    "position depends on your lease, your state, and facts we cannot see. "
    "Treat all of it as a prompt to verify.",
    "This is information, not legal advice. For anything contested, a tenant "
    "attorney or a legal-services organisation is worth the call — many are free.",
    "An unpaid balance after you leave can be sent to collections and can "
    "follow you into your next tenancy application. That risk is the reason "
    "the cheapest-looking route is not always the best one.",
)


# Metro key -> the state rules we have verified. Absent means we have
# nothing beyond the general "go and check" guidance, which is the
# honest default and covers every other metro today.
_METRO_TO_STATE = {"new_york": NY_MITIGATION}


def block(metro_key: str, reason: str | None) -> dict:
    """Everything we can honestly say, for one metro and reason.

    Deliberately thin. There is no per-state table here yet, and
    inventing one would be worse than admitting its absence: a wrong
    mitigation rule would tell somebody their exposure is one month when
    it is twelve.
    """
    norm = (metro_key or "").lower().replace(" ", "_").replace("-", "_")
    state = _METRO_TO_STATE.get(norm)

    steps = [READ_YOUR_LEASE, MITIGATION_STEP]

    statutory = None
    if reason in STATUTORY_TRIGGERS:
        label, note = STATUTORY_TRIGGERS[reason]
        statutory = {"label": label, "note": note}
        steps.insert(1, STATUTORY_STEP)
    else:
        steps.append(STATUTORY_STEP)

    steps.append(WRITING_STEP)

    return {
        "rules_verified": VERIFIED,
        # Present only where a statute has been read at the primary source.
        "state_mitigation": state,
        "verified_on": VERIFIED_ON,
        "how_to_verify": [s.to_dict() for s in steps],
        "statutory_route": statutory,
        "caveats": list(STANDING_CAVEATS),
        "status_note": (
            "We have verified one state's mitigation statute (New York) and "
            "publish what it says. Everywhere else we have not published "
            "state-by-state rules: we tell you which question to ask and who "
            "to ask it of, rather than guessing at an answer that varies by "
            "state and by lease."
            if state else
            "We have not published state-by-state termination rules for your "
            "area. Where the law matters we tell you which question to ask and "
            "who to ask it of, rather than guessing at an answer that varies by "
            "state and by lease."
        ),
    }
