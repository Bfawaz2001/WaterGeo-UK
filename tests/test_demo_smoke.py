import httpx2 as httpx

from watergeo.operations.demo_smoke import SOURCE_PATHS, run_demo_smoke


def responder(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/":
        return httpx.Response(
            200,
            text="<!doctype html><html></html>",
            headers={"content-type": "text/html"},
        )
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/ready":
        return httpx.Response(200, json={"status": "ready"})
    if request.url.path == "/v1/sources/status":
        return httpx.Response(
            200,
            json={
                "sources": [
                    {"source": source, "availability": "available"} for source in SOURCE_PATHS
                ]
            },
        )
    return httpx.Response(200, json={"items": []})


def test_complete_demo_smoke_checks_all_sources_search_and_explorer(capsys) -> None:
    assert run_demo_smoke(
        "http://demo.test",
        complete=True,
        explorer=True,
        transport=httpx.MockTransport(responder),
    )
    output = capsys.readouterr().out
    assert "PASS       Unified search" in output
    assert "PASS       ofwat" in output
    assert "PASS       Explorer" in output


def test_complete_demo_smoke_fails_when_source_not_loaded(capsys) -> None:
    def incomplete(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/sources/status":
            return httpx.Response(200, json={"sources": []})
        return responder(request)

    assert not run_demo_smoke(
        "http://demo.test",
        complete=True,
        explorer=False,
        transport=httpx.MockTransport(incomplete),
    )
    assert "NOT LOADED" in capsys.readouterr().out
