"""Build a deterministic, validated complete static-publication evidence package."""

import argparse
import gzip
import hashlib
import importlib.metadata
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from watergeo.ingestion import (
    catchment_client,
    hydrology_client,
    phase15_client,
    stream_reservoir_client,
    thames_discharge_client,
    water_quality_client,
)
from watergeo.ingestion.ofwat_canonical import decode_reviewed_water_supply
from watergeo.operations.static_evidence import (
    MAX_ARCHIVE_BYTES,
    MAX_FILES,
    PACKAGE_VERSION,
    REPLAY_VERSION,
    REQUIRED_SOURCES,
    directory_summary,
    encoded,
    extract,
)


def validate_source(source: str, directory: Path) -> None:
    if source == "ofwat":
        decode_reviewed_water_supply(raw_root=directory)
    elif source == "hydrology":
        hydrology_client.read_snapshot(directory)
    elif source == "catchments":
        catchment_client.read_snapshot(directory)
    elif source == "water-quality":
        water_quality_client.read_snapshot(directory)
    elif source == "stream-reservoir-levels":
        stream_reservoir_client.read_snapshot(directory)
    elif source == "thames-discharge-status":
        thames_discharge_client.read_snapshot(directory)
    elif source in {"rainfall", "flood-monitoring", "bathing-waters", "company-performance"}:
        phase15_client.read_bundle(directory, phase15_client.normalizer(source))
    else:
        raise ValueError(f"Unexpected static evidence source: {source}")


def current_commit() -> str:
    result = subprocess.run(
        ("/usr/bin/git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _sources(values: Sequence[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or name not in REQUIRED_SOURCES or not raw_path:
            raise ValueError("Each --source must be REQUIRED_SOURCE=EVIDENCE_DIRECTORY")
        if name in sources:
            raise ValueError(f"Duplicate static evidence source: {name}")
        sources[name] = Path(raw_path)
    if set(sources) != set(REQUIRED_SOURCES):
        missing = sorted(set(REQUIRED_SOURCES) - set(sources))
        raise ValueError(f"Every required static source must be supplied exactly once: {missing}")
    return sources


def _member(archive: tarfile.TarFile, name: str, body: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(body)
    info.mtime = 0
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    archive.addfile(info, io.BytesIO(body))


def _file_member(archive: tarfile.TarFile, name: str, path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Evidence source changed while packaging")
    info = tarfile.TarInfo(name)
    info.size = path.stat().st_size
    info.mtime = 0
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    with path.open("rb") as source:
        archive.addfile(info, source)


def package(
    source_directories: dict[str, Path], output: Path, *, commit: str | None = None
) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ValueError("Evidence package output already exists")
    if set(source_directories) != set(REQUIRED_SOURCES):
        raise ValueError("Every required static source must be supplied exactly once")
    selected_commit = commit or current_commit()
    if re.fullmatch(r"[0-9a-f]{40}", selected_commit) is None:
        raise ValueError("WaterGeo commit must be one full lowercase Git SHA")
    summaries: dict[str, dict[str, Any]] = {}
    source_files: list[tuple[str, Path]] = []
    total_files = 2
    total_bytes = 0
    for source in REQUIRED_SOURCES:
        directory = source_directories[source]
        summary = directory_summary(directory)
        validate_source(source, directory)
        summaries[source] = {"directory": f"evidence/{source}", **summary}
        total_files += int(summary["files"])
        total_bytes += int(summary["bytes"])
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                source_files.append(
                    (
                        f"evidence/{source}/{path.relative_to(directory).as_posix()}",
                        path,
                    )
                )
    if total_files > MAX_FILES or total_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError("Complete evidence package exceeds reviewed limits")
    replay = {
        "version": REPLAY_VERSION,
        "sources": [
            {"source": source, "evidence_directory": f"evidence/{source}"}
            for source in REQUIRED_SOURCES
        ],
    }
    replay_body = encoded(replay)
    manifest = {
        "format_version": PACKAGE_VERSION,
        "watergeo": {
            "commit": selected_commit,
            "version": importlib.metadata.version("watergeo-uk"),
        },
        "replay": {"path": "replay.json", "sha256": hashlib.sha256(replay_body).hexdigest()},
        "sources": summaries,
    }
    manifest_body = encoded(manifest)
    if total_bytes + len(replay_body) + len(manifest_body) > MAX_ARCHIVE_BYTES:
        raise ValueError("Complete evidence package exceeds reviewed limits")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            output.open("xb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as archive,
        ):
            _member(archive, "evidence-package.json", manifest_body)
            _member(archive, "replay.json", replay_body)
            for name, path in source_files:
                _file_member(archive, name, path)
        archive_bytes = output.stat().st_size
        if archive_bytes > MAX_ARCHIVE_BYTES:
            raise ValueError("Compressed evidence package exceeds reviewed limits")
        # Verify the exact bytes just written using the independent consumer contract.
        with tempfile.TemporaryDirectory(prefix="watergeo-static-evidence-verify-") as temporary:
            extract(output, Path(temporary) / "accepted-evidence")
        archive_digest = hashlib.sha256()
        with output.open("rb") as archive_source:
            while chunk := archive_source.read(1024 * 1024):
                archive_digest.update(chunk)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {
        "archive": str(output),
        "archive_bytes": archive_bytes,
        "archive_sha256": archive_digest.hexdigest(),
        "format_version": PACKAGE_VERSION,
        "sources": summaries,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SOURCE=EVIDENCE_DIRECTORY",
        help="Validated evidence directory; pass exactly once for each required source",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit")
    arguments = parser.parse_args(argv)
    try:
        result = package(_sources(arguments.source), arguments.output, commit=arguments.commit)
    except Exception as error:
        print(json.dumps({"status": "rejected", "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
