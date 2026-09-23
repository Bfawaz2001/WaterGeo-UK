"""Bounded fixed-host retrieval of the reviewed Stream reservoir edition."""

import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.stream_reservoirs import (
    EDITION,
    FIELDS,
    ITEM_ID,
    ITEM_URL,
    LAYER_URL,
    MAX_RECORDS,
    PRESENTATION_SRID,
    PUBLIC_ITEM_URL,
    SERVICE_ROOT,
    VERSION,
    NormalizedReservoirs,
    StreamReservoirError,
    decode,
    digest,
    encoded,
    normalize,
    parse_ids,
    parse_item,
    parse_layer,
)

ROOT = Path("data/raw/stream/severn-trent-reservoir-levels")
PAGE_SIZE = 250
MAX_PAGES = 8
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RESPONSE_SECONDS = 120.0
HEADERS = ("date", "etag", "last-modified", "content-type")
RETRYABLE = {429, 500, 502, 503, 504}
OUT_FIELDS = ",".join(FIELDS)
ORDER = "RESERVOIR_ID ASC,DATE ASC,FID ASC"


def item_url() -> str:
    return str(httpx.URL(ITEM_URL, params={"f": "json"}))


def layer_url() -> str:
    return str(httpx.URL(LAYER_URL, params={"f": "json"}))


def ids_url() -> str:
    return str(
        httpx.URL(
            LAYER_URL + "/query",
            params={"where": "1=1", "returnIdsOnly": "true", "f": "json"},
        )
    )


def page_url(object_ids: list[int]) -> str:
    if (
        not object_ids
        or len(object_ids) > PAGE_SIZE
        or object_ids != sorted(set(object_ids))
        or any(type(value) is not int or value <= 0 for value in object_ids)
    ):
        raise StreamReservoirError("Invalid Stream page identity")
    return str(
        httpx.URL(
            LAYER_URL + "/query",
            params={
                "objectIds": ",".join(str(value) for value in object_ids),
                "outFields": OUT_FIELDS,
                "returnGeometry": "true",
                "outSR": str(PRESENTATION_SRID),
                "orderByFields": ORDER,
                "f": "geojson",
            },
        )
    )


def _allowed_url(url: str) -> None:
    parsed = httpx.URL(url)
    if (
        parsed.scheme != "https"
        or parsed.port not in (None, 443)
        or parsed.userinfo
        or parsed.fragment
    ):
        raise StreamReservoirError("Disallowed Stream request target")
    if str(parsed) in {item_url(), layer_url(), ids_url()}:
        return
    if (
        parsed.host != "services-eu1.arcgis.com"
        or parsed.path != httpx.URL(LAYER_URL + "/query").path
    ):
        raise StreamReservoirError("Disallowed Stream request target")
    query = parse_qs(parsed.query.decode(), keep_blank_values=True)
    expected = {
        "outFields": [OUT_FIELDS],
        "returnGeometry": ["true"],
        "outSR": [str(PRESENTATION_SRID)],
        "orderByFields": [ORDER],
        "f": ["geojson"],
    }
    values = query.pop("objectIds", [])
    if query != expected or len(values) != 1:
        raise StreamReservoirError("Disallowed Stream query")
    try:
        identities = [int(value) for value in values[0].split(",")]
    except ValueError as error:
        raise StreamReservoirError("Disallowed Stream query") from error
    if url != page_url(identities):
        raise StreamReservoirError("Disallowed Stream query")


def _request(client: httpx.Client, url: str) -> tuple[bytes, dict[str, str]]:
    _allowed_url(url)
    for attempt in range(3):
        time.sleep(0.25 * (2**attempt))
        try:
            with client.stream("GET", url, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise StreamReservoirError("Unexpected Stream redirect")
                if response.status_code in RETRYABLE:
                    if attempt == 2:
                        raise StreamReservoirError("Stream source temporarily unavailable")
                    continue
                if response.status_code != 200:
                    raise StreamReservoirError("Unexpected Stream source status")
                if response.headers.get("content-type", "").split(";")[0].lower() not in {
                    "application/json",
                    "application/geo+json",
                }:
                    raise StreamReservoirError("Unexpected Stream content type")
                body = bytearray()
                started = time.monotonic()
                for chunk in response.iter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if (
                        len(body) > MAX_RESPONSE_BYTES
                        or time.monotonic() - started > MAX_RESPONSE_SECONDS
                    ):
                        raise StreamReservoirError("Stream response budget exceeded")
                return bytes(body), {
                    key: response.headers[key] for key in HEADERS if key in response.headers
                }
        except httpx.TransportError:
            if attempt == 2:
                raise StreamReservoirError(
                    "Stream transport failed after bounded retries"
                ) from None
    raise StreamReservoirError("Stream retrieval failed")


def _entry(
    kind: str,
    name: str,
    url: str,
    body: bytes,
    headers: dict[str, str],
    *,
    object_ids: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "file": name,
        "request_url": url,
        "object_ids": object_ids,
        "headers": headers,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def content_hash(entries: list[dict[str, Any]]) -> str:
    return digest(
        [
            {
                "kind": entry["kind"],
                "request_url": entry["request_url"],
                "object_ids": entry["object_ids"],
                "sha256": entry["sha256"],
            }
            for entry in entries
        ]
    )


def fetch_snapshot(root: Path = ROOT, *, transport: httpx.BaseTransport | None = None) -> Path:
    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC)
    entries: list[dict[str, Any]] = []
    total_bytes = 0

    with httpx.Client(
        transport=transport,
        trust_env=False,
        timeout=httpx.Timeout(60, connect=10),
        headers={"User-Agent": "WaterGeo-UK/0.1 (public source ingestion)"},
    ) as client:

        def fetch(kind: str, url: str, object_ids: list[int] | None = None) -> bytes:
            nonlocal total_bytes
            body, headers = _request(client, url)
            total_bytes += len(body)
            if total_bytes > MAX_TOTAL_BYTES:
                raise StreamReservoirError("Stream retrieval byte budget exceeded")
            name = f"response-{len(entries):03d}.json"
            (directory / name).write_bytes(body)
            entries.append(_entry(kind, name, url, body, headers, object_ids=object_ids))
            return body

        item_before = parse_item(fetch("item-before", item_url()))
        parse_layer(fetch("layer", layer_url()))
        identities = parse_ids(fetch("ids-before", ids_url()))
        if len(identities) > MAX_RECORDS:
            raise StreamReservoirError("Stream record budget exceeded")
        pages: list[dict[str, Any]] = []
        for offset in range(0, len(identities), PAGE_SIZE):
            page_ids = identities[offset : offset + PAGE_SIZE]
            if len(pages) >= MAX_PAGES:
                raise StreamReservoirError("Stream page budget exceeded")
            pages.append(decode(fetch("page", page_url(page_ids), page_ids)))
        identities_after = parse_ids(fetch("ids-after", ids_url()))
        item_after = parse_item(fetch("item-after", item_url()))
        if identities_after != identities:
            raise StreamReservoirError("Stream object IDs changed during retrieval")
        for key in ("id", "title", "modified", "url", "accessInformation", "licenseInfo"):
            if item_after.get(key) != item_before.get(key):
                raise StreamReservoirError("Stream item changed during retrieval")
        data = normalize(pages, identities)

    manifest = {
        "source": PUBLIC_ITEM_URL,
        "source_item_id": ITEM_ID,
        "service": SERVICE_ROOT,
        "edition": EDITION,
        "normalization_version": VERSION,
        "retrieval_started_at": started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "source_item_created_ms": item_before["created"],
        "source_item_modified_ms": item_before["modified"],
        "entries": entries,
        "content_sha256": content_hash(entries),
        "normalized_sha256": data.sha256,
        "reservoir_count": len(data.reservoirs),
        "reading_count": len(data.readings),
    }
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return directory


def read_snapshot(directory: Path) -> tuple[dict[str, Any], NormalizedReservoirs]:
    try:
        return _read_snapshot(directory)
    except StreamReservoirError:
        raise
    except (KeyError, TypeError, ValueError, OSError, OverflowError, AttributeError) as error:
        raise StreamReservoirError("Malformed Stream evidence") from error


def _read_snapshot(directory: Path) -> tuple[dict[str, Any], NormalizedReservoirs]:
    manifest_path = directory / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise StreamReservoirError("Invalid Stream manifest")
    manifest = decode(manifest_path.read_bytes())
    expected_identity = {
        "source": PUBLIC_ITEM_URL,
        "source_item_id": ITEM_ID,
        "service": SERVICE_ROOT,
        "edition": EDITION,
        "normalization_version": VERSION,
    }
    if any(manifest.get(key) != value for key, value in expected_identity.items()):
        raise StreamReservoirError("Unsupported Stream evidence bundle")
    started = datetime.fromisoformat(manifest["retrieval_started_at"])
    completed = datetime.fromisoformat(manifest["retrieval_completed_at"])
    if started.tzinfo is None or completed.tzinfo is None or started > completed:
        raise StreamReservoirError("Invalid Stream retrieval timestamps")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not 6 <= len(entries) <= MAX_PAGES + 5:
        raise StreamReservoirError("Invalid Stream evidence entries")

    total_bytes = 0
    bodies: list[bytes] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise StreamReservoirError("Invalid Stream evidence entry")
        name = f"response-{index:03d}.json"
        path = directory / name
        if (
            entry.get("file") != name
            or path.is_symlink()
            or path.stat().st_size > MAX_RESPONSE_BYTES
        ):
            raise StreamReservoirError("Unsafe Stream evidence file")
        body = path.read_bytes()
        total_bytes += len(body)
        headers = entry.get("headers")
        if (
            total_bytes > MAX_TOTAL_BYTES
            or not isinstance(headers, dict)
            or headers.get("content-type", "").split(";")[0].lower()
            not in {"application/json", "application/geo+json"}
            or entry.get("bytes") != len(body)
            or entry.get("sha256") != hashlib.sha256(body).hexdigest()
        ):
            raise StreamReservoirError("Stream evidence integrity mismatch")
        bodies.append(body)

    if entries[0].get("kind") != "item-before" or entries[0].get("request_url") != item_url():
        raise StreamReservoirError("Invalid Stream evidence sequence")
    item_before = parse_item(bodies[0])
    if entries[1].get("kind") != "layer" or entries[1].get("request_url") != layer_url():
        raise StreamReservoirError("Invalid Stream evidence sequence")
    parse_layer(bodies[1])
    if entries[2].get("kind") != "ids-before" or entries[2].get("request_url") != ids_url():
        raise StreamReservoirError("Invalid Stream evidence sequence")
    identities = parse_ids(bodies[2])
    page_count = (len(identities) + PAGE_SIZE - 1) // PAGE_SIZE
    if len(entries) != page_count + 5 or page_count > MAX_PAGES:
        raise StreamReservoirError("Incomplete Stream evidence sequence")
    pages = []
    for page_index in range(page_count):
        index = 3 + page_index
        page_ids = identities[page_index * PAGE_SIZE : (page_index + 1) * PAGE_SIZE]
        if (
            entries[index].get("kind") != "page"
            or entries[index].get("object_ids") != page_ids
            or entries[index].get("request_url") != page_url(page_ids)
        ):
            raise StreamReservoirError("Stream page identity mismatch")
        pages.append(decode(bodies[index]))
    ids_index = 3 + page_count
    item_index = ids_index + 1
    if (
        entries[ids_index].get("kind") != "ids-after"
        or entries[ids_index].get("request_url") != ids_url()
        or parse_ids(bodies[ids_index]) != identities
        or entries[item_index].get("kind") != "item-after"
        or entries[item_index].get("request_url") != item_url()
    ):
        raise StreamReservoirError("Stream retrieval changed during paging")
    item_after = parse_item(bodies[item_index])
    for key in ("id", "title", "modified", "url", "accessInformation", "licenseInfo"):
        if item_after.get(key) != item_before.get(key):
            raise StreamReservoirError("Stream item changed during retrieval")
    data = normalize(pages, identities)
    if (
        manifest.get("source_item_created_ms") != item_before["created"]
        or manifest.get("source_item_modified_ms") != item_before["modified"]
        or manifest.get("content_sha256") != content_hash(entries)
        or manifest.get("normalized_sha256") != data.sha256
        or manifest.get("reservoir_count") != len(data.reservoirs)
        or manifest.get("reading_count") != len(data.readings)
    ):
        raise StreamReservoirError("Stream manifest integrity mismatch")
    expected_files = {"manifest.json", *(entry["file"] for entry in entries)}
    if {path.name for path in directory.iterdir()} != expected_files:
        raise StreamReservoirError("Unexpected Stream evidence file")
    return manifest, data
