"""Bounded official EA retrieval and verifiable local evidence bundles."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.hydrology import (
    LICENCE,
    ROOT,
    VERSION,
    HydrologyError,
    Normalized,
    decode,
    digest,
    encoded,
    normalize,
)

PATHS = {"stations": "/id/stations", "measures": "/id/measures", "observations": "/data/readings"}
PAGE_LIMIT = 30000
MAX_PAGES = 20
MAX_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_RECORDS = 100000
HEADERS = ("date", "etag", "last-modified", "content-type")


def request_url(kind: str, offset: int) -> str:
    if kind not in PATHS or type(offset) is not int or not 0 <= offset <= MAX_RECORDS:
        raise HydrologyError("Unsupported source request")
    params = [
        ("observedProperty", "waterLevel"),
        ("observedProperty", "waterFlow"),
        ("_limit", str(PAGE_LIMIT)),
        ("_offset", str(offset)),
    ]
    params.append(("latest", "") if kind == "observations" else ("_sort", "notation"))
    return str(httpx.URL(ROOT + PATHS[kind], params=params))


def check_url(url: str) -> None:
    parsed = httpx.URL(url)
    if (
        parsed.scheme != "https"
        or parsed.host != "environment.data.gov.uk"
        or parsed.port not in (None, 443)
        or parsed.userinfo
        or parsed.fragment
        or parsed.path not in {"/hydrology" + path for path in PATHS.values()}
    ):
        raise HydrologyError("Disallowed source request target")


def _request(client: httpx.Client, url: str) -> tuple[bytes, dict[str, str]]:
    check_url(url)
    for attempt in range(3):
        try:
            with client.stream("GET", url, follow_redirects=False) as response:
                # No redirects are needed by the reviewed endpoints. Reject every redirect,
                # including same-host ones, instead of broadening the fetch capability.
                if 300 <= response.status_code < 400:
                    raise HydrologyError("Unexpected source redirect")
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt == 2:
                        raise HydrologyError("Source temporarily unavailable")
                else:
                    if response.status_code != 200:
                        raise HydrologyError("Unexpected source HTTP status")
                    if (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                        != "application/json"
                    ):
                        raise HydrologyError("Unsupported source content type")
                    body = bytearray()
                    started = time.monotonic()
                    for chunk in response.iter_bytes(chunk_size=65536):
                        body.extend(chunk)
                        if len(body) > MAX_BYTES or time.monotonic() - started > 120:
                            raise HydrologyError("Source response budget exceeded")
                    return bytes(body), {
                        key: response.headers[key] for key in HEADERS if key in response.headers
                    }
        except httpx.TransportError:
            if attempt == 2:
                raise HydrologyError("Source transport failed after bounded retries") from None
        time.sleep(0.5 * (2**attempt))
    raise HydrologyError("Source retrieval failed")


def page_records(body: bytes, offset: int) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    value = decode(body)
    meta, items = value.get("meta"), value.get("items")
    if (
        not isinstance(meta, dict)
        or not isinstance(items, list)
        or any(not isinstance(x, dict) for x in items)
    ):
        raise HydrologyError("Unexpected response shape")
    if (
        meta.get("publisher") != "Environment Agency"
        or meta.get("license") != LICENCE
        or meta.get("version") != "2.1.1"
    ):
        raise HydrologyError("Source provenance contract changed")
    limit = meta.get("limit")
    if type(limit) is not int or not 1 <= limit <= PAGE_LIMIT or len(items) > limit:
        raise HydrologyError("Invalid effective page limit")
    if meta.get("offset", 0) != offset:
        raise HydrologyError("Inconsistent page offset")
    return items, limit, meta


def content_hash(pages: list[dict[str, Any]]) -> str:
    return digest(
        [{"kind": p["kind"], "request_url": p["request_url"], "sha256": p["sha256"]} for p in pages]
    )


def fetch_snapshot(
    root: Path = Path("data/raw/environment-agency/hydrology"),
    *,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC)
    pages: list[dict[str, Any]] = []
    total_bytes = 0
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(60, connect=10),
        trust_env=False,
        headers={
            "User-Agent": "WaterGeo-UK/0.1 (public source ingestion)",
            "Accept": "application/json",
        },
    ) as client:
        for kind in PATHS:
            offset = 0
            seen: set[str] = set()
            for _ in range(MAX_PAGES):
                url = request_url(kind, offset)
                request_started = datetime.now(UTC)
                body, headers = _request(client, url)
                completed = datetime.now(UTC)
                total_bytes += len(body)
                if total_bytes > MAX_TOTAL_BYTES:
                    raise HydrologyError("Retrieval size budget exceeded")
                filename = f"{kind}-{offset}.json"
                (directory / filename).write_bytes(body)
                items, limit, meta = page_records(body, offset)
                for item in items:
                    key = (
                        item.get("measure", {}).get("@id")
                        if kind == "observations" and isinstance(item.get("measure"), dict)
                        else item.get("@id")
                    )
                    if not isinstance(key, str) or key in seen:
                        raise HydrologyError("Missing/duplicate identity or pagination loop")
                    seen.add(key)
                if len(seen) > MAX_RECORDS:
                    raise HydrologyError("Source record budget exceeded")
                pages.append(
                    {
                        "kind": kind,
                        "offset": offset,
                        "file": filename,
                        "request_url": url,
                        "request_started_at": request_started.isoformat(),
                        "request_completed_at": completed.isoformat(),
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
                raise HydrologyError("Pagination budget exceeded; incomplete retrieval")
    manifest = {
        "source": ROOT,
        "normalization_version": VERSION,
        "retrieval_started_at": started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "pages": pages,
        "content_sha256": content_hash(pages),
    }
    # A manifest is written only after complete retrieval. No manifest means incomplete.
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return directory


def read_snapshot(directory: Path) -> tuple[dict[str, Any], Normalized]:
    """Reject malformed evidence without exposing parser internals to callers."""
    try:
        return _read_snapshot(directory)
    except HydrologyError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise HydrologyError("Malformed evidence manifest") from error


def _read_snapshot(directory: Path) -> tuple[dict[str, Any], Normalized]:
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise HydrologyError("Invalid evidence manifest file")
    manifest = decode(manifest_path.read_bytes())
    if manifest.get("source") != ROOT or manifest.get("normalization_version") != VERSION:
        raise HydrologyError("Unsupported evidence bundle")
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not 3 <= len(pages) <= 3 * MAX_PAGES:
        raise HydrologyError("Invalid evidence manifest")
    records: dict[str, list[dict[str, Any]]] = {kind: [] for kind in PATHS}
    total_bytes = 0
    for kind in PATHS:
        selected = [page for page in pages if isinstance(page, dict) and page.get("kind") == kind]
        if not selected or len(selected) > MAX_PAGES:
            raise HydrologyError("Incomplete evidence manifest")
        offset = 0
        for index, page in enumerate(selected):
            expected_name = f"{kind}-{offset}.json"
            if (
                page.get("file") != expected_name
                or page.get("offset") != offset
                or page.get("request_url") != request_url(kind, offset)
            ):
                raise HydrologyError("Invalid evidence page identity")
            path = directory / expected_name
            if path.is_symlink() or path.stat().st_size > MAX_BYTES:
                raise HydrologyError("Invalid evidence file")
            body = path.read_bytes()
            total_bytes += len(body)
            if total_bytes > MAX_TOTAL_BYTES or hashlib.sha256(body).hexdigest() != page.get(
                "sha256"
            ):
                raise HydrologyError("Evidence byte budget or hash mismatch")
            items, limit, _ = page_records(body, offset)
            if (
                page.get("bytes") != len(body)
                or page.get("count") != len(items)
                or page.get("effective_limit") != limit
            ):
                raise HydrologyError("Evidence counts mismatch")
            if (index == len(selected) - 1) != (len(items) < limit):
                raise HydrologyError("Incomplete or excessive evidence pagination")
            records[kind].extend(items)
            offset += len(items)
            if offset > MAX_RECORDS:
                raise HydrologyError("Evidence record budget exceeded")
    if sum(len([p for p in pages if p.get("kind") == k]) for k in PATHS) != len(pages):
        raise HydrologyError("Unknown evidence page")
    if content_hash(pages) != manifest.get("content_sha256"):
        raise HydrologyError("Manifest content hash mismatch")
    for key in ("retrieval_started_at", "retrieval_completed_at"):
        value = datetime.fromisoformat(manifest[key])
        if value.tzinfo is None:
            raise HydrologyError("Naive retrieval timestamp")
    if datetime.fromisoformat(manifest["retrieval_started_at"]) > datetime.fromisoformat(
        manifest["retrieval_completed_at"]
    ):
        raise HydrologyError("Reversed retrieval window")
    return manifest, normalize(records)
