import pytest
from duration import parse_duration


def test_basic_combo():
    assert parse_duration("1h30m") == 5400

def test_seconds_only():
    assert parse_duration("45s") == 45

def test_hours_only():
    assert parse_duration("2h") == 7200

def test_all_three():
    assert parse_duration("1h30m15s") == 5415

def test_minutes_overflow():
    assert parse_duration("90m") == 5400

def test_whitespace_stripped():
    assert parse_duration("  10s  ") == 10

def test_empty_raises():
    with pytest.raises(ValueError):
        parse_duration("")

def test_no_unit_raises():
    with pytest.raises(ValueError):
        parse_duration("100")

def test_unknown_unit_raises():
    with pytest.raises(ValueError):
        parse_duration("5x")

def test_negative_raises():
    with pytest.raises(ValueError):
        parse_duration("-5s")

def test_out_of_order_raises():
    with pytest.raises(ValueError):
        parse_duration("1m30h")

def test_repeated_unit_raises():
    with pytest.raises(ValueError):
        parse_duration("1h1h")

def test_trailing_junk_raises():
    with pytest.raises(ValueError):
        parse_duration("1h!")
