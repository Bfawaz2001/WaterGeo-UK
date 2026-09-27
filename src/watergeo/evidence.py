"""Provider-neutral immutable evidence archiving for refresh jobs."""

import hashlib
import importlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from watergeo.core.config import IngestionSettings

FORMAT = "watergeo-evidence-v1"
CHUNK_SIZE = 1024 * 1024
SOURCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
Disposition = Literal["accepted", "rejected"]


class EvidenceStorageError(RuntimeError):
    """Evidence could not be proven durable and immutable."""


@dataclass(frozen=True)
class EvidenceIdentity:
    backend: Literal["local", "s3"]
    uri: str
    bundle_sha256: str
    index_sha256: str
    object_count: int
    total_bytes: int
    disposition: Disposition
    version_id: str | None = None

    def as_manifest(self) -> dict[str, str | int | None]:
        return {
            "format": FORMAT,
            "backend": self.backend,
            "uri": self.uri,
            "bundle_sha256": self.bundle_sha256,
            "index_sha256": self.index_sha256,
            "object_count": self.object_count,
            "total_bytes": self.total_bytes,
            "disposition": self.disposition,
            "version_id": self.version_id,
        }


class EvidenceStore(Protocol):
    def persist(
        self, source: str, directory: Path, *, disposition: Disposition
    ) -> EvidenceIdentity: ...


def _encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(source: str, directory: Path, disposition: Disposition) -> dict[str, Any]:
    if not SOURCE_PATTERN.fullmatch(source):
        raise EvidenceStorageError("Invalid evidence source identity")
    if directory.is_symlink() or not directory.is_dir():
        raise EvidenceStorageError("Evidence bundle must be a real directory")
    files: list[dict[str, str | int]] = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise EvidenceStorageError("Evidence bundle contains a symbolic link")
        if path.is_dir():
            continue
        if not path.is_file():
            raise EvidenceStorageError("Evidence bundle contains a non-file entry")
        relative = path.relative_to(directory).as_posix()
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise EvidenceStorageError("Unsafe evidence path")
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)})
    if not files:
        raise EvidenceStorageError("Evidence bundle is empty")
    content = {"format": FORMAT, "source": source, "disposition": disposition, "files": files}
    content["bundle_sha256"] = hashlib.sha256(_encoded(content)).hexdigest()
    return content


def _sync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_durable(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with source.open("rb") as incoming, os.fdopen(descriptor, "wb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, CHUNK_SIZE)
        outgoing.flush()
        os.fsync(outgoing.fileno())


class LocalEvidenceStore:
    """Content-addressed local archive; suitable for development and operator mounts."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _verify(self, target: Path, index: dict[str, Any], index_body: bytes) -> None:
        index_path = target / "evidence-index.json"
        if index_path.is_symlink() or index_path.read_bytes() != index_body:
            raise EvidenceStorageError("Local evidence index mismatch")
        for entry in index["files"]:
            path = target / entry["path"]
            if path.is_symlink() or not path.is_file():
                raise EvidenceStorageError("Local evidence object missing")
            if path.stat().st_size != entry["bytes"] or _sha256(path) != entry["sha256"]:
                raise EvidenceStorageError("Local evidence object checksum mismatch")

    def persist(
        self, source: str, directory: Path, *, disposition: Disposition
    ) -> EvidenceIdentity:
        index = _inventory(source, directory, disposition)
        index_body = _encoded(index)
        digest = index["bundle_sha256"]
        target = self.root / source / disposition / digest
        if target.exists():
            self._verify(target, index, index_body)
        else:
            staging = target.parent / f".{digest}.{uuid4().hex}.pending"
            staging.mkdir(parents=True, exist_ok=False)
            try:
                for entry in index["files"]:
                    _copy_durable(directory / entry["path"], staging / entry["path"])
                index_path = staging / "evidence-index.json"
                descriptor = os.open(index_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(index_body)
                    stream.flush()
                    os.fsync(stream.fileno())
                _sync_directory(staging)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.rename(staging, target)
                _sync_directory(target.parent)
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            self._verify(target, index, index_body)
        return EvidenceIdentity(
            "local",
            target.resolve().as_uri(),
            digest,
            hashlib.sha256(index_body).hexdigest(),
            len(index["files"]),
            sum(entry["bytes"] for entry in index["files"]),
            disposition,
        )


class S3EvidenceStore:
    """S3-compatible archive using versioning, conditional writes and read-back checks."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        client: Any,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client
        if self.client.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
            raise EvidenceStorageError("Evidence bucket versioning is not enabled")

    @staticmethod
    def _precondition_failed(error: BaseException) -> bool:
        response = getattr(error, "response", None)
        return isinstance(response, dict) and str(response.get("Error", {}).get("Code")) in {
            "412",
            "PreconditionFailed",
        }

    def _put_and_verify(self, key: str, body: bytes, sha256: str) -> str | None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                IfNoneMatch="*",
                Metadata={"watergeo-sha256": sha256},
            )
        except Exception as error:
            if not self._precondition_failed(error):
                raise EvidenceStorageError("S3 evidence write failed") from error
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            stored = response["Body"].read()
        except Exception as error:
            raise EvidenceStorageError("S3 evidence read-back failed") from error
        if len(stored) != len(body) or hashlib.sha256(stored).hexdigest() != sha256:
            raise EvidenceStorageError("S3 evidence read-back checksum mismatch")
        version = response.get("VersionId")
        if not isinstance(version, str) or not version:
            raise EvidenceStorageError("S3 evidence object has no version identity")
        return version

    def persist(
        self, source: str, directory: Path, *, disposition: Disposition
    ) -> EvidenceIdentity:
        index = _inventory(source, directory, disposition)
        digest = index["bundle_sha256"]
        base = "/".join(part for part in (self.prefix, source, disposition, digest) if part)
        versioned_files: list[dict[str, Any]] = []
        for entry in index["files"]:
            body = (directory / entry["path"]).read_bytes()
            version = self._put_and_verify(f"{base}/{entry['path']}", body, entry["sha256"])
            versioned_files.append({**entry, "version_id": version})
        durable_index = {**index, "files": versioned_files}
        index_body = _encoded(durable_index)
        index_sha = hashlib.sha256(index_body).hexdigest()
        index_key = f"{base}/evidence-index.json"
        version = self._put_and_verify(index_key, index_body, index_sha)
        return EvidenceIdentity(
            "s3",
            f"s3://{self.bucket}/{base}",
            digest,
            index_sha,
            len(index["files"]),
            sum(entry["bytes"] for entry in index["files"]),
            disposition,
            version,
        )


def create_evidence_store(settings: IngestionSettings) -> EvidenceStore:
    if settings.evidence_backend == "local":
        return LocalEvidenceStore(settings.evidence_local_root)
    try:
        boto3 = importlib.import_module("boto3")
    except ImportError as error:
        raise EvidenceStorageError("S3 evidence support is not installed") from error
    client = boto3.client(
        "s3",
        endpoint_url=settings.evidence_s3_endpoint,
        region_name=settings.evidence_s3_region,
        aws_access_key_id=settings.evidence_s3_access_key_id.get_secret_value()
        if settings.evidence_s3_access_key_id
        else None,
        aws_secret_access_key=settings.evidence_s3_secret_access_key.get_secret_value()
        if settings.evidence_s3_secret_access_key
        else None,
    )
    return S3EvidenceStore(
        bucket=settings.evidence_s3_bucket or "",
        prefix=settings.evidence_s3_prefix,
        client=client,
    )
