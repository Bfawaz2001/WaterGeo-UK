import io
import json
from pathlib import Path

import pytest

from watergeo.evidence import EvidenceStorageError, LocalEvidenceStore, S3EvidenceStore


class PreconditionFailed(Exception):
    response = {"Error": {"Code": "PreconditionFailed"}}


class FakeS3:
    def __init__(self, *, versioning: bool = True) -> None:
        self.versioning = versioning
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.puts = 0

    def get_bucket_versioning(self, **kwargs):
        return {"Status": "Enabled" if self.versioning else "Suspended"}

    def put_object(self, **kwargs):
        key = kwargs["Key"]
        if key in self.objects:
            raise PreconditionFailed()
        self.puts += 1
        version = f"version-{self.puts}"
        self.objects[key] = (bytes(kwargs["Body"]), version)
        return {"VersionId": version}

    def get_object(self, **kwargs):
        body, version = self.objects[kwargs["Key"]]
        return {"Body": io.BytesIO(body), "VersionId": version, "ContentLength": len(body)}


def bundle(tmp_path: Path) -> Path:
    directory = tmp_path / "bundle"
    (directory / "nested").mkdir(parents=True)
    (directory / "response.json").write_bytes(b'{"ok":true}')
    (directory / "nested" / "manifest.json").write_bytes(b'{"complete":true}')
    return directory


def test_local_archive_is_content_addressed_verified_and_never_overwritten(tmp_path: Path) -> None:
    source = bundle(tmp_path)
    store = LocalEvidenceStore(tmp_path / "archive")
    first = store.persist("hydrology", source, disposition="accepted")
    second = store.persist("hydrology", source, disposition="accepted")
    assert first == second
    target = Path(first.uri.removeprefix("file://"))
    index = json.loads((target / "evidence-index.json").read_bytes())
    assert index["bundle_sha256"] == first.bundle_sha256
    assert first.object_count == 2
    (target / "response.json").write_bytes(b"changed")
    with pytest.raises(EvidenceStorageError, match="checksum"):
        store.persist("hydrology", source, disposition="accepted")


def test_archive_rejects_symlinks(tmp_path: Path) -> None:
    source = bundle(tmp_path)
    (source / "link").symlink_to(source / "response.json")
    with pytest.raises(EvidenceStorageError, match="symbolic"):
        LocalEvidenceStore(tmp_path / "archive").persist(
            "hydrology", source, disposition="rejected"
        )


def test_s3_archive_requires_versioning_and_idempotently_verifies_existing_objects(
    tmp_path: Path,
) -> None:
    source = bundle(tmp_path)
    with pytest.raises(EvidenceStorageError, match="versioning"):
        S3EvidenceStore(bucket="evidence", prefix="watergeo", client=FakeS3(versioning=False))
    client = FakeS3()
    store = S3EvidenceStore(bucket="evidence", prefix="watergeo", client=client)
    first = store.persist("thames-discharge-status", source, disposition="accepted")
    put_count = client.puts
    second = store.persist("thames-discharge-status", source, disposition="accepted")
    assert first == second
    assert client.puts == put_count
    assert first.uri.startswith("s3://evidence/watergeo/thames-discharge-status/accepted/")
    assert first.version_id is not None


def test_s3_archive_detects_changed_existing_object(tmp_path: Path) -> None:
    source = bundle(tmp_path)
    client = FakeS3()
    store = S3EvidenceStore(bucket="evidence", prefix="watergeo", client=client)
    identity = store.persist("water-quality", source, disposition="accepted")
    base = identity.uri.removeprefix("s3://evidence/")
    _, version = client.objects[f"{base}/response.json"]
    client.objects[f"{base}/response.json"] = (b"changed", version)
    with pytest.raises(EvidenceStorageError, match="checksum"):
        store.persist("water-quality", source, disposition="accepted")
