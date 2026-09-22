"""Reviewed bounded WQE observations; no invented UTC, identities or unit conversion."""

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from watergeo.ingestion.water_quality import (
    ID_PATTERN,
    ROOT,
    SAMPLING_POINT_ROOT,
    WaterQualityError,
    digest,
    encoded,
    string,
)

VERSION = "ea-water-quality-observations-v1"
OBSERVATION_CONTEXT = ROOT + "/context/wqa_observation_context.json-ld"
CODELIST_CONTEXT = ROOT + "/context/wqa_codelist_context.json-ld"
CODE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MAX_RECORDS = 5000


@dataclass(frozen=True)
class Scope:
    sampling_point_id: str
    determinand: str
    date_from: date
    date_to: date

    def __post_init__(self) -> None:
        if not ID_PATTERN.fullmatch(self.sampling_point_id) or not CODE.fullmatch(self.determinand):
            raise WaterQualityError("Invalid observation scope identity")
        if type(self.date_from) is not date or type(self.date_to) is not date:
            raise WaterQualityError("Observation scope requires calendar dates")
        if not 1 <= (self.date_to - self.date_from).days <= 31:
            raise WaterQualityError("Observation scope requires 1–31 calendar days, end-exclusive")

    def as_dict(self) -> dict[str, str]:
        return {
            "sampling_point_id": self.sampling_point_id,
            "determinand": self.determinand,
            "date_from": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat(),
        }


def code_record(raw: Any, kind: str, expected: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or kind not in {"unit", "determinand"}:
        raise WaterQualityError("Invalid codelist record")
    if not CODE.fullmatch(expected) or raw.get("notation") != expected:
        raise WaterQualityError("Codelist notation mismatch")
    if raw.get("@id") != f"_:{kind}#{expected}":
        raise WaterQualityError("Unreviewed codelist identity")
    string(raw.get("prefLabel"), "codelist label")
    string(raw.get("altLabel"), "codelist alternate label")
    return raw


def number(value: Any) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise WaterQualityError("Non-finite or non-numeric observation quantity")
    return float(value)


def linked_id(value: Any, prefix: str) -> str:
    identity = string(value, "publisher relationship", max_length=2048)
    if not identity.startswith(prefix) or not CODE.fullmatch(identity[len(prefix) :]):
        raise WaterQualityError("Observation relationship outside reviewed scope")
    return identity


@dataclass(frozen=True)
class Normalized:
    scope: Scope
    determinand: dict[str, Any]
    units: list[dict[str, Any]]
    observations: list[dict[str, Any]]

    @property
    def sha256(self) -> str:
        return digest(
            {
                "normalization_version": VERSION,
                "scope": self.scope.as_dict(),
                "determinand": self.determinand,
                "units": self.units,
                "observations": self.observations,
            }
        )


def normalize(
    scope: Scope,
    records: list[dict[str, Any]],
    determinand: dict[str, Any],
    units: list[dict[str, Any]],
) -> Normalized:
    code_record(determinand, "determinand", scope.determinand)
    if len(records) > MAX_RECORDS or len(units) > 20:
        raise WaterQualityError("Observation normalization budget exceeded")
    unit_map = {}
    for unit in units:
        code_record(unit, "unit", unit.get("notation", ""))
        if unit["notation"] in unit_map:
            raise WaterQualityError("Duplicate unit evidence")
        unit_map[unit["notation"]] = unit
    rows: dict[str, dict[str, Any]] = {}
    point_uri = SAMPLING_POINT_ROOT + scope.sampling_point_id
    used_units: set[str] = set()
    for raw in records:
        if not isinstance(raw, dict) or len(encoded(raw)) > 128 * 1024:
            raise WaterQualityError("Invalid or oversized observation")
        if raw.get("@type") != "sosa:Observation":
            raise WaterQualityError("Unreviewed observation type")
        point = raw.get("hasSamplingPoint")
        sample = raw.get("hasSample")
        quantity = raw.get("hasResult")
        if (
            not isinstance(point, dict)
            or point.get("id") != point_uri
            or point.get("notation") != scope.sampling_point_id
        ):
            raise WaterQualityError("Observation sampling-point scope mismatch")
        if not isinstance(sample, dict) or sample.get("@type") != "sosa:Sample":
            raise WaterQualityError("Missing publisher sample")
        sample_id = linked_id(sample.get("id"), point_uri + "/sample/")
        sampling = sample.get("isResultOf")
        if not isinstance(sampling, dict) or sampling.get("@type") != "sosa:Sampling":
            raise WaterQualityError("Missing publisher sampling")
        sampling_id = linked_id(sampling.get("id"), point_uri + "/sampling/")
        for relationship in (sample.get("hasSamplingPoint"), sampling.get("hasFeatureOfInterest")):
            if relationship is not None and (
                not isinstance(relationship, dict) or relationship.get("id") != point_uri
            ):
                raise WaterQualityError("Conflicting publisher sampling relationship")
        identity = linked_id(raw.get("id"), sample_id + "/observation/")
        if identity in rows:
            raise WaterQualityError("Duplicate observation identity")
        timestamp = string(raw.get("phenomenonTime"), "phenomenonTime", max_length=64)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?", timestamp):
            raise WaterQualityError("Unreviewed observation timestamp; no timezone is assumed")
        observed = datetime.fromisoformat(timestamp)
        if not scope.date_from <= observed.date() < scope.date_to:
            raise WaterQualityError("Observation outside requested date window")
        prop = code_record(raw.get("observedProperty"), "determinand", scope.determinand)
        if any(prop.get(key) != determinand.get(key) for key in ("prefLabel", "altLabel")):
            raise WaterQualityError("Determinand changed during retrieval")
        if not isinstance(quantity, dict) or quantity.get("@type") != "qudt:QuantityValue":
            raise WaterQualityError("Unreviewed quantity model")
        embedded_unit = quantity.get("hasUnit")
        if not isinstance(embedded_unit, dict):
            raise WaterQualityError("Missing quantity unit")
        unit_id = embedded_unit.get("notation")
        if not isinstance(unit_id, str) or unit_id not in unit_map:
            raise WaterQualityError("Unit without codelist evidence")
        code_record(embedded_unit, "unit", unit_id)
        unit = unit_map[unit_id]
        if (
            any(embedded_unit.get(key) != unit.get(key) for key in ("prefLabel", "altLabel"))
            or raw.get("hasUnit") != unit["altLabel"]
        ):
            raise WaterQualityError("Inconsistent observation unit")
        used_units.add(unit_id)
        values = {
            key: number(quantity.get(key)) for key in ("numericValue", "upperBound", "lowerBound")
        }
        if sum(value is not None for value in values.values()) > 1:
            raise WaterQualityError("Unreviewed simultaneous quantity values/bounds")
        result_text = raw.get("hasSimpleResult")
        if result_text is not None:
            string(result_text, "result text", max_length=256)
        for key, prefix in (("numericValue", ""), ("upperBound", "<"), ("lowerBound", ">")):
            if values[key] is not None:
                if not isinstance(result_text, str) or (
                    prefix and not result_text.startswith(prefix)
                ):
                    raise WaterQualityError("Quantity and result qualifier disagree")
                try:
                    parsed = float(result_text[len(prefix) :])
                except ValueError as error:
                    raise WaterQualityError("Unreviewed result qualifier") from error
                if parsed != values[key]:
                    raise WaterQualityError("Quantity and result text disagree")
        rows[identity] = {
            "observation_id": identity,
            "sampling_point_id": scope.sampling_point_id,
            "sample_id": sample_id,
            "sampling_id": sampling_id,
            "observed_at_text": timestamp,
            "determinand_notation": scope.determinand,
            "unit_notation": unit_id,
            "result_text": result_text,
            "numeric_value": values["numericValue"],
            "upper_bound": values["upperBound"],
            "lower_bound": values["lowerBound"],
            "source_fields": raw,
        }
    if used_units != set(unit_map):
        raise WaterQualityError("Unreferenced unit evidence")
    return Normalized(
        scope,
        determinand,
        [unit_map[key] for key in sorted(unit_map)],
        [rows[key] for key in sorted(rows)],
    )
