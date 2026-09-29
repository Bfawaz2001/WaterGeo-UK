"""Bounded evidence-first retrieval for Phase 15 JSON source products."""

import hashlib
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.phase15_sources import (
    BATHING_ROOT,
    FLOOD_ROOT,
    VERSION,
    NormalizedProduct,
    Phase15SourceError,
    decode,
    encoded,
    normalize_bathing,
    normalize_company_performance,
    normalize_floods,
    normalize_rainfall,
)

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 96 * 1024 * 1024
HEADERS = ("date", "etag", "last-modified", "content-type")
ROOT = Path("data/raw/phase15")


def _write(path: Path, body: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def _replace(path: Path, body: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4()}.tmp")
    _write(temporary, body)
    os.replace(temporary, path)


def _get(client: httpx.Client, url: str) -> tuple[bytes, dict[str, str]]:
    with client.stream("GET", url, follow_redirects=False) as response:
        if response.status_code != 200:
            raise Phase15SourceError("Unexpected publisher response status")
        if response.headers.get("content-type", "").split(";")[0].lower() not in {
            "application/json",
            "application/geo+json",
        }:
            raise Phase15SourceError("Unexpected publisher response type")
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=65536):
            body.extend(chunk)
            if len(body) > MAX_FILE_BYTES:
                raise Phase15SourceError("Publisher response exceeded size budget")
    return bytes(body), {key: response.headers[key] for key in HEADERS if key in response.headers}


class EvidenceBundle:
    """Persist each bounded response before any publisher-schema interpretation."""

    def __init__(self, source: str, root: Path):
        self.source = source
        self.directory = root / source / str(uuid4())
        self.directory.mkdir(parents=True, exist_ok=False)
        self.started = datetime.now(UTC)
        self.responses: dict[str, dict[str, Any]] = {}
        self.total = 0
        self._record_retrieval("retrieving")

    def _record_retrieval(self, state: str, completed: datetime | None = None) -> dict[str, Any]:
        retrieval = {
            "evidence_state": state,
            "source": self.source,
            "retrieval_started_at": self.started.isoformat(),
            **({"retrieval_completed_at": completed.isoformat()} if completed else {}),
            "responses": self.responses,
        }
        _replace(self.directory / "retrieval.json", encoded(retrieval))
        return retrieval

    def add(self, name: str, url: str, body: bytes, headers: Mapping[str, str]) -> None:
        if (
            name != Path(name).name
            or not name.endswith(".json")
            or name in self.responses
            or len(body) > MAX_FILE_BYTES
        ):
            raise Phase15SourceError("Invalid evidence response")
        self.total += len(body)
        if self.total > MAX_TOTAL_BYTES:
            raise Phase15SourceError("Evidence bundle exceeded size budget")
        _write(self.directory / name, body)
        self.responses[name] = {
            "url": url,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "headers": dict(headers),
        }
        self._record_retrieval("retrieving")

    def fetch(self, client: httpx.Client, name: str, url: str) -> bytes:
        body, headers = _get(client, url)
        self.add(name, url, body, headers)
        return body

    def validate(self, normalize: Callable[[dict[str, dict[str, Any]]], NormalizedProduct]) -> Path:
        completed = datetime.now(UTC)
        retrieval = self._record_retrieval("retrieved", completed)
        decoded = {
            name: decode((self.directory / name).read_bytes()) for name in sorted(self.responses)
        }
        product = normalize(decoded)
        if product.source != self.source:
            raise Phase15SourceError("Evidence source and normalized product differ")
        content_sha256 = hashlib.sha256(
            encoded({name: value["sha256"] for name, value in self.responses.items()})
        ).hexdigest()
        manifest = {
            **retrieval,
            "evidence_state": "validated",
            "normalization_version": VERSION,
            "content_sha256": content_sha256,
            "normalized_sha256": product.sha256,
            "entity_count": len(product.entities),
            "secondary_count": len(product.secondary),
            "skipped_count": product.skipped_count,
        }
        _write(self.directory / "manifest.json", encoded(manifest))
        return self.directory


def create_bundle(
    source: str,
    responses: Mapping[str, tuple[str, bytes, Mapping[str, str]]],
    normalize: Callable[[dict[str, dict[str, Any]]], NormalizedProduct],
    *,
    root: Path = ROOT,
) -> Path:
    bundle = EvidenceBundle(source, root)
    for name, (url, body, headers) in sorted(responses.items()):
        bundle.add(name, url, body, headers)
    return bundle.validate(normalize)


def read_bundle(
    directory: Path,
    normalize: Callable[[dict[str, dict[str, Any]]], NormalizedProduct],
) -> tuple[dict[str, Any], NormalizedProduct]:
    try:
        manifest_path = directory / "manifest.json"
        retrieval_path = directory / "retrieval.json"
        if manifest_path.is_symlink() or retrieval_path.is_symlink():
            raise Phase15SourceError("Evidence metadata cannot be a symlink")
        manifest, retrieval = (
            decode(manifest_path.read_bytes()),
            decode(retrieval_path.read_bytes()),
        )
        if (
            manifest.get("evidence_state") != "validated"
            or retrieval.get("evidence_state") != "retrieved"
            or manifest.get("normalization_version") != VERSION
            or manifest.get("responses") != retrieval.get("responses")
        ):
            raise Phase15SourceError("Incomplete Phase 15 evidence bundle")
        responses = manifest.get("responses")
        if not isinstance(responses, dict):
            raise Phase15SourceError("Invalid Phase 15 evidence manifest")
        decoded: dict[str, dict[str, Any]] = {}
        checksums: dict[str, str] = {}
        expected_files = {"manifest.json", "retrieval.json", *responses}
        if {path.name for path in directory.iterdir()} != expected_files:
            raise Phase15SourceError("Unexpected Phase 15 evidence file")
        for name, metadata in responses.items():
            path = directory / name
            if path.is_symlink() or not isinstance(metadata, dict):
                raise Phase15SourceError("Invalid Phase 15 evidence response")
            body = path.read_bytes()
            checksum = hashlib.sha256(body).hexdigest()
            if (
                len(body) > MAX_FILE_BYTES
                or metadata.get("bytes") != len(body)
                or metadata.get("sha256") != checksum
            ):
                raise Phase15SourceError("Phase 15 evidence checksum mismatch")
            decoded[name] = decode(body)
            checksums[name] = checksum
        content = hashlib.sha256(encoded(checksums)).hexdigest()
        product = normalize(decoded)
        if (
            manifest.get("source") != product.source
            or manifest.get("content_sha256") != content
            or manifest.get("normalized_sha256") != product.sha256
            or manifest.get("entity_count") != len(product.entities)
            or manifest.get("secondary_count") != len(product.secondary)
            or manifest.get("skipped_count") != product.skipped_count
        ):
            raise Phase15SourceError("Phase 15 normalized evidence mismatch")
        return manifest, product
    except Phase15SourceError:
        raise
    except (KeyError, TypeError, ValueError, OSError, AttributeError) as error:
        raise Phase15SourceError("Malformed Phase 15 evidence bundle") from error


def fetch_rainfall(root: Path = ROOT, *, transport: httpx.BaseTransport | None = None) -> Path:
    urls = {
        "stations.json": f"{FLOOD_ROOT}/id/stations?parameter=rainfall&_view=full&_limit=10000",
        "readings.json": (
            f"{FLOOD_ROOT}/data/readings?parameter=rainfall&latest&_view=full&_limit=10000"
        ),
    }
    bundle = EvidenceBundle("rainfall", root)
    with httpx.Client(transport=transport, trust_env=False, timeout=120) as client:
        for name, url in urls.items():
            bundle.fetch(client, name, url)
    return bundle.validate(
        lambda value: normalize_rainfall(value["stations.json"], value["readings.json"])
    )


def fetch_bathing_waters(
    root: Path = ROOT, *, transport: httpx.BaseTransport | None = None
) -> Path:
    url = f"{BATHING_ROOT}?_pageSize=1000"
    bundle = EvidenceBundle("bathing-waters", root)
    with httpx.Client(transport=transport, trust_env=False, timeout=120) as client:
        bundle.fetch(client, "bathing-waters.json", url)
    return bundle.validate(lambda value: normalize_bathing(value["bathing-waters.json"]))


def _flood_product(value: dict[str, dict[str, Any]]) -> NormalizedProduct:
    warnings = value["warnings.json"]
    areas: list[dict[str, Any]] = []
    for area_id in sorted({text_area_id(item) for item in _ea_items(warnings)}):
        area = value[f"area-{area_id}.json"].get("items")
        polygon = value[f"polygon-{area_id}.json"]
        features = polygon.get("features")
        if (
            not isinstance(area, dict)
            or polygon.get("type") != "FeatureCollection"
            or not isinstance(features, list)
            or len(features) != 1
            or not isinstance(features[0], dict)
        ):
            raise Phase15SourceError("Invalid flood area or polygon response")
        areas.append({**area, "geometry": features[0].get("geometry")})
    return normalize_floods(warnings, {"meta": warnings.get("meta"), "items": areas})


def fetch_flood_monitoring(
    root: Path = ROOT, *, transport: httpx.BaseTransport | None = None
) -> Path:
    warnings_url = f"{FLOOD_ROOT}/id/floods?_limit=1000"
    bundle = EvidenceBundle("flood-monitoring", root)
    with httpx.Client(transport=transport, trust_env=False, timeout=120) as client:
        warnings_body = bundle.fetch(client, "warnings.json", warnings_url)
        warnings = decode(warnings_body)
        warning_items = _ea_items(warnings)
        area_ids = sorted({text_area_id(item) for item in warning_items})
        for area_id in area_ids:
            area_url = f"{FLOOD_ROOT}/id/floodAreas/{area_id}"
            bundle.fetch(client, f"area-{area_id}.json", area_url)
            polygon_url = f"{FLOOD_ROOT}/id/floodAreas/{area_id}/polygon"
            bundle.fetch(client, f"polygon-{area_id}.json", polygon_url)
    return bundle.validate(_flood_product)


def _ea_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise Phase15SourceError("Invalid flood warnings")
    return items


def text_area_id(item: dict[str, Any]) -> str:
    value = item.get("floodAreaID")
    if not isinstance(value, str) or not ID_SAFE.fullmatch(value):
        raise Phase15SourceError("Invalid flood area identity")
    return value


ID_SAFE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


def normalizer(source: str) -> Callable[[dict[str, dict[str, Any]]], NormalizedProduct]:
    functions: dict[str, Callable[[dict[str, dict[str, Any]]], NormalizedProduct]] = {
        "rainfall": lambda value: normalize_rainfall(
            value["stations.json"], value["readings.json"]
        ),
        "flood-monitoring": _flood_product,
        "bathing-waters": lambda value: normalize_bathing(value["bathing-waters.json"]),
        "company-performance": lambda value: normalize_company_performance(
            value["company-performance.json"]
        ),
    }
    try:
        return functions[source]
    except KeyError as error:
        raise Phase15SourceError("Unsupported automated Phase 15 source") from error
