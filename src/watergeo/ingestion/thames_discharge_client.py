"""Bounded fixed-host retrieval of Thames Water discharge status."""

import hashlib
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
    data = normalize(decode(body))
    raw_name = "response.json"
    (directory / raw_name).write_bytes(body)
    manifest: dict[str, Any] = {
        "source": SOURCE_URL,
        "publisher": PUBLISHER,
        "licence": LICENCE_URL,
        "documentation": DOCUMENTATION_URL,
        "api_version": API_VERSION,
        "normalization_version": VERSION,
        "retrieval_started_at": started.isoformat(),
        "retrieval_completed_at": datetime.now(UTC).isoformat(),
        "response": {
            "file": raw_name,
            "request_url": SOURCE_URL,
            "headers": headers,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        },
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "normalized_sha256": data.sha256,
        "site_count": len(data.sites),
    }
    (directory / "manifest.json").write_bytes(encoded(manifest))
    return directory


def read_snapshot(directory: Path) -> tuple[dict[str, Any], NormalizedDischargeStatus]:
    try:
        manifest_path = directory / "manifest.json"
        if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ThamesDischargeError("Invalid Thames Water manifest")
        manifest = decode(manifest_path.read_bytes())
        expected = {
            "source": SOURCE_URL,
            "publisher": PUBLISHER,
            "licence": LICENCE_URL,
            "documentation": DOCUMENTATION_URL,
            "api_version": API_VERSION,
            "normalization_version": VERSION,
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            raise ThamesDischargeError("Unsupported Thames Water evidence bundle")
        started = datetime.fromisoformat(manifest["retrieval_started_at"])
        completed = datetime.fromisoformat(manifest["retrieval_completed_at"])
        if started.tzinfo is None or completed.tzinfo is None or started > completed:
            raise ThamesDischargeError("Invalid Thames Water retrieval timestamps")
        response = manifest["response"]
        path = directory / "response.json"
        if {entry.name for entry in directory.iterdir()} != {"manifest.json", "response.json"}:
            raise ThamesDischargeError("Unexpected Thames Water evidence file")
        if (
            path.is_symlink()
            or response.get("file") != "response.json"
            or response.get("request_url") != SOURCE_URL
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
