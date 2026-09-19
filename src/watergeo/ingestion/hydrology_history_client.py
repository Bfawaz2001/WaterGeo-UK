"""Bounded official EA historical-reading retrieval and local evidence bundles."""

import hashlib
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.hydrology import (
    ID_PATTERN,
    LICENCE,
    ROOT,
    HydrologyError,
    decode,
    digest,
    encoded,
    timestamp,
)
from watergeo.ingestion.hydrology_history import (
    VERSION,
    NormalizedHistory,
    normalize_history,
)

PAGE_LIMIT = 5000
MAX_PAGES = 20
MAX_RECORDS = 100000
MAX_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_WINDOW = timedelta(days=31)

HISTORY_ROOT = Path("data/raw/environment-agency/hydrology-history")
HEADERS = ("date", "etag", "last-modified", "content-type")


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise HydrologyError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def validate_window(
    requested_from: datetime,
    requested_to: datetime,
) -> tuple[datetime, datetime]:
    start = _utc(requested_from, "History from")
    end = _utc(requested_to, "History to")

    if end < start:
        raise HydrologyError("History window is reversed")

    if end - start > MAX_WINDOW:
        raise HydrologyError("History window exceeds 31 days")

    return start, end


def _source_time(value: datetime) -> str:
    value = value.astimezone(UTC)

    if value.microsecond:
        rendered = value.isoformat(timespec="microseconds")
    else:
        rendered = value.isoformat(timespec="seconds")

    return rendered.replace("+00:00", "Z")


def _measure_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(ID_PATTERN, value):
        raise HydrologyError("Invalid history measure identity")
    return value


def request_url(
    measure_id: str,
    requested_from: datetime,
    requested_to: datetime,
    offset: int,
) -> str:
    measure_id = _measure_id(measure_id)
    start, end = validate_window(requested_from, requested_to)

    if type(offset) is not int or not 0 <= offset <= MAX_RECORDS:
        raise HydrologyError("Unsupported history offset")

    path = f"/id/measures/{measure_id}/readings"

    params = [
        ("mineq-dateTime", _source_time(start)),
        ("maxeq-dateTime", _source_time(end)),
        ("_limit", str(PAGE_LIMIT)),
        ("_sort", "dateTime"),
        ("_offset", str(offset)),
    ]

    return str(httpx.URL(ROOT + path, params=params))


def check_url(url: str, measure_id: str) -> None:
    measure_id = _measure_id(measure_id)
    parsed = httpx.URL(url)

    expected_path = f"/hydrology/id/measures/{measure_id}/readings"

    if (
        parsed.scheme != "https"
        or parsed.host != "environment.data.gov.uk"
        or parsed.port not in (None, 443)
        or parsed.userinfo
        or parsed.fragment
        or parsed.path != expected_path
    ):
        raise HydrologyError("Disallowed history source request target")


def _request(
    client: httpx.Client,
    url: str,
    measure_id: str,
) -> tuple[bytes, dict[str, str]]:
    check_url(url, measure_id)

    for attempt in range(3):
        try:
            with client.stream("GET", url, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise HydrologyError("Unexpected history source redirect")

                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 2:
                        raise HydrologyError("History source temporarily unavailable")
                else:
                    if response.status_code != 200:
                        raise HydrologyError("Unexpected history source HTTP status")

                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                    )

                    if content_type != "application/json":
                        raise HydrologyError("Unsupported history source content type")

                    body = bytearray()
                    started = time.monotonic()

                    for chunk in response.iter_bytes(chunk_size=65536):
                        body.extend(chunk)

                        if len(body) > MAX_BYTES or time.monotonic() - started > 120:
                            raise HydrologyError("History source response budget exceeded")

                    return bytes(body), {
                        key: response.headers[key] for key in HEADERS if key in response.headers
                    }

        except httpx.TransportError:
            if attempt == 2:
                raise HydrologyError(
                    "History source transport failed after bounded retries"
                ) from None

        time.sleep(0.5 * (2**attempt))

    raise HydrologyError("History source retrieval failed")


def page_records(
    body: bytes,
    offset: int,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    value = decode(body)

    meta = value.get("meta")
    items = value.get("items")

    if (
        not isinstance(meta, dict)
        or not isinstance(items, list)
        or any(not isinstance(item, dict) for item in items)
    ):
        raise HydrologyError("Unexpected history response shape")

    if (
        meta.get("publisher") != "Environment Agency"
        or meta.get("license") != LICENCE
        or meta.get("version") != "2.1.1"
    ):
        raise HydrologyError("History source provenance contract changed")

    limit = meta.get("limit")

    if type(limit) is not int or not 1 <= limit <= PAGE_LIMIT or len(items) > limit:
        raise HydrologyError("Invalid history effective page limit")

    # EA omits offset on the first page but reports it on subsequent pages.
    if meta.get("offset", 0) != offset:
        raise HydrologyError("Inconsistent history page offset")

    return items, limit, meta


def content_hash(pages: list[dict[str, Any]]) -> str:
    return digest(
        [
            {
                "request_url": page["request_url"],
                "sha256": page["sha256"],
            }
            for page in pages
        ]
    )


def _validate_observation_window(
    normalized: NormalizedHistory,
    requested_from: datetime,
    requested_to: datetime,
) -> None:
    start, end = validate_window(requested_from, requested_to)

    for row in normalized.observations:
        observed = datetime.fromisoformat(row["observed_at"])

        if observed < start or observed > end:
            raise HydrologyError("Historical observation outside requested window")


def fetch_history(
    measure_id: str,
    requested_from: datetime,
    requested_to: datetime,
    root: Path = HISTORY_ROOT,
    *,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    measure_id = _measure_id(measure_id)
    start, end = validate_window(requested_from, requested_to)

    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)

    retrieval_started = datetime.now(UTC)

    pages: list[dict[str, Any]] = []
    all_records: list[dict[str, Any]] = []
    seen_timestamps: set[str] = set()
    total_bytes = 0
    offset = 0

    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(60, connect=10),
        trust_env=False,
        headers={
            "User-Agent": "WaterGeo-UK/0.1 (historical public source ingestion)",
            "Accept": "application/json",
        },
    ) as client:
        for _ in range(MAX_PAGES):
            url = request_url(measure_id, start, end, offset)

            request_started = datetime.now(UTC)
            body, headers = _request(client, url, measure_id)
            request_completed = datetime.now(UTC)

            total_bytes += len(body)

            if total_bytes > MAX_TOTAL_BYTES:
                raise HydrologyError("History retrieval size budget exceeded")

            filename = f"readings-{offset}.json"
            (directory / filename).write_bytes(body)

            items, limit, meta = page_records(body, offset)

            for item in items:
                raw_time = item.get("dateTime")

                if not isinstance(raw_time, str):
                    raise HydrologyError("Missing historical observation timestamp")

                observed = timestamp(raw_time).isoformat()

                if observed in seen_timestamps:
                    raise HydrologyError("Duplicate historical observation timestamp")

                seen_timestamps.add(observed)

            all_records.extend(items)

            if len(all_records) > MAX_RECORDS:
                raise HydrologyError("History source record budget exceeded")

            pages.append(
                {
                    "offset": offset,
                    "file": filename,
                    "request_url": url,
                    "request_started_at": request_started.isoformat(),
                    "request_completed_at": request_completed.isoformat(),
                    "headers": headers,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "bytes": len(body),
                    "count": len(items),
                    "effective_limit": limit,
                    "api_version": meta["version"],
                }
            )

            if len(items) < limit:
                break

            offset += len(items)

        else:
            raise HydrologyError("History pagination budget exceeded; incomplete retrieval")

    normalized = normalize_history(measure_id, all_records)
    _validate_observation_window(normalized, start, end)

    manifest = {
        "source": ROOT,
        "normalization_version": VERSION,
        "measure_id": measure_id,
        "requested_from": start.isoformat(),
        "requested_to": end.isoformat(),
        "retrieval_started_at": retrieval_started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "pages": pages,
        "content_sha256": content_hash(pages),
        "record_count": normalized.record_count,
    }

    # Completion marker only after every page and normalized record has passed.
    (directory / "manifest.json").write_bytes(encoded(manifest))

    return directory


def read_history(
    directory: Path,
) -> tuple[dict[str, Any], NormalizedHistory]:
    try:
        return _read_history(directory)
    except HydrologyError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as error:
        raise HydrologyError("Malformed history evidence bundle") from error


def _read_history(
    directory: Path,
) -> tuple[dict[str, Any], NormalizedHistory]:
    manifest_path = directory / "manifest.json"

    if manifest_path.is_symlink() or manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise HydrologyError("Invalid history evidence manifest")

    manifest = decode(manifest_path.read_bytes())

    if manifest.get("source") != ROOT or manifest.get("normalization_version") != VERSION:
        raise HydrologyError("Unsupported history evidence bundle")

    measure_id = _measure_id(manifest["measure_id"])

    requested_from = datetime.fromisoformat(manifest["requested_from"])
    requested_to = datetime.fromisoformat(manifest["requested_to"])

    start, end = validate_window(requested_from, requested_to)

    retrieval_started = datetime.fromisoformat(manifest["retrieval_started_at"])
    retrieval_completed = datetime.fromisoformat(manifest["retrieval_completed_at"])

    if retrieval_started.tzinfo is None or retrieval_completed.tzinfo is None:
        raise HydrologyError("Naive history retrieval timestamp")

    if retrieval_completed < retrieval_started:
        raise HydrologyError("Reversed history retrieval window")

    pages = manifest.get("pages")

    if not isinstance(pages, list) or not pages or len(pages) > MAX_PAGES:
        raise HydrologyError("Invalid history evidence pages")

    all_records: list[dict[str, Any]] = []
    total_bytes = 0
    offset = 0

    for index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise HydrologyError("Invalid history evidence page")

        expected_name = f"readings-{offset}.json"

        if (
            page.get("file") != expected_name
            or page.get("offset") != offset
            or page.get("request_url") != request_url(measure_id, start, end, offset)
        ):
            raise HydrologyError("Invalid history evidence page identity")

        path = directory / expected_name

        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            raise HydrologyError("Invalid history evidence file")

        body = path.read_bytes()
        total_bytes += len(body)

        if total_bytes > MAX_TOTAL_BYTES:
            raise HydrologyError("History evidence byte budget exceeded")

        if hashlib.sha256(body).hexdigest() != page.get("sha256"):
            raise HydrologyError("History evidence hash mismatch")

        items, limit, _ = page_records(body, offset)

        if (
            page.get("bytes") != len(body)
            or page.get("count") != len(items)
            or page.get("effective_limit") != limit
        ):
            raise HydrologyError("History evidence counts mismatch")

        terminal = len(items) < limit

        if (index == len(pages) - 1) != terminal:
            raise HydrologyError("Incomplete or excessive history evidence pagination")

        all_records.extend(items)
        offset += len(items)

        if offset > MAX_RECORDS:
            raise HydrologyError("History evidence record budget exceeded")

    if content_hash(pages) != manifest.get("content_sha256"):
        raise HydrologyError("History manifest content hash mismatch")

    normalized = normalize_history(measure_id, all_records)

    if normalized.record_count != manifest.get("record_count"):
        raise HydrologyError("History manifest record count mismatch")

    _validate_observation_window(normalized, start, end)

    return manifest, normalized
