from pathlib import Path

import pytest

from watergeo.operations.public_artifact import PublicArtifactError, validate_public_artifact


def test_public_artifact_accepts_bounded_static_site(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<script src='/WaterGeo-UK/assets/app.js'></script>")
    assets = tmp_path / "watergeo-data"
    assets.mkdir()
    (assets / "manifest.json").write_text('{"publication_id":"safe"}')
    assert validate_public_artifact(tmp_path)["file_count"] == 2


@pytest.mark.parametrize(
    ("relative", "body", "message"),
    [
        (".env", "SAFE=false", "private path"),
        (".env.production", "SAFE=false", "private path"),
        ("app.js", "postgresql://user:password@example/db", "database URL"),
        ("app.js", "WATERGEO_DB_PASSWORD=secret", "WaterGeo credential"),
        ("app.js", "-----BEGIN PRIVATE KEY-----", "private key"),
        ("app.js", "/Users/operator/private/source", "macOS user path"),
        ("app.js", "/private/tmp/build/output", "local temporary path"),
        ("app.js", "http://127.0.0.1:8000/v1/search", "localhost API"),
        ("accepted-evidence/raw.json", "{}", "private path"),
    ],
)
def test_public_artifact_rejects_private_runtime_material(
    tmp_path: Path, relative: str, body: str, message: str
) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    with pytest.raises(PublicArtifactError, match=message):
        validate_public_artifact(tmp_path)
