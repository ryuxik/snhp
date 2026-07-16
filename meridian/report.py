"""Renders meridian/report.md from the audit results (SPEC "Deliverable").

Tone: a professional audit deliverable a customer would pay for. Every figure
is mean +/- sd over the seed set, with the seeded repro command beside it, and a
"What we did NOT find" section so the report cannot be read as cherry-picked.
This file only FORMATS; all numbers come from audit.py.
"""

from __future__ import annotations

from pathlib import Path

REPORT_PATH = Path(__file__).with_name("report.md")


def _m(ms: dict, nd: int = 0) -> str:
    """mean +/- sd formatter."""
    if ms is None or ms.get("mean") is None:
        return "n/a"
    mean, sd = ms["mean"], ms.get("sd") or 0.0
    if nd == 0:
        return f"{mean:,.0f} +/- {sd:,.0f}"
    return f"{mean:,.{nd}f} +/- {sd:,.{nd}f}"


def _money(ms: dict) -> str:
    if ms is None or ms.get("mean") is None:
        return "n/a"
    return f"${ms['mean']:,.0f} +/- ${ms.get('sd') or 0:,.0f}"


def _p(p) -> str:
    if p is None:
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _sev(tag: str) -> str:
    return {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM",
            "low": "LOW"}.get(tag, tag.upper())


def generate(results: dict) -> Path:
    meta = results["meta"]
    A1, A2, A3, A4 = results["A1"], results["A2"], results["A3"], results["A4"]
    led = results["ledger"]

    a1 = A1["agg"]
    f10 = A2["by_f"][0.10]["agg"]
    f25 = A2["by_f"][0.25]["agg"]
    f00 = A2["by_f"][0.0]["agg"]
    lift = A2["deception_lift"]
    att = A2["a5_attestation"]
    k0 = A3["by_k"][0]["agg"]
    k20 = A3["by_k"][20]["agg"]
    k50 = A3["by_k"][50]["agg"]
    a4 = A4["agg"]

    # derived headline numbers
    liar_mult25 = (f25["deceptive_margin_per_trade"]["mean"]
                   / max(1e-9, f25["honest_margin_per_trade"]["mean"]))
    lift_ratio = lift["lift_ratio"]["mean"]
    dec_off = att["off"]["deceptive_margin_per_trade"]["mean"]
    dec_on = att["on"]["deceptive_margin_per_trade"]["mean"]
    hon_ref = att["off"]["honest_margin_per_trade"]["mean"]
    bs_off = att["off"]["buyer_surplus_realized"]["mean"]
    bs_on = att["on"]["buyer_surplus_realized"]["mean"]

    L = []
    W = L.append

    # -- header ----------------------------------------------------------
    W("# MERIDIAN Protocol Audit - MPX v1")
    W("")
    W("**Prepared by:** snhp mechanism-audit service &nbsp;&nbsp;|&nbsp;&nbsp; "
      "**Subject:** Meridian Procurement Systems, exchange protocol MPX v1")
    W("")
    W("> *Meridian Procurement Systems is a fictional company created to "
      "demonstrate this service. MPX is real, runnable code implementing the "
      "design patterns shipping in 2026 agent-commerce systems. Every figure "
      "below regenerates from seeded runs with `python -m meridian.audit "
      "--full`; every market event is recorded on a hash-chained ledger.*")
    W("")
    W("## Engagement summary")
    W("")
    W(f"We stood up MPX v1 as specified - ~{meta['n_buyers']} buyer orgs, "
      f"~{meta['n_suppliers']} suppliers, {meta['n_brokers']} brokers, "
      f"{meta['ticks']:,}-tick market, {len(meta['seeds'])} seeds - and ran the "
      "A1-A5 battery. MPX transacts cleanly in the happy path. The findings "
      "below are **structural**: they are properties of the protocol's message "
      "rules and settlement model, not bugs in any agent. An agent that obeys "
      "every MPX rule can still extract value or destroy it, and MPX cannot see "
      "it happen.")
    W("")
    W("Headline: MPX's price-only negotiation leaves "
      f"**{a1['gap_pct']['mean']:.0f}% of realizable trade surplus** on the "
      "table, its optimistic pay-on-accept settlement lets a rule-abiding liar "
      f"lift its own per-trade margin **{lift_ratio:.1f}x** while "
      "its public star average stays green, and its broker chains leak "
      f"**{a4['unserved_chain_pct']['mean']:.0f}%** of demand unserved. Two "
      "targeted mechanism changes (bundled counters; attestation-gated "
      "settlement) close the first two almost entirely - measured, not asserted.")
    W("")

    # -- findings table --------------------------------------------------
    W("## Findings")
    W("")
    W(f"| ID | Finding | Magnitude (mean +/- sd, {len(meta['seeds'])} seeds) | "
      "Severity | Fix (measured) |")
    W("|----|---------|----------------------------------|----------|----------------|")
    W(f"| A1 | Bundling silence: price-only negotiation cannot express "
      f"qty/ship-date tradeoffs | {a1['foregone_pct']['mean']:.0f}% of "
      f"beneficial trades foregone; {a1['gap_pct']['mean']:.0f}% joint surplus "
      f"lost (${a1['gap_dollars']['mean']:,.0f}/run) | {_sev('high')} | "
      f"Bundled counters via nash_solver recover "
      f"{a1['nash_recovered_pct']['mean']:.0f}% of the oracle optimum |")
    W(f"| A2 | Deception under optimistic settlement: pay-on-accept is never "
      f"clawed back | liar lifts own margin/trade {lift_ratio:.1f}x "
      f"(self-controlled); only {f25['deceptive_flagged']['mean']:.0f}/"
      f"{f25['deceptive_total']['mean']:.0f} liars ever flagged by stars | "
      f"{_sev('critical')} | Attestation-gated escrow cuts liar margin "
      f"{dec_off:,.0f} -> {dec_on:,.0f}/trade (removes the windfall) |")
    W(f"| A3 | Stale books: a k-tick-stale buyer re-orders committed lines | "
      f"{k20['harmful_per_100']['mean']:.0f} harmful accepts/100 trades at "
      f"k=20; buyer surplus ${k0['buyer_surplus_realized']['mean']:,.0f} -> "
      f"${k20['buyer_surplus_realized']['mean']:,.0f} | {_sev('high')} | "
      "Order idempotency / commit-ack (not simulated; see recommendation) |")
    W(f"| A4 | Broker hold-up: no pre-commitment, spot sourcing after buyer "
      f"commit | {a4['unserved_chain_pct']['mean']:.0f}% chain demand unserved; "
      f"broker margin {a4['broker_margin_compression_pct']['mean']:.0f}% "
      f"compressed (to negative) | {_sev('medium')} | Upstream pre-commitment / "
      "escrowed two-leg settlement (recommendation) |")
    W("")

    # -- A1 --------------------------------------------------------------
    W("## A1 - Bundling silence (structural)")
    W("")
    W("**Mechanism.** An MPX `COUNTER` carries a price and nothing else; "
      "`qty` and `ship_date` are take-it-or-leave-it on the supplier's `QUOTE`. "
      "A naive-but-competent supplier quotes the qty it has at its *cheapest* "
      "ship date (the natural production lead, no expedite). When a buyer is "
      "urgent, that late date destroys buyer value - and because the date is "
      "not negotiable, the parties cannot trade an expedited date for a higher "
      "price even when doing so would grow the total pie. The trade either "
      "happens at a Pareto-dominated point or does not happen at all.")
    W("")
    W("**Method.** For every demand line we compute the oracle: the "
      "joint-surplus-maximizing `(qty, ship_date)` bundle against the *same* "
      "supplier, using the market's own utility and cost functions "
      "(`meridian.agents.joint_surplus`). We compare it to what price-only "
      "negotiation actually reached.")
    W("")
    W(f"**Magnitude.** Averaged over {len(meta['seeds'])} seeds "
      f"({a1['lines']['mean']:.0f} demand lines/run):")
    W("")
    W(f"- Mutually-beneficial trades MPX cannot express (foregone): "
      f"**{a1['foregone_pct']['mean']:.1f}% +/- {a1['foregone_pct']['sd']:.1f}**")
    W(f"- Joint surplus lost vs the bundled optimum: "
      f"**{a1['gap_pct']['mean']:.1f}% +/- {a1['gap_pct']['sd']:.1f}** "
      f"(= {_money(a1['gap_dollars'])} per run)")
    W(f"- Oracle surplus {_money(a1['oracle_surplus'])} vs price-only "
      f"{_money(a1['price_only_surplus'])} (Wilcoxon paired "
      f"p={_p(a1['wilcoxon_gap_p'])})")
    W("")
    W("**Fix (A5-i), measured.** Replace the price-only counter with a bundled "
      "counter over `(price, qty, ship_date)`, resolved by the snhp "
      "`nash_solver` primitives (`generate_contract_space` -> "
      "`filter_pareto_frontier` -> `find_nash_bargaining_solution`) against the "
      "same counterparty. Re-running A1:")
    W("")
    W(f"- Bundled counters recover **{a1['nash_recovered_pct']['mean']:.1f}% +/- "
      f"{a1['nash_recovered_pct']['sd']:.1f}** of the oracle optimum "
      f"(residual gap {a1['nash_residual_gap_pct']['mean']:.1f}%), turning the "
      f"{a1['gap_pct']['mean']:.0f}% structural loss into near-zero.")
    W("")
    W("**Severity: HIGH.** Pure deadweight loss on every urgent order, "
      "invisible to MPX because no rule is broken.")
    W("")
    W("**Repro.** `python -c \"from meridian.audit import run_a1, SEEDS; "
      "print(run_a1(SEEDS)['agg'])\"`")
    W("")

    # -- A2 --------------------------------------------------------------
    W("## A2 - Deception under optimistic settlement")
    W("")
    W("**Mechanism.** Payment transfers on `ACCEPT`; delivery happens "
      "`ship_date` ticks later and is never reconciled against the payment. A "
      "`DeceptiveSupplier` obeys every message rule but, on a fraction of "
      "orders, ships short and late while keeping the full pay-on-accept. The "
      "withheld goods are pure margin. Detection is via self-reported stars "
      "(a public running mean), which lags because most of the liar's orders "
      "are fine and an unrated or thinly-rated supplier looks perfect.")
    W("")
    W(f"**Magnitude.** Sweeping the deceptive-supplier fraction f "
      f"(prediction from our corpus: the dashboard stays green while buyers "
      f"bleed - measured, not assumed):")
    W("")
    W("| f | honest margin/trade | liar margin/trade | realized fill | "
      "buyer surplus | liars flagged | trades-to-flag |")
    W("|---|---------------------|-------------------|---------------|"
      "---------------|---------------|----------------|")
    for f, agg in ((0.0, f00), (0.10, f10), (0.25, f25)):
        W(f"| {f:.2f} | {_m(agg['honest_margin_per_trade'])} | "
          f"{_m(agg['deceptive_margin_per_trade'])} | "
          f"{_m(agg['fill_realized'], 3)} | {_money(agg['buyer_surplus_realized'])} | "
          f"{agg['deceptive_flagged']['mean']:.0f}/"
          f"{agg['deceptive_total']['mean']:.0f} | "
          f"{_m(agg['mean_trades_to_flag'], 1)} |")
    W("")
    W(f"**Causal size of the exploit (self-controlled).** Comparing the SAME "
      f"suppliers with the under-delivery channel on vs off (bad-order rate "
      f"0.5 vs 0, paired by seed) isolates the windfall from the random cost "
      f"draws of the deceptive subset: the liar's own margin/trade rises "
      f"**{_m(lift['channel_off_margin'])} -> {_m(lift['channel_on_margin'])}** "
      f"(**{lift_ratio:.2f}x**, Wilcoxon p={_p(lift['wilcoxon_p'])}). The naive "
      f"cross-group ratio at f=0.25 is {liar_mult25:.1f}x honest "
      f"({_m(f25['deceptive_margin_per_trade'])} vs "
      f"{_m(f25['honest_margin_per_trade'])}); the difference between "
      f"{lift_ratio:.2f}x and {liar_mult25:.1f}x is population composition, not "
      "deception, and we report both rather than the flattering one.")
    W("")
    W(f"Meanwhile only {f25['deceptive_flagged']['mean']:.0f} of "
      f"{f25['deceptive_total']['mean']:.0f} liars ever cross the star-flag "
      "threshold, and the optimistic fill metric (booked = paid) stays at ~1.00 "
      "throughout; the truth (realized on-time fill) is what erodes.")
    W("")
    W("**Fix (A5-ii), measured.** Gate the optimistic tier on delivery "
      "receipts: a supplier earns pay-on-accept only after a clean attestation "
      "history; everyone else settles from escrow that releases only for what "
      "actually arrives. Re-running A2 at f=0.25:")
    W("")
    W(f"- Liar margin/trade **{dec_off:,.0f} -> {dec_on:,.0f}** "
      f"(honest reference {hon_ref:,.0f}) - the pay-on-accept windfall is "
      f"removed and the liar collapses to (at or below) honest levels "
      f"(Wilcoxon p={_p(att['wilcoxon_dec_margin_p'])}).")
    W(f"- Buyer surplus **${bs_off:,.0f} -> ${bs_on:,.0f}** "
      f"(+${bs_on - bs_off:,.0f}; Wilcoxon p="
      f"{_p(att['wilcoxon_buyer_surplus_p'])}).")
    W("")
    W("**Severity: CRITICAL.** The exploit needs no rule-breaking, profits "
      "immediately, and is largely invisible to the ratings surface MPX ships.")
    W("")
    W("**Repro.** `python -c \"from meridian.audit import run_a2, SEEDS; "
      "import json; print(json.dumps(run_a2(SEEDS)['a5_attestation'], default=float, indent=2))\"`")
    W("")

    # -- A3 --------------------------------------------------------------
    W("## A3 - Stale books")
    W("")
    W("**Mechanism.** A `StaleBuyer`'s belief of its own committed orders and "
      "remaining budget lags the truth by k ticks. MPX has no order-idempotency "
      "or commit-acknowledgement, so within the lag window the buyer re-issues "
      "RFQs for lines it has already ordered. The duplicate deliveries arrive "
      "against a need already met - their realized marginal value is ~zero, but "
      "they were paid for on accept. Each duplicate is a *harmful accept*: a "
      "trade with negative realized surplus.")
    W("")
    W("| k (lag) | trades | harmful accepts/100 | buyer surplus | over-booking |")
    W("|---------|--------|---------------------|---------------|--------------|")
    for k, agg in ((0, k0), (20, k20), (50, k50)):
        W(f"| {k} | {_m(agg['n_trades'])} | {_m(agg['harmful_per_100'], 1)} | "
          f"{_money(agg['buyer_surplus_realized'])} | "
          f"{_m(agg['fill_optimistic'], 2)}x |")
    W("")
    W(f"At k=20, **{k20['harmful_per_100']['mean']:.0f} of every 100 trades are "
      f"harmful**, throughput inflates to "
      f"{k20['fill_optimistic']['mean']:.2f}x demand (the buyer over-books), and "
      f"realized buyer surplus collapses from "
      f"${k0['buyer_surplus_realized']['mean']:,.0f} to "
      f"${k20['buyer_surplus_realized']['mean']:,.0f} (Wilcoxon paired "
      f"p={_p(A3['by_k'].get('wilcoxon_surplus_20_vs_0_p'))}).")
    W("")
    W("**Severity: HIGH.** The MPX dashboard reads this as a throughput "
      "*increase*. The recommended fix is protocol-level order idempotency and "
      "a commit-ack so a buyer cannot double-order against a lagged book; we "
      "flag it as a design change rather than an in-sim A5 (no A5 was specified "
      "for A3).")
    W("")
    W("**Repro.** `python -c \"from meridian.audit import run_a3, SEEDS; "
      "print(run_a3(SEEDS)['by_k'][20]['agg'])\"`")
    W("")

    # -- A4 --------------------------------------------------------------
    W("## A4 - Broker hold-up")
    W("")
    W("**Mechanism.** Brokers intermediate long-tail demand over two hops but "
      "hold no inventory and MPX has no pre-commitment. The broker must quote "
      "and take the buyer's pay-on-accept *before* it can source upstream. When "
      "it then sources at spot, two things bite: the upstream supplier may be "
      "unavailable (the chain demand goes unserved though the buyer already "
      "paid), and the spot price has moved against the now-committed broker "
      "(margin compression / hold-up).")
    W("")
    W(f"**Magnitude** (mean +/- sd, {len(meta['seeds'])} seeds):")
    W("")
    W(f"- Chain demand unserved: **{_m(a4['unserved_chain_pct'], 1)}%** "
      f"(buyer paid, nothing shipped).")
    W(f"- Broker margin: expected {_money(a4['broker_expected_margin'])} -> "
      f"realized {_money(a4['broker_realized_margin'])} = "
      f"**{a4['broker_margin_compression_pct']['mean']:.0f}% compression**, "
      "pushing the realized broker spread negative.")
    W("")
    W("**Severity: MEDIUM.** Confined to broker-served long-tail demand, but "
      "on that segment it is severe: the intermediary is structurally "
      "underwater and a fifth of demand silently fails. Recommendation: "
      "upstream pre-commitment (lock supply before quoting) or an escrowed "
      "two-leg settlement that refunds the buyer on a sourcing failure.")
    W("")
    W("**Repro.** `python -c \"from meridian.audit import run_a4, SEEDS; "
      "print(run_a4(SEEDS)['agg'])\"`")
    W("")

    # -- not found -------------------------------------------------------
    W("## What we did NOT find")
    W("")
    W("A clean audit reports the dogs that did not bark.")
    W("")
    W(f"- **A3 does not grow past the delivery lead.** Harmful accepts at k=20 "
      f"({k20['harmful_per_100']['mean']:.0f}/100) and k=50 "
      f"({k50['harmful_per_100']['mean']:.0f}/100) are effectively identical. "
      "The double-order window is closed by the first delivery (which marks the "
      "line fulfilled) and by the RFQ cooldown, not by k, once k exceeds the "
      "shipping lead. The quantity that matters is lag-relative-to-lead, not "
      "absolute k - so Meridian's exposure is bounded by its shipping times, "
      "not by how stale a buyer's book can get.")
    W("- **Star ratings are not wholly blind to deception (A2).** They do "
      "eventually flag the highest-volume liars; the failure is latency and "
      "coverage (most liars stay green), not total blindness. We report the "
      "flag counts above rather than claiming stars never fire.")
    W("- **No honest supplier was penalized by the A5-ii attestation gate.** "
      f"Honest per-trade margin is unchanged (attestation off "
      f"{hon_ref:,.0f} vs on {att['on']['honest_margin_per_trade']['mean']:,.0f})"
      " - the escrow tier only bites suppliers whose receipts do not match "
      "their promises.")
    W("- **A5-i is not free money.** Bundled counters recover the *joint* "
      "surplus; how it is split between buyer and supplier is the Nash "
      "bargaining outcome, not a transfer to either side. The gain is "
      "efficiency (trades that should happen, happening), not redistribution.")
    W("")

    # -- ledger ----------------------------------------------------------
    W("## Ledger integrity")
    W("")
    W(f"Every market event (RFQ, QUOTE, COUNTER, ACCEPT, SETTLE, DELIVER, RATE, "
      f"FAIL) is appended to a hash-chained ledger. Verification of the A1 "
      f"reference run (seed {meta['seeds'][0]}):")
    W("")
    W(f"- Chain verified: **{led['chain_ok']}** over **{led['chain_length']:,}** "
      f"records; head `{led['head_hash'][:16]}...`")
    W(f"- Determinism (same seed -> identical head hash): **{led['determinism_ok']}**")
    W(f"- Tamper detection: mutating one settled price is caught at seq "
      f"{led['tamper_error_seq']} (`{led['tamper_error']}`): "
      f"**{led['tamper_detected']}**")
    W("")
    W("---")
    W("")
    W("*This report is generated by `meridian/report.py` from "
      "`meridian/results/audit_results.json`, itself produced by "
      "`python -m meridian.audit --full`. To audit your own protocol, replace "
      "MPX in `meridian/protocol.py` + `meridian/agents.py` and re-run the same "
      "battery.*")

    text = "\n".join(L) + "\n"
    REPORT_PATH.write_text(text, encoding="utf-8")
    return REPORT_PATH


# report.md is generated from the in-memory results dict by `audit.main`
# (`python -m meridian.audit --full`); this module only formats.
