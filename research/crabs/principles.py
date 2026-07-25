"""Machine-checkable enforcement of research/DESIGN-PRINCIPLES.md.

The principles were derived from seven artefacts this study produced, five of
which pre-registration did not catch because pre-registration constrains what
you CLAIM, not what you BUILD. These are the parts that can be checked by a
machine rather than by remembering.

    A. one knob            `assert_one_knob` -- two compared arms may differ in
                           exactly the declared dimension(s), and the descriptor
                           covers the DERIVED structure (round count, move
                           order, action-grid reach), not only `Params`.
    B. information budget  `information_leaks` -- transitive-closure scan of an
                           agent's decision path for symbols outside its
                           declared observation set. Generalises
                           `test_renewal_offer_uses_no_private_tenant_draw`,
                           which was one hand-written instance of this.
    C. no finding in a     `PARAM_SOURCES` -- every constant carries a source
       parameter           class; CIRCULAR is a hard failure, INVENTED must be
                           labelled in code and in every result table.
    D. identical           `conditional_statistics` -- parses the reporting
       populations         layer, classifies every ratio by whether its
                           DENOMINATOR is conditioned on an outcome, and demands
                           a declared unconditional counterpart.

What is deliberately NOT here: E (assume artefact) and F (the prose is a
detector) are postures, not predicates. They cannot be mechanised and pretending
otherwise would be worse than leaving them to people.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

# =============================================================================
# A. ONE KNOB
# =============================================================================

class OneKnobViolation(AssertionError):
    """Raised when two compared arms differ in more than the declared knob."""


def diff_arms(a: dict, b: dict) -> dict:
    """Every key on which two arm descriptors disagree -> (a_value, b_value)."""
    out = {}
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k, "<absent>"), b.get(k, "<absent>")
        if va != vb:
            out[k] = (va, vb)
    return out


def assert_one_knob(a: dict, b: dict, declared, label: str = "") -> None:
    """PRINCIPLE A. `declared` is the treatment: the dimension(s) the comparison
    is ABOUT. Anything else that differs is a confound, and a confound wearing
    the treatment's label is how K16 reported "who holds the engine" while also
    varying the optimiser, the move order and the action grid."""
    declared = {declared} if isinstance(declared, str) else set(declared)
    extra = {k: v for k, v in diff_arms(a, b).items() if k not in declared}
    if extra:
        lines = "\n".join(f"    {k}: {v[0]!r} vs {v[1]!r}"
                          for k, v in sorted(extra.items()))
        raise OneKnobViolation(
            f"{label or 'arms'} declare treatment {sorted(declared)} but also "
            f"differ in {len(extra)} undeclared dimension(s):\n{lines}")


# Fields of `Params` that describe the world rather than an arm. Two arms may
# differ here only because the RUNNER varies them deliberately (the regime, the
# sensitivity sweeps), so they are still surfaced -- never silently dropped.
def params_descriptor(params, **runner) -> dict:
    """An arm as data: every field of `Params` plus the runner-level knobs that
    `Params` does not carry (asker share, crab strategy, adaptive station)."""
    d = {f"params.{k}": v for k, v in sorted(params.__dict__.items())}
    d.update({f"runner.{k}": v for k, v in sorted(runner.items())})
    return d


def matrix_arm_descriptor(tenant_engine: bool, landlord_engine: bool) -> dict:
    """AMENDMENT 4's 2x2 as data.

    `Params` alone would say these four cells differ in exactly two booleans,
    which is precisely the illusion that let K16's 8.5x be read as "who holds
    the engine". The descriptor therefore reports the STRUCTURE each boolean
    switches on, read off `armk.negotiate_matrix` rather than restated by hand:
    which optimiser each side gets, how many rounds it gets, who moves first,
    and how far up the rent grid each side may reach."""
    from crabs import armk
    from crabs.engine_bridge import (N_ROUNDS, N_TENANT_RENT, RENT_FACTORS,
                                     THEIR_BATNA_ESTIMATE)

    # the round count is a FUNCTION of tenant_engine in negotiate_matrix
    rounds = min(N_ROUNDS, armk.HEUR_ROUNDS if not tenant_engine else N_ROUNDS)
    # the landlord may open only when it holds the engine; the tenant never has
    # an opener in any cell (there is no `tenant_opener`)
    l_opens = bool(landlord_engine)
    l_reach = (max(RENT_FACTORS[b.ri] for b in armk.LANDLORD_OPENERS)
               if landlord_engine else RENT_FACTORS[0])
    t_reach = min(RENT_FACTORS[:N_TENANT_RENT])
    return {
        "tenant_engine": bool(tenant_engine),
        "landlord_engine": bool(landlord_engine),
        "tenant_optimiser": "negotiate_bundle" if tenant_engine
                            else "anchor_and_satisfice",
        "landlord_optimiser": "negotiate_bundle" if landlord_engine
                              else "budget_satisfice",
        "landlord_opener": "brute_force_bundle_npv_search" if landlord_engine
                           else "none",
        "rounds": rounds,
        "who_moves_first": "landlord" if l_opens else "tenant",
        "resets_status_quo": l_opens,
        "landlord_rent_grid_max_factor": l_reach,
        "tenant_rent_grid_min_factor": t_reach,
        "tenant_their_batna_estimate": THEIR_BATNA_ESTIMATE
                                       if tenant_engine else None,
        "landlord_their_batna_estimate": 0.45 if landlord_engine else None,
        "reads_tenant_private_utility": bool(landlord_engine),
    }


# =============================================================================
# B. INFORMATION BUDGET
# =============================================================================

# Attribute names that are a PER-TENANT PRIVATE DRAW. Matched as attribute
# accesses (`obj.attr`) so that a local variable of the same name is not a
# false positive. A landlord decision path that reaches any of these is pricing
# off something no landlord can observe -- artefact #2's exact shape.
PRIVATE_TENANT_FIELDS = frozenset({
    "c_persist",     # this crab's switching-cost draw (world.Crab)
    "move_cost",     # this tenant's moving cost in dollars (demographics)
    "job_flex",      # job flexibility -> how much a term lock costs it
    "income",        # income -> its CRRA curvature over the rent
    "burdened",      # derived from income, but still a private draw
    "hh_size",
    "w",             # the Dirichlet priority weights over the four issues
    "courage",       # arm F: this crab's private cost of asking
    "belief",        # arm F: its private subjective P(concession | ask)
    "wealth",        # shock state: its private tolerance for above-market rent
})

# Function names that RETURN a private draw, so calling one is a leak even
# though no forbidden attribute appears in the caller's own source.
PRIVATE_TENANT_CALLS = frozenset({
    "_c_total",              # total realised switching cost of THIS crab
    "draw_tenant",           # materialises the private demographic draw
    "welfare_premium",       # weights dollars by ten.w
    "tenant_batna_normalised",   # built from ten.income and c_tot
    "build_issues",          # the tenant's own utility vectors
})

# What the station legitimately observes: SPEC §5 and PREREG §1. Everything the
# station is allowed to price off is a population object or something it wrote
# down itself.
STATION_OBSERVATION_SET = (
    "market rent M_t", "the rent of record r it charges", "tenure j",
    "payment history (q_sit)", "this habitat's own make-ready and vacancy "
    "exposure (tmul, vmul)", "the POPULATION switching-cost distribution",
    "the lease dates it wrote and elapsed time since its own offer",
    "whatever the tenant has actually asked for",
)

_SRC_CACHE: dict = {}


def _module_of(fn):
    return inspect.getmodule(fn)


def _resolve(name, mod):
    """A called name -> the function object, if it lives in the crabs package."""
    obj = getattr(mod, name, None)
    if obj is None:
        return None
    if not (inspect.isfunction(obj) or inspect.ismethod(obj)):
        return None
    m = _module_of(obj)
    if m is None or not (m.__name__.startswith("crabs")
                         or m.__name__ == "crabs"):
        return None
    return obj


def _scan(fn, depth, seen, slice_from=None, slice_to=None):
    """(private attributes touched, private calls made) over the transitive
    closure of `fn`, following only calls into the crabs package."""
    key = (getattr(fn, "__qualname__", str(fn)), slice_from, slice_to)
    if key in seen or depth < 0:
        return set(), set()
    seen.add(key)
    try:
        src = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):                          # pragma: no cover
        return set(), set()
    if slice_from is not None:
        src = src[src.index(slice_from):]
    if slice_to is not None:
        src = src[:src.index(slice_to)]
        src = textwrap.dedent(src)
    attrs, called = _symbols(src)
    calls = {c for c in called if c in PRIVATE_TENANT_CALLS}
    mod = _module_of(fn)
    for nm in sorted(called):
        sub = _resolve(nm, mod) if mod is not None else None
        if sub is None:
            continue
        sa, sc = _scan(sub, depth - 1, seen)
        attrs |= {f"{nm}() -> {x}" for x in sa}
        calls |= {f"{nm}() -> {x}" for x in sc}
    return attrs, calls


_ATTR_RE = None
_CALL_RE = None


def _symbols(src: str):
    """(private attributes touched, names called) in one block of source.

    Prefers the AST. A SLICE of a function -- the renewal-offer block of a long
    simulation loop, say -- is not a parseable unit on its own, so the fallback
    is lexical. Lexical is the weaker tool and it is only ever the fallback,
    but for this purpose it errs toward reporting MORE, which is the safe
    direction for a check whose failure mode is a missed leak."""
    global _ATTR_RE, _CALL_RE
    tree = None
    for candidate in (src, "if True:\n" + textwrap.indent(src, "    ")):
        try:
            tree = ast.parse(candidate)
            break
        except (SyntaxError, IndentationError, ValueError):
            continue
    if tree is not None:
        attrs, called = set(), set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute)
                    and node.attr in PRIVATE_TENANT_FIELDS):
                attrs.add(f"{getattr(node.value, 'id', '?')}.{node.attr}")
            elif isinstance(node, ast.Call):
                nm = (node.func.id if isinstance(node.func, ast.Name)
                      else node.func.attr if isinstance(node.func, ast.Attribute)
                      else None)
                if nm:
                    called.add(nm)
        return attrs, called
    import re
    if _ATTR_RE is None:
        _ATTR_RE = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*)\.([A-Za-z_]\w*)")
        _CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
    attrs = {f"{a}.{b}" for a, b in _ATTR_RE.findall(src)
             if b in PRIVATE_TENANT_FIELDS}
    return attrs, set(_CALL_RE.findall(src))


def information_leaks(fn, depth: int = 4, slice_from=None, slice_to=None):
    """PRINCIPLE B, reusable. Returns the sorted list of private-tenant symbols
    an agent decision path can reach, directly or through any call it makes into
    the crabs package.

    `slice_from` / `slice_to` narrow the scan to one block of a long function
    (the renewal-offer block of `simulate_market`, say), so the check applies to
    a DECISION rather than to a whole simulation loop."""
    attrs, calls = _scan(fn, depth, set(), slice_from, slice_to)
    return sorted(attrs | calls)


def assert_information_budget(fn, allowed=(), depth: int = 4,
                              slice_from=None, slice_to=None, label="") -> None:
    """Fails if the decision path reaches a private tenant draw that is not in
    the explicitly `allowed` set for this agent."""
    leaks = [x for x in information_leaks(fn, depth, slice_from, slice_to)
             if x not in set(allowed)]
    if leaks:
        raise AssertionError(
            f"{label or getattr(fn, '__qualname__', fn)} reads private tenant "
            f"state outside its declared observation set:\n  "
            + "\n  ".join(leaks)
            + f"\n\ndeclared observation set: {STATION_OBSERVATION_SET}")


# =============================================================================
# C. NO PARAMETER MAY ENCODE A FINDING
# =============================================================================

# Source class for every constant. Binding meaning:
#   UPSTREAM  traceable to a published number that is NOT the phenomenon under
#             study (a cost, a survey, an index)
#   DERIVED   computed from other declared parameters, never set by hand
#   INVENTED  our choice, no published counterpart -- legal, but must be
#             labelled INVENTED in code AND in every result table
#   CALIBRATED  set so the model reproduces an observed fact; that fact may then
#             never be claimed as a prediction
#   SCOPED    traceable to a published number, but installed on the OTHER SIDE
#             of the phenomenon it describes. Legitimate for the claims its own
#             side supports and circular for the rest, so the entry must say
#             which is which. Added 2026-07-25 for `ask_frac`, where a flat
#             relabel either way would have been wrong.
#   CIRCULAR  its justification IS the phenomenon under study. Always a defect.
UPSTREAM, DERIVED, INVENTED, CALIBRATED, SCOPED, CIRCULAR = (
    "UPSTREAM", "DERIVED", "INVENTED", "CALIBRATED", "SCOPED", "CIRCULAR")

# AMENDMENT 11, appended to BOTH halves of the counter-rate loop because it is a
# fact about the pair and not about either one.
AND_ONE_KNOB = (
    " AMENDMENT 11: `courage_med` and `belief0` are ONE degree of freedom "
    "under two names. `world._set_endogenous_askers` asks iff "
    "belief x ask_scale x ask_frac x 12q > courage, so only the RATIO "
    "belief0/courage_med enters; holding it fixed and moving both ends over a "
    "20x range moves the counter rate by 0.7% relative. The ratio spans counter "
    "rates 0.0003 to 1.0000, so the model does not identify it at all -- which "
    "means arm F never measured the courage problem, it restated an input. "
    "K32 FIRED: at the sourced ratio (uninformative prior over one hour of the "
    "ACS renter wage) the counter rate is 99.96%. Reproducing the observed 39% "
    "needs the cost of sending one email to be 27-55 hours of that wage. "
    "See COURAGE_MED_1H and RESULTS-A11 §4.")


# Every constant in SPEC.md §4-§7 and SPEC-A2.md §A2-2, with the class its own
# stated basis earns it. Audited 2026-07-25 under AMENDMENT 7.
#
# SECOND PASS, same day, after DESIGN-PRINCIPLES gained Principle G. The first
# pass had two failure modes and both are closed here:
#
#   1. MISCLASSIFICATION. Four entries cited a real published number that is one
#      of this model's OWN validation targets. Read parameter-by-parameter that
#      looks like data; read output-by-output it is a loop. `vacancy`,
#      `p_exo_floor`, `p_exo_extra` and `belief0` move to CIRCULAR; `ask_frac`
#      moves to SCOPED. See `research/crabs/FREE-OUTPUTS.md` for the
#      output-by-output view, which is the one that makes these visible.
#   2. COVERAGE. The table stopped at SPEC §4-§7 and SPEC-A2, so the ~20
#      module constants and 15 `MarketParams` fields that AMENDMENTS 5/5a/6/6a/8
#      added -- everything K22 through K27 actually runs on -- were in no table
#      at all. They are below, under `market.py`.
PARAM_SOURCES = {
    # --- market process (SPEC §3) ---
    "drift": (UPSTREAM, "2021-22 asking-rent growth +11-15% (loss, we use +9%); "
                        "MAA new-lease FY2024 -5.9%/FY2025 -5.8% (gain)"),
    "sigma_burn": (INVENTED, "no stated source"),
    "sigma_meas": (INVENTED, "no stated source"),
    "burn_years": (INVENTED, "no stated source"),
    "meas_years": (UPSTREAM, "PREREG §3 requires >=200 station-years: Params' "
                             "4 x 60 stations = 240, MarketParams' 10 x 40 "
                             "= 400. One entry, two dataclasses -- the table is "
                             "keyed by name and both values answer to the same "
                             "requirement."),
    "g_long": (UPSTREAM, "underwriting practice: long-run terminal growth"),
    # --- station cost side (SPEC §5) ---
    "turn_cost": (UPSTREAM, "NAA/IREM/BOMA triangulation, 1-2 months"),
    "vacancy": (CIRCULAR, "SPEC §5: 'soft markets relet slower; 39.7% of 2026 "
                          "listings carried a concession vs ~1 in 6 "
                          "pre-pandemic.' THE CONCESSION RATE IS THE "
                          "VALIDATION TARGET -- V6 (institutional concession "
                          "rate 15-35%, RealPage ~2026) and V5, and SPEC-A2 "
                          "§A2-3 says V6 'is close to the same quantity Phase "
                          "1's V1 already failed'. And `vacancy` is not "
                          "incidental to it: it enters `StationDP._turn_val`, "
                          "the value of LETTING THE CRAB GO, which is the "
                          "counterfactual every concession is judged against. "
                          "So the observed concession rate sets the parameter "
                          "that sets the modelled concession rate. Filed "
                          "UPSTREAM in the first pass because the cited number "
                          "is real and published; the source was never the "
                          "problem. PRINCIPLE G."),
    "q_new": (UPSTREAM, "~1.5% of annual rent, NAA bad-debt expense line"),
    "q_sit_tau": (INVENTED, "decay constant, no stated source"),
    "renewal_cap": (CIRCULAR, "SPEC §5: '2022 renewals averaged +10.7% while "
                              "asking rents rose faster' -- the OUTCOME the "
                              "model is asked to produce, installed as a "
                              "constraint. AMENDMENT 7."),
    "renewal_floor": (DERIVED, "1.00 = non-binding by construction"),
    "face_premium": (INVENTED, "SPEC §6: cap-rate arithmetic implies far more; "
                               "1.0 chosen as the conservative round number"),
    "disc_station": (UPSTREAM, "7% discount rate"),
    "disc_crab": (UPSTREAM, "households discount at ~12%"),
    # --- crab side (SPEC §4) ---
    "kappa_crab": (INVENTED, "1.6yr horizon; 'myopic' asserted, no source"),
    "lambda_ref": (INVENTED, "0.5; reference dependence, no published value"),
    "nu": (INVENTED, "SPEC §4 gives no basis at all -- the table cell is '--'"),
    "move_med": (CALIBRATED, "SPEC §4/§8 says so explicitly: 'calibrated to "
                             "observed elasticity'. V2 may not be claimed as a "
                             "prediction, and SPEC §8 says so. What SPEC §8 "
                             "does NOT say is that `p_exo_*` fits the OTHER "
                             "half of the same fact, which is what makes V2 an "
                             "identity rather than a partly-calibrated test. "
                             "A8 is the fix: derive it from search."),
    "move_sigma": (CALIBRATED, "same distribution as move_med"),
    "move_transient": (INVENTED, "50% redrawn each year, no stated source"),
    "attach_coef": (INVENTED, "0.35; the dollar figures are outputs, not a "
                              "source"),
    "p_exo_floor": (CIRCULAR, "SPEC §4: 'NAA turnover ~47% is mostly "
                              "non-rent.' TURNOVER IS THE VALIDATION TARGET: "
                              "V2 is retention in 0.45-0.65, i.e. turnover "
                              "0.35-0.55, and ~47% is the middle of it. The "
                              "floor+extra give 0.42 at first renewal decaying "
                              "to 0.26, which IS the non-rent half of the "
                              "target. Compounds with `move_med`: SPEC §8 "
                              "calibrates the switching cost to the RENT-driven "
                              "half of the same fact, so between them V2 is not "
                              "a weak test, it is an identity -- and nothing in "
                              "a per-parameter audit says so. PRINCIPLE G "
                              "rule 1 (two parameters fitted to two halves of "
                              "one fact fit the whole fact). "
                              "AMENDMENT 11 SOURCED THE REPLACEMENT and left "
                              "this default in place, so the class stands: the "
                              "shipped 0.24 is still justified by the number it "
                              "reproduces, and every published run used it. See "
                              "P_EXO_CPS_NONHOUSING (0.0990, CPS ASEC 2023) and "
                              "RESULTS-A11 -- K31 FIRED, and the fitted value "
                              "implies 90.4% of moves are non-rent where the "
                              "Census says 61.2%."),
    "p_exo_extra": (CIRCULAR, "same source, same target: the other term of "
                              "p_exo(j) = 0.24 + 0.18*exp(-(j-1)/3). AMENDMENT "
                              "11: the CPS publishes reason for move by nine "
                              "characteristics and NOT by length of residence, "
                              "so the decay this term carries has no source at "
                              "all -- the form the data supports is a constant. "
                              "Ablated in RESULTS-A11 §2: the shape is worth "
                              "under 0.2pp of retention."),
    "p_exo_tau": (INVENTED, "decay constant, no stated source"),
    # --- negotiation (SPEC §7) ---
    "ask_frac": (SCOPED, "SPEC §6: 'RealPage Jun 2026, ~6 weeks = 11% of "
                         "annual rent'. The published number is what landlords "
                         "GRANT. It is installed as the size of what tenants "
                         "ASK, and every instrument is then sized to deliver "
                         "that same crab value -- so Phase 1's largest possible "
                         "rent concession is 1.0 x 0.11 BY CONSTRUCTION. "
                         "IN SCOPE: existence and ORDERING claims -- which "
                         "instrument the station prefers at equal crab value is "
                         "what SPEC §6 set this up to isolate, and K1 turns on "
                         "the ordering, not the size. OUT OF SCOPE: any claim "
                         "about the MAGNITUDE of a concession, or about how "
                         "much a tenant should ask for. Those read the input "
                         "back out. Not a flat UPSTREAM (it would license the "
                         "magnitude claims) and not a flat CIRCULAR (it would "
                         "void K1, which does not depend on the level)."),
    "fee_cap_frac": (UPSTREAM, "ancillary fees ~4% of annual rent"),
    "term_cap": (INVENTED, "8%, no stated source"),
    "p_continue": (CIRCULAR, "SPEC §7: 'Without this, RANKED nests PRICE and K1 "
                             "could NOT FIRE on a level playing field.' The "
                             "value is justified by the kill condition it "
                             "enables. Swept {0.3,0.6,0.9}."),
    "p_substitute": (INVENTED, "0.35; SPEC §7 states the DIRECTION it moves "
                               "C-B, which is a conservatism argument, not a "
                               "source. Swept {0,0.35,0.7,1.0}."),
    "break_fee": (INVENTED, "2 months, no stated source"),
    "break_damp": (INVENTED, "0.5, no stated source"),
    "grant_menu": (INVENTED, "{1.0,0.6,0.3}, no stated source"),
    # --- arm F (AMENDMENT 1) ---
    "courage_med": (CIRCULAR, "world.py:122 in terms: 'Set so that at the "
                              "pessimistic prior belief the endogenous counter "
                              "rate lands near the observed 39%.' The counter "
                              "rate is the phenomenon arm F measures. Read the "
                              "sentence again: 'at the pessimistic prior "
                              "belief' -- the fit is JOINT with `belief0`, "
                              "which was fitted to the 61% complement of the "
                              "same number." + AND_ONE_KNOB),
    "courage_sigma": (INVENTED, "no stated source"),
    "belief0": (CIRCULAR, "world.py:126 in terms: 'prior P(concession | ask): "
                          "61% never try'. Its own first-pass note already read "
                          "'an output not a source', which is the DEFINITION of "
                          "CIRCULAR, not of INVENTED -- INVENTED means no "
                          "published counterpart, and this one has a "
                          "counterpart: it is the 39/61 counter-rate split, the "
                          "phenomenon arm F measures. Second fit to the same "
                          "fact `courage_med` was already fitted to, so the two "
                          "together pin the counter rate from both ends "
                          "(the cost of asking and the perceived odds of "
                          "winning). PRINCIPLE G rule 1." + AND_ONE_KNOB),
    "learn_rate": (INVENTED, "0.40, no stated source"),
    # --- AMENDMENT 2 §A2-2 primitives ---
    "risk_rho": (UPSTREAM, "upper end of standard CRRA estimates"),
    "comp_sigma0": (DERIVED, "sigma0/sqrt(U) from own-relet counts"),
    "nonpec0": (INVENTED, "0.5 mo/yr, no published counterpart"),
    "raise_cost0": (INVENTED, "0.6 mo, no published counterpart"),
    "u_personal": (INVENTED, "'you can personally know about ten tenants'"),
    "turn_scale_beta": (INVENTED, "1.0, no published counterpart"),
    "u_cap": (INVENTED, "50, no published counterpart"),
    "agent_bonus": (UPSTREAM, "leasing commission commonly 50-100% of a month"),
    "u_agent": (INVENTED, "20, no published counterpart"),
    "queue_frac": (INVENTED, "SPEC-A2 §A2-5 says so: 'a working guess'. Swept."),
    "engage_margin": (INVENTED, "2.0 months, no stated source"),
    "tool_noise": (INVENTED, "1.0 month for the honest case, no source"),
    # --- EXPLORATORY respecification (run.py EXPLORATORY) ---
    "sigma_turn": (INVENTED, "'p10/p90 ratio ~3.6x' is a restatement of the "
                             "value, not a source"),
    "sigma_vac": (INVENTED, "'p10/p90 ratio ~2.8x' -- same"),
    "turn_tenure_slope": (INVENTED, "'an 8-year habitat costs ~32% more' -- an "
                                    "output of the value, not a source"),
    # --- arm F clamps ---
    "belief_lo": (INVENTED, "clamp, no stated source"),
    "belief_hi": (INVENTED, "clamp, no stated source"),
    "ask_scale_lo": (INVENTED, "clamp, no stated source"),
    "ask_scale_hi": (INVENTED, "clamp, no stated source"),
    # --- AMENDMENT 8 (searchcost.py). Two are reused verbatim from market.py's
    # pre-A8 declarations, two are new and swept. `move_med` stays CALIBRATED
    # above: A8 does not repair it, it MEASURES what it should have been.
    "VIEW_COST": (UPSTREAM, "= market.py APP_COST, declared before A8"),
    "SPELL_COST": (UPSTREAM, "= market.py SEARCH_COST, declared before A8"),
    "OVERRUN_COST": (UPSTREAM, "= A6a HOLDOVER + EMERGENCY, declared before A8"),
    "MOVE_PHYSICAL": (UPSTREAM, "US local 1-2BR professional move, commonly "
                                "quoted $1,000-2,000. Swept {0,0.5,1,1.5,2}; "
                                "the sweep moves the derived median 0.48-2.48 "
                                "months, so it is reported as a range"),
    "TIME_COST": (INVENTED, "ANCHORED wage (ACS renter median already in "
                            "demographics.py), INVENTED hours (~10/month). "
                            "Swept."),
    "BROKER_FEE": (UPSTREAM, "one month's rent where a broker fee is charged"),
    "BROKER_SHARE": (INVENTED, "0.15, no published counterpart. Swept."),
    # --- AMENDMENT 9 ---
    "signal_cost": (INVENTED, "0.10 months to produce the proof; SPEC declared "
                              "it swept before A9 existed"),
    # --- AMENDMENT 4 heuristics (armk.py, already labelled INVENTED there) ---
    "SATISFICE_FRAC": (INVENTED, "labelled INVENTED in armk.py"),
    "HEUR_ANCHOR": (INVENTED, "sized to match Phase 1's ask"),
    "HEUR_BUDGET_FRAC": (INVENTED, "labelled INVENTED in armk.py"),
    "HEUR_ROUNDS": (INVENTED, "2 rounds; ALSO a Principle A confound -- it is a "
                              "function of tenant_engine in negotiate_matrix"),

    # =========================================================================
    # market.py -- AMENDMENTS 5 / 5a / 6 / 6a / 8. THE COVERAGE GAP.
    #
    # None of the following was in any table until 2026-07-25. K22 (depth vs
    # days-on-market), K23 (the engine and the deadline), K24 (deadline shape),
    # K25 (answer early), K26 (secure an alternative) and GATE 3's V8/V9/V10 all
    # run on these and only these. Two are CIRCULAR, three CALIBRATED, and the
    # shipped value of one of them contradicts its own module docstring.
    # =========================================================================

    # --- the bargaining solution (A5) ---
    "LAMBDA_SPLIT": (INVENTED, "market.py:38 'lambda_split = 0.5 is declared, "
                               "not fitted' -- true, and not a source: a "
                               "symmetric Nash split is a solution CONCEPT "
                               "asserted, not a measured value. Legal because "
                               "it is the same on both channels, which is what "
                               "makes A5's channel comparison mean anything. "
                               "Swept {0.25, 0.5, 0.75}."),
    "RELET_RISK_ON": (INVENTED, "market.py:294, no stated basis anywhere: a "
                                "hardcoded True that adds the sitting-vs-relet "
                                "rent gap to the landlord's renewal walk-away. "
                                "NEVER ABLATED in any reported cell, and K20's "
                                "1.08x ratio is measured with it on -- the "
                                "landlord's walk-away is turn + vacancy + THIS."),
    "SEARCH_COST": (INVENTED, "market.py:42 '0.25 months ($500) viewings, "
                              "applications, time'. A8.2 quotes it as one of "
                              "the two numbers 'describing overlapping things, "
                              "not speaking' -- no published counterpart."),
    "APP_COST": (INVENTED, "market.py:43 '0.08 months ($160) switching between "
                           "listings while already moving -- much smaller than "
                           "a move'. A relative-size argument, not a source."),
    "K_VISIBLE": (INVENTED, "market.py:45 '5 listings a searcher can see (local "
                            "information only)'. No source; sets how much of "
                            "the market a searcher's next-best option covers."),

    # --- days-on-market (A5a.3) -- both install the relationship K22 tests ---
    "DOM_LEARN": (CIRCULAR, "market.py:61 in terms: 'the expected remaining "
                            "wait -- and thus the landlord's walk-away -- grows "
                            "in days-on-market. THIS IS WHAT MAKES THE "
                            "LANDLORD'S RESERVATION WEAKEN MONOTONICALLY IN "
                            "DOM.' A5a.3's model requirement is 'the landlord's "
                            "reservation must weaken monotonically in it', and "
                            "K22 tests that requirement's consequence. RESULTS "
                            "Phase 5 §3 then reports the monotone weakening as "
                            "one of four VERIFIED unit properties; it is this "
                            "constant's definition read back out. Magnitude "
                            "0.35 has no source."),
    "DOM_CUT": (CIRCULAR, "market.py:154 'a landlord that has sat unlet "
                          "re-lists lower: 2% off the ask per month on market, "
                          "capped. Concession DEPTH is then measured off the "
                          "ORIGINAL listed ask.' K22 fires on 'concession depth "
                          "rises with days-on-market'. Cutting the ask 2%/month "
                          "in dom while measuring depth off the pre-cut ask "
                          "installs exactly that, so the kill could only ever "
                          "have measured the parameter. A5a.3 half-admits it "
                          "('close to an accounting identity once vacancy is a "
                          "flow') -- an identity is not a test. Only K22's "
                          "UNDECIDED verdict kept this out of the findings. "
                          "Magnitude 2%/month has no source."),
    "BASE_LET_MONTHS": (UPSTREAM, "market.py:60 '30-41 day commonly cited let "
                                  "times' -- a real published range, and NOT a "
                                  "target of this model. But E[wait] is then a "
                                  "READOUT of it: Phase 5 §3's 'E[wait] 1.15 -> "
                                  "3.56 months from dom 0 -> 6' is literally "
                                  "BASE_LET_MONTHS x (1 + DOM_LEARN x dom)."),

    # --- elastic demand (A6.1) ---
    "ETA_DEMAND": (UPSTREAM, "market.py:75-81, self-labelled 'ANCHORED range, "
                             "INVENTED functional form': published headship-"
                             "rate / household-formation elasticities sit "
                             "around 0.5-1.5, and 1.0 is the primary with a "
                             "PRE-DECLARED sweep {0.5,1.0,1.5,2.0}. The "
                             "magnitude is upstream; the multiplicative form "
                             "inflow = base x (M_ref/M)^eta is invented."),
    "M_REF": (DERIVED, "= ANCHOR_RENT, the reference price level for entry"),

    # --- the two clocks (A6a). Every one of these is INVENTED, and K25 is
    #     measured entirely in the units they define. ---
    "NOTICE_WINDOW": (INVENTED, "market.py:95 'months between the renewal offer "
                                "and lease end'. Declared in Phase 8 before "
                                "running; no published source given, and it "
                                "equals RESP_DELAY_MAX, so K25's last bucket "
                                "IS the whole window by construction."),
    "LEAD_MEDIAN": (INVENTED, "market.py:96-97 self-labelled 'LABEL: INVENTED "
                              "distribution'"),
    "LEAD_SIGMA": (INVENTED, "same distribution, same label"),
    "CLIFF_CONVEX": (INVENTED, "market.py:98 'walk-away rises convexly as "
                               "usable time runs out'. Shape asserted, "
                               "magnitude 0.5 unsourced. K24 ABLATED it (linear "
                               "mean-matched ramp) and found it carries 13% of "
                               "the effect -- which is the model of how an "
                               "invented constant should be handled."),
    "HOLDOVER_MONTHS": (INVENTED, "market.py:99 'penalty-rent differential on a "
                                  "holdover tenancy'. Real institution, no "
                                  "cited number."),
    "EMERGENCY_MONTHS": (INVENTED, "market.py:100 'temporary housing, storage, "
                                   "emergency-move premium'. Same."),
    "LAND_LIN_RATE": (INVENTED, "market.py:101 'each month of delay adds 15% to "
                                "E[vacancy]. The landlord gets NO cliff, per "
                                "A6a.3.' The no-cliff shape is registered; the "
                                "15% is not sourced. It is the landlord half of "
                                "the mechanism K24 found to be LEVEL, so the "
                                "level in question is this and CLIFF_* only."),
    "RESP_DELAY_MAX": (INVENTED, "market.py:103 'exogenous tenant response "
                                 "delay, 0..3 months. Drawn independently of "
                                 "type so K25 is a causal comparison rather "
                                 "than the survivorship trap K21 fell into.' "
                                 "The independence is a design property worth "
                                 "keeping; the 0-3 range has no source."),

    # --- the ask rule. Where the vacancy rate gets installed. ---
    "VAC_ADJUST": (CALIBRATED, "RESULTS Phase 5 §5 in terms: 'I tried three "
                               "calibrations (searcher inflow 0.035-0.25) and a "
                               "much stronger ask-adjustment (0.6 -> 3.0).' "
                               "Retuned AFTER seeing the deflation, i.e. fitted "
                               "to an output. DEFECT TO REPORT, NOT TO FIX "
                               "HERE: market.py's own module docstring still "
                               "declares 'vac_adjust 0.6' while line 162 ships "
                               "3.0, so the declared-before-running value and "
                               "the run value differ by 5x."),
    "V_TARGET": (CALIBRATED, "market.py:47 'the vacancy a station prices "
                             "toward', 0.06 -- the observed ~6% US apartment "
                             "vacancy that `searcher_inflow` is ALSO explicitly "
                             "calibrated to. Same fact entered twice, on the "
                             "supply side and the demand side, so the reported "
                             "vacancy LEVEL is a readout. The SIGN of the "
                             "supply response (V8) does not come from it."),

    # --- MarketParams fields ---
    "exit_share": (INVENTED, "market.py:175 'leavers who exit the market "
                             "entirely (left the metro), so they do not fill "
                             "the listing they vacated. This is what creates "
                             "slack for vacancy to exist.' A mechanism "
                             "argument for why it is non-zero, not a source "
                             "for 0.15."),
    "searcher_inflow": (CALIBRATED, "market.py:179-186 says so itself: "
                                    "'CALIBRATED so baseline vacancy lands near "
                                    "the observed ~6% US apartment vacancy. A "
                                    "level calibration to a published "
                                    "aggregate, not to any kill.' The second "
                                    "sentence is the right disclosure and the "
                                    "consequence still holds: the vacancy level "
                                    "may not be claimed."),
    "completions_frac": (INVENTED, "the V8 supply-shock dose (0.30 in the "
                                   "reported cell). No source; V8 is a "
                                   "DIRECTIONAL bar, so the dose sets the "
                                   "magnitude of the response and not its sign."),
    "completions_year": (INVENTED, "market.py:187 'GATE 3 V8: a supply shock "
                                   "lands here'. Timing, no source."),
    "completions_span": (INVENTED, "3 years to deliver the shock, no source"),
    "precedent": (INVENTED, "A5.3: 'Model it; do not assume its magnitude.' "
                            "Default 0.0 -- not assumed -- and swept {0.002, "
                            "0.01}. The honest handling of an unknown."),
    "signal_cost": (INVENTED, "market.py:210 'months of market rent to produce "
                              "the proof (forward the offer letter, pay a "
                              "holding deposit). DECLARED, swept.' 0.10 has no "
                              "source. Inert in every reported cell: "
                              "`signal_enabled` is False throughout, which is "
                              "why K26's null is a property of the setup."),
    "lambda_split": (DERIVED, "= LAMBDA_SPLIT"),
    "eta_demand": (DERIVED, "= ETA_DEMAND"),

    # --- world.py module scope (previously covered only via `Params`) ---
    "ANCHOR_RENT": (INVENTED, "SPEC §1: '$2,000/month converts to dollars for "
                              "reporting'. Free in world.py, which is "
                              "scale-free by construction -- but NOT free in "
                              "market.py, where it is the initial rent level "
                              "AND M_REF, the price entry responds to."),
    "ANNUAL_RENT": (DERIVED, "12 x ANCHOR_RENT; the fixed $24,000 denominator "
                             "for every '% of annual rent' bar in PREREG §5"),
    "REGIMES": (DERIVED, "the per-regime values of `drift` and `vacancy` and "
                         "nothing else -- both classified above, and `vacancy` "
                         "is CIRCULAR. A8.3 is the standing objection to the "
                         "table existing at all: the regimes are imposed where "
                         "search frictions should generate them."),

    # --- AMENDMENT 11 (world.py module scope). The sourced replacements for the
    # two CIRCULAR loops below. Declared here, NOT installed as `Params`
    # defaults: the defaults are what every published run used, and PREREG-A11
    # §A11.1 fixes that they do not move, so the before/after tables stay
    # reproducible and three concurrent workers are not silently invalidated.
    "CPS_RENTER_MOVER_RATE": (UPSTREAM, "US Census Bureau, Geographic Mobility: "
                              "2023 (2023 CPS ASEC, released 2024-12-10), "
                              "Table 1 mig_01_2023_1yr.xlsx, row 'In a "
                              "renter-occupied housing unit': 16,337 movers / "
                              "101,024 total = 16.171%/yr. A different survey, "
                              "producer, unit of analysis and quantity from the "
                              "NAA/RealPage apartment turnover V2 measures. "
                              "LIMITATION, declared in PREREG-A11 §A11.2.5: "
                              "person-weighted, all renters, tenure recorded at "
                              "the DESTINATION -- so a renter who bought is in "
                              "the owner row and this UNDERSTATES exit from a "
                              "rental."),
    "CPS_NONHOUSING_SHARE": (UPSTREAM, "same package, Table 13 "
                             "mig_13_2023_1yr.xlsx, same row: (family 3,496 + "
                             "employment 3,845 + other 2,665) / 16,337 = "
                             "0.6125. Mapping M1, the literal 'non-housing "
                             "share' and the conservative one -- it lets every "
                             "housing-related reason count as a rent response."),
    "CPS_NONPRICE_SHARE": (UPSTREAM, "same table, same row: 1 - (cheaper "
                           "housing 1,793 / 16,337) = 0.8902. Mapping M2, the "
                           "model's own reading -- the endogenous exit is a "
                           "logit on price against market, and 'cheaper "
                           "housing' is the Census category that is a price "
                           "response. Wanting a bigger apartment, a better "
                           "neighbourhood or to buy are exogenous, which is "
                           "what world.p_exo's docstring already said."),
    "P_EXO_CPS_NONHOUSING": (DERIVED, "CPS_RENTER_MOVER_RATE x "
                             "CPS_NONHOUSING_SHARE = 0.099046/yr. The A11 "
                             "PRIMARY. Flat in tenure: CPS publishes reason for "
                             "move by nine characteristics and NOT by length of "
                             "residence, so the shipped exp(-(j-1)/3) has no "
                             "source and is demoted to an INVENTED shape and "
                             "ablated (PREREG-A11 §A11.2.3)."),
    "P_EXO_CPS_NONPRICE": (DERIVED, "CPS_RENTER_MOVER_RATE x "
                           "CPS_NONPRICE_SHARE = 0.143966/yr, the M2 secondary"),
    "COURAGE_WAGE_HOURLY": (UPSTREAM, "demographics.INCOME_MEDIAN $75,000 "
                            "(ANCHORED, ACS renter median, market-rate segment) "
                            "/ 2080 h = $36.06/h -- the same conversion "
                            "searchcost.TIME_COST already declared before A11. "
                            "A wage is upstream of rent-setting: what a tenant "
                            "earns is not a function of how hard landlords push "
                            "at renewal."),
    "COURAGE_MED_1H": (INVENTED, "COURAGE_WAGE_HOURLY / ANCHOR_RENT = 0.018029 "
                       "months ($36.06), one hour to read the notice, check two "
                       "comparable listings and write the email. ANCHORED wage, "
                       "INVENTED hours -- the label TIME_COST already carries -- "
                       "and swept over 15 min to 80 h. It replaces a value that "
                       "was 9.98 hours of the same wage to send one email, "
                       "which is not a cost but a fitted residual wearing a "
                       "cost's name. Everything above the time cost (fear of "
                       "retaliation, conflict aversion) has NO published dollar "
                       "value, so it is swept rather than fixed."),
}


# Fields of `Params` / `MarketParams` that are NOT constants and therefore need
# no source: they select an arm, or they fix the geometry of the run. Kept
# explicit so that a new constant cannot be smuggled in by not declaring it.
ARM_SELECTORS = frozenset({
    "size_scaled_face", "menu_costs", "ask_mode", "no_concessions",
    "negotiator", "tenant_engine", "landlord_engine", "drop_term",
    "ladder_continues",
    # --- MarketParams. Each names the kill or amendment it switches. ---
    "tenant_sees_dom",      # K23: does the tenant negotiator see the timing?
    "deadline_shape",       # A6a on/off -- the "none" row of K24's table
    "tenant_clock_linear",  # K24's mean-matched ablation
    "secured_share",        # K26's treatment share
    "signal_enabled",       # K26 AUDIT; False in every reported cell
    "derive_switching",     # A8; separate rng, off in every reported cell
})
STRUCTURAL = frozenset({
    "n_stations", "units", "j_max", "comp_nodes", "blanket_grid",
    # --- module scope: labels, enum indices and rng slot geometry. These name
    # positions, not quantities, so there is nothing for a source to be.
    "NEVER_ASK", "ASK_PRICE", "ASK_RANKED",
    "ONE_TIME", "FEES", "TERM", "RENT", "KIND_NAMES",
    "U_STRAT", "U_CP", "U_CT", "U_EXO", "U_LOGIT", "U_TEN0", "U_PATIENCE",
    "U_SUB", "U_LOCKEXO", "U_RESTRAT", "U_TCOST", "U_VAC", "U_COURAGE",
    "U_MPGRANT", "U_EXODUS", "U_TOOL", "U_DEMO", "N_UNIFORMS",
    "RENEWAL", "NEW_LET", "MONTHS",
})


def undeclared_parameters(params_cls=None) -> list:
    """Fields of `Params` that are neither an arm selector, nor geometry, nor
    a constant with a declared source class. The forcing function: adding a
    constant without saying where it came from fails the suite."""
    if params_cls is None:
        from crabs.world import Params
        params_cls = Params
    return sorted(k for k in params_cls().__dict__
                  if k not in PARAM_SOURCES and k not in ARM_SELECTORS
                  and k not in STRUCTURAL)


# The modules whose module-level constants must be declared, and the dataclasses
# whose fields must be. This is the COVERAGE half of Principle C: the first audit
# classified `Params` exhaustively and never noticed that `market.py` held
# another twenty-odd constants in no table at all -- the ones K22-K27 and GATE 3
# run on. A table that covers one module is not a table, it is a sample.
DECLARED_MODULES = ("crabs.world", "crabs.market")
DECLARED_DATACLASSES = (("crabs.world", "Params"),
                        ("crabs.market", "MarketParams"))


def module_constants(module_name: str) -> list:
    """Public names bound by an assignment at MODULE scope in `module_name`'s
    own source.

    Read off the AST rather than `dir()`, for two reasons: a name imported from
    elsewhere (`ANCHOR_RENT` inside `market`) belongs to the module that DEFINES
    it and must not be demanded twice, and a module-level constant added in a
    branch or a tuple-unpack (`RENEWAL, NEW_LET = 0, 1`) is invisible to a
    line-oriented grep but not to this."""
    import importlib
    mod = importlib.import_module(module_name)
    try:
        src = inspect.getsource(mod)
    except (OSError, TypeError):                          # pragma: no cover
        return []
    out = []
    for node in ast.parse(src).body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for t in targets:
            for leaf in ([t] if isinstance(t, ast.Name)
                         else [e for e in getattr(t, "elts", [])
                               if isinstance(e, ast.Name)]):
                nm = leaf.id
                if nm.startswith("_") or nm in out:
                    continue
                if callable(getattr(mod, nm, None)):      # a def-by-assignment
                    continue
                out.append(nm)
    return out


def dataclass_fields(module_name: str, cls_name: str) -> list:
    import importlib
    cls = getattr(importlib.import_module(module_name), cls_name)
    return sorted(cls().__dict__)


def undeclared_symbols() -> dict:
    """PRINCIPLE C, the coverage half. {where: [symbols]} for every module-level
    constant and every dataclass field with no entry in `PARAM_SOURCES` and no
    explicit structural / arm-selector declaration.

    Empty is the only passing value. A non-empty return names exactly what to
    write down, which is the point: the cost of adding a constant should be one
    line in the table, paid at write time."""
    out = {}
    def missing(names):
        return sorted(n for n in names if n not in PARAM_SOURCES
                      and n not in ARM_SELECTORS and n not in STRUCTURAL)
    for m in DECLARED_MODULES:
        if (gap := missing(module_constants(m))):
            out[m] = gap
    for m, c in DECLARED_DATACLASSES:
        if (gap := missing(dataclass_fields(m, c))):
            out[f"{m}.{c}"] = gap
    return out


def circular_parameters() -> dict:
    """Every constant whose stated justification is the phenomenon under study.
    A non-empty return is a standing defect list, not a pass."""
    return {k: v[1] for k, v in PARAM_SOURCES.items() if v[0] == CIRCULAR}


def scoped_parameters() -> dict:
    """Constants that are upstream for some claims and circular for others. The
    entry itself has to say which, so reading the class alone is never enough --
    that is the price of not forcing a wrong binary."""
    return {k: v[1] for k, v in PARAM_SOURCES.items() if v[0] == SCOPED}


def unsourced_parameters() -> dict:
    """INVENTED constants, which are legal but must be labelled as such in every
    result table (DESIGN-PRINCIPLES C rule 1)."""
    return {k: v[1] for k, v in PARAM_SOURCES.items() if v[0] == INVENTED}


# =============================================================================
# D. IDENTICAL POPULATIONS
# =============================================================================

# Recorder denominators, classified by what they condition on. A statistic whose
# denominator is not UNCONDITIONAL measures a SUBSET selected by an outcome, and
# must be reported beside its unconditional counterpart or not at all.
DENOMINATORS = {
    "habitat_years":        None,   # every habitat-year. unconditional.
    "crab_years":           None,   # counted for leavers too. unconditional.
    "crab_years_asker":     "self-selected into asking (endogenous in "
                                    "ask_mode tool/selfselect/everyone and in "
                                    "arm F, where the trait is a decision)",
    "crab_years_nonasker":  "the complement of the above",
    "renewals":             "excludes years inside a TERM lock -- i.e. excludes "
                                    "the crabs that accepted a term concession",
    "renewals_asker":       "asking AND not term-locked",
    "renewals_nonasker":    "not asking AND not term-locked",
    "push_n":               "same as renewals",
    "countered":            "conditioned on having asked",
    "countered_lt2":        "asked AND tenure == 1",
    "countered_ge2":        "asked AND tenure >= 2",
    "rent_ratio_n":         "STAYED (or was term-locked): the leave branch of "
                                    "world._year never increments it",
    "engine_util_n":        "asked AND the engine was consulted",
    "bundles_granted":      "STAYED AND was granted a bundle",
    "belief_n":             "STAYED",
    "wealthy_years":        "STAYED AND carries shock wealth",
    "burdened_years":       "STAYED AND cost-burdened",
    "termlover_years":      "STAYED AND weights term over rent",
    "blanket_n":            "arm G only",
    "rent_ratio_sum":       "see rent_ratio_n",
    "ask_share_n":          "arm F years only",
    # --- market.py recorder (AMENDMENT 5/6). No TERM locks exist here, so a
    # renewal decision really is every renewal decision.
    "n_renewal":            None,
    "wa_n_renew":           None,
    "wa_n_newlet":          None,
    "move_gain_n":          None,   # market.py:487 fixes the survivorship
    "move_gain_q{}_n":      None,
    "secured_n":            None,   # secured status is assigned, not an outcome
    "unsecured_n":          None,
    "renew_elapsed{}_n":    None,   # elapsed bucket is assigned, not an outcome
    "renew_growth_n":       "SIGNED: the renewal was accepted. Tenants the "
                                    "offer pushed out are not in it -- and this "
                                    "is the denominator under V9/K19/K24",
    "n_renewal_signed":     "SIGNED: the renewal was accepted",
    "newlet_growth_n":      "a match cleared (zone > 0)",
    "n_newlet_signed":      "a match cleared (zone > 0)",
    "ask_n":                "weighted by vacant months, so a long-DOM unit at a "
                                    "deep cut is counted repeatedly",
}
for _j in range(1, 9):
    DENOMINATORS[f"ten{_j}_renewals"] = (
        f"SURVIVED to tenure {_j} -- artefact #5's family")
# f-string-keyed statistics normalise to a `{}` pattern, so that a per-tenure
# or per-instrument family is checked as one entry. K21's quartiles were built
# in a loop exactly like this, which is why the pattern form has to be covered.
DENOMINATORS["ten{}_renewals"] = ("SURVIVED to that tenure -- artefact #5's "
                                  "family")

# Declared unconditional counterpart for each conditional statistic. A
# statistic that appears in `derive()` with a conditional denominator and is
# absent here is an unpaired conditional statistic and the check fails.
PAIRED = {
    "retention_asker": "retention",
    "retention_nonasker": "retention",
    "surplus_asker": "surplus_pcy",
    "surplus_nonasker": "surplus_pcy",
    "success_rate": "counter_rate",
    "success_rate_price": "counter_rate",
    "success_lt2": "counter_rate",
    "success_ge2": "counter_rate",
    "tenure_ratio": "success_rate",
    "counter_rate": "retention",
    "retention": "turnover",
    "turnover": "retention",
    "rounds_per_renewal": "habitat_years",
    "calib_pred_leave": "calib_real_leave",
    "calib_real_leave": "calib_pred_leave",
    "zero_increase_share": "mean_offer_push",
    "mean_offer_push": "habitat_years",
    "issues_per_grant": "bundles_granted",
    "engine_util": "habitat_years",
    "grant_share_one_time": "counter_rate",
    "grant_share_fees": "counter_rate",
    "grant_share_term": "counter_rate",
    "grant_share_rent": "counter_rate",
}
for _j in range(1, 9):
    PAIRED[f"retention_ten{_j}"] = "retention"
PAIRED["retention_ten{}"] = "retention"
PAIRED["grant_share_{}"] = "counter_rate"


def conditional_statistics(fn=None) -> dict:
    """PRINCIPLE D, reusable. Parses the reporting layer and returns
    {statistic: (denominator, what the denominator conditions on)} for every
    ratio whose denominator is NOT the full population.

    Reads the source rather than a hand-kept list, so a statistic added later
    is caught without anyone remembering to add it here."""
    if fn is None:
        from crabs.run import derive
        fn = derive
    src = textwrap.dedent(inspect.getsource(fn))
    out = {}
    for node in ast.walk(ast.parse(src)):
        # d["name"] = ... _d(num, den) ...   and   {"name": ... _d(num, den)}
        pairs = []
        if isinstance(node, ast.Dict):
            pairs = [(k, v) for k, v in zip(node.keys, node.values)
                     if k is not None]
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Subscript)):
            pairs = [(node.targets[0].slice, node.value)]
        for k, v in pairs:
            name = _key_pattern(k)
            if name is None:
                continue
            for sub in ast.walk(v):
                if not (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "_d" and len(sub.args) == 2):
                    continue
                den = _denominator_name(sub.args[1])
                if den and DENOMINATORS.get(den, "unknown") is not None:
                    out[name] = (den, DENOMINATORS.get(den, "UNKNOWN "
                                                       "denominator"))
    return out


def _key_pattern(node):
    """A dict key or subscript index as a string. A literal returns itself; an
    f-string returns its shape with `{}` in place of each interpolation, so a
    family built in a loop (`f"ten{j}_renewals"`) is checked as one entry
    instead of being invisible to the parser -- which is where K21's
    survivorship artefact lived."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            else:
                out.append("{}")
        return "".join(out)
    return None


def _denominator_name(node):
    """`a["renewals"]` -> "renewals"; `a[f"ten{j}_renewals"]` ->
    "ten{}_renewals"; anything else -> None."""
    if isinstance(node, ast.Subscript):
        nm = _key_pattern(node.slice)
        if nm is not None:
            return nm
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id == "_d" and len(node.args) == 2:
        return _denominator_name(node.args[1])
    return None


def unpaired_conditional_statistics(fn=None) -> dict:
    """Conditional statistics with no declared unconditional counterpart. This
    is the check artefacts #4 and #5 would have failed."""
    return {k: v for k, v in conditional_statistics(fn).items()
            if k not in PAIRED}


# --- D, second half: the ratio whose two halves are on DIFFERENT populations --
# Worse than an unpaired conditional statistic, and harder to see: a mean whose
# numerator sums over survivors while its denominator counts everyone is neither
# the conditional nor the unconditional figure. It is nothing. Artefact #5 was
# the readable version of this; the mismatched form hides inside a `_d()` call.
ALL_HABITAT_YEARS = "every habitat-year"
ALL_CRAB_YEARS = "every crab-year, leavers included"
ALL_RENEWALS = "every renewal decision"
ASKERS = "crabs that asked"
STAYERS = "crabs that renewed AND stayed"
NEWLET = "new lets that signed"
ENGINE_ASKERS = "askers whose renewal reached the engine"

POPULATION_OF = {}
POPULATION_OF.update({k: ALL_HABITAT_YEARS for k in (
    "habitat_years", "market_sum", "station_cash", "station_objective",
    "turn_cost_paid", "vacancy_lost", "move_cost_paid", "crab_cash",
    "arrival_cash", "welfare_extra", "rent_paid_sum", "vacant_years",
    "turn_events")})
POPULATION_OF.update({k: ALL_CRAB_YEARS for k in (
    "crab_years", "surplus")})
POPULATION_OF.update({k: ALL_RENEWALS for k in (
    "renewals", "left", "countered", "success", "success_price", "push_n",
    "push_sum", "offer_ratio_sum", "zero_increase", "rounds", "pred_leave",
    "real_leave", "countered_lt2", "countered_ge2", "success_lt2",
    "success_ge2", "renewals_asker", "renewals_nonasker", "left_asker",
    "left_nonasker", "n_renewal", "n_renewal_left", "wa_n_renew",
    "wa_tenant_renew", "wa_land_renew", "zone_renew_sum", "lead_sum",
    "elapsed_sum", "secured_n", "unsecured_n", "secured_offer",
    "unsecured_offer", "move_gain_n", "move_gain_sum", "move_gain_pos",
    "rent_gap_sum", "ask_sum", "ask_n")})
POPULATION_OF.update({k: ASKERS for k in (
    "crab_years_asker", "surplus_asker", "crab_years_nonasker",
    "surplus_nonasker")})
POPULATION_OF.update({k: STAYERS for k in (
    "rent_ratio_sum", "rent_ratio_n", "belief_sum", "belief_n",
    "ask_scale_sum", "wealthy_years", "surplus_wealthy", "burdened_years",
    "surplus_burdened", "termlover_years", "surplus_termlover",
    "concession_value", "bundles_granted", "issues_conceded",
    "n_renewal_signed", "renew_growth_sum", "renew_growth_n",
    "renew_ratio_sum", "renew_rent_sum", "sitting_rent_sum", "sitting_rent_n",
    "secured_surp", "unsecured_surp", "surplus_renew", "surplus_renew_n")})
POPULATION_OF.update({k: NEWLET for k in (
    "newlet_growth_sum", "newlet_growth_n", "n_newlet_signed",
    "newlet_rent_sum", "newlet_vs_ask_sum")})
POPULATION_OF.update({k: ENGINE_ASKERS for k in (
    "engine_util_sum", "engine_util_n")})
POPULATION_OF["grant_{}"] = STAYERS
POPULATION_OF["grantval_{}"] = STAYERS
POPULATION_OF["ten{}_renewals"] = ALL_RENEWALS
POPULATION_OF["ten{}_left"] = ALL_RENEWALS
POPULATION_OF["renew_elapsed{}_n"] = ALL_RENEWALS
POPULATION_OF["renew_elapsed{}_offer"] = ALL_RENEWALS
POPULATION_OF["renew_elapsed{}_surp"] = STAYERS
POPULATION_OF["move_gain_q{}"] = ALL_RENEWALS
POPULATION_OF["move_gain_q{}_n"] = ALL_RENEWALS
POPULATION_OF["move_gain_q{}_pos"] = ALL_RENEWALS
POPULATION_OF["surp_renew_q{}"] = STAYERS
POPULATION_OF["surp_renew_q{}_n"] = STAYERS

# Ratios where the mismatch is intended and meaningful: a rate whose numerator
# is a strict subset of its denominator by definition (a success rate, a
# retention rate). Declared, so that everything else is a defect.
RATE_OF_SUBSET = frozenset({
    "retention", "retention_asker", "retention_nonasker", "turnover",
    "counter_rate", "success_rate", "success_rate_price", "success_lt2",
    "success_ge2", "zero_increase_share", "calib_real_leave",
    "calib_pred_leave", "rounds_per_renewal", "mean_offer_push",
    "tenure_ratio", "retention_ten{}", "move_gain_share", "move_gain",
    "rent_gap", "move_gain_q{}", "move_share_q{}", "wa_tenant_renew",
    "wa_land_renew", "zone_renew", "wa_ratio_renew", "wa_tenant_newlet",
    "wa_land_newlet", "zone_newlet", "vacancy", "turn_events_per_hab",
    "mean_ask", "deadweight_phy", "elapsed{}_offer", "secured_offer",
    "unsecured_offer",
    # per-habitat-year normalisations: crab-years are a subset of habitat-years
    # by construction (a vacant habitat has no crab), so dividing a crab-year
    # sum by habitat-years is the intended "per habitat we own" figure
    "tenant_phy", "tenant_cash_phy",
})


def _populations(node, out):
    """Every recorder key reached by an expression, mapped to its population."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Subscript):
            nm = _key_pattern(sub.slice)
            if nm is not None and nm in POPULATION_OF:
                out.add(POPULATION_OF[nm])
            elif nm is not None:
                out.add(f"UNCLASSIFIED:{nm}")
    return out


def mismatched_ratios(fn=None) -> dict:
    """PRINCIPLE D, the sharp half. Returns {statistic: (numerator population,
    denominator population)} for every `_d(num, den)` whose two halves are drawn
    from different populations and which is not a declared rate-of-a-subset."""
    if fn is None:
        from crabs.run import derive
        fn = derive
    src = textwrap.dedent(inspect.getsource(fn))
    out = {}
    for node in ast.walk(ast.parse(src)):
        pairs = []
        if isinstance(node, ast.Dict):
            pairs = [(k, v) for k, v in zip(node.keys, node.values)
                     if k is not None]
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Subscript)):
            pairs = [(node.targets[0].slice, node.value)]
        for k, v in pairs:
            name = _key_pattern(k)
            if name is None or name in RATE_OF_SUBSET:
                continue
            for sub in ast.walk(v):
                if not (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "_d" and len(sub.args) == 2):
                    continue
                np_, dp_ = _populations(sub.args[0], set()), \
                    _populations(sub.args[1], set())
                if np_ and dp_ and np_ != dp_:
                    out[name] = (sorted(np_), sorted(dp_))
    return out
