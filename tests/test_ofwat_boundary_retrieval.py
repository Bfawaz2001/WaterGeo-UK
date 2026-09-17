"""Tests for bounded, verified Ofwat boundary retrieval."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import replace
from pathlib import Path

import httpx2
import pytest

from watergeo.ingestion.ofwat_boundaries import (
    BoundaryRetrievalError,
    BoundarySource,
    fetch_boundary_source,
)


def _zip_bytes(
    *,
    basename: str = "WaterSupplyAreas_incNAVs v1_5",
    extensions: tuple[str, ...] = (
        ".shp",
        ".shx",
        ".dbf",
        ".prj",
    ),
    extra: tuple[tuple[str, bytes], ...] = (),
) -> bytes:
    buffer = io.BytesIO()

    with zipfile.ZipFile(
        buffer,
        "w",
        compression=zipfile.ZIP_STORED,
    ) as archive:
        for extension in extensions:
            archive.writestr(
                f"{basename}{extension}",
                f"fixture-{extension}".encode(),
            )

        for name, content in extra:
            archive.writestr(
                name,
                content,
            )

    return buffer.getvalue()


def _source(payload: bytes) -> BoundarySource:
    return BoundarySource(
        dataset="test-water-supply",
        release="test",
        release_date="2026-09",
        publisher="test publisher",
        distributor="test distributor",
        source_url=(
            "https://data.parliament.uk/resources/"
            "constituencystatistics/water/"
            "WaterSupplyAreas_incNAVsv1_5.zip"
        ),
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_bytes=len(payload),
        expected_basename="WaterSupplyAreas_incNAVs v1_5",
        licence_name="Open Government Licence",
    )


def _client(
    payload: bytes,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx2.Client:

    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status,
            stream=httpx2.ByteStream(payload),
            headers=headers,
            request=request,
        )

    return httpx2.Client(
        transport=httpx2.MockTransport(handler),
        follow_redirects=False,
    )


def test_valid_archive_is_verified_and_retained(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes()
    source = _source(payload)

    with _client(
        payload,
        headers={"Last-Modified": ("Thu, 18 Apr 2024 13:38:40 GMT")},
    ) as client:
        result = fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )

    assert result.archive_path.read_bytes() == payload
    assert result.sha256 == source.expected_sha256
    assert result.byte_count == len(payload)
    assert result.manifest_path.exists()

    assert sorted(result.archive_members) == [
        "WaterSupplyAreas_incNAVs v1_5.dbf",
        "WaterSupplyAreas_incNAVs v1_5.prj",
        "WaterSupplyAreas_incNAVs v1_5.shp",
        "WaterSupplyAreas_incNAVs v1_5.shx",
    ]


def test_repeated_verified_retrieval_preserves_existing_artifacts(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes()
    source = _source(payload)

    with _client(
        payload,
        headers={"Last-Modified": "first"},
    ) as client:
        first = fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )

    original_manifest = first.manifest_path.read_text(encoding="utf-8")
    original_inode = first.archive_path.stat().st_ino

    with _client(
        payload,
        headers={"Last-Modified": "second"},
    ) as client:
        second = fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )

    assert second.archive_path == first.archive_path
    assert second.manifest_path == first.manifest_path
    assert second.archive_path.stat().st_ino == original_inode
    assert second.manifest_path.read_text(encoding="utf-8") == original_manifest


def test_wrong_sha_is_rejected_and_partial_removed(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes()

    source = replace(
        _source(payload),
        expected_sha256="0" * 64,
    )

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="SHA-256",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )

    assert not list(tmp_path.glob("*.zip"))
    assert not list(tmp_path.glob("*.part"))


def test_missing_required_member_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes(
        extensions=(
            ".shp",
            ".shx",
            ".prj",
        )
    )

    source = _source(payload)

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="exactly four",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


def test_extra_member_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes(extra=(("README.exe", b"no"),))

    source = _source(payload)

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="exactly four",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../evil.shp",
        "/evil.shp",
        r"..\evil.shp",
    ],
)
def test_unsafe_member_paths_are_rejected(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    payload = _zip_bytes(
        extensions=(
            ".shx",
            ".dbf",
            ".prj",
        ),
        extra=((unsafe_name, b"evil"),),
    )

    source = _source(payload)

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="unsafe member path",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


def test_different_basename_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes(
        basename="Unexpected",
    )

    source = _source(payload)

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="basename",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


def test_non_zip_response_is_rejected(
    tmp_path: Path,
) -> None:
    payload = b"not a zip archive"
    source = _source(payload)

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="not a ZIP",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


def test_unapproved_hostname_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes()

    source = replace(
        _source(payload),
        source_url="https://example.com/archive.zip",
    )

    with (
        _client(payload) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="approved HTTPS Parliament host",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


def test_redirect_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes()
    source = _source(payload)

    with (
        _client(
            b"",
            status=302,
            headers={
                "Location": "https://evil.example/archive.zip",
            },
        ) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="unexpected redirect",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )


def test_declared_oversize_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _zip_bytes()
    source = _source(payload)

    with (
        _client(
            payload,
            headers={"Content-Length": str(26 * 1024 * 1024)},
        ) as client,
        pytest.raises(
            BoundaryRetrievalError,
            match="maximum permitted download size",
        ),
    ):
        fetch_boundary_source(
            source,
            raw_root=tmp_path,
            client=client,
        )
