"""Read-only evidence for WGS84 output; candidates never become API policy."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import shapely
from sqlalchemy import Connection, Engine, text

from watergeo.core.datasets import OFWAT_WATER_SUPPLY_SHA256, OFWAT_WATER_SUPPLY_TRANSFORMATION
from watergeo.db.water_supply import MAX_GEOMETRY_BYTES

ASSESSMENT_VERSION = "ofwat-water-supply-wgs84-assessment-v1"
MAX_CANDIDATE_AREAS = 20
MAX_CANDIDATE_POINTS = 1_000_000
CANDIDATES = (
    "direct",
    "segmentize_100m",
    "segmentize_10m",
    "segmentize_1m",
    "linework",
    "structure_keep",
    "structure_drop",
)
BASELINE_SQL = text("""
    WITH output AS MATERIALIZED (
        SELECT public.ST_AsGeoJSON(
            public.ST_ForcePolygonCCW(public.ST_Transform(geom, 4326)), 15, 0
        ) AS geojson
        FROM watergeo.water_supply_area
        WHERE snapshot_id = :snapshot_id AND source_id = :source_id
    )
    SELECT octet_length(geojson) AS byte_count,
           CASE WHEN octet_length(geojson) <= :max_bytes
                THEN public.ST_IsValid(public.ST_GeomFromGeoJSON(geojson), 0)
                ELSE false END AS valid
    FROM output
""")


class PresentationAssessmentError(RuntimeError):
    """An assessment cannot be completed without changing its review scope."""


def _segments(geometry: Any) -> list[Any]:
    """Index individual boundary segments, including any collapsed lines/points."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return _segments(geometry.boundary)
    if geometry.geom_type in {"LineString", "LinearRing"}:
        coordinates = shapely.get_coordinates(geometry)
        return list(
            shapely.linestrings([coordinates[i : i + 2] for i in range(len(coordinates) - 1)])
        )
    if geometry.geom_type == "Point":
        return [geometry]
    return [segment for part in geometry.geoms for segment in _segments(part)]


def boundary_hausdorff(left: Any, right: Any) -> float:
    """Symmetric discrete boundary Hausdorff distance, at existing vertices.

    Equivalent to the undensified boundary metric, not continuous Hausdorff.
    Indexing segments avoids an all-pairs scan for 100,000+ vertex boundaries.
    This offline diagnostic never participates in API spatial queries.
    """
    if left.is_empty or right.is_empty:
        raise PresentationAssessmentError("Cannot measure an empty boundary.")
    maximum = 0.0
    for source, target in ((left, right), (right, left)):
        tree = shapely.STRtree(_segments(target))
        coordinates = shapely.get_coordinates(source)
        for offset in range(0, len(coordinates), 4096):
            _, distances = tree.query_nearest(
                shapely.points(coordinates[offset : offset + 4096]),
                return_distance=True,
                all_matches=False,
            )
            maximum = max(maximum, float(distances.max()))
    return maximum


def canonical_digest(connection: Connection, snapshot_id: UUID) -> str:
    """Hash ordered IDs, complete source fields and canonical EWKB for all areas."""
    return str(
        connection.execute(
            text("""
        SELECT encode(sha256(convert_to(string_agg(
            source_id::text || ':' ||
            encode(sha256(convert_to(source_fields::text, 'UTF8')), 'hex') || ':' ||
            encode(sha256(public.ST_AsEWKB(geom, 'NDR')), 'hex'), ',' ORDER BY source_id
        ), 'UTF8')), 'hex')
        FROM watergeo.water_supply_area WHERE snapshot_id = :snapshot
    """),
            {"snapshot": snapshot_id},
        ).scalar_one()
    )


def component_correspondence(canonical: Any, candidate: Any) -> dict[str, Any]:
    """Describe intersecting polygon parts; net counts alone hide splits/merges."""
    before = list(canonical.geoms)

    def polygons(geometry: Any) -> list[Any]:
        if geometry.geom_type == "Polygon":
            return [geometry]
        return [polygon for part in getattr(geometry, "geoms", []) for polygon in polygons(part)]

    after = polygons(candidate)
    matches = shapely.STRtree(after).query(before, predicate="intersects")
    before_counts = [0] * len(before)
    after_counts = [0] * len(after)
    for left, right in matches.T:
        before_counts[int(left)] += 1
        after_counts[int(right)] += 1
    return {
        "canonical_parts_without_candidate_intersection": before_counts.count(0),
        "candidate_parts_without_canonical_intersection": after_counts.count(0),
        "canonical_parts_intersecting_multiple_candidates": sum(n > 1 for n in before_counts),
        "candidate_parts_intersecting_multiple_canonical": sum(n > 1 for n in after_counts),
    }


def inspect_candidate(
    connection: Connection,
    snapshot_id: UUID,
    source_id: int,
    candidate: str,
    *,
    geometry_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure one fixed candidate without persisting it.

    Round-trip area metrics include projection/serialization effects. They do not
    isolate the repair's contribution or establish that boundary changes are safe.
    """
    if candidate not in CANDIDATES:
        raise ValueError("Unknown presentation candidate.")
    # A conservative bound on segmentized vertices: existing points + length / step.
    segment_length = {"segmentize_100m": 100, "segmentize_10m": 10, "segmentize_1m": 1}.get(
        candidate
    )
    parameters = {"snapshot_id": snapshot_id, "source_id": source_id, "candidate": candidate}
    original = (
        connection.execute(
            text("""
        SELECT encode(sha256(public.ST_AsBinary(geom, 'NDR')), 'hex') AS wkb_sha256,
               public.ST_NPoints(geom) AS points,
               public.ST_NumGeometries(geom) AS parts,
               public.ST_NRings(geom) - public.ST_NumGeometries(geom) AS holes,
               public.ST_Area(geom) AS area_m2,
               public.ST_Perimeter(geom) AS perimeter_m
        FROM watergeo.water_supply_area
        WHERE snapshot_id = :snapshot_id AND source_id = :source_id
    """),
            parameters,
        )
        .mappings()
        .one()
    )
    evidence: dict[str, Any] = {"candidate": candidate, "canonical": dict(original)}
    if segment_length and (
        original["points"] + original["perimeter_m"] / segment_length > MAX_CANDIDATE_POINTS
    ):
        return {**evidence, "status": "skipped_vertex_budget"}
    # CTEs avoid repeating expensive transformation and geometry validation work.
    result = (
        connection.execute(
            text(
                """
        WITH source AS MATERIALIZED (
            SELECT geom FROM watergeo.water_supply_area
            WHERE snapshot_id = :snapshot_id AND source_id = :source_id
        ), candidate AS MATERIALIZED (
            SELECT CASE :candidate
                WHEN 'direct' THEN public.ST_Transform(geom, 4326)
                WHEN 'segmentize_100m' THEN public.ST_Transform(public.ST_Segmentize(geom,100),4326)
                WHEN 'segmentize_10m' THEN public.ST_Transform(public.ST_Segmentize(geom,10),4326)
                WHEN 'segmentize_1m' THEN public.ST_Transform(public.ST_Segmentize(geom,1),4326)
                WHEN 'linework' THEN public.ST_MakeValid(public.ST_Transform(geom,4326),
                                                       'method=linework')
                WHEN 'structure_keep' THEN public.ST_MakeValid(public.ST_Transform(geom,4326),
                                                       'method=structure keepcollapsed=true')
                WHEN 'structure_drop' THEN public.ST_MakeValid(public.ST_Transform(geom,4326),
                                                       'method=structure keepcollapsed=false')
            END AS geom FROM source
        ), serialized AS MATERIALIZED (
            SELECT geom, public.ST_AsGeoJSON(public.ST_ForcePolygonCCW(geom), 15, 0) j
            FROM candidate
        ), output AS MATERIALIZED (
            SELECT geom, j, public.ST_GeomFromGeoJSON(j) decoded FROM serialized
        ), roundtrip AS MATERIALIZED (
            SELECT *, public.ST_Transform(decoded, 27700) back FROM output
        ), checked AS MATERIALIZED (
            SELECT *, public.ST_IsValid(decoded, 0) output_valid,
                      public.ST_IsValid(back, 0) back_valid FROM roundtrip
        )
        SELECT public.ST_GeometryType(decoded) AS geometry_type,
               public.ST_IsEmpty(decoded) AS empty,
               public.ST_IsValid(checked.geom, 0) AS before_serialization_valid,
               output_valid, public.ST_IsValidReason(decoded) AS validity_reason,
               public.ST_NPoints(decoded) AS points,
               public.ST_NumGeometries(public.ST_CollectionExtract(decoded, 3)) AS parts,
               public.ST_NRings(public.ST_CollectionExtract(decoded, 3))
                 - public.ST_NumGeometries(public.ST_CollectionExtract(decoded, 3)) AS holes,
               EXISTS (SELECT 1 FROM public.ST_Dump(decoded) part
                       WHERE public.ST_Dimension(part.geom) < 2) AS lower_dimension_parts,
               octet_length(j) AS geometry_bytes,
               encode(sha256(convert_to(j, 'UTF8')), 'hex') AS geojson_sha256,
               encode(sha256(public.ST_AsBinary(decoded, 'NDR')), 'hex') AS output_wkb_sha256,
               back_valid AS roundtrip_valid,
               public.ST_IsValidReason(back) AS roundtrip_validity_reason,
               public.ST_Area(back) - public.ST_Area(source.geom) AS area_delta_untrusted_m2,
               CASE WHEN back_valid
                    THEN public.ST_Area(back) - public.ST_Area(source.geom) END AS area_delta_m2,
               CASE WHEN back_valid
                    THEN public.ST_Area(public.ST_SymDifference(source.geom, back))
                    END AS symmetric_difference_m2,
               public.ST_AsBinary(source.geom, 'NDR') AS canonical_wkb,
               public.ST_AsBinary(decoded, 'NDR') AS output_wkb,
               public.ST_AsBinary(back, 'NDR') AS roundtrip_wkb
        FROM checked CROSS JOIN source
    """
            ),
            parameters,
        )
        .mappings()
        .one()
    )
    output = dict(result)
    canonical = shapely.from_wkb(bytes(output.pop("canonical_wkb")))
    roundtrip = shapely.from_wkb(bytes(output.pop("roundtrip_wkb")))
    decoded = shapely.from_wkb(bytes(output.pop("output_wkb")))
    if geometry_evidence is not None and candidate in {
        "linework",
        "structure_keep",
        "structure_drop",
    }:
        geometry_evidence[candidate] = (decoded, roundtrip)
    output["boundary_hausdorff_m"] = boundary_hausdorff(canonical, roundtrip)
    output["component_correspondence"] = (
        component_correspondence(canonical, roundtrip) if output["roundtrip_valid"] else None
    )
    output["part_count_delta"] = output["parts"] - original["parts"]
    output["hole_count_delta"] = output["holes"] - original["holes"]
    output["within_api_byte_limit"] = output["geometry_bytes"] <= MAX_GEOMETRY_BYTES
    return {**evidence, "status": "measured", "output": output}


def assess_feature(connection: Connection, snapshot: UUID, source_id: int) -> dict[str, Any]:
    geometries: dict[str, Any] = {}
    candidates = [
        inspect_candidate(connection, snapshot, source_id, name, geometry_evidence=geometries)
        for name in CANDIDATES
    ]
    comparisons = []
    for left_name, right_name in (
        ("structure_drop", "linework"),
        ("structure_drop", "structure_keep"),
    ):
        left, left_back = geometries[left_name]
        right, right_back = geometries[right_name]
        comparisons.append(
            {
                "left": left_name,
                "right": right_name,
                "wgs84_topologically_equal": bool(left.equals(right)),
                "roundtrip_symmetric_difference_m2": (
                    float(left_back.symmetric_difference(right_back).area)
                    if left_back.is_valid and right_back.is_valid
                    else None
                ),
                "roundtrip_boundary_hausdorff_m": boundary_hausdorff(left_back, right_back),
            }
        )
    return {"source_id": source_id, "candidates": candidates, "comparisons": comparisons}


def assess_presentation(engine: Engine) -> dict[str, Any]:
    """Audit every API representation, then compare candidates only for failures.

    Caller configures a bounded diagnostic statement timeout. The API's own
    three-second timeout is not changed. This is not an HTTP latency benchmark.
    """
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection,
        connection.begin(),
    ):
        connection.execute(text("SET TRANSACTION READ ONLY"))
        runtime = dict(
            connection.execute(
                text("""
                SELECT public.PostGIS_Lib_Version() AS postgis,
                       public.PostGIS_GEOS_Version() AS geos,
                       public.PostGIS_PROJ_Version() AS proj,
                       current_setting('server_version') AS postgres,
                       current_setting('statement_timeout') AS statement_timeout,
                       current_setting('transaction_read_only') AS transaction_read_only
            """)
            )
            .mappings()
            .one()
        )
        snapshot = connection.execute(
            text("""
                SELECT id FROM watergeo.water_supply_snapshot
                WHERE source_sha256 = :sha AND transformation_version = :version
            """),
            {"sha": OFWAT_WATER_SUPPLY_SHA256, "version": OFWAT_WATER_SUPPLY_TRANSFORMATION},
        ).scalar_one_or_none()
        if snapshot is None:
            raise PresentationAssessmentError("The reviewed snapshot is not loaded.")
        ids = list(
            connection.execute(
                text("""
                SELECT source_id FROM watergeo.water_supply_area
                WHERE snapshot_id = :snapshot ORDER BY source_id
            """),
                {"snapshot": snapshot},
            ).scalars()
        )
        if ids != list(range(1, 1142)):
            raise PresentationAssessmentError("Expected exactly source IDs 1 through 1141.")
        before = canonical_digest(connection, snapshot)
        baseline = []
        failed_ids = []
        for source_id in ids:
            row = (
                connection.execute(
                    BASELINE_SQL,
                    {
                        "snapshot_id": snapshot,
                        "source_id": source_id,
                        "max_bytes": MAX_GEOMETRY_BYTES,
                    },
                )
                .mappings()
                .one()
            )
            status = "available" if row["valid"] else "invalid"
            if row["byte_count"] > MAX_GEOMETRY_BYTES:
                status = "oversized"
            baseline.append(
                {"source_id": source_id, "status": status, "geometry_bytes": row["byte_count"]}
            )
            if status != "available":
                failed_ids.append(source_id)
        if len(failed_ids) > MAX_CANDIDATE_AREAS:
            raise PresentationAssessmentError("Too many failing areas; review assessment scope.")
        features = [assess_feature(connection, snapshot, source_id) for source_id in failed_ids]
        runtime.update(shapely=shapely.__version__, shapely_geos=shapely.geos_version_string)
        report = {
            "assessment_version": ASSESSMENT_VERSION,
            "status": "diagnostic_only_not_approved",
            "assessed_at": datetime.now(UTC).isoformat(),
            "source_sha256": OFWAT_WATER_SUPPLY_SHA256,
            "transformation_version": OFWAT_WATER_SUPPLY_TRANSFORMATION,
            "snapshot_id": str(snapshot),
            "runtime": runtime,
            "geometry_hash_encoding": "Little-endian 2D WKB, no SRID, no normalization",
            "max_geometry_bytes": MAX_GEOMETRY_BYTES,
            "max_candidate_points": MAX_CANDIDATE_POINTS,
            "canonical_rows_sha256_before": before,
            "hausdorff_method": "Symmetric discrete boundary Hausdorff at existing vertices",
            "baseline": baseline,
            "failed_source_ids": failed_ids,
            "features": features,
        }
    # A fresh transaction can see any committed change hidden by the assessment's
    # repeatable-read snapshot. No writer credentials are used by this tool.
    with engine.connect() as connection:
        after = canonical_digest(connection, snapshot)
    if before != after:
        raise PresentationAssessmentError("Canonical rows changed during assessment.")
    report["canonical_rows_sha256_after"] = after
    return report
