# Trust model — what the A2A / AP2 layer does and does NOT guarantee

Honest answer to "is the verified-peer moat real cryptographic substance or theater?"
The handshake crypto is **real**; the trust **fabric is single-vendor**. Read this
before relying on any "verified" or "non-repudiable" guarantee for value.

## What is real (and tested)

- **Genuine Ed25519 commit/verify.** A peer proof binds `operator_id | role |
  negotiation_id | expires_at` and is signed with the operator's key, which never
  leaves the operator's host. `open_session` DERIVES `peer_mode` server-side; a
  forged, revoked, below-level, cross-role-replayed, expired, or self-dealing proof
  fails **closed** to `peer_mode=false`. Sticky revocation; no-downgrade
  re-registration. (~65 crypto/A2A tests.)
- **The cooperation premium is a falsifiable MECHANISM, not a reported bonus.**
  `peer_mode` actually forks strategy in `gametheory/negotiation/_peer.py` /
  `sell.py` (verified peers run cooperative signalling→descent instead of adversarial
  Rubinstein). You can re-run with `peer_mode=false` and measure the delta.
- **Key separation (added).** The registry-CA / first-strike key and the AP2
  settlement-notary key are now **distinct** keys (the notary is HKDF-derived from
  the root), so a settlement-key compromise cannot forge operator identities, and
  vice versa. Published at `/v1/keys/trust_anchor` and `/v1/keys/settlement_notary`.

## What is NOT guaranteed (the honest limits)

- **Single vendor-held root.** Both the registry-CA and settlement-notary keys derive
  from one secret (`FIRST_STRIKE_PRIVATE_PEM`) that the vendor controls. A Cart Mandate
  is non-repudiable **to third parties and between the two counterparties**, but **NOT
  against the vendor** — whoever holds the root can in principle mint an identity or
  re-sign a record. **Do not move real money on the VC-JWT alone.** Treat it as a
  signed deal record, not an escrow or a settlement guarantee.
- **Default `require_level="self"` has NO sybil resistance.** Anyone can register any
  unclaimed `operator_id`. Only `require_level="domain"` carries an identity claim —
  and that rests on a DNS-TXT check over DNS-over-HTTPS to `dns.google` with **no
  DNSSEC validation**, so a poisoned/MITM'd resolution could forge a domain identity.
  Domain-level is "better than self," not "strong." **Require `domain` for anything
  that matters, and understand its ceiling.**
- **Server clock, no external timestamp.** Commitment/issuance times use the server
  clock; a compromised server could back-date undetectably (no RFC-3161 timestamp
  authority yet).
- **No transparency log.** There is no append-only public log of issued attestations /
  mandates, so a third party cannot independently audit what the anchor has signed.

## Hardening roadmap

Each phase is **demand-triggered** — we build it when a real use case crosses the
trigger, not before. The current state is pilot/demo-grade: real crypto, real
mechanism, single-vendor trust — fine for a controlled bilateral pilot, not yet for
autonomously settling value between mutually-distrusting parties.

| Phase | What | What it buys | Trigger | Effort |
|---|---|---|---|---|
| **0 — done** | Separate registry-CA and settlement-notary keys (HKDF-derived); this honest doc | A settlement-key leak can't forge identities; reviewers know exactly what they're trusting | — | done |
| **1 — pre-money** | Validate DNSSEC on the domain TXT lookup; make `require_level="domain"` the default for any settle path | Closes the DNS-poisoning forge of a domain identity; no silent `self`-level settlement | Before the first deal that names a real counterparty | small |
| **2 — before real value** | Move the root key into KMS/HSM (AWS KMS / GCP KMS), sign via the API; publish a rotation + revocation policy | Server compromise ≠ root compromise; the vendor becomes a hard target, not an env var | Before settling actual money | medium |
| **3 — multi-party / audit** | RFC-3161 external timestamp authority on issuance; append-only transparency log (Sigstore Rekor / Trillian) of attestations + mandates | The vendor can't back-date undetectably; third parties can audit what the anchor signed | When >2 independent operators settle, or a counterparty demands auditability | medium-large |
| **4 — decentralize** | Replace the single self-signed root with external anchors — operator-controlled domain certs / DIDs / real PKI | Trust no longer routes through one vendor key; "non-repudiable" holds **against the vendor too** | When mutually-distrusting parties settle without a shared trusted operator | large (architecture) |

The honest line stays with each phase: until Phase 4, every "verified" / "non-repudiable"
guarantee ultimately reduces to "trust the operator of this anchor." Phases 1–3 make that
operator progressively harder to compromise or cheat; Phase 4 removes the dependency.
