# SNHP-NX/1 — the Missing Layer

An open extension that gives a checkout-shaped agent-payment protocol a place to
negotiate a package. Protocols in the ACP/AP2 mold resolve a cart or RFQ to one
fixed price, so two issues that trade off against each other — quantity against
delivery date, scope against price — cannot be moved in a single message. NX
mounts between the host's cart/RFQ step and its payment-intent step, carries
whole-package proposals across every issue, and hands a settled package back for
the host to pay for. It moves no money and holds no goods; it bounds the
negotiation, forbids pricing any line above its listed price, and exposes a
canonical transcript hash that any attestor can sign. It is a mount, not a fork:
a host that has never heard of NX is unaffected by two peers that both speak it.

## Evidence, including the part that failed

We registered a kill before writing the experiment (`PREREG.md`) and reported it
as it landed (`results/RESULTS.md`). Over 240 seeded procurement scenarios on a
checkout-shaped host, the pre-registered claim — that bundling is structurally
necessary for machine trade to happen at all — **died**: price-only haggling
reached **94.2%** of NX's deal-formation rate (0.942 vs 1.000, against a 0.80
kill threshold), because a price ZOPA already exists at the seller's quoted terms
in 226 of 240 scenarios. What survived is narrower and is what the spec now rests
on: package deals raise realized joint surplus — NX captured **0.928** of oracle
surplus against **0.889** for price-only and **0.880** for plain checkout, +3.9
points of the achievable pie — and in constrained regimes (tight deadlines,
conflicting requirements) price-only recovers only **0.696** of NX's deal
formation, so there bundling is load-bearing for the deal existing at all. A
checkout-shaped protocol can express neither. Every number regenerates:
`python -m nx.experiment` for the pre-registered set and
`python -m nx.experiment --regime constrained` for the constrained regime — the
latter prints its own not-pre-registered label, because it locates a boundary
rather than establishing a headline.

## Run the conformance suite against your own implementation

`test_nx.py` is portable. Point `NX_IMPL` at a module exposing the reference
names with the same signatures and the suite runs against your classes:

```
python -m pytest nx/test_nx.py -q                    # reference implementation
NX_IMPL=your_pkg.nx_adapter python -m pytest nx/test_nx.py -q
```

Your adapter must expose `Line`, `ListSchedule`, `NXQuote`, `NXPropose`,
`NXAccept`, `NXDecline`, `NXSession`, `NXReceipt`, `State`, `NXViolation`,
`NXProtocolError`, `schedule_key`, `message_from_wire`, and `verify_transcript`
— constructors raising `NXViolation` on an above-list or off-schedule line, and
`NXProtocolError` on an illegal transition or an exceeded round bound. The full
contract is in the `test_nx.py` module docstring. The pinned transcript hash is a
property of the canonical encoding (sorted-key JSON, no whitespace, SHA-256), so
any conforming implementation reproduces it byte-for-byte. MPX-specific bridge
tests skip automatically when `nx.bridge` is absent.

## Layout

| file | what it is |
|---|---|
| `SPEC.md` | the citable specification — session model, messages, invariants I1–I4, wire format, host-mapping appendix, evidence |
| `PREREG.md` | the kill, registered before the experiment existed |
| `protocol.py` | reference implementation of the state machine and messages |
| `bridge.py` | worked mount onto MPX (`meridian/`), with the SNHP notary as one conforming attestor |
| `test_nx.py` | conformance suite (23 tests, no network, deterministic) |
| `experiment.py` | the three-arm experiment |
| `results/RESULTS.md` | the verdict, the fired kill, and the caveats |
| `results/experiment.json` | per-scenario records |

## Versioning and citation

Wire protocol id `snhp-nx/1`. Additions that leave invariants I1–I4 and the
canonical-hash input untouched are minor and MUST be ignorable by an older
reader; any change to an invariant or to the hash input is a new major
(`snhp-nx/2`). The transcript hash covers the protocol string, so a receipt is
bound to the version that produced it.

> SNHP-NX/1 — the Missing Layer: a package-negotiation extension for
> checkout-shaped agent-payment protocols. SNHP, 2026.
> Specification: `nx/SPEC.md`. Evidence: `nx/PREREG.md`, `nx/results/RESULTS.md`.
