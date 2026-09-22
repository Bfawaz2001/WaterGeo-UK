"""Synthetic sampling-point HTTP/refresh coverage, rerunnable with existing real data."""

from urllib.parse import quote

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from test_hydrology_http import engines as engines

from watergeo.api.app import create_app
from watergeo.db.water_quality_ingestion import load_snapshot
from watergeo.ingestion.water_quality import API_VERSION, CONTEXT, CRS_4326, SAMPLING_POINT_ROOT
from watergeo.ingestion.water_quality_client import fetch_snapshot
from watergeo.operations.refresh import RefreshRequest, refresh

IDS = ["AN-B BOOTH", "AN-CORBY  I", "MD-GWW20/01", "NW-GWW08/02"]


@pytest.fixture
def bundle(tmp_path):
    records = [
        {
            "id": SAMPLING_POINT_ROOT + identity,
            "notation": identity,
            "altLabel": "Synthetic point",
            "prefLabel": "Synthetic preferred label",
            "geometry": {"@type": "geo:Geometry", "asWKT": f"POINT(-1 52) <{CRS_4326}>"},
            "region": {"notation": "AN", "prefLabel": "Source region"},
        }
        for identity in IDS
    ]

    def respond(request):
        return httpx.Response(
            200,
            json={
                "@context": CONTEXT,
                "@type": "hydra:Collection",
                "totalItems": len(records),
                "view": {},
                "member": records,
            },
            headers={
                "content-type": "application/ld+json",
                "content-crs": CRS_4326,
                "api-version": API_VERSION,
            },
        )

    return fetch_snapshot(tmp_path, transport=httpx.MockTransport(respond))


@pytest.fixture
def loaded(engines, bundle):
    result = load_snapshot(engines[0], bundle)
    yield result
    with engines[2].begin() as connection:
        connection.execute(
            text("DELETE FROM watergeo.water_quality_sampling_point WHERE snapshot_id=:id"),
            {"id": result["snapshot_id"]},
        )
        connection.execute(
            text("DELETE FROM watergeo.water_quality_snapshot WHERE id=:id"),
            {"id": result["snapshot_id"]},
        )


def test_sampling_points_pagination_identity_and_provenance(loaded):
    with TestClient(create_app()) as client:
        prefix = "/v1/water-quality"
        params = {"snapshot_id": loaded["snapshot_id"]}
        dataset = client.get(prefix + "/dataset", params=params)
        assert dataset.status_code == 200
        assert dataset.json()["sampling_point_count"] == 4
        assert dataset.json()["licence"] == "Open Government Licence v3"
        assert dataset.headers["cache-control"] == "no-store"
        first = client.get(prefix + "/sampling-points", params={**params, "limit": 2}).json()
        assert [r["sampling_point_id"] for r in first["items"]] == IDS[:2]
        assert "source_fields" not in first["items"][0]
        second = client.get(
            prefix + "/sampling-points", params={**params, "after_id": first["next_after_id"]}
        ).json()
        assert [r["sampling_point_id"] for r in second["items"]] == IDS[2:]
        for identity in IDS:
            detail = client.get(
                prefix + "/sampling-points/" + quote(identity, safe=""), params=params
            )
            assert detail.status_code == 200
            assert detail.json()["sampling_point_id"] == identity
            assert detail.json()["publisher_metadata"]["region"]["notation"] == "AN"
        assert client.get(prefix + "/sampling-points/missing", params=params).status_code == 404
        assert client.get(prefix + "/dataset?extra=1").status_code == 422
        assert client.get(prefix + "/sampling-points?limit=101").status_code == 422


def test_near_ordering_snapshot_pinning_and_unlocated_semantics(engines, loaded):
    params = {"snapshot_id": loaded["snapshot_id"], "lon": -1, "lat": 52, "radius_m": 1}
    with TestClient(create_app()) as client:
        result = client.get("/v1/water-quality/sampling-points/near", params=params)
        assert result.status_code == 200
        assert [r["sampling_point_id"] for r in result.json()["items"]] == IDS
        assert all(r["distance_m"] == 0 for r in result.json()["items"])
        assert result.json()["spatial_exclusion_note"]
        # Change only synthetic fixture content to exercise missing location responses.
        with engines[2].begin() as connection:
            connection.execute(
                text("""UPDATE watergeo.water_quality_sampling_point
                SET geom=NULL, latitude=NULL, longitude=NULL
                WHERE snapshot_id=:id AND sampling_point_id=:point"""),
                {"id": loaded["snapshot_id"], "point": IDS[0]},
            )
        near = client.get("/v1/water-quality/sampling-points/near", params=params).json()
        assert [r["sampling_point_id"] for r in near["items"]] == IDS[1:]
        detail = client.get(
            "/v1/water-quality/sampling-points/" + quote(IDS[0]),
            params={"snapshot_id": loaded["snapshot_id"]},
        ).json()
        assert detail["location_status"] == "unavailable" and detail["geometry"] is None


def test_water_quality_refresh_retry_and_status(engines, bundle, loaded):
    result = refresh(engines[0], RefreshRequest("water-quality", bundle), "synthetic-run")
    assert result == {"status": "existing", "snapshot_id": loaded["snapshot_id"]}
    with TestClient(create_app()) as client:
        status = client.get("/v1/sources/status")
        assert status.status_code == 200
        item = next(row for row in status.json()["sources"] if row["source"] == "water-quality")
        assert item["snapshot_id"] == loaded["snapshot_id"]
        assert item["retrieval_freshness"] == "unknown"
        assert item["observation_freshness"] == "not_applicable"
