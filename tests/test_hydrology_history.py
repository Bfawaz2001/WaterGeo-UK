"""Historical Environment Agency hydrology normalization tests."""

import pytest

from watergeo.ingestion.hydrology import HydrologyError
from watergeo.ingestion.hydrology_history import normalize_history

MEASURE_ID = "abc-flow-i-900-m3s-qualified"
MEASURE_URI = "http://environment.data.gov.uk/hydrology/id/measures/" + MEASURE_ID


def reading(
    timestamp: str,
    *,
    value: float | None = 1.25,
    quality: str = "Unchecked",
) -> dict:
    result = {
        "measure": {"@id": MEASURE_URI},
        "date": timestamp[:10],
        "dateTime": timestamp,
        "quality": quality,
    }

    if value is not None:
        result["value"] = value

    return result


def test_history_normalizes_and_sorts() -> None:
    result = normalize_history(
        MEASURE_ID,
        [
            reading("2026-09-19T00:15:00", value=2.0),
            reading("2026-09-19T00:00:00", value=1.0),
        ],
    )

    assert result.record_count == 2
    assert [row["observed_at"] for row in result.observations] == [
        "2026-09-19T00:00:00+00:00",
        "2026-09-19T00:15:00+00:00",
    ]


def test_history_missing_value_is_preserved() -> None:
    result = normalize_history(
        MEASURE_ID,
        [
            reading(
                "2025-09-07T02:15:00",
                value=None,
                quality="Missing",
            )
        ],
    )

    assert result.record_count == 1
    assert result.observations[0]["value"] is None
    assert result.observations[0]["source_fields"]["quality"] == "Missing"
    assert "value" not in result.observations[0]["source_fields"]


def test_history_zero_is_not_missing() -> None:
    result = normalize_history(
        MEASURE_ID,
        [
            reading(
                "2026-09-19T00:00:00",
                value=0,
                quality="Unchecked",
            )
        ],
    )

    assert result.observations[0]["value"] == 0


def test_history_duplicate_timestamp_fails_closed() -> None:
    row = reading("2026-09-19T00:00:00")

    with pytest.raises(
        HydrologyError,
        match="Duplicate historical observation timestamp",
    ):
        normalize_history(MEASURE_ID, [row, row])


def test_history_measure_mismatch_fails_closed() -> None:
    row = reading("2026-09-19T00:00:00")
    row["measure"]["@id"] = (
        "http://environment.data.gov.uk/hydrology/id/measures/different-flow-i-900-m3s-qualified"
    )

    with pytest.raises(
        HydrologyError,
        match="measure mismatch",
    ):
        normalize_history(MEASURE_ID, [row])


@pytest.mark.parametrize(
    ("value", "quality"),
    [
        (None, "Unchecked"),
        (1.0, "Missing"),
    ],
)
def test_history_value_quality_contradictions_fail(
    value: float | None,
    quality: str,
) -> None:
    with pytest.raises(HydrologyError):
        normalize_history(
            MEASURE_ID,
            [
                reading(
                    "2026-09-19T00:00:00",
                    value=value,
                    quality=quality,
                )
            ],
        )


def test_history_date_must_match_timestamp() -> None:
    row = reading("2026-09-19T00:00:00")
    row["date"] = "2026-09-18"

    with pytest.raises(
        HydrologyError,
        match="date/time mismatch",
    ):
        normalize_history(MEASURE_ID, [row])


def test_empty_history_is_valid() -> None:
    result = normalize_history(MEASURE_ID, [])

    assert result.record_count == 0
    assert result.observations == []


def test_history_digest_is_deterministic() -> None:
    rows = [
        reading("2026-09-19T00:15:00", value=2),
        reading("2026-09-19T00:00:00", value=1),
    ]

    forward = normalize_history(MEASURE_ID, rows)
    reverse = normalize_history(MEASURE_ID, list(reversed(rows)))

    assert forward.sha256 == reverse.sha256


@pytest.mark.parametrize(
    "measure_id",
    [
        "",
        "not/a/measure",
        "x" * 257,
    ],
)
def test_invalid_measure_identity_rejected_even_when_empty(
    measure_id: str,
) -> None:
    with pytest.raises(HydrologyError, match="Invalid history measure identity"):
        normalize_history(measure_id, [])
