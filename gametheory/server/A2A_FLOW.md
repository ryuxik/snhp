# Two agents do a verified deal (the A2A flow)

`negotiate_turn` / `negotiate_bundle` work against **any** counterparty with zero
setup. This flow is the **advanced** path for when the **other side also runs SNHP**:
prove who you both are, and you unlock two things a lone agent can't get —

1. a **cooperation premium** (more joint surplus when both sides are verified peers
   negotiating in good faith), and
2. a **signed, settleable deal record** (an AP2 Cart Mandate) that either party can
   present later — non-repudiable, no escrow.

If the counterparty is unknown or doesn't run SNHP, **don't use this** — just call
`negotiate_turn` / `negotiate_bundle`.

## The shape of it

```
ONE-TIME, per operator (you + the counterparty each do this):
  register_operator(...)            -> a signed identity attestation
  [optional] verify_domain(...)     -> upgrade to domain-level identity (sybil-resistant)

PER DEAL:
  1. each side: build_peer_proof(...)   -> a role-bound, short-lived proof (signs LOCALLY)
  2. exchange the two proofs (over your own channel / an A2A message)
  3. one side: open_session(seller_proof, buyer_proof)
                                        -> session_id + peer_mode (TRUE only if BOTH verify)
  4. each side: next_offer(session_id, role, ...)
                                        -> recommendation using the SESSION's peer_mode
  5. on agreement: settle(session_id, agreed_price)
                                        -> a signed AP2 Cart Mandate (the deal record)
```

## Step by step (MCP names; HTTP twins are `POST /v1/...`)

**Identity (once).** Each operator generates an Ed25519 keypair and registers:

```
gt_a2a_register_operator(operator_id="acme.example",
                         public_key_b64="<your 32-byte ed25519 pubkey, base64>")
  -> {"attestation_jwt": "...", "verification_level": "self"}
```

Optionally prove domain control for a sybil-resistant identity: `gt_a2a_request_domain_challenge`
→ publish the returned DNS-TXT record → `gt_a2a_verify_domain` (lifts you to
`verification_level="domain"`, which a counterparty can require).

**1. Build a peer proof (per negotiation, signs locally).** Your operator private key
**never leaves your machine** — run this MCP server on your own host.

```
gt_a2a_build_peer_proof(operator_attestation_jwt="...", operator_id="acme.example",
                        negotiation_id="neg-2026-06-25-001", role="seller",
                        private_key_b64="<your ed25519 PRIVATE key, base64>")
  -> {"operator_attestation_jwt": "...", "sig_b64": "...", "role": "seller", "expires_at": ...}
```

**2. Exchange proofs.** Send your proof to the counterparty and receive theirs (your
channel, or as an A2A message Part). Proofs are bound to *this* `negotiation_id` and
*this* `role`, and expire — they can't be replayed elsewhere.

**3. Open the session.** Either side (or a coordinator) submits **both** proofs:

```
gt_a2a_open_session(negotiation_id="neg-2026-06-25-001",
                    seller_proof={...}, buyer_proof={...},
                    require_level="self")          # or "domain" to demand domain-verified peers
  -> {"session_id": "sess_...", "peer_mode": true, "self_deal": false, ...}
```

`peer_mode` is **server-derived**: it is `true` only if both proofs verify (at or above
`require_level`), are for their respective roles, are unexpired, and name **distinct**
operators. You cannot claim the premium by lying — a forged, revoked, below-level, or
self-dealing proof yields `peer_mode=false`.

**4. Negotiate using the session.** Each side asks for its next move; the recommender
uses the session's verified `peer_mode` (not a self-asserted flag):

```
gt_a2a_next_offer(session_id="sess_...", role="seller",
                  my_reservation=0.40,               # normalized [0,1]
                  opponent_offer_history=[...], my_offer_history=[...])
  -> {"peer_mode": true, "recommendation": {...}}
```

(Working in dollars? Map your floor/target to `[0,1]` the way `negotiate_turn` does, or
use `negotiate_turn`/`negotiate_bundle` for the math and only use this path for the
verified-peer premium + settlement.)

**5. Settle.** Once both agree on a price, mint the deal record:

```
gt_a2a_settle(session_id="sess_...", agreed_price=7500, currency="USD", item="...")
  -> {"cart_mandate": "<signed AP2 VC-JWT>"}        # + intent_mandate if you pass buyer_max_price
```

`settle` refuses unless the session is `peer_mode=true` (both verified and distinct), so
a Cart Mandate always names two real, verified parties.

## Honest scope

- **Both sides must run SNHP.** This is bilateral by design; against a non-SNHP
  counterparty there's nothing to verify — use `negotiate_turn` / `negotiate_bundle`.
- **The premium is the bilateral-cooperation figure** from the LLM tournament, not the
  single-side +12%. The mechanism (verified peers → more joint surplus) is what's proven
  here; treat the exact magnitude as directional.
- **Run `gametheory/negotiation/a2a_peer_demo.py`** for a runnable end-to-end (it derives
  `peer_mode` from a real cross-boundary attestation exchange and shows spoofers caught at
  the handshake).
