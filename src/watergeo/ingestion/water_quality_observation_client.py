"""Fixed-host, paced bounded observation retrieval and independently checked evidence."""

import hashlib
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.water_quality import (
    API_VERSION,
    CRS_4326,
    ROOT,
    WaterQualityError,
    decode,
    digest,
    encoded,
)
from watergeo.ingestion.water_quality_observations import (
    CODE,
    CODELIST_CONTEXT,
    MAX_RECORDS,
    OBSERVATION_CONTEXT,
    VERSION,
    Normalized,
    Scope,
    normalize,
)

PAGE_LIMIT = 250
MAX_PAGES = 20
MAX_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_UNITS = 20


def request_url(kind: str, scope: Scope, skip: int = 0, unit: str | None = None) -> str:
    if type(skip) is not int or not 0 <= skip < MAX_RECORDS:
        raise WaterQualityError("Invalid observation page")
    if kind == "observation":
        path = "/data/observation"
        params = {
            "pointNotation": scope.sampling_point_id,
            "determinand": scope.determinand,
            "dateFrom": scope.date_from.isoformat(),
            "dateTo": scope.date_to.isoformat(),
            "limit": str(PAGE_LIMIT),
            "skip": str(skip),
        }
    elif kind in {"determinand", "unit"} and skip == 0:
        notation = scope.determinand if kind == "determinand" else unit
        if not isinstance(notation, str) or not CODE.fullmatch(notation):
            raise WaterQualityError("Invalid codelist request")
        path = "/codelist/" + kind
        params = {"notation": notation, "limit": str(PAGE_LIMIT), "skip": "0"}
    else:
        raise WaterQualityError("Disallowed observation request")
    return str(httpx.URL(ROOT + path, params=params))


def _request(
    client: httpx.Client, kind: str, scope: Scope, skip: int, unit: str | None
) -> tuple[bytes, dict[str, str]]:
    url = request_url(kind, scope, skip, unit)
    for attempt in range(3):
        # Includes retries: stay below the reviewed automated request ceiling.
        time.sleep(0.5 * (2**attempt))
        try:
            with client.stream(
                "POST" if kind == "observation" else "GET",
                url,
                content=b"null" if kind == "observation" else None,
                follow_redirects=False,
            ) as response:
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt == 2:
                        raise WaterQualityError("Observation source temporarily unavailable")
                    continue
                if response.status_code != 200:
                    raise WaterQualityError("Observation source status/redirect rejected")
                if (
                    response.headers.get("content-type", "").split(";")[0].lower()
                    != "application/ld+json"
                    or response.headers.get("api-version") != API_VERSION
                ):
                    raise WaterQualityError("Observation response contract changed")
                if kind == "observation" and response.headers.get("content-crs") != CRS_4326:
                    raise WaterQualityError("Observation response CRS changed")
                body = bytearray()
                start = time.monotonic()
                for chunk in response.iter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_BYTES or time.monotonic() - start > 120:
                        raise WaterQualityError("Observation response budget exceeded")
                return bytes(body), {
                    key: response.headers[key]
                    for key in (
                        "date",
                        "content-type",
                        "api-version",
                        "content-crs",
                        "x-total-items",
                        "x-page-skip",
                        "x-page-limit",
                    )
                    if key in response.headers
                }
        except httpx.TransportError:
            if attempt == 2:
                raise WaterQualityError(
                    "Observation transport failed after bounded retries"
                ) from None
    raise WaterQualityError("Observation retrieval failed")


def members(body: bytes, kind: str, skip: int) -> tuple[list[dict[str, Any]], int]:
    payload = decode(body)
    context = OBSERVATION_CONTEXT if kind == "observation" else CODELIST_CONTEXT
    rows, total = payload.get("member"), payload.get("totalItems")
    if payload.get("@context") != context or payload.get("@type") != "hydra:Collection":
        raise WaterQualityError("Unreviewed observation/codelist collection")
    if (
        type(total) is not int
        or not 0 <= total <= MAX_RECORDS
        or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise WaterQualityError("Invalid observation collection")
    if skip > total or len(rows) != min(PAGE_LIMIT, total - skip):
        raise WaterQualityError("Incomplete observation page")
    if kind != "observation" and total != 1:
        raise WaterQualityError("Codelist must have exactly one scoped entry")
    return rows, total


def content_hash(scope: Scope, pages: list[dict[str, Any]]) -> str:
    return digest(
        {
            "scope": scope.as_dict(),
            "pages": [
                {key: page[key] for key in ("kind", "request_url", "sha256")} for page in pages
            ],
        }
    )


def fetch_observations(
    scope: Scope,
    root: Path = Path("data/raw/environment-agency/water-quality/observations"),
    *,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC)
    pages: list[dict[str, Any]] = []
    total_bytes = 0
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with httpx.Client(
        transport=transport,
        trust_env=False,
        timeout=httpx.Timeout(60, connect=10),
        headers={
            "User-Agent": "WaterGeo-UK/0.1 (public source ingestion)",
            "Accept": "application/ld+json",
            "Content-Type": "application/json",
            "Accept-Crs": CRS_4326,
            "API-Version": API_VERSION,
        },
    ) as client:

        def fetch(
            kind: str, skip: int = 0, unit: str | None = None
        ) -> tuple[list[dict[str, Any]], int]:
            nonlocal total_bytes
            body, headers = _request(client, kind, scope, skip, unit)
            total_bytes += len(body)
            if total_bytes > MAX_TOTAL_BYTES:
                raise WaterQualityError("Observation retrieval byte budget exceeded")
            name = f"response-{len(pages):03d}.json"
            (directory / name).write_bytes(body)
            rows, total = members(body, kind, skip)
            pages.append(
                {
                    "kind": kind,
                    "skip": skip,
                    "unit": unit,
                    "file": name,
                    "request_url": request_url(kind, scope, skip, unit),
                    "headers": headers,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "bytes": len(body),
                    "count": len(rows),
                    "reported_total": total,
                }
            )
            return rows, total

        total: int | None = None
        for _ in range(MAX_PAGES):
            rows, current = fetch("observation", len(records))
            if total is not None and total != current:
                raise WaterQualityError("Observation total changed during retrieval")
            total = current
            for row in rows:
                identity = row.get("id")
                if not isinstance(identity, str) or identity in seen:
                    raise WaterQualityError("Missing or repeated observation identity")
                seen.add(identity)
            records.extend(rows)
            if len(records) == total:
                break
        else:
            raise WaterQualityError("Incomplete observation page budget")
        determinands, _ = fetch("determinand")
        unit_ids = referenced_units(records)
        units = [fetch("unit", unit=identity)[0][0] for identity in unit_ids]
        data = normalize(scope, records, determinands[0], units)
    manifest = {
        "source": ROOT,
        "dataset": "observations",
        "api_version": API_VERSION,
        "normalization_version": VERSION,
        "scope": scope.as_dict(),
        "pages": pages,
        "retrieval_started_at": started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "content_sha256": content_hash(scope, pages),
        "normalized_sha256": data.sha256,
    }
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return directory


def referenced_units(records: list[dict[str, Any]]) -> list[str]:
    units: set[str] = set()
    for row in records:
        quantity = row.get("hasResult")
        unit = quantity.get("hasUnit") if isinstance(quantity, dict) else None
        notation = unit.get("notation") if isinstance(unit, dict) else None
        if not isinstance(notation, str) or not CODE.fullmatch(notation):
            raise WaterQualityError("Invalid referenced unit")
        units.add(notation)
    if len(units) > MAX_UNITS:
        raise WaterQualityError("Unit request budget exceeded")
    return sorted(units)


def read_observations(directory: Path) -> tuple[dict[str, Any], Normalized]:
    try:
        return _read(directory)
    except WaterQualityError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OSError, OverflowError) as error:
        raise WaterQualityError("Malformed observation evidence") from error


def _read(directory: Path) -> tuple[dict[str, Any], Normalized]:
    path = directory / "manifest.json"
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise WaterQualityError("Invalid observation manifest")
    manifest = decode(path.read_bytes())
    if any(
        manifest.get(key) != value
        for key, value in {
            "source": ROOT,
            "dataset": "observations",
            "api_version": API_VERSION,
            "normalization_version": VERSION,
        }.items()
    ):
        raise WaterQualityError("Observation evidence version mismatch")
    raw_scope = manifest["scope"]
    scope = Scope(
        raw_scope["sampling_point_id"],
        raw_scope["determinand"],
        date.fromisoformat(raw_scope["date_from"]),
        date.fromisoformat(raw_scope["date_to"]),
    )
    if raw_scope != scope.as_dict():
        raise WaterQualityError("Unreviewed observation scope")
    start, end = (
        datetime.fromisoformat(manifest[key])
        for key in ("retrieval_started_at", "retrieval_completed_at")
    )
    if start.tzinfo is None or end.tzinfo is None or start > end:
        raise WaterQualityError("Invalid observation retrieval timestamps")
    pages = manifest["pages"]
    if not isinstance(pages, list) or not 2 <= len(pages) <= MAX_PAGES + MAX_UNITS + 1:
        raise WaterQualityError("Invalid observation evidence page count")
    records: list[dict[str, Any]] = []
    total: int | None = None
    determinand = None
    units = []
    total_bytes = 0
    obs_pages = 0
    for index, page in enumerate(pages):
        if total is None or len(records) < total:
            kind, skip, unit = "observation", len(records), None
            obs_pages += 1
            if obs_pages > MAX_PAGES:
                raise WaterQualityError("Observation page budget exceeded")
        elif determinand is None:
            kind, skip, unit = "determinand", 0, None
        else:
            expected_units = referenced_units(records)
            if len(units) >= len(expected_units):
                raise WaterQualityError("Unexpected extra observation evidence")
            kind, skip, unit = "unit", 0, expected_units[len(units)]
        name = f"response-{index:03d}.json"
        expected = {
            "kind": kind,
            "skip": skip,
            "unit": unit,
            "file": name,
            "request_url": request_url(kind, scope, skip, unit),
        }
        if any(page.get(key) != value for key, value in expected.items()):
            raise WaterQualityError("Observation request identity mismatch")
        headers = page.get("headers")
        if (
            not isinstance(headers, dict)
            or headers.get("api-version") != API_VERSION
            or headers.get("content-type", "").split(";")[0].lower() != "application/ld+json"
        ):
            raise WaterQualityError("Observation evidence response contract mismatch")
        if kind == "observation" and headers.get("content-crs") != CRS_4326:
            raise WaterQualityError("Observation evidence CRS mismatch")
        path = directory / name
        if path.is_symlink() or path.stat().st_size > MAX_BYTES:
            raise WaterQualityError("Unsafe observation evidence file")
        body = path.read_bytes()
        total_bytes += len(body)
        if (
            total_bytes > MAX_TOTAL_BYTES
            or len(body) != page["bytes"]
            or hashlib.sha256(body).hexdigest() != page["sha256"]
        ):
            raise WaterQualityError("Observation evidence size/hash mismatch")
        rows, current = members(body, kind, skip)
        if page["count"] != len(rows) or page["reported_total"] != current:
            raise WaterQualityError("Observation evidence counts mismatch")
        if kind == "observation":
            if total is not None and total != current:
                raise WaterQualityError("Observation evidence total changed")
            total = current
            records.extend(rows)
        elif kind == "determinand":
            determinand = rows[0]
        else:
            units.append(rows[0])
    if total != len(records) or determinand is None:
        raise WaterQualityError("Incomplete observation evidence")
    data = normalize(scope, records, determinand, units)
    if (
        content_hash(scope, pages) != manifest["content_sha256"]
        or data.sha256 != manifest["normalized_sha256"]
    ):
        raise WaterQualityError("Observation manifest integrity mismatch")
    return manifest, data
