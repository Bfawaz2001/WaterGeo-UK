"""Deliberate numeric and timestamp semantics for stored-content verification."""

from datetime import datetime

from watergeo.db.hydrology_integrity import _canonical, _source_json
from watergeo.ingestion.hydrology import digest


def test_jsonb_order_and_numeric_scale_are_equivalent() -> None:
    left = _source_json('{"a":1,"b":[0.000001,-0.0]}')
    right = _source_json('{"b":[1e-6,0],"a":1.000}')
    assert digest(_canonical(left)) == digest(_canonical(right))


def test_jsonb_high_precision_alteration_is_detected() -> None:
    original = _source_json('{"value":1.2345678901234567890123456789012345}')
    altered = _source_json('{"value":1.2345678901234567890123456789012346}')
    assert digest(_canonical(original)) != digest(_canonical(altered))
    assert _canonical(_source_json("true")) != _canonical(_source_json("1"))


def test_queryable_floats_use_exact_binary_values() -> None:
    assert _canonical(0.0) != _canonical(-0.0)
    assert _canonical(1.0) != _canonical(1.0000000000000002)


def test_timestamp_digest_is_independent_of_session_timezone() -> None:
    assert _canonical(datetime.fromisoformat("2026-09-19T12:00:00+01:00")) == _canonical(
        datetime.fromisoformat("2026-09-19T11:00:00+00:00")
    )
