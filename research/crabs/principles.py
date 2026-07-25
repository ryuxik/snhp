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
#   CIRCULAR  its justification IS the phenomenon under study. Always a defect.
UPSTREAM, DERIVED, INVENTED, CALIBRATED, CIRCULAR = (
    "UPSTREAM", "DERIVED", "INVENTED", "CALIBRATED", "CIRCULAR")


# Every constant in SPEC.md §4-§7 and SPEC-A2.md §A2-2, with the class its own
# stated basis earns it. Audited 2026-07-25 under AMENDMENT 7.
PARAM_SOURCES = {
    # --- market process (SPEC §3) ---
    "drift": (UPSTREAM, "2021-22 asking-rent growth +11-15% (loss, we use +9%); "
                        "MAA new-lease FY2024 -5.9%/FY2025 -5.8% (gain)"),
    "sigma_burn": (INVENTED, "no stated source"),
    "sigma_meas": (INVENTED, "no stated source"),
    "burn_years": (INVENTED, "no stated source"),
    "meas_years": (UPSTREAM, "PREREG §3 requires >=200 station-years"),
    "g_long": (UPSTREAM, "underwriting practice: long-run terminal growth"),
    # --- station cost side (SPEC §5) ---
    "turn_cost": (UPSTREAM, "NAA/IREM/BOMA triangulation, 1-2 months"),
    "vacancy": (UPSTREAM, "39.7% of 2026 listings carried a concession"),
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
                             "prediction, and SPEC §8 says so."),
    "move_sigma": (CALIBRATED, "same distribution as move_med"),
    "move_transient": (INVENTED, "50% redrawn each year, no stated source"),
    "attach_coef": (INVENTED, "0.35; the dollar figures are outputs, not a "
                              "source"),
    "p_exo_floor": (UPSTREAM, "NAA turnover ~47%, mostly non-rent"),
    "p_exo_extra": (UPSTREAM, "same"),
    "p_exo_tau": (INVENTED, "decay constant, no stated source"),
    # --- negotiation (SPEC §7) ---
    "ask_frac": (UPSTREAM, "RealPage Jun 2026, ~6 weeks = 11% of annual rent"),
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
                              "rate is the phenomenon arm F measures."),
    "courage_sigma": (INVENTED, "no stated source"),
    "belief0": (INVENTED, "0.10 -> '61% never try', an output not a source"),
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
    # --- AMENDMENT 4 heuristics (armk.py, already labelled INVENTED there) ---
    "SATISFICE_FRAC": (INVENTED, "labelled INVENTED in armk.py"),
    "HEUR_ANCHOR": (INVENTED, "sized to match Phase 1's ask"),
    "HEUR_BUDGET_FRAC": (INVENTED, "labelled INVENTED in armk.py"),
    "HEUR_ROUNDS": (INVENTED, "2 rounds; ALSO a Principle A confound -- it is a "
                              "function of tenant_engine in negotiate_matrix"),
}


# Fields of `Params` that are NOT constants and therefore need no source: they
# select an arm, or they fix the geometry of the run. Kept explicit so that a
# new constant cannot be smuggled in by not declaring it.
ARM_SELECTORS = frozenset({
    "size_scaled_face", "menu_costs", "ask_mode", "no_concessions",
    "negotiator", "tenant_engine", "landlord_engine", "drop_term",
    "ladder_continues",
})
STRUCTURAL = frozenset({
    "n_stations", "units", "j_max", "comp_nodes", "blanket_grid",
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


def circular_parameters() -> dict:
    """Every constant whose stated justification is the phenomenon under study.
    A non-empty return is a standing defect list, not a pass."""
    return {k: v[1] for k, v in PARAM_SOURCES.items() if v[0] == CIRCULAR}


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
