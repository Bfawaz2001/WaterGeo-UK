"""Validate and safely extract one governed static-publication evidence archive."""

import argparse
import hashlib
import json
import re
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_FILES = 20_000
PACKAGE_VERSION = "watergeo-static-evidence-package-v1"
REPLAY_VERSION = "watergeo-static-replay-v1"
REQUIRED_SOURCES = (
    "ofwat",
    "hydrology",
    "catchments",
    "water-quality",
    "stream-reservoir-levels",
    "thames-discharge-status",
    "rainfall",
    "flood-monitoring",
    "bathing-waters",
    "company-performance",
)


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def directory_summary(directory: Path) -> dict[str, Any]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Evidence source must be one real directory")
    files: dict[str, dict[str, Any]] = {}
    total = 0
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Evidence source cannot contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Evidence source contains an unsupported file type")
        relative = path.relative_to(directory).as_posix()
        size = path.stat().st_size
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        total += size
        if len(files) >= MAX_FILES or total > MAX_ARCHIVE_BYTES:
            raise ValueError("Evidence source exceeds package limits")
        files[relative] = {"bytes": size, "sha256": digest.hexdigest()}
    if not files:
        raise ValueError("Evidence source directory is empty")
    return {
        "bytes": total,
        "files": len(files),
        "sha256": hashlib.sha256(encoded(files)).hexdigest(),
    }


def _read_object(path: Path, description: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError(f"Invalid {description}")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid {description}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Invalid {description}")
    return value


def validate_package_directory(root: Path) -> dict[str, Any]:
    manifest = _read_object(root / "evidence-package.json", "evidence package manifest")
    replay_path = root / "replay.json"
    replay = _read_object(replay_path, "static evidence replay plan")
    sources = manifest.get("sources")
    replay_sources = replay.get("sources")
    watergeo = manifest.get("watergeo")
    if (
        manifest.get("format_version") != PACKAGE_VERSION
        or replay.get("version") != REPLAY_VERSION
        or not isinstance(watergeo, dict)
        or set(watergeo) != {"commit", "version"}
        or not isinstance(watergeo.get("commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", watergeo["commit"]) is None
        or not isinstance(watergeo.get("version"), str)
        or not watergeo["version"]
        or not isinstance(sources, dict)
        or set(sources) != set(REQUIRED_SOURCES)
        or not isinstance(replay_sources, list)
    ):
        raise ValueError("Invalid governed evidence package")
    expected_replay = [
        {"source": source, "evidence_directory": f"evidence/{source}"}
        for source in REQUIRED_SOURCES
    ]
    replay_body = replay_path.read_bytes()
    if replay_sources != expected_replay or manifest.get("replay") != {
        "path": "replay.json",
        "sha256": hashlib.sha256(replay_body).hexdigest(),
    }:
        raise ValueError("Evidence package replay plan mismatch")
    allowed_files = {"evidence-package.json", "replay.json"}
    for source in REQUIRED_SOURCES:
        metadata = sources.get(source)
        directory = root / "evidence" / source
        summary = directory_summary(directory)
        if not isinstance(metadata, dict) or metadata != {
            "directory": f"evidence/{source}",
            **summary,
        }:
            raise ValueError(f"Evidence package source mismatch: {source}")
        allowed_files.update(
            f"evidence/{source}/{path.relative_to(directory).as_posix()}"
            for path in directory.rglob("*")
            if path.is_file()
        )
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual_files != allowed_files:
        raise ValueError("Evidence package contains an unexpected file")
    return manifest


def extract(archive: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("Evidence extraction destination already exists")
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Evidence archive is missing or exceeds reviewed limits")
    try:
        with tarfile.open(archive, mode="r:gz") as source:
            members = source.getmembers()
            names = [member.name for member in members]
            if (
                len(members) > MAX_FILES
                or sum(member.size for member in members) > MAX_ARCHIVE_BYTES
            ):
                raise ValueError("Evidence archive exceeds reviewed limits")
            if len(names) != len(set(names)):
                raise ValueError("Evidence archive contains duplicate members")
            for member in members:
                path = PurePosixPath(member.name)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or member.name != path.as_posix()
                    or member.issym()
                    or member.islnk()
                    or member.isdev()
                    or not member.isfile()
                ):
                    raise ValueError("Unsafe evidence archive member")
            destination.mkdir(parents=True)
            source.extractall(destination, members=members, filter="data")  # noqa: S202
        validate_package_directory(destination)
    except Exception:
        # A rejected or partially extracted archive must never be replayable later.
        if destination.exists():
            shutil.rmtree(destination)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    extract(arguments.archive, arguments.destination)


if __name__ == "__main__":
    main()
