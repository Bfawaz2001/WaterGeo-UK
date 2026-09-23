"""Synthetic EA Water Quality Explorer tests; never contact the live publisher."""

from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest

from watergeo.ingestion.water_quality import (
    API_VERSION,
    CONTEXT,
    CRS_4326,
    WaterQualityError,
    decode,
    normalize,
    point_geometry,
)
from watergeo.ingestion.water_quality_client import (
    check_url,
    fetch_snapshot,
    read_snapshot,
    request_url,
)


def record(
    notation: str, *, longitude: float = -1.192, latitude: float = 52.0473
) -> dict[str, Any]:
    root = "https://environment.data.gov.uk/water-quality/sampling-point/"
    return {
        "id": root + notation,
        "@type": ["sosa:FeatureOfInterest", "geo:Feature"],
        "altLabel": f"ALT {notation}",
        "prefLabel": f"Preferred {notation}",
        "notation": notation,
        "hasObservations": root + notation + "/observation",
        "geometry": {
            "id": root + notation + "#Geometry",
            "@type": "geo:Geometry",
            "asWKT": (
                f"POINT({longitude} {latitude}) <http://www.opengis.net/def/crs/EPSG/0/4326>"
            ),
        },
        "samplingPointStatus": {"notation": "O", "prefLabel": "OPEN"},
        "samplingPointType": {"notation": "UA", "prefLabel": "Synthetic type"},
        "region": {"notation": "AN", "prefLabel": "Anglian"},
        "area": {"notation": "L", "prefLabel": "Synthetic area"},
        "subArea": {"notation": "L-S", "prefLabel": "Synthetic sub area"},
    }


RECORDS = [record("AN-000001"), record("AN-000002"), record("AN-000003")]


def responder(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST"
    assert request.content == b"null"
    assert request.headers["accept"] == "application/ld+json"
    assert request.headers["accept-crs"] == CRS_4326
    assert request.headers["api-version"] == API_VERSION

    skip = int(request.url.params["skip"])
    limit = int(request.url.params["limit"])
    members = RECORDS[skip : skip + limit]

    return httpx.Response(
        200,
        json={
            "@context": CONTEXT,
            "@type": "hydra:Collection",
            "totalItems": len(RECORDS),
            "view": {
                "first": "http://environment.data.gov.uk/water-quality/data/sampling-point",
            },
            "member": members,
        },
        headers={
            "content-type": "application/ld+json",
            "content-crs": CRS_4326,
            "api-version": API_VERSION,
            "x-total-items": str(len(RECORDS)),
            "x-page-skip": str(skip),
            "x-page-limit": str(limit),
        },
    )


def test_normalize_sampling_point() -> None:
    data = normalize([record("AN-011262")])

    assert data.counts == {
        "sampling_point_count": 1,
        "sampling_point_with_location_count": 1,
        "sampling_point_without_location_count": 0,
    }

    row = data.sampling_points[0]
    assert row["sampling_point_id"] == "AN-011262"
    assert row["longitude"] == -1.192
    assert row["latitude"] == 52.0473
    assert row["status"] == {"notation": "O", "pref_label": "OPEN"}


def test_missing_geometry_is_preserved() -> None:
    raw = record("AN-000001")
    raw["geometry"] = None
    data = normalize([raw])
    assert data.sampling_points[0]["latitude"] is None
    assert data.sampling_points[0]["longitude"] is None


@pytest.mark.parametrize(
    "value",
    [
        {"@type": "geo:Geometry", "asWKT": "LINESTRING(0 0, 1 1)"},
        {
            "@type": "geo:Geometry",
            "asWKT": "POINT(181 52) <http://www.opengis.net/def/crs/EPSG/0/4326>",
        },
        {
            "@type": "geo:Geometry",
            "asWKT": "POINT(1 91) <http://www.opengis.net/def/crs/EPSG/0/4326>",
        },
        {
            "@type": "geo:Geometry",
            "asWKT": "POINT(1 52) <http://www.opengis.net/def/crs/EPSG/0/27700>",
        },
        {"@type": "unexpected", "asWKT": "POINT(1 52)"},
    ],
)
def test_invalid_geometry_rejected(value: dict[str, Any]) -> None:
    with pytest.raises(WaterQualityError):
        point_geometry(value)


@pytest.mark.parametrize(
    "notation",
    [
        "AN-B BOOTH",
        "AN-CORBY  I",
        "MD-GWW20/01",
        "NW-GWW08/02",
    ],
)
def test_reviewed_publisher_notation_characters_are_preserved(notation: str) -> None:
    data = normalize([record(notation)])
    row = data.sampling_points[0]
    assert row["sampling_point_id"] == notation
    assert row["source_uri"].endswith(notation)


@pytest.mark.parametrize(
    "notation",
    [
        "AN-BAD?QUERY",
        "AN-BAD#FRAGMENT",
        "AN-BAD%2FENCODED",
        "AN-BAD\nCONTROL",
    ],
)
def test_unreviewed_notation_characters_are_rejected(notation: str) -> None:
    with pytest.raises(WaterQualityError, match="identity"):
        normalize([record(notation)])


def test_duplicate_and_inconsistent_identity_rejected() -> None:
    raw = record("AN-000001")

    with pytest.raises(WaterQualityError, match="Duplicate"):
        normalize([raw, raw])

    changed = record("AN-000001")
    changed["notation"] = "AN-OTHER"
    with pytest.raises(WaterQualityError, match="notation"):
        normalize([changed])


def test_unexpected_observation_relationship_rejected() -> None:
    raw = record("AN-000001")
    raw["hasObservations"] = "https://evil.invalid"
    with pytest.raises(WaterQualityError, match="observations"):
        normalize([raw])


@pytest.mark.parametrize(
    "url",
    [
        "http://environment.data.gov.uk/water-quality/data/sampling-point",
        "https://evil.invalid/water-quality/data/sampling-point",
        "https://environment.data.gov.uk.evil.invalid/water-quality/data/sampling-point",
        "https://user@environment.data.gov.uk/water-quality/data/sampling-point",
        "https://environment.data.gov.uk:8443/water-quality/data/sampling-point",
        "https://environment.data.gov.uk/water-quality/data/observation",
    ],
)
def test_disallowed_targets(url: str) -> None:
    with pytest.raises(WaterQualityError):
        check_url(url)


def test_request_url_is_fixed_and_bounded() -> None:
    url = request_url(0)
    check_url(url)
    parsed = httpx.URL(url)
    assert parsed.params["limit"] == "250"
    assert parsed.params["skip"] == "0"

    with pytest.raises(WaterQualityError):
        request_url(-1)
    with pytest.raises(WaterQualityError):
        request_url(100001)


def test_round_trip_evidence_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("watergeo.ingestion.water_quality_client.PAGE_LIMIT", 2)

    path = fetch_snapshot(tmp_path, transport=httpx.MockTransport(responder))
    manifest, data = read_snapshot(path)

    assert len(manifest["pages"]) == 2
    assert data.counts["sampling_point_count"] == 3
    assert data.sampling_points[0]["sampling_point_id"] == "AN-000001"

    second = fetch_snapshot(tmp_path, transport=httpx.MockTransport(responder))
    other_manifest, other_data = read_snapshot(second)

    assert other_manifest["content_sha256"] == manifest["content_sha256"]
    assert other_data.sha256 == data.sha256

    (path / "sampling-points-0.json").write_text("{}")
    with pytest.raises(WaterQualityError, match="hash"):
        read_snapshot(path)


def test_changed_total_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("watergeo.ingestion.water_quality_client.PAGE_LIMIT", 2)
    calls = 0

    def changing(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            members = RECORDS[:2]
            total = 3
        else:
            members = [RECORDS[2], record("AN-000004")]
            total = 4

        return httpx.Response(
            200,
            json={
                "@context": CONTEXT,
                "@type": "hydra:Collection",
                "totalItems": total,
                "view": {"first": "synthetic"},
                "member": members,
            },
            headers={
                "content-type": "application/ld+json",
                "content-crs": CRS_4326,
                "api-version": API_VERSION,
            },
        )

    with pytest.raises(WaterQualityError, match="total changed"):
        fetch_snapshot(tmp_path, transport=httpx.MockTransport(changing))


@pytest.mark.parametrize(
    "status,headers",
    [
        (302, {"location": "https://evil.invalid"}),
        (200, {"content-type": "text/html", "content-crs": CRS_4326, "api-version": "1"}),
        (
            200,
            {
                "content-type": "application/ld+json",
                "content-crs": "http://www.opengis.net/def/crs/EPSG/0/27700",
                "api-version": "1",
            },
        ),
    ],
)
def test_redirect_content_type_and_crs_rejected(
    tmp_path: Path,
    status: int,
    headers: dict[str, str],
) -> None:
    with pytest.raises(WaterQualityError):
        fetch_snapshot(
            tmp_path,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(status, headers=headers, content=b"{}")
            ),
        )


def test_json_duplicate_members_and_nonfinite_rejected() -> None:
    for body in [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]"]:
        with pytest.raises(WaterQualityError):
            decode(body)
