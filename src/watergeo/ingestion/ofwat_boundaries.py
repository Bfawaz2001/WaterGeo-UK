"""Verified retrieval for the published Ofwat water-supply boundary snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx2

from watergeo.core.datasets import OFWAT_WATER_SUPPLY_SHA256

SOURCE_HOST = "data.parliament.uk"
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
EXPECTED_EXTENSIONS = frozenset({".shp", ".shx", ".dbf", ".prj"})


class BoundaryRetrievalError(RuntimeError):
    """Raised when a source cannot be retrieved and verified safely."""


@dataclass(frozen=True, slots=True)
class BoundarySource:
    dataset: str
    release: str
    release_date: str
    publisher: str
    distributor: str
    source_url: str
    expected_sha256: str
    expected_bytes: int
    expected_basename: str
    licence_name: str
    licence_version: str | None = None


OFWAT_WATER_SUPPLY_V1_5 = BoundarySource(
    dataset="ofwat-water-supply-areas",
    release="v1_5",
    release_date="2024-04",
    publisher="Water Services Regulation Authority (Ofwat)",
    distributor="House of Commons Library",
    source_url=(
        "https://data.parliament.uk/resources/constituencystatistics/water/"
        "WaterSupplyAreas_incNAVsv1_5.zip"
    ),
    expected_sha256=OFWAT_WATER_SUPPLY_SHA256,
    expected_bytes=15_192_919,
    expected_basename="WaterSupplyAreas_incNAVs v1_5",
    licence_name="Open Government Licence",
    licence_version=None,
)


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    archive_path: Path
    manifest_path: Path
    sha256: str
    byte_count: int
    archive_members: tuple[str, ...]


def _validate_source(source: BoundarySource) -> None:
    parsed = urlparse(source.source_url)

    if parsed.scheme != "https" or parsed.hostname != SOURCE_HOST:
        raise BoundaryRetrievalError("Source URL is not an approved HTTPS Parliament host.")

    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise BoundaryRetrievalError("Source URL contains unsupported authority components.")

    if source.expected_bytes <= 0 or source.expected_bytes > MAX_DOWNLOAD_BYTES:
        raise BoundaryRetrievalError(
            "Expected source size is outside the permitted download bound."
        )

    if len(source.expected_sha256) != 64:
        raise BoundaryRetrievalError("Expected SHA-256 fingerprint is malformed.")

    try:
        int(source.expected_sha256, 16)
    except ValueError as error:
        raise BoundaryRetrievalError("Expected SHA-256 fingerprint is malformed.") from error


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    if info.create_system != 3:
        return False

    mode = info.external_attr >> 16
    return stat.S_ISLNK(mode)


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            hasher.update(chunk)

    return hasher.hexdigest()


def _validate_archive(
    path: Path,
    source: BoundarySource,
) -> tuple[str, ...]:
    if not zipfile.is_zipfile(path):
        raise BoundaryRetrievalError("Downloaded content is not a ZIP archive.")

    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]

            if len(names) != len(set(names)):
                raise BoundaryRetrievalError("Archive contains duplicate member names.")

            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise BoundaryRetrievalError("Archive exceeds the uncompressed size limit.")

            for info in infos:
                name = info.filename
                member_path = PurePosixPath(name)

                unsafe = (
                    not name
                    or "\\" in name
                    or name.startswith("/")
                    or member_path.is_absolute()
                    or ".." in member_path.parts
                    or member_path.name != name
                )

                if unsafe:
                    raise BoundaryRetrievalError("Archive contains an unsafe member path.")

                if info.is_dir() or _is_symlink(info):
                    raise BoundaryRetrievalError("Archive contains a non-regular member.")

                if info.flag_bits & 0x1:
                    raise BoundaryRetrievalError("Encrypted archive members are not supported.")

            if len(infos) != 4:
                raise BoundaryRetrievalError("Archive must contain exactly four Shapefile members.")

            member_paths = [PurePosixPath(name) for name in names]

            extensions = {member.suffix.lower() for member in member_paths}

            stems = {member.stem for member in member_paths}

            if extensions != EXPECTED_EXTENSIONS:
                raise BoundaryRetrievalError("Archive does not contain the expected Shapefile set.")

            if stems != {source.expected_basename}:
                raise BoundaryRetrievalError(
                    "Archive member basename does not match the source contract."
                )

            bad_member = archive.testzip()

            if bad_member is not None:
                raise BoundaryRetrievalError("Archive CRC validation failed.")

    except zipfile.BadZipFile as error:
        raise BoundaryRetrievalError("Downloaded ZIP archive is corrupt.") from error

    return tuple(sorted(names))


def _write_manifest(
    destination: Path,
    source: BoundarySource,
    *,
    sha256: str,
    byte_count: int,
    members: tuple[str, ...],
    response_headers: httpx2.Headers,
) -> Path:
    manifest_path = destination / f"{sha256}.json"

    manifest: dict[str, Any] = {
        "dataset": source.dataset,
        "release": source.release,
        "release_date": source.release_date,
        "source_url": source.source_url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "sha256": sha256,
        "bytes": byte_count,
        "publisher": source.publisher,
        "distributor": source.distributor,
        "licence_name": source.licence_name,
        "licence_version": source.licence_version,
        "http": {
            "last_modified": response_headers.get("last-modified"),
            "etag": response_headers.get("etag"),
        },
        "archive_members": list(members),
    }

    fd, temporary_name = tempfile.mkstemp(
        dir=destination,
        prefix=".manifest-",
        suffix=".part",
    )

    temporary = Path(temporary_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                manifest,
                handle,
                indent=2,
                ensure_ascii=False,
                sort_keys=True,
            )
            handle.write("\n")

        os.replace(temporary, manifest_path)

    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return manifest_path


def fetch_boundary_source(
    source: BoundarySource = OFWAT_WATER_SUPPLY_V1_5,
    *,
    raw_root: Path = Path("data/raw/ofwat/water-supply"),
    client: httpx2.Client | None = None,
) -> RetrievalResult:
    """Download and verify an approved boundary archive."""

    _validate_source(source)

    raw_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    timeout = httpx2.Timeout(
        30.0,
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    owns_client = client is None

    http_client = client or httpx2.Client(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
        headers={
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "User-Agent": "WaterGeo-UK/0.1 boundary-ingestion",
        },
    )

    temporary: Path | None = None

    try:
        with http_client.stream(
            "GET",
            source.source_url,
        ) as response:
            if 300 <= response.status_code < 400:
                raise BoundaryRetrievalError("Source returned an unexpected redirect.")

            if response.status_code != 200:
                raise BoundaryRetrievalError(
                    f"Source returned unexpected HTTP status {response.status_code}."
                )

            content_encoding = response.headers.get(
                "content-encoding",
                "identity",
            ).lower()

            if content_encoding not in ("", "identity"):
                raise BoundaryRetrievalError("Compressed HTTP content encoding is not permitted.")

            content_length = response.headers.get("content-length")

            if content_length is not None:
                try:
                    declared_length = int(content_length)
                except ValueError as error:
                    raise BoundaryRetrievalError(
                        "Source returned an invalid Content-Length."
                    ) from error

                if declared_length > MAX_DOWNLOAD_BYTES:
                    raise BoundaryRetrievalError(
                        "Source exceeds the maximum permitted download size."
                    )

            hasher = hashlib.sha256()
            byte_count = 0

            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=raw_root,
                prefix=".download-",
                suffix=".part",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)

                for chunk in response.iter_raw(
                    chunk_size=CHUNK_SIZE,
                ):
                    if not chunk:
                        continue

                    byte_count += len(chunk)

                    if byte_count > MAX_DOWNLOAD_BYTES:
                        raise BoundaryRetrievalError(
                            "Source exceeded the maximum permitted download size."
                        )

                    hasher.update(chunk)
                    handle.write(chunk)

            digest = hasher.hexdigest()

            if byte_count != source.expected_bytes:
                raise BoundaryRetrievalError(
                    "Downloaded byte count does not match the reviewed source release."
                )

            if digest != source.expected_sha256:
                raise BoundaryRetrievalError(
                    "Downloaded SHA-256 does not match the reviewed source release."
                )

            members = _validate_archive(
                temporary,
                source,
            )

            archive_path = raw_root / f"{digest}.zip"
            manifest_path = raw_root / f"{digest}.json"

            if archive_path.exists() or manifest_path.exists():
                if (
                    archive_path.is_symlink()
                    or manifest_path.is_symlink()
                    or not archive_path.is_file()
                    or not manifest_path.is_file()
                ):
                    raise BoundaryRetrievalError(
                        "Existing content-addressed source state is incomplete."
                    )

                if (
                    archive_path.stat().st_size != byte_count
                    or _sha256_file(archive_path) != digest
                ):
                    raise BoundaryRetrievalError(
                        "Existing content-addressed archive failed integrity verification."
                    )

                existing_members = _validate_archive(
                    archive_path,
                    source,
                )

                if existing_members != members:
                    raise BoundaryRetrievalError(
                        "Existing archive members do not match the verified download."
                    )

                try:
                    existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise BoundaryRetrievalError(
                        "Existing retrieval manifest is unreadable."
                    ) from error

                if (
                    not isinstance(existing_manifest, dict)
                    or existing_manifest.get("dataset") != source.dataset
                    or existing_manifest.get("release") != source.release
                    or existing_manifest.get("source_url") != source.source_url
                    or existing_manifest.get("sha256") != digest
                    or existing_manifest.get("bytes") != byte_count
                    or existing_manifest.get("archive_members") != list(members)
                ):
                    raise BoundaryRetrievalError(
                        "Existing retrieval manifest does not match the verified source."
                    )

                temporary.unlink(missing_ok=True)
                temporary = None

                return RetrievalResult(
                    archive_path=archive_path,
                    manifest_path=manifest_path,
                    sha256=digest,
                    byte_count=byte_count,
                    archive_members=members,
                )

            os.replace(
                temporary,
                archive_path,
            )

            temporary = None

            manifest_path = _write_manifest(
                raw_root,
                source,
                sha256=digest,
                byte_count=byte_count,
                members=members,
                response_headers=response.headers,
            )

            return RetrievalResult(
                archive_path=archive_path,
                manifest_path=manifest_path,
                sha256=digest,
                byte_count=byte_count,
                archive_members=members,
            )

    except BoundaryRetrievalError:
        raise

    except httpx2.HTTPError as error:
        raise BoundaryRetrievalError(f"HTTP retrieval failed: {type(error).__name__}.") from None

    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

        if owns_client:
            http_client.close()
