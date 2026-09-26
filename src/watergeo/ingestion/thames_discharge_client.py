"""Bounded fixed-host retrieval of Thames Water discharge status."""

import hashlib
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx2 as httpx

from watergeo.ingestion.thames_discharge import (
    API_VERSION,
    DOCUMENTATION_URL,
    LICENCE_URL,
    MAX_RECORDS,
    PUBLISHER,
    SOURCE_URL,
    VERSION,
    NormalizedDischargeStatus,
    ThamesDischargeError,
    decode,
    encoded,
    normalize,
)

ROOT = Path("data/raw/thames-water/discharge-status")
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
HEADERS = ("date", "etag", "last-modified", "content-type")
RETRYABLE = {429, 500, 502, 503, 504}


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_durable(path: Path, body: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _complete_bundle(directory: Path, manifest: dict[str, Any]) -> None:
    body = encoded(manifest)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ThamesDischargeError("Thames Water manifest exceeds size budget")
    pending = directory / ".manifest.json.pending"
    _write_durable(pending, body)
    os.replace(pending, directory / "manifest.json")
    _sync_directory(directory)


def _request(client: httpx.Client) -> tuple[bytes, dict[str, str]]:
    for attempt in range(3):
        if attempt:
            time.sleep(0.25 * (2 ** (attempt - 1)))
        try:
            with client.stream("GET", SOURCE_URL, follow_redirects=False) as response:
                if 300 <= response.status_code < 400:
                    raise ThamesDischargeError("Unexpected Thames Water redirect")
                if response.status_code in RETRYABLE:
                    if attempt == 2:
                        raise ThamesDischargeError("Thames Water source temporarily unavailable")
                    continue
                if response.status_code != 200:
                    raise ThamesDischargeError("Unexpected Thames Water source status")
                if (
                    response.headers.get("content-type", "").split(";")[0].lower()
                    != "application/json"
                ):
                    raise ThamesDischargeError("Unexpected Thames Water content type")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ThamesDischargeError("Thames Water response budget exceeded")
                return bytes(body), {
                    key: response.headers[key] for key in HEADERS if key in response.headers
                }
        except httpx.TransportError:
            if attempt == 2:
                raise ThamesDischargeError(
                    "Thames Water transport failed after bounded retries"
                ) from None
    raise ThamesDischargeError("Thames Water retrieval failed")


def fetch_snapshot(root: Path = ROOT, *, transport: httpx.BaseTransport | None = None) -> Path:
    directory = root / str(uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC)
    with httpx.Client(
        transport=transport,
        trust_env=False,
        timeout=httpx.Timeout(60, connect=10),
        headers={"User-Agent": "WaterGeo-UK/0.1 (public source ingestion)"},
    ) as client:
        body, headers = _request(client)
    raw_name = "response.json"
    content_sha256 = hashlib.sha256(body).hexdigest()
    completed = datetime.now(UTC)
    response = {
        "file": raw_name,
        "request_url": SOURCE_URL,
        "headers": headers,
        "bytes": len(body),
        "sha256": content_sha256,
    }
    retrieval: dict[str, Any] = {
        "evidence_state": "retrieved",
        "source": SOURCE_URL,
        "retrieval_started_at": started.isoformat(),
        "retrieval_completed_at": completed.isoformat(),
        "response": response,
        "content_sha256": content_sha256,
    }
    retrieval_body = encoded(retrieval)
    if len(retrieval_body) > MAX_MANIFEST_BYTES:
        raise ThamesDischargeError("Thames Water retrieval manifest exceeds size budget")
    _write_durable(directory / raw_name, body)
    _write_durable(directory / "retrieval.json", retrieval_body)

    data = normalize(decode(body))
    manifest: dict[str, Any] = {
        "evidence_state": "validated",
        "source": SOURCE_URL,
        "publisher": PUBLISHER,
        "licence": LICENCE_URL,
        "documentation": DOCUMENTATION_URL,
        "api_version": API_VERSION,
        "normalization_version": VERSION,
        "retrieval_started_at": retrieval["retrieval_started_at"],
        "retrieval_completed_at": retrieval["retrieval_completed_at"],
        "response": response,
        "content_sha256": content_sha256,
        "normalized_sha256": data.sha256,
        "site_count": len(data.sites),
    }
    _complete_bundle(directory, manifest)
    return directory


def read_snapshot(directory: Path) -> tuple[dict[str, Any], NormalizedDischargeStatus]:
    try:
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ThamesDischargeError("Invalid Thames Water manifest")
        manifest = decode(manifest_path.read_bytes())
        expected = {
            "evidence_state": "validated",
            "source": SOURCE_URL,
            "publisher": PUBLISHER,
            "licence": LICENCE_URL,
            "documentation": DOCUMENTATION_URL,
            "api_version": API_VERSION,
            "normalization_version": VERSION,
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ThamesDischargeError("Unsupported Thames Water evidence bundle")
        retrieval_path = directory / "retrieval.json"
        if retrieval_path.is_symlink() or retrieval_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ThamesDischargeError("Invalid Thames Water retrieval manifest")
        retrieval = decode(retrieval_path.read_bytes())
        if (
            retrieval.get("evidence_state") != "retrieved"
            or retrieval.get("source") != SOURCE_URL
            or retrieval.get("retrieval_started_at") != manifest.get("retrieval_started_at")
            or retrieval.get("retrieval_completed_at") != manifest.get("retrieval_completed_at")
            or retrieval.get("response") != manifest.get("response")
            or retrieval.get("content_sha256") != manifest.get("content_sha256")
        ):
            raise ThamesDischargeError("Thames Water retrieval evidence mismatch")
        started = datetime.fromisoformat(manifest["retrieval_started_at"])
        completed = datetime.fromisoformat(manifest["retrieval_completed_at"])
        if started.tzinfo is None or completed.tzinfo is None or started > completed:
            raise ThamesDischargeError("Invalid Thames Water retrieval timestamps")
        response = manifest["response"]
        path = directory / "response.json"
        if {entry.name for entry in directory.iterdir()} != {
            "manifest.json",
            "retrieval.json",
            "response.json",
        }:
            raise ThamesDischargeError("Unexpected Thames Water evidence file")
        if (
            path.is_symlink()
            or path.stat().st_size > MAX_RESPONSE_BYTES
            or response.get("file") != "response.json"
            or response.get("request_url") != SOURCE_URL
            or not isinstance(response.get("headers"), dict)
            or not set(response["headers"]) <= set(HEADERS)
            or not all(isinstance(value, str) for value in response["headers"].values())
        ):
            raise ThamesDischargeError("Invalid Thames Water evidence response")
        body = path.read_bytes()
        checksum = hashlib.sha256(body).hexdigest()
        if (
            len(body) > MAX_RESPONSE_BYTES
            or response.get("bytes") != len(body)
            or response.get("sha256") != checksum
            or manifest.get("content_sha256") != checksum
        ):
            raise ThamesDischargeError("Thames Water evidence checksum mismatch")
        data = normalize(decode(body))
        if (
            manifest.get("site_count") != len(data.sites)
            or manifest.get("normalized_sha256") != data.sha256
            or len(data.sites) > MAX_RECORDS
        ):
            raise ThamesDischargeError("Thames Water normalized evidence mismatch")
        return manifest, data
    except ThamesDischargeError:
        raise
    except (KeyError, TypeError, ValueError, OSError, AttributeError) as error:
        raise ThamesDischargeError("Malformed Thames Water evidence") from error
