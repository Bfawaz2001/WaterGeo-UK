import io
import json
import tarfile
from pathlib import Path

import pytest

from watergeo.operations.static_evidence import (
    REQUIRED_SOURCES,
    extract,
    validate_package_directory,
)
from watergeo.operations.static_evidence_package import main, package
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


def test_static_replay_revalidates_governed_package_before_database_access(tmp_path: Path) -> None:
    sources = []
    for source in REQUIRED_SOURCES:
        directory = tmp_path / "evidence" / source
        directory.mkdir(parents=True)
        sources.append({"source": source, "evidence_directory": f"evidence/{source}"})
    plan = tmp_path / "replay.json"
    plan.write_text(json.dumps({"version": "watergeo-static-replay-v1", "sources": sources}))
    with pytest.raises(ValueError, match="evidence package manifest"):
        replay(plan)


def evidence_directories(tmp_path: Path) -> dict[str, Path]:
    result = {}
    for source in REQUIRED_SOURCES:
        directory = tmp_path / "sources" / source
        directory.mkdir(parents=True)
        (directory / "evidence.json").write_text(json.dumps({"source": source}))
        result[source] = directory
    return result


def test_complete_evidence_package_is_deterministic_and_self_validating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validated: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        "watergeo.operations.static_evidence_package.validate_source",
        lambda source, directory: validated.append((source, directory)),
    )
    sources = evidence_directories(tmp_path)
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    first_result = package(sources, first, commit="a" * 40)
    second_result = package(sources, second, commit="a" * 40)

    assert first.read_bytes() == second.read_bytes()
    assert first_result["archive_sha256"] == second_result["archive_sha256"]
    assert first_result["archive_bytes"] == first.stat().st_size
    assert [source for source, _ in validated[:10]] == list(REQUIRED_SOURCES)
    with pytest.raises(ValueError, match="already exists"):
        package(sources, first, commit="a" * 40)
    extracted = tmp_path / "extracted"
    extract(first, extracted)
    manifest = validate_package_directory(extracted)
    assert manifest["watergeo"]["commit"] == "a" * 40
    assert set(manifest["sources"]) == set(REQUIRED_SOURCES)
    assert json.loads((extracted / "replay.json").read_text())["sources"] == [
        {"source": source, "evidence_directory": f"evidence/{source}"}
        for source in REQUIRED_SOURCES
    ]


def test_package_rejects_missing_duplicate_and_unknown_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "evidence.json").write_text("{}")
    common = ["--output", str(tmp_path / "accepted-evidence.tar.gz")]

    assert main(["--source", f"unknown={source}", *common]) == 1
    assert "Each --source" in json.loads(capsys.readouterr().err)["error"]
    assert main(["--source", f"ofwat={source}", "--source", f"ofwat={source}", *common]) == 1
    assert "Duplicate" in json.loads(capsys.readouterr().err)["error"]
    assert main(["--source", f"ofwat={source}", *common]) == 1
    assert "Every required" in json.loads(capsys.readouterr().err)["error"]


def test_packager_and_extractor_reject_symlinks_and_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "watergeo.operations.static_evidence_package.validate_source",
        lambda source, directory: None,
    )
    sources = evidence_directories(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    link = sources["ofwat"] / "linked.json"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        package(sources, tmp_path / "linked.tar.gz", commit="a" * 40)
    link.unlink()

    archive = tmp_path / "accepted-evidence.tar.gz"
    package(sources, archive, commit="a" * 40)
    extracted = tmp_path / "extracted"
    extract(archive, extracted)
    (extracted / "evidence" / "rainfall" / "evidence.json").write_text("tampered")
    with pytest.raises(ValueError, match="source mismatch"):
        validate_package_directory(extracted)


def test_packager_does_not_write_archive_when_source_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = evidence_directories(tmp_path)
    output = tmp_path / "accepted-evidence.tar.gz"

    def reject_rainfall(source: str, directory: Path) -> None:
        if source == "rainfall":
            raise ValueError("invalid source manifest")

    monkeypatch.setattr(
        "watergeo.operations.static_evidence_package.validate_source", reject_rainfall
    )
    with pytest.raises(ValueError, match="invalid source manifest"):
        package(sources, output, commit="a" * 40)
    assert not output.exists()


def test_complete_replay_publishes_every_required_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = tmp_path / "replay.json"
    sources = []
    for source in REQUIRED_SOURCES:
        directory = tmp_path / "evidence" / source
        directory.mkdir(parents=True)
        sources.append({"source": source, "evidence_directory": f"evidence/{source}"})
    plan.write_text(json.dumps({"version": "watergeo-static-replay-v1", "sources": sources}))
    called: list[str] = []
    monkeypatch.setattr(
        "watergeo.operations.static_replay.validate_package_directory",
        lambda root: {},
    )

    class Engine:
        def dispose(self) -> None:
            called.append("disposed")

    monkeypatch.setattr(
        "watergeo.operations.static_replay.create_database_engine", lambda settings: Engine()
    )

    def accepted(engine: Engine, request: object, run_id: str) -> dict[str, str]:
        called.append(request.source)  # type: ignore[attr-defined]
        return {"status": "inserted", "snapshot_id": "snapshot"}

    monkeypatch.setattr("watergeo.operations.static_replay.refresh", accepted)
    replay(plan)
    assert called == [*REQUIRED_SOURCES, "disposed"]
