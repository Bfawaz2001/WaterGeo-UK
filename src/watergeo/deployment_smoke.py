"""Bounded checks for a deployed WaterGeo HTTP API."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

import httpx2 as httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REQUIRED_OPENAPI_PATHS = {"/health", "/ready", "/v1/sources/status"}
SENSITIVE_ERROR_MARKERS = (
    "postgresql://",
    "traceback",
    "psycopg",
    "sqlalchemy",
    "watergeo_app",
    "password=",
)


class SmokeFailure(RuntimeError):
    """A deployment does not satisfy the public HTTP contract."""


def _json_response(client: httpx.Client, path: str, expected_status: int) -> Any:
    display_path = "/" + path.lstrip("/")
    try:
        with client.stream("GET", path) as response:
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SmokeFailure(
                        f"{display_path} response exceeded {MAX_RESPONSE_BYTES} bytes"
                    )
    except httpx.TransportError as error:
        raise SmokeFailure(f"{display_path} could not be reached") from error
    if response.status_code != expected_status:
        raise SmokeFailure(
            f"{display_path} returned HTTP {response.status_code}, expected {expected_status}"
        )
    media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if media_type not in {"application/json", "application/geo+json"}:
        raise SmokeFailure(f"{display_path} returned an unexpected content type")
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SmokeFailure(f"{display_path} did not return valid JSON") from error


def run_smoke_checks(
    base_url: str,
    *,
    data_path: str | None = None,
    allow_http: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> list[str]:
    """Run platform-independent deployment checks and return their names."""
    try:
        url = httpx.URL(base_url)
    except (TypeError, ValueError) as error:
        raise SmokeFailure("base URL is invalid") from error
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or url.query
        or url.fragment
    ):
        raise SmokeFailure("base URL must be HTTP(S) without credentials, query, or fragment")
    if url.scheme == "http" and not allow_http:
        raise SmokeFailure("HTTPS is required unless local HTTP is explicitly allowed")
    if data_path is not None and (not data_path.startswith("/v1/") or "//" in data_path):
        raise SmokeFailure("data path must be an absolute /v1/ path")

    normalized = str(url.copy_with(path=url.path.rstrip("/") + "/"))
    completed: list[str] = []
    with httpx.Client(
        base_url=normalized,
        timeout=httpx.Timeout(10.0),
        transport=transport,
        trust_env=False,
        follow_redirects=False,
        headers={"Accept": "application/json, application/geo+json"},
    ) as client:
        if _json_response(client, "health", 200) != {"status": "ok"}:
            raise SmokeFailure("/health returned an unexpected contract")
        completed.append("health")
        if _json_response(client, "ready", 200) != {"status": "ready"}:
            raise SmokeFailure("/ready returned an unexpected contract")
        completed.append("readiness")
        document = _json_response(client, "openapi.json", 200)
        paths = document.get("paths") if isinstance(document, dict) else None
        if not isinstance(paths, dict) or not REQUIRED_OPENAPI_PATHS.issubset(paths):
            raise SmokeFailure("/openapi.json is missing required WaterGeo paths")
        completed.append("openapi")
        if data_path is not None:
            _json_response(client, data_path.lstrip("/"), 200)
            completed.append("representative_data")
        invalid = _json_response(client, "v1/water-supply/areas?limit=0", 422)
        serialized = json.dumps(invalid, sort_keys=True).lower()
        if any(marker in serialized for marker in SENSITIVE_ERROR_MARKERS):
            raise SmokeFailure("invalid request response exposed implementation details")
        completed.append("invalid_request")
    return completed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a deployed WaterGeo API")
    parser.add_argument(
        "base_url", help="Explicit HTTPS deployment base URL (HTTP requires --allow-http)"
    )
    parser.add_argument(
        "--data-path",
        help="Representative /v1/ endpoint expected to return 200 after data bootstrap",
    )
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="allow insecure HTTP for local testing only; never use for public go-live validation",
    )
    arguments = parser.parse_args(argv)
    try:
        checks = run_smoke_checks(
            arguments.base_url,
            data_path=arguments.data_path,
            allow_http=arguments.allow_http,
        )
    except SmokeFailure as error:
        print(f"deployment smoke check failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", "checks": checks}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
