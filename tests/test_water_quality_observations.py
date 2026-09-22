"""Synthetic bounded WQE observations, codelists, qualifiers and evidence failures."""

import copy
import json
from datetime import date

import httpx2 as httpx
import pytest

from watergeo.ingestion import water_quality_observation_client as client
from watergeo.ingestion.water_quality import (
    API_VERSION,
    CRS_4326,
    ROOT,
    SAMPLING_POINT_ROOT,
    WaterQualityError,
)
from watergeo.ingestion.water_quality_observations import (
    CODELIST_CONTEXT,
    OBSERVATION_CONTEXT,
    Scope,
    normalize,
)

SCOPE = Scope("MD-GWW20/01", "0085", date(2020, 1, 1), date(2020, 1, 31))
DETERMINAND = {
    "@id": "_:determinand#0085",
    "notation": "0085",
    "prefLabel": "Synthetic BOD",
    "altLabel": "BOD",
}
UNIT = {
    "@id": "_:unit#205",
    "notation": "205",
    "prefLabel": "Synthetic milligram per litre",
    "altLabel": "mg/l",
}


def record(sample="1", result="<0.98"):
    point = SAMPLING_POINT_ROOT + SCOPE.sampling_point_id
    return {
        "@type": "sosa:Observation",
        "id": point + f"/sample/{sample}/observation/0085",
        "hasSamplingPoint": {"id": point, "notation": SCOPE.sampling_point_id},
        "hasSample": {
            "id": point + f"/sample/{sample}",
            "@type": "sosa:Sample",
            "sampleMaterialType": {"notation": "4AZZ", "prefLabel": "Synthetic material"},
            "isResultOf": {
                "id": point + f"/sampling/{sample}",
                "@type": "sosa:Sampling",
                "samplingPurpose": {"notation": "CS", "prefLabel": "Synthetic purpose"},
            },
        },
        "phenomenonTime": "2020-01-23T11:51:00",
        "observedProperty": copy.deepcopy(DETERMINAND),
        "hasSimpleResult": result,
        "hasUnit": "mg/l",
        "hasResult": {
            "@type": "qudt:QuantityValue",
            "numericValue": None,
            "upperBound": 0.98,
            "lowerBound": None,
            "hasUnit": copy.deepcopy(UNIT),
        },
    }


def transport(records, *, status=200):
    def respond(request):
        assert request.url.host == "environment.data.gov.uk" and request.url.scheme == "https"
        assert request.headers["api-version"] == "1"
        path = request.url.path
        if path.endswith("/data/observation"):
            assert request.method == "POST" and request.content == b"null"
            assert request.url.params["pointNotation"] == SCOPE.sampling_point_id
            assert request.url.params["determinand"] == "0085"
            skip = int(request.url.params["skip"])
            rows = records[skip : skip + client.PAGE_LIMIT]
            total, context = len(records), OBSERVATION_CONTEXT
        else:
            assert request.method == "GET"
            rows = [DETERMINAND if path.endswith("/determinand") else UNIT]
            total, context = 1, CODELIST_CONTEXT
        return httpx.Response(
            status,
            json={
                "@context": context,
                "@type": "hydra:Collection",
                "member": rows,
                "totalItems": total,
                "view": {"next": "https://evil.invalid/"},
            },
            headers={
                "content-type": "application/ld+json",
                "api-version": API_VERSION,
                "content-crs": CRS_4326,
            },
        )

    return httpx.MockTransport(respond)


@pytest.fixture(autouse=True)
def no_source_sleep(monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _: None)


def test_roundtrip_preserves_scope_qualifier_units_and_relationships(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "PAGE_LIMIT", 1)
    directory = client.fetch_observations(
        SCOPE, tmp_path, transport=transport([record("1"), record("2")])
    )
    manifest, data = client.read_observations(directory)
    assert len(manifest["pages"]) == 4
    assert len(data.observations) == 2
    row = data.observations[0]
    assert row["result_text"] == "<0.98" and row["numeric_value"] is None
    assert row["upper_bound"] == 0.98
    assert row["observed_at_text"] == "2020-01-23T11:51:00"
    assert row["sample_id"].endswith("/sample/1")
    assert row["sampling_id"].endswith("/sampling/1")
    assert data.units == [UNIT] and data.determinand == DETERMINAND
    assert data.sha256 == manifest["normalized_sha256"]
    assert row["sampling_point_id"] == "MD-GWW20/01"


def test_empty_scoped_history_is_valid(tmp_path):
    directory = client.fetch_observations(SCOPE, tmp_path, transport=transport([]))
    _, data = client.read_observations(directory)
    assert data.observations == [] and data.units == []


@pytest.mark.parametrize(
    "start,end", [(date(2020, 1, 1), date(2020, 2, 2)), (date(2020, 2, 1), date(2020, 1, 1))]
)
def test_bounded_date_scope(start, end):
    with pytest.raises(WaterQualityError):
        Scope("point", "0085", start, end)


@pytest.mark.parametrize(
    "point,determinand", [("point?x=1", "0085"), ("point", "0085,0076"), ("point\n", "0085")]
)
def test_scope_cannot_expand_query(point, determinand):
    with pytest.raises(WaterQualityError):
        Scope(point, determinand, date(2020, 1, 1), date(2020, 1, 1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("phenomenonTime", "2020-01-23T11:51:00Z"),
        ("phenomenonTime", "2020-02-01T00:00:00"),
        ("id", ROOT + "/wrong"),
        ("hasSamplingPoint", {"id": "wrong"}),
        ("hasSample", None),
        ("observedProperty", {"notation": "0076"}),
        ("hasSimpleResult", "0.98"),
        ("hasUnit", "ppm"),
    ],
)
def test_rejects_unreviewed_or_inconsistent_observation(field, value):
    raw = record()
    raw[field] = value
    with pytest.raises(WaterQualityError):
        normalize(SCOPE, [raw], DETERMINAND, [UNIT])


@pytest.mark.parametrize("value", [True, "0.98", float("nan"), float("inf")])
def test_invalid_quantities(value):
    raw = record()
    raw["hasResult"]["upperBound"] = value
    with pytest.raises((WaterQualityError, ValueError)):
        normalize(SCOPE, [raw], DETERMINAND, [UNIT])


@pytest.mark.parametrize("kind", ["numericValue", "lowerBound", "missing"])
def test_measurement_lower_bound_and_missing_are_distinct(kind):
    raw = record()
    raw["hasResult"]["upperBound"] = None
    if kind == "missing":
        raw["hasSimpleResult"] = None
    else:
        raw["hasResult"][kind] = 1.5
        raw["hasSimpleResult"] = ">1.5" if kind == "lowerBound" else "1.5"
    row = normalize(SCOPE, [raw], DETERMINAND, [UNIT]).observations[0]
    assert row["numeric_value"] == (1.5 if kind == "numericValue" else None)
    assert row["lower_bound"] == (1.5 if kind == "lowerBound" else None)


@pytest.mark.parametrize("status", [301, 302, 403, 500])
def test_bad_status_does_not_publish_manifest(tmp_path, status):
    with pytest.raises(WaterQualityError):
        client.fetch_observations(SCOPE, tmp_path, transport=transport([record()], status=status))
    assert not list(tmp_path.glob("*/manifest.json"))


@pytest.mark.parametrize("change", ["body", "path", "partial", "scope", "hash"])
def test_evidence_integrity(tmp_path, change):
    directory = client.fetch_observations(SCOPE, tmp_path, transport=transport([record()]))
    manifest = json.loads((directory / "manifest.json").read_text())
    if change == "body":
        (directory / "response-000.json").write_text("{}")
    elif change == "path":
        manifest["pages"][0]["file"] = "../outside"
    elif change == "partial":
        manifest["pages"].pop()
    elif change == "scope":
        manifest["scope"]["determinand"] = "0076"
    else:
        manifest["normalized_sha256"] = "0" * 64
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(WaterQualityError):
        client.read_observations(directory)


def test_duplicate_observations_never_publish(tmp_path):
    with pytest.raises(WaterQualityError, match="repeated"):
        client.fetch_observations(SCOPE, tmp_path, transport=transport([record(), record()]))
    assert not list(tmp_path.glob("*/manifest.json"))


@pytest.mark.parametrize("change", ["headers", "truncated", "total", "budget"])
def test_response_contract_and_budget_fail_closed(tmp_path, monkeypatch, change):
    delegate = transport([record()])

    def respond(request):
        response = delegate.handle_request(request)
        if change == "headers":
            response.headers["api-version"] = "2"
            return response
        body = json.loads(response.content)
        if request.url.path.endswith("/data/observation"):
            if change == "truncated":
                body["member"] = []
            elif change == "total":
                body["totalItems"] = 5001
        return httpx.Response(200, json=body, headers=response.headers)

    if change == "budget":
        monkeypatch.setattr(client, "MAX_BYTES", 10)
    with pytest.raises(WaterQualityError):
        client.fetch_observations(SCOPE, tmp_path, transport=httpx.MockTransport(respond))
    assert not list(tmp_path.glob("*/manifest.json"))


def test_end_date_is_exclusive_and_zero_length_window_rejected():
    raw = record()
    raw["phenomenonTime"] = "2020-01-31T00:00:00"
    with pytest.raises(WaterQualityError, match="outside"):
        normalize(SCOPE, [raw], DETERMINAND, [UNIT])
    with pytest.raises(WaterQualityError, match="1–31"):
        Scope(SCOPE.sampling_point_id, "0085", date(2020, 1, 1), date(2020, 1, 1))


def test_page_budget_never_accepts_partial_result(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "MAX_PAGES", 1)
    monkeypatch.setattr(client, "PAGE_LIMIT", 1)
    with pytest.raises(WaterQualityError, match="page budget"):
        client.fetch_observations(SCOPE, tmp_path, transport=transport([record("1"), record("2")]))
    assert not list(tmp_path.glob("*/manifest.json"))
