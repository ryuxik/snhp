# The certificate signing key

**Fingerprint: `sha256:57fac11a3062c2c5b4064ef5`**

Pin that string. Any certificate whose `pubkey_fpr` does not match it was not
signed by SNHP, whatever else it says. A verifier that trusts the key travelling
inside the certificate is only checking internal consistency — the fingerprint
is what ties a certificate to us.

## Why this is not the notary key

A **receipt** attests one transaction. A **certificate** attests a claim about
someone else's agent. Different trust domains, so different keys:

- if the certificate key is ever compromised, certificates are revoked and the
  receipt ledger is untouched;
- the certificate runner can live anywhere without carrying the key that signs
  customer receipts.

`load_cert_key()` reads `SNHP_CERT_KEY_PEM` and **never** falls back to
`NOTARY_KEY_PEM`. Sharing one key would silently merge the two domains.

## Minting

```bash
export SNHP_CERT_KEY_PEM="$(cat ~/.snhp/cert_key.pem)"
python -m arena.gauntlet.certify --run engine --require-persistent-key
```

`--require-persistent-key` refuses to mint when the key would be ephemeral, and
fails before spending the run rather than emitting a certificate that has to be
recalled. **Use it for anything published.**

Without `SNHP_CERT_KEY_PEM` the loader falls back to a throwaway key and marks
the certificate `key_source: ephemeral`. That is correct behaviour for local
development and tests — such a certificate proves the numbers are internally
consistent and proves nothing about who signed it. It is not an attestation.

## Key handling

- The private key lives at `~/.snhp/cert_key.pem`, mode `600`, outside the
  repository. It is never printed, logged, or committed.
- A malformed `SNHP_CERT_KEY_PEM` **raises** rather than downgrading to
  ephemeral — a silent swap would invalidate every prior certificate unnoticed.
- To rotate: generate a new key, publish the new fingerprint here, and re-mint.
  Certificates signed by the old key stay verifiable against the old
  fingerprint; say so publicly rather than reissuing silently.

```bash
python -m core.notary keygen > ~/.snhp/cert_key.pem && chmod 600 ~/.snhp/cert_key.pem
```
