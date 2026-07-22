"""Gauntlet certificate (/3, pool protocol) tests — all offline (no network,
no LLM, no private key leaves the process). Covers: canonical-hash stability +
field-order independence; sign->verify round-trip; TAMPER detection (primary
pooled own-utility fields incl. the per-counterparty breakdown, secondary
capture/logroll fields, per-match rows, candidate name, pool declaration,
signature); the scored-both logroll pairing rule; row labeling (counterparty
is mandatory); ephemeral vs env key_source transparency; the metric math on a
hand-computed synthetic fixture; and CLI --verify exit codes."""
from __future__ import annotations

import copy
import json
import os

import pytest

from arena.gauntlet import certify as C
from arena.gauntlet.certify import (
    PRIMARY_STATISTIC, SPEC_VERSION, bootstrap_mean_ci, canon_hash, certify,
    main, paired_permutation_pvalue, sign_certificate, verify_certificate,
)


# ── synthetic fixture (hand-computable) ─────────────────────────────────────
def _row(sid, role, cp, u, cap, deal, joint, lr, dl, ff=0):
    return {"scenario_id": sid, "role": role, "counterparty": cp,
            "u_candidate": u, "capture": cap, "deal": deal, "joint": joint,
            "logroll": lr, "dollars_left": dl, "format_failures": ff}


def _ref_rows():
    """Reference-tier rows (Amendment 1): candidate own-u [0.9, 0.7] vs
    baseline [0.4, 0.2] -> delta 0.5 over 2 pairs. Deliberately LARGER than the
    pool delta so any accidental pooling would visibly move the primary."""
    cand = [_row(0, "seller", "snhp-engine", 0.9, 0.9, True, 0.9, 0.4, 100),
            _row(0, "buyer", "snhp-engine", 0.7, 0.8, True, 0.8, 0.2, 150)]
    base = [_row(0, "seller", "snhp-engine", 0.4, 0.5, True, 0.5, 0.1, 700),
            _row(0, "buyer", "snhp-engine", 0.2, 0.4, True, 0.4, 0.0, 800)]
    return cand, base


def _synthetic():
    """4 matches (2 scenarios x 2 roles x 1 counterparty 'hardball'):
      OWN-UTILITY (primary):
        candidate [0.8, 0.6, 0.7, 0.5] -> mean 0.65
        baseline  [0.3, 0.3, 0.4, 0.2] -> mean 0.30
        per-pair deltas [0.5, 0.3, 0.3, 0.3] -> delta 0.35 (4 pairs)
        per_counterparty['hardball']: same numbers, n_pairs 4
      CAPTURE (secondary):
        candidate [0.9, 0.8, 1.0, 0.7] -> 0.85; baseline 0.50; delta 0.35
      LOGROLL (secondary):
        candidate scored [0.5, 0.3, 0.1] (one None) -> mean 0.3, n_scored 3
        baseline [0.2, 0.1, 0.1, 0.0] -> 0.1; scored-both pairs 3, delta 0.2
      deals [T,T,F,T] -> 0.75; dollars [100..400] -> 250; ff [0,1,0,2] -> 3
    """
    cand = [
        _row(0, "seller", "hardball", 0.8, 0.9, True, 0.9, 0.5, 100, 0),
        _row(0, "buyer", "hardball", 0.6, 0.8, True, 0.8, None, 200, 1),
        _row(1, "seller", "hardball", 0.7, 1.0, False, 0.7, 0.3, 300, 0),
        _row(1, "buyer", "hardball", 0.5, 0.7, True, 0.6, 0.1, 400, 2),
    ]
    base = [
        _row(0, "seller", "hardball", 0.3, 0.5, True, 0.5, 0.2, 900, 0),
        _row(0, "buyer", "hardball", 0.3, 0.6, True, 0.6, 0.1, 800, 0),
        _row(1, "seller", "hardball", 0.4, 0.5, True, 0.5, 0.1, 900, 0),
        _row(1, "buyer", "hardball", 0.2, 0.4, False, 0.3, 0.0, 950, 0),
    ]
    meta = {
        "candidate_name": "synthetic",
        "candidate_digest": "sha256:deadbeef",
        "scenario_set": {"n": 2, "seed": 12345, "n_issues": 4, "deadline": 8,
                         "code_version": "testcafe"},
        "replay_command": "python -m arena.gauntlet.certify --run synthetic",
    }
    return cand, base, meta


# ── canonical hashing ───────────────────────────────────────────────────────
def test_canon_hash_stable_and_field_order_independent():
    a = {"z": 1, "a": {"y": [1, 2, 3], "x": True}, "m": None}
    b = {"m": None, "a": {"x": True, "y": [1, 2, 3]}, "z": 1}  # keys reordered
    assert canon_hash(a) == canon_hash(b)          # order-independent
    assert canon_hash(a) == canon_hash(a)          # stable
    assert canon_hash(a).startswith("sha256:")
    # a list REORDER must change the hash (list order is meaningful)
    c = {"m": None, "a": {"x": True, "y": [3, 2, 1]}, "z": 1}
    assert canon_hash(a) != canon_hash(c)


# ── sign -> verify round-trip ───────────────────────────────────────────────
def test_certify_sign_verify_roundtrip():
    cand, base, meta = _synthetic()
    cert = sign_certificate(certify(cand, base, meta))
    assert cert["spec_version"] == SPEC_VERSION == "gauntlet-cert/3"
    assert (cert["metrics"]["primary_statistic"] == PRIMARY_STATISTIC
            == "own_utility_pooled")
    # the pool declaration travels inside the signed content
    assert cert["pool"]["members"] == ["naive", "hardball", "conceder"]
    assert cert["pool"]["parameters"]["hardball_accept"] == 0.65
    assert cert["pool"]["parameters"]["conceder_accept"] == 0.45
    assert cert["pool"]["parameters"]["conceder_step"] == 0.15
    ok, reasons = verify_certificate(cert)
    assert ok, reasons
    # a JSON round-trip (field order shuffled by the encoder) still verifies
    ok2, _ = verify_certificate(json.loads(json.dumps(cert, sort_keys=True)))
    assert ok2


# ── metric math on the hand-computed fixture ────────────────────────────────
def test_metric_math_synthetic():
    cand, base, meta = _synthetic()
    cert = certify(cand, base, meta)
    m, b = cert["metrics"], cert["baseline"]
    # primary: pooled own-utility
    assert m["own_utility_mean"] == pytest.approx(0.65, abs=1e-9)
    assert b["own_utility_mean"] == pytest.approx(0.30, abs=1e-9)
    assert b["delta_own_utility"] == pytest.approx(0.35, abs=1e-9)
    assert b["perm_test_own_utility"]["n_pairs"] == 4
    lo, hi = m["own_utility_ci95"]
    assert lo <= m["own_utility_mean"] <= hi
    # per-counterparty breakdown (single member here)
    assert set(b["per_counterparty"]) == {"hardball"}
    hb = b["per_counterparty"]["hardball"]
    assert hb["n_pairs"] == 4
    assert hb["candidate_u"] == pytest.approx(0.65, abs=1e-9)
    assert hb["baseline_u"] == pytest.approx(0.30, abs=1e-9)
    assert hb["delta"] == pytest.approx(0.35, abs=1e-9)
    # secondary: capture
    assert m["capture_mean"] == pytest.approx(0.85, abs=1e-9)
    assert b["capture_mean"] == pytest.approx(0.5, abs=1e-9)
    assert b["delta_capture"] == pytest.approx(0.35, abs=1e-9)
    # secondary: logroll (scored-both pairing)
    assert m["logroll_mean"] == pytest.approx(0.3, abs=1e-9)
    assert m["logroll_n_scored"] == 3
    assert b["logroll_mean"] == pytest.approx(0.1, abs=1e-9)
    assert b["delta_logroll"] == pytest.approx(0.2, abs=1e-9)
    assert b["perm_test_logroll"]["n_pairs"] == 3
    assert b["perm_test_logroll"]["pairing"] == "scored-both"
    # the rest
    assert m["n_matches"] == 4
    assert m["deal_rate"] == 0.75
    assert m["dollars_left_mean"] == pytest.approx(250.0, abs=1e-9)
    assert m["format_failure_total"] == 3
    # certify is fully deterministic (CIs + p-values reproduce exactly)
    cert2 = certify(cand, base, meta)
    assert cert2["metrics"]["own_utility_ci95"] == m["own_utility_ci95"]
    assert (cert2["baseline"]["perm_test_own_utility"]["p_value"]
            == b["perm_test_own_utility"]["p_value"])
    assert (cert2["baseline"]["per_counterparty"]["hardball"]["p_value"]
            == hb["p_value"])


def test_bootstrap_and_permutation_determinism_and_bounds():
    vals = [0.9, 0.8, 1.0, 0.7, 0.6, 0.95]
    assert bootstrap_mean_ci(vals, 42) == bootstrap_mean_ci(vals, 42)
    assert bootstrap_mean_ci(vals, 42) != bootstrap_mean_ci(vals, 7)
    assert bootstrap_mean_ci([], 42) is None             # empty -> None, honestly
    # all-zero paired differences -> obs 0 -> every permutation qualifies -> p==1
    assert paired_permutation_pvalue([0.0, 0.0, 0.0, 0.0], 123) == 1.0
    # a large, consistent separation -> tiny p; and deterministic
    p_big = paired_permutation_pvalue([1.0] * 8, 123)
    assert p_big < 0.05
    assert p_big == paired_permutation_pvalue([1.0] * 8, 123)


def test_logroll_scored_both_pairing_rule():
    """A pair is dropped when EITHER side's logroll is None, and the pair count
    reports it; unpaired scored matches still count in the candidate mean."""
    cand, base, meta = _synthetic()
    base2 = copy.deepcopy(base)
    base2[2]["logroll"] = None        # (1, seller): candidate scored, baseline not
    cert = certify(cand, base2, meta)
    b = cert["baseline"]
    assert b["perm_test_logroll"]["n_pairs"] == 2        # (0,seller), (1,buyer)
    assert b["delta_logroll"] == pytest.approx((0.3 + 0.1) / 2, abs=1e-9)
    # candidate logroll mean unchanged: scored set is per-side, not per-pair
    assert cert["metrics"]["logroll_mean"] == pytest.approx(0.3, abs=1e-9)
    assert cert["metrics"]["logroll_n_scored"] == 3
    # own-utility pairing untouched by logroll holes
    assert b["perm_test_own_utility"]["n_pairs"] == 4


def test_baseline_pairing_mismatch_fails_closed():
    cand, base, meta = _synthetic()
    bad = copy.deepcopy(base)
    bad[0]["scenario_id"] = 99            # break the (sid, role, cp) pairing
    with pytest.raises(ValueError):
        certify(cand, bad, meta)
    # a counterparty relabel is also a pairing break
    bad2 = copy.deepcopy(base)
    bad2[0]["counterparty"] = "conceder"
    with pytest.raises(ValueError):
        certify(cand, bad2, meta)


def test_row_without_counterparty_is_refused():
    cand, base, meta = _synthetic()
    naked = copy.deepcopy(cand)
    del naked[0]["counterparty"]          # no label and no pool-* condition
    with pytest.raises(ValueError):
        certify(naked, base, meta)
    # but a run_pool_match-style condition label is accepted
    relabeled = copy.deepcopy(cand)
    del relabeled[0]["counterparty"]
    relabeled[0]["condition"] = "pool-hardball"
    cert = certify(relabeled, base, meta)
    assert cert["baseline"]["perm_test_own_utility"]["n_pairs"] == 4


# ── tamper detection ────────────────────────────────────────────────────────
def _signed():
    cand, base, meta = _synthetic()
    return sign_certificate(certify(cand, base, meta))


def test_tamper_primary_own_utility_detected():
    cert = _signed()
    cert["metrics"]["own_utility_mean"] = 0.999
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("own_utility_mean tampered" in r for r in reasons)


def test_tamper_delta_and_pvalue_detected():
    cert = _signed()
    cert["baseline"]["delta_own_utility"] = 0.9
    cert["baseline"]["perm_test_own_utility"]["p_value"] = 0.00001
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("delta_own_utility tampered" in r for r in reasons)
    assert any("perm_test_own_utility.p_value tampered" in r for r in reasons)


def test_tamper_per_counterparty_breakdown_detected():
    cert = _signed()
    cert["baseline"]["per_counterparty"]["hardball"]["delta"] = 0.99
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("per_counterparty.hardball.delta tampered" in r for r in reasons)
    # inventing a pool member is caught too
    cert2 = _signed()
    cert2["baseline"]["per_counterparty"]["fakebot"] = {
        "n_pairs": 4, "candidate_u": 0.9, "baseline_u": 0.1,
        "delta": 0.8, "p_value": 0.0001}
    ok2, reasons2 = verify_certificate(cert2)
    assert not ok2
    assert any("per_counterparty.fakebot" in r for r in reasons2)


def test_tamper_secondary_metrics_detected():
    cert = _signed()
    cert["metrics"]["capture_mean"] = 0.999
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("capture_mean tampered" in r for r in reasons)
    cert2 = _signed()
    cert2["baseline"]["delta_logroll"] = 0.9
    ok2, reasons2 = verify_certificate(cert2)
    assert not ok2
    assert any("delta_logroll tampered" in r for r in reasons2)


def test_tamper_per_match_row_detected():
    cert = _signed()
    cert["per_match"]["candidate"][0]["u"] = 0.99     # flatter the primary
    ok, reasons = verify_certificate(cert)
    assert not ok
    # recomputed metrics no longer match the (untouched) stored metrics
    assert any("tampered" in r for r in reasons)
    assert any("payload_sha256" in r for r in reasons)


def test_tamper_candidate_name_detected():
    cert = _signed()
    cert["candidate"]["name"] = "impostor"
    ok, reasons = verify_certificate(cert)
    assert not ok
    # name is inside the signed content -> signature AND payload hash both fail
    assert any("signature invalid" in r for r in reasons)
    assert any("payload_sha256" in r for r in reasons)


def test_tamper_pool_declaration_detected():
    cert = _signed()
    cert["pool"]["parameters"]["hardball_accept"] = 0.05   # easier pool, faked
    ok, reasons = verify_certificate(cert)
    assert not ok
    # the pool is signed content: the signature and payload hash both break
    assert any("signature invalid" in r for r in reasons)
    assert any("payload_sha256" in r for r in reasons)


def test_tamper_signature_detected():
    cert = _signed()
    cert["cert_sig"] = cert["cert_sig"][:-4] + ("AAAA" if not
                                                cert["cert_sig"].endswith("AAAA")
                                                else "BBBB")
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("signature invalid" in r for r in reasons)


# ── key_source transparency ─────────────────────────────────────────────────
def test_ephemeral_key_verifies_but_is_surfaced():
    cert = _signed()                                # no NOTARY_KEY_PEM in env
    assert cert["key_source"] == "ephemeral"
    ok, reasons = verify_certificate(cert)
    assert ok
    assert any(r.startswith("NOTE") and "ephemeral" in r for r in reasons)


def test_env_key_source_is_env_and_noted():
    from core.notary import load_notary_key
    pem = C.generate_key_pem()
    old = os.environ.get("NOTARY_KEY_PEM")
    try:
        os.environ["NOTARY_KEY_PEM"] = pem
        key = load_notary_key(refresh=True)
        assert key.key_source == "env"
        cand, base, meta = _synthetic()
        cert = sign_certificate(certify(cand, base, meta), key=key)
        assert cert["key_source"] == "env"
        ok, reasons = verify_certificate(cert)
        assert ok
        assert any(r.startswith("NOTE") and "env" in r for r in reasons)
    finally:
        if old is None:
            os.environ.pop("NOTARY_KEY_PEM", None)
        else:
            os.environ["NOTARY_KEY_PEM"] = old
        load_notary_key(refresh=True)               # reset the module cache


# ── trust-pin via explicit public key ───────────────────────────────────────
def test_explicit_pubkey_pin_matches_and_wrong_pin_fails():
    cert = _signed()
    good = cert["pubkey_b64"]
    ok, _ = verify_certificate(cert, pubkey_b64=good)
    assert ok
    # a different key: the fingerprint won't match and the signature won't verify
    other = sign_certificate(certify(*_synthetic()))
    # (fresh ephemeral key each call -> different pubkey with overwhelming prob)
    if other["pubkey_b64"] != good:
        ok2, reasons = verify_certificate(cert, pubkey_b64=other["pubkey_b64"])
        assert not ok2
        assert any("fingerprint" in r or "signature invalid" in r for r in reasons)


# ── Amendment 1: the reference tier is reported, never certified ────────────
def _signed_with_ref():
    cand, base, meta = _synthetic()
    rc, rb = _ref_rows()
    return sign_certificate(certify(cand, base, meta,
                                    reference_results=rc,
                                    baseline_reference_results=rb))


def test_reference_tier_reported_and_verifies():
    cert = _signed_with_ref()
    rt = cert["reference_tier"]
    assert rt["counterparty"] == "snhp-engine"
    ts = rt["this_scenario_set"]
    assert ts["n_pairs"] == 2
    assert ts["candidate_own_utility"] == pytest.approx(0.8, abs=1e-9)
    assert ts["baseline_own_utility"] == pytest.approx(0.3, abs=1e-9)
    assert ts["delta_own_utility"] == pytest.approx(0.5, abs=1e-9)
    assert rt["prediction_outcome"] in ("held", "contradicted", "not_evaluated")
    assert "not part of the certified claim" in rt["scope"].lower()
    ok, reasons = verify_certificate(cert)
    assert ok, reasons


def test_reference_tier_is_NOT_in_the_primary_statistic():
    """THE GUARD (PREREG-pool.md Amendment 1). The reference rows carry a huge
    +0.5 delta; the certified statistic must be byte-identical with and without
    them, and the reference counterparty must not appear in the certified
    per-counterparty breakdown or the primary's row set."""
    cand, base, meta = _synthetic()
    rc, rb = _ref_rows()
    without = certify(cand, base, meta)
    with_ref = certify(cand, base, meta, reference_results=rc,
                       baseline_reference_results=rb)
    assert with_ref["metrics"] == without["metrics"]
    assert with_ref["baseline"] == without["baseline"]
    # and specifically: the pool delta stays 0.35, not dragged toward 0.5
    assert with_ref["baseline"]["delta_own_utility"] == pytest.approx(0.35, abs=1e-9)
    assert "snhp-engine" not in with_ref["baseline"]["per_counterparty"]
    assert all(r["counterparty"] != "snhp-engine"
               for r in with_ref["per_match"]["candidate"])
    assert all(r["counterparty"] != "snhp-engine"
               for r in with_ref["per_match"]["baseline"])
    assert with_ref["metrics"]["n_matches"] == 4      # pool rows only


def test_certify_refuses_reference_smuggled_into_the_pool():
    """Structural anti-pooling: reference rows among the POOL rows, an off-pool
    counterparty, or mislabeled reference rows all fail closed."""
    cand, base, meta = _synthetic()
    rc, rb = _ref_rows()
    with pytest.raises(ValueError, match="snhp-engine"):
        certify(cand + rc, base + rb, meta)
    stray_c = cand + [_row(0, "seller", "mystery", 0.9, 0.9, True, 0.9, 0.4, 100)]
    stray_b = base + [_row(0, "seller", "mystery", 0.4, 0.5, True, 0.5, 0.1, 700)]
    with pytest.raises(ValueError, match="outside the frozen pool"):
        certify(stray_c, stray_b, meta)
    mislabeled = [dict(r, counterparty="naive") for r in rc]
    with pytest.raises(ValueError, match="must all carry counterparty"):
        certify(cand, base, meta, reference_results=mislabeled,
                baseline_reference_results=rb)


def test_reference_tier_determinism_and_pairing():
    cand, base, meta = _synthetic()
    rc, rb = _ref_rows()
    a = certify(cand, base, meta, reference_results=rc,
                baseline_reference_results=rb)
    b = certify(cand, base, meta, reference_results=rc,
                baseline_reference_results=rb)
    assert (a["reference_tier"]["this_scenario_set"]
            == b["reference_tier"]["this_scenario_set"])
    # a broken reference pairing fails closed rather than pairing partially
    with pytest.raises(ValueError, match="reference-tier"):
        certify(cand, base, meta, reference_results=rc,
                baseline_reference_results=rb[:1])


def test_tamper_reference_tier_detected():
    cert = _signed_with_ref()
    cert["reference_tier"]["this_scenario_set"]["delta_own_utility"] = 0.001
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("reference_tier.this_scenario_set.delta_own_utility tampered" in r
               for r in reasons)
    # the prediction/outcome strings are signed content: editing breaks the sig
    cert2 = _signed_with_ref()
    cert2["reference_tier"]["prediction_outcome"] = "contradicted"
    ok2, reasons2 = verify_certificate(cert2)
    assert not ok2
    assert any("signature invalid" in r for r in reasons2)
    assert any("payload_sha256" in r for r in reasons2)


def test_verify_catches_reference_contamination_of_the_primary():
    """A cert whose POOL rows were doctored to include the reference
    counterparty must FAIL verification naming the contamination."""
    cert = _signed_with_ref()
    cert["per_match"]["candidate"].append(
        dict(cert["per_match"]["candidate_reference"][0]))
    cert["per_match"]["baseline"].append(
        dict(cert["per_match"]["baseline_reference"][0]))
    ok, reasons = verify_certificate(cert)
    assert not ok
    assert any("contaminated" in r or "snhp-engine" in r for r in reasons)


# ── the honesty text travels in the artifact ────────────────────────────────
def test_not_attested_carries_the_disclosures():
    cert = _signed()
    text = " ".join(cert["not_attested"]).lower()
    assert "outside the declared pool" in text     # claim scope is pool-bound
    assert "capture kill fired" in text            # the /1 history travels
    assert "post-hoc" in text                      # the /2 history travels
    assert "held-out validation failed" in text
    # Amendment 1: the reference tier disclaimer is pinned
    assert "reference tier" in text
    assert "not part of the certified claim" in text
    assert "never pooled into the primary" in text


def test_spec_version_unchanged_content_revision_bumped():
    """Amendment 1 is ADDITIVE context: the certified claim (and therefore the
    spec version) must NOT change; the content revision tracks the addition."""
    cert = _signed_with_ref()
    assert cert["spec_version"] == "gauntlet-cert/3"
    assert cert["content_revision"] == 2
    assert any("reference_tier" in c for c in cert["changelog"])
    assert cert["metrics"]["primary_statistic"] == "own_utility_pooled"


# ── CLI --verify exit codes ─────────────────────────────────────────────────
def test_cli_verify_exit_codes(tmp_path):
    cert = _signed()
    good = tmp_path / "good.cert.json"
    good.write_text(json.dumps(cert, indent=1, sort_keys=True))
    assert main(["--verify", str(good)]) == 0
    bad = copy.deepcopy(cert)
    bad["metrics"]["own_utility_mean"] = 0.123
    badp = tmp_path / "bad.cert.json"
    badp.write_text(json.dumps(bad, indent=1, sort_keys=True))
    assert main(["--verify", str(badp)]) == 1
    # a missing file fails closed, does not raise
    assert main(["--verify", str(tmp_path / "nope.json")]) == 1


def test_cli_run_engine_smoke(tmp_path):
    """A tiny end-to-end --run: mints a real signed /3 cert for the engine seat
    on a 2-scenario set (2x2x3 pool matches + baseline) and self-verifies.
    Offline (engine + pool local seats)."""
    rc = main(["--run", "engine", "--n", "2", "--seed", "12345",
               "--out-dir", str(tmp_path), "--quiet"])
    assert rc == 0
    certs = list(tmp_path.glob("*.cert.json"))
    assert len(certs) == 1
    cert = json.loads(certs[0].read_text())
    assert cert["spec_version"] == "gauntlet-cert/3"
    assert cert["metrics"]["primary_statistic"] == "own_utility_pooled"
    assert cert["metrics"]["n_matches"] == 2 * 2 * 3
    assert set(cert["baseline"]["per_counterparty"]) == {
        "naive", "hardball", "conceder"}
    ok, _ = verify_certificate(cert)
    assert ok
