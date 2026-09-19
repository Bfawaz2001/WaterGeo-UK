"""Strict normalization for bounded Environment Agency hydrology history."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from watergeo.ingestion.hydrology import (
    ID_PATTERN,
    HydrologyError,
    digest,
    number,
    reference,
    string,
    timestamp,
)

VERSION = "ea-hydrology-history-v1"


@dataclass(frozen=True)
class NormalizedHistory:
    measure_id: str
    observations: list[dict[str, Any]]
    sha256: str

    @property
    def record_count(self) -> int:
        return len(self.observations)


def normalize_history(
    measure_id: str,
    records: list[dict[str, Any]],
) -> NormalizedHistory:
    """Normalize one bounded historical retrieval for one publisher measure."""

    if not isinstance(measure_id, str) or not re.fullmatch(ID_PATTERN, measure_id):
        raise HydrologyError("Invalid history measure identity")

    if not isinstance(records, list):
        raise HydrologyError("Invalid history records")

    observations: dict[str, dict[str, Any]] = {}

    for raw in records:
        if not isinstance(raw, dict):
            raise HydrologyError("Invalid historical observation")

        source_measure_id = reference(raw.get("measure"), "measures")
        if source_measure_id != measure_id:
            raise HydrologyError("Historical observation measure mismatch")

        observed = timestamp(raw.get("dateTime"))
        observed_key = observed.isoformat()

        if observed_key in observations:
            raise HydrologyError("Duplicate historical observation timestamp")

        raw_date = string(raw.get("date"), "observation date")

        try:
            expected_date = datetime.fromisoformat(raw_date).date()
        except ValueError as error:
            raise HydrologyError("Invalid observation date") from error

        if raw_date != expected_date.isoformat():
            raise HydrologyError("Invalid observation date")

        if expected_date != observed.date():
            raise HydrologyError("Observation date/time mismatch")

        quality = string(raw.get("quality"), "observation quality")

        value = raw.get("value")

        if value is None:
            if quality != "Missing":
                raise HydrologyError("Missing historical observation value without Missing quality")
        else:
            value = number(value, "historical observation value")

            if quality == "Missing":
                raise HydrologyError("Numeric historical observation contradicts Missing quality")

        observations[observed_key] = {
            "measure_id": measure_id,
            "observed_at": observed_key,
            "value": value,
            "source_fields": raw,
        }

    rows = [observations[key] for key in sorted(observations)]

    return NormalizedHistory(
        measure_id=measure_id,
        observations=rows,
        sha256=digest(
            {
                "version": VERSION,
                "measure_id": measure_id,
                "rows": rows,
            }
        ),
    )
