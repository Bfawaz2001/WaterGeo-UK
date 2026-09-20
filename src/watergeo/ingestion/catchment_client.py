"""Bounded Environment Agency Catchment Data Explorer Cycle 3 retrieval."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.catchments import (
    MAX_MANAGEMENT_CATCHMENTS,
    MAX_OPERATIONAL_CATCHMENTS,
    MAX_RIVER_BASIN_DISTRICTS,
    PLAN_VERSION,
    ROOT,
    VERSION,
    CatchmentError,
    NormalizedCatchments,
    digest,
    encoded,
    entity_url,
    hierarchy_links,
    normalize,
    parse_entity_page,
    parse_rbd_geojson,
    rbd_geojson_url,
)

CATCHMENT_ROOT = Path("data/raw/environment-agency/catchments")

MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAX_REQUESTS = 1000

MAX_HTML_BYTES = 32 * 1024 * 1024
MAX_GEOJSON_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_RESPONSE_SECONDS = 180.0
MAX_MANIFEST_BYTES = 8 * 1024 * 1024

HEADERS = ("date", "etag", "last-modified", "content-type")

HTML_CONTENT_TYPE = "text/html"
GEOJSON_CONTENT_TYPES = {
    "application/vnd.geo+json",
    "application/geo+json",
}

RETRYABLE_STATUSES = {403, 429, 500, 502, 503, 504}


class RequestPacer:
    """Ensure source requests begin no faster than the configured interval."""

    def __init__(
        self,
        interval: float = MIN_REQUEST_INTERVAL_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(interval, (int, float)) or interval < 0:
            raise CatchmentError("Invalid catchment request interval")

        self._interval = float(interval)
        self._clock = clock
        self._sleeper = sleeper
        self._last_started: float | None = None

    def wait(self) -> None:
        now = self._clock()

        if self._last_started is not None:
            remaining = self._interval - (now - self._last_started)
            if remaining > 0:
                self._sleeper(remaining)
                now = self._clock()

        self._last_started = now


def root_url() -> str:
    return f"{ROOT}/v/{PLAN_VERSION}"


def _source_url(url: str) -> httpx.URL:
    parsed = httpx.URL(url)

    if (
        parsed.scheme != "https"
        or parsed.host != "environment.data.gov.uk"
        or parsed.port not in (None, 443)
        or parsed.userinfo
        or parsed.fragment
        or parsed.query
        or not parsed.path.startswith(f"/catchment-planning/v/{PLAN_VERSION}")
    ):
        raise CatchmentError("Disallowed Catchment Data Explorer request target")

    allowed_root = f"/catchment-planning/v/{PLAN_VERSION}"

    if parsed.path == allowed_root:
        return parsed

    parts = parsed.path[len(allowed_root) :].strip("/").split("/")

    if len(parts) != 2:
        raise CatchmentError("Disallowed Catchment Data Explorer request path")

    kind, entity = parts

    if kind == "RiverBasinDistrict" and entity.endswith(".geojson"):
        entity_id = entity[: -len(".geojson")]
        if str(parsed) != rbd_geojson_url(entity_id):
            raise CatchmentError("Unexpected River Basin District GeoJSON URL")
        return parsed

    expected = entity_url(kind, entity)

    if str(parsed) != expected:
        raise CatchmentError("Unexpected Catchment Data Explorer entity URL")

    return parsed


def _content_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";")[0].strip().lower()


def _request(
    client: httpx.Client,
    url: str,
    *,
    expected: str,
    pacer: RequestPacer,
) -> tuple[bytes, dict[str, str]]:
    _source_url(url)

    if expected not in {"html", "geojson"}:
        raise CatchmentError("Unsupported Catchment Data Explorer response type")

    byte_limit = MAX_HTML_BYTES if expected == "html" else MAX_GEOJSON_BYTES

    for attempt in range(3):
        pacer.wait()

        try:
            with client.stream("GET", url, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise CatchmentError("Unexpected catchment source redirect")

                if response.status_code in RETRYABLE_STATUSES:
                    if attempt == 2:
                        raise CatchmentError("Catchment source temporarily unavailable")
                    continue

                if response.status_code != 200:
                    raise CatchmentError("Unexpected catchment source HTTP status")

                content_type = _content_type(response.headers)

                if expected == "html":
                    if content_type != HTML_CONTENT_TYPE:
                        raise CatchmentError("Unsupported catchment HTML content type")
                elif content_type not in GEOJSON_CONTENT_TYPES:
                    raise CatchmentError("Unsupported catchment GeoJSON content type")

                body = bytearray()
                started = time.monotonic()

                for chunk in response.iter_bytes(chunk_size=65536):
                    body.extend(chunk)

                    if len(body) > byte_limit or time.monotonic() - started > MAX_RESPONSE_SECONDS:
                        raise CatchmentError("Catchment source response budget exceeded")

                return bytes(body), {
                    key: response.headers[key] for key in HEADERS if key in response.headers
                }

        except httpx.TransportError:
            if attempt == 2:
                raise CatchmentError(
                    "Catchment source transport failed after bounded retries"
                ) from None

    raise CatchmentError("Catchment source retrieval failed")


def _safe_path(directory: Path, relative: str) -> Path:
    if relative.startswith("/") or ".." in Path(relative).parts:
        raise CatchmentError("Invalid catchment evidence path")

    path = directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_response(
    directory: Path,
    *,
    relative: str,
    body: bytes,
) -> None:
    path = _safe_path(directory, relative)

    if path.exists():
        raise CatchmentError("Duplicate catchment evidence file")

    path.write_bytes(body)


def _entry(
    *,
    kind: str,
    entity_id: str | None,
    relative: str,
    request_url: str,
    request_started: datetime,
    request_completed: datetime,
    headers: dict[str, str],
    body: bytes,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "entity_id": entity_id,
        "file": relative,
        "request_url": request_url,
        "request_started_at": request_started.isoformat(),
        "request_completed_at": request_completed.isoformat(),
        "headers": headers,
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }


def content_hash(entries: list[dict[str, Any]]) -> str:
    return digest(
        [
            {
                "kind": entry["kind"],
                "entity_id": entry["entity_id"],
                "request_url": entry["request_url"],
                "sha256": entry["sha256"],
            }
            for entry in entries
        ]
    )


def _request_and_record(
    *,
    client: httpx.Client,
    pacer: RequestPacer,
    directory: Path,
    entries: list[dict[str, Any]],
    kind: str,
    entity_id: str | None,
    relative: str,
    url: str,
    expected: str,
    total_bytes: int,
) -> tuple[bytes, int]:
    if len(entries) >= MAX_REQUESTS:
        raise CatchmentError("Catchment request budget exceeded")

    request_started = datetime.now(UTC)
    body, headers = _request(
        client,
        url,
        expected=expected,
        pacer=pacer,
    )
    request_completed = datetime.now(UTC)

    total_bytes += len(body)

    if total_bytes > MAX_TOTAL_BYTES:
        raise CatchmentError("Catchment retrieval size budget exceeded")

    _write_response(
        directory,
        relative=relative,
        body=body,
    )

    entries.append(
        _entry(
            kind=kind,
            entity_id=entity_id,
            relative=relative,
            request_url=url,
            request_started=request_started,
            request_completed=request_completed,
            headers=headers,
            body=body,
        )
    )

    return body, total_bytes


def fetch_snapshot(
    root: Path = CATCHMENT_ROOT,
    *,
    transport: httpx.BaseTransport | None = None,
    request_interval: float = MIN_REQUEST_INTERVAL_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)

    retrieval_started = datetime.now(UTC)
    entries: list[dict[str, Any]] = []
    total_bytes = 0

    pacer = RequestPacer(
        request_interval,
        clock=clock,
        sleeper=sleeper,
    )

    root_html: bytes
    rbd_html: dict[str, bytes] = {}
    management_html: dict[str, bytes] = {}
    operational_html: dict[str, bytes] = {}
    rbd_geojson: dict[str, bytes] = {}

    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(60, connect=10),
        trust_env=False,
        headers={
            "User-Agent": "WaterGeo-UK/0.1 (public source ingestion)",
        },
    ) as client:
        root_html, total_bytes = _request_and_record(
            client=client,
            pacer=pacer,
            directory=directory,
            entries=entries,
            kind="root",
            entity_id=None,
            relative="root.html",
            url=root_url(),
            expected="html",
            total_bytes=total_bytes,
        )

        root_links = hierarchy_links(root_html, root_url())
        rbd_ids = root_links["RiverBasinDistrict"]

        if not rbd_ids or len(rbd_ids) > MAX_RIVER_BASIN_DISTRICTS:
            raise CatchmentError("Invalid River Basin District root inventory")

        management_parents: dict[str, str] = {}

        for rbd_id in rbd_ids:
            url = entity_url("RiverBasinDistrict", rbd_id)

            body, total_bytes = _request_and_record(
                client=client,
                pacer=pacer,
                directory=directory,
                entries=entries,
                kind="river_basin_district",
                entity_id=rbd_id,
                relative=f"rbd/{rbd_id}.html",
                url=url,
                expected="html",
                total_bytes=total_bytes,
            )

            rbd_html[rbd_id] = body

            page = parse_entity_page(
                body,
                kind="RiverBasinDistrict",
                entity_id=rbd_id,
            )

            children = page.links["ManagementCatchment"]

            if not children:
                raise CatchmentError("River Basin District has no Management Catchments")

            for management_id in children:
                if management_id in management_parents:
                    raise CatchmentError(
                        "Management Catchment has multiple River Basin District parents"
                    )
                management_parents[management_id] = rbd_id

        if not management_parents or len(management_parents) > MAX_MANAGEMENT_CATCHMENTS:
            raise CatchmentError("Invalid Management Catchment inventory")

        operational_parents: dict[str, tuple[str, str]] = {}

        for management_id in sorted(management_parents):
            url = entity_url("ManagementCatchment", management_id)

            body, total_bytes = _request_and_record(
                client=client,
                pacer=pacer,
                directory=directory,
                entries=entries,
                kind="management_catchment",
                entity_id=management_id,
                relative=f"management/{management_id}.html",
                url=url,
                expected="html",
                total_bytes=total_bytes,
            )

            management_html[management_id] = body

            page = parse_entity_page(
                body,
                kind="ManagementCatchment",
                entity_id=management_id,
            )

            expected_rbd = management_parents[management_id]

            if page.links["RiverBasinDistrict"] != (expected_rbd,):
                raise CatchmentError("Management Catchment parent relationship mismatch")

            children = page.links["OperationalCatchment"]

            if not children:
                raise CatchmentError("Management Catchment has no Operational Catchments")

            for operational_id in children:
                if operational_id in operational_parents:
                    raise CatchmentError(
                        "Operational Catchment has multiple Management Catchment parents"
                    )

                operational_parents[operational_id] = (
                    management_id,
                    expected_rbd,
                )

        if not operational_parents or len(operational_parents) > MAX_OPERATIONAL_CATCHMENTS:
            raise CatchmentError("Invalid Operational Catchment inventory")

        for operational_id in sorted(operational_parents):
            url = entity_url("OperationalCatchment", operational_id)

            body, total_bytes = _request_and_record(
                client=client,
                pacer=pacer,
                directory=directory,
                entries=entries,
                kind="operational_catchment",
                entity_id=operational_id,
                relative=f"operational/{operational_id}.html",
                url=url,
                expected="html",
                total_bytes=total_bytes,
            )

            operational_html[operational_id] = body

            page = parse_entity_page(
                body,
                kind="OperationalCatchment",
                entity_id=operational_id,
            )

            expected_management, expected_rbd = operational_parents[operational_id]

            if page.links["RiverBasinDistrict"] != (expected_rbd,):
                raise CatchmentError("Operational Catchment River Basin District mismatch")

            if page.links["ManagementCatchment"] != (expected_management,):
                raise CatchmentError("Operational Catchment Management Catchment mismatch")

        for rbd_id in rbd_ids:
            url = rbd_geojson_url(rbd_id)

            body, total_bytes = _request_and_record(
                client=client,
                pacer=pacer,
                directory=directory,
                entries=entries,
                kind="river_basin_district_geojson",
                entity_id=rbd_id,
                relative=f"rbd-geojson/{rbd_id}.geojson",
                url=url,
                expected="geojson",
                total_bytes=total_bytes,
            )

            # Validate each geometry response before considering retrieval complete.
            parse_rbd_geojson(body, rbd_id=rbd_id)
            rbd_geojson[rbd_id] = body

    normalized = normalize(
        root_html=root_html,
        rbd_html=rbd_html,
        management_html=management_html,
        operational_html=operational_html,
        rbd_geojson=rbd_geojson,
    )

    manifest = {
        "source": ROOT,
        "plan_version": PLAN_VERSION,
        "normalization_version": VERSION,
        "retrieval_started_at": retrieval_started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "entries": entries,
        "content_sha256": content_hash(entries),
        "normalized_sha256": normalized.sha256,
        **normalized.counts,
    }

    manifest_body = encoded(manifest)

    if len(manifest_body) > MAX_MANIFEST_BYTES:
        raise CatchmentError("Catchment evidence manifest exceeds size budget")

    # Completion marker only after the complete hierarchy and geometry inventory
    # has normalized successfully.
    (directory / "manifest.json").write_bytes(manifest_body)

    return directory


def _manifest_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise CatchmentError(f"Invalid {field}")

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CatchmentError(f"Invalid {field}") from error

    if parsed.tzinfo is None:
        raise CatchmentError(f"Naive {field}")

    return parsed


def _expected_entry(
    *,
    kind: str,
    entity_id: str | None,
) -> tuple[str, str, str]:
    if kind == "root":
        if entity_id is not None:
            raise CatchmentError("Invalid root evidence identity")
        return "root.html", root_url(), "html"

    if not isinstance(entity_id, str):
        raise CatchmentError("Missing catchment evidence identity")

    if kind == "river_basin_district":
        return (
            f"rbd/{entity_id}.html",
            entity_url("RiverBasinDistrict", entity_id),
            "html",
        )

    if kind == "management_catchment":
        return (
            f"management/{entity_id}.html",
            entity_url("ManagementCatchment", entity_id),
            "html",
        )

    if kind == "operational_catchment":
        return (
            f"operational/{entity_id}.html",
            entity_url("OperationalCatchment", entity_id),
            "html",
        )

    if kind == "river_basin_district_geojson":
        return (
            f"rbd-geojson/{entity_id}.geojson",
            rbd_geojson_url(entity_id),
            "geojson",
        )

    raise CatchmentError("Unknown catchment evidence entry kind")


def _read_evidence_file(
    directory: Path,
    *,
    entry: dict[str, Any],
) -> tuple[bytes, str]:
    kind = entry.get("kind")
    entity_id = entry.get("entity_id")

    if not isinstance(kind, str):
        raise CatchmentError("Invalid catchment evidence entry")

    relative, expected_url, expected_type = _expected_entry(
        kind=kind,
        entity_id=entity_id,
    )

    if entry.get("file") != relative or entry.get("request_url") != expected_url:
        raise CatchmentError("Invalid catchment evidence entry identity")

    request_started = _manifest_timestamp(
        entry.get("request_started_at"),
        "catchment request start",
    )
    request_completed = _manifest_timestamp(
        entry.get("request_completed_at"),
        "catchment request completion",
    )

    if request_completed < request_started:
        raise CatchmentError("Reversed catchment request window")

    path = directory / relative

    if path.is_symlink():
        raise CatchmentError("Catchment evidence file must not be a symlink")

    max_bytes = MAX_HTML_BYTES if expected_type == "html" else MAX_GEOJSON_BYTES

    if not path.is_file() or path.stat().st_size > max_bytes:
        raise CatchmentError("Invalid catchment evidence file")

    body = path.read_bytes()

    if entry.get("bytes") != len(body) or entry.get("sha256") != hashlib.sha256(body).hexdigest():
        raise CatchmentError("Catchment evidence hash or size mismatch")

    headers = entry.get("headers")

    if not isinstance(headers, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in headers.items()
    ):
        raise CatchmentError("Invalid catchment evidence headers")

    return body, expected_type


def read_snapshot(
    directory: Path,
) -> tuple[dict[str, Any], NormalizedCatchments]:
    try:
        return _read_snapshot(directory)
    except CatchmentError:
        raise
    except (
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
        OSError,
    ) as error:
        raise CatchmentError("Malformed catchment evidence bundle") from error


def _read_snapshot(
    directory: Path,
) -> tuple[dict[str, Any], NormalizedCatchments]:
    manifest_path = directory / "manifest.json"

    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or manifest_path.stat().st_size > MAX_MANIFEST_BYTES
    ):
        raise CatchmentError("Invalid catchment evidence manifest")

    from watergeo.ingestion.catchments import decode_json

    manifest = decode_json(manifest_path.read_bytes())

    if (
        manifest.get("source") != ROOT
        or manifest.get("plan_version") != PLAN_VERSION
        or manifest.get("normalization_version") != VERSION
    ):
        raise CatchmentError("Unsupported catchment evidence bundle")

    retrieval_started = _manifest_timestamp(
        manifest.get("retrieval_started_at"),
        "catchment retrieval start",
    )
    retrieval_completed = _manifest_timestamp(
        manifest.get("retrieval_completed_at"),
        "catchment retrieval completion",
    )

    if retrieval_completed < retrieval_started:
        raise CatchmentError("Reversed catchment retrieval window")

    entries = manifest.get("entries")

    if (
        not isinstance(entries, list)
        or not entries
        or len(entries) > MAX_REQUESTS
        or any(not isinstance(entry, dict) for entry in entries)
    ):
        raise CatchmentError("Invalid catchment evidence entries")

    total_bytes = 0

    root_html: bytes | None = None
    rbd_html: dict[str, bytes] = {}
    management_html: dict[str, bytes] = {}
    operational_html: dict[str, bytes] = {}
    rbd_geojson: dict[str, bytes] = {}

    seen_entry_keys: set[tuple[str, str | None]] = set()

    for entry in entries:
        kind = entry["kind"]
        entity_id = entry.get("entity_id")

        evidence_key = (kind, entity_id)

        if evidence_key in seen_entry_keys:
            raise CatchmentError("Duplicate catchment evidence entry")

        seen_entry_keys.add(evidence_key)

        body, _ = _read_evidence_file(
            directory,
            entry=entry,
        )

        total_bytes += len(body)

        if total_bytes > MAX_TOTAL_BYTES:
            raise CatchmentError("Catchment evidence byte budget exceeded")

        if kind == "root":
            root_html = body
        elif kind == "river_basin_district":
            if not isinstance(entity_id, str):
                raise CatchmentError("Missing River Basin District evidence identity")
            rbd_html[entity_id] = body
        elif kind == "management_catchment":
            if not isinstance(entity_id, str):
                raise CatchmentError("Missing Management Catchment evidence identity")
            management_html[entity_id] = body
        elif kind == "operational_catchment":
            if not isinstance(entity_id, str):
                raise CatchmentError("Missing Operational Catchment evidence identity")
            operational_html[entity_id] = body
        elif kind == "river_basin_district_geojson":
            if not isinstance(entity_id, str):
                raise CatchmentError("Missing River Basin District GeoJSON identity")
            rbd_geojson[entity_id] = body
        else:
            raise CatchmentError("Unknown catchment evidence entry")

    if root_html is None:
        raise CatchmentError("Missing catchment root evidence")

    if content_hash(entries) != manifest.get("content_sha256"):
        raise CatchmentError("Catchment manifest content hash mismatch")

    normalized = normalize(
        root_html=root_html,
        rbd_html=rbd_html,
        management_html=management_html,
        operational_html=operational_html,
        rbd_geojson=rbd_geojson,
    )

    if normalized.sha256 != manifest.get("normalized_sha256"):
        raise CatchmentError("Catchment normalized hash mismatch")

    for count_key, value in normalized.counts.items():
        if manifest.get(count_key) != value:
            raise CatchmentError("Catchment manifest count mismatch")

    return manifest, normalized
