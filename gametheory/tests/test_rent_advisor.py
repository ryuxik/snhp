"""Tests for the rent-renewal advisor.

The properties that matter here are honesty properties, not just
correctness ones: the tool must be able to say "you have no leverage,"
must never assert a legal status, and must never invent local data for a
metro it doesn't know.
"""

import pytest

from vend.rent import advisor, jurisdictions, metros


# --- determinism + basic math ---------------------------------------

def test_deterministic():
    a = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    b = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    assert a == b


def test_increase_math():
    d = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    assert d["increase"]["monthly"] == 150
    assert d["increase"]["pct"] == 7.5
    assert d["increase"]["annual_cost"] == 1800


def test_rejects_nonsense_input():
    for args in [("Denver", 0, 2000, 12), ("Denver", 2000, -1, 12),
                 ("Denver", 2000, 2100, -3)]:
        with pytest.raises(ValueError):
            advisor.assess(*args)


# --- the honesty properties -----------------------------------------

def test_can_say_you_have_no_leverage():
    """A tool that always finds leverage is a horoscope."""
    d = advisor.assess("Buffalo", 1400, 1500, 10).to_dict()
    assert d["verdict"] == "weak"
    assert d["asks"] == []
    assert d["message"] == ""


def test_no_increase_means_nothing_to_do():
    d = advisor.assess("Denver", 2000, 2000, 40).to_dict()
    assert d["verdict"] == "weak"
    assert "isn't going up" in d["headline"]


def test_tightening_market_downgrades_even_at_decent_share():
    """San Francisco has a ~27% concession share but is tightening hard
    (-8pp). Level alone would read 'moderate'; direction must win."""
    sf = metros.lookup("San Francisco")
    assert sf.tightening is True
    d = advisor.assess("San Francisco", 3200, 3400, 36).to_dict()
    assert d["verdict"] == "weak"


def test_never_asserts_legal_status():
    """The legal block may raise the question. It must never answer it.

    These are whole assertive phrases — a bare keyword check would trip
    on our own safety copy ('never withhold rent'), which is the
    opposite of the harm.
    """
    d = advisor.assess("New York", 3400, 3600, 30).to_dict()
    legal = d["legal"]
    assert legal["may_be_regulated"] is True
    blob = str(legal).lower()
    for forbidden in [
        "you are rent stabilized",
        "your unit is stabilized",
        "this increase is illegal",
        "your legal rent is",
        "you are covered by good cause",
        "your increase is unlawful",
    ]:
        assert forbidden not in blob, forbidden
    assert "how_to_verify" in legal


def test_published_rates_carry_provenance_and_are_framed_safely():
    """Rates may appear only once verified — and Good Cause must be
    described as a rebuttable presumption, never as a cap."""
    legal = advisor.assess("New York", 3400, 3600, 30).to_dict()["legal"]
    rates = legal["official_rates"]
    assert legal["rates_as_of"] and legal["rates_source"]

    gce = rates["good_cause"]
    assert "not a cap" in gce["what_it_is"].lower()
    assert gce["freshness_warning"]          # the AG's own page is stale
    assert gce["how_to_tell_if_covered"]     # the §231-c notice is the evidence

    # The guideline must be tied to lease commencement, not offer date.
    assert "new lease starts" in rates["rgb_note"].lower()


def test_rgb_order_is_keyed_to_lease_commencement():
    """The easiest silent bug: an Oct 1 boundary flips a stabilized
    tenant between a 3% guideline and a 0% freeze."""
    sep = jurisdictions.rgb_order_for("2026-09-15")
    oct_ = jurisdictions.rgb_order_for("2026-10-01")
    assert sep["one_year_pct"] == 3.0
    assert oct_["one_year_pct"] == 0.0
    # Unknown date must refuse to guess rather than default to either.
    assert jurisdictions.rgb_order_for(None) is None
    assert jurisdictions.rgb_order_for("2019-01-01") is None


def test_notice_rights_apply_to_everyone_and_scale_with_tenure():
    """RPL 226-c covers unregulated tenants too — the fact almost no
    market-rate renter knows."""
    assert jurisdictions.notice_days_required(6) == 30
    assert jurisdictions.notice_days_required(18) == 60
    assert jurisdictions.notice_days_required(40) == 90
    rates = advisor.assess("New York", 3400, 3600, 30).to_dict()["legal"]["official_rates"]
    assert "including unregulated" in rates["notice_rights"]["applies_to"].lower()


def test_safety_copy_is_present():
    """Positive assertion: the never-withhold guidance must survive any
    future copy edit."""
    caveats = " ".join(
        advisor.assess("New York", 3400, 3600, 30).to_dict()["legal"]["caveats"]
    ).lower()
    assert "never withhold rent" in caveats
    assert "not legal advice" in caveats


def test_regulated_metro_routes_to_legal_check_even_when_market_is_weak():
    """The bug the smoke test caught: NYC market leverage is weak, but a
    possibly-stabilized tenant must be pointed at the legal question
    before being told to sign."""
    d = advisor.assess("New York", 3400, 3600, 14).to_dict()
    assert d["verdict"] == "weak"
    assert "regulated" in d["next_step"].lower()


def test_unknown_metro_degrades_instead_of_inventing():
    d = advisor.assess("Ulaanbaatar", 2000, 2100, 30).to_dict()
    assert d["market"]["metro_known"] is False
    assert "concession_share_pct" not in d["market"]
    assert any("national" in c.lower() for c in d["caveats"])


# --- the evidence-backed product logic ------------------------------

def test_tenure_doubles_odds():
    """Odds are deliberately rounded to 2dp in the payload — the source
    is one 2022 vendor survey, and rendering 14.5% would be false
    precision. The near-doubling is the finding; the decimal isn't."""
    short = advisor.assess("Denver", 2000, 2150, 12).to_dict()
    long = advisor.assess("Denver", 2000, 2150, 36).to_dict()
    assert long["odds_if_you_ask"] > short["odds_if_you_ask"]
    assert short["odds_if_you_ask"] == pytest.approx(0.14, abs=0.01)
    assert long["odds_if_you_ask"] == pytest.approx(0.27, abs=0.01)
    # the load-bearing claim: tenure roughly doubles your odds
    assert long["odds_if_you_ask"] / short["odds_if_you_ask"] > 1.7


def test_asks_are_ordered_easiest_to_hardest():
    """The whole expert insight: headline rent is the HARDEST ask and
    most tenants lead with it."""
    d = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    keys = [a["key"] for a in d["asks"]]
    assert keys[0] == "concession_parity"
    assert keys[-1] == "rent_reduction"
    assert d["asks"][0]["ease"] == "easiest"
    assert d["asks"][-1]["ease"] == "hardest"


def test_message_is_sendable_and_non_adversarial():
    d = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    msg = d["message"]
    assert len(msg) > 100
    for hostile in ["demand", "legal action", "unacceptable", "or else"]:
        assert hostile not in msg.lower()
    assert "thanks" in msg.lower()


def test_base_rates_are_cited_not_invented():
    d = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    assert "Urban Institute" in d["evidence_note"]
    assert d["share_who_never_ask"] == pytest.approx(0.61)
    # Guard the specific mis-attribution that shipped once: the Urban
    # Institute reports 39% TRIED to negotiate, so 61% did not. 72% came
    # from a different survey and must never be cited to them again.
    assert d["share_who_never_ask"] != pytest.approx(0.72)


# --- data layer integrity -------------------------------------------

def test_metro_table_is_sane():
    assert len(metros.METROS) >= 50
    for key, m in metros.METROS.items():
        assert 0 <= m.concession_share <= 100, key
        assert m.typical_rent > 0, key
    assert metros.lookup("Denver").tier == "strong"
    assert metros.lookup("New York").tier == "weak"


def test_market_context_always_stamps_provenance():
    for metro in ["Denver", "Nowhereville"]:
        ctx = metros.market_context(metro)
        assert ctx["as_of"], metro


def test_default_jurisdiction_is_unregulated():
    """Defaulting to 'no regulation' understates rather than invents."""
    j = jurisdictions.for_metro("Austin")
    assert j.has_regulated_stock is False


def test_drafted_message_is_grammatical():
    """Regression: the message spliced lowercased imperatives into a
    clause, producing 'would you consider request 6 weeks of free rent'.
    This is the text a user copies and sends to their landlord, so a
    grammar bug here is a credibility bug."""
    d = advisor.assess("Denver", 2000, 2150, 30).to_dict()
    msg = d["message"]
    for broken in ["consider request", "consider offer", "consider ask",
                   "open to offer 24", "consider parking"]:
        assert broken not in msg.lower(), broken
    assert "would you consider applying" in msg.lower()
    # every ask must carry an embeddable clause, not just an imperative
    for a in d["asks"]:
        assert a["ask_phrase"]
        assert not a["ask_phrase"][0].isupper(), a["key"]


def test_next_step_uses_no_directional_language():
    """This payload renders in different orders on the page and via MCP, so
    'below'/'above' is a bug waiting to happen — it has bitten twice.
    Describe the thing, never its position."""
    for metro in ("Denver", "New York", "Buffalo"):
        step = advisor.assess(metro, 2000, 2150, 30).to_dict()["next_step"]
        for directional in ("below", "above"):
            assert directional not in step.lower(), (metro, directional)


def test_our_own_measurements_are_described_never_quoted():
    """`evidence` strings say how sure we are about our OWN findings.

    A figure in one is a simulation output reaching a renter, on a page
    that promises none. This is a SHAPE rule, not another denylist entry,
    because the denylist is exactly what failed: $460 went reader-facing
    the day `evidence` was wired into rent.html, and the enumerated-figure
    guard in test_situations.py sailed past it. Every number this study
    produced is downstream of at least one parameter whose justification
    was the outcome it produces, so the ordering ships and the magnitude
    does not.
    """
    import re

    from vend.rent import advisor as A

    out = A.assess(metro="denver", current_rent=1800, offered_rent=1950,
                   months_at_address=30).to_dict()
    for i, ev in enumerate(out.get("evidence", [])):
        assert "$" not in ev, (
            f"evidence[{i}] quotes a dollar figure from our own model: {ev!r}"
        )
        assert not re.search(r"\d+(?:\.\d+)?\s?%", ev), (
            f"evidence[{i}] quotes a percentage from our own model: {ev!r}"
        )
