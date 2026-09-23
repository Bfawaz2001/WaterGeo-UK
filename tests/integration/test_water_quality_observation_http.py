"""Synthetic observation persistence, HTTP, correction and privilege contracts."""

import json
import subprocess
import sys
from datetime import date

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from test_water_quality_http import bundle as bundle
from test_water_quality_http import engines as engines
from test_water_quality_http import loaded as sampling_point_fixture

from watergeo.api.app import create_app
from watergeo.db.water_quality_observation_ingestion import load_observations
from watergeo.ingestion import water_quality_observation_client as source
from watergeo.ingestion.water_quality import CRS_4326, SAMPLING_POINT_ROOT, WaterQualityError
from watergeo.ingestion.water_quality_observations import (
    CODELIST_CONTEXT,
    OBSERVATION_CONTEXT,
    Scope,
)

SCOPE = Scope("MD-GWW20/01", "0085", date(2020, 1, 1), date(2020, 1, 31))
points = sampling_point_fixture


def evidence_at(root, *, corrected=False, empty=False, scope=SCOPE):
    determinand = {
        "@id": "_:determinand#0085",
        "notation": "0085",
        "prefLabel": "Synthetic BOD",
        "altLabel": "BOD",
    }
    unit = {
        "@id": "_:unit#205",
        "notation": "205",
        "prefLabel": "Milligram per litre",
        "altLabel": "mg/l",
    }
    point = SAMPLING_POINT_ROOT + scope.sampling_point_id
    records = (
        [
            {
                "@type": "sosa:Observation",
                "id": point + f"/sample/{n}/observation/0085",
                "hasSamplingPoint": {"id": point, "notation": scope.sampling_point_id},
                "hasSample": {
                    "@type": "sosa:Sample",
                    "id": point + f"/sample/{n}",
                    "sampleMaterialType": {"notation": "4AZZ", "prefLabel": "Synthetic material"},
                    "isResultOf": {
                        "@type": "sosa:Sampling",
                        "id": point + f"/sampling/{n}",
                        "samplingPurpose": {"notation": "CS", "prefLabel": "Synthetic purpose"},
                    },
                },
                "phenomenonTime": "2020-01-23T11:51:00",
                "observedProperty": determinand,
                "hasSimpleResult": "<0.9" if corrected else "<0.98",
                "hasUnit": "mg/l",
                "hasResult": {
                    "@type": "qudt:QuantityValue",
                    "numericValue": None,
                    "upperBound": 0.9 if corrected else 0.98,
                    "lowerBound": None,
                    "hasUnit": unit,
                },
            }
            for n in (1, 2)
        ]
        if not empty
        else []
    )

    def respond(request):
        if request.url.path.endswith("/data/observation"):
            rows, context = records, OBSERVATION_CONTEXT
        else:
            rows, context = (
                [determinand if request.url.path.endswith("/determinand") else unit],
                CODELIST_CONTEXT,
            )
        return httpx.Response(
            200,
            json={
                "@context": context,
                "@type": "hydra:Collection",
                "totalItems": len(rows),
                "member": rows,
                "view": None,
            },
            headers={
                "content-type": "application/ld+json",
                "api-version": "1",
                "content-crs": CRS_4326,
            },
        )

    return source.fetch_observations(scope, root, transport=httpx.MockTransport(respond))


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setattr(source.time, "sleep", lambda _: None)


@pytest.fixture
def evidence(tmp_path):
    return evidence_at(tmp_path)


@pytest.fixture
def loaded(engines, points, evidence):
    result = load_observations(engines[0], evidence)
    yield result
    # Only this fixture's point snapshot, including correction/empty retrievals.
    with engines[2].begin() as connection:
        for table in ("water_quality_observation", "water_quality_observation_unit"):
            connection.execute(
                text(
                    f"DELETE FROM watergeo.{table} WHERE retrieval_id IN "  # noqa: S608 -- fixed test table names
                    "(SELECT id FROM watergeo.water_quality_observation_retrieval "
                    "WHERE sampling_point_snapshot_id=:snapshot)"
                ),
                {"snapshot": points["snapshot_id"]},
            )
        connection.execute(
            text(
                "DELETE FROM watergeo.water_quality_observation_retrieval "
                "WHERE sampling_point_snapshot_id=:snapshot"
            ),
            {"snapshot": points["snapshot_id"]},
        )


def test_observation_retry_http_paging_and_correction(engines, loaded, evidence, tmp_path):
    assert load_observations(engines[0], evidence) == {**loaded, "status": "existing"}
    corrected = load_observations(engines[0], evidence_at(tmp_path, corrected=True))
    assert corrected["retrieval_id"] != loaded["retrieval_id"]
    with TestClient(create_app()) as client:
        url = "/v1/water-quality/observations/" + loaded["retrieval_id"]
        response = client.get(url, params={"limit": 1})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        data = response.json()
        assert data["record_count"] == 2 and data["sampling_point_id"] == SCOPE.sampling_point_id
        row = data["observations"][0]
        assert row["numeric_value"] is None and row["upper_bound"] == 0.98
        assert row["result_text"] == "<0.98" and row["time_zone_status"] == "unspecified_by_source"
        assert row["observed_at_text"] == "2020-01-23T11:51:00"
        assert row["publisher_sample"]["isResultOf"]["id"] == row["sampling_id"]
        assert data["determinand"]["notation"] == "0085" and data["units"][0]["notation"] == "205"
        second = client.get(url, params={"after_id": data["next_after_id"]}).json()
        assert len(second["observations"]) == 1 and second["next_after_id"] is None
        assert second["observations"][0]["observation_id"] != row["observation_id"]
        assert client.get(url + "?unexpected=1").status_code == 422
        assert client.get(url + "?limit=101").status_code == 422
        assert (
            client.get(
                "/v1/water-quality/observations/00000000-0000-0000-0000-000000000000"
            ).status_code
            == 404
        )
        correction = client.get(
            "/v1/water-quality/observations/" + corrected["retrieval_id"]
        ).json()
        assert correction["observations"][0]["upper_bound"] == 0.9


def test_empty_observation_retrieval(engines, loaded, tmp_path):
    result = load_observations(engines[0], evidence_at(tmp_path, empty=True))
    assert result["record_count"] == 0
    with TestClient(create_app()) as client:
        body = client.get("/v1/water-quality/observations/" + result["retrieval_id"]).json()
        assert body["observations"] == [] and body["units"] == [] and body["next_after_id"] is None


@pytest.mark.parametrize("corruption", ["value", "relationship", "unit", "determinand", "count"])
def test_observation_retry_detects_stored_corruption(engines, loaded, evidence, corruption):
    statements = {
        "value": (
            "UPDATE watergeo.water_quality_observation SET upper_bound=0.1 WHERE retrieval_id=:id"
        ),
        "relationship": (
            "UPDATE watergeo.water_quality_observation SET sample_id='corrupt' "
            "WHERE retrieval_id=:id"
        ),
        "unit": (
            "UPDATE watergeo.water_quality_observation_unit SET source_fields="
            "jsonb_set(source_fields,'{altLabel}', '\"corrupt\"') WHERE retrieval_id=:id"
        ),
        "determinand": (
            "UPDATE watergeo.water_quality_observation_retrieval SET determinand="
            "jsonb_set(determinand,'{prefLabel}', '\"corrupt\"') WHERE id=:id"
        ),
        "count": (
            "UPDATE watergeo.water_quality_observation_retrieval SET record_count=0 WHERE id=:id"
        ),
    }
    with engines[2].begin() as connection:
        connection.execute(text(statements[corruption]), {"id": loaded["retrieval_id"]})
    with pytest.raises(WaterQualityError, match="mismatch"):
        load_observations(engines[0], evidence)


def test_failed_observation_insert_rolls_back(engines, points, evidence):
    def fail(connection, cursor, statement, parameters, context, executemany):
        if "INSERT INTO watergeo.water_quality_observation\n" in statement:
            raise RuntimeError("synthetic insert failure")

    event.listen(engines[0], "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic"):
            load_observations(engines[0], evidence)
    finally:
        event.remove(engines[0], "before_cursor_execute", fail)
    with engines[1].connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM watergeo.water_quality_observation_retrieval "
                    "WHERE sampling_point_snapshot_id=:snapshot"
                ),
                {"snapshot": points["snapshot_id"]},
            ).scalar_one()
            == 0
        )


def test_observations_require_known_sampling_point(engines, tmp_path):
    scope = Scope("SYNTHETIC-UNKNOWN", "0085", SCOPE.date_from, SCOPE.date_to)
    with pytest.raises(WaterQualityError, match="unknown sampling point"):
        load_observations(engines[0], evidence_at(tmp_path, scope=scope))


def test_observation_cli_verified_retry(loaded, evidence):
    result = subprocess.run(  # noqa: S603 -- fixed CLI with synthetic evidence
        [
            sys.executable,
            "scripts/refresh_sources.py",
            "water-quality-observations",
            "--evidence-dir",
            str(evidence),
            "--timeout-seconds",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )  # noqa: S603
    assert result.returncode == 0, result.stdout
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert (
        next(e for e in events if e["event"] == "refresh_complete")["snapshot_id"]
        == loaded["retrieval_id"]
    )
    assert not result.stderr


def test_observation_roles_remain_least_privilege(engines):
    with engines[1].connect() as connection:
        for table in (
            "water_quality_observation_retrieval",
            "water_quality_observation_unit",
            "water_quality_observation",
        ):
            for role in ("watergeo_app", "watergeo_ingest"):
                for privilege in (
                    "SELECT",
                    "INSERT",
                    "UPDATE",
                    "DELETE",
                    "TRUNCATE",
                    "REFERENCES",
                    "TRIGGER",
                ):
                    actual = connection.execute(
                        text("SELECT has_table_privilege(:role,:table,:privilege)"),
                        {"role": role, "table": "watergeo." + table, "privilege": privilege},
                    ).scalar_one()
                    assert actual == (
                        privilege == "SELECT"
                        or (role == "watergeo_ingest" and privilege == "INSERT")
                    )
