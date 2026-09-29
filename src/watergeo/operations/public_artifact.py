"""Reject private or runtime-only material in a finished public static site."""

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".map", ".svg", ".txt", ".xml"}
FORBIDDEN_PARTS = {".env", ".git", "accepted-evidence", "evidence-download"}
MAX_PAGES_BYTES = 1024 * 1024 * 1024
PATTERNS = {
    "database URL": re.compile(rb"postgres(?:ql)?://", re.IGNORECASE),
    "WaterGeo credential": re.compile(
        rb"WATERGEO_[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN)\s*[:=]", re.IGNORECASE
    ),
    "GitHub token": re.compile(
        rb"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"
    ),
    "private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "macOS user path": re.compile(rb"/Users/[^/\s]+/"),
    "GitHub runner path": re.compile(rb"/(?:home/runner/work|runner/_work|__w)/"),
    "local temporary path": re.compile(rb"/private/(?:tmp|var/folders)/"),
    "localhost API": re.compile(
        rb"http://(?:localhost|127\.0\.0\.1)(?::\d+)?/(?:v1|health|ready)(?:[/\"'?]|$)",
        re.IGNORECASE,
    ),
}


class PublicArtifactError(ValueError):
    """The candidate public site contains unsafe material."""


def validate_public_artifact(root: Path) -> dict[str, int]:
    if not root.is_dir() or root.is_symlink():
        raise PublicArtifactError("Public artifact must be one real directory")
    file_count = 0
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise PublicArtifactError(f"Public artifact contains symlink: {relative}")
        lowered = {part.casefold() for part in relative.parts}
        has_env = any(
            part.casefold() == ".env" or part.casefold().startswith(".env.")
            for part in relative.parts
        )
        if (
            has_env
            or lowered & FORBIDDEN_PARTS
            or tuple(part.casefold() for part in relative.parts[:2])
            == (
                "data",
                "raw",
            )
        ):
            raise PublicArtifactError(f"Public artifact contains private path: {relative}")
        if not path.is_file():
            continue
        file_count += 1
        total_bytes += path.stat().st_size
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        body = path.read_bytes()
        for label, pattern in PATTERNS.items():
            if pattern.search(body):
                raise PublicArtifactError(f"Public artifact contains {label}: {relative}")
    if file_count == 0:
        raise PublicArtifactError("Public artifact is empty")
    if total_bytes > MAX_PAGES_BYTES:
        raise PublicArtifactError("Public artifact exceeds the GitHub Pages site limit")
    return {"file_count": file_count, "total_bytes": total_bytes}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    result = validate_public_artifact(parser.parse_args(argv).site)
    print(json.dumps({"status": "safe", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
