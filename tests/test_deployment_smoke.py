import json

import httpx2 as httpx
import pytest

from watergeo.deployment_smoke import SmokeFailure, run_smoke_checks


def response_for(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/ready":
        return httpx.Response(200, json={"status": "ready"})
    if request.url.path == "/openapi.json":
        return httpx.Response(
            200,
            json={"paths": {"/health": {}, "/ready": {}, "/v1/sources/status": {}}},
        )
    if request.url.path == "/v1/sources/status":
        return httpx.Response(200, json={"sources": []})
    assert request.url.params["limit"] == "0"
    return httpx.Response(422, json={"detail": "Input should be greater than or equal to 1"})


def test_smoke_checks_operational_openapi_data_and_invalid_request():
    checks = run_smoke_checks(
        "https://api.example.test",
        data_path="/v1/sources/status",
        transport=httpx.MockTransport(response_for),
    )
    assert checks == [
        "health",
        "readiness",
        "openapi",
        "representative_data",
        "invalid_request",
    ]


@pytest.mark.parametrize(
    "url",
    ["api.example.test", "ftp://api.example.test", "https://user:secret@api.example.test"],
)
def test_smoke_rejects_unsafe_base_urls(url: str):
    with pytest.raises(SmokeFailure, match="base URL"):
        run_smoke_checks(url, transport=httpx.MockTransport(response_for))


def test_smoke_fails_closed_when_readiness_fails():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ready":
            return httpx.Response(503, json={"status": "not_ready"})
        return response_for(request)

    with pytest.raises(SmokeFailure, match="/ready returned HTTP 503"):
        run_smoke_checks("https://api.example.test", transport=httpx.MockTransport(responder))


def test_smoke_rejects_error_detail_leakage():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/water-supply/areas":
            return httpx.Response(422, json={"detail": "psycopg connection failed"})
        return response_for(request)

    with pytest.raises(SmokeFailure, match="exposed implementation details"):
        run_smoke_checks("https://api.example.test", transport=httpx.MockTransport(responder))


def test_smoke_bounds_every_response():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(
                200,
                content=json.dumps({"status": "ok", "padding": "x" * (2 * 1024 * 1024)}),
                headers={"content-type": "application/json"},
            )
        return response_for(request)

    with pytest.raises(SmokeFailure, match="response exceeded"):
        run_smoke_checks("https://api.example.test", transport=httpx.MockTransport(responder))
