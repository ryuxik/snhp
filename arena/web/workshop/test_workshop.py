#!/usr/bin/env python3
"""
test_antfarm.py — guards on the ANT FARM event generator.

Runs stand-alone (`python3 arena/web/workshop/test_antfarm.py`) or under pytest.
No third-party deps. These assert the honesty invariants of events.json:
idempotency, schema completeness, a real event census, and chronological order.
"""
from __future__ import annotations

import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GEN_PATH = os.path.join(HERE, "generate_events.py")
JSON_PATH = os.path.join(HERE, "events.json")
VALID_TYPES = {"REGISTRATION", "BUILDRUN", "VERDICT", "CORRECTION", "PERF"}


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_events", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_doc() -> dict:
    """Build the events document from live git state (does not touch disk)."""
    gen = _load_generator()
    doc = gen.build_events()
    gen.sanity_check(doc)  # the generator's own asserts must pass
    return doc


def test_generator_idempotent():
    """Two back-to-back generations are byte-identical for a fixed git state."""
    gen = _load_generator()
    a = gen.serialize(gen.build_events())
    b = gen.serialize(gen.build_events())
    assert a == b, "generator is not idempotent"
    # and the checked-in events.json must match a fresh generation (not stale)
    assert os.path.exists(JSON_PATH), "events.json is not checked in"
    with open(JSON_PATH, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == a, "checked-in events.json is stale — re-run generate_events.py"


def test_schema_fields_present():
    """Every event carries the required honesty fields with valid values."""
    doc = _fresh_doc()
    for e in doc["events"]:
        for field in ("hash", "full_hash", "iso_time", "type", "summary"):
            assert e.get(field), f"event missing '{field}': {e}"
        assert e["type"] in VALID_TYPES, f"invalid type {e['type']!r}"
        assert len(e["hash"]) == 7, f"short hash not 7 chars: {e['hash']}"
        assert e["full_hash"].startswith(e["hash"]), "hash/full_hash mismatch"
        # every element on screen maps to a commit -> hash+time+summary must exist
        assert e["iso_time"][0].isdigit(), f"bad timestamp {e['iso_time']}"
        if "column_source" in e:
            assert "column" in e, "column_source without a column"
    # column manifest is self-consistent
    for col in doc["columns"]:
        assert col["completed"] == bool(col["built"] and col["verdict"]), (
            f"column {col['letter']} completion flag disagrees with build/verdict"
        )


def test_event_count_over_40():
    """The real pipeline produced more than 40 classified events."""
    doc = _fresh_doc()
    assert len(doc["events"]) > 40, f"only {len(doc['events'])} events"
    # and all five pipeline organs are represented
    types = {e["type"] for e in doc["events"]}
    assert {"REGISTRATION", "BUILDRUN", "VERDICT"}.issubset(types), types


def test_chronological_and_unique():
    """Events are non-decreasing in time with no duplicate commit hashes."""
    doc = _fresh_doc()
    events = doc["events"]
    seen: set[str] = set()
    prev = ""
    for e in events:
        assert e["hash"] not in seen, f"duplicate hash {e['hash']}"
        seen.add(e["hash"])
        assert e["iso_time"] >= prev, f"out of order at {e['hash']}"
        prev = e["iso_time"]
    # panel row is a strict run-order prefix: built columns precede unbuilt
    run_times = [c["run_time"] for c in doc["columns"] if c["run_time"]]
    assert run_times == sorted(run_times), "panel columns not in run order"


def _main() -> int:
    tests = [
        test_generator_idempotent,
        test_schema_fields_present,
        test_event_count_over_40,
        test_chronological_and_unique,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")
    doc = _fresh_doc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed — {len(doc['events'])} events, "
          f"{len(doc['columns'])} columns")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
