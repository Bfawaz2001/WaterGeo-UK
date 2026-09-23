"""Bounded EA Water Quality Explorer sampling-point retrieval and evidence bundles."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.water_quality import (
    API_VERSION,
    CONTEXT,
    CRS_4326,
    ROOT,
    VERSION,
    Normalized,
    WaterQualityError,
    decode,
    encoded,
    normalize,
)

PATH = "/data/sampling-point"
PAGE_LIMIT = 250
MAX_PAGES = 400
MAX_RECORDS = 100000
MAX_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MIN_REQUEST_INTERVAL_SECONDS = 0.5

HEADERS = (
    "date",
    "etag",
    "last-modified",
    "content-type",
    "content-crs",
    "api-version",
    "x-total-items",
    "x-page-skip",
    "x-page-limit",
)


def request_url(skip: int) -> str:
    if type(skip) is not int or not 0 <= skip <= MAX_RECORDS:
        raise WaterQualityError("Unsupported source request")
    return str(
        httpx.URL(
            ROOT + PATH,
            params={
                "limit": str(PAGE_LIMIT),
                "skip": str(skip),
            },
        )
    )


def check_url(url: str) -> None:
    parsed = httpx.URL(url)
    if (
        parsed.scheme != "https"
        or parsed.host != "environment.data.gov.uk"
        or parsed.port not in (None, 443)
        or parsed.userinfo
        or parsed.fragment
        or parsed.path != "/water-quality/data/sampling-point"
    ):
        raise WaterQualityError("Disallowed source request target")


def _request(client: httpx.Client, url: str) -> tuple[bytes, dict[str, str]]:
    check_url(url)

    for attempt in range(3):
        try:
            with client.stream(
                "POST",
                url,
                content=b"null",
                headers={"Content-Type": "application/json"},
                follow_redirects=False,
            ) as response:
                if 300 <= response.status_code < 400:
                    raise WaterQualityError("Unexpected source redirect")

                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 2:
                        raise WaterQualityError("Source temporarily unavailable")
                else:
                    if response.status_code != 200:
                        raise WaterQualityError("Unexpected source HTTP status")

                    content_type = (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                    )
                    if content_type != "application/ld+json":
                        raise WaterQualityError("Unsupported source content type")
                    if response.headers.get("content-crs") != CRS_4326:
                        raise WaterQualityError("Unexpected source CRS")
                    if response.headers.get("api-version") != API_VERSION:
                        raise WaterQualityError("Unexpected source API version")

                    body = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        body.extend(chunk)
                        if len(body) > MAX_BYTES or time.monotonic() - started > 120:
                            raise WaterQualityError("Source response budget exceeded")

                    return bytes(body), {
                        key: response.headers[key] for key in HEADERS if key in response.headers
                    }

        except httpx.TransportError:
            if attempt == 2:
                raise WaterQualityError("Source transport failed after bounded retries") from None

        time.sleep(0.5 * (2**attempt))

    raise WaterQualityError("Source retrieval failed")


def page_records(
    body: bytes,
    *,
    expected_skip: int,
) -> tuple[list[dict[str, Any]], int]:
    value = decode(body)

    if value.get("@context") != CONTEXT or value.get("@type") != "hydra:Collection":
        raise WaterQualityError("Source collection contract changed")

    total = value.get("totalItems")
    members = value.get("member")
    view = value.get("view")

    if (
        type(total) is not int
        or total < 1
        or total > MAX_RECORDS
        or not isinstance(members, list)
        or any(not isinstance(item, dict) for item in members)
        or not isinstance(view, dict)
    ):
        raise WaterQualityError("Unexpected response shape")

    if len(members) > PAGE_LIMIT:
        raise WaterQualityError("Source page exceeds reviewed limit")

    expected_count = min(PAGE_LIMIT, total - expected_skip)
    if expected_count < 0 or len(members) != expected_count:
        raise WaterQualityError("Incomplete sampling-point page")

    return members, total


def content_hash(pages: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        encoded(
            [
                {
                    "request_url": page["request_url"],
                    "sha256": page["sha256"],
                }
                for page in pages
            ]
        )
    ).hexdigest()


def fetch_snapshot(
    root: Path = Path("data/raw/environment-agency/water-quality/sampling-points"),
    *,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)

    started = datetime.now(UTC)
    pages: list[dict[str, Any]] = []
    total_bytes = 0
    skip = 0
    expected_total: int | None = None
    seen: set[str] = set()

    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(60, connect=10),
        trust_env=False,
        headers={
            "User-Agent": "WaterGeo-UK/0.1 (public source ingestion)",
            "Accept": "application/ld+json",
            "Accept-Crs": CRS_4326,
            "API-Version": API_VERSION,
        },
    ) as client:
        previous_request_started: float | None = None

        for _ in range(MAX_PAGES):
            now = time.monotonic()
            if previous_request_started is not None:
                remaining = MIN_REQUEST_INTERVAL_SECONDS - (now - previous_request_started)
                if remaining > 0:
                    time.sleep(remaining)

            previous_request_started = time.monotonic()
            url = request_url(skip)
            request_started = datetime.now(UTC)
            body, headers = _request(client, url)
            completed = datetime.now(UTC)

            total_bytes += len(body)
            if total_bytes > MAX_TOTAL_BYTES:
                raise WaterQualityError("Retrieval size budget exceeded")

            members, total = page_records(body, expected_skip=skip)

            if expected_total is None:
                expected_total = total
            elif total != expected_total:
                raise WaterQualityError("Sampling-point total changed during retrieval")

            filename = f"sampling-points-{skip}.json"
            (directory / filename).write_bytes(body)

            for member in members:
                identity = member.get("id")
                if not isinstance(identity, str) or identity in seen:
                    raise WaterQualityError("Missing/duplicate identity or pagination loop")
                seen.add(identity)

            pages.append(
                {
                    "skip": skip,
                    "file": filename,
                    "request_url": url,
                    "request_started_at": request_started.isoformat(),
                    "request_completed_at": completed.isoformat(),
                    "headers": headers,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "bytes": len(body),
                    "count": len(members),
                    "reported_total": total,
                }
            )

            skip += len(members)

            if skip == total:
                break
            if skip > total or not members:
                raise WaterQualityError("Invalid source pagination")
        else:
            raise WaterQualityError("Pagination budget exceeded; incomplete retrieval")

    if expected_total is None or len(seen) != expected_total:
        raise WaterQualityError("Incomplete sampling-point retrieval")

    manifest = {
        "source": ROOT,
        "dataset": "sampling-points",
        "api_version": API_VERSION,
        "response_crs": CRS_4326,
        "normalization_version": VERSION,
        "retrieval_started_at": started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "pages": pages,
        "content_sha256": content_hash(pages),
    }

    (directory / "manifest.json").write_bytes(encoded(manifest))
    return directory


def read_snapshot(directory: Path) -> tuple[dict[str, Any], Normalized]:
    try:
        return _read_snapshot(directory)
    except WaterQualityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as error:
        raise WaterQualityError("Malformed evidence bundle") from error


def _read_snapshot(directory: Path) -> tuple[dict[str, Any], Normalized]:
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise WaterQualityError("Invalid evidence manifest file")

    manifest = decode(manifest_path.read_bytes())

    if (
        manifest.get("source") != ROOT
        or manifest.get("dataset") != "sampling-points"
        or manifest.get("api_version") != API_VERSION
        or manifest.get("response_crs") != CRS_4326
        or manifest.get("normalization_version") != VERSION
    ):
        raise WaterQualityError("Unsupported evidence bundle")

    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages or len(pages) > MAX_PAGES:
        raise WaterQualityError("Invalid evidence manifest")

    records: list[dict[str, Any]] = []
    total_bytes = 0
    expected_total: int | None = None
    skip = 0

    for page in pages:
        if not isinstance(page, dict):
            raise WaterQualityError("Invalid evidence manifest")

        expected_name = f"sampling-points-{skip}.json"

        if (
            page.get("skip") != skip
            or page.get("file") != expected_name
            or page.get("request_url") != request_url(skip)
        ):
            raise WaterQualityError("Invalid evidence page identity")

        path = directory / expected_name
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            raise WaterQualityError("Invalid evidence file")

        body = path.read_bytes()
        total_bytes += len(body)

        if total_bytes > MAX_TOTAL_BYTES:
            raise WaterQualityError("Evidence byte budget exceeded")
        if hashlib.sha256(body).hexdigest() != page.get("sha256"):
            raise WaterQualityError("Evidence hash mismatch")

        members, total = page_records(body, expected_skip=skip)

        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise WaterQualityError("Inconsistent evidence total")

        if (
            page.get("bytes") != len(body)
            or page.get("count") != len(members)
            or page.get("reported_total") != total
        ):
            raise WaterQualityError("Evidence counts mismatch")

        records.extend(members)
        skip += len(members)

    if expected_total is None or skip != expected_total:
        raise WaterQualityError("Incomplete evidence pagination")

    if content_hash(pages) != manifest.get("content_sha256"):
        raise WaterQualityError("Manifest content hash mismatch")

    started = datetime.fromisoformat(manifest["retrieval_started_at"])
    completed = datetime.fromisoformat(manifest["retrieval_completed_at"])
    if started.tzinfo is None or completed.tzinfo is None or started > completed:
        raise WaterQualityError("Invalid retrieval window")

    return manifest, normalize(records)
