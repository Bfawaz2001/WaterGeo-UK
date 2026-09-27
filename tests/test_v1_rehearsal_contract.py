from pathlib import Path

import yaml


def test_rehearsal_stack_preserves_service_identity_boundaries() -> None:
    stack = yaml.safe_load(Path("docker-compose.rehearsal.yml").read_text())
    services = stack["services"]
    assert "ports" not in services["db"]
    assert "ports" not in services["restore-db"]
    assert "ports" not in services["api"]
    assert services["edge"]["ports"] == ["127.0.0.1:${WATERGEO_REHEARSAL_PORT:-8080}:8080"]
    assert services["edge"].get("environment") is None

    api_environment = services["api"]["environment"]
    assert "WATERGEO_DB_PASSWORD" in api_environment
    assert all("MIGRATION" not in key for key in api_environment)
    assert all("INGESTION" not in key for key in api_environment)
    assert all("EVIDENCE" not in key for key in api_environment)

    migration_environment = services["migrate"]["environment"]
    assert "WATERGEO_MIGRATION_PASSWORD" in migration_environment
    assert "WATERGEO_DB_PASSWORD" not in migration_environment


def test_edge_is_same_origin_and_does_not_enable_cors_or_proxy_trust() -> None:
    nginx = Path("deploy/nginx.conf").read_text()
    assert "proxy_pass http://api:8000" in nginx
    assert "proxy_set_header Host $host" in nginx
    assert "Access-Control-Allow-Origin *" not in nginx
    assert "X-Forwarded-For" not in nginx
    assert 'Cache-Control "public, max-age=31536000, immutable"' in nginx
    assert 'Cache-Control "no-cache"' in nginx


def test_backup_rehearsal_has_destructive_safety_interlock() -> None:
    script = Path("scripts/rehearse_backup_restore.sh").read_text()
    assert "WATERGEO_DISPOSABLE_REHEARSAL:-}" in script
    assert "watergeo-v1-rehearsal-*" in script
    assert "Refusing to overwrite" in script
    assert "snapshot_signature" in script
