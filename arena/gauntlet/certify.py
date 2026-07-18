"""arena/gauntlet/certify.py — the GAUNTLET CERTIFICATE: signed, offline-
verifiable certification of a negotiation agent's gauntlet performance.

A GauntletCertificate is the leaderboard's shippable artifact — the "MLPerf/UL
receipt" for a negotiating agent. It is built with the same DNA as
`core.notary` (canonical-JSON hashing, Ed25519 via env `NOTARY_KEY_PEM` else an
ephemeral key with `key_source` exposed, offline verify with only the public
key) and it reuses core.notary's helpers directly rather than reimplementing
the crypto.

SPEC HISTORY (each bump is a protocol change, disclosed):
  /1  capture primary vs the single EngineSeat counterparty — the registered
      capture kill FIRED (certs/SEPARATION.md §1).
  /2  logroll primary (post-hoc re-cut) — held-out validation FAILED
      (certs/SEPARATION.md §2).
  /3  CURRENT. The pre-registered PROTOCOL change (PREREG-pool.md): the
      candidate plays a declared POOL of scripted counterparties
      (naive | hardball | conceder, parameters frozen by the registration) and
      the primary certified claim is POOLED OWN-UTILITY vs the naive baseline
      on the same pool. The registered experiment SURVIVED on both the public
      and a never-before-used held-out scenario set (certs/POOL-RESULTS.md:
      delta +0.107/+0.109, p=0.0001/0.0001, every pool member separating
      individually).

WHAT A CERTIFICATE ATTESTS (exactly this, and nothing more):

  (a)  a run happened       — the named CANDIDATE played the FIXED, versioned
                              gauntlet scenario set (n, seed, n_issues, protocol
                              DEADLINE) under a pinned CODE VERSION (git HEAD
                              short hash), against the DECLARED counterparty
                              POOL recorded in the certificate (`pool`:
                              members + frozen parameters + registration). The
                              exact `replay.command` regenerates it.
  (b)  these metrics         — computed from the run's match records and
                              RE-DERIVABLE from the per-match summary rows the
                              certificate carries. The PRIMARY certified
                              statistic is POOLED OWN-UTILITY (the candidate's
                              true-weight utility, BATNA when no deal), mean
                              over all pool matches + a seeded 95% bootstrap
                              CI, with a per-counterparty breakdown. CAPTURE
                              and LOGROLL are SECONDARY context — see the
                              caveats below. Also: n_matches, deal_rate,
                              dollars_left mean, format_failure total. A
                              verifier recomputes every one of these FROM THE
                              EMBEDDED ROWS, so a metric edited to flatter the
                              candidate is caught even when the JSON still
                              looks well-formed.
  (c)  the baseline gap      — the SAME scenario set x pool run by the naive
                              split-the-difference baseline seat, with
                              `delta_own_utility` paired by (scenario_id, role,
                              counterparty) and a seeded, deterministic,
                              two-sided sign-flip PERMUTATION-TEST p-value
                              (n_perm=10000), plus per-counterparty deltas and
                              p-values (a pool that separates via one member
                              only is visible as exactly that). Secondary
                              capture/logroll deltas are reported with their
                              own p-values (logroll: scored-both pairing with
                              the pair count).
  (d)  who signed it         — canonical-JSON sha256 payload hash, an Ed25519
                              signature, the public key (raw b64 + PEM), a key
                              fingerprint, `key_source` ("env" | "ephemeral"),
                              and a UTC timestamp. The private key is never
                              printed, logged, or serialized.

WHAT IT DOES NOT ATTEST:

  - FUTURE performance, or performance on ANY scenario outside this exact
    (n, seed, n_issues, deadline, code_version) set — the number is in-sample
    by construction (`not_attested`);
  - OUT-OF-DISTRIBUTION scenarios — a different generator, seed, or issue
    count is a different gauntlet and needs its own certificate;
  - performance against counterparties OUTSIDE the declared pool — the pooled
    own-utility claim is vs the three frozen scripted counterparties recorded
    in `pool`, not vs LLMs, humans, or any other opponent;
  - the candidate's real-world IDENTITY beyond the opaque `candidate_digest`
    the submitter supplied. The certificate binds the digest to the metrics; it
    does NOT prove what code, model, or human produced the moves. A self-signed
    certificate with an ephemeral key proves internal consistency, NOT that any
    particular vendor stands behind it — verifiers MUST pin `pubkey_fpr`
    against a key published out-of-band to trust the signer;
  - CANDIDATE SKILL via capture — capture is a JOINT/pair efficiency metric;
    against a logrolling counterparty a naive splitter is carried to ~90% of
    the ceiling. A pre-registered capture kill FIRED on exactly this point
    (certs/SEPARATION.md §1). Capture here is context only;
  - CANDIDATE SKILL via logroll — logroll was tried as a post-hoc primary
    after the capture kill and FAILED its held-out validation vs the EngineSeat
    counterparty (certs/SEPARATION.md §2). Logroll here is context only;
  - anything about runs THIS certificate did not sign. Each certificate stands
    alone; there is no chain.

KEYS: identical policy to core.notary — signing key from env `NOTARY_KEY_PEM`
(PKCS8 PEM) else an ephemeral key generated this process (`key_source`
"ephemeral"), so a verifier can SEE that a throwaway key signed a certificate.
DEPENDENCY DIRECTION: this module imports the crypto DNA from core.notary and
the pool/run machinery from arena.gauntlet; nothing imports it back
(pool_experiment imports only the statistics helpers).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# Reuse core.notary's crypto DNA verbatim — same canonical hashing, same
# env-or-ephemeral key policy, same fingerprint/verify helpers. We do NOT
# reimplement any of it; a certificate is a notary receipt's sibling.
from core.notary import (
    _b64d,
    _canon_bytes,
    _fingerprint,
    _load_pub,
    NotaryKey,
    canon_hash,
    generate_key_pem,
    load_notary_key,
)

SPEC_VERSION = "gauntlet-cert/3"
PRIMARY_STATISTIC = "own_utility_pooled"

# The CERTIFIED CLAIM is fixed by SPEC_VERSION. `content_revision` tracks
# ADDITIVE, non-claim-changing content within a spec (Amendment 1's reference
# tier is additive context, so the spec stays /3 and this bumps instead).
CONTENT_REVISION = 2
_CHANGELOG = [
    "3.1 — gauntlet-cert/3: primary claim = pooled own-utility vs the frozen "
    "three (naive, hardball, conceder); registered pool experiment SURVIVED on "
    "public + held-out sets (PREREG-pool.md, certs/POOL-RESULTS.md)",
    "3.2 — ADDITIVE: `reference_tier` block (counterparty snhp-engine) with its "
    "registered prediction and outcome (PREREG-pool.md Amendment 1). Reported "
    "context only; the certified claim is UNCHANGED and the reference tier is "
    "never pooled into the primary statistic",
]

# ── deterministic-analysis constants (documented so a third party recomputes
#    the EXACT same CIs and p-values). The same two derived seeds are used for
#    every statistic; the data vectors differ, so the draws differ. ──────────
_BOOT_B = 10000                 # bootstrap resamples per 95% CI
_BOOT_XOR = 0x1B007B00          # seed = scenario_seed ^ this  (mnemonic: "boot")
_N_PERM = 10000                 # permutation-test resamples per baseline gap
_PERM_XOR = 0x9E3779B9          # seed = scenario_seed ^ this  (golden ratio)
_PERM_STAT = "paired_signflip_mean_diff"
_TOL = 1e-9

# fields added by signing — everything ELSE is the signed "content"
_SIGNING_FIELDS = frozenset({
    "payload_sha256", "pubkey_b64", "pubkey_pem", "pubkey_fpr",
    "key_source", "algo", "signed_at", "cert_sig",
})

_NOT_ATTESTED = [
    "future performance — the metrics are in-sample on exactly this scenario set",
    "out-of-distribution scenarios — a different generator/seed/n_issues is a "
    "different gauntlet and needs its own certificate",
    "performance against counterparties OUTSIDE the declared pool — the pooled "
    "own-utility claim is vs the three frozen scripted counterparties recorded "
    "in this certificate's `pool` field (registration: PREREG-pool.md; "
    "validation: certs/POOL-RESULTS.md), not vs LLMs, humans, or any other "
    "opponent",
    "the candidate's real-world identity beyond the opaque candidate_digest the "
    "submitter supplied — a self-signed certificate does not prove what code or "
    "model produced the moves; pin pubkey_fpr against a key published out-of-band",
    "candidate skill via CAPTURE — a joint/pair metric; a pre-registered capture "
    "kill FIRED (certs/SEPARATION.md, section 1); capture here is context only",
    "candidate skill via LOGROLL — tried as a post-hoc primary after the capture "
    "kill and its held-out validation FAILED vs the EngineSeat counterparty "
    "(certs/SEPARATION.md, section 2); logroll here is context only",
    "statistical significance beyond the reported permutation p-values — they "
    "are REPORTED alongside the deltas; the protocol-level evidence that this "
    "primary statistic separates competent play from the naive baseline is the "
    "registered pool experiment (certs/POOL-RESULTS.md: SURVIVE on public + "
    "held-out sets)",
    "the REFERENCE TIER (`reference_tier`, counterparty snhp-engine) — it is "
    "REPORTED CONTEXT, NOT part of the certified claim. It is measured on the "
    "same statistic but is never pooled into the primary, per PREREG-pool.md "
    "Amendment 1; its registered prediction is that it catches weakness and "
    "cannot rank strength. Nothing in that block strengthens or weakens the "
    "certified pooled-own-utility claim against the frozen three",
    "anything about runs this certificate did not sign — each certificate stands "
    "alone, there is no chain",
]

# Amendment 1: the reference counterparty is reported alongside the certified
# claim but MUST NEVER appear among the pool rows that feed the primary
# statistic. certify() enforces this structurally (see _REFERENCE_CP checks).
_REFERENCE_CP = "snhp-engine"
_REFERENCE_SUMMARY = pathlib.Path(__file__).with_name("certs") / "reference-tier.json"


# ── time / code version ─────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git_head() -> str:
    """The pinned code version: $SOURCE_VERSION if set (deployed images have no
    .git), else the short git HEAD, else 'unknown'. Recorded in the scenario-set
    pin so a verifier knows which code produced the run."""
    env = os.environ.get("SOURCE_VERSION", "").strip()
    if env:
        return env[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


# ── per-match summary rows (the re-derivation fuel) ─────────────────────────
def _as_row(m) -> dict:
    """One canonical, rounded per-match summary row from a MatchResult (or an
    equivalent dict). Small on purpose — this is what travels in the
    certificate and what a verifier recomputes the metrics from. Rounding is
    applied ONCE, here, so certify() and verify_certificate() see identical
    numbers. `counterparty` comes from an explicit key or the run_pool_match
    condition ("pool-<name>"); a row without one is refused — the /3 claim is
    per-pool-member paired and unlabeled rows cannot pair."""
    d = m.to_dict() if hasattr(m, "to_dict") else dict(m)
    cp = d.get("counterparty")
    if cp is None:
        cond = str(d.get("condition", ""))
        cp = cond[5:] if cond.startswith("pool-") else None
    if not cp:
        raise ValueError(
            "match row has no counterparty label (need 'counterparty' or a "
            "'pool-<name>' condition) — cannot build a /3 pool certificate")
    lr = d.get("logroll")
    return {
        "scenario_id": int(d["scenario_id"]),
        "role": str(d["role"]),
        "counterparty": str(cp),
        "u": round(float(d["u_candidate"]), 4),
        "capture": round(float(d["capture"]), 4),
        "deal": bool(d["deal"]),
        "joint": round(float(d["joint"]), 4),
        "logroll": (None if lr is None else round(float(lr), 4)),
        "dollars_left": round(float(d["dollars_left"]), 2),
        "format_failures": int(d.get("format_failures", 0)),
    }


def _key(r: dict) -> tuple:
    return (int(r["scenario_id"]), str(r["role"]), str(r["counterparty"]))


def _sorted_rows(rows) -> list:
    return sorted(rows, key=_key)


# ── the deterministic statistics (ONE implementation, used by certify AND
#    verify AND the pool experiment) ─────────────────────────────────────────
def bootstrap_mean_ci(values, seed: int, *, b: int = _BOOT_B,
                      alpha: float = 0.05) -> Optional[list]:
    """Seeded percentile-bootstrap (1-alpha) CI of the mean of `values`.
    Deterministic: numpy's PCG64 stream is stable across versions, so a third
    party recomputes the same interval. Returns [lo, hi] rounded to 6dp, or
    None for an empty vector."""
    v = np.asarray(list(values), dtype=float)
    n = len(v)
    if n == 0:
        return None
    rng = np.random.default_rng(seed ^ _BOOT_XOR)
    idx = rng.integers(0, n, size=(b, n))
    means = v[idx].mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return [round(float(lo), 6), round(float(hi), 6)]


def paired_permutation_pvalue(diffs, seed: int, *, n_perm: int = _N_PERM) -> float:
    """Two-sided paired sign-flip permutation p-value for mean(diffs) != 0.
    Under H0 the sign of each within-pair difference is exchangeable, so we
    randomly negate each difference. Deterministic (seeded PCG64). Uses the
    +1/+1 correction so p is never exactly 0. Returns a float rounded to 6dp."""
    d = np.asarray(diffs, dtype=float)
    m = len(d)
    if m == 0:
        return 1.0
    obs = abs(float(d.mean()))
    rng = np.random.default_rng(seed ^ _PERM_XOR)
    signs = rng.integers(0, 2, size=(n_perm, m)) * 2 - 1
    perm_means = np.abs((signs * d).mean(axis=1))
    count = int(np.sum(perm_means >= obs - 1e-12))
    return round((count + 1) / (n_perm + 1), 6)


def _perm_block(p_value, n_pairs: int, pairing: str) -> dict:
    return {
        "statistic": _PERM_STAT,
        "n_perm": _N_PERM,
        "two_sided": True,
        "paired_by": "(scenario_id, role, counterparty)",
        "pairing": pairing,
        "n_pairs": int(n_pairs),
        "p_value": p_value,
    }


def _round_opt(v, nd: int = 6):
    return None if v is None else round(float(v), nd)


def _reference_from_rows(cand_rows, base_rows, seed: int) -> tuple[dict, bool]:
    """Amendment 1: the SNHP-REFERENCE tier statistic, computed by the SAME
    own-utility / pairing / permutation procedure as the primary — but kept in
    its OWN structure so it can never be summed into the certified claim.
    Returns (block, paired_ok); block is None-valued when there are no rows."""
    cand = _sorted_rows(cand_rows)
    base = _sorted_rows(base_rows)
    if not cand and not base:
        return {}, True
    ckey = {_key(r): r for r in cand}
    bkey = {_key(r): r for r in base}
    keys = sorted(set(ckey) & set(bkey))
    paired_ok = bool(keys) and set(ckey) == set(bkey) \
        and len(keys) == len(cand) == len(base)
    cu = np.asarray([float(ckey[k]["u"]) for k in keys], dtype=float)
    bu = np.asarray([float(bkey[k]["u"]) for k in keys], dtype=float)
    diffs = cu - bu
    return {
        "n_pairs": len(keys),
        "candidate_own_utility": round(float(cu.mean()), 6) if len(cu) else None,
        "baseline_own_utility": round(float(bu.mean()), 6) if len(bu) else None,
        "delta_own_utility": round(float(diffs.mean()), 6) if len(diffs) else None,
        "p_value": (paired_permutation_pvalue(diffs, seed) if len(diffs) else None),
    }, paired_ok


def _load_reference_outcome() -> tuple[str, str, str]:
    """(prediction, outcome, source) from the registered experiment's summary.
    The outcome is a FINDING of the two-set experiment, so it is sourced from
    certs/reference-tier.json rather than hardcoded here; if the file is absent
    the certificate says 'not_evaluated' honestly instead of guessing."""
    try:
        d = json.loads(_REFERENCE_SUMMARY.read_text())
        return (str(d.get("prediction", "")),
                str(d.get("prediction_outcome", "not_evaluated")),
                "certs/reference-tier.json (arena.gauntlet.pool_experiment)")
    except (OSError, json.JSONDecodeError, ValueError):
        return ("", "not_evaluated",
                "unavailable — run python -m arena.gauntlet.pool_experiment")


def _metrics_from_rows(cand_rows, base_rows, seed: int,
                       baseline_name: str = "naive-baseline") -> tuple[dict, bool]:
    """Recompute EVERY certified metric from the per-match rows. The single
    source of truth: certify() calls it to fill the certificate, and
    verify_certificate() calls it to check the certificate wasn't edited.

    PRIMARY: pooled own-utility — mean + seeded bootstrap CI over all matches;
    baseline delta paired by (scenario_id, role, counterparty), sign-flip
    permutation p; per-counterparty breakdown (delta + p per pool member).
    SECONDARY: capture (all pairs) and logroll (scored-both pairs, pair count
    reported), each with mean/CI/delta/p.

    Returns (metrics, paired_ok). paired_ok is False when the candidate and
    baseline rows are not the SAME scenario-set x pool (their (scenario_id,
    role, counterparty) key sets differ) — the caller must fail closed."""
    cand = _sorted_rows(cand_rows)
    base = _sorted_rows(base_rows)
    n = len(cand)

    u = np.asarray([r["u"] for r in cand], dtype=float)
    cap = np.asarray([r["capture"] for r in cand], dtype=float)
    deal_rate = round(float(np.mean([1.0 if r["deal"] else 0.0 for r in cand])), 6) \
        if n else 0.0
    lr_scored = [float(r["logroll"]) for r in cand if r["logroll"] is not None]
    dl_mean = round(float(np.mean([r["dollars_left"] for r in cand])), 4) if n else 0.0
    fmt_total = int(sum(int(r["format_failures"]) for r in cand))

    bu = np.asarray([r["u"] for r in base], dtype=float)
    bcap = np.asarray([r["capture"] for r in base], dtype=float)
    blr_scored = [float(r["logroll"]) for r in base if r["logroll"] is not None]

    # scenario-set x pool identity: keys must cover the whole set exactly
    ckey = {_key(r): r for r in cand}
    bkey = {_key(r): r for r in base}
    keys = sorted(set(ckey) & set(bkey))
    paired_ok = bool(keys) and set(ckey) == set(bkey) \
        and len(keys) == len(cand) == len(base)

    # PRIMARY: pooled own-utility
    u_diffs = np.asarray([float(ckey[k]["u"]) - float(bkey[k]["u"])
                          for k in keys], dtype=float)
    u_delta = round(float(u_diffs.mean()), 6) if len(u_diffs) else 0.0
    u_p = paired_permutation_pvalue(u_diffs, seed)

    # per-counterparty breakdown (sorted member names, deterministic)
    members = sorted({k[2] for k in keys})
    per_cp = {}
    for cp in members:
        cp_keys = [k for k in keys if k[2] == cp]
        cd = np.asarray([float(ckey[k]["u"]) for k in cp_keys], dtype=float)
        bd = np.asarray([float(bkey[k]["u"]) for k in cp_keys], dtype=float)
        diffs = cd - bd
        per_cp[cp] = {
            "n_pairs": len(cp_keys),
            "candidate_u": round(float(cd.mean()), 6) if len(cd) else None,
            "baseline_u": round(float(bd.mean()), 6) if len(bd) else None,
            "delta": round(float(diffs.mean()), 6) if len(diffs) else None,
            "p_value": (paired_permutation_pvalue(diffs, seed)
                        if len(diffs) else None),
        }

    # SECONDARY: capture (all pairs) and logroll (scored-both)
    cap_diffs = np.asarray([float(ckey[k]["capture"]) - float(bkey[k]["capture"])
                            for k in keys], dtype=float)
    cap_delta = round(float(cap_diffs.mean()), 6) if len(cap_diffs) else 0.0
    cap_p = paired_permutation_pvalue(cap_diffs, seed)
    lr_keys = [k for k in keys
               if ckey[k]["logroll"] is not None and bkey[k]["logroll"] is not None]
    lr_diffs = np.asarray([float(ckey[k]["logroll"]) - float(bkey[k]["logroll"])
                           for k in lr_keys], dtype=float)
    lr_delta = round(float(lr_diffs.mean()), 6) if len(lr_diffs) else None
    lr_p = paired_permutation_pvalue(lr_diffs, seed) if len(lr_diffs) else None

    metrics = {
        "candidate": {
            "primary_statistic": PRIMARY_STATISTIC,
            "n_matches": n,
            "deal_rate": deal_rate,
            "own_utility_mean": round(float(u.mean()), 6) if n else 0.0,
            "own_utility_ci95": bootstrap_mean_ci(u, seed),
            "capture_mean": round(float(cap.mean()), 6) if n else 0.0,
            "capture_ci95": bootstrap_mean_ci(cap, seed),
            "logroll_mean": (_round_opt(np.mean(lr_scored))
                             if lr_scored else None),
            "logroll_ci95": bootstrap_mean_ci(lr_scored, seed),
            "logroll_n_scored": len(lr_scored),
            "dollars_left_mean": dl_mean,
            "format_failure_total": fmt_total,
            "ci_method": "percentile_bootstrap",
            "bootstrap_b": _BOOT_B,
            "bootstrap_seed": int(seed ^ _BOOT_XOR),
        },
        "baseline": {
            "name": baseline_name,
            "n_matches": len(base),
            "own_utility_mean": round(float(bu.mean()), 6) if len(bu) else 0.0,
            "delta_own_utility": u_delta,
            "perm_test_own_utility": _perm_block(u_p, len(u_diffs), "all"),
            "per_counterparty": per_cp,
            "capture_mean": round(float(bcap.mean()), 6) if len(bcap) else 0.0,
            "delta_capture": cap_delta,
            "perm_test_capture": _perm_block(cap_p, len(cap_diffs), "all"),
            "logroll_mean": (_round_opt(np.mean(blr_scored))
                             if blr_scored else None),
            "delta_logroll": lr_delta,
            "perm_test_logroll": _perm_block(lr_p, len(lr_diffs), "scored-both"),
            "perm_seed": int(seed ^ _PERM_XOR),
        },
    }
    return metrics, paired_ok


# ── certify (pure, testable) ────────────────────────────────────────────────
def certify(results, baseline_results, meta: dict,
            reference_results=None, baseline_reference_results=None) -> dict:
    """Build an UNSIGNED certificate dict from a candidate's pool run and the
    naive baseline's pool run on the SAME scenario set. Pure and deterministic.

    `meta` must carry:
      candidate_name    - the row's display name
      candidate_digest  - an OPAQUE, non-secret digest the runner supplies to
                          identify the candidate (e.g. a container-image hash);
                          the certificate binds it but does not interpret it
      scenario_set      - {n, seed, n_issues, deadline, code_version}
      replay_command    - the exact command that regenerates the run
    optional:
      baseline_name (default "naive-baseline"), generated (UTC ISO).

    The `pool` section (members + frozen parameters + registration pointer) is
    stamped from arena.gauntlet.pool so the certificate SAYS which pool the
    claim is against. RAISES ValueError if the candidate and baseline runs are
    not the identical scenario-set x pool — a baseline comparison across
    different matches is a lie."""
    from arena.gauntlet.pool import POOL_MEMBERS, POOL_PARAMETERS
    cand_rows = _sorted_rows(_as_row(m) for m in results)
    base_rows = _sorted_rows(_as_row(m) for m in baseline_results)
    ss = meta["scenario_set"]
    seed = int(ss["seed"])
    baseline_name = meta.get("baseline_name", "naive-baseline")

    # STRUCTURAL GUARD (PREREG-pool.md Amendment 1): the reference counterparty
    # must never reach the certified statistic. Refuse rather than silently
    # pooling it — this is the forking-paths error the registration forbids.
    stray = sorted({r["counterparty"] for r in cand_rows + base_rows
                    if r["counterparty"] == _REFERENCE_CP})
    if stray:
        raise ValueError(
            f"reference counterparty {_REFERENCE_CP!r} found among the POOL "
            f"rows that feed the primary statistic — refusing to certify. The "
            f"reference tier is reported context only (Amendment 1); pass it "
            f"via reference_results/baseline_reference_results instead.")
    off_pool = sorted({r["counterparty"] for r in cand_rows + base_rows
                       if r["counterparty"] not in POOL_MEMBERS})
    if off_pool:
        raise ValueError(
            f"pool rows contain counterparties outside the frozen pool "
            f"{list(POOL_MEMBERS)}: {off_pool} — the certified claim is defined "
            f"against the frozen three only")

    metrics, paired_ok = _metrics_from_rows(cand_rows, base_rows, seed,
                                            baseline_name=baseline_name)
    if not paired_ok:
        raise ValueError(
            "candidate and baseline runs are not the SAME scenario-set x pool "
            "(their (scenario_id, role, counterparty) keys differ) — refusing "
            "to certify a meaningless baseline comparison")

    # ── the reference tier: own structure, own rows, never pooled ───────────
    ref_rows = _sorted_rows(_as_row(m) for m in (reference_results or []))
    ref_base_rows = _sorted_rows(_as_row(m) for m in
                                 (baseline_reference_results or []))
    bad_ref = sorted({r["counterparty"] for r in ref_rows + ref_base_rows
                      if r["counterparty"] != _REFERENCE_CP})
    if bad_ref:
        raise ValueError(
            f"reference rows must all carry counterparty {_REFERENCE_CP!r}; "
            f"found {bad_ref}")
    ref_stat, ref_paired = _reference_from_rows(ref_rows, ref_base_rows, seed)
    if not ref_paired:
        raise ValueError(
            "reference-tier candidate and baseline rows are not the same "
            "(scenario_id, role) set — refusing to certify a broken pairing")
    prediction, outcome, source = _load_reference_outcome()

    cert = {
        "spec_version": SPEC_VERSION,
        "content_revision": CONTENT_REVISION,
        "changelog": list(_CHANGELOG),
        "candidate": {
            "name": str(meta["candidate_name"]),
            "candidate_digest": str(meta["candidate_digest"]),
        },
        "scenario_set": {
            "n": int(ss["n"]),
            "seed": seed,
            "n_issues": int(ss.get("n_issues", 4)),
            "deadline": int(ss["deadline"]),
            "code_version": str(ss["code_version"]),
            "generator": "arena.gauntlet.protocol.gen_gauntlet_scenarios",
        },
        "pool": {
            "members": list(POOL_MEMBERS),
            "parameters": {k: float(v) for k, v in POOL_PARAMETERS.items()},
            "registration": "arena/gauntlet/PREREG-pool.md",
            "validation": ("certs/POOL-RESULTS.md — registered experiment "
                           "SURVIVED on public (20260709) and held-out "
                           "(20260718) sets"),
            "runner": "arena.gauntlet.pool.run_pool_match",
        },
        "metrics": metrics["candidate"],
        "baseline": metrics["baseline"],
        "reference_tier": {
            "counterparty": _REFERENCE_CP,
            "scope": ("REPORTED CONTEXT — not part of the certified claim; "
                      "never pooled into the primary statistic "
                      "(PREREG-pool.md Amendment 1)"),
            "protocol": "the original gauntlet: EngineSeat as counterparty",
            "statistic": "own_utility (same pairing + permutation as primary)",
            "this_scenario_set": ref_stat,
            "prediction": prediction,
            "prediction_outcome": outcome,
            "prediction_outcome_source": source,
            "both_sets": "certs/POOL-RESULTS.md + certs/reference-tier.json",
            "registration": "arena/gauntlet/PREREG-pool.md Amendment 1",
        },
        "per_match": {"candidate": cand_rows, "baseline": base_rows,
                      "candidate_reference": ref_rows,
                      "baseline_reference": ref_base_rows},
        "replay": {
            "command": str(meta["replay_command"]),
            "note": "reproduces this run byte-for-byte on the pinned code_version",
        },
        "not_attested": list(_NOT_ATTESTED),
        "generated": meta.get("generated") or _now_iso(),
    }
    return cert


# ── signing (mirrors core.notary._sign; drops cert_sig from the payload) ────
def _content(cert: dict) -> dict:
    """The signed CONTENT — every field except the signing envelope."""
    return {k: v for k, v in cert.items() if k not in _SIGNING_FIELDS}


def _cert_sig_bytes(cert: dict) -> bytes:
    """The exact bytes covered by cert_sig — the whole certificate except the
    signature itself, canonically encoded. One definition, used by sign+verify."""
    return _canon_bytes({k: v for k, v in cert.items() if k != "cert_sig"})


def _raw_pubkey_b64(pubkey_pem: str) -> str:
    raw = _load_pub(pubkey_pem).public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def sign_certificate(cert: dict, *, key: Optional[NotaryKey] = None) -> dict:
    """Sign an unsigned certificate. Adds the payload hash, the public key (raw
    b64 + PEM), the fingerprint, key_source, algo, timestamp, and the Ed25519
    signature. Re-signing an already-signed certificate is safe: the previous
    signing envelope is stripped first, so the content hash is stable."""
    key = key or load_notary_key()
    base = _content(cert)                      # strip any prior signing fields
    signed = dict(base)
    signed["payload_sha256"] = canon_hash(base)
    signed["algo"] = "ed25519"
    signed["key_source"] = key.key_source
    signed["pubkey_fpr"] = key.pubkey_fpr
    signed["pubkey_pem"] = key.pubkey_pem
    signed["pubkey_b64"] = _raw_pubkey_b64(key.pubkey_pem)
    signed["signed_at"] = _now_iso()
    sig = key._private.sign(_cert_sig_bytes(signed))
    signed["cert_sig"] = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return signed


# ── verify (offline; only the cert file needed) ─────────────────────────────
def _num_eq(a, b) -> bool:
    """Tolerant equality for recomputed vs stored metric values (handles None,
    numbers, and [lo, hi] lists)."""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_num_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-6
    return a == b


def _pem_from_b64(pubkey_b64: str) -> str:
    raw = base64.b64decode(pubkey_b64)
    pub = Ed25519PublicKey.from_public_bytes(raw)
    return pub.public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()


def verify_certificate(cert, pubkey_b64: Optional[str] = None) -> tuple[bool, list]:
    """Verify a certificate STANDALONE from its JSON/dict. Fails CLOSED: any
    problem sets ok=False and appends a reason naming it. Checks, in order:

      1. spec_version is recognized;
      2. the public key resolves (explicit `pubkey_b64` trust-pin > the cert's
         embedded pubkey_pem/pubkey_b64) and its fingerprint matches pubkey_fpr;
      3. the Ed25519 signature over the canonical payload is valid;
      4. payload_sha256 == canon_hash(content) (content = all non-signing fields);
      5. EVERY metric — pooled own-utility (primary: mean, CI, delta,
         per-counterparty breakdown, p-values) AND capture/logroll (secondary)
         — recomputed from the embedded per-match rows equals the stored value
         (a tampered number is caught even with a valid structure; a tampered
         row changes the recomputation and is caught too).

    Also appends a NOTE (never a failure) surfacing key_source: an ephemeral-key
    certificate verifies but is NOT a production attestation. `ok` is the
    authority; reasons may contain NOTE lines even when ok is True.

    Needs only the certificate (public key travels inside) and numpy+cryptography
    — never the private key. Returns (ok, reasons)."""
    d = cert
    if isinstance(d, str):
        d = json.loads(d)
    if not isinstance(d, dict):
        return False, ["certificate is not a JSON object"]
    d = dict(d)
    reasons: list[str] = []
    ok = True

    # 1. spec version
    if d.get("spec_version") != SPEC_VERSION:
        ok = False
        reasons.append(
            f"spec_version {d.get('spec_version')!r} != {SPEC_VERSION!r}")

    # 2. resolve the verifying public key
    pem = None
    if pubkey_b64:
        try:
            pem = _pem_from_b64(pubkey_b64)
        except Exception as e:
            ok = False
            reasons.append(f"explicit pubkey_b64 is not a valid Ed25519 key: {e}")
    if pem is None:
        pem = d.get("pubkey_pem")
    if pem is None and d.get("pubkey_b64"):
        try:
            pem = _pem_from_b64(d["pubkey_b64"])
        except Exception as e:
            ok = False
            reasons.append(f"embedded pubkey_b64 is not a valid Ed25519 key: {e}")
    if pem is None:
        return False, reasons + ["no public key available (cert carries none and "
                                 "none was supplied)"]

    fpr_ok = _fingerprint(pem) == d.get("pubkey_fpr")
    if not fpr_ok:
        ok = False
        reasons.append("pubkey fingerprint does not match the cert's pubkey_fpr")
    # if a raw pubkey_b64 is embedded, it must agree with the PEM we verify under
    if d.get("pubkey_b64"):
        try:
            if _raw_pubkey_b64(pem) != d["pubkey_b64"]:
                ok = False
                reasons.append("embedded pubkey_b64 disagrees with pubkey_pem")
        except Exception:
            pass

    # 3. signature over the canonical payload (all fields except cert_sig)
    try:
        _load_pub(pem).verify(_b64d(d["cert_sig"]), _cert_sig_bytes(d))
    except (InvalidSignature, KeyError, ValueError, TypeError) as e:
        ok = False
        reasons.append(f"signature invalid: {type(e).__name__}")

    # 4. payload hash binds the content
    recomputed_hash = canon_hash(_content(d))
    if d.get("payload_sha256") != recomputed_hash:
        ok = False
        reasons.append(
            "payload_sha256 does not match canon_hash(content) — the certificate "
            "content was edited after signing")

    # 5. recompute EVERY metric from the embedded per-match rows
    try:
        pm = d.get("per_match") or {}
        seed = int(d["scenario_set"]["seed"])
        base_name = (d.get("baseline") or {}).get("name", "naive-baseline")
        mets, paired_ok = _metrics_from_rows(
            pm.get("candidate", []), pm.get("baseline", []), seed,
            baseline_name=base_name)
        if not paired_ok:
            ok = False
            reasons.append("per-match candidate/baseline rows are not the same "
                           "scenario-set x pool (keys differ)")
        cm, bm = mets["candidate"], mets["baseline"]
        stored_c = d.get("metrics") or {}
        stored_b = d.get("baseline") or {}
        s_u = stored_b.get("perm_test_own_utility") or {}
        s_cap = stored_b.get("perm_test_capture") or {}
        s_lr = stored_b.get("perm_test_logroll") or {}
        checks = [
            ("metrics.primary_statistic", stored_c.get("primary_statistic"),
             cm["primary_statistic"]),
            ("metrics.n_matches", stored_c.get("n_matches"), cm["n_matches"]),
            ("metrics.deal_rate", stored_c.get("deal_rate"), cm["deal_rate"]),
            ("metrics.own_utility_mean", stored_c.get("own_utility_mean"),
             cm["own_utility_mean"]),
            ("metrics.own_utility_ci95", stored_c.get("own_utility_ci95"),
             cm["own_utility_ci95"]),
            ("metrics.capture_mean", stored_c.get("capture_mean"),
             cm["capture_mean"]),
            ("metrics.capture_ci95", stored_c.get("capture_ci95"),
             cm["capture_ci95"]),
            ("metrics.logroll_mean", stored_c.get("logroll_mean"),
             cm["logroll_mean"]),
            ("metrics.logroll_ci95", stored_c.get("logroll_ci95"),
             cm["logroll_ci95"]),
            ("metrics.logroll_n_scored", stored_c.get("logroll_n_scored"),
             cm["logroll_n_scored"]),
            ("metrics.dollars_left_mean", stored_c.get("dollars_left_mean"),
             cm["dollars_left_mean"]),
            ("metrics.format_failure_total", stored_c.get("format_failure_total"),
             cm["format_failure_total"]),
            ("baseline.own_utility_mean", stored_b.get("own_utility_mean"),
             bm["own_utility_mean"]),
            ("baseline.delta_own_utility", stored_b.get("delta_own_utility"),
             bm["delta_own_utility"]),
            ("baseline.perm_test_own_utility.n_pairs", s_u.get("n_pairs"),
             bm["perm_test_own_utility"]["n_pairs"]),
            ("baseline.perm_test_own_utility.p_value", s_u.get("p_value"),
             bm["perm_test_own_utility"]["p_value"]),
            ("baseline.capture_mean", stored_b.get("capture_mean"),
             bm["capture_mean"]),
            ("baseline.delta_capture", stored_b.get("delta_capture"),
             bm["delta_capture"]),
            ("baseline.perm_test_capture.p_value", s_cap.get("p_value"),
             bm["perm_test_capture"]["p_value"]),
            ("baseline.logroll_mean", stored_b.get("logroll_mean"),
             bm["logroll_mean"]),
            ("baseline.delta_logroll", stored_b.get("delta_logroll"),
             bm["delta_logroll"]),
            ("baseline.perm_test_logroll.n_pairs", s_lr.get("n_pairs"),
             bm["perm_test_logroll"]["n_pairs"]),
            ("baseline.perm_test_logroll.p_value", s_lr.get("p_value"),
             bm["perm_test_logroll"]["p_value"]),
        ]
        # per-counterparty breakdown: every member's delta/p/n/means must match
        stored_cp = stored_b.get("per_counterparty") or {}
        for cp in sorted(set(stored_cp) | set(bm["per_counterparty"])):
            got = bm["per_counterparty"].get(cp) or {}
            has = stored_cp.get(cp) or {}
            for f in ("n_pairs", "candidate_u", "baseline_u", "delta", "p_value"):
                checks.append((f"baseline.per_counterparty.{cp}.{f}",
                               has.get(f), got.get(f)))

        # ANTI-POOLING GUARD (Amendment 1): the reference counterparty must not
        # appear among the rows that produced the certified statistic, and the
        # certified per-counterparty breakdown must be exactly the frozen pool.
        pool_cps = {str(r.get("counterparty")) for r in pm.get("candidate", [])}
        pool_cps |= {str(r.get("counterparty")) for r in pm.get("baseline", [])}
        if _REFERENCE_CP in pool_cps:
            ok = False
            reasons.append(
                f"reference counterparty {_REFERENCE_CP!r} is present among the "
                f"POOL rows feeding the primary statistic — the certified claim "
                f"is contaminated (Amendment 1 forbids pooling it)")
        if _REFERENCE_CP in set(bm["per_counterparty"]) | set(stored_cp):
            ok = False
            reasons.append(
                f"reference counterparty {_REFERENCE_CP!r} appears in the "
                f"certified per-counterparty breakdown — it is context only")

        # the reference tier itself: recompute from its OWN embedded rows
        ref_stat, ref_paired = _reference_from_rows(
            pm.get("candidate_reference", []), pm.get("baseline_reference", []),
            seed)
        stored_ref = (d.get("reference_tier") or {}).get("this_scenario_set") or {}
        if not ref_paired:
            ok = False
            reasons.append("reference-tier rows are not a matched "
                           "(scenario_id, role) set")
        for f in ("n_pairs", "candidate_own_utility", "baseline_own_utility",
                  "delta_own_utility", "p_value"):
            if f in stored_ref or f in ref_stat:
                checks.append((f"reference_tier.this_scenario_set.{f}",
                               stored_ref.get(f), ref_stat.get(f)))

        for label, stored, got in checks:
            if not _num_eq(stored, got):
                ok = False
                reasons.append(
                    f"{label} tampered: stored={stored!r} but recomputed={got!r} "
                    f"from the embedded per-match rows")
    except Exception as e:
        ok = False
        reasons.append(f"metric recomputation failed: {type(e).__name__}: {e}")

    # key_source transparency (a NOTE, never a failure)
    ks = d.get("key_source")
    if ks == "ephemeral":
        reasons.append(
            "NOTE key_source=ephemeral — signed with a throwaway key generated at "
            "runtime; this proves the certificate is internally consistent, NOT "
            "who signed it. Not a production attestation.")
    elif ks == "env":
        reasons.append(
            "NOTE key_source=env — persistent key; pin pubkey_fpr against the "
            "vendor's published key out-of-band to trust the signer.")
    else:
        ok = False
        reasons.append(f"key_source {ks!r} is neither 'env' nor 'ephemeral'")

    return ok, reasons


# ── the run harness (local seats only — engine | naive | champion vs POOL) ──
from arena.gauntlet.agents import EngineSeat, NaiveSeat  # noqa: E402
from arena.gauntlet.protocol import DEADLINE, gen_gauntlet_scenarios  # noqa: E402
from arena.gauntlet.pool import (  # noqa: E402
    POOL_MEMBERS, make_pool_seat, pool_match_seed, run_pool_match,
)

try:
    from arena.gauntlet.run import SCENARIO_SEED as DEFAULT_SEED  # public practice seed
except Exception:  # pragma: no cover
    DEFAULT_SEED = 20260709

_LOCAL_ALIASES = {
    "engine": "engine", "snhp-engine": "engine",
    "naive": "naive-baseline", "naive-baseline": "naive-baseline",
    "naive-split": "naive-baseline", "scripted-naive": "naive-baseline",
    "champion": "champion", "evolved-champion": "champion",
}


def _seat_for(name: str, match_seed: int):
    if name == "engine":
        return EngineSeat(match_seed)
    if name == "naive-baseline":
        return NaiveSeat()
    if name == "champion":
        from arena.gauntlet.champion import CHAMPION_PATH, load_champion
        from arena.gauntlet.agents import GenomeSeat
        genome, _ = load_champion(CHAMPION_PATH)
        return GenomeSeat(genome, match_seed)
    raise SystemExit(f"unknown local candidate {name!r} "
                     f"(engine | naive | champion)")


def run_local(candidate: str, *, seed: int = DEFAULT_SEED, n: int = 60,
              deadline: int = DEADLINE, verbose: bool = False) -> list:
    """Play `candidate` (a LOCAL seat name) against the FULL declared pool over
    the fixed scenario set in both roles: n x 2 roles x len(POOL_MEMBERS)
    matches. No network, no LLM — engine/naive/champion only. Returns dict
    records (MatchResult.to_dict() + counterparty label)."""
    name = _LOCAL_ALIASES.get(candidate, candidate)
    scenarios = gen_gauntlet_scenarios(n, seed)
    out = []
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            for cp in POOL_MEMBERS:
                ms = pool_match_seed(seed, sid, role, cp)
                r = run_pool_match(_seat_for(name, ms), make_pool_seat(cp),
                                   sc, w_s, w_b, role=role,
                                   condition=f"pool-{cp}", scenario_id=sid,
                                   deadline=deadline)
                rec = r.to_dict()
                rec["counterparty"] = cp
                out.append(rec)
                if verbose:
                    tag = "deal" if r.deal else f"no-deal({r.walked_by})"
                    print(f"  [{name} vs {cp}] sc{sid:02d}/{role:<6} {tag:>20} "
                          f"u={r.u_candidate:.3f}", flush=True)
    return out


def run_reference_local(candidate: str, *, seed: int = DEFAULT_SEED, n: int = 60,
                        deadline: int = DEADLINE) -> list:
    """The SNHP-REFERENCE arm for one candidate (Amendment 1): the EngineSeat as
    counterparty — the original gauntlet protocol — over the same scenario set,
    both roles. Reported context; NEVER pooled into the certified statistic."""
    name = _LOCAL_ALIASES.get(candidate, candidate)
    scenarios = gen_gauntlet_scenarios(n, seed)
    out = []
    for sid, (sc, w_s, w_b) in enumerate(scenarios):
        for role in ("seller", "buyer"):
            ms = pool_match_seed(seed, sid, role, _REFERENCE_CP)
            r = run_pool_match(_seat_for(name, ms), EngineSeat(ms),
                               sc, w_s, w_b, role=role,
                               condition=f"pool-{_REFERENCE_CP}",
                               scenario_id=sid, deadline=deadline)
            rec = r.to_dict()
            rec["counterparty"] = _REFERENCE_CP
            out.append(rec)
    return out


def _candidate_digest(name: str, code_version: str, seed: int, n: int) -> str:
    """A CLI-convenience opaque digest of the local candidate's identity — NOT a
    secret. In a real vendor flow the submitter supplies their own (e.g. a hash
    of their container image); here we bind the seat name + code + scenario pin so
    the digest is stable and reproducible."""
    return canon_hash({"candidate": name, "code_version": code_version,
                       "seed": int(seed), "n": int(n), "kind": "local-seat"})


def make_certificate(candidate: str, *, seed: int = DEFAULT_SEED, n: int = 60,
                     deadline: int = DEADLINE, verbose: bool = False,
                     key: Optional[NotaryKey] = None) -> dict:
    """Run the candidate AND the naive baseline against the declared pool on
    the fixed scenario set, certify, sign."""
    name = _LOCAL_ALIASES.get(candidate, candidate)
    cand_results = run_local(name, seed=seed, n=n, deadline=deadline, verbose=verbose)
    base_results = (cand_results if name == "naive-baseline"
                    else run_local("naive-baseline", seed=seed, n=n,
                                   deadline=deadline, verbose=verbose))
    code_version = git_head()
    meta = {
        "candidate_name": name,
        "candidate_digest": _candidate_digest(name, code_version, seed, n),
        "scenario_set": {"n": n, "seed": seed, "n_issues": 4,
                         "deadline": deadline, "code_version": code_version},
        "replay_command": (f"python -m arena.gauntlet.certify --run {candidate} "
                           f"--seed {seed} --n {n} --deadline {deadline}"),
        "baseline_name": "naive-baseline",
    }
    ref_results = run_reference_local(name, seed=seed, n=n, deadline=deadline)
    ref_base = (ref_results if name == "naive-baseline"
                else run_reference_local("naive-baseline", seed=seed, n=n,
                                         deadline=deadline))
    cert = certify(cand_results, base_results, meta,
                   reference_results=ref_results,
                   baseline_reference_results=ref_base)
    return sign_certificate(cert, key=key)


# ── CLI ─────────────────────────────────────────────────────────────────────
_CERTS_DIR = pathlib.Path(__file__).with_name("certs")


def _fmt_opt(v, spec: str = ".4f") -> str:
    return "n/a" if v is None else format(v, spec)


def _cmd_run(args) -> int:
    cert = make_certificate(args.run, seed=args.seed, n=args.n,
                            deadline=args.deadline, verbose=not args.quiet)
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else _CERTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    name = cert["candidate"]["name"]
    seed = cert["scenario_set"]["seed"]
    path = out_dir / f"{name}-seed{seed}-n{args.n}.cert.json"
    path.write_text(json.dumps(cert, indent=1, sort_keys=True))

    c, b = cert["metrics"], cert["baseline"]
    ok, reasons = verify_certificate(cert)
    pu = b["perm_test_own_utility"]
    print(f"\n=== gauntlet certificate: {name} "
          f"(seed {seed}, n={args.n}, code {cert['scenario_set']['code_version']}, "
          f"pool {'+'.join(cert['pool']['members'])}) ===")
    print(f"  candidate_digest   {cert['candidate']['candidate_digest']}")
    print(f"  n_matches          {c['n_matches']}   deal_rate {c['deal_rate']:.3f}")
    print(f"  own-u (PRIMARY)    {c['own_utility_mean']:.4f}  "
          f"95% CI {c['own_utility_ci95']}")
    print(f"  vs {b['name']:<15}  own-u {b['own_utility_mean']:.4f}   "
          f"delta {b['delta_own_utility']:+.4f}   perm p={pu['p_value']:.4f}   "
          f"({pu['n_pairs']} pairs)")
    for cp, row in b["per_counterparty"].items():
        print(f"    - vs {cp:<9} delta {_fmt_opt(row['delta'], '+.4f')}   "
              f"p={_fmt_opt(row['p_value'])}   ({row['n_pairs']} pairs)")
    print(f"  capture (context)  {c['capture_mean']:.4f}   "
          f"delta {b['delta_capture']:+.4f}  p={b['perm_test_capture']['p_value']:.4f}")
    print(f"  logroll (context)  {_fmt_opt(c['logroll_mean'])}   "
          f"delta {_fmt_opt(b['delta_logroll'], '+.4f')}  "
          f"p={_fmt_opt(b['perm_test_logroll']['p_value'])}")
    rt = cert.get("reference_tier") or {}
    rs = rt.get("this_scenario_set") or {}
    if rs:
        print(f"  -- reference tier (NOT certified; context only) --")
        print(f"     vs {rt['counterparty']:<12} cand-u "
              f"{_fmt_opt(rs['candidate_own_utility'])}  naive-u "
              f"{_fmt_opt(rs['baseline_own_utility'])}  "
              f"delta {_fmt_opt(rs['delta_own_utility'], '+.4f')}  "
              f"p={_fmt_opt(rs['p_value'])}  ({rs['n_pairs']} pairs)")
        print(f"     registered prediction: {rt.get('prediction_outcome')}")
    print(f"  key_source         {cert['key_source']}   fpr {cert['pubkey_fpr']}")
    print(f"  self-verify        {'OK' if ok else 'FAIL'}")
    for r in reasons:
        if r.startswith("NOTE"):
            print(f"    - {r}")
    print(f"\nwrote {path}")
    return 0 if ok else 1


def _cmd_verify(args) -> int:
    path = pathlib.Path(args.verify)
    try:
        cert = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"[FAIL] cannot read certificate {path}: {e}", file=sys.stderr)
        return 1
    ok, reasons = verify_certificate(cert, pubkey_b64=args.pubkey_b64)
    name = (cert.get("candidate") or {}).get("name", "?")
    print(f"certificate: {name} (seed {(cert.get('scenario_set') or {}).get('seed')}, "
          f"key_source={cert.get('key_source')})")
    print(f"[{'OK' if ok else 'FAIL'}] {path}")
    for r in reasons:
        print(f"  - {r}")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m arena.gauntlet.certify",
        description="mint / verify signed gauntlet certificates (offline)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", metavar="CANDIDATE",
                   help="local seat to certify: engine | naive | champion")
    g.add_argument("--verify", metavar="CERT.JSON",
                   help="verify a certificate offline (exit 0 ok / 1 fail)")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help=f"scenario seed (default {DEFAULT_SEED}, the public set)")
    p.add_argument("--n", type=int, default=60, help="scenarios (default 60)")
    p.add_argument("--deadline", type=int, default=DEADLINE)
    p.add_argument("--out-dir", default=None,
                   help="where to write the cert (default arena/gauntlet/certs/)")
    p.add_argument("--pubkey-b64", default=None,
                   help="verify: raw Ed25519 public key (b64) to pin against")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)
    if args.run:
        return _cmd_run(args)
    return _cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
