import json

import httpx2 as httpx
import pytest

import watergeo.deployment_smoke as deployment_smoke
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


def test_smoke_rejects_http_by_default():
    with pytest.raises(SmokeFailure, match="HTTPS is required"):
        run_smoke_checks("http://127.0.0.1:8000", transport=httpx.MockTransport(response_for))


def test_smoke_allows_http_only_with_explicit_local_opt_in():
    checks = run_smoke_checks(
        "http://127.0.0.1:8000",
        allow_http=True,
        transport=httpx.MockTransport(response_for),
    )
    assert checks == ["health", "readiness", "openapi", "invalid_request"]


def test_smoke_cli_forwards_explicit_http_opt_in(monkeypatch, capsys):
    received = {}

    def run(base_url, *, data_path=None, allow_http=False):
        received.update(base_url=base_url, data_path=data_path, allow_http=allow_http)
        return ["health"]

    monkeypatch.setattr(deployment_smoke, "run_smoke_checks", run)
    assert deployment_smoke.main(["http://127.0.0.1:8000", "--allow-http"]) == 0
    assert received == {
        "base_url": "http://127.0.0.1:8000",
        "data_path": None,
        "allow_http": True,
    }
    assert '"status":"ok"' in capsys.readouterr().out


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
