"""Read compatible snapshot metadata with a single database clock and bounded queries."""

from datetime import datetime
from typing import Any

from sqlalchemy import Engine, text

from watergeo.api.source_models import Freshness, SourceStatus, SourceStatuses
from watergeo.core.config import Settings
from watergeo.core.datasets import OFWAT_WATER_SUPPLY_SHA256, OFWAT_WATER_SUPPLY_TRANSFORMATION
from watergeo.ingestion.catchments import PLAN_VERSION
from watergeo.ingestion.catchments import VERSION as CATCHMENT_VERSION
from watergeo.ingestion.hydrology import VERSION as HYDROLOGY_VERSION
from watergeo.ingestion.hydrology_history import VERSION as HISTORY_VERSION


def age(now: datetime, value: datetime | None) -> float | None:
    if value is None or value > now:
        return None
    return (now - value).total_seconds()


def freshness(seconds: float | None, threshold: int | None) -> Freshness:
    if seconds is None or threshold is None:
        return "unknown"
    return "stale" if seconds > threshold else "current"


def describe(
    source: str,
    row: dict[str, Any] | None,
    now: datetime,
    settings: Settings,
) -> SourceStatus:
    contracts: dict[str, tuple[str, str, str | None, str]] = {
        "ofwat": (
            "versioned_release",
            OFWAT_WATER_SUPPLY_TRANSFORMATION,
            "2024-04 / v1_5",
            "Reviewed static release. Retrieval age does not establish a newer publisher release.",
        ),
        "hydrology": (
            "dynamic_snapshot",
            HYDROLOGY_VERSION,
            None,
            "Current/stale refer only to configured operator age limits, not a publisher SLA. "
            "Retrieval time is not observation time; current does not establish reading quality.",
        ),
        "hydrology-history": (
            "bounded_history",
            HISTORY_VERSION,
            None,
            "Latest accepted bounded retrieval only; not coverage or freshness of all "
            "measures/history. Old observations can be correct for the requested window.",
        ),
        "catchments": (
            "versioned_plan",
            CATCHMENT_VERSION,
            PLAN_VERSION,
            "Reviewed Cycle 3 plan. Retrieval age does not establish publisher revision time "
            "or whether a newer plan exists.",
        ),
    }
    semantics, version, source_version, caveat = contracts[source]
    values: dict[str, Any] = dict(row or {})
    values.update(
        source=source,
        semantics=semantics,
        normalization_version=version,
        source_version=source_version,
        caveat=caveat,
        availability="available" if row else "unavailable",
    )
    values["snapshot_age_seconds"] = age(now, values.get("retrieved_at"))
    if source == "hydrology":
        values["retrieval_max_age_seconds"] = settings.hydrology_retrieval_max_age_seconds
        values["observation_max_age_seconds"] = settings.hydrology_observation_max_age_seconds
        values["retrieval_freshness"] = freshness(
            values["snapshot_age_seconds"], settings.hydrology_retrieval_max_age_seconds
        )
        oldest = age(now, values.get("observation_oldest_at"))
        newest = age(now, values.get("observation_newest_at"))
        observed = freshness(oldest, settings.hydrology_observation_max_age_seconds)
        if observed == "current" and (
            newest is None
            or values.get("missing_value_count", 0)
            or values.get("measures_without_observation_count", 0)
        ):
            observed = "unknown"
        values.update(observation_freshness=observed)
    else:
        values["retrieval_freshness"] = "not_applicable" if row else "unknown"
    for bound in ("oldest", "newest"):
        values[f"{bound}_observation_age_seconds"] = age(now, values.get(f"observation_{bound}_at"))
    return SourceStatus.model_validate(values)


def source_statuses(engine: Engine, settings: Settings) -> SourceStatuses:
    queries = {
        "ofwat": """SELECT id AS snapshot_id, source_sha256 AS content_sha256,
            retrieved_at FROM watergeo.water_supply_snapshot
            WHERE source_sha256=:ofwat_hash AND transformation_version=:ofwat_version""",
        "hydrology": """WITH latest AS (
            SELECT * FROM watergeo.hydrology_snapshot WHERE normalization_version=:hydrology_version
            ORDER BY retrieval_completed_at DESC, id DESC LIMIT 1)
            SELECT s.id AS snapshot_id, s.content_sha256, s.retrieval_started_at,
                s.retrieval_completed_at AS retrieved_at, o.*,
                s.measure_count - o.observation_count AS measures_without_observation_count
            FROM latest s CROSS JOIN LATERAL (
                SELECT min(observed_at) AS observation_oldest_at,
                    max(observed_at) AS observation_newest_at, count(*) AS observation_count,
                    count(*) FILTER (WHERE value IS NULL) AS missing_value_count
                FROM watergeo.hydrology_latest_observation WHERE snapshot_id=s.id) o""",
        "hydrology-history": """WITH latest AS (
            SELECT * FROM watergeo.hydrology_history_retrieval
            WHERE normalization_version=:history_version
            ORDER BY retrieval_completed_at DESC, id DESC LIMIT 1)
            SELECT s.id AS snapshot_id, s.content_sha256, s.retrieval_started_at,
                s.retrieval_completed_at AS retrieved_at, s.measure_id,
                s.requested_from, s.requested_to, o.*
            FROM latest s CROSS JOIN LATERAL (
                SELECT min(observed_at) AS observation_oldest_at,
                    max(observed_at) AS observation_newest_at, count(*) AS observation_count,
                    count(*) FILTER (WHERE value IS NULL) AS missing_value_count
                FROM watergeo.hydrology_historical_observation WHERE retrieval_id=s.id) o""",
        "catchments": """SELECT id AS snapshot_id, content_sha256, retrieval_started_at,
            retrieval_completed_at AS retrieved_at FROM watergeo.catchment_snapshot
            WHERE normalization_version=:catchment_version AND plan_version=:plan
            ORDER BY retrieval_completed_at DESC, id DESC LIMIT 1""",
    }
    parameters = {
        "ofwat_hash": OFWAT_WATER_SUPPLY_SHA256,
        "ofwat_version": OFWAT_WATER_SUPPLY_TRANSFORMATION,
        "hydrology_version": HYDROLOGY_VERSION,
        "history_version": HISTORY_VERSION,
        "catchment_version": CATCHMENT_VERSION,
        "plan": PLAN_VERSION,
    }
    # Snapshot metadata and observation summaries must describe the same database view.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        now = connection.execute(text("SELECT transaction_timestamp()")).scalar_one()
        sources = []
        for source, sql in queries.items():
            row = connection.execute(text(sql), parameters).mappings().one_or_none()
            sources.append(describe(source, dict(row) if row else None, now, settings))
    return SourceStatuses(checked_at=now, sources=sources)
