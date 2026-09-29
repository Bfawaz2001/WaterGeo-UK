"""Safely extract one bounded static-publication evidence archive."""

import argparse
import tarfile
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_FILES = 20_000


def extract(archive: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("Evidence extraction destination already exists")
    with tarfile.open(archive, mode="r:gz") as source:
        members = source.getmembers()
        if len(members) > MAX_FILES or sum(member.size for member in members) > MAX_ARCHIVE_BYTES:
            raise ValueError("Evidence archive exceeds reviewed limits")
        for member in members:
            path = PurePosixPath(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or member.issym()
                or member.islnk()
                or member.isdev()
            ):
                raise ValueError("Unsafe evidence archive member")
        destination.mkdir(parents=True)
        source.extractall(destination, members=members, filter="data")  # noqa: S202


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    extract(arguments.archive, arguments.destination)


if __name__ == "__main__":
    main()
