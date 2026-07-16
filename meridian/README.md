# MERIDIAN — a fictional customer, a real audit

**Meridian Procurement Systems** is a fictional company ("agentic checkout for B2B"); its exchange protocol **MPX v1** is real, runnable code implementing the design patterns shipping in 2026 agent-commerce systems (optimistic pay-on-accept settlement, price-only counters, self-reported star ratings, two-hop broker chains). This package builds MPX faithfully — the flaws are *design patterns of a naive-but-competent protocol*, not planted bugs — then runs the snhp mechanism-audit battery A1–A5 against it for real: A1 measures the surplus a price-only protocol structurally cannot express (oracle vs bargaining), A2 the profit a rule-abiding liar extracts under optimistic settlement, A3 the harm a stale-book buyer self-inflicts, A4 broker hold-up with no pre-commitment, and A5 the two measured fixes (bundled counters via the repo's `snhp` `nash_solver`; attestation-gated escrow). Every figure regenerates from ≥8 seeded runs with means ± sd and Wilcoxon tests, every market event is recorded on a self-contained hash-chained ledger (determinism and tamper-detection both tested), and findings that did not materialize are reported as such. This is the public sample deliverable for the audit service: to audit a real protocol, swap MPX in `protocol.py` + `agents.py` and re-run the same battery.

```
python -m meridian.audit --full     # regenerates results/audit_results.json + report.md
python -m pytest meridian/test_meridian.py -q
```

Layout: `protocol.py` (MPX messages + state machine), `agents.py` (buyer/supplier/broker + deceptive/stale variants + the shared utility/cost functions the auditor also scores against), `market.py` (seeded tick loop, settlement, delivery, ratings, metrics, ledger), `audit.py` (A1–A5 battery + oracle + nash bundle), `report.py` (renders `report.md`), `ledger.py` (hash-chained event log), `test_meridian.py`.
