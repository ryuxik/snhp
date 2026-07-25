"""Tests for the situation framework.

The load-bearing one is `test_framework_is_situation_agnostic`. Everything
else checks behaviour; that one checks the claim — that a new situation is
data plus one pure function, and that the framework does not know which
situations exist. If it ever fails, the abstraction has leaked and the
right response is to fix the layering, not the test.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re

import pytest

from vend.situations import answer, guard, intake, priors, registry, sensitivity, ux
from vend.situations import rent_renewal
from vend.situations.lease_break import assess as lb_assess, evidence, rules
from vend.situations.schema import (
    FIRM, INFERRED, MustNotAssert, Outcome, Rule, STATED,
)

_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_FRAMEWORK_DIR = os.path.join(_HERE, "vend", "situations")

# The framework proper. registry.py and __init__.py are the wiring and
# are allowed to name situations; nothing else is.
FRAMEWORK_FILES = ("schema.py", "priors.py", "sensitivity.py", "ux.py", "guard.py")


def _src(name: str) -> str:
    with open(os.path.join(_FRAMEWORK_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def _code_only(text: str) -> str:
    """Strip docstrings and comments — prose may discuss situations."""
    text = re.sub(r'""".*?"""', "", text, flags=re.S)
    text = re.sub(r"'''.*?'''", "", text, flags=re.S)
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


# ── The gate ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("fname", FRAMEWORK_FILES)
def test_framework_is_situation_agnostic(fname):
    """No framework file may name a situation or its data modules.

    This is the pre-registered gate. Adding lease-break was allowed to
    touch: its own package, one registry line, one route, one page. If a
    framework file has to learn a situation's name, a new situation is a
    rewrite and the layering claim is false.
    """
    code = _code_only(_src(fname))
    for forbidden in ("rent_renewal", "lease_break", "vend.rent", "advisor",
                      "metros", "jurisdictions"):
        assert forbidden not in code, (
            f"{fname} references {forbidden!r} in code — the framework must not "
            f"know which situations exist."
        )


def test_framework_does_not_import_the_registry():
    """The judgment layers must be usable with a situation passed in."""
    for fname in FRAMEWORK_FILES:
        code = _code_only(_src(fname))
        assert "import registry" not in code and "from vend.situations import registry" not in code


def test_adding_a_situation_is_one_registry_line():
    assert set(registry.SITUATIONS) == {"rent_renewal", "lease_break"}
    for key, s in registry.SITUATIONS.items():
        assert s.key == key
        assert callable(s.assess)
        assert s.fields, f"{key} declares no fields"


def test_renewal_core_is_untouched():
    """The adapter wraps vend/rent; it does not reach into it sideways."""
    from vend.rent import advisor

    a = advisor.assess(metro="denver", current_rent=1800,
                       offered_rent=1950, months_at_address=30)
    o = rent_renewal.assess({"metro": "denver", "current_rent": 1800,
                             "offered_rent": 1950, "months_at_address": 30})
    assert o.verdict == a.verdict
    assert o.headline == a.headline
    assert [r.key for r in o.routes] == [x.key for x in a.asks]


# ── Determinism ──────────────────────────────────────────────────────


@pytest.mark.parametrize("key,values", [
    ("rent_renewal", {"metro": "austin", "current_rent": 1600,
                      "offered_rent": 1750, "months_at_address": 26}),
    ("lease_break", {"metro": "denver", "monthly_rent": 2400,
                     "months_remaining": 8.0, "has_termination_clause": False,
                     "termination_fee_months": None,
                     "replacement_tenant_ready": False,
                     "lease_allows_transfer": "unknown",
                     "move_out_reason": "job", "security_deposit": 2400,
                     "credit_score": None}),
])
def test_assess_is_deterministic(key, values):
    s = registry.get(key)
    first = s.assess(values).to_dict()
    for _ in range(5):
        assert s.assess(values).to_dict() == first


def test_every_situation_returns_the_same_contract():
    """One answer shape, so a person learns to read one answer."""
    outs = [
        registry.get("rent_renewal").assess(
            {"metro": "denver", "current_rent": 1800, "offered_rent": 1950,
             "months_at_address": 30}),
        registry.get("lease_break").assess(
            {"metro": "denver", "monthly_rent": 2000, "months_remaining": 9.0,
             "has_termination_clause": None, "termination_fee_months": None,
             "replacement_tenant_ready": None, "lease_allows_transfer": "unknown",
             "move_out_reason": "other", "security_deposit": None,
             "credit_score": None}),
    ]
    keys = [set(o.to_dict()) for o in outs]
    assert keys[0] == keys[1]
    for o in outs:
        assert isinstance(o, Outcome)
        assert o.verdict in ("strong", "moderate", "weak")
        assert o.headline
        assert o.caveats, "every answer must carry its own limits"


# ── The horoscope guard ──────────────────────────────────────────────


def test_renewal_can_tell_you_to_just_sign():
    o = registry.get("rent_renewal").assess(
        {"metro": "new_york", "current_rent": 3000,
         "offered_rent": 3100, "months_at_address": 10})
    assert o.verdict == "weak"
    assert o.message == ""


@pytest.mark.parametrize("override,why", [
    ({"months_remaining": 1.5}, "short tail — riding it out costs the same"),
    ({"has_termination_clause": True, "termination_fee_months": 1.0},
     "the clause is already cheaper than any negotiation"),
])
def test_lease_break_can_tell_you_there_is_no_leverage(override, why):
    """A tool that always finds an exit is a horoscope."""
    values = {"metro": "new_york", "monthly_rent": 3400, "months_remaining": 11.0,
              "has_termination_clause": None, "termination_fee_months": None,
              "replacement_tenant_ready": None, "lease_allows_transfer": "unknown",
              "move_out_reason": "other", "security_deposit": None,
              "credit_score": None}
    o = registry.get("lease_break").assess({**values, **override})
    assert o.verdict == "weak", why
    assert o.message == "", "nothing to send when there is nothing to ask for"


# ── Must-not-assert ──────────────────────────────────────────────────


def _grid_lease_break():
    for metro in ("denver", "new_york", "san_francisco", "nowhere_at_all"):
        for months in (0.5, 3.0, 11.0, 23.0):
            for clause in (None, True, False):
                for rep in (None, True, False):
                    for transfer in ("yes", "no", "unknown"):
                        for reason in ("job", "military", "safety",
                                       "habitability", "cost", "other"):
                            yield {
                                "metro": metro, "monthly_rent": 2200,
                                "months_remaining": months,
                                "has_termination_clause": clause,
                                "termination_fee_months": 2.0 if clause else None,
                                "replacement_tenant_ready": rep,
                                "lease_allows_transfer": transfer,
                                "move_out_reason": reason,
                                "security_deposit": 2200, "credit_score": 700,
                            }


def test_lease_break_never_breaks_its_own_rules():
    s = registry.get("lease_break")
    n = 0
    for values in _grid_lease_break():
        guard.check(s, s.assess(values))
        n += 1
    assert n > 500


def test_renewal_never_breaks_its_own_rules():
    s = registry.get("rent_renewal")
    n = 0
    for metro in ("denver", "new_york", "san_francisco", "nowhere_at_all"):
        for cur in (900, 1800, 4000):
            for delta in (-100, 0, 50, 300, 900):
                for months in (2, 14, 30, 60):
                    guard.check(s, s.assess({
                        "metro": metro, "current_rent": cur,
                        "offered_rent": cur + delta, "months_at_address": months,
                    }))
                    n += 1
    assert n > 100


def test_the_guard_actually_fires():
    """A rule set that never fires is decoration."""
    s = registry.get("lease_break")
    bad = Outcome(verdict="strong", headline="You have the right to terminate.")
    with pytest.raises(MustNotAssert):
        guard.check(s, bad)


def test_guard_allows_the_warning_against_withholding():
    """Regression: a blunter rule blocked our own do-not-withhold caveat."""
    for key in ("lease_break", "rent_renewal"):
        s = registry.get(key)
        ok = Outcome(
            verdict="moderate", headline="Fine.",
            caveats=["Do not stop paying rent while any of this is in progress.",
                     "Never withhold rent on the strength of anything here."],
        )
        guard.check(s, ok)


def test_withholding_advice_is_still_caught():
    s = registry.get("lease_break")
    for text in ("You could stop paying rent until they respond.",
                 "Consider withholding rent as leverage.",
                 "You don't owe anything after you leave."):
        with pytest.raises(MustNotAssert):
            guard.check(s, Outcome(verdict="strong", headline=text))


# ── Derived UX: questions are earned, not authored ───────────────────


def _lb_priors(**over):
    s = registry.get("lease_break")
    return s, priors.resolve(s, stated={"metro": "new_york", "monthly_rent": 3000,
                                        "months_remaining": 10.0, **over})


def test_credit_score_is_never_asked():
    """The deliberate control. It is declared and swept; it earns nothing."""
    s = registry.get("lease_break")
    asked = set()
    for metro in ("denver", "new_york", "austin", "nowhere_at_all"):
        for months in (1.0, 3.0, 6.0, 11.0):
            for rent in (900, 2000, 5000):
                _, p = _lb_priors(metro=metro, monthly_rent=rent,
                                  months_remaining=months)
                asked |= {q.key for q in sensitivity.rank(s, p)}
    assert asked, "sanity: something must be asked"
    assert "credit_score" not in asked


def test_the_question_set_shrinks_as_facts_are_established():
    """What "derived, not authored" actually means — corrected.

    An earlier version of this test asserted that different markets
    produce different QUESTION SETS, and it passed. It was passing for
    the wrong reason: a cap of three questions truncated the ranked list,
    so the markets differed only in what got cut off. With the cap gone
    (a cap could suppress a prior that changes the advice) both markets
    ask everything above the threshold, and the sets are identical.

    The real demonstration is this: establish a couple of facts and
    questions DISAPPEAR, because they no longer change anything. No form
    does that.
    """
    s = registry.get("lease_break")
    cold = priors.resolve(s, stated={"metro": "denver", "monthly_rent": 2000,
                                     "months_remaining": 9.0})
    warm = priors.resolve(s, stated={"metro": "denver", "monthly_rent": 2000,
                                     "months_remaining": 9.0,
                                     "has_termination_clause": False,
                                     "replacement_tenant_ready": False})
    before = [q.key for q in sensitivity.rank(s, cold)]
    after = [q.key for q in sensitivity.rank(s, warm)]
    assert len(after) < len(before), "answering should retire questions"
    assert set(after) < set(before)


def test_questions_are_ranked_by_consequence_not_declaration_order():
    s = registry.get("lease_break")
    p = priors.resolve(s, stated={"metro": "denver", "monthly_rent": 2000,
                                  "months_remaining": 9.0})
    qs = sensitivity.rank(s, p)
    assert [q.score for q in qs] == sorted((q.score for q in qs), reverse=True)
    declared = [f.key for f in s.fields]
    assert [q.key for q in qs] != [k for k in declared if k in {q.key for q in qs}][:len(qs)] \
        or len(qs) < 2, "ranking must not merely echo declaration order"


def test_the_stakes_attached_to_a_question_track_the_market():
    """The set no longer differs by market; what is at stake does, and
    that is what the person is actually told."""
    s = registry.get("lease_break")
    swings = {}
    for metro in ("denver", "new_york"):
        p = priors.resolve(s, stated={"metro": metro, "monthly_rent": 2000,
                                      "months_remaining": 9.0})
        top = sensitivity.rank(s, p)[0]
        swings[metro] = top.swing_usd
    assert swings["denver"] > swings["new_york"] * 1.5, (
        "a soft market puts more at stake on the same question")


def test_no_questions_once_nothing_would_change_the_answer():
    s = registry.get("lease_break")
    p = priors.resolve(s, stated={
        "metro": "new_york", "monthly_rent": 3400, "months_remaining": 11.0,
        "has_termination_clause": False, "replacement_tenant_ready": True,
        "lease_allows_transfer": "yes", "move_out_reason": "job",
    })
    assert sensitivity.rank(s, p) == []


def test_all_required_inputs_are_asked_at_once():
    """Regression: a cap of three sent renewal back for a second round.

    Required inputs are not a judgment call — they are the minimum the
    core needs to run. Rationing them is the one thing the threshold was
    never meant to do.
    """
    for key in registry.SITUATIONS:
        s = registry.get(key)
        p = priors.resolve(s, stated={})
        asked = {q.key for q in sensitivity.rank(s, p)}
        required = {f.key for f in s.fields if f.required}
        assert required <= asked, f"{key} withheld required inputs: {required - asked}"


def test_nothing_that_clears_the_threshold_is_dropped():
    """No quota above the relevance filter."""
    s = registry.get("lease_break")
    p = priors.resolve(s, stated={"metro": "denver", "monthly_rent": 2400,
                                  "months_remaining": 9.0})
    qs = sensitivity.rank(s, p)
    assert all(q.score >= sensitivity.ASK_THRESHOLD for q in qs)
    assert not hasattr(sensitivity, "MAX_QUESTIONS"), (
        "a cap on questions can silently suppress a prior that changes the advice"
    )


def test_ux_uses_only_the_fixed_component_vocabulary():
    """Nothing generates markup. Only which components appear is dynamic."""
    for key in registry.SITUATIONS:
        s = registry.get(key)
        p = priors.resolve(s, stated={})
        screen = ux.build(s, p, None)
        for q in screen["questions"]:
            assert q["kind"] in ux.COMPONENTS
        for f in s.fields:
            assert f.kind in ux.COMPONENTS


# ── The mechanism worth showing ──────────────────────────────────────


def test_exposure_inverts_with_the_market():
    """The non-obvious finding, and the reason lease-break is the demo.

    A soft market is where a renewing tenant has leverage and where a
    leaving tenant is most exposed — the unit sits empty and that empty
    time is what gets billed to them.
    """
    s = registry.get("lease_break")
    base = {"monthly_rent": 2000, "months_remaining": 9.0,
            "has_termination_clause": None, "termination_fee_months": None,
            "replacement_tenant_ready": None, "lease_allows_transfer": "unknown",
            "move_out_reason": "other", "security_deposit": None,
            "credit_score": None}
    soft = s.assess({**base, "metro": "denver"})
    tight = s.assess({**base, "metro": "new_york"})
    assert soft.metric_usd > tight.metric_usd * 1.5
    # ...and both stay far below the naive "you owe the whole lease" figure.
    assert soft.metric_usd < soft.context["remaining_balance_usd"]

    renew = registry.get("rent_renewal")
    assert renew.assess({"metro": "denver", "current_rent": 2000,
                         "offered_rent": 2200, "months_at_address": 30}).verdict == "strong"
    assert renew.assess({"metro": "new_york", "current_rent": 2000,
                         "offered_rent": 2200, "months_at_address": 30}).verdict == "weak"


def test_unknown_metro_degrades_and_says_so():
    s = registry.get("lease_break")
    o = s.assess({"metro": "atlantis", "monthly_rent": 2000,
                  "months_remaining": 9.0, "has_termination_clause": None,
                  "termination_fee_months": None, "replacement_tenant_ready": None,
                  "lease_allows_transfer": "unknown", "move_out_reason": "other",
                  "security_deposit": None, "credit_score": None})
    assert o.context["market"]["metro_known"] is False
    assert any("don't have market data" in c for c in o.caveats)


# ── Unverified figures may not masquerade as data ────────────────────


def test_lease_break_evidence_is_not_marked_publishable():
    """Fails deliberately the day somebody flips it without sourcing.

    Both flags are gates in the spirit of jurisdictions.rates_verified.
    When the VERIFY BEFORE LAUNCH lists in evidence.py and rules.py are
    actually worked through, flip the flag AND update this test in the
    same commit — that is the point of the coupling.
    """
    assert evidence.PUBLISHABLE is False
    assert rules.VERIFIED is False


def test_every_lease_break_answer_discloses_its_basis():
    s = registry.get("lease_break")
    o = s.assess({"metro": "denver", "monthly_rent": 2000, "months_remaining": 9.0,
                  "has_termination_clause": None, "termination_fee_months": None,
                  "replacement_tenant_ready": None, "lease_allows_transfer": "unknown",
                  "move_out_reason": "other", "security_deposit": None,
                  "credit_score": None})
    assert evidence.BASIS in o.caveats
    assert o.evidence_note
    assert any("how to check" in c.lower() or "prompt to verify" in c.lower()
               for c in o.caveats)


def test_lease_break_makes_no_odds_claim():
    """There is no survey we trust. The slot stays empty rather than filled."""
    s = registry.get("lease_break")
    o = s.assess({"metro": "denver", "monthly_rent": 2000, "months_remaining": 9.0,
                  "has_termination_clause": None, "termination_fee_months": None,
                  "replacement_tenant_ready": None, "lease_allows_transfer": "unknown",
                  "move_out_reason": "other", "security_deposit": None,
                  "credit_score": None})
    assert o.odds is None and o.odds_basis == ""


def test_verification_always_starts_with_your_own_lease():
    s = registry.get("lease_break")
    for values in list(_grid_lease_break())[:40]:
        o = s.assess(values)
        assert o.verify, "a lease-break answer without verification steps is unsafe"
        assert "lease" in o.verify[0]["action"].lower() or \
               "statutory" in o.verify[0]["action"].lower()


# ── Intake: the LLM fills the struct and nothing else ────────────────


def test_intake_marks_unquoted_values_as_guesses():
    s = registry.get("lease_break")
    text = "I signed a year lease in Brooklyn at 3400 a month and need out by October"
    items = [
        {"key": "monthly_rent", "value_text": "3400",
         "quoted_from_user": "3400 a month", "confidence": 0.95},
        {"key": "months_remaining", "value_text": "9",
         "quoted_from_user": "", "confidence": 0.9},          # worked out, not quoted
        {"key": "metro", "value_text": "new_york",
         "quoted_from_user": "in Brooklyn", "confidence": 0.9},
        {"key": "landlord_mood", "value_text": "grumpy",
         "quoted_from_user": "", "confidence": 1.0},          # undeclared — dropped
        {"key": "monthly_rent_2", "value_text": "1",
         "quoted_from_user": "totally not in the text", "confidence": 1.0},
    ]
    values, prov, conf, quoted = intake._harvest(s, items, text)

    assert prov["monthly_rent"] == STATED
    assert prov["months_remaining"] == INFERRED, "unquoted values are guesses"
    assert "landlord_mood" not in values, "undeclared fields never enter the struct"
    assert "monthly_rent_2" not in values
    assert conf["months_remaining"] <= 0.6


def test_inferred_values_keep_getting_asked_about():
    """A guess is not a fact, no matter how confident the model was."""
    s = registry.get("lease_break")
    p = priors.resolve(
        s,
        stated={"metro": "new_york", "monthly_rent": 3400, "months_remaining": 11.0},
        provenance={"months_remaining": INFERRED},
    )
    assert not p.is_firm("months_remaining")
    assert "months_remaining" in p.unresolved(s)
    assert INFERRED not in FIRM


def test_intake_degrades_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = intake.read("my landlord wants to raise the rent on my renewal")
    assert r.used_llm is False
    assert r.situation_key == "rent_renewal"
    assert r.values == {}, "no key means no extraction, never invented values"
    assert r.note


def test_keyword_classifier_separates_the_two_situations():
    assert registry.classify(
        "I want to break my lease and move out early",
        public=False)[0] == "lease_break"
    assert registry.classify(
        "they sent me a renewal offer, rent increase")[0] == "rent_renewal"
    assert registry.classify("what is the capital of France") == (None, 0.0)


# ── End to end ───────────────────────────────────────────────────────


def test_answer_asks_before_it_answers(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = answer(text="I need to get out of my lease early", include_draft=True)
    assert r["resolved"] is True
    assert r["situation"]["key"] == "lease_break"
    assert r["answer"] is None
    assert r["missing_required"]
    assert r["questions"]


def test_answer_confirmed_values_beat_read_values(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = answer(situation_key="lease_break", include_draft=True, values={
        "metro": "denver", "monthly_rent": 2400, "months_remaining": 8,
        "has_termination_clause": False, "replacement_tenant_ready": False,
        "lease_allows_transfer": "no", "move_out_reason": "job",
    })
    assert r["answer"] is not None
    assert r["answer_is_provisional"] is False
    assert r["blocked"] is None
    # Typed by hand, so it belongs in the quiet line, not the check list.
    confirmed = {f["key"]: f for f in r["reflection"]["confirmed"]}
    assert confirmed["monthly_rent"]["provenance"] == STATED
    assert r["reflection"]["check"] == [], (
        "nothing was guessed, so nothing should be put up for review")


def test_answer_reports_a_blocked_situation_rather_than_serving_it(monkeypatch):
    """A must-not-assert violation degrades the page; it never leaks."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Situations are frozen, which is the point — swap the registry entry
    # rather than mutating one.
    hostile = dataclasses.replace(
        registry.get("lease_break"),
        must_not_assert=(Rule(r".", "everything is forbidden, for the test"),),
    )
    monkeypatch.setitem(registry.SITUATIONS, "lease_break", hostile)
    r = answer(situation_key="lease_break", include_draft=True, values={
        "metro": "denver", "monthly_rent": 2400, "months_remaining": 8})
    assert r["answer"] is None
    assert r["blocked"] == "guard_tripped"


def test_unknown_situation_asks_rather_than_guessing(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = answer(text="what's a good recipe for risotto")
    assert r["resolved"] is False
    assert r["catalog"]


# ── Intake wire shape (stubbed client) ───────────────────────────────
# These cover our side of the call: the request we build and how we
# handle what comes back. What they cannot cover is whether the model
# actually obeys the quote-your-source instruction — that needs a live
# key and a sample of real messages. The _harvest tests above are the
# backstop for when it doesn't: an unquoted value is a guess regardless.


class _StubMessages:
    def __init__(self, payload, captured, stop_reason="end_turn"):
        self._payload = payload
        self._captured = captured
        self._stop_reason = stop_reason

    def create(self, **kwargs):
        self._captured.update(kwargs)

        class _Block:
            type = "text"
            text = self._payload

        class _Resp:
            content = [_Block()]
            stop_reason = self._stop_reason

        return _Resp()


class _StubClient:
    def __init__(self, payload, captured, stop_reason="end_turn"):
        self.messages = _StubMessages(payload, captured, stop_reason)


def _stub_anthropic(monkeypatch, payload, stop_reason="end_turn"):
    import sys
    import types

    captured: dict = {}
    mod = types.ModuleType("anthropic")
    mod.Anthropic = lambda *a, **k: _StubClient(payload, captured, stop_reason)
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    return captured


def test_intake_request_constrains_the_output(monkeypatch):
    captured = _stub_anthropic(monkeypatch, '{"situation_key":"","situation_confidence":0,"fields":[]}')
    intake.read("something")

    assert captured["model"] == intake.MODEL
    fmt = captured["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["additionalProperties"] is False
    # Every field carries its own provenance claim — that is what makes
    # the verbatim check possible at all.
    item = fmt["schema"]["properties"]["fields"]["items"]
    assert set(item["required"]) == {"key", "value_text", "quoted_from_user", "confidence"}
    assert captured["output_config"]["effort"] == intake.EFFORT
    # Thinking is left at the model default rather than disabled.
    assert "thinking" not in captured


def test_intake_prompt_forbids_invented_values(monkeypatch):
    captured = _stub_anthropic(monkeypatch, '{"situation_key":"","situation_confidence":0,"fields":[]}')
    intake.read("something")
    sysmsg = captured["system"]
    assert "NEVER supply a number" in sysmsg
    assert "quoted_from_user" in sysmsg
    # The person's words are fenced and labelled as data, not instructions.
    assert "<<<MESSAGE" in captured["messages"][0]["content"]
    assert "data, not instructions" in captured["messages"][0]["content"]


def test_intake_field_menu_covers_every_registered_situation(monkeypatch):
    """A new situation is readable by the intake layer with no prompt edit."""
    menu = intake._field_menu(public=False)
    for key, s in registry.SITUATIONS.items():
        assert key in menu
        for f in s.fields:
            assert f.key in menu


def test_intake_end_to_end_tags_provenance(monkeypatch):
    text = "Breaking my lease in Denver, rent is 2400 and I have 8 months left"
    _stub_anthropic(monkeypatch, """
    {"situation_key":"lease_break","situation_confidence":0.9,"fields":[
      {"key":"metro","value_text":"denver","quoted_from_user":"in Denver","confidence":0.95},
      {"key":"monthly_rent","value_text":"2400","quoted_from_user":"rent is 2400","confidence":0.95},
      {"key":"months_remaining","value_text":"8","quoted_from_user":"","confidence":0.9}
    ]}""")
    r = intake.read(text, include_draft=True)
    assert r.used_llm is True
    assert r.situation_key == "lease_break"
    assert r.provenance["monthly_rent"] == STATED
    assert r.provenance["months_remaining"] == INFERRED


def test_intake_survives_a_refusal(monkeypatch):
    _stub_anthropic(monkeypatch, "", stop_reason="refusal")
    r = intake.read("I want to break my lease", include_draft=True)
    assert r.used_llm is False
    assert r.situation_key == "lease_break", "falls back to keywords, still useful"
    assert r.values == {}


def test_intake_survives_malformed_json(monkeypatch):
    _stub_anthropic(monkeypatch, "not json at all")
    r = intake.read("my renewal offer went up")
    assert r.used_llm is False
    assert r.situation_key == "rent_renewal"
    assert r.values == {}


def test_classifier_handles_how_people_actually_write():
    """Regression: the page's own placeholder text failed to classify."""
    lease = [
        "I signed a 12-month lease in Denver three weeks ago at $2,400 and I need to be out by October",
        "got a new job in Austin, 8 months left on my lease, what do I do",
        "can I sublet my apartment",
        "I want out of my lease early",
        "landlord offered me a buyout to leave",
    ]
    # lease_break is not live yet, so the public classifier must not
    # route to it. public=False is the development path.
    for t in lease:
        assert registry.classify(t, public=False)[0] == "lease_break", t
        assert registry.classify(t)[0] != "lease_break", (
            f"a draft situation leaked to the public classifier: {t}")

    renewal = [
        "they're raising my rent from 1800 to 2100 on the renewal",
        "my lease is up and the renewal offer came in higher",
        "rent increase, should I sign",
    ]
    for t in renewal:
        assert registry.classify(t)[0] == "rent_renewal", t


def test_unclassified_text_still_offers_a_way_forward(monkeypatch):
    """`resolved: false` must always carry the catalog — never a dead end."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = answer(text="something completely unrelated to housing")
    assert r["resolved"] is False
    assert len(r["catalog"]) == len(registry.live())
    assert all(s["name"] and s["key"] for s in r["catalog"])


# ── The closing instruction ──────────────────────────────────────────


def test_every_answer_carries_a_next_step():
    """Regression: next_step lived in `context` and was never rendered.

    On the regulated renewal path it is the most important sentence on
    the page — it routes somebody to the legal question instead of the
    negotiation, which is worth more than any concession.
    """
    outs = {
        "renewal_denver": registry.get("rent_renewal").assess(
            {"metro": "denver", "current_rent": 1800, "offered_rent": 1950,
             "months_at_address": 30}),
        "renewal_nyc": registry.get("rent_renewal").assess(
            {"metro": "new_york", "current_rent": 3000, "offered_rent": 3300,
             "months_at_address": 30}),
        "lease_break": registry.get("lease_break").assess(
            {"metro": "denver", "monthly_rent": 2000, "months_remaining": 9.0,
             "has_termination_clause": None, "termination_fee_months": None,
             "replacement_tenant_ready": None, "lease_allows_transfer": "unknown",
             "move_out_reason": "other", "security_deposit": None,
             "credit_score": None}),
    }
    for name, o in outs.items():
        assert o.next_step, f"{name} has no closing instruction"
        assert o.to_dict()["next_step"] == o.next_step

    # The regulated path must route to the legal question, not the ask.
    assert "regulated" in outs["renewal_nyc"].next_step.lower()
    # The unregulated path leads with urgency (K25).
    assert "now rather than later" in outs["renewal_denver"].next_step


def test_next_step_is_covered_by_the_guard():
    s = registry.get("lease_break")
    with pytest.raises(MustNotAssert):
        guard.check(s, Outcome(verdict="strong", headline="Fine.",
                               next_step="You have the right to terminate."))


def test_guard_allows_the_conditional_framing():
    """Regression: "find out WHETHER your apartment is regulated" is the
    correct framing and an earlier rule read it as an assertion."""
    s = registry.get("rent_renewal")
    guard.check(s, Outcome(
        verdict="weak", headline="Fine.",
        next_step="Before you sign: find out whether your apartment is rent "
                  "regulated. If it is, the increase may be capped by law.",
    ))
    with pytest.raises(MustNotAssert):
        guard.check(s, Outcome(verdict="weak", headline="Fine.",
                               next_step="Your apartment is rent regulated."))


def test_the_never_ask_figure_reaches_the_reader():
    """Regression: the 61% stat sat in `context` and was never shown.

    It is what turns odds into a reason to act rather than a number.
    """
    o = registry.get("rent_renewal").assess(
        {"metro": "denver", "current_rent": 1800, "offered_rent": 1950,
         "months_at_address": 30})
    assert "61%" in o.odds_basis
    assert o.odds_basis.startswith(
        "You've been there 2+ years"), "the tenure basis must survive too"


# ── The crab-landlord lessons ────────────────────────────────────────
# writing/crab-landlord-article.md + writing/rent-no-source.md.


def test_buyout_anchor_stays_inside_the_sourced_envelope():
    """Regression, and it was a big one.

    The anchor used to be built from an invented 0.5 months re-letting
    plus up to 3.0 months vacancy — 3.5 months, against a surveyed
    1–2 months (NAA/IREM/BOMA, 4,666 properties). On a $2,400 Denver
    apartment that recommended opening at $8,400 when the landlord's
    real loss is nearer $4,800. It was the "1–3 months of rent" folk
    number the research exists to kill, re-derived by accident.
    """
    s = registry.get("lease_break")
    base = {"has_termination_clause": False, "termination_fee_months": None,
            "replacement_tenant_ready": False, "lease_allows_transfer": "no",
            "move_out_reason": "job", "security_deposit": None,
            "credit_score": None}
    for metro in ("denver", "new_york", "austin", "san_francisco", "nowhere_at_all"):
        for rent in (900, 1600, 2400, 5000):
            o = s.assess({**base, "metro": metro, "monthly_rent": rent,
                          "months_remaining": 9.0})
            loss = o.context["landlord_expected_loss_usd"]
            lo = evidence.TURN_COST_MONTHS_LOW * rent
            hi = evidence.TURN_COST_MONTHS_HIGH * rent
            assert lo <= loss <= hi, (
                f"{metro} @ ${rent}: anchor ${loss:,} outside the sourced "
                f"${lo:,.0f}-${hi:,.0f} envelope"
            )


def test_turn_cost_never_bills_past_the_end_of_the_term():
    s = registry.get("lease_break")
    o = s.assess({"metro": "denver", "monthly_rent": 2400, "months_remaining": 3.0,
                  "has_termination_clause": False, "termination_fee_months": None,
                  "replacement_tenant_ready": False, "lease_allows_transfer": "no",
                  "move_out_reason": "job", "security_deposit": None,
                  "credit_score": None})
    assert o.context["landlord_expected_loss_usd"] <= 3.0 * 2400


def test_the_message_asks_for_proof_not_a_claim():
    """"Be credible" is the action; asking is only how you deliver it.

    An unbacked "I need to move out" is free to say, so it carries no
    information and a landlord is right to ignore it. The message must
    make room for the checkable thing.
    """
    s = registry.get("lease_break")
    o = s.assess({"metro": "denver", "monthly_rent": 2400, "months_remaining": 9.0,
                  "has_termination_clause": False, "termination_fee_months": None,
                  "replacement_tenant_ready": False, "lease_allows_transfer": "no",
                  "move_out_reason": "job", "security_deposit": None,
                  "credit_score": None})
    assert o.message
    low = o.message.lower()
    assert "checkable" in low or "confirm" in low
    assert "might have to move" in low, "must name the claim that is worth nothing"
    assert "date" in low and "name" in low
    # ...and the closing instruction says to get it BEFORE sending.
    assert "before you send" in o.next_step.lower()


def test_renewal_carries_the_credible_alternative_note():
    """Regression: the adapter dropped `shopping_around` on the floor.

    It is the corrected version of advice that shipped backwards once
    already — a vague "I could move" is not the same object as a
    specific alternative that can be checked.
    """
    from vend.rent import advisor

    o = registry.get("rent_renewal").assess(
        {"metro": "denver", "current_rent": 1800, "offered_rent": 1950,
         "months_at_address": 30})
    assert advisor.SHOPPING_AROUND_NOTE in o.exposure
    assert "can be checked" in advisor.SHOPPING_AROUND_NOTE, (
        "the advisor's note has been reverted to the retracted version"
    )


def test_no_simulation_figure_is_quoted_to_the_reader():
    """All three of the sim's accuracy checks failed, so nothing on a
    page may be quoted from it. The 10.2% credible-signal effect is a
    real finding about the model, not a promise to a renter."""
    import re as _re

    for key in registry.SITUATIONS:
        s = registry.get(key)
        values = ({"metro": "denver", "current_rent": 1800, "offered_rent": 1950,
                   "months_at_address": 30} if key == "rent_renewal" else
                  {"metro": "denver", "monthly_rent": 2400, "months_remaining": 9.0,
                   "has_termination_clause": False, "termination_fee_months": None,
                   "replacement_tenant_ready": True, "lease_allows_transfer": "yes",
                   "move_out_reason": "job", "security_deposit": None,
                   "credit_score": None})
        o = s.assess(values)
        for where, text in guard.strings(o):
            low = text.lower()
            assert "crab" not in low, f"{key}:{where} quotes the sim"
            for fig in (r"10\.2\s?%",          # crab-landlord credible signal
                        r"\$?2,851", r"\$?6,528",  # molt verifiability inversion
                        r"\$?27,286", r"\$?12,993", r"91\.6\s?%"):
                assert not _re.search(fig, text), (
                    f"{key}:{where} quotes a simulation figure. The studies' "
                    f"accuracy checks failed; the advice ships, the numbers do not."
                )


def test_the_externality_is_disclosed_before_anyone_acts_on_the_advice():
    """The one result that survived the audit.

    This test previously required the disclosure ABOVE the input box,
    reading "in front of the tool" literally. That put a paragraph of
    hedging at somebody who had typed nothing and received nothing.
    The shipped rent.html renders the same disclosure inside its
    results, so the precedent is: with the advice, before they act on
    it — which is the moment that actually matters. Full content still
    required; only its position moved.
    """
    page = os.path.join(_HERE, "gametheory", "server", "static", "helper.html")
    with open(page, encoding="utf-8") as fh:
        html = fh.read()

    answer_at = html.index('<section id="answer"')
    edge_at = html.index('id="edge"')
    restart_at = html.index('id="restart"')
    assert answer_at < edge_at < restart_at, (
        "the catch belongs inside the answer, after the advice and before "
        "the way out"
    )
    for required in ("61%", "opening number for everyone", "stay quiet",
                     "having nothing"):
        assert required in html, f"disclosure lost {required!r}"


def test_the_proof_advice_carries_its_own_downside():
    """The molt study's inversion: proving your alternative helps you and
    would hurt renters collectively if it became standard, because silence
    then reads as having nothing. Same shape as the 61%, and the tool
    gives the proof advice, so it owes the caveat."""
    cases = {
        "rent_renewal": {"metro": "denver", "current_rent": 1800,
                         "offered_rent": 1950, "months_at_address": 30},
        "lease_break": {"metro": "denver", "monthly_rent": 2400,
                        "months_remaining": 9.0, "has_termination_clause": False,
                        "termination_fee_months": None,
                        "replacement_tenant_ready": False,
                        "lease_allows_transfer": "no", "move_out_reason": "job",
                        "security_deposit": None, "credit_score": None},
    }
    for key, values in cases.items():
        o = registry.get(key).assess(values)
        joined = " ".join(o.caveats).lower()
        assert "checkable" in joined or "check" in joined, key
        assert "reads as having nothing" in joined or \
               "read as having nothing" in joined, (
            f"{key} recommends proof without disclosing that normalising it "
            f"turns silence into evidence")


# ── Conformance: how situation #50 gets built safely ─────────────────


def test_every_registered_situation_is_well_formed():
    """The linter is the enforcement half of the authoring split.

    The model drafts, this checks, a human verifies the numbers. Any
    error here blocks registration — that is what makes a new situation
    a bounded piece of work rather than a specialist's whole afternoon.
    """
    from vend.situations import lint

    for key in registry.SITUATIONS:
        errs = lint.errors(registry.get(key))
        assert not errs, f"{key}:\n" + "\n".join(f"  {e}" for e in errs)


def test_lint_catches_a_horoscope():
    """A situation that can never say "do nothing" must not register."""
    from vend.situations import lint
    from vend.situations.schema import COUNT, Field, Outcome, Rule, Situation

    always_confident = Situation(
        key="horoscope", name="Horoscope", one_liner="Always finds leverage.",
        fields=(Field(key="n", label="A number", kind=COUNT, required=True,
                      sweep=(1, 5, 9)),),
        assess=lambda v: Outcome(verdict="strong", verdict_label="go",
                                 headline="You have leverage.",
                                 next_step="Ask.", caveats=["None."]),
        must_not_assert=(Rule(r"\bguaranteed\b", "no promises"),),
        triggers=("stars",),
    )
    checks = [f.check for f in lint.errors(always_confident)]
    assert "horoscope" in checks


def test_lint_catches_a_missing_rule_set():
    from vend.situations import lint
    from vend.situations.schema import COUNT, Field, Outcome, Situation

    unguarded = Situation(
        key="unguarded", name="Unguarded", one_liner="No rules.",
        fields=(Field(key="n", label="A number", kind=COUNT, required=True,
                      sweep=(1, 5)),),
        assess=lambda v: Outcome(verdict="weak", headline="Nothing to do.",
                                 next_step="Nothing.", caveats=["None."]),
    )
    assert "must_not_assert" in [f.check for f in lint.errors(unguarded)]


# ── Authoring: the model drafts, Python verifies it followed the rules ─


def test_author_refuses_a_draft_carrying_invented_numbers():
    """The rule the model is most likely to break, checked not trusted.

    A plausible figure written into a draft becomes a figure somebody
    acts on. This codebase's most expensive mistake was exactly that.
    """
    from vend.situations import author

    d = author.Draft(
        key="deposit_dispute", name="Deposit dispute",
        one_liner="Getting a security deposit back.",
        fields=[{"key": "amount", "label": "How much they kept", "kind": "money",
                 "required": True, "sweep": ["100", "500"],
                 "help": "Landlords typically keep 2 months of rent."}],
        must_not_assert=[{"pattern": r"\byou will win\b", "why": "no promises"}],
        verify_steps=[{"action": "Read your lease", "where": "Your lease", "note": ""}],
        evidence_needed=[{"question": "What share of deposits are disputed?",
                          "why_it_matters": "sets the odds", "possible_source": "?"}],
        weak_case="They kept nothing.", triggers=["deposit"],
    )
    problems = author.review(d)
    assert any("quantity" in p for p in problems), problems


def test_author_review_demands_the_parts_that_cannot_be_skipped():
    from vend.situations import author

    empty = author.Draft(key="x", name="X", one_liner="Y")
    problems = " ".join(author.review(empty))
    for required in ("must-not-assert", "verification steps", "evidence",
                     "weak case", "no fields"):
        assert required in problems, f"missing {required!r} in: {problems}"


def test_author_scaffold_refuses_to_write_the_judgment():
    """Judgment logic is the one thing a person has to own, because it
    is the thing they will later have to defend."""
    from vend.situations import author

    d = author.Draft(
        key="deposit_dispute", name="Deposit dispute", one_liner="Getting it back.",
        fields=[{"key": "amount", "label": "Amount", "kind": "money",
                 "required": True, "sweep": [100, 500]}],
        must_not_assert=[{"pattern": r"\byou will win\b", "why": "no promises"}],
        evidence_needed=[{"question": "How often do renters win?",
                          "why_it_matters": "odds", "possible_source": "court data"}],
        weak_case="They kept nothing.",
    )
    src = author.scaffold(d)
    assert "raise NotImplementedError" in src
    assert "NOT REGISTERED. NOT VERIFIED" in src
    assert "PUBLISHABLE = False" in src
    assert "VERIFY_BEFORE_LAUNCH" in src
    assert "How often do renters win?" in src
    compile(src, "<scaffold>", "exec")   # it must at least be valid Python


def test_author_cannot_register_anything():
    """A draft is a starting point for a human, not a shortcut past one."""
    from vend.situations import author

    before = set(registry.SITUATIONS)
    d = author.Draft(key="deposit_dispute", name="X", one_liner="Y")
    author.review(d)
    author.scaffold(d)
    assert set(registry.SITUATIONS) == before
    assert d.to_dict()["registered"] is False
    assert d.to_dict()["verified"] is False


def test_author_degrades_without_a_key(monkeypatch):
    from vend.situations import author

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = author.draft("helping someone dispute a deposit deduction")
    assert d.used_llm is False
    assert d.problems and "No API key" in d.problems[0]
    assert not d.fields, "nothing is invented when there is no model"


# ── Jobs pass ────────────────────────────────────────────────────────


def test_verdicts_read_like_something_a_person_would_say():
    """Nobody has ever felt "moderate" about their rent."""
    for key, values in (
        ("rent_renewal", {"metro": "denver", "current_rent": 1800,
                          "offered_rent": 1950, "months_at_address": 30}),
        ("lease_break", {"metro": "new_york", "monthly_rent": 3400,
                         "months_remaining": 1.5, "has_termination_clause": None,
                         "termination_fee_months": None,
                         "replacement_tenant_ready": None,
                         "lease_allows_transfer": "unknown",
                         "move_out_reason": "other", "security_deposit": None,
                         "credit_score": None}),
    ):
        o = registry.get(key).assess(values)
        assert o.verdict_label and o.verdict_label != o.verdict
        assert o.to_dict()["verdict_label"] == o.verdict_label


# ── Telemetry: anonymity enforced at a choke point ───────────────────

# Distinctive strings planted in every field a caller could reach. If any
# survives redaction, the anonymity claim is false and the test says so.
_PII = {
    "name": "Ada Kelpline",
    "email": "ada@example.com",
    "phone": "+1-555-0132",
    "address": "42 Wharf Road, Apt 3B, Brooklyn NY 11222",
    "ssn": "123-45-6789",
    "landlord": "Bob Stationmaster",
    "story": "I live at 42 Wharf Road and my landlord Bob keeps calling me",
}


def _leaks(blob: str) -> list[str]:
    return [k for k, v in _PII.items() if v.lower() in blob.lower()]


def test_redact_is_an_allowlist_not_a_filter():
    """A field nobody deliberately added is absent, not sanitised.

    That is the property that makes adding a field to a situation safe:
    the failure mode is losing data, never leaking it.
    """
    from vend.situations import telemetry

    rec = telemetry.redact(
        situation_key="lease_break",
        values={
            "metro": "new_york", "monthly_rent": 3400, "months_remaining": 11,
            # everything below is NOT in FIELD_BUCKETS
            "tenant_name": _PII["name"], "email": _PII["email"],
            "street_address": _PII["address"], "ssn": _PII["ssn"],
            "landlord_name": _PII["landlord"], "notes": _PII["story"],
        },
        provenance={"metro": STATED, "monthly_rent": STATED},
        verdict="moderate", asked=["replacement_tenant_ready"],
        route_offered="surrender", used_llm=True,
    )
    blob = json.dumps(rec)
    assert not _leaks(blob), f"leaked {_leaks(blob)}: {blob}"
    assert set(rec) <= telemetry.RECORD_KEYS
    assert set(rec["inputs"]) <= set(telemetry.FIELD_BUCKETS) | {"increase_pct"}


def test_no_exact_figure_survives():
    """An exact rent plus a metro plus a lease length is close to a
    fingerprint. A band is not."""
    from vend.situations import telemetry

    rec = telemetry.redact(
        situation_key="rent_renewal",
        values={"metro": "denver", "current_rent": 1837, "offered_rent": 1993,
                "months_at_address": 31},
        provenance={}, verdict="strong", asked=[],
        route_offered="concession_parity", used_llm=False,
    )
    # Scan everything except the receipt: it is 16 random hex characters,
    # so it contains any given short digit run often enough to make this
    # test flaky for a reason that has nothing to do with privacy.
    blob = json.dumps({k: v for k, v in rec.items() if k != "receipt"})
    for exact in ("1837", "1993", "31"):
        assert exact not in blob, f"exact value {exact} survived: {blob}"
    assert rec["inputs"]["current_rent"] == "1500_1999"
    assert rec["inputs"]["increase_pct"] == "8_15"
    assert rec["inputs"]["months_at_address"] == "24_48"


def test_the_description_cannot_be_recorded_by_accident():
    """The largest PII risk is handled structurally: free text is not a
    parameter of redact(), so it cannot be written even by mistake."""
    import inspect

    from vend.situations import telemetry

    params = set(inspect.signature(telemetry.redact).parameters)
    for forbidden in ("text", "description", "message", "request", "ip",
                      "user_agent", "session"):
        assert forbidden not in params, (
            f"redact() accepts {forbidden!r} — unsafe data must be "
            f"structurally unavailable, not filtered")


def test_timestamps_are_never_finer_than_a_month():
    """Day granularity was the weakest link: a rare band combination plus
    a specific date is close to a singleton even when every field is
    coarse — "the one person in Buffalo who used this on a Tuesday"."""
    from vend.situations import telemetry

    rec = telemetry.redact(situation_key="lease_break", values={},
                           provenance={}, verdict="weak", asked=[],
                           route_offered=None, used_llm=False)
    assert re.fullmatch(r"\d{4}-\d{2}", rec["month"])
    assert "day" not in rec
    blob = json.dumps(rec)
    assert not re.search(r"\d{2}:\d{2}", blob), "no clock time anywhere"
    assert not re.search(r"\d{4}-\d{2}-\d{2}", blob), "no date finer than month"


def test_unknown_choice_values_are_dropped_not_guessed():
    from vend.situations import telemetry

    rec = telemetry.redact(
        situation_key="lease_break",
        values={"move_out_reason": "my landlord is Bob at 42 Wharf Road",
                "lease_allows_transfer": "yes"},
        provenance={}, verdict="weak", asked=[], route_offered=None,
        used_llm=False)
    assert "move_out_reason" not in rec["inputs"]
    assert rec["inputs"]["lease_allows_transfer"] == "yes"


def test_outcome_reports_reject_free_text():
    """"other" with no detail is worth more than a text field somebody
    types their address into."""
    from vend.situations import telemetry

    assert telemetry.redact_outcome("a1b2c3d4e5f6", "concession", 1200) is not None
    assert telemetry.redact_outcome("a1b2c3d4e5f6", _PII["story"]) is None
    assert telemetry.redact_outcome("", "concession") is None
    assert telemetry.redact_outcome("short", "concession") is None
    got = telemetry.redact_outcome("a1b2c3d4e5f6" + _PII["ssn"], "refused")
    assert not _leaks(json.dumps(got))
    assert got["amount"] is None


def test_receipts_do_not_link_two_sessions():
    from vend.situations import telemetry

    same = dict(situation_key="lease_break", values={"metro": "denver"},
                provenance={}, verdict="weak", asked=[], route_offered=None,
                used_llm=False)
    a, b = telemetry.redact(**same), telemetry.redact(**same)
    assert a["receipt"] != b["receipt"], (
        "identical inputs must not produce a stable identifier")


def test_telemetry_is_off_by_default(monkeypatch, tmp_path):
    from vend.situations import telemetry

    monkeypatch.delenv("SNHP_HELPER_TELEMETRY", raising=False)
    monkeypatch.setenv("SNHP_DATA_DIR", str(tmp_path))
    assert telemetry.enabled() is False
    rec = telemetry.redact(situation_key="lease_break", values={},
                           provenance={}, verdict="weak", asked=[],
                           route_offered=None, used_llm=False)
    assert telemetry.write(rec) is False
    assert not list(tmp_path.glob("*.jsonl"))


def test_write_refuses_a_record_with_stray_keys(monkeypatch, tmp_path):
    """The check that makes adding a situation field safe."""
    from vend.situations import telemetry

    monkeypatch.setenv("SNHP_HELPER_TELEMETRY", "1")
    monkeypatch.setenv("SNHP_DATA_DIR", str(tmp_path))
    rec = telemetry.redact(situation_key="lease_break", values={},
                           provenance={}, verdict="weak", asked=[],
                           route_offered=None, used_llm=False)
    assert telemetry.write(rec) is True
    assert telemetry.write({**rec, "tenant_email": _PII["email"]}) is False
    written = (tmp_path / "helper_telemetry.jsonl").read_text()
    assert not _leaks(written)
    assert len(written.strip().splitlines()) == 1


def test_disclosure_names_what_is_not_kept():
    """A disclosure that only says what is collected is marketing."""
    from vend.situations import telemetry

    d = telemetry.DISCLOSURE.lower()
    for promise in ("never your description", "never an exact rent",
                    "never your address", "never your ip", "no account",
                    "no cookie"):
        assert promise in d, f"disclosure omits {promise!r}"


def test_the_opt_out_is_honoured_before_anything_is_built():
    """Not before it is written — before the record exists at all."""
    import inspect

    from gametheory.server import http as _http

    src = inspect.getsource(_http.helper_ask)
    build_at = src.index("_helper_telemetry.redact(")
    guard_at = src.index("body.no_telemetry")
    assert guard_at < build_at, (
        "the opt-out must gate construction, not just the write")


def test_no_page_promises_that_nothing_is_stored():
    """FTC §5: saying "nothing is stored" while storing something is a
    deceptive practice, and it does not matter how anonymous the stored
    thing is. /rent genuinely stores nothing and may keep saying so;
    /helper may not."""
    page = os.path.join(_HERE, "gametheory", "server", "static", "helper.html")
    with open(page, encoding="utf-8") as fh:
        html = fh.read().lower()
    for lie in ("nothing stored", "nothing is stored", "we store nothing",
                "we don't store anything"):
        assert lie not in html, f"helper page still claims {lie!r}"

    readme = os.path.join(_HERE, "vend", "situations", "README.md")
    with open(readme, encoding="utf-8") as fh:
        assert "nothing stored" not in fh.read().lower()


def test_the_privacy_promise_is_served_from_the_redacting_module():
    """A promise in hand-written page copy drifts from the code. This one
    is generated by the module that performs the redaction."""
    from gametheory.server import http as _http
    from vend.situations import telemetry

    p = _http.helper_privacy()
    assert p["disclosure"] == telemetry.DISCLOSURE
    assert p["commitment"] == telemetry.COMMITMENT
    assert set(p["stored"]) == telemetry.RECORD_KEYS
    assert set(p["bucketed_fields"]) == set(telemetry.FIELD_BUCKETS)
    # The CPRA deidentification test needs a public commitment covering
    # all three: no reidentification, no sale, no combining.
    c = p["commitment"].lower()
    assert "reidentify" in c and "sell" in c and "combine" in c


def test_not_legal_advice_is_on_the_page_not_only_inside_an_answer():
    page = os.path.join(_HERE, "gametheory", "server", "static", "helper.html")
    with open(page, encoding="utf-8") as fh:
        html = fh.read()
    assert 'id="notadvice"' in html
    from vend.situations import telemetry
    n = telemetry.NOT_ADVICE.lower()
    assert "not legal" in n and "does not create" in n


def test_outcome_endpoint_refuses_free_text():
    from fastapi.testclient import TestClient

    from gametheory.server.http import app

    c = TestClient(app)
    bad = c.post("/v1/helper/outcome", json={
        "receipt": "a1b2c3d4e5f6",
        "outcome": "they said no but my landlord Bob at 42 Wharf Road called"})
    assert bad.status_code == 422
    ok = c.post("/v1/helper/outcome",
                json={"receipt": "a1b2c3d4e5f6", "outcome": "concession"})
    assert ok.status_code == 200


def test_derived_values_are_not_laundered_into_stated():
    """Found on the first live run against the real model.

    The model quoted the span it reasoned FROM — "I signed a 12-month
    lease three weeks ago" — in support of months_remaining=11. The
    quote was genuine, so the verbatim check passed and a derived number
    was marked "you said" and treated as firm. Eleven is a correct
    inference and it is not something the person said.

    A wrong INFERRED costs one extra question. A wrong STATED costs
    somebody a decision they never agreed to.
    """
    s = registry.get("lease_break")
    text = ("I signed a 12-month lease in Brooklyn three weeks ago at $3,400 "
            "a month and I need to be out by October. I have not found "
            "anyone to take over.")
    items = [
        {"key": "monthly_rent", "value_text": "3400",
         "quoted_from_user": "$3,400 a month", "confidence": 0.98},
        {"key": "months_remaining", "value_text": "11",
         "quoted_from_user": "I signed a 12-month lease in Brooklyn three weeks ago",
         "confidence": 0.9},
        {"key": "metro", "value_text": "New York",
         "quoted_from_user": "Brooklyn", "confidence": 0.95},
    ]
    _, prov, conf, _ = intake._harvest(s, items, text)

    # The value really is inside the quote, punctuation aside.
    assert prov["monthly_rent"] == STATED
    # Arithmetic on what they said is not what they said.
    assert prov["months_remaining"] == INFERRED
    # Nor is a lookup: "New York" does not appear in "Brooklyn".
    assert prov["metro"] == INFERRED
    assert conf["months_remaining"] <= 0.6


def test_value_in_quote_is_punctuation_insensitive_but_not_generous():
    assert intake._value_in_quote("3400", "$3,400 a month")
    assert intake._value_in_quote("yes", "Yes, with consent")
    assert not intake._value_in_quote("11", "a 12-month lease three weeks ago")
    assert not intake._value_in_quote("New York", "Brooklyn")
    assert not intake._value_in_quote("false", "I have not found anyone")
    assert not intake._value_in_quote("", "anything")


# ── The live gate ────────────────────────────────────────────────────


def test_only_sourced_situations_reach_the_public():
    """Without this the registry is all-or-nothing, and shipping the
    finished renewal advisor would mean shipping unfinished lease-break
    alongside it."""
    from vend.situations.lease_break import evidence

    assert registry.get("rent_renewal").live is True
    assert registry.get("lease_break").live is False
    assert evidence.PUBLISHABLE is False, (
        "a situation may only go live once its evidence is sourced")

    assert [c["key"] for c in registry.catalog()] == ["rent_renewal"]
    assert registry.get("lease_break", public=True) is None
    assert registry.get("lease_break") is not None, "still reachable in dev"


def test_a_draft_situation_cannot_be_reached_by_naming_it():
    """The obvious bypass: skip the classifier and ask for it directly."""
    r = answer(situation_key="lease_break", values={
        "metro": "denver", "monthly_rent": 2400, "months_remaining": 8})
    assert r["resolved"] is False
    assert "lease_break" not in [c["key"] for c in r["catalog"]]


def test_the_public_intake_menu_omits_drafts():
    """The model cannot classify into a situation it was never shown."""
    menu = intake._field_menu()
    assert "rent_renewal" in menu
    assert "lease_break" not in menu
    assert "months_remaining" not in menu


# ── The reflection panel, after the redesign ─────────────────────────


def test_nothing_is_put_up_for_review_when_nothing_was_guessed():
    """The panel used to show every resolved prior as a row with a
    colour-coded provenance badge and a legend to decode it — seven rows
    of homework, most of them things the person typed thirty seconds
    earlier. Showing somebody their own answer back is noise, not trust.
    """
    s = registry.get("rent_renewal")
    p = priors.resolve(s, stated={"metro": "denver", "current_rent": 1800,
                                  "offered_rent": 1950, "months_at_address": 30})
    rf = ux.build(s, p, s.assess(p.values))["reflection"]
    assert rf["check"] == []
    assert rf["check_intro"] == ""
    assert rf["confirmed_summary"], "still shown, but as one line"
    assert len(rf["confirmed"]) == 4


def test_only_guesses_are_put_up_for_review():
    """What earns the person's attention is the narrow set we worked out
    rather than read."""
    s = registry.get("rent_renewal")
    p = priors.resolve(
        s,
        stated={"metro": "denver", "current_rent": 1800,
                "offered_rent": 1950, "months_at_address": 30},
        provenance={"months_at_address": INFERRED, "metro": INFERRED},
    )
    rf = ux.build(s, p, s.assess(p.values))["reflection"]
    assert {f["key"] for f in rf["check"]} == {"months_at_address", "metro"}
    assert {f["key"] for f in rf["confirmed"]} == {"current_rent", "offered_rent"}
    assert rf["check_intro"]


def test_defaults_are_disclosed_in_the_quiet_line_not_hidden():
    """Assumed values are firm enough not to interrupt, and not so firm
    that they go unmentioned.

    Neither situation currently produces a surviving default — every
    defaulted field clears the threshold and gets asked instead — so this
    exercises the mechanism directly rather than contorting a scenario
    into existence. If a future situation does default something the
    engine judges irrelevant, this is the behaviour it gets.
    """
    from vend.situations.schema import ASSUMED

    s = registry.get("lease_break")
    p = priors.resolve(s, stated={
        "metro": "denver", "monthly_rent": 2400, "months_remaining": 9.0,
        "has_termination_clause": False, "replacement_tenant_ready": True,
        "lease_allows_transfer": "yes", "move_out_reason": "job",
        "security_deposit": 2000})
    p.provenance["security_deposit"] = ASSUMED

    rf = ux.build(s, p, s.assess(p.values))["reflection"]
    assumed = [f for f in rf["confirmed"] if f["provenance"] == ASSUMED]
    assert assumed, "a surviving default must still appear"
    assert "default" in rf["confirmed_summary"].lower()
    assert not [f for f in rf["check"] if f["provenance"] == ASSUMED], (
        "a default the engine judged irrelevant must not be put up for review")


def test_the_provenance_legend_is_gone_from_the_page():
    """With only guesses shown prominently there is nothing to decode."""
    page = os.path.join(_HERE, "gametheory", "server", "static", "helper.html")
    with open(page, encoding="utf-8") as fh:
        html = fh.read()
    assert 'class="prov-key"' not in html
    assert "prov-stated" not in html and "prov-market" not in html
    assert 'id="said-toggle"' in html, "the quiet line must still be openable"
