import io
import json
import tarfile
from pathlib import Path

import pytest

from watergeo.operations.static_evidence import extract
from watergeo.operations.static_replay import replay


def test_static_archive_rejects_links_and_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as value:
        member = tarfile.TarInfo("../outside")
        body = b"private"
        member.size = len(body)
        value.addfile(member, io.BytesIO(body))
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, tmp_path / "result")
    assert not (tmp_path / "outside").exists()


def test_static_replay_requires_every_source_once_before_database_access(tmp_path: Path) -> None:
    plan = tmp_path / "replay.json"
    plan.write_text(json.dumps({"version": "watergeo-static-replay-v1", "sources": []}))
    with pytest.raises(ValueError, match="every required source exactly once"):
        replay(plan)
