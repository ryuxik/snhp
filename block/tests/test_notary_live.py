"""The live twin-street driver notarizes each day: a signed, chained
NotaryReceipt whose counterfactual block carries the paired sticker-vs-snhp
day totals. These tests pin: every day-record carries a verifiable receipt, the
prev_hash chain verifies across a season (≥3 days), tampering the counterfactual
or a signed field is caught, and the snapshot exposes the chain head + pubkey.
Fast: two-venue worlds. All receipts here are ephemeral-key (no NOTARY_KEY_PEM).
"""
from __future__ import annotations

import json

from block.live import LiveBlock, read_log, replay_day, strip_ts
from block.venues import BlockConfig
from core.notary import verify_chain, verify_receipt

SEED = 20260710
TWO = ("vending", "bodega")
CFG2 = BlockConfig(regulars=5, bodega_adopts=True)


def _driver(**kw):
    kw.setdefault("seed", SEED)
    kw.setdefault("venues", TWO)
    kw.setdefault("cfg", CFG2)
    return LiveBlock(**kw)


def test_day_record_carries_a_verifiable_receipt():
    d = _driver()
    rec = d.step_day()
    att = rec["attestation"]
    assert att is not None and "notary_sig" in att
    # the counterfactual block is the day's paired totals — nothing invented
    cf = att["counterfactual"]
    assert cf["sticker_world_total"] == rec["block"]["margin"]["sticker"]
    assert cf["snhp_world_total"] == rec["block"]["margin"]["snhp"]
    assert cf["delta"] == rec["block"]["d_margin"]
    # verifiable with only the driver's published public key
    res = verify_receipt(att, pubkey_pem=d.notary_key.pubkey_pem)
    assert res["ok"] and res["key_source"] == "ephemeral"
    # a day is an AGGREGATE: it is a "ledger" receipt with honestly-null
    # economics and conditions — NO fabricated discount-only shell
    assert att["regime"] == "ledger"
    assert att["reservation_basis"] == "n/a(ledger)"
    assert att["conditions"]["b"] is None          # not attested for an aggregate
    assert att["conditions"]["a"] is None
    assert att["conditions"]["c"] is True          # engine version still attested
    assert att["list_price"] is None and att["saving"] is None
    # per-day receipts do NOT embed the PEM (trust pins on fpr; snapshot has it)
    assert att.get("pubkey_pem") is None
    # a consumer counting discount-only QUOTE receipts filters ledger out
    assert att["regime"] == "ledger"


def test_chain_verifies_across_a_season():
    d = _driver()
    recs = [d.step_day() for _ in range(4)]
    atts = [r["attestation"] for r in recs]
    assert atts[0]["prev_hash"] is None          # season head
    res = verify_chain(atts, pubkey_pem=d.notary_key.pubkey_pem)
    assert res["ok"] and res["chain_ok"] and res["n"] == 4 and not res["breaks"]
    # each link points at the previous receipt's digest
    from core.notary import canon_hash
    for i in range(1, 4):
        assert atts[i]["prev_hash"] == canon_hash(atts[i - 1])


def test_tampered_counterfactual_fails_verify():
    d = _driver()
    att = d.step_day()["attestation"]
    forged = {**att, "counterfactual": {**att["counterfactual"],
                                        "delta": att["counterfactual"]["delta"] + 99.0}}
    assert not verify_receipt(forged, pubkey_pem=d.notary_key.pubkey_pem)["ok"]
    # a broken chain link is caught too
    atts = [d.step_day()["attestation"] for _ in range(3)]
    atts[2] = {**atts[2], "prev_hash": "sha256:deadbeef"}
    assert not verify_chain([att, *atts],
                            pubkey_pem=d.notary_key.pubkey_pem)["chain_ok"]


def test_chain_resets_per_season():
    d = _driver(season_days=2)
    r0, r1, r2 = d.step_day(), d.step_day(), d.step_day()
    assert r0["attestation"]["prev_hash"] is None          # season 0 head
    assert r1["attestation"]["prev_hash"] is not None      # chained within season
    assert r2["attestation"]["prev_hash"] is None          # season 1: fresh chain
    # replay reproduces the attested record byte-for-byte (same process key)
    assert replay_day(1, 0, seed=SEED, venues=TWO, cfg=CFG2,
                      season_days=2) == r2


def test_logged_chain_verifies_and_resume_continues_it(tmp_path):
    log = str(tmp_path / "block-live.jsonl")
    d1 = _driver(log_path=log)
    [d1.step_day() for _ in range(3)]
    # the on-disk log verifies end-to-end via the standalone verifier
    atts = [r["attestation"] for r in read_log(log)]
    assert verify_chain(atts, pubkey_pem=d1.notary_key.pubkey_pem)["ok"]
    # the sidecar chain head matches the last receipt's digest
    from core.notary import canon_hash
    side = json.loads((tmp_path / "block-live.jsonl.chain.json").read_text())
    assert side["chain_head"] == canon_hash(atts[-1])
    # resume, then step: the new day continues the SAME chain
    d2 = _driver(log_path=log)
    d2.resume()
    r3 = d2.step_day()
    assert r3["attestation"]["prev_hash"] == canon_hash(atts[-1])
    all_atts = [r["attestation"] for r in read_log(log)]
    assert verify_chain(all_atts, pubkey_pem=d2.notary_key.pubkey_pem)["ok"]


def test_snapshot_exposes_chain_head_and_pubkey():
    d = _driver()
    d.step_day()
    d.step_day()
    nt = d.public["notary"]
    assert nt["chain_head"] == d._chain_head
    assert "BEGIN PUBLIC KEY" in nt["pubkey_pem"]
    assert nt["pubkey_fpr"].startswith("sha256:")
    assert nt["key_source"] == "ephemeral" and nt["algo"] == "ed25519"
    # the exposed head is the digest of the last window record's receipt
    from core.notary import canon_hash
    last_att = list(d.window)[-1]["attestation"]
    assert nt["chain_head"] == canon_hash(last_att)
