"""Verify a local WaterGeo demo without contacting upstream publishers."""

import argparse
import sys
from collections.abc import Sequence
from typing import Any

import httpx2 as httpx

from watergeo.deployment_smoke import SmokeFailure, _json_response

SOURCE_PATHS = {
    "ofwat": "v1/water-supply/areas?limit=1",
    "hydrology": "v1/hydrology/stations?limit=1",
    "catchments": "v1/catchments/water-bodies?limit=1",
    "water-quality": "v1/water-quality/sampling-points?limit=1",
    "stream-reservoir-levels": "v1/severn-trent/reservoir-levels/reservoirs?limit=1",
    "thames-discharge-status": "v1/thames-water/discharge-status/sites?limit=1",
}


def _result(label: str, state: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"{state:<10} {label}{suffix}")


def run_demo_smoke(
    base_url: str,
    *,
    complete: bool,
    explorer: bool,
    transport: httpx.BaseTransport | None = None,
) -> bool:
    failed = False
    with httpx.Client(
        base_url=base_url.rstrip("/") + "/",
        timeout=httpx.Timeout(10),
        transport=transport,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        for label, path, contract in (
            ("Health", "health", {"status": "ok"}),
            ("Readiness", "ready", {"status": "ready"}),
        ):
            try:
                body = _json_response(client, path, 200)
                if body != contract:
                    raise SmokeFailure("unexpected response contract")
                _result(label, "PASS")
            except SmokeFailure as error:
                _result(label, "FAIL", str(error))
                failed = True

        statuses: dict[str, Any] = {}
        try:
            body = _json_response(client, "v1/sources/status", 200)
            statuses = {item["source"]: item for item in body.get("sources", [])}
            _result("Source status", "PASS")
        except (SmokeFailure, KeyError, TypeError) as error:
            _result("Source status", "FAIL", str(error))
            failed = True

        try:
            _json_response(client, "v1/search?q=river&limit=1", 200)
            _result("Unified search", "PASS")
        except SmokeFailure as error:
            _result("Unified search", "FAIL", str(error))
            failed = True

        for source, path in SOURCE_PATHS.items():
            status = statuses.get(source, {})
            if status.get("availability") != "available":
                state = "NOT LOADED" if complete else "SKIP"
                detail = "required by --complete" if complete else "optional source"
                _result(source, state, detail)
                failed = failed or complete
                continue
            try:
                _json_response(client, path, 200)
                _result(source, "PASS")
            except SmokeFailure as error:
                _result(source, "FAIL", str(error))
                failed = True

        if explorer:
            try:
                response = client.get("")
                media = response.headers.get("content-type", "").split(";", 1)[0]
                if (
                    response.status_code != 200
                    or media != "text/html"
                    or b"<html" not in response.content.lower()
                ):
                    raise SmokeFailure("explorer HTML was not served")
                _result("Explorer", "PASS")
            except (httpx.TransportError, SmokeFailure) as error:
                _result("Explorer", "FAIL", str(error))
                failed = True
    return not failed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--complete", action="store_true", help="require every demo source")
    parser.add_argument("--explorer", action="store_true", help="require explorer HTML at /")
    args = parser.parse_args(argv)
    try:
        url = httpx.URL(args.base_url)
        if url.scheme not in {"http", "https"} or not url.host or url.userinfo:
            raise ValueError
    except (TypeError, ValueError):
        print("FAIL       invalid base URL", file=sys.stderr)
        return 2
    return 0 if run_demo_smoke(str(url), complete=args.complete, explorer=args.explorer) else 1


if __name__ == "__main__":
    raise SystemExit(main())
